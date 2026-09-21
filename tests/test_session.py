import pytest
from sim.session import Session
from tests.conftest import MDN


@pytest.fixture(scope='module')
def sess():
    return Session(MDN)


def test_run_and_lever(sess):
    sess.reset()
    sess.run(0.2)
    r0 = sess.value(42)
    sess.set_lever(14, 30.0)             # НДС 20 → 30 %
    assert sess.lever(14) == 30.0
    sess.run(0.5)
    assert sess.t == pytest.approx(0.7)
    assert sess.value(42) < r0 - 20      # доходы бюджета заметно падают
    ts, M = sess.series([42, 44], t_from=0.5)
    assert ts[0] == pytest.approx(0.5) and M.shape[1] == 2 and len(ts) == len(M)


def test_switch_and_reset(sess):
    sess.switch(299, 298, True)
    sess.run(0.3)
    assert abs(sess.value(51) - sess.value(42)) < 0.01 * sess.value(42)   # расходы следуют за доходами
    sess.reset()
    assert sess.t == 0.0 and sess.lever(14) == 20.0 and sess.lever(299) == 0.0
    assert abs(sess.value(42) - 1770.1) < 2


def test_schedule_step_and_linear(sess):
    sess.reset(keep_schedules=False)
    sess.set_schedule(14, [(0.2, 25.0), (0.4, 30.0)], 'step')          # НДС ступенями
    sess.set_schedule(15, [(0.0, 30.0), (1.0, 40.0)], 'linear')        # налог на прибыль плавно
    sess.run(0.1)
    assert sess.lever(14) == 20.0                                        # до первой точки не трогаем
    assert sess.lever(15) == pytest.approx(31.0, abs=0.02)
    sess.run(0.2)                                                        # t = 0.3
    assert sess.lever(14) == 25.0 and sess.lever(15) == pytest.approx(33.0, abs=0.02)
    sess.run(0.3)                                                        # t = 0.6
    assert sess.lever(14) == 30.0 and sess.lever(15) == pytest.approx(36.0, abs=0.02)
    sess.run(0.6)                                                        # t = 1.2, после последней точки — держим
    assert sess.lever(15) == 40.0
    assert any('график' in e.label for e in sess.events)
    sess.reset()                                                         # графики сохраняются, уставки — исходные
    assert len(sess.schedules) == 2 and sess.lever(14) == 20.0
    sess.set_schedule(14, [])                                            # снять график
    assert 14 not in sess.schedules
    sess.reset(keep_schedules=False)
    assert not sess.schedules
