import numpy as np
import pytest
from sim.patches import apply_patches, CAP_QUALITY, GROUP_BASES
from sim.session import Session
from tests.conftest import MDN


def test_reference_untouched(blocks, settled):
    patched, log = apply_patches(blocks, settled)
    by = {b.idx: b for b in blocks}
    assert by[1811].srcs == [1012] and by[15411].srcs == [0x7FFFFFFF] and by[1858].hi is None
    pb = {b.idx: b for b in patched}
    assert pb[1811].srcs == [1029] and pb[15411].srcs == [231] and pb[1858].hi == CAP_QUALITY
    assert len(log) == 15


def test_patched_equals_reference_at_start():
    """Нормировка: при t = 0 patched-вариант воспроизводит исходное состояние файла."""
    S = Session(MDN, variant='patched')
    d = np.abs(np.asarray(S.vl) - S.v_ref)
    d[~np.isfinite(d)] = 0
    assert d.max() < 1e-6, int(np.argmax(d))


def test_patched_people_flow_and_cap():
    S = Session(MDN, variant='patched')
    S.set_lever(14, 30.0)
    S.run(16.0)
    v = S.vl
    for k in range(1, 14):                                  # численность ∝ занятые
        r = S.v_ref[k * 1000 + 12] / S.v_ref[k * 1000 + 29]
        assert v[k * 1000 + 811] == pytest.approx(r * v[k * 1000 + 29], rel=1e-9)
    assert v[15411] == pytest.approx(v[231] / S.v_ref[231], rel=1e-9)
    assert v[87] < 8.0 * S.v_ref[231] / v[231] * 1.01        # пособие на одного падает с ростом безработных (статья — план)
    assert all(v[b + 58] <= CAP_QUALITY + 1e-9 for b in GROUP_BASES)
    assert v[380] < 1.0 and np.isfinite(v).all()


def test_patched_baseline_quasistatic():
    S = Session(MDN, variant='patched')
    S.run(3.0)
    assert abs(S.value(380) - 0.604) < 0.05 and abs(S.value(155) / 11330 - 1) < 0.03
    S.set_variant('reference')
    assert S.variant == 'reference' and S.t == 0.0
