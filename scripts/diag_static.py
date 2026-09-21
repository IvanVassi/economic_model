import sys, collections, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '/Users/ivan/code/model')
import numpy as np
from mdn import load, NONE
from sim import Model, Semantics
B = load('/Users/ivan/code/model/SNHM.MDN')
m = Model(B, Semantics(t4='lag', t17='lag'))
v = m.initial_state('saved')
# итерации вручную, чтобы поймать последние дельты
prev = None
for it in range(40):
    prev = v.copy(); m.settle(v, iters=1)
d = np.abs(v - prev); d[~np.isfinite(d)] = 0
print("=== 15 блоков с наибольшим |Δ| на последней итерации ===")
for i in np.argsort(-d)[:15]:
    b = m.by[int(i)]; print(f"  #{i:<6} t{b.typ:<2} Δ={d[i]:<10.3g} v={v[i]:<10.4g} saved={b.saved:<9.4g} {b.name[:36]:36s} | {b.formula()[:80]}")
print("\n=== деления на ноль по блокам (top 15) ===")
for i, c in collections.Counter(m.divc.where).most_common(15):
    b = m.by[i]; print(f"  #{i:<6} t{b.typ:<2} ×{c:<3} v={v[i]:<10.4g} {b.name[:36]:36s} | {b.formula()[:80]}")
print("\n=== значения вне разумного: |v|>1e6 ===")
big = [i for i in range(m.N) if abs(v[i]) > 1e6 and i in m.by]
print(f"  всего {len(big)}:", [(i, f'{v[i]:.3g}') for i in big[:12]])
print("\n=== трассировка нулей вверх по входам для #1155, #255, #879 ===")
def trace(i, depth=0, seen=set()):
    b = m.by[i]
    print("    " * depth + f"#{i} t{b.typ} v={v[i]:.4g} saved={b.saved:.4g} {b.name[:30]} | {b.formula()[:60]}")
    if depth >= 6 or i in seen: return
    seen.add(i)
    for s in b.inputs:
        if abs(v[s]) < 1e-12 or not np.isfinite(v[s]):
            trace(s, depth + 1, seen)
for i in (1155, 255, 879):
    trace(i); print()
