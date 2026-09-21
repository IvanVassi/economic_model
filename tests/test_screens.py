from collections import Counter
from mdn.screens import load_screens
from tests.conftest import MDN


def test_frames_chain(blocks):
    screens, frames = load_screens(MDN)
    ids = {b.idx for b in blocks}
    assert len(screens) == 51 and len(frames) == 250
    assert Counter(f.kind for f in frames.values()) == {1: 167, 11: 31, 2: 44, 13: 5, 3: 3}
    items = [it for f in frames.values() for it in f.items]
    assert len(items) == 1746 and all(it.block in ids for it in items)
    assert {p.frame for s in screens for p in s.panes} <= set(frames)


def test_levers_match_settings(blocks):
    by = {b.idx: b for b in blocks}
    screens, frames = load_screens(MDN)
    levers = [it for f in frames.values() if f.is_panel for it in f.items]
    assert len(levers) == 573
    assert all(by[it.block].typ == 2 for it in levers)
    for f in frames.values():
        if f.kind in (2, 11):
            for it in f.items:
                assert abs(it.value - by[it.block].pa[0]) <= 1e-6 * max(1.0, abs(it.value))


def test_switches():
    _, frames = load_screens(MDN)
    sw = {f.id: f for f in frames.values() if f.kind == 13}
    assert sw[66].switches == [('в ограничениях', 299, 298)]
    assert sw[52].switches == [('денежная эмиссия', 191, 192)]
    assert sw[207].options == ['коридор', 'траекторя']
