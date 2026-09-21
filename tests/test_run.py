import numpy as np


def test_one_year_bounded(model, settled):
    v = settled.copy()
    ts, out = model.run(v, 1.0, 0.001, 0.1, watch=model.state_idx)
    assert np.isfinite(out).all()
    st = np.array(model.state_idx)
    rel = np.abs(v[st] - settled[st]) / np.maximum(np.abs(settled[st]), 1e-6)
    assert (rel < 1e-2).mean() > 0.9
