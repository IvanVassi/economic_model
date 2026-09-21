"""Переходный процесс первого года: варианты порядка вычисления и инициализации типа 17."""
import sys, warnings; warnings.filterwarnings('ignore')
sys.path.insert(0, '/Users/ivan/code/model')
import numpy as np
from mdn import load
from sim import Model, Semantics
B = load('/Users/ivan/code/model/SNHM.MDN')
KEY = [(42, 'доходы'), (51, 'расходы'), (44, 'дефицит'), (161, '#161'), (501, 'курс'), (155, 'ВВП'), (210, 'цены'), (231, 'безраб.')]
pts = [0, 0.05, 0.1, 0.25, 0.5, 1.0]
for order in ('seq', 'jacobi'):
    for t17 in ('steady', 'pa'):
        m = Model(B, Semantics(order=order))
        v = m.initial_state('saved'); m.settle(v, iters=150)
        if t17 == 'pa': m.set_t17(v, 'pa'); m.alg(v)
        v0 = v.copy()
        ts, out = m.run(v, 1.0, 0.001, 0.01)
        st = np.array(m.state_idx)
        rel = np.abs(v[st] - v0[st]) / np.maximum(np.abs(v0[st]), 1e-6)
        print(f'\n=== order={order} t17={t17}: дрейф за год <1e-3: {(rel<1e-3).mean():.1%}, <1e-2: {(rel<1e-2).mean():.1%}; nan: {int((~np.isfinite(v)).sum())}')
        print(f"{'':10}" + ''.join(f'{f"t={t}":>10}' for t in pts))
        for i, nm in KEY:
            print(f'{nm:<10}' + ''.join(f'{out[int(round(t/0.01)), i]:>10.4g}' for t in pts))
