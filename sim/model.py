"""Кодогенерация интерпретатора: один проход по блокам в порядке idx.

Семантика типов параметризована (Semantics), чтобы проверять гипотезы:
  t4:  'clip' — clip(g·Σ, pb1, pb0);  'lag' — x' = (g·Σ − x)/T, T = pb1 (pb0 пока не используется)
  t17: 'lag'  — x' = (Σ − x)/T, T = pb0, pa0 — начальное значение (в файле состояние не сохраняется);
       'deriv' — фильтрованная производная (в статике 0)
  t23: 'id'   — тождество
Для типов 2, 3, 4, 5 первое число группы A (pa0) — усилитель g.
Тип 5: нижняя граница pa1, верхняя pb0. Тип 14: нижняя pa0, верхняя pb0.
Константный вход (NONE) = 1.
"""
from __future__ import annotations
import math
from dataclasses import dataclass

import numpy as np

from mdn import Block, NONE

ALG_TYPES = (1, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 23)


@dataclass(frozen=True)
class Semantics:
    t4: str = 'lag'
    t17: str = 'lag'
    t23: str = 'id'
    order: str = 'seq'   # 'seq' — Гаусс–Зейдель по idx (читаем уже обновлённые младшие); 'jacobi' — все читают прошлый шаг

    def state_types(self) -> tuple[int, ...]:
        st = [3, 5, 17]
        if self.t4 == 'lag':
            st.append(4)
        return tuple(st)


class DivCounter:
    __slots__ = ('zero', 'where')

    def __init__(self):
        self.zero = 0
        self.where = {}

    def div(self, a, b, i=0):
        if b != 0.0:
            return a / b
        self.zero += 1
        self.where[i] = self.where.get(i, 0) + 1
        return 0.0 if a == 0.0 else math.copysign(math.inf, a)


def _S(b: Block) -> str:
    if b.n == 0:
        return '1.0' if b.typ == 2 else '0.0'
    return ' + '.join(f'{c!r}' + ('' if s == NONE else f'*v[{s}]') for c, s in zip(b.coefs, b.srcs))


def _P(refs: list[int]) -> str:
    refs = [r for r in refs if r]
    return '*'.join(f'v[{r}]' for r in refs) if refs else '1.0'


def alg_expr(b: Block, sem: Semantics) -> str | None:
    """Выражение алгебраического блока; None для блоков состояния. Учитывает правки lo/hi (patched-вариант)."""
    e = _alg_expr(b, sem)
    if e is None or (b.lo is None and b.hi is None):
        return e
    if b.lo is not None:
        e = f'max({e}, {b.lo!r})'
    if b.hi is not None:
        e = f'min({e}, {b.hi!r})'
    return e


def _alg_expr(b: Block, sem: Semantics) -> str | None:
    t, S = b.typ, _S(b)
    if t == 1: return f'({S})'
    if t == 2: return f'P[{b.idx}]*({S})'
    if t == 4 and sem.t4 == 'clip': return f'min(max({b.pa[0]!r}*({S}), {b.pb[1]!r}), {b.pb[0]!r})'
    if t == 7: return 'min(' + ', '.join(f'v[{r}]' for r in b.ra) + ')'
    if t == 8: return 'max(' + ', '.join(f'v[{r}]' for r in b.ra) + ')'
    if t == 9: return _P(b.ra)
    if t == 10: return f'({S})*{_P(b.ra)}'
    if t == 11: return f'D({_P(b.ra)}, {_P(b.rb)}, {b.idx})'
    if t == 12: return f'D({_P(b.ra)}, ({S}), {b.idx})'
    if t == 13: return f'D(({S}), {_P(b.rb)}, {b.idx})'
    if t == 16: return f'(v[{b.rb[0]}] if ({S}) > 0.0 else v[{b.rb[1]}])'
    if t == 14: return f'min(max({S}, {b.pa[0]!r}), {b.pb[0]!r})'
    if t == 15: return f'(v[{b.rb[0]}] if ({S}) > 0.0 else 0.0)'
    if t == 23: return f'({S})'
    return None


def input_expr(b: Block) -> str:
    """«Вход» блока состояния: g·Σ для типов 3, 4, 5 (pa0 — усилитель); Σ для типа 17 (pa0 — начальное значение)."""
    if b.typ == 17:
        return f'({_S(b)})'
    g = b.pa[0] if b.pa else 1.0
    return f'{g!r}*({_S(b)})'


def state_update(b: Block, sem: Semantics) -> str:
    i, t = b.idx, b.typ
    u = input_expr(b)
    if t == 3: return f'v[{i}] = v[{i}] + dt*({u})'
    if t == 5: return f'v[{i}] = min(max(v[{i}] + dt*({u}), {b.pa[1]!r}), {b.pb[0]!r})'
    if t == 4: return f'v[{i}] = v[{i}] + dt*(({u}) - v[{i}])/{max(b.pb[1], 1e-9)!r}'
    if t == 17:
        if sem.t17 == 'lag': return f'v[{i}] = v[{i}] + dt*(({u}) - v[{i}])/{max(b.pb[0], 1e-9)!r}'
        # deriv: скрытое состояние s (лаг входа), выход = (вход − s)/T
        return f's[{i}] = s[{i}] + dt*(({u}) - s[{i}])/{max(b.pb[0], 1e-9)!r}; v[{i}] = (({u}) - s[{i}])/{max(b.pb[0], 1e-9)!r}'
    raise ValueError(t)


class Model:
    def __init__(self, blocks: list[Block], sem: Semantics = Semantics()):
        self.blocks = blocks
        self.by = {b.idx: b for b in blocks}
        self.sem = sem
        self.N = max(b.idx for b in blocks) + 1
        self.state_types = sem.state_types()
        self.state_idx = [b.idx for b in blocks if b.typ in self.state_types]
        self.alg_idx = [b.idx for b in blocks if b.typ not in self.state_types]
        self.divc = DivCounter()
        self.P = [0.0] * self.N                      # уставки типа 2 (рычаги), изменяемые на лету
        for b in blocks:
            if b.typ == 2:
                self.P[b.idx] = b.pa[0]
        self.P0 = list(self.P)
        self._compile()

    def _compile(self):
        sem = self.sem
        alg_lines = ['def alg(v, D, P):']
        for b in self.blocks:
            e = alg_expr(b, sem)
            if e is not None:
                alg_lines.append(f'    v[{b.idx}] = {e}')
        step_lines = ['def step(v, s, dt, D, P):']
        if sem.order == 'jacobi':
            step_lines.append('    u = v[:]')
        for b in self.blocks:
            if b.typ in self.state_types:
                line = state_update(b, sem)
            else:
                line = f'v[{b.idx}] = {alg_expr(b, sem)}'
            if sem.order == 'jacobi':
                lhs, rhs = line.split(' = ', 1)
                line = lhs + ' = ' + rhs.replace('v[', 'u[')
            step_lines.append('    ' + line)
        ns = {}
        exec('\n'.join(alg_lines), ns)
        exec('\n'.join(step_lines), ns)
        self._alg, self._step = ns['alg'], ns['step']
        self.source = '\n'.join(alg_lines) + '\n\n' + '\n'.join(step_lines)

    # --- состояние ---
    def initial_state(self, mode: str = 'saved') -> np.ndarray:
        """mode: 'saved' — хвостовые значения (типы 3,4,5), 'pa' — pa0 как начальное."""
        v = np.zeros(self.N, dtype=np.float64)
        for b in self.blocks:
            if b.typ in (3, 4, 5):
                v[b.idx] = b.saved if mode == 'saved' else (b.pa[0] if b.pa else 0.0)
        return v

    def set_t17(self, v: np.ndarray, mode: str = 'steady') -> None:
        """Инициализация состояния блоков типа 17: 'steady' — Σ входа (стационар), 'pa' — pa0 из файла."""
        if mode == 'pa':
            for b in self.blocks:
                if b.typ == 17:
                    v[b.idx] = b.pa[0]
        else:
            self.settle(v, iters=1, t17='passthrough')

    def set_param(self, idx: int, value: float) -> None:
        if self.by[idx].typ != 2:
            raise ValueError(f'#{idx} не уставка (тип {self.by[idx].typ})')
        self.P[idx] = float(value)

    def get_param(self, idx: int) -> float:
        return self.P[idx]

    def reset_params(self) -> None:
        self.P[:] = self.P0

    def alg(self, v) -> None:
        self._alg(v, self.divc.div, self.P)

    def settle(self, v: np.ndarray, iters: int = 30, t17: str = 'passthrough') -> list[float]:
        """Согласовать алгебраические блоки при фиксированном состоянии (Гаусс–Зейдель по idx).
        Блоки типа 17 (без сохранённого состояния) ставятся в стационар: passthrough → g·Σ, zero → 0.
        Возвращает историю max|Δ| по итерациям."""
        hist = []
        t17_blocks = [b for b in self.blocks if b.typ == 17]
        t17_fn = {}
        ns = {}
        for b in t17_blocks:
            src = f'def f(v):\n    return {input_expr(b)}\n'
            exec(src, ns)
            t17_fn[b.idx] = ns['f']
        for _ in range(iters):
            prev = v.copy()
            self._alg(v, self.divc.div, self.P)
            for b in t17_blocks:
                v[b.idx] = t17_fn[b.idx](v) if t17 == 'passthrough' else 0.0
            d = np.abs(v - prev)
            d[~np.isfinite(d)] = 0
            hist.append(float(d.max()))
            if hist[-1] < 1e-12:
                break
        return hist

    def step(self, v, s, dt: float) -> None:
        """Один шаг Эйлера; v, s — списки Python (быстрее numpy для построчного кода)."""
        self._step(v, s, dt, self.divc.div, self.P)

    def run(self, v: np.ndarray, T: float, dt: float, dt_out: float, watch: list[int] | None = None):
        """Прогон; возвращает (времена, матрица [шагов_вывода × N или × len(watch)])."""
        s = np.zeros(self.N)
        nsteps = int(round(T / dt))
        every = max(1, int(round(dt_out / dt)))
        cols = watch if watch is not None else list(range(self.N))
        out = np.empty((nsteps // every + 1, len(cols)))
        ts = np.empty(nsteps // every + 1)
        out[0] = v[cols]; ts[0] = 0.0
        k = 1
        vl = v.tolist(); sl = s.tolist()
        for n in range(1, nsteps + 1):
            self._step(vl, sl, dt, self.divc.div, self.P)
            if n % every == 0:
                out[k] = np.asarray(vl)[cols]; ts[k] = n * dt; k += 1
        v[:] = vl
        return ts[:k], out[:k]
