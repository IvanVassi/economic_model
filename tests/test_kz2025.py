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
