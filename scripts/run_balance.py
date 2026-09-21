"""Прогон эталона из сохранённого состояния: дрейф переменных состояния за T лет."""
import sys, time, argparse, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '/Users/ivan/code/model')
import numpy as np
from mdn import load
from sim import Model, Semantics

ap = argparse.ArgumentParser()
ap.add_argument('--T', type=float, default=1.0)
ap.add_argument('--dt', type=float, default=0.001)
ap.add_argument('--out', type=float, default=0.01)
ap.add_argument('--top', type=int, default=15)
ap.add_argument('--save', default='')
args = ap.parse_args()

B = load('/Users/ivan/code/model/SNHM.MDN')
m = Model(B, Semantics(t4='lag', t17='lag', t23='id'))
v = m.initial_state('saved'); m.settle(v, iters=150)
v0 = v.copy()
st = m.state_idx
t0 = time.time()
ts, out = m.run(v, args.T, args.dt, args.out, watch=st)
el = time.time() - t0
print(f'прогон T={args.T} dt={args.dt}: {len(ts)-1} точек вывода, {el:.1f} с ({el/(args.T/args.dt)*1e3:.2f} мс/шаг); делений на ноль: {m.divc.zero}; nan/inf: {int((~np.isfinite(v)).sum())}')
x0 = v0[st]; x1 = v[st]
rel = np.abs(x1 - x0) / np.maximum(np.abs(x0), 1e-6)
print(f'дрейф состояния ({len(st)} блоков): доля <1e-4: {(rel<1e-4).mean():.1%}, <1e-3: {(rel<1e-3).mean():.1%}, <1e-2: {(rel<1e-2).mean():.1%}, <0.1: {(rel<0.1).mean():.1%}; медиана {np.median(rel):.2g}')
order = np.argsort(-rel)
print('наибольший дрейф:')
for k in order[:args.top]:
    b = m.by[st[k]]
    traj = out[:, k]
    print(f'  #{st[k]:<6} t{b.typ} x0={x0[k]:<10.4g} xT={x1[k]:<10.4g} rel={rel[k]:<8.2g} min={traj.min():<9.4g} max={traj.max():<9.4g} {b.name[:34]:34s} | {b.formula()[:50]}')
if args.save:
    np.savez(args.save, ts=ts, out=out, idx=np.array(st), v0=v0, vT=v)
