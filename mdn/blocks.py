"""Блоки модели (секция INFOBLKS).

Запись блока: [idx:i32][nl:u8][name:nl][typ:u8][a:u8][aa:u8][n:u8] + S слотов по 4 байта,
S = 3 + 2a + 2aa + 2n:
    slot 0            — служебный int (flag0: 0 / 12 у типа 4 / 5 у типов 15,16 / 10 у типа 23)
    slots 1..a        — числовые параметры группы A (float32)        -> pa
    slots a+1..2a     — ссылки группы A (int32, номера блоков)      -> ra
    slots ..+aa       — числовые параметры группы B (float32)        -> pb
    slots ..+aa       — ссылки группы B (int32)                      -> rb
    slots ..+n        — коэффициенты Σ-входов (float32)              -> coefs
    slots ..+n        — источники Σ-входов (int32; NONE = константа 1) -> srcs
    slots -2, -1      — сохранённое значение блока (float32; только у типов 3,4,5) и 0

Семантика типов (см. PLAN.md §1.4, уточнено по сырым данным):
    1  Σ                              2  pa0 · Σ  (уставка/усилитель; ra0 == idx — признак редактируемости)
    4  апериодическое звено: x' = (pa0·Σ − x)/T (T = pb1?; сохранённое значение = состояние)
    5  ∫pa0·Σ dt, состояние = сохранённое значение, низ pa1, верх pb0
    3  ∫pa0·Σ dt, состояние = сохранённое значение
    7  min(ra)   8  max(ra)   9  Π(ra)   10  Σ · [ra0]
    11 Π(ra)/Π(rb)   12 Π(ra)/Σ   13 Σ/Π(rb)   16 ключ: Σ>0 ? [rb0] : [rb1]
    14 clip(Σ, lo=pa0, hi=pb0)        15  ключ: [rb0], если Σ > 0, иначе 0
    17 1/(Tp+1): начальное pa0, T = pb0
    23 неизвестно (1 вход, pa0 = 10)
"""
from __future__ import annotations
import json
import struct
from dataclasses import dataclass, field, asdict

from .sections import read_sections, section_blob

NONE = 0x7FFFFFFF
STATE_TYPES = (3, 5, 17)


@dataclass
class Block:
    idx: int
    typ: int
    name: str
    a: int
    aa: int
    n: int
    flag0: int
    pa: list[float]
    ra: list[int]
    pb: list[float]
    rb: list[int]
    coefs: list[float]
    srcs: list[int]
    saved: float
    off: int = 0
    lo: float | None = None      # правка: нижний предел выхода (patched-вариант)
    hi: float | None = None      # правка: верхний предел выхода
    patched: str = ''            # описание правки, если блок изменён относительно файла

    @property
    def editable(self) -> bool:
        return self.typ == 2 and bool(self.ra) and self.ra[0] == self.idx

    @property
    def inputs(self) -> list[int]:
        """Все блоки-источники (без константы)."""
        return [s for s in self.srcs if s != NONE] + [r for r in self.ra if r] + [r for r in self.rb if r]

    def formula(self) -> str:
        f = self._formula()
        if self.lo is not None or self.hi is not None:
            f = f'clip({f}, {self.lo if self.lo is not None else "-∞"}, {self.hi if self.hi is not None else "+∞"})'
        return f

    def _formula(self) -> str:
        S = ' + '.join(f'{c:g}·' + ('1' if s == NONE else f'[{s}]') for c, s in zip(self.coefs, self.srcs)) or '0'
        RA = '·'.join(f'[{r}]' for r in self.ra if r) or '1'
        RB = '·'.join(f'[{r}]' for r in self.rb if r) or '1'
        t = self.typ
        if t == 1: return S
        if t == 2: return f'{self.pa[0]:g}·({S})'
        if t == 3: return f'∫({S}) dt, x0={self.pa[0]:g}'
        if t == 4: return f'clip({self.pa[0]:g}·({S}), {self.pb[1]:g}, {self.pb[0]:g})'
        if t == 5: return f'∫({S}) dt, x0={self.pa[0]:g}, pa1={self.pa[1]:g}, hi={self.pb[0]:g}'
        if t == 7: return 'min(' + ', '.join(f'[{r}]' for r in self.ra) + ')'
        if t == 8: return 'max(' + ', '.join(f'[{r}]' for r in self.ra) + ')'
        if t == 9: return RA
        if t == 10: return f'({S})·{RA}'
        if t == 11: return f'{RA} / {RB}'
        if t == 12: return f'{RA} / ({S})'
        if t == 13: return f'({S}) / {RB}'
        if t == 16: return f'({S}) > 0 ? [{self.rb[0]}] : [{self.rb[1]}]'
        if t == 14: return f'clip({S}, {self.pa[0]:g}, {self.pb[0]:g})'
        if t == 15: return f'({S}) > 0 ? {RB} : 0'
        if t == 17: return f'1/(Tp+1)({S}), T={self.pb[0]:g}, x0={self.pa[0]:g}'
        if t == 23: return f'?23({S}; {self.pa[0]:g})'
        return f'?{t}({S})'


def parse_blocks(blob: bytes) -> list[Block]:
    recs, p = [], 0
    while p + 9 <= len(blob):
        idx = struct.unpack_from('<I', blob, p)[0]
        nl = blob[p + 4]
        if not (1 <= idx <= 200000 and nl <= 90):
            raise ValueError(f'битая запись по смещению {p}')
        name = blob[p + 5:p + 5 + nl].decode('cp866').strip()
        q = p + 5 + nl
        typ, a, aa, n = blob[q:q + 4]
        S = 3 + 2 * a + 2 * aa + 2 * n
        L = 4 + 4 * S
        if q + L > len(blob):
            raise ValueError(f'обрезанная запись #{idx}')
        iv = list(struct.unpack_from(f'<{S}i', blob, q + 4))
        fv = list(struct.unpack_from(f'<{S}f', blob, q + 4))
        h = 1 + 2 * a + 2 * aa
        recs.append(Block(
            idx=idx, typ=typ, name=name, a=a, aa=aa, n=n, flag0=iv[0],
            pa=fv[1:1 + a], ra=iv[1 + a:1 + 2 * a],
            pb=fv[1 + 2 * a:1 + 2 * a + aa], rb=iv[1 + 2 * a + aa:1 + 2 * a + 2 * aa],
            coefs=fv[h:h + n], srcs=iv[h + n:h + 2 * n],
            saved=fv[h + 2 * n], off=p))
        p = q + L
    if p != len(blob):
        raise ValueError(f'разбор остановился на {p} из {len(blob)}')
    return recs


def load(path: str) -> list[Block]:
    return parse_blocks(section_blob(read_sections(path), 'INFOBLKS'))


def to_json(blocks: list[Block], path: str) -> None:
    json.dump([asdict(b) for b in blocks], open(path, 'w', encoding='utf-8'), ensure_ascii=False)


def validate(blocks: list[Block]) -> dict:
    ids = {b.idx for b in blocks}
    bad = [(b.idx, r) for b in blocks for r in b.inputs if r not in ids]
    return dict(n=len(blocks), ids_unique=len(ids) == len(blocks),
                sorted=[b.idx for b in blocks] == sorted(ids), unresolved=bad,
                edges=sum(len(b.inputs) for b in blocks))
