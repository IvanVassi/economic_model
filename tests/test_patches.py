import numpy as np
import pytest
from sim.patches import apply_patches, CAP_QUALITY, GROUP_BASES, INFLATION_BLOCKS, INDEXATION
from sim.session import Session
from tests.conftest import MDN


def test_reference_untouched(blocks, settled):
    patched, log = apply_patches(blocks, settled)
    by = {b.idx: b for b in blocks}
    assert by[1811].srcs == [1012] and by[15411].srcs == [0x7FFFFFFF] and by[1858].hi is None
    pb = {b.idx: b for b in patched}
    assert pb[1811].srcs == [1029] and pb[15411].srcs == [231] and pb[1858].hi == CAP_QUALITY
    assert len(log) == 15 + len(INFLATION_BLOCKS) + 1
    assert by[116].srcs == [0x7FFFFFFF] and pb[116].srcs == [14020]
    assert all(i not in by for i in INFLATION_BLOCKS) and all(i in pb for i in INFLATION_BLOCKS)


def test_patched_equals_reference_at_start():
    """Нормировка: при t = 0 patched-вариант воспроизводит исходное состояние файла."""
    S = Session(MDN, variant='patched')
    d = np.abs(np.asarray(S.vl) - S.v_ref)
    d[~np.isfinite(d)] = 0
    d[INFLATION_BLOCKS] = 0                                  # новых блоков в эталоне нет (D = 1, номинальный ВВП = #155)
    assert S.value(14004) == 1.0 and S.value(14017) == pytest.approx(S.value(155))
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


def test_inflation_overlay():
    """Правка inflation: без фона дефлятор ≈ 1 и реальная динамика не меняется; при фоне p установившаяся
    инфляция = p/(1−ζ); номинальный ВВП = реальный · дефлятор."""
    S = Session(MDN, variant='patched')
    S.run(3.0)
    gdp_real, d = S.value(155), S.value(14004)
    assert abs(d - 1) < 0.02 and abs(S.value(14008) - 1) < 0.05        # цены модели почти постоянны
    S.set_lever(14009, 5.0)                                             # фон 5 % в год
    S.run(12.0)
    pi = 100 * S.value(14016)
    assert abs(pi - 5.0 / (1 - INDEXATION)) < 0.5, pi                   # 10 % при ζ = 0.5
    assert S.value(14004) > 2.0                                         # дефлятор вырос
    assert S.value(14017) == pytest.approx(S.value(155) * S.value(14004), rel=1e-9)
    assert S.value(14020) == pytest.approx(1 / (1 + 0.10 * 0.5), rel=0.02)   # выплаты обесценены до индексации
    assert 0.9 < S.value(155) / gdp_real < 1.0                          # обратное влияние: спрос групп на выплатах ниже
