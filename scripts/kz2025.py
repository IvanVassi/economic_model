"""Калибровка Сложной народнохозяйственной модели к Казахстану 2025 года.

Подход: структура секторов и реальные пропорции модели сохраняются (эксперименты
показали, что перестройка численности занятых/фондов по секторам дестабилизирует
модель). Под Казахстан подгоняются:
  * ставки налогов (законные ставки 2025 г.) и коэффициенты приведения базы #21–#29,
    так чтобы вклад каждого налога в доходы бюджета (#42) соответствовал факту 2025 г.
    в % ВВП;
  * объём и структура расходов бюджета (#90, #101–#117, #855–#885);
  * экспортные цены секторов (k160) — структура экспорта (нефть, руды/металлы, газ …);
  * экспортные пошлины (#321–#333), продажа валюты Минфином (#122) ≈ трансферт Нацфонда + таможня;
  * неналоговые доходы (#56, #57).

Масштаб: 1 единица модели ≈ ВВП_KZ/ВВП_модели трлн тенге (см. SCALE в отчёте).
"""
from __future__ import annotations
import json, sys, os, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sim.session import Session
from sim.patches import SOCIAL_NOMINAL, T_INDEX

MDN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'SNHM.MDN')
SEC = {1: 'сырьё (горнодобыча)', 2: 'машиностроение', 3: 'строительство', 4: 'сельское хозяйство',
       5: 'ТНП (лёгкая пром.)', 6: 'металлургия и пр. экспорт (сектор ВПК)', 7: 'уголь', 8: 'нефть',
       9: 'газ', 10: 'электроэнергетика', 11: 'пищевая пром.', 12: 'транспорт', 13: 'прочее (услуги)'}
SEC_SHORT = {1: 'сырьё', 2: 'машиностр', 3: 'строит', 4: 'с/х', 5: 'ТНП', 6: 'металлургия*', 7: 'уголь',
             8: 'нефть', 9: 'газ', 10: 'эл-эн', 11: 'пищепром', 12: 'транспорт', 13: 'прочее'}

# --- Факты Казахстана 2025 (трлн тенге, если не сказано иное) ---
KZ = dict(gdp_trln=159.6, gdp_usd_bln=306.0, rate_avg=521.0, inflation=12.3, unemployment=4.6,
          population_mln=20.48, exports_goods_usd=71.1, exports_services_usd=9.5, imports_goods_usd=57.7,
          vat_total=6.11, vat_import=2.9, cit_rb=4.53, cit_nf=2.5, pit=2.85, social_tax=1.6, excise_met_rent=3.0,
          property=0.9, nf_transfer=5.25, customs=2.32, nontax=0.82, expenditures=33.7, deficit=4.4,
          # рынок труда и структура населения, млн человек (2025)
          labour_force=9.8, employed=9.35, unemployed=0.45, pensioners=2.4, public_employees=1.7, military=0.3, self_employed=2.1,
          # инфляция, % в год: факт 2025 и прогноз Нацбанка без реформы — для сравнения с траекторией модели
          inflation_path={2025: 12.3, 2026: 9.5, 2027: 7.5, 2028: 6.0, 2029: 5.5, 2030: 5.0})

# Демография и рынок труда. Трудовые ресурсы секторов (k012) — уставки; их общая сумма задаёт масштаб «человек»:
# 1 ед. = labour_force / Σk012 млн чел. Безработица подгоняется масштабированием k012 (структура по секторам сохраняется).
# Численности внепроизводственных групп: #15111 бюджетники, #15211 военные (константы), #15311 пенсионеры (множитель к #15400 = 61.5).
# Демографический блок (#17001–#17699) в файле односторонний: экономика влияет на него, обратно — нет; #17670 «всего населения»
# только отображается, поэтому его множитель ставится так, чтобы показывать население Казахстана в тех же единицах.
UNEMP_TARGET = KZ['unemployment']
INFL_TARGET = KZ['inflation']        # сложившаяся инфляция 2025 г.; в модели — инерционный процесс (правка inflation)
INFL_LONGRUN = 5.0                   # цель Нацбанка: к ней снижается внешний фон в сценариях 2026+
INFL_DECLINE_YEARS = 2.0             # за сколько лет фон линейно снижается от сложившегося уровня к цели

# Целевой вклад компонент в доходы бюджета #42, % ВВП (после коэффициентов 0.8 и 0.8907).
# #42 = 0.8907·(0.8·(#33+#34+#35+#36) + #40 + #41 + #60 + #56)
TARGET = {
    34: 2.0,   # НДС внутренний (импортный НДС ~1.8% ВВП вне модели)
    33: 1.9,   # НДПИ, рентный налог, акцизы производителей (налоги с оборота)
    35: 4.0,   # КПН (респ. бюджет + часть в Нацфонд)
    36: 0.6,   # налоги на имущество, землю, транспорт
    40: 2.8,   # ИПН + социальный налог/взносы
    41: 4.5,   # трансферт Нацфонда + таможенные платежи (продажа валюты Минфином)
    60: 0.5,   # акцизы в розничной торговле
    56: 0.2,   # неналоговые доходы
}
REV_TARGET = sum(TARGET.values())    # ≈ 18.5 % ВВП
EXP_TARGET = 21.1                    # расходы гос. бюджета, % ВВП (дефицит ≈ 2.6–2.8)

# Законные ставки 2025 г. (до Налогового кодекса 2026)
RATES = {14: 12, 19: 12,          # НДС производство / розница
         15: 20,                  # КПН
         12: 10,                  # ИПН
         11: 12,                  # взносы работников (ОПВ 10% + ВОСМС 2%)
         18: 21.5,                # начисления на ФОТ (соц. налог 11 + СО 5 + ОПВР 2.5 + ООСМС 3)
         16: 1.5,                 # налог на имущество
         13: 1.0,                 # прочие налоги с оборота (усреднённо: НДПИ/рента)
         7: 0.05, 8: 10, 9: 10, 10: 30, 17: 3}   # акцизы/НДПИ по секторам, розница
BASE_RATES = {7: 0.05, 8: 40, 9: 20, 10: 30, 11: 5, 12: 12, 13: 4, 14: 20, 15: 30, 16: 3, 17: 20, 18: 41, 19: 20}
RATE2K = {14: 24, 19: 29, 15: 25, 12: 22, 11: 21, 18: 28, 16: 26, 13: 23, 17: 27}   # ставка → её К приведения
# Коэффициенты приведения базы (подбираются)
KLEV = {34: 24, 33: 23, 35: 25, 36: 26, 40: (21, 22), 60: 27}
COEF = {34: 0.8 * 0.8907, 33: 0.8 * 0.8907, 35: 0.8 * 0.8907, 36: 0.8 * 0.8907, 40: 0.8907, 41: 0.8907,
        60: 0.8907, 56: 0.8907}

# Структура расходов, доли от общей суммы (факт КЗ 2025 по функциям, гос. бюджет)
# Целевые статьи расходов (ед. модели при ВВП≈11370 → 21.1 % ВВП); затем масштабируются к total
# Эксперименты показали: резкое (×2.5–3.5) изменение отдельных статей раскачивает модель
# (колебания спроса на ТНП, безработица), равномерное увеличение всех статей устойчиво.
# Поэтому структура сдвигается умеренно: пенсии/образование/здравоохранение/инфраструктура вверх, наука вниз.
EXP_ITEMS = {116: 200, 117: 10, 114: 260, 115: 200, 885: 260, 865: 180, 855: 56.5, 875: 50,
             101: 30, 102: 60, 103: 60, 104: 50, 105: 16.7, 106: 149.6, 107: 17.2, 108: 69.8, 109: 49.9,
             110: 38.7, 111: 38.7, 112: 50, 113: 220}
# 116 пенсии/пособия, 117 безработные, 114 бюджетники, 115 военные/силовые, 885 образование, 865 здравоохранение,
# 855 культура, 875 наука, 103 строительство (инфраструктура), 112 транспорт, 104 с/х субсидии, 113 прочие услуги,
# 102 Фа(оборудование), 110 эл-эн, 111 пищепром, 105 ТНП, 106 ВПК/металлургия, 101 сырьё, 107 уголь, 108 нефть, 109 газ

# Экспортные цены (индексы k160, базово 1.0 → 65 $): целевая структура экспорта, % ВВП
EXPORT_PRICE = {8: 2.2, 1: 1.15, 6: 0.8, 9: 0.5, 7: 0.8, 2: 0.9, 3: 0.5, 10: 0.5, 12: 1.05, 13: 1.3}
# Экспортные пошлины/рента, % выручки: нефть высокая (ЭТП + рентный налог), остальное низкое
# Экспортные пошлины (#321–#325, #334–#337) оставлены на исходных 20 %: их изменение раскачивает
# валютный рынок модели, а фискальный эффект пошлин учтён через целевой вклад #41.
TARIFFS: dict[int, float] = {}


def contributions(s: Session) -> dict[int, float]:
    gdp = s.value(155)
    return {c: 100 * COEF[c] * s.value(c) / gdp for c in TARGET}


def apply_static(s: Session) -> None:
    for k, v in RATES.items():
        s.set_lever(k, v)
        if k in RATE2K:   # смена ставки нейтральна: К приведения компенсирует, эффективная ставка та же
            s.set_lever(RATE2K[k], s.lever(RATE2K[k]) * BASE_RATES[k] / v)
    for k, v in EXPORT_PRICE.items():
        s.set_lever(k * 1000 + 160, v)
    for k, v in TARIFFS.items():
        if k in s.model.by and s.model.by[k].typ == 2:
            s.set_lever(k, v)


def deflator(s: Session) -> float:
    """Дефлятор модели (#14004, правка inflation): 1 при t = 0."""
    return s.value(14004)


def index_ratio(s: Session) -> float:
    """Реальная ценность бюджетных выплат (#14020): номинальные планы #114–#117 индексируются с лагом."""
    return s.value(14020)


def apply_expenditures(s: Session, total: float) -> None:
    """total — расходы в реальном выражении (ценах модели); планы социальных выплат задаются в номинале
    так, чтобы их реальная величина при текущей инфляции равнялась целевой структуре."""
    tot0 = sum(EXP_ITEMS.values())
    r = index_ratio(s)
    for k, v in EXP_ITEMS.items():
        s.set_lever(k, total * v / tot0 / (r if k in SOCIAL_NOMINAL else 1.0))
    s.set_lever(90, total)
    s.set_lever(159, total)


def set_nontax(s: Session, gdp: float) -> None:
    s.set_lever(56, gdp * TARGET[56] / 100 / COEF[56])


def inflation(s: Session, years: float = 1.0) -> float:
    """Номинальная инфляция за последние years лет по ИПЦ модели · дефлятор (#14018), % годовых."""
    ts, M = s.series([14018])
    import numpy as np
    i = int(np.searchsorted(ts, s.t - years))
    return 100 * ((float(M[-1, 0]) / float(M[i, 0])) ** (1 / years) - 1)


def set_background(s: Session, steady: float) -> None:
    """Рычаг внешнего фона #14009 (% в год), при котором установившаяся инфляция равна steady:
    π = ζ·π + фон  →  фон = (1 − ζ)·π."""
    s.set_lever(14009, steady * (1 - s.lever(14010)))


def background_path(s: Session, start: float, end: float, years: float = INFL_DECLINE_YEARS) -> None:
    """График фона #14009: линейно от уровня start к end за years лет с текущего момента (сценарии 2026+:
    сложившаяся инфляция не исчезает разом — тарифы, импорт, ожидания снижаются постепенно)."""
    z = 1 - s.lever(14010)
    s.set_schedule(14009, [(s.t, start * z), (s.t + years, end * z)], mode='linear')


def labour_units(s: Session) -> float:
    """Сколько млн человек в одной единице численности модели."""
    return KZ['labour_force'] / sum(s.lever(k * 1000 + 12) for k in SEC)


def unemployment(s: Session) -> float:
    return 100 * s.value(231) / sum(s.lever(k * 1000 + 12) for k in SEC)


def apply_demography(s: Session) -> None:
    """Численность групп и населения в единицах модели при текущем масштабе трудовых ресурсов."""
    u = labour_units(s)
    s.set_lever(15111, KZ['public_employees'] / u)
    s.set_lever(15211, KZ['military'] / u)
    s.set_lever(15311, KZ['pensioners'] / u / s.value(15400))         # #15311 = pa0 · #15400
    s.set_lever(17670, s.lever(17670) * (KZ['population_mln'] / u) / max(s.value(17670), 1e-9))


def calibrate(verbose: bool = True, years_warm: float = 3.0, iters: int = 6) -> Session:
    s = Session(MDN, variant='patched')
    set_background(s, INFL_TARGET)        # сложившаяся инфляция: фон (1−ζ)·12.3 %, ожидания накапливаются за прогрев
    apply_static(s)
    gdp0 = s.value(155)
    apply_expenditures(s, gdp0 * EXP_TARGET / 100)
    set_nontax(s, gdp0)
    # старт: коэффициенты приведения — пропорционально отношению целевого вклада к текущему
    for it in range(iters):
        s.run(years_warm if it == 0 else 2.0)
        gdp = s.value(155)
        cur = contributions(s)
        if verbose:
            print(f'итерация {it}: t={s.t:.1f} ВВП={gdp:.0f} доходы={100*s.value(42)/gdp:.2f}% расходы={100*s.value(51)/gdp:.2f}% '
                  + ' '.join(f'#{c}={cur[c]:.2f}/{TARGET[c]}' for c in TARGET))
        for c, lev in KLEV.items():
            f = TARGET[c] / max(cur[c], 1e-6)
            f = min(max(f, 0.5), 2.0) ** 0.7   # демпфирование
            for l in (lev if isinstance(lev, tuple) else (lev,)):
                s.set_lever(l, s.lever(l) * f)
        s.set_lever(122, s.lever(122) * min(max(TARGET[41] / max(cur[41], 1e-6), 0.5), 2.0) ** 0.7)
        set_nontax(s, gdp)
        apply_expenditures(s, gdp * EXP_TARGET / 100)
    s.run(2.0)
    apply_demography(s)
    # безработица: подгонка масштаба трудовых ресурсов (2 итерации), доходы бюджета почти не меняются
    for _ in range(3):
        s.run(2.0)
        gdp = s.value(155)
        set_nontax(s, gdp)
        apply_expenditures(s, gdp * EXP_TARGET / 100)
        cur41 = contributions(s)[41]      # трансферт Нацфонда/таможня уходит при перестройке рынка труда — подправить #122
        s.set_lever(122, s.lever(122) * min(max(TARGET[41] / max(cur41, 1e-6), 0.5), 2.0) ** 0.7)
        u = unemployment(s)
        if abs(u - UNEMP_TARGET) < 0.15:
            break
        f = (1 - u / 100) / (1 - UNEMP_TARGET / 100)
        for k in SEC:
            s.set_lever(k * 1000 + 12, s.lever(k * 1000 + 12) * f)
        apply_demography(s)
    s.run(2.0)
    if verbose:
        gdp = s.value(155); cur = contributions(s)
        print(f'итог: t={s.t:.1f} ВВП={gdp:.0f} доходы={100*s.value(42)/gdp:.2f}% расходы={100*s.value(51)/gdp:.2f}% '
              + ' '.join(f'#{c}={cur[c]:.2f}' for c in TARGET)
              + f' инфляция={inflation(s):.1f}% безработица={unemployment(s):.1f}% дефлятор={deflator(s):.2f}')
    return s


def levers_dict(s: Session) -> dict[str, float]:
    """Все рычаги (тип 2, ra0==idx), отличающиеся от исходных."""
    out = {}
    for b in s.model.blocks:
        if b.typ == 2 and b.ra and b.ra[0] == b.idx and abs(s.model.P[b.idx] - s.model.P0[b.idx]) > 1e-9:
            out[str(b.idx)] = float(s.model.P[b.idx])
    return out


if __name__ == '__main__':
    import time
    t0 = time.time()
    s = calibrate()
    print('время', round(time.time() - t0), 'с')
    sys.path.insert(0, '/private/tmp/claude-501/-Users-ivan-code-model/7a0cdc6e-53ea-42f7-9acb-9505b4a18eb4/scratchpad')
    from diag import diag
    diag(s)
    print(json.dumps(levers_dict(s), ensure_ascii=False))
