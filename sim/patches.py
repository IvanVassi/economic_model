"""Правки «patched»-варианта модели. Эталон (файл СНХМ) не меняется: правки применяются к копии
списка блоков перед компиляцией. Каждая правка — именованная функция со словесным обоснованием."""
from __future__ import annotations
import copy
from dataclasses import dataclass
from typing import Callable

from mdn import Block, NONE

SECTORS = range(1, 14)
GROUP_BASES = [k * 1000 + 800 for k in SECTORS] + [15100, 15200, 15300, 15400, 15500, 16100, 16200, 16300, 16400]
CAP_QUALITY = 5.0        # верхний предел индекса качества жизни группы (в исходном состоянии максимум 3.13)


@dataclass
class Patch:
    name: str
    title: str
    why: str
    apply: Callable[[dict[int, Block], "Baseline"], list[str]]


Baseline = "np.ndarray"   # согласованное исходное состояние эталона (v[idx]); правки нормируются к нему,
                          # чтобы при t = 0 patched-вариант совпадал с файлом, а менялась только динамика


def _group_size_by_employment(by: dict[int, Block], base) -> list[str]:
    log = []
    for k in SECTORS:
        b, i029 = by[k * 1000 + 811], k * 1000 + 29
        assert b.typ == 2 and b.srcs == [k * 1000 + 12], b
        ratio = float(base[k * 1000 + 12]) / float(base[i029])
        b.srcs, b.coefs = [i029], [ratio]
        b.patched = f'численность = {ratio:.4g}·занятые #{i029} (при t=0 равна файловой; было: подано труда #{k}012)'
        log.append(f'#{b.idx}: {b.patched}')
    u = by[15411]
    assert u.typ == 2 and u.srcs == [NONE], u
    u.srcs, u.coefs = [231], [1.0 / float(base[231])]
    u.patched = f'численность безработных = #231/{float(base[231]):.3g} (в единицах файла: 1 при исходной безработице; было: константа 1)'
    log.append(f'#15411: {u.patched}')
    return log


def _cap_quality_index(by: dict[int, Block], base) -> list[str]:
    log = []
    for base in GROUP_BASES:
        b = by[base + 58]
        assert b.typ == 12 and 'качество' in b.name, b
        b.hi = CAP_QUALITY
        b.patched = f'индекс качества жизни ограничен сверху {CAP_QUALITY:g}'
    log.append(f'#k858 (22 группы): верхний предел {CAP_QUALITY:g}')
    return log


PATCHES: list[Patch] = [
    Patch('group_size_by_employment', 'Численность групп по занятости',
          'Доход на одного (#k026) считается на занятых, а численность группы (#k811) бралась из «подано труда» — '
          'уволенные оставались в группе и получали доход занятых; группа безработных имела постоянную численность 1. '
          'Теперь численность группы пропорциональна занятым, а группа безработных — общему числу безработных (#231); '
          'нормировано так, что при t = 0 всё равно файлу. Статья пособий (#117) остаётся планом игрока: при росте '
          'безработицы пособие на одного падает, уровень жизни группы снижается — сигнал поднять статью.',
          _group_size_by_employment),
    Patch('cap_quality_index', 'Предел индекса качества жизни',
          'Индекс #k858 = досуг·K / (доля на питание + отношение нормы жилья к имеющемуся) не ограничен сверху, '
          'а знаменатели ограничены снизу — одна разбогатевшая группа уводила общий индекс страны с 0.6 до 1.9.',
          _cap_quality_index),
]


def apply_patches(blocks: list[Block], base, names: list[str] | None = None) -> tuple[list[Block], list[str]]:
    """Копия блоков с применёнными правками (по умолчанию все) и журнал изменений.
    base — согласованное исходное состояние эталона (Model.initial_state + settle)."""
    sel = [p for p in PATCHES if names is None or p.name in names]
    out = copy.deepcopy(blocks)
    by = {b.idx: b for b in out}
    log = []
    for p in sel:
        log += [f'[{p.name}] {line}' for line in p.apply(by, base)]
    return out, log
