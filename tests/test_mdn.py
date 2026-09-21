import pytest
from mdn import NONE
from mdn.blocks import validate
from mdn.sections import read_sections, read_zadm
from tests.conftest import MDN


def test_counts(blocks):
    r = validate(blocks)
    assert r['n'] == 7993 and r['ids_unique'] and r['sorted']
    assert r['unresolved'] == []
    assert r['edges'] == 18305  # Σ-входы + ссылки групп A/B


def test_types(blocks):
    from collections import Counter
    c = Counter(b.typ for b in blocks)
    assert c == {1: 972, 2: 1085, 3: 87, 4: 576, 5: 380, 7: 137, 8: 13, 9: 1500, 10: 158,
                 11: 1395, 12: 572, 13: 82, 14: 803, 15: 141, 16: 1, 17: 69, 23: 22}


def test_state_saved_only_for_345(blocks):
    for b in blocks:
        if b.typ not in (3, 4, 5):
            assert b.saved == 0.0, b.idx


def test_proof_blocks(blocks):
    by = {b.idx: b for b in blocks}
    assert by[1029].typ == 7 and by[1029].ra == [1016, 1009]           # min(подано, требуется)
    assert by[1003].typ == 7 and len(by[1003].ra) == 8                 # min по 8 видам сырья
    assert by[1364].typ == 8 and by[1364].ra == [1215, 1225, 1235, 1245, 1255, 1265, 1275, 1285]
    assert by[1032].typ == 9 and by[1032].ra == [1029, 1031]           # ЗП = труд × ставка
    assert by[1009].typ == 10 and by[1009].ra == [1025] and by[1009].srcs == [1093]
    assert by[89].typ == 11 and by[89].ra == [42] and by[89].rb == [51]
    assert by[61].typ == 13 and by[61].rb == [1039] and by[61].coefs == pytest.approx([6.0])
    assert by[46].typ == 16 and by[46].rb == [54, 90] and by[46].srcs == [299]
    assert by[1025].typ == 5 and by[1025].pa[1] == pytest.approx(0.2) and by[1025].pb[0] == 2.5  # К сменности 0.2…2.5
    assert by[12].typ == 2 and by[12].pa[0] == 12.0 and by[12].coefs == pytest.approx([0.01]) and by[12].srcs == [NONE]
    assert by[12].editable and not by[6].editable


def test_zadm():
    z = read_zadm(read_sections(MDN))
    assert z['horizon'] == 5.0 and abs(z['dt'] - 0.001) < 1e-9 and abs(z['dt_out'] - 0.01) < 1e-9
