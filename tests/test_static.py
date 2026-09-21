"""Статическая согласованность семантики с сохранённым состоянием."""
import numpy as np
from sim.model import input_expr


def _gS(v, b):
    ns = {}
    exec(f'def f(v):\n    return {input_expr(b)}\n', ns)
    return ns['f'](v)


def test_settle_converges(model, settled):
    v = settled.copy()
    hist = model.settle(v, iters=3)
    assert hist[-1] < 1e-9
    assert np.isfinite(v).all()
    model.divc.zero = 0
    model.alg(v)
    assert model.divc.zero == 0


def test_type4_is_lag_steady_state(blocks, settled):
    """Сохранённое значение звена ≈ g·Σ у ≥97% блоков (не ограничитель: у clip ~38%)."""
    errs = []
    for b in blocks:
        if b.typ == 4 and b.saved != 0:
            u = _gS(settled, b)
            errs.append(abs(b.saved - u) / max(abs(b.saved), abs(u), 1e-9))
    errs = np.array(errs)
    assert (errs < 0.01).mean() > 0.97
    assert np.median(errs) < 1e-4


def test_type35_near_balance(blocks, settled):
    for t, thr in ((3, 0.95), (5, 0.99)):
        r = np.array([abs(_gS(settled, b)) / max(abs(b.saved), 1e-6) for b in blocks if b.typ == t])
        assert (r < 1e-2).mean() > thr, (t, (r < 1e-2).mean())


def test_key_values(settled):
    assert abs(settled[501] - 25.0) < 0.1        # курс 25 руб/$
    assert abs(settled[46] - 1770) < 1           # план расходов = #90
    assert abs(settled[51] - 1771) < 2           # расходы бюджета
    assert abs(settled[42] - 1770.1) < 2         # доходы бюджета
