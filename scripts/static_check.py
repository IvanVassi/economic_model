"""Статическая проверка семантики: состояние = сохранённые значения (типы 3,4,5), алгебра согласуется
Гауссом–Зейделем, затем: тип 4 — saved ≈ g·Σ (стационар звена); типы 3/5 — производная ≈ 0."""
import sys, argparse, collections, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '/Users/ivan/code/model')
import numpy as np
from mdn import load, NONE
from sim import Model, Semantics
from sim.model import input_expr

ap = argparse.ArgumentParser()
ap.add_argument('--t17', default='passthrough', choices=['passthrough', 'zero'])
ap.add_argument('--iters', type=int, default=150)
ap.add_argument('--top', type=int, default=10)
args = ap.parse_args()

B = load('/Users/ivan/code/model/SNHM.MDN')
m = Model(B, Semantics(t4='lag', t17='lag', t23='id'))
v = m.initial_state('saved')
hist = m.settle(v, iters=args.iters, t17=args.t17)
print(f'согласование алгебры: итераций {len(hist)}, max|Δ| в конце: {hist[-1]:.2e}; делений на ноль: {m.divc.zero}; nan/inf: {int((~np.isfinite(v)).sum())}')

ns = {}
def gS(b):
    exec(f'def f(v):\n    return {input_expr(b)}\n', ns); return ns['f'](v)
def rel(a, b):
    return abs(a - b) / max(abs(a), abs(b), 1e-9)

rows = [(b.idx, b.saved, gS(b), rel(b.saved, gS(b))) for b in B if b.typ == 4 and b.saved != 0]
r = np.array([x[3] for x in rows])
print(f'\nТИП 4 (n={len(rows)}): saved ≈ g·Σ — доля <1%: {(r<0.01).mean():.1%}, <5%: {(r<0.05).mean():.1%}, <20%: {(r<0.2).mean():.1%}, медиана {np.median(r):.3g}')
bad = [x for x in rows if x[3] > 0.05]
grp = collections.defaultdict(list)
for i, s, u, e in bad: grp[i % 1000 if i >= 1000 else i].append((i, s, u, e))
print(f'  ошибка >5% у {len(bad)} блоков; по офсетам:')
for off, L in sorted(grp.items(), key=lambda x: -len(x[1]))[:args.top + 8]:
    i, s, u, e = L[0]; b = m.by[i]
    print(f'   off {off:<4} ×{len(L):<2} #{i:<6} saved={s:<9.4g} gΣ={u:<9.4g} err={e:.2g} {b.name[:34]:34s} | {b.formula()[:62]}')

for t in (3, 5):
    rows = [(b.idx, b.saved, gS(b), abs(gS(b)) / max(abs(b.saved), 1e-6)) for b in B if b.typ == t]
    r = np.array([x[3] for x in rows])
    print(f'\nТИП {t} (n={len(rows)}): |g·Σ|/|x| — доля <1e-3: {(r<1e-3).mean():.1%}, <1e-2: {(r<1e-2).mean():.1%}, <0.1: {(r<0.1).mean():.1%}; медиана {np.median(r):.3g}')
    for x in sorted(rows, key=lambda x: -x[3])[:args.top]:
        b = m.by[x[0]]; print(f'   #{x[0]:<6} x={x[1]:<10.4g} dx/dt={x[2]:<10.3g} rel={x[3]:.2g} {b.name[:36]:36s} | {b.formula()[:66]}')
np.save('/Users/ivan/code/model/out/state_settled.npy', v)
