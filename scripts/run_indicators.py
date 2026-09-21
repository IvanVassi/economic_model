"""Пятилетний прогон: таблица ключевых показателей по годам + сводка дрейфа."""
import sys, time, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '/Users/ivan/code/model')
import numpy as np
from mdn import load
from sim import Model, Semantics

KEY = [(155, 'ВВП произв+торг'), (156, 'ВВП сфера произв'), (42, 'доходы бюджета'), (51, 'расходы бюджета'), (44, 'текущий дефицит'),
       (43, 'накопл. дефицит'), (55, 'накопл. эмиссия'), (191, 'поток эмиссии'), (501, 'курс руб/дол'), (540, 'курс ЦБ'), (523, 'резервы ЦБ'),
       (210, 'индекс розн. цен'), (225, 'ср. оптовая цена'), (546, 'темп инфляции'), (151, 'уровень жизни'), (152, 'соц. напряжённость'), (380, 'качество жизни'),
       (231, 'безработных'), (153, 'численность'), (17670, 'население всего'), (130, 'внешний долг $'), (100, 'валюта Минфина'),
       (1001, 'выпуск сырьё'), (1039, 'цена сырьё'), (1025, 'К сменности сырьё'), (1063, 'фонды сырьё'), (4001, 'выпуск с/х'), (11039, 'цена пищепром'), (1000, 'интеллект. индекс')]
B = load('/Users/ivan/code/model/SNHM.MDN')
m = Model(B, Semantics())
v = m.initial_state('saved'); m.settle(v, iters=150)
v0 = v.copy()
b191 = m.by[191]; print(f'#191 «{b191.name}»: {b191.formula()}  pa={b191.pa} ra={b191.ra}')
t0 = time.time()
ts, out = m.run(v, 5.0, 0.001, 0.01)
print(f'5 лет за {time.time()-t0:.1f} с; nan/inf: {int((~np.isfinite(v)).sum())}')
years = [int(round(y / 0.01)) for y in (0, 1, 2, 3, 4, 5)]
print(f"\n{'показатель':<20}" + ''.join(f'{f"t={y}":>12}' for y in (0, 1, 2, 3, 4, 5)))
for i, nm in KEY:
    print(f'{nm:<20}' + ''.join(f'{out[k, i]:>12.4g}' for k in years))
st = np.array(m.state_idx)
rel = np.abs(v[st] - v0[st]) / np.maximum(np.abs(v0[st]), 1e-6)
print(f'\nдрейф состояния за 5 лет: <1e-3: {(rel<1e-3).mean():.1%}, <1e-2: {(rel<1e-2).mean():.1%}, <0.1: {(rel<0.1).mean():.1%}, <1: {(rel<1).mean():.1%}')
print('наибольший дрейф (кроме валюты соцгрупп 6xx/7xx):')
for k in np.argsort(-rel):
    i = int(st[k])
    if 600 <= i <= 780 or 1600 <= i <= 1630: continue
    b = m.by[i]; print(f'  #{i:<6} t{b.typ} x0={v0[i]:<10.4g} x5={v[i]:<10.4g} rel={rel[k]:<8.2g} {b.name[:38]:38s} | {b.formula()[:44]}')
    if rel[k] < 0.05: break
np.savez('/Users/ivan/code/model/out/run5y.npz', ts=ts, out=out, v0=v0, vT=v)
