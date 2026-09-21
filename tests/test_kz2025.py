"""Калибровка к Казахстану-2025 и сценарий НДС 12 → 16 %."""
import copy, os, sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import kz2025 as kz  # noqa: E402


@pytest.fixture(scope='module')
def calibrated():
    return kz.calibrate(verbose=False)


def test_calibration_matches_targets(calibrated):
    s = calibrated
    gdp = s.value(155)
    assert abs(100 * s.value(42) / gdp - kz.REV_TARGET) < 0.3
    assert abs(100 * s.value(51) / gdp - kz.EXP_TARGET) < 0.3
    contrib = kz.contributions(s)
    for c, target in kz.TARGET.items():
        assert abs(contrib[c] - target) < 0.15, (c, contrib[c], target)
    assert s.lever(14) == 12 and s.lever(19) == 12


def test_vat_hike_raises_vat_and_lowers_gdp(calibrated):
    base = copy.deepcopy(calibrated)
    a = copy.deepcopy(calibrated)
    a.set_lever(14, 16); a.set_lever(19, 16)
    base.run(1.0); a.run(1.0)
    assert a.value(34) > base.value(34) * 1.15          # сбор внутреннего НДС растёт
    assert a.value(155) < base.value(155)               # ВВП ниже базы
    assert a.value(210) > base.value(210)               # розничные цены выше


def test_calibration_inflation_and_scenario_path(calibrated):
    """Сложившаяся инфляция 2025 ≈ 12.3 % (инерционный процесс); в сценарии фон снижается к 5 % — инфляция падает,
    а повышение НДС даёт дополнительную инфляцию с эффектом второго круга."""
    assert abs(kz.inflation(calibrated) - kz.INFL_TARGET) < 1.0
    base = copy.deepcopy(calibrated); a = copy.deepcopy(calibrated)
    for s in (base, a):
        kz.background_path(s, kz.INFL_TARGET, kz.INFL_LONGRUN)
    a.set_lever(14, 16); a.set_lever(19, 16)
    infl_b, infl_a = [], []
    for _ in range(5):
        base.run(1.0); a.run(1.0)
        infl_b.append(kz.inflation(base)); infl_a.append(kz.inflation(a))
    assert infl_b[0] > infl_b[-1] and 4.5 < infl_b[-1] < 7.0          # снижение к цели
    assert infl_a[0] > infl_b[0] + 3.0                                 # НДС: заметный скачок в первый год
    prim = a.value(14008) / base.value(14008) - 1                     # первичный сдвиг цен модели
    full = a.value(14018) / base.value(14018) - 1                     # с учётом второго круга
    assert full > 1.5 * prim, (prim, full)
