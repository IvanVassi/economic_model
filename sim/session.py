"""Сессия модели: модель работает «без остановки» — рычаги меняются между отрезками прогона,
история всех блоков хранится с шагом вывода."""
from __future__ import annotations
import time
from bisect import bisect_right
from dataclasses import dataclass, field

import numpy as np

from mdn import load, Block
from mdn.screens import load_screens, Screen, Frame
from .model import Model, Semantics
from .patches import apply_patches, PATCHES


@dataclass
class Event:
    t: float
    idx: int
    old: float
    new: float
    label: str = ''


@dataclass
class Schedule:
    """График изменения рычага: точки (t, значение) в модельных годах.
    До первой точки рычаг не трогается; между точками — ступенька (mode='step') или линейная
    интерполяция (mode='linear'); после последней — держится последнее значение."""
    idx: int
    points: list[tuple[float, float]]
    mode: str = 'step'
    label: str = ''

    def __post_init__(self):
        self.points = sorted((float(t), float(v)) for t, v in self.points)
        if not self.points:
            raise ValueError('график без точек')
        if self.mode not in ('step', 'linear'):
            raise ValueError(f'режим {self.mode}')
        self._ts = [t for t, _ in self.points]

    def value(self, t: float) -> float | None:
        pts = self.points
        if t < pts[0][0] - 1e-12:
            return None
        if t >= pts[-1][0]:
            return pts[-1][1]
        i = bisect_right(self._ts, t) - 1
        (t0, v0), (t1, v1) = pts[i], pts[i + 1]
        if self.mode == 'step' or t1 <= t0:
            return v0
        return v0 + (v1 - v0) * (t - t0) / (t1 - t0)


class Session:
    VARIANTS = ('reference', 'patched')

    def __init__(self, path: str, dt: float = 0.001, dt_out: float = 0.01, sem: Semantics = Semantics(),
                 variant: str = 'patched'):
        self.path, self.dt, self.dt_out, self.sem = path, dt, dt_out, sem
        self.blocks_ref: list[Block] = load(path)
        self.model_ref = Model(self.blocks_ref, sem)
        self.v_ref = self.model_ref.initial_state('saved')
        self.model_ref.settle(self.v_ref, iters=150)          # исходное состояние эталона — база для нормировки правок
        self.screens, self.frames = load_screens(path)
        self.every = max(1, int(round(dt_out / dt)))
        self.schedules: dict[int, Schedule] = {}
        self.patch_log: list[str] = []
        self.set_variant(variant, _init=True)

    def set_variant(self, variant: str, _init: bool = False) -> None:
        """'reference' — файл как есть; 'patched' — с правками sim/patches.py. Смена варианта сбрасывает модель."""
        if variant not in self.VARIANTS:
            raise ValueError(variant)
        self.variant = variant
        if variant == 'patched':
            self.blocks, self.patch_log = apply_patches(self.blocks_ref, self.v_ref)
            self.model = Model(self.blocks, self.sem)
        else:
            self.blocks, self.patch_log = self.blocks_ref, []
            self.model = self.model_ref
        self.reset()

    # --- состояние ---
    def reset(self, keep_schedules: bool = True) -> None:
        """Исходное состояние и уставки; графики рычагов по умолчанию сохраняются (эксперимент можно повторить)."""
        if not keep_schedules:
            self.schedules.clear()
        v = self.model.initial_state('saved')
        self.model.settle(v, iters=150)
        self.model.reset_params()
        self.vl = v.tolist()
        self.sl = [0.0] * self.model.N
        self.t = 0.0
        self.nstep = 0
        self.hist_t: list[float] = [0.0]
        self.hist: list[np.ndarray] = [np.asarray(self.vl, dtype=np.float32)]
        self.events: list[Event] = []

    def run(self, years: float) -> float:
        """Продвинуть модель на years лет; возвращает затраченное время, с."""
        t0 = time.time()
        n = int(round(years / self.dt))
        sched = list(self.schedules.values())
        P = self.model.P
        for _ in range(n):
            if sched:
                t = self.nstep * self.dt
                for sc in sched:
                    val = sc.value(t)
                    if val is not None and val != P[sc.idx]:
                        P[sc.idx] = val
            self.model.step(self.vl, self.sl, self.dt)
            self.nstep += 1
            if self.nstep % self.every == 0:
                self.hist_t.append(self.nstep * self.dt)
                self.hist.append(np.asarray(self.vl, dtype=np.float32))
        self.t = self.nstep * self.dt
        return time.time() - t0

    # --- рычаги ---
    def set_lever(self, idx: int, value: float, label: str = '') -> Event:
        old = self.model.get_param(idx)
        self.model.set_param(idx, value)
        ev = Event(self.t, idx, old, float(value), label or self.model.by[idx].name)
        self.events.append(ev)
        return ev

    def switch(self, block_a: int, block_b: int, choose_a: bool, label: str = '') -> list[Event]:
        """Переключатель типа 13: положение A ↔ блок A = 1, блок B = 0."""
        return [self.set_lever(block_a, 1.0 if choose_a else 0.0, label),
                self.set_lever(block_b, 0.0 if choose_a else 1.0, label)]

    def lever(self, idx: int) -> float:
        return self.model.get_param(idx)

    # --- графики рычагов ---
    def set_schedule(self, idx: int, points, mode: str = 'step', label: str = '') -> Schedule | None:
        """Задать график; пустой список точек — снять график."""
        if self.model.by[idx].typ != 2:
            raise ValueError(f'#{idx} не уставка')
        if not points:
            old = self.schedules.pop(idx, None)
            if old:
                self.events.append(Event(self.t, idx, self.lever(idx), self.lever(idx), f'график снят: {label or old.label}'))
            return None
        sc = Schedule(idx, points, mode, label or self.model.by[idx].name)
        self.schedules[idx] = sc
        self.events.append(Event(self.t, idx, self.lever(idx), sc.points[-1][1],
                                 f'график ({"плавно" if mode == "linear" else "ступенчато"}, {len(sc.points)} т.): {sc.label}'))
        val = sc.value(self.t)          # если график уже действует — применить сразу
        if val is not None:
            self.model.set_param(idx, val)
        return sc

    def clear_schedules(self) -> None:
        self.schedules.clear()

    # --- наблюдение ---
    def value(self, idx: int) -> float:
        return self.vl[idx]

    def series(self, idxs: list[int], t_from: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
        ts = np.asarray(self.hist_t)
        k0 = int(np.searchsorted(ts, t_from - 1e-12))
        H = np.stack(self.hist[k0:]) if len(self.hist) > k0 else np.empty((0, self.model.N), np.float32)
        return ts[k0:], H[:, idxs]

    def screen(self, sid: int) -> Screen:
        return next(s for s in self.screens if s.id == sid)
