"""Экспорт модели в JSON/CSV/текст (замена export/export17.py с правильной раскладкой параметров)."""
from __future__ import annotations
import csv
import json
import re
import sys
from dataclasses import asdict

from .blocks import load, NONE
from .screens import load_screens, levers

TYPE_NAME = {1: 'Σ', 2: 'уставка·Σ', 3: '∫', 4: '1/(Tp+1)·g', 5: '∫ с пределами', 7: 'min', 8: 'max', 9: 'Π',
             10: 'Σ·[ref]', 11: 'Π/Π', 12: 'Π/Σ', 13: 'Σ/Π', 14: 'clip Σ', 15: 'ключ', 16: 'ключ 2-поз.',
             17: '1/(Tp+1)', 23: '?23'}


def clean_title(t: str) -> str:
    return re.sub(r'^\s*[Тт][Рр]\s*17\s*', '', t).strip(' .')


def export(mdn_path: str, out_dir: str) -> None:
    B = load(mdn_path)
    by = {b.idx: b for b in B}
    json.dump([asdict(b) | {'formula': b.formula(), 'editable': b.editable} for b in B],
              open(f'{out_dir}/model_blocks.json', 'w', encoding='utf-8'), ensure_ascii=False)
    with open(f'{out_dir}/model_blocks.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['idx', 'type', 'type_name', 'name', 'formula', 'pa', 'ra', 'pb', 'rb', 'coefs', 'srcs', 'saved', 'editable'])
        for b in B:
            w.writerow([b.idx, b.typ, TYPE_NAME.get(b.typ, '?'), b.name, b.formula(),
                        ';'.join(f'{x:g}' for x in b.pa), ';'.join(map(str, b.ra)), ';'.join(f'{x:g}' for x in b.pb),
                        ';'.join(map(str, b.rb)), ';'.join(f'{x:g}' for x in b.coefs),
                        ';'.join('const' if s == NONE else str(s) for s in b.srcs), f'{b.saved:g}', int(b.editable)])
    with open(f'{out_dir}/model_blocks.txt', 'w', encoding='utf-8') as fh:
        fh.write(f'МОДЕЛЬ «Управление страной» ({mdn_path}); блоков {len(B)}\n\n')
        for b in B:
            fh.write(f'#{b.idx:<6} [{TYPE_NAME.get(b.typ, b.typ):<14}] {b.name or "(без имени)"}\n')
            fh.write(f'         = {b.formula()}\n')
            if b.typ in (3, 4, 5):
                fh.write(f'         состояние = {b.saved:g}\n')
            ins = [s for s in b.inputs if s in by]
            if ins:
                fh.write('         входы: ' + ', '.join(f'#{s} {by[s].name[:30]}' for s in ins[:8]) + ('…' if len(ins) > 8 else '') + '\n')
            fh.write('\n')
    screens, frames = load_screens(mdn_path)
    lv = levers(screens, frames)
    with open(f'{out_dir}/model_screens.txt', 'w', encoding='utf-8') as fh:
        for s in screens:
            fh.write(f'=== ЭКРАН {s.id}: {clean_title(s.title)}\n')
            for pn in s.panes:
                slot, fid = pn.slot, pn.frame
                f = frames.get(fid)
                if not f:
                    fh.write(f'   [{slot}] фрейм {fid} — не разобран\n'); continue
                fh.write(f'   [{slot}] фрейм {fid} {"ПАНЕЛЬ" if f.is_panel else "график"} «{f.title}»\n')
                for it in f.items:
                    blk, lab = it.block, it.label
                    fh.write(f'        {lab[:42]:42s} -> ' + (f'#{blk} t{by[blk].typ} {by[blk].name[:40]}' if blk in by else '?') + '\n')
            fh.write('\n')
    print(f'блоков {len(B)}, экранов {len(screens)}, фреймов {len(frames)}, рычагов на панелях {sum(len(v) for v in lv.values())}')


if __name__ == '__main__':
    export(sys.argv[1] if len(sys.argv) > 1 else '/Users/ivan/code/model/SNHM.MDN',
           sys.argv[2] if len(sys.argv) > 2 else '/Users/ivan/code/model/export')
