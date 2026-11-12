# -*- coding: utf-8 -*-
"""PoC: юнит-экономика на Python + SQLite. Сверка с золотыми CSV приложения."""
import csv, sqlite3, math, os
from decimal import Decimal, ROUND_HALF_UP

import pathlib
DB = str(pathlib.Path(__file__).with_name('poc_catalog.db'))
if os.path.exists(DB): os.remove(DB)
db = sqlite3.connect(DB)
db.executescript('''
CREATE TABLE products(
  article TEXT PRIMARY KEY, price REAL, cost REAL,
  weight REAL, length REAL, width REAL, height REAL, sales REAL DEFAULT 0);
CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE eco_results(
  article TEXT PRIMARY KEY, total_cost REAL, profit REAL,
  margin REAL, roi REAL, break_even REAL, target_price REAL);
''')
# настройки из золотого файла (Ozon FBS): комиссия 14%, перевод 1.5%, налог УСН 6%
for k, v in {'commission_pct':'14','transfer_pct':'1.5','last_mile':'25','handover':'10',
             'pack':'18','transit':'30','returns_per_unit':'2.17','tax_regime':'usn_income_6',
             'tax_pct':'6','target_margin':'20'}.items():
    db.execute('INSERT INTO settings VALUES(?,?)', (k, v))
db.commit()
cfg = {k: v for k, v in db.execute('SELECT key,value FROM settings')}

def rnd(x, d=2):
    # Excel-стиль: половина от нуля, как round() в приложении
    q = Decimal(1).scaleb(-d)
    return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))

def vat_from_gross(amount, rate):
    return amount * rate / (100 + rate) if rate > 0 else 0.0

def calc_tax(price, costs, regime, pct=6.0, osno_share=0.0):
    p, c = max(0.0, price), max(0.0, costs)
    if regime == 'usn_income_6': return rnd(p * 0.06)
    if regime in ('usn_income_vat_5', 'usn_income_7', 'usn_income_vat_7'):
        rate = 5 if regime.endswith('_5') else 7
        vat = vat_from_gross(p, rate)
        return rnd(vat + (p - vat) * 0.06)
    if regime == 'usn_income_expense_15': return rnd(max(0.0, p - c) * 0.15)
    if regime in ('usn_income_expense_vat_5', 'usn_income_expense_vat_7'):
        rate = 5 if regime.endswith('_5') else 7
        vat = vat_from_gross(p, rate)
        return rnd(vat + max(0.0, p - vat - c) * 0.15)
    if regime in ('osno_20', 'osno_22'):
        vat_out = vat_from_gross(p, 22)
        vat_in = vat_from_gross(c, 22) * min(100.0, max(0.0, osno_share)) / 100
        return rnd(max(0.0, vat_out - vat_in) + max(0.0, (p - vat_out) - (c - vat_in)) * 0.25)
    if regime == 'custom_profit': return rnd(max(0.0, p - c) * pct / 100)
    return rnd(p * pct / 100)

def wb_base_logistics(v):
    if v <= 0: return 0.0
    if v <= 0.2: return 23.0
    if v <= 0.4: return 26.0
    if v <= 0.6: return 29.0
    if v <= 0.8: return 30.0
    if v <= 1: return 32.0
    return rnd(46 + (v - 1) * 14)

def ozon_unit(price, cost):
    comm = rnd(price * float(cfg['commission_pct']) / 100)
    transfer = rnd(price * float(cfg['transfer_pct']) / 100)
    fixed = (cost + float(cfg['last_mile']) + float(cfg['handover']) + float(cfg['pack'])
             + float(cfg['transit']) + float(cfg['returns_per_unit']))
    tax = calc_tax(price, fixed + comm + transfer, cfg['tax_regime'], float(cfg['tax_pct']))
    total = rnd(fixed + comm + transfer + tax)
    return total, comm, transfer, tax

def solve(price0, cost, target_margin_pct):
    # первое целое p с прибылью >= 0 (и >= целевой маржи), как решатель приложения
    def profit(p):
        total, *_ = ozon_unit(p, cost)
        return rnd(p - total)
    def margin_ok(p):
        return profit(p) - p * target_margin_pct / 100
    be = next((p for p in range(0, 2_000_000) if profit(p) >= 0), None)
    tgt = next((p for p in range(be or 0, 2_000_000) if margin_ok(p) >= 0), None)
    return be, tgt

# --- загрузка золотого файла в SQLite ---
def num(v):
    v = str(v or '').replace(' ', '').replace(',', '.')
    return float(v) if v else 0.0

rows = list(csv.reader(open(str(pathlib.Path(__file__).resolve().parent.parent / 'UC_unit_economics_OZON_2026-11-06_filtered.csv'),
                            encoding='utf-8-sig'), delimiter=';'))
hdr = rows[0]; ix = {h: i for i, h in enumerate(hdr)}
for r in rows[1:]:
    db.execute('INSERT INTO products VALUES(?,?,?,?,?,?,?,?)',
               (r[ix['Артикул']], num(r[ix['Цена, ₽/ед.']]), num(r[ix['Себестоимость, ₽']]),
                num(r[ix['Вес, кг']]), num(r[ix['Длина, см']]), num(r[ix['Ширина, см']]),
                num(r[ix['Высота, см']]), 10))
db.commit()

# --- расчёт из SQLite и сверка ---
rec = list(csv.reader(open(str(pathlib.Path(__file__).resolve().parent.parent / 'UC_unit_economics_OZON_2026-11-06_recalculated.csv'),
                           encoding='utf-8-sig'), delimiter=';'))
rix = {h: i for i, h in enumerate(rec[0])}
manual_be = {r[0]: num(r[rix['Цена безубыточности (ручной пересчёт), руб']]) for r in rec[1:]}

bad = 0
for art, price, cost, w, L, W, H, sales in db.execute('SELECT * FROM products'):
    total, comm, transfer, tax = ozon_unit(price, cost)
    profit = rnd(price - total)
    margin = rnd(profit / price * 100, 1) if price else 0
    roi = rnd(profit / cost * 100, 1) if cost else 0
    be, tgt = solve(price, cost, float(cfg['target_margin']))
    db.execute('INSERT INTO eco_results VALUES(?,?,?,?,?,?,?)', (art, total, profit, margin, roi, be, tgt))
    # сверка с золотым файлом
    grow = next(r for r in rows[1:] if r[0] == art)
    checks = [(total, num(grow[ix['Все затраты на 1 ед., ₽']]), 'итого'),
              (profit, num(grow[ix['ЧП на 1 ед., ₽']]), 'прибыль'),
              (margin, num(grow[ix['Маржа, %']]), 'маржа'),
              (roi, num(grow[ix['ROI, %']]), 'ROI'),
              (be, manual_be[art], 'безубыток')]
    for got, want, name in checks:
        tol = 1.0 if name == 'безубыток' else 0.011  # решатель приложения целочисленный, ручная колонка — дробная
        if abs(got - want) > tol:
            bad += 1; print(f'РАСХОЖДЕНИЕ {art} {name}: python={got} эталон={want}')
db.commit()
n = db.execute('SELECT COUNT(*) FROM eco_results').fetchone()[0]
print(f'PoC OK: {n} SKU посчитано в Python+SQLite, расхождений с эталоном: {bad}')
print('пример:', db.execute("SELECT * FROM eco_results WHERE article='DEMO-CLT-001'").fetchone())
print('налоги: УСН6 100000 ->', calc_tax(100000, 40000, 'usn_income_6'),
      '| УСН+НДС5 ->', calc_tax(100000, 40000, 'usn_income_vat_5'),
      '| ОСНО 1220/610 доля100 ->', calc_tax(1220, 610, 'osno_20', 6, 100))
print('WB логистика 0.5л/2л:', wb_base_logistics(0.5), wb_base_logistics(2))
print('размер БД:', os.path.getsize(DB), 'байт')
