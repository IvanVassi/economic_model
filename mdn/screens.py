"""Экраны (INFOPICT) и фреймы (INFOFR15) — строгий последовательный разбор.

Фрейм: [id:i32][kind:u8][a:i32][b:i32][len:i32][title:len] + тело по kind:
  1  график:      [0:i32][xscale:f32][0:i32][n:i32] + n × [block:i32][ymin:f32][ymax:f32][len:i32][label]
  2  панель:      [n:i32] + n × [block:i32][value:f32][len:i32][label] + n × i32 + n × vmin:f32 + n × vmax:f32
  3  гистограмма: [0:i32][f:f32][f:f32][f:f32][len:i32][xlabel][f:f32][f:f32][n:i32] + n × [block:i32][len:i32][label]
  11 панель:      [0:i32][f:f32][n:i32] + n × [block:i32][value:f32][vmin:f32][vmax:f32][i:i32][len:i32][label][7 × i32/f32] + n × i32
  13 переключатель: [len][optA][len][optB][i32×3][n:i32] + n × [len][caption][blockA:i32][blockB:i32][i32×3]
     (положение A активно, когда блок A = 1, B = 0; переключение — обмен единицы между блоками)
Экран: [id:i32][len:i32][title][npan:i32] + npan × [slot:i32][x0:i32][y0:i32][x1:i32][y1:i32][frame:i32].
"""
from __future__ import annotations
import struct
from dataclasses import dataclass, field

from .sections import read_sections, section_blob

PANEL_KINDS = (2, 11, 13)


@dataclass
class Item:
    block: int
    label: str
    value: float | None = None   # текущее значение рычага (панели)
    vmin: float | None = None    # диапазон рычага (тип 11) или шкала графика
    vmax: float | None = None


@dataclass
class Frame:
    id: int
    kind: int
    a: int
    b: int
    title: str
    items: list[Item] = field(default_factory=list)
    options: list[str] = field(default_factory=list)              # тип 13: подписи двух положений
    switches: list[tuple[str, int, int]] = field(default_factory=list)  # тип 13: (подпись, блок положения A, блок положения B)
    xlabel: str = ''
    off: int = 0

    @property
    def is_panel(self) -> bool:
        return self.kind in PANEL_KINDS


@dataclass
class Pane:
    slot: int
    x0: int
    y0: int
    x1: int
    y1: int
    frame: int


@dataclass
class Screen:
    id: int
    title: str
    panes: list[Pane]


class _R:
    def __init__(self, b: bytes, p: int = 0):
        self.b, self.p = b, p

    def i(self) -> int:
        v = struct.unpack_from('<i', self.b, self.p)[0]; self.p += 4; return v

    def f(self) -> float:
        v = struct.unpack_from('<f', self.b, self.p)[0]; self.p += 4; return v

    def u8(self) -> int:
        v = self.b[self.p]; self.p += 1; return v

    def s(self) -> str:
        n = self.i()
        if not (0 <= n <= 200):
            raise ValueError(f'длина строки {n} @ {self.p - 4}')
        v = self.b[self.p:self.p + n].decode('cp866', 'replace'); self.p += n; return v.strip()


def parse_frames(fr: bytes) -> dict[int, Frame]:
    r = _R(fr); frames = {}
    while r.p + 17 <= len(fr):
        off = r.p
        fid, kind, a, b = r.i(), r.u8(), r.i(), r.i()
        title = r.s()
        F = Frame(fid, kind, a, b, title, off=off)
        if kind == 1:
            r.i(); r.f(); r.i(); n = r.i()
            for _ in range(n):
                blk, lo, hi = r.i(), r.f(), r.f(); lab = r.s()
                F.items.append(Item(blk, lab, None, lo, hi))
        elif kind == 2:
            n = r.i()
            for _ in range(n):
                blk, val = r.i(), r.f(); lab = r.s()
                F.items.append(Item(blk, lab, val))
            flags = [r.i() for _ in range(n)]
            lo = [r.f() for _ in range(n)]
            hi = [r.f() for _ in range(n)]
            for it, a_, b_ in zip(F.items, lo, hi):
                it.vmin, it.vmax = a_, b_
        elif kind == 3:
            r.i(); r.f(); r.f(); r.f(); F.xlabel = r.s(); r.f(); r.f(); n = r.i()
            for _ in range(n):
                blk = r.i(); lab = r.s()
                F.items.append(Item(blk, lab))
        elif kind == 11:
            r.i(); r.f(); n = r.i()
            for _ in range(n):
                blk, val, lo, hi, _x = r.i(), r.f(), r.f(), r.f(), r.i(); lab = r.s()
                for _ in range(7): r.i()          # хвост элемента: 1,1,1,0,0,0,value
                F.items.append(Item(blk, lab, val, lo, hi))
            for _ in range(n): r.i()              # хвост фрейма: n нулей
        elif kind == 13:
            F.options = [r.s(), r.s()]
            r.i(); r.i(); r.i(); n = r.i()
            for _ in range(n):
                cap = r.s(); ba, bb = r.i(), r.i(); r.i(); r.i(); r.i()
                F.switches.append((cap, ba, bb))
                F.items += [Item(ba, f'{cap}: {F.options[0]}'), Item(bb, f'{cap}: {F.options[1]}')]
        else:
            raise ValueError(f'неизвестный тип фрейма {kind} (id {fid}) @ {off}')
        frames[fid] = F
    if r.p != len(fr):
        raise ValueError(f'остаток {len(fr) - r.p} байт')
    return frames


def parse_screens(pic: bytes) -> list[Screen]:
    r = _R(pic); screens = []
    while r.p + 8 < len(pic):
        sid = r.i(); title = r.s(); n = r.i()
        panes = [Pane(r.i(), r.i(), r.i(), r.i(), r.i(), r.i()) for _ in range(n)]
        screens.append(Screen(sid, title, panes))
    return screens


def load_screens(path: str) -> tuple[list[Screen], dict[int, Frame]]:
    sec = read_sections(path)
    return parse_screens(section_blob(sec, 'INFOPICT')), parse_frames(section_blob(sec, 'INFOFR15'))


def levers(screens: list[Screen], frames: dict[int, Frame]) -> dict[int, list[tuple[int, str, str]]]:
    """экран → [(блок, подпись, заголовок панели)] для панелей управления."""
    out = {}
    for s in screens:
        L = []
        for p in s.panes:
            f = frames.get(p.frame)
            if f and f.is_panel:
                L += [(it.block, it.label, f.title) for it in f.items]
        if L:
            out[s.id] = L
    return out
