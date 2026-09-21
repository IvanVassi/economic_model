"""Локальный веб-интерфейс модели: 51 экран, панели рычагов, графики.
Запуск: python3 -m ui.server [--port 8765] [--mdn путь]"""
from __future__ import annotations
import argparse
import json
import math
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sim.session import Session  # noqa: E402
from sim.patches import PATCHES  # noqa: E402

STATIC = Path(__file__).resolve().parent / 'static'
SESSION: Session | None = None
LOCK = threading.Lock()
GRID = dict(x0=0, x1=640, y0=22, y1=458)   # поле экрана оригинала (640×480, строка заголовка сверху)


def _num(x):
    x = float(x)
    return None if (math.isnan(x) or math.isinf(x)) else x


def _title(s: str) -> str:
    return re.sub(r'^\s*[Тт][Рр]\s*17\s*', '', s).strip(' .')


def screen_group(sid: int) -> str:
    if sid <= 3: return 'Макроэкономика'
    if sid <= 10: return 'Бюджет'
    if sid <= 18: return 'Финансы и ВЭД'
    if sid <= 24: return 'Производство и труд'
    if sid <= 36: return 'Секторы'
    if sid <= 44: return 'Социальные группы'
    if sid <= 48: return 'Инвестиции и ресурсы'
    return 'Демография и оборона'


def screens_json():
    S = SESSION
    return [dict(id=s.id, title=_title(s.title), group=screen_group(s.id),
                 has_panel=any(SESSION.frames[p.frame].is_panel for p in s.panes)) for s in S.screens]


def screen_json(sid: int):
    S = SESSION; s = S.screen(sid); by = S.model.by
    panes = []
    last_title: dict[int, str] = {}          # безымянные фреймы — продолжение предыдущего того же типа (экран 2: сектора 7–13)
    for p in sorted(s.panes, key=lambda q: q.slot):
        f = S.frames[p.frame]
        title = f.title
        if not title and f.kind in last_title:
            labs = [it.label.lstrip('!').strip() for it in f.items if it.label.strip()]
            span = f': {labs[0]} … {labs[-1]}' if len(labs) > 1 else (f': {labs[0]}' if labs else '')
            title = f'{last_title[f.kind]} (продолжение{span})'
        elif title:
            last_title[f.kind] = title
        box = dict(x=(p.x0 - GRID['x0']) / (GRID['x1'] - GRID['x0']), y=(p.y0 - GRID['y0']) / (GRID['y1'] - GRID['y0']),
                   w=(p.x1 - p.x0) / (GRID['x1'] - GRID['x0']), h=(p.y1 - p.y0) / (GRID['y1'] - GRID['y0']))
        items = []
        for it in f.items:
            b = by[it.block]
            sc = S.schedules.get(it.block)
            items.append(dict(block=it.block, label=it.label, name=b.name, typ=b.typ,
                              value=(S.lever(it.block) if f.kind in (2, 11) else None),
                              default=(S.model.P0[it.block] if f.kind in (2, 11) else None),
                              schedule=(dict(mode=sc.mode, points=sc.points) if sc else None),
                              vmin=it.vmin, vmax=it.vmax, cur=_num(S.value(it.block))))
        fr = dict(id=f.id, kind=f.kind, title=title, items=items, xlabel=f.xlabel)
        if f.kind == 13:
            fr['options'] = f.options
            fr['switches'] = [dict(caption=c, a=a, b=b_, state_a=(S.lever(a) > 0.5)) for c, a, b_ in f.switches]
        panes.append(dict(slot=p.slot, box=box, frame=fr))
    panes.sort(key=lambda q: (q['box']['y'], q['box']['x']))
    return dict(id=s.id, title=_title(s.title), panes=panes, t=S.t)


def series_json(blocks: list[int], t_from: float):
    ts, M = SESSION.series(blocks, t_from)
    return dict(t=[round(float(x), 4) for x in ts],
                series={str(b): [_num(v) for v in M[:, k]] for k, b in enumerate(blocks)})


def schedules_json():
    S = SESSION
    return [dict(block=sc.idx, label=sc.label, name=S.model.by[sc.idx].name, mode=sc.mode, points=sc.points,
                 current=S.lever(sc.idx)) for sc in S.schedules.values()]


def state_json():
    S = SESSION
    return dict(t=S.t, dt=S.dt, dt_out=S.dt_out, n_blocks=len(S.blocks), n_schedules=len(S.schedules),
                variant=S.variant, patches=[dict(name=p.name, title=p.title, why=p.why) for p in PATCHES],
                patch_log=S.patch_log,
                events=[dict(t=e.t, block=e.idx, old=e.old, new=e.new, label=e.label) for e in S.events[-200:]])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # тише: не логировать API-запросы
        if args and '/api/' in str(args[0]):
            return
        super().log_message(fmt, *args)

    def do_HEAD(self):
        self.send_response(200); self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204); self.end_headers()

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path: Path, ctype: str):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        try:
            if u.path in ('/', '/index.html'):
                return self._file(STATIC / 'index.html', 'text/html; charset=utf-8')
            if u.path.startswith('/static/'):
                p = (STATIC / u.path[len('/static/'):]).resolve()
                if STATIC in p.parents and p.exists():
                    ctype = {'.js': 'application/javascript', '.css': 'text/css', '.html': 'text/html'}.get(p.suffix, 'application/octet-stream')
                    return self._file(p, ctype + '; charset=utf-8')
                return self._json({'error': 'not found'}, 404)
            with LOCK:
                if u.path == '/api/screens':
                    return self._json(screens_json())
                m = re.match(r'^/api/screen/(\d+)$', u.path)
                if m:
                    return self._json(screen_json(int(m.group(1))))
                if u.path == '/api/series':
                    blocks = [int(x) for x in q.get('blocks', [''])[0].split(',') if x]
                    return self._json(series_json(blocks, float(q.get('from', ['0'])[0])))
                if u.path == '/api/state':
                    return self._json(state_json())
                if u.path == '/api/schedules':
                    return self._json(schedules_json())
                if u.path == '/api/block':
                    b = SESSION.model.by[int(q['id'][0])]
                    return self._json(dict(idx=b.idx, typ=b.typ, name=b.name, formula=b.formula(), inputs=b.inputs,
                                           value=_num(SESSION.value(b.idx))))
            return self._json({'error': 'not found'}, 404)
        except Exception as e:  # noqa: BLE001
            return self._json({'error': repr(e)}, 500)

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        body = json.loads(self.rfile.read(n) or b'{}')
        try:
            with LOCK:
                if self.path == '/api/run':
                    years = float(body.get('years', 1.0))
                    years = max(0.0, min(years, 50.0))
                    el = SESSION.run(years)
                    return self._json(dict(t=SESSION.t, elapsed=el))
                if self.path == '/api/lever':
                    ev = SESSION.set_lever(int(body['block']), float(body['value']), body.get('label', ''))
                    return self._json(dict(t=ev.t, block=ev.idx, old=ev.old, new=ev.new))
                if self.path == '/api/switch':
                    evs = SESSION.switch(int(body['a']), int(body['b']), bool(body['choose_a']), body.get('label', ''))
                    return self._json(dict(events=[dict(block=e.idx, new=e.new) for e in evs]))
                if self.path == '/api/reset':
                    SESSION.reset(keep_schedules=bool(body.get('keep_schedules', True)))
                    return self._json(dict(t=SESSION.t))
                if self.path == '/api/schedule':
                    sc = SESSION.set_schedule(int(body['block']), body.get('points') or [], body.get('mode', 'step'), body.get('label', ''))
                    return self._json(dict(ok=True, schedule=(dict(mode=sc.mode, points=sc.points) if sc else None), value=SESSION.lever(int(body['block']))))
                if self.path == '/api/variant':
                    SESSION.set_variant(str(body.get('variant', 'reference')))
                    return self._json(dict(variant=SESSION.variant, t=SESSION.t, patch_log=SESSION.patch_log))
                if self.path == '/api/schedules/clear':
                    SESSION.clear_schedules()
                    return self._json(dict(ok=True))
            return self._json({'error': 'not found'}, 404)
        except Exception as e:  # noqa: BLE001
            return self._json({'error': repr(e)}, 500)


def main():
    global SESSION
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--mdn', default=str(Path(__file__).resolve().parent.parent / 'SNHM.MDN'))
    a = ap.parse_args()
    SESSION = Session(a.mdn)
    srv = ThreadingHTTPServer(('127.0.0.1', a.port), Handler)
    print(f'Сложная народнохозяйственная модель: http://127.0.0.1:{a.port}/  (блоков {len(SESSION.blocks)}, экранов {len(SESSION.screens)})', flush=True)
    srv.serve_forever()


if __name__ == '__main__':
    main()
