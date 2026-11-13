# -*- coding: utf-8 -*-
"""
UNIT·CONTROL — локальный расчётный движок (Python + SQLite).

Запуск:
  python uc_engine.py serve            # HTTP 127.0.0.1:8765 (только локально)
  python uc_engine.py watch            # планировщик: почта + папка + очередь отправки
  python uc_engine.py mail --once      # одна проверка почты
  python uc_engine.py calc --demo      # самопроверка экономики на демо-строке

Зависимости: только стандартная библиотека. Для XLSX — openpyxl (необязательно).

Безопасность: сервер слушает только 127.0.0.1; все эндпоинты кроме /health
требуют заголовок X-UC-Token (токен в engine_data/token.txt, создаётся сам).
Ключи маркетплейсов и пароль почты читаются из переменных окружения или
engine_data/secrets.json (на Windows рекомендуется DPAPI-обёртка, см. README).
"""
import argparse, csv, email, imaplib, io, json, math, os, re, shutil, sqlite3, sys, time, zipfile
from decimal import Decimal, ROUND_HALF_UP
from email.header import decode_header
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import URLError

BASE = Path(__file__).resolve().parent
FROZEN = getattr(sys, 'frozen', False)
# v12.9.124: один файл. В frozen-сборке (PyInstaller --onefile) ресурсы лежат
# во временной распаковке _MEIPASS, а данные обязаны жить РЯДОМ с exe —
# иначе каталог и токен терялись бы при каждом закрытии.
BUNDLE = Path(getattr(sys, '_MEIPASS', BASE)) if FROZEN else BASE
DATA = (Path(sys.executable).resolve().parent / 'engine_data') if FROZEN else BASE / 'engine_data'
DATA.mkdir(exist_ok=True)
DB_PATH = DATA / 'catalog.db'
TOKEN_PATH = DATA / 'token.txt'
SECRETS_PATH = DATA / 'secrets.json'
VERSION = '12.9.151-pyengine-36'

class DiskFullError(Exception):
    """v12.9.144: на диске с базой не хватает места для безопасного импорта."""

MIN_FREE_FOR_IMPORT = 250 * 1024 * 1024

def ensure_free_space(need_bytes=0):
    """Предпроверка места ПЕРЕД записью в SQLite: лучше честный отказ до
       импорта, чем 'database or disk is full' в середине и полупустая база.
       Нужно: минимум 250 МБ и не меньше 4 размеров файла (строки в SQLite
       шире исходного CSV: индексы, FTS, история цен, WAL)."""
    import shutil as _sh
    try: free = _sh.disk_usage(str(DATA)).free
    except Exception: return
    need = max(MIN_FREE_FOR_IMPORT, int(need_bytes or 0) * 4)
    if free < need: raise DiskFullError(f'free={free} need={need}')

# ---------------- деньги и округление (Excel-стиль, как в приложении) ----------------
def rnd(x, d=2):
    q = Decimal(1).scaleb(-d)
    return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))

def num(v):
    if v is None: return 0.0
    if isinstance(v, (int, float)): return float(v)
    s = str(v).replace(' ', '').replace(' ', '').replace('%', '')
    if ',' in s and '.' in s:
        s = s.replace('.', '', 1).replace(',', '.') if s.rfind(',') > s.rfind('.') else s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '.') if s.count(',') == 1 else s.replace(',', '')
    elif s.count('.') > 1:
        s = s.replace('.', '')  # 12.345.678 — тысячные, как num() браузера
    try: return float(s)
    except ValueError: return 0.0

def vat_from_gross(amount, rate):
    return amount * rate / (100 + rate) if rate > 0 else 0.0

def calc_tax(price, costs, regime='usn_income_6', pct=6.0, osno_share=0.0):
    """Все налоговые режимы приложения, копейка в копейку (проверено тестами)."""
    p, c = max(0.0, num(price)), max(0.0, num(costs))
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
    if regime == 'self_employed_4': return rnd(p * 0.04)
    if regime == 'self_employed_6': return rnd(p * 0.06)
    if regime == 'custom_profit': return rnd(max(0.0, p - c) * min(100.0, max(0.0, pct)) / 100)
    return rnd(p * min(100.0, max(0.0, pct if pct is not None else 6.0)) / 100)

def wb_base_logistics(v):
    v = max(0.0, num(v))
    if v <= 0: return 0.0
    if v <= 0.2: return 23.0
    if v <= 0.4: return 26.0
    if v <= 0.6: return 29.0
    if v <= 0.8: return 30.0
    if v <= 1: return 32.0
    return rnd(46 + (v - 1) * 14)

def wb_storage_month(volume, first_liter_day=0.15, coeff=1.0, days=30):
    """Ступенчатое хранение WB FBO: первый литр по ставке, далее 7/15."""
    v = max(0.0, num(volume))
    if v <= 0: return 0.0
    per_day = first_liter_day * min(v, 1) + first_liter_day * (7 / 15) * max(0.0, v - 1)
    return rnd(per_day * coeff * days)

# ---------------- экономика Ozon (паритет с приложением; эталон — золотые CSV) ----------------
def ozon_unit(price, cost, st):
    if isinstance(st.get('ozon'), dict):
        return _ozon_browser_unit(price, cost, st)
    comm = rnd(price * num(st.get('commission_pct', 14)) / 100)
    transfer = rnd(price * num(st.get('transfer_pct', 1.5)) / 100)
    failed_case = num(st.get('failed_case', 0))
    rate = min(100.0, max(0.0, num(st.get('no_buy_pct', 0))))
    returns = rnd(failed_case * rate / (100 - rate), 6) if rate < 100 else 0.0
    if num(st.get('returns_per_unit', 0)):
        returns = num(st.get('returns_per_unit'))
    vol = num(st.get('_volume', 0))
    storage = wb_storage_month(vol, num(st.get('storage_first_liter_day', 0.15)),
                               num(st.get('storage_coeff', 1)), num(st.get('storage_days', 30))) \
        if st.get('fulfillment') == 'FBO' else 0.0
    fixed_parts = [cost, num(st.get('last_mile', 25)), num(st.get('handover', 10)),
                   num(st.get('pack', 18)), num(st.get('transit', 30)), returns, storage,
                   num(st.get('processing', 0)), num(st.get('fixed_per_unit', 0))]
    tax = calc_tax(price, sum(fixed_parts) + comm + transfer,
                   st.get('tax_regime', 'usn_income_6'), num(st.get('tax_pct', 6)),
                   num(st.get('tax_osno_share', 0)))
    total = rnd(sum(fixed_parts) + comm + transfer + tax)
    return {'total': total, 'commission': comm, 'transfer': transfer, 'tax': tax,
            'returns': rnd(returns), 'storage': storage}

def _ozon_browser_unit(price, cost, st):
    """v12.9.146: Ozon — той же формулой, что evaluateOzon в браузере
       (calcMarketplacesEconomics): скидка за быструю отгрузку, ручной маршрут
       + обработка, сдача по режиму, хранение FBO за литр, невыкуп от полного
       расхода случая, нестандарт 3% с капом, поздняя отгрузка, хранение возврата.
       Настройки приходят в st['ozon'] из _settingsSnapshot приложения."""
    oz = st['ozon']
    scheme = str(oz.get('fulfillment') or 'FBS').upper()
    vol = num(st.get('_volume', 0))
    liters = max(0.01, vol) if vol > 0 else 0.0
    comm_base = num(st.get('commission_pct', 14))
    ship_disc = num(oz.get('ship_discount_pp')) if scheme == 'FBS' else 0.0
    comm = rnd(price * max(0.0, comm_base - ship_disc) / 100)
    transfer = rnd(price * num(st.get('transfer_pct', 1.5)) / 100)
    ads = rnd(price * num(oz.get('boost_pct')) / 100)
    cofin = rnd(price * num(oz.get('cofin_pct')) / 100)
    manual_log = num(st.get('_row_logistics', oz.get('logistics_manual')))
    processing = 0.0 if scheme == 'REALFBS' else num(oz.get('fbo_processing') if scheme == 'FBO' else oz.get('processing'))
    realfbs_del = num(st.get('_row_realfbs', 0))
    logistics = realfbs_del if scheme == 'REALFBS' else rnd(manual_log + processing)
    last_mile = 0.0 if scheme == 'REALFBS' else num(oz.get('last_mile', st.get('last_mile', 25)))
    units = max(1.0, num(oz.get('units_per_shipment')) or 1)
    handover = 0.0
    if scheme == 'FBS':
        mode = str(oz.get('handover_mode') or 'sc')
        if mode == 'sc_self': handover = 0.0
        elif mode == 'pvz_pct': handover = rnd(min(price * units * num(oz.get('pvz_pct')) / 100, num(oz.get('pvz_cap'))) / units)
        elif mode == 'courier': handover = rnd((num(oz.get('courier_trip')) / max(1.0, num(oz.get('courier_orders')) or 1) + num(oz.get('courier_order'))) / units + num(oz.get('courier_liter')) * liters)
        else: handover = rnd(num(oz.get('handover_fee', 10)) / units)
    storage = rnd(liters * num(oz.get('storage_per_l')) * num(oz.get('storage_days', 30))) if scheme == 'FBO' else 0.0
    rate = min(100.0, max(0.0, num(st.get('no_buy_pct', 0))))
    failed_override = num(st.get('failed_case')) > 0 or num(oz.get('failed_manual')) > 0
    realfbs_service = (num(oz.get('realfbs_service', 20)) / max(1.0, num(oz.get('realfbs_units')) or 1)) if scheme == 'REALFBS' else 0.0
    failed_case = num(st.get('failed_case')) or num(oz.get('failed_manual')) if failed_override else (
        realfbs_del + num(oz.get('realfbs_return')) + realfbs_service if scheme == 'REALFBS'
        else 2 * manual_log + last_mile + num(oz.get('return_handling')))
    returns = rnd(failed_case * rate / (100 - rate), 6) if rate < 100 else 0.0
    return_storage = 0.0 if failed_override else (
        rnd(num(oz.get('return_storage')) * rate / (100 - rate), 6) if scheme == 'FBS' and rate < 100 else 0.0)
    nonstd = 0.0
    if oz.get('nonstd_enabled', True) and scheme != 'REALFBS' and num(st.get('_weight', 0)) > 25:
        nonstd = rnd(min(price * num(oz.get('nonstd_pct', 3)) / 100, num(oz.get('nonstd_cap', 280))))
    late = rnd(price * num(oz.get('late_ship_pct')) / 100) if scheme == 'FBS' else 0.0
    pack = num(st.get('pack', 18))
    transit = num(st.get('transit', 30)) if scheme == 'FBS' else 0.0
    fixed = num(st.get('fixed_per_unit', 0))
    parts = [cost, comm, transfer, logistics, last_mile, handover, pack, transit,
             returns, return_storage, storage, ads, cofin, nonstd, late, fixed, realfbs_service]
    tax = calc_tax(price, sum(parts), st.get('tax_regime', 'usn_income_6'),
                   num(st.get('tax_pct', 6)), num(st.get('tax_osno_share', 0)))
    total = rnd(sum(parts) + tax)
    return {'total': total, 'commission': comm, 'transfer': transfer, 'tax': tax,
            'returns': rnd(returns + return_storage), 'storage': storage}

def wb_unit(price, cost, st):
    """v12.9.149: WB — формулой evaluateWb браузера: база логистики по объёму,
       складской коэффициент (СГТ без него, база 1000–3000), хранение FBO
       ступенчатое, доставка в СЦ по платному весу, невыкуп от полного расхода
       случая (ПВЗ-период — по объёму), комиссия/эквайринг/реклама/софин."""
    wb = st.get('wb') or {}
    scheme = str(wb.get('fulfillment') or 'FBS').upper()
    v = num(st.get('_volume', 0))
    dims = st.get('_dims') or (0, 0, 0)
    base = wb_base_logistics(v)
    sgt = num(st.get('_weight', 0)) > 25 or max(dims) > 200 or sum(dims) > 280
    coeff = 1.0 if sgt else num(wb.get('warehouse_coeff', 1.7))
    direct_base = min(3000.0, max(1000.0, base)) if sgt else base
    logistics = rnd(rnd(direct_base * coeff) + (num(wb.get('acceptance')) if scheme == 'FBO' else 0.0))
    storage = wb_storage_month(v, num(wb.get('storage_per_l', 0.15)), num(wb.get('storage_coeff', 1)), num(wb.get('storage_days', 30))) if scheme == 'FBO' else 0.0
    div = num(wb.get('vol_divisor')) or 5000
    _vol_kg = (dims[0] * dims[1] * dims[2] / div) if all(d > 0 for d in dims) else (v * 1000 / div if v > 0 else 0.0)
    billable = max(num(st.get('_weight', 0)), _vol_kg)
    sc_delivery = rnd(num(wb.get('sc_per_kg', 12)) * billable) if scheme == 'FBS' else 0.0
    rate = min(100.0, max(0.0, num(st.get('no_buy_pct', 0))))
    failed_manual = num(wb.get('failed_manual'))
    if failed_manual > 0: failed_case = failed_manual
    elif scheme == 'FBS':
        import datetime as _dt
        today = _dt.date.today()
        in_pvz = _dt.date(2026, 8, 7) <= today <= _dt.date(2027, 1, 31)
        failed_case = (rnd(25 if v <= 1 else 25 + (v - 1) * 4) if v > 0 else 0.0) if in_pvz else 0.0
    else:
        extra = num(wb.get('return_extra'))
        failed_case = rnd(base * coeff + extra) if extra > 0 else base
    returns = rnd(failed_case * rate / (100 - rate), 6) if rate < 100 else 0.0
    comm = rnd(price * num(wb.get('commission_pct', 15)) / 100)
    transfer = rnd(price * num(wb.get('acquiring_pct', 1.5)) / 100)
    ads = rnd(price * num(wb.get('boost_pct')) / 100)
    cofin = rnd(price * num(wb.get('cofin_pct')) / 100)
    pack = num(st.get('pack', 18)); transit = num(st.get('transit', 30)) if scheme == 'FBS' else 0.0
    fixed = num(st.get('fixed_per_unit', 0))
    parts = [cost, comm, transfer, logistics, sc_delivery, pack, transit, returns, storage, ads, cofin, fixed]
    tax = calc_tax(price, sum(parts), st.get('tax_regime', 'usn_income_6'), num(st.get('tax_pct', 6)), num(st.get('tax_osno_share', 0)))
    return {'total': rnd(sum(parts) + tax), 'commission': comm, 'transfer': transfer, 'tax': tax,
            'returns': rnd(returns), 'storage': storage}

def solve_prices(price, cost, st, target_margin=20.0, sales=1, unit=None):
    """Целочисленный решатель: первое целое с прибылью >= 0 и >= целевой маржи.
       Как в приложении: при продажах 0 безубыток не выдумывается (0)."""
    if not (num(sales) > 0):
        return {'break_even': 0, 'target': 0}
    if min(100.0, max(0.0, num(st.get('no_buy_pct', 0)))) >= 100:
        return {'break_even': 0, 'target': 0}  # как solveMarketplacePrices при returnRateInvalid
    _unit = unit or ozon_unit
    def profit(p):
        return rnd(p - _unit(p, cost, st)['total'])
    def ok(p, margin):
        return profit(p) - p * margin / 100 >= 0
    # аналитический старт для процентной части + локальная доводка
    pct_rate = (num(st.get('commission_pct', 14)) + num(st.get('transfer_pct', 1.5))) / 100
    if st.get('tax_regime', 'usn_income_6') in ('usn_income_6', 'custom'):
        pct_rate += num(st.get('tax_pct', 6)) / 100
    fixed_est = max(1.0, cost + num(st.get('last_mile', 25)) + num(st.get('handover', 10))
                    + num(st.get('pack', 18)) + num(st.get('transit', 30)))
    def find(margin):
        denom = 1 - pct_rate - margin / 100
        p = max(0, math.ceil(fixed_est / denom)) if denom > 0.01 else 10_000_000
        p = min(p, 10_000_000)
        while p < 10_000_000 and not ok(p, margin): p += 1
        while p > 0 and ok(p - 1, margin): p -= 1
        return p if ok(p, margin) else 10_000_000
    be = find(0.0)
    tgt = max(be, find(target_margin)) if be < 10_000_000 else 10_000_000
    return {'break_even': be, 'target': tgt}

def calc_row(row, st):
    price, cost = num(row.get('price')), num(row.get('cost'))
    if num(row.get('eff_price')) > 0: price = num(row.get('eff_price'))  # v12.9.149: промо-цена, как effPrice браузера
    # v12.9.145: паритет с браузером (calcMarketplacesEconomics/costWithMultiplicity):
    # себестоимость одного продаваемого SKU — с учётом кратности отгрузки,
    # а построчные тарифы SKU важнее общих настроек.
    if st.get('multiplicity_enabled', True):
        _mult = num(row.get('multiplicity'))
        if _mult > 1: cost = rnd(cost * _mult)
    L, W, H = num(row.get('length')), num(row.get('width')), num(row.get('height'))
    vol = num(row.get('volume')) or (L * W * H / 1000 if L and W and H else 0.0)
    st2 = dict(st); st2['_volume'] = vol; st2['_weight'] = num(row.get('weight'))
    st2['_dims'] = (num(row.get('length')), num(row.get('width')), num(row.get('height')))
    if num(row.get('ozon_commission')) > 0: st2['commission_pct'] = num(row.get('ozon_commission'))
    if num(row.get('no_buy_pct')) > 0: st2['no_buy_pct'] = num(row.get('no_buy_pct'))
    elif isinstance(st.get('no_buy_by_category'), dict) and str(row.get('category') or '') in st['no_buy_by_category']:
        st2['no_buy_pct'] = num(st['no_buy_by_category'][str(row.get('category'))])
    if num(row.get('ozon_failed_cost')) > 0: st2['failed_case'] = num(row.get('ozon_failed_cost'))
    # браузер: месячный фикс (SKU + общий/число SKU) делится на прогноз продаж
    _fixed_month = num(row.get('fixed_cost')) + num(st.get('fixed_monthly_per_sku'))
    if _fixed_month > 0:
        _sales = num(row.get('sales'))
        st2['fixed_per_unit'] = _fixed_month / _sales if _sales > 0 else _fixed_month
    if num(row.get('ozon_logistics')) > 0: st2['_row_logistics'] = num(row.get('ozon_logistics'))
    if num(row.get('ozon_realfbs_delivery')) > 0: st2['_row_realfbs'] = num(row.get('ozon_realfbs_delivery'))
    if num(row.get('ozon_logistics')) > 0 or num(row.get('ozon_realfbs_delivery')) > 0:
        # заданный маршрут SKU заменяет усреднённую пару «последняя миля + сдача»
        st2['last_mile'] = num(row.get('ozon_logistics')) + num(row.get('ozon_realfbs_delivery'))
        st2['handover'] = 0
    _is_wb = str(st.get('mp_scope') or '').upper() == 'WB'
    _unit = wb_unit if _is_wb else ozon_unit
    u = _unit(price, cost, st2)
    profit = rnd(price - u['total'])
    solved = solve_prices(price, cost, st2, num(st.get('target_margin', 20)), row.get('sales', 1), unit=_unit)
    return {'article': row.get('article', ''), 'brand': row.get('brand', ''), 'total': u['total'], 'profit': profit,
            'margin': rnd(profit / price * 100, 1) if price else 0.0,
            'roi': rnd(profit / cost * 100, 1) if cost else 0.0,
            'commission': u['commission'], 'tax': u['tax'], 'returns': u['returns'],
            'storage': u['storage'], 'volume': rnd(vol, 4),
            'break_even': solved['break_even'], 'target': solved['target']}

# ---------------- SQLite ----------------
SCHEMA = '''
CREATE TABLE IF NOT EXISTS products(
  article TEXT NOT NULL, brand TEXT DEFAULT '', name TEXT DEFAULT '',
  price REAL DEFAULT 0, cost REAL DEFAULT 0, stock REAL DEFAULT 0, sales REAL DEFAULT 0,
  weight REAL DEFAULT 0, length REAL DEFAULT 0, width REAL DEFAULT 0, height REAL DEFAULT 0,
  volume REAL DEFAULT 0, oe_numbers TEXT DEFAULT '', analog_list TEXT DEFAULT '',
  source TEXT DEFAULT '', updated_at TEXT DEFAULT '',
  PRIMARY KEY(article, brand));
CREATE INDEX IF NOT EXISTS ix_products_oe ON products(oe_numbers);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS supplier_rules(email TEXT, file_pattern TEXT, profile TEXT);
CREATE TABLE IF NOT EXISTS outbox(
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, marketplace TEXT, article TEXT,
  payload TEXT, idempotency_key TEXT UNIQUE, status TEXT DEFAULT 'pending',
  attempts INTEGER DEFAULT 0, last_error TEXT DEFAULT '', created_at TEXT, sent_at TEXT);
CREATE TABLE IF NOT EXISTS price_history(article TEXT, brand TEXT DEFAULT '', price REAL, cost REAL,
  stock REAL, source TEXT, ts TEXT);
CREATE INDEX IF NOT EXISTS ix_price_history_key ON price_history(article, brand, ts);
CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, note TEXT, total INTEGER);
CREATE TABLE IF NOT EXISTS snapshot_rows(snapshot_id INTEGER, article TEXT, brand TEXT DEFAULT '',
  price REAL, cost REAL, stock REAL, PRIMARY KEY(snapshot_id, article, brand));
CREATE TABLE IF NOT EXISTS parse_sessions(id TEXT PRIMARY KEY, filename TEXT, headers TEXT,
  total INTEGER, created TEXT);
CREATE TABLE IF NOT EXISTS parse_rows(session TEXT, idx INTEGER, data TEXT,
  PRIMARY KEY(session, idx));
CREATE TABLE IF NOT EXISTS donors(article TEXT NOT NULL, brand TEXT DEFAULT '', source TEXT DEFAULT '',
  name TEXT DEFAULT '', category TEXT DEFAULT '', tnved TEXT DEFAULT '', applicability TEXT DEFAULT '',
  warranty TEXT DEFAULT '', country TEXT DEFAULT '',
  weight REAL DEFAULT 0, length REAL DEFAULT 0, width REAL DEFAULT 0, height REAL DEFAULT 0,
  oe_numbers TEXT DEFAULT '', PRIMARY KEY(article, brand, source));
CREATE TABLE IF NOT EXISTS oe_links(oe TEXT NOT NULL, article TEXT NOT NULL, brand TEXT DEFAULT '',
  PRIMARY KEY(oe, article, brand));
CREATE INDEX IF NOT EXISTS ix_oe_links_article ON oe_links(article, brand);
CREATE TABLE IF NOT EXISTS eco_results(
  article TEXT NOT NULL, brand TEXT DEFAULT '', total REAL, profit REAL, margin REAL,
  roi REAL, break_even REAL, target REAL, computed_at TEXT DEFAULT '',
  inputs_hash TEXT DEFAULT '',
  PRIMARY KEY(article, brand));
CREATE TABLE IF NOT EXISTS api_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, action TEXT,
  endpoint TEXT, status TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS mail_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, subject TEXT,
  sender TEXT, filename TEXT, rows INTEGER, status TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(article, brand, name, oe_numbers, content='products', content_rowid='rowid');
'''
_SCHEMA_DONE = set()
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try: conn.execute('PRAGMA busy_timeout=5000')
    except Exception: pass
    # v12.9.118: WAL кратно ускоряет массовые записи (импорт/обогащение) и не
    # блокирует чтение на время записи; synchronous=NORMAL безопасен при WAL.
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA temp_store=MEMORY')
    except Exception: pass
    if str(DB_PATH) in _SCHEMA_DONE:  # B4: схема и миграции — один раз на процесс
        return conn
    conn.executescript(SCHEMA)
    # миграция баз до v12.9.110: обогащаемые текстовые поля каталога
    ecols = {r[1] for r in conn.execute('PRAGMA table_info(eco_results)')}
    if 'inputs_hash' not in ecols:
        conn.execute("ALTER TABLE eco_results ADD COLUMN inputs_hash TEXT DEFAULT ''")
    dcols = {r[1] for r in conn.execute('PRAGMA table_info(donors)')}
    for col in ('warranty', 'country'):
        if col not in dcols:
            conn.execute(f"ALTER TABLE donors ADD COLUMN {col} TEXT DEFAULT ''")
    cols = {r[1] for r in conn.execute('PRAGMA table_info(products)')}
    for col in ('category', 'tnved', 'applicability',
                'barcode', 'image_url', 'extra_photos', 'ozon_sku', 'ozon_type', 'ozon_category',
                'model', 'hazard_class', 'color', 'material', 'country', 'warranty', 'diameter',
                'package_contents', 'rich_content', 'description', 'mark_required',
                'group_articles', 'cross_numbers'):
        if col not in cols:
            conn.execute(f"ALTER TABLE products ADD COLUMN {col} TEXT DEFAULT ''")
    for col in ('multiplicity', 'net_weight', 'old_price'):
        if col not in cols:
            conn.execute(f"ALTER TABLE products ADD COLUMN {col} REAL DEFAULT 0")
    # v12.9.140: поля обогащения браузера, которых не было в SQLite
    for col in ('original_article', 'category_type', 'category_src', 'ozon_description_category_id',
                'ozon_type_id', 'visible_reason', 'mark_status', 'mark_code', 'dimensions_str', 'currency'):
        if col not in cols:
            conn.execute(f"ALTER TABLE products ADD COLUMN {col} TEXT DEFAULT ''")
    for col in ('ozon_commission', 'ozon_logistics', 'ozon_realfbs_delivery', 'ozon_failed_cost',
                'min_stock', 'no_buy_pct', 'fixed_cost'):
        if col not in cols:
            conn.execute(f"ALTER TABLE products ADD COLUMN {col} REAL DEFAULT 0")
    if 'eff_price' not in cols:
        conn.execute("ALTER TABLE products ADD COLUMN eff_price REAL DEFAULT 0")
    dcols = {r[1] for r in conn.execute('PRAGMA table_info(donors)')}
    for col, typ, dflt in (('barcode', 'TEXT', "''"), ('image_url', 'TEXT', "''"), ('multiplicity', 'REAL', '0')):
        if col not in dcols:
            conn.execute(f"ALTER TABLE donors ADD COLUMN {col} {typ} DEFAULT {dflt}")
    # B5: retention — история цен год, лог API 90 дней
    try:
        conn.execute("DELETE FROM price_history WHERE ts < datetime('now','-365 days')")
        conn.execute("DELETE FROM api_log WHERE ts < datetime('now','-90 days')")
    except Exception: pass
    conn.commit()
    _SCHEMA_DONE.add(str(DB_PATH))
    return conn

def log_api(conn, action, endpoint, status, detail=''):
    conn.execute('INSERT INTO api_log(ts,action,endpoint,status,detail) VALUES(datetime("now"),?,?,?,?)',
                 (action, endpoint, status, str(detail)[:500]))
    conn.commit()

def get_settings(conn):
    return {r['key']: r['value'] for r in conn.execute('SELECT key,value FROM settings')}

def _dpapi(data: bytes, protect: bool) -> bytes:
    # A3 (аудит v12.9.133): на Windows секреты хранятся зашифрованными DPAPI
    # (привязка к учётной записи пользователя); на прочих ОС — как есть.
    if os.name != 'nt': return data
    import ctypes, base64 as _b64
    class BLOB(ctypes.Structure):
        _fields_ = [('cbData', ctypes.c_ulong), ('pbData', ctypes.POINTER(ctypes.c_char))]
    if protect:
        raw = data
    else:
        try: raw = _b64.b64decode(data)
        except Exception: return data  # старый открытый формат — читаем как есть
    buf = ctypes.create_string_buffer(raw, len(raw))
    blob_in, blob_out = BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), BLOB()
    fn = (ctypes.windll.crypt32.CryptProtectData if protect
          else ctypes.windll.crypt32.CryptUnprotectData)
    if not fn(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        return data if not protect else (_b64.b64encode(data))
    out = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    import base64 as _b64
    return _b64.b64encode(out) if protect else out

def save_secret(key, value):
    cur = {}
    if SECRETS_PATH.exists():
        try: cur = json.loads(_dpapi(SECRETS_PATH.read_bytes(), False).decode('utf-8'))
        except Exception: cur = {}
    if value: cur[key] = value
    else: cur.pop(key, None)  # пустое значение = удалить секрет
    SECRETS_PATH.write_bytes(_dpapi(json.dumps(cur, ensure_ascii=False).encode('utf-8'), True))

def secrets():
    env = {k: os.environ.get(k) for k in
           ('UC_OZON_CLIENT_ID', 'UC_OZON_API_KEY', 'UC_WB_TOKEN', 'UC_MAIL_PASSWORD', 'UC_YM_TOKEN')}
    file_secrets = {}
    if SECRETS_PATH.exists():
        try: file_secrets = json.loads(_dpapi(SECRETS_PATH.read_bytes(), False).decode('utf-8'))
        except Exception: file_secrets = {}
    merged = dict(file_secrets)
    for k, v in env.items():
        if v: merged[k] = v
    return merged

# ---------------- импорт строк (CSV/XLSX/ZIP) ----------------
ALIASES = {
    'article': ('артикул', 'article', 'sku', 'каталожный номер', 'код товара', 'артикул продавца', 'артикул поставщика'),
    'brand': ('бренд', 'brand', 'производитель'),
    'name': ('название', 'name', 'наименование', 'описание'), 'price': ('цена', 'price'),
    'barcode': ('штрихкод', 'barcode', 'ean'), 'multiplicity': ('кратность', 'multiplicity'),
    'cost': ('себестоимость', 'cost', 'закупка'), 'stock': ('остаток', 'stock', 'количество'),
    'oe_numbers': ('oe', 'oem', 'ое', 'номер oe'), 'weight': ('вес', 'weight'),
    'sales': ('продажи', 'sales'), 'category': ('категор', 'category'),
    'tnved': ('тн вэд', 'тнвэд', 'tnved', 'hs code'), 'applicability': ('применяем', 'applicab', 'совмест'),
    'length': ('длина', 'length'), 'width': ('ширина', 'width'), 'height': ('высота', 'height'),
    # v12.9.140: поля обогащения браузерного импорта (STD/FIELD_ALIAS приложения)
    'volume': ('объём', 'объем', 'volume'), 'analog_list': ('аналоги', 'analog', 'кроссы'),
    'group_articles': ('группа артикулов', 'group'), 'cross_numbers': ('кросс-номера', 'кросс номера', 'cross'),
    'original_article': ('ориг. артикул', 'оригинальный артикул', 'original'), 'category_type': ('вид категории', 'тип категории', 'подкатегория'),
    'category_src': ('исходная категория', 'путь категории', 'breadcrumb'), 'currency': ('валюта', 'currency'),
    'warranty': ('гарантия', 'warranty'), 'country': ('страна-изготовитель', 'страна', 'country'),
    'image_url': ('ссылка на изображение', 'изображение', 'фото', 'image'), 'extra_photos': ('дополнительные фото', 'extra_photos'),
    'ozon_sku': ('sku ozon', 'ozon sku', 'ozon_sku'), 'ozon_category': ('категория ozon', 'ozon_category'),
    'ozon_type': ('тип ozon', 'ozon_type'), 'ozon_description_category_id': ('id категории ozon', 'description_category_id'),
    'ozon_type_id': ('id типа ozon', 'type_id'), 'model': ('модель', 'model'), 'color': ('цвет', 'color'),
    'material': ('материал', 'material'), 'description': ('аннотация', 'описание товара', 'description'),
    'dimensions_str': ('весогабариты', 'габариты', 'dimensions'), 'mark_required': ('нужен честный знак', 'требуется сертификат', 'маркировка'),
    'mark_status': ('статус честного знака', 'mark_status'), 'mark_code': ('код маркировки', 'mark_code'),
    'min_stock': ('мин. остаток', 'минимальный остаток', 'min_stock', 'неснижаемый'),
    'no_buy_pct': ('невыкуп', 'no_buy', 'возврат'), 'fixed_cost': ('фикс. расходы', 'fixed'),
    'ozon_commission': ('вознаграждение ozon', 'комиссия ozon', 'ozon_commission'),
    'ozon_logistics': ('логистика ozon', 'ozon_logistics', 'ozon logistics'),
    'ozon_realfbs_delivery': ('ozon_realfbs_delivery', 'доставка ozon realfbs', 'ozon realfbs доставка'),
    'net_weight': ('вес нетто', 'масса нетто', 'вес товара без упаковки', 'net_weight', 'net weight'),
    'old_price': ('зачёркнутая цена', 'зачеркнутая цена', 'старая цена', 'old_price')}
def map_header(header):
    """v12.9.146 (проверка №3): назначение колонок однозначное, как guessField
       браузера: одна колонка — одно поле. Раньше независимый проход по полям
       отдавал «Код ТН ВЭД» и в article, и в tnved, а «Зачёркнутую цену» —
       и в price, и в old_price. Побеждает лучшее совпадение (точное >
       начало > подстрока), при равенстве — порядок полей как объявлен."""
    low = [str(h or '').strip().lower() for h in header]
    cands = []  # (score, -len(alias), field_order, col, field): длинный алиас точнее
    for fo, (field, names) in enumerate(ALIASES.items()):
        for i, h in enumerate(low):
            if not h: continue
            if field == 'article' and 'штрих' in h: continue
            sc, best_len = -1, 0
            for n in names:
                if h == n: sc, best_len = 0, len(n); break
            if sc < 0:
                for n in names:
                    if h.startswith(n): sc, best_len = 1, max(best_len, len(n)); break
            if sc < 0:
                for n in names:
                    if n in h: sc, best_len = 2, max(best_len, len(n))
            if sc >= 0: cands.append((sc, -best_len, fo, i, field))
    out, used_cols, used_fields = {}, set(), set()
    for sc, _nl, fo, i, field in sorted(cands):
        if i in used_cols or field in used_fields: continue
        out[field] = i; used_cols.add(i); used_fields.add(field)
    return out

def _apply_units(item, mp, headers):
    """v12.9.147: единицы как в браузерном импорте (parseDimensionCm и вес):
       длина/ширина/высота в базе — сантиметры, вес — килограммы, объём — литры.
       Движок раньше писал число как есть: «Длина, мм» давала 10-кратную ошибку.
       Сводную ячейку габаритов («230x170x80») разбираем в Д/Ш/В, если пусты."""
    def hdr(f):
        i = mp.get(f)
        return str(headers[i]).lower() if i is not None and i < len(headers) else ''
    for f in ('length', 'width', 'height'):
        if f in item and num(item[f]) > 0:
            h = hdr(f)
            if 'мм' in h or 'mm' in h: item[f] = num(item[f]) / 10
    for f in ('weight', 'net_weight'):
        if f in item and num(item[f]) > 0:
            h = hdr(f)
            if 'грамм' in h or ', г' in h or '(г' in h or ' g' in h or h.rstrip().endswith('г'): item[f] = num(item[f]) / 1000
    if 'volume' in item and num(item['volume']) > 0:
        h = hdr('volume')
        if 'см3' in h or 'см³' in h or 'cm3' in h: item['volume'] = num(item['volume']) / 1000
        elif 'м3' in h or 'м³' in h or 'm3' in h: item['volume'] = num(item['volume']) * 1000
    ds = str(item.get('dimensions_str') or '').strip()
    if ds and not all(num(item.get(f)) > 0 for f in ('length', 'width', 'height')):
        parts = [x for x in re.split(r'[*x×х/|;]', ds.replace(',', '.')) if str(x).strip()]
        nums = []
        for x in parts[:3]:
            m = re.search(r'\d+(?:\.\d+)?', str(x))
            if m: nums.append(float(m.group(0)))
        if len(nums) == 3 and all(n > 0 for n in nums):
            k = 0.1 if ('мм' in hdr('dimensions_str') or 'mm' in hdr('dimensions_str')) else 1
            for f, v in zip(('length', 'width', 'height'), nums):
                if not num(item.get(f)) > 0: item[f] = v * k
    return item

def rows_from_csv_bytes(data):
    text = data.decode('utf-8-sig', errors='replace')
    if '\ufffd' in text[:400]:
        # как браузерный импорт: российские прайсы часто в windows-1251
        try: text = data.decode('cp1251')
        except Exception: pass
    delim = ';' if text.split('\n', 1)[0].count(';') >= text.split('\n', 1)[0].count(',') else ','
    try:  # B9: Sniffer учитывает кавычки; fallback — эвристика по первой строке
        delim = csv.Sniffer().sniff(text[:2048], delimiters=';,\t').delimiter
    except Exception: pass
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows: return []
    mp = map_header(rows[0])
    if 'article' not in mp: return []
    out = []
    for r in rows[1:]:
        if not r or mp['article'] >= len(r) or not str(r[mp['article']]).strip(): continue
        item = {}
        for f, i in mp.items():
            item[f] = r[i] if i < len(r) else ''
        out.append(_apply_units(item, mp, rows[0]))
    return out

def _xlsx_sheet_rows(data):
    """v12.9.141: чтение XLSX чистым stdlib (zip + XML) — движок собирается в
       exe без openpyxl, а импорт XLSX падал с «openpyxl не установлен».
       Понимает sharedStrings, inlineStr, числа и строки; первый лист книги."""
    import zipfile
    import xml.etree.ElementTree as ET
    NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    RNS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        shared = []
        if 'xl/sharedStrings.xml' in names:
            root = ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in root.findall(NS + 'si'):
                shared.append(''.join(t.text or '' for t in si.iter(NS + 't')))
        # целевой лист: первый из workbook.xml по rels, иначе sheet1
        sheet_path = 'xl/worksheets/sheet1.xml'
        try:
            wbroot = ET.fromstring(z.read('xl/workbook.xml'))
            rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
            relmap = {r.get('Id'): r.get('Target') for r in rels}
            first = wbroot.find(NS + 'sheets/' + NS + 'sheet')
            if first is not None:
                tgt = relmap.get(first.get(RNS + 'id'), '')
                if tgt:
                    sheet_path = 'xl/' + tgt.lstrip('/') if not tgt.startswith('xl/') else tgt
        except Exception: pass
        if sheet_path not in names:
            cand = sorted(n for n in names if n.startswith('xl/worksheets/sheet'))
            if not cand: return []
            sheet_path = cand[0]
        root = ET.fromstring(z.read(sheet_path))
    def col_idx(ref):
        n = 0
        for ch in ref:
            if ch.isalpha(): n = n * 26 + (ord(ch.upper()) - 64)
            else: break
        return n - 1
    rows = []
    for row_el in root.iter(NS + 'row'):
        cells = {}
        maxc = -1
        for c in row_el.findall(NS + 'c'):
            idx = col_idx(c.get('r', 'A1'))
            t = c.get('t')
            v = c.find(NS + 'v')
            val = None
            if t == 'inlineStr':
                is_el = c.find(NS + 'is')
                val = ''.join(x.text or '' for x in is_el.iter(NS + 't')) if is_el is not None else ''
            elif v is not None and v.text is not None:
                if t == 's':
                    try: val = shared[int(v.text)]
                    except Exception: val = ''
                elif t in ('str', 'e'):
                    val = v.text
                else:
                    try:
                        fv = float(v.text)
                        val = int(fv) if fv == int(fv) and '.' not in v.text else fv
                    except Exception: val = v.text
            if val is not None:
                cells[idx] = val; maxc = max(maxc, idx)
        if maxc >= 0:
            rows.append([cells.get(i, '') for i in range(maxc + 1)])
    return rows

def rows_from_xlsx_bytes(data):
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    except ImportError:
        rows = _xlsx_sheet_rows(data)
    if not rows: return []
    mp = map_header(rows[0])
    if 'article' not in mp: return []
    out = []
    for r in rows[1:]:
        if not r or mp['article'] >= len(r) or r[mp['article']] in (None, ''): continue
        out.append(_apply_units({f: (r[i] if i < len(r) and r[i] is not None else '') for f, i in mp.items()}, mp, rows[0]))
    return out

def files_from_zip(data):
    # B3 (аудит №2): лимиты против zip-бомб — по числу файлов и распакованному объёму
    out = []; total = 0
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos = [i for i in z.infolist() if i.filename.lower().endswith(('.csv', '.xlsx'))]
        if len(infos) > 200: raise ValueError('в архиве больше 200 файлов данных')
        for info in infos:
            if info.file_size > 200 * 1024 * 1024: raise ValueError('файл в архиве больше 200 МБ: ' + info.filename)
            total += info.file_size
            if total > 500 * 1024 * 1024: raise ValueError('суммарный объём архива больше 500 МБ')
            out.append((os.path.basename(info.filename), z.read(info.filename)))
    return out

def import_rows(conn, rows, source, rebuild_fts=True):
    n = 0
    for r in rows:
        art = str(r.get('article', '')).strip()
        if not art: continue
        brand = str(r.get('brand', '')).strip()
        old = conn.execute('SELECT price,cost,stock,sales,weight,length,width,height FROM products WHERE article=? AND brand=?', (art, brand)).fetchone()
        # B1 (аудит №2): поля, которых нет в строке источника, не трогаем —
        # ценовой файл без остатков не должен обнулять остатки/габариты.
        # Явно переданный 0 (ключ есть) — честное обновление.
        def eff(k):
            if k in r: return num(r.get(k))
            if old is None: return 0.0
            try: return float(old[k])
            except Exception: return 0.0
        conn.execute('''INSERT INTO products(article,brand,name,price,cost,stock,sales,weight,length,width,height,volume,oe_numbers,analog_list,category,tnved,applicability,barcode,image_url,extra_photos,ozon_sku,ozon_type,ozon_category,model,hazard_class,color,material,country,warranty,diameter,package_contents,rich_content,description,mark_required,group_articles,cross_numbers,multiplicity,net_weight,old_price,original_article,category_type,category_src,ozon_description_category_id,ozon_type_id,mark_status,mark_code,dimensions_str,currency,ozon_commission,ozon_logistics,ozon_realfbs_delivery,ozon_failed_cost,min_stock,no_buy_pct,fixed_cost,source,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime("now"))
            ON CONFLICT(article,brand) DO UPDATE SET
              name=COALESCE(NULLIF(excluded.name,''),products.name),
              price=CASE WHEN excluded.price>0 THEN excluded.price ELSE products.price END,
              cost=CASE WHEN excluded.cost>0 THEN excluded.cost ELSE products.cost END,
              stock=excluded.stock, sales=excluded.sales, weight=excluded.weight, length=excluded.length,
              width=excluded.width, height=excluded.height,
              volume=CASE WHEN excluded.volume>0 THEN excluded.volume ELSE products.volume END,
              oe_numbers=CASE WHEN excluded.oe_numbers<>'' THEN excluded.oe_numbers ELSE products.oe_numbers END,
              analog_list=CASE WHEN excluded.analog_list<>'' THEN excluded.analog_list ELSE products.analog_list END,
              category=CASE WHEN excluded.category<>'' THEN excluded.category ELSE products.category END,
              tnved=CASE WHEN excluded.tnved<>'' THEN excluded.tnved ELSE products.tnved END,
              applicability=CASE WHEN excluded.applicability<>'' THEN excluded.applicability ELSE products.applicability END,
              barcode=CASE WHEN excluded.barcode<>'' THEN excluded.barcode ELSE products.barcode END,
              image_url=CASE WHEN excluded.image_url<>'' THEN excluded.image_url ELSE products.image_url END,
              extra_photos=CASE WHEN excluded.extra_photos<>'' THEN excluded.extra_photos ELSE products.extra_photos END,
              ozon_sku=CASE WHEN excluded.ozon_sku<>'' THEN excluded.ozon_sku ELSE products.ozon_sku END,
              ozon_type=CASE WHEN excluded.ozon_type<>'' THEN excluded.ozon_type ELSE products.ozon_type END,
              ozon_category=CASE WHEN excluded.ozon_category<>'' THEN excluded.ozon_category ELSE products.ozon_category END,
              model=CASE WHEN excluded.model<>'' THEN excluded.model ELSE products.model END,
              hazard_class=CASE WHEN excluded.hazard_class<>'' THEN excluded.hazard_class ELSE products.hazard_class END,
              color=CASE WHEN excluded.color<>'' THEN excluded.color ELSE products.color END,
              material=CASE WHEN excluded.material<>'' THEN excluded.material ELSE products.material END,
              country=CASE WHEN excluded.country<>'' THEN excluded.country ELSE products.country END,
              warranty=CASE WHEN excluded.warranty<>'' THEN excluded.warranty ELSE products.warranty END,
              diameter=CASE WHEN excluded.diameter<>'' THEN excluded.diameter ELSE products.diameter END,
              package_contents=CASE WHEN excluded.package_contents<>'' THEN excluded.package_contents ELSE products.package_contents END,
              rich_content=CASE WHEN excluded.rich_content<>'' THEN excluded.rich_content ELSE products.rich_content END,
              description=CASE WHEN excluded.description<>'' THEN excluded.description ELSE products.description END,
              mark_required=CASE WHEN excluded.mark_required<>'' THEN excluded.mark_required ELSE products.mark_required END,
              group_articles=CASE WHEN excluded.group_articles<>'' THEN excluded.group_articles ELSE products.group_articles END,
              cross_numbers=CASE WHEN excluded.cross_numbers<>'' THEN excluded.cross_numbers ELSE products.cross_numbers END,
              multiplicity=CASE WHEN excluded.multiplicity>0 THEN excluded.multiplicity ELSE products.multiplicity END,
              net_weight=CASE WHEN excluded.net_weight>0 THEN excluded.net_weight ELSE products.net_weight END,
              old_price=CASE WHEN excluded.old_price>0 THEN excluded.old_price ELSE products.old_price END,
              original_article=CASE WHEN excluded.original_article<>'' THEN excluded.original_article ELSE products.original_article END,
              category_type=CASE WHEN excluded.category_type<>'' THEN excluded.category_type ELSE products.category_type END,
              category_src=CASE WHEN excluded.category_src<>'' THEN excluded.category_src ELSE products.category_src END,
              ozon_description_category_id=CASE WHEN excluded.ozon_description_category_id<>'' THEN excluded.ozon_description_category_id ELSE products.ozon_description_category_id END,
              ozon_type_id=CASE WHEN excluded.ozon_type_id<>'' THEN excluded.ozon_type_id ELSE products.ozon_type_id END,
              mark_status=CASE WHEN excluded.mark_status<>'' THEN excluded.mark_status ELSE products.mark_status END,
              mark_code=CASE WHEN excluded.mark_code<>'' THEN excluded.mark_code ELSE products.mark_code END,
              dimensions_str=CASE WHEN excluded.dimensions_str<>'' THEN excluded.dimensions_str ELSE products.dimensions_str END,
              currency=CASE WHEN excluded.currency<>'' THEN excluded.currency ELSE products.currency END,
              ozon_commission=CASE WHEN excluded.ozon_commission<>0 THEN excluded.ozon_commission ELSE products.ozon_commission END,
              ozon_logistics=CASE WHEN excluded.ozon_logistics<>0 THEN excluded.ozon_logistics ELSE products.ozon_logistics END,
              ozon_realfbs_delivery=CASE WHEN excluded.ozon_realfbs_delivery<>0 THEN excluded.ozon_realfbs_delivery ELSE products.ozon_realfbs_delivery END,
              ozon_failed_cost=CASE WHEN excluded.ozon_failed_cost<>0 THEN excluded.ozon_failed_cost ELSE products.ozon_failed_cost END,
              min_stock=CASE WHEN excluded.min_stock<>0 THEN excluded.min_stock ELSE products.min_stock END,
              no_buy_pct=CASE WHEN excluded.no_buy_pct<>0 THEN excluded.no_buy_pct ELSE products.no_buy_pct END,
              fixed_cost=CASE WHEN excluded.fixed_cost<>0 THEN excluded.fixed_cost ELSE products.fixed_cost END,
              source=excluded.source, updated_at=datetime("now")''',
            (art, str(r.get('brand', '')).strip(), str(r.get('name', '')),
             num(r.get('price')), num(r.get('cost')), eff('stock'), eff('sales'), eff('weight'),
             eff('length'), eff('width'), eff('height'), num(r.get('volume')),
             str(r.get('oe_numbers', '')), str(r.get('analog_list', '')), str(r.get('category', '')), str(r.get('tnved', '')),
             str(r.get('applicability', '')),
             str(r.get('barcode', '')), str(r.get('image_url', '')), str(r.get('extra_photos', '')),
             str(r.get('ozon_sku', '')), str(r.get('ozon_type', '')), str(r.get('ozon_category', '')),
             str(r.get('model', '')), str(r.get('hazard_class', '')), str(r.get('color', '')),
             str(r.get('material', '')), str(r.get('country', '')), str(r.get('warranty', '')),
             str(r.get('diameter', '')), str(r.get('package_contents', '')), str(r.get('rich_content', '')),
             str(r.get('description', '')), str(r.get('mark_required', '')), str(r.get('group_articles', '')),
             str(r.get('cross_numbers', '')), num(r.get('multiplicity')), num(r.get('net_weight')),
             num(r.get('old_price')),
             str(r.get('original_article', '')), str(r.get('category_type', '')), str(r.get('category_src', '')), str(r.get('ozon_description_category_id', '')), str(r.get('ozon_type_id', '')), str(r.get('mark_status', '')), str(r.get('mark_code', '')), str(r.get('dimensions_str', '')), str(r.get('currency', '')),
             eff('ozon_commission'), eff('ozon_logistics'), eff('ozon_realfbs_delivery'), eff('ozon_failed_cost'), eff('min_stock'), eff('no_buy_pct'), eff('fixed_cost'), source))
        if 'eff_price' in r:
            conn.execute('UPDATE products SET eff_price=? WHERE article=? AND brand=?',
                         (num(r.get('eff_price')), art, brand))
        # история цен (п.6): только реальные изменения цены/себестоимости
        eff_price = num(r.get('price')) if num(r.get('price')) > 0 else (old['price'] if old else 0)
        eff_cost = num(r.get('cost')) if num(r.get('cost')) > 0 else (old['cost'] if old else 0)
        if eff_price > 0 and (not old or abs(old['price'] - eff_price) > 1e-9 or abs(old['cost'] - eff_cost) > 1e-9):
            conn.execute('INSERT INTO price_history(article,brand,price,cost,stock,source,ts) VALUES(?,?,?,?,?,?,datetime("now"))',
                         (art, brand, eff_price, eff_cost, eff('stock'), source))
        n += 1
    if rebuild_fts:
        conn.execute("INSERT INTO products_fts(products_fts) VALUES('rebuild')")
    conn.commit()
    if rebuild_fts:  # финальный чанк: сжимаем WAL, иначе файл журнала растёт без bound
        try: conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        except Exception: pass
    return n

# ---------------- почта (IMAP) ----------------
def _decode_hdr(v):
    parts = decode_header(v or '')
    return ''.join(p.decode(enc or 'utf-8', errors='replace') if isinstance(p, bytes) else p
                   for p, enc in parts)
def mail_check_once(cfg=None, sec=None):
    cfg = cfg or {}
    sec = sec or secrets()
    host = cfg.get('imap_host') or os.environ.get('UC_IMAP_HOST', '')
    user = cfg.get('imap_user') or os.environ.get('UC_IMAP_USER', '')
    password = sec.get('UC_MAIL_PASSWORD') or os.environ.get('UC_IMAP_PASSWORD', '')
    if not (host and user and password):
        raise RuntimeError('Почта не настроена: нужны UC_IMAP_HOST, UC_IMAP_USER и пароль приложения (UC_MAIL_PASSWORD)')
    days = int(num(cfg.get('mail_days', 14))) or 14
    conn = db()
    rules = [dict(r) for r in conn.execute('SELECT email,file_pattern,profile FROM supplier_rules')]
    imported, seen = 0, 0
    m = imaplib.IMAP4_SSL(host)
    try:
        m.login(user, password)
        m.select('INBOX')
        since = time.strftime('%d-%b-%Y', time.gmtime(time.time() - days * 86400))
        _, data = m.search(None, f'(SINCE {since})')
        ids = data[0].split()[-200:]
        for mid in ids:
            _, msg_data = m.fetch(mid, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            sender = _decode_hdr(msg.get('From', ''))
            subject = _decode_hdr(msg.get('Subject', ''))
            for part in msg.walk():
                fname = _decode_hdr(part.get_filename() or '')
                if not fname or not fname.lower().endswith(('.csv', '.xlsx', '.zip')): continue
                seen += 1
                if rules and not any((not r['email'] or r['email'].lower() in sender.lower()) and
                                     (not r['file_pattern'] or re.search(re.escape(r['file_pattern']).replace(r'\*', '.*'), fname, re.I))
                                     for r in rules):
                    continue
                payload = part.get_payload(decode=True) or b''
                files = files_from_zip(payload) if fname.lower().endswith('.zip') else [(fname, payload)]
                for name, blob in files:
                    try:
                        rows = rows_from_xlsx_bytes(blob) if name.lower().endswith('.xlsx') else rows_from_csv_bytes(blob)
                        n = import_rows(conn, rows, f'mail:{sender} {name}')
                        imported += n
                        conn.execute('INSERT INTO mail_log(ts,subject,sender,filename,rows,status) VALUES(datetime("now"),?,?,?,?,?)',
                                     (subject, sender, name, n, 'ok'))
                        conn.commit()
                    except Exception as e:
                        conn.execute('INSERT INTO mail_log(ts,subject,sender,filename,rows,status) VALUES(datetime("now"),?,?,?,?,?)',
                                     (subject, sender, name, 0, 'err: ' + str(e)[:200]))
                        conn.commit()
    finally:
        try: m.logout()
        except Exception: pass
    log_api(conn, 'mailCheck', host, 'ok', f'вложений {seen}, строк {imported}')
    return {'attachments': seen, 'imported_rows': imported}

# ---------------- полный пересчёт каталога (v12.9.104) ----------------
def _calc_rows_chunk(task):
    rows, st = task
    return [calc_row(r, st) for r in rows]

def _calc_all(rows, st):
    """Пересчёт всех строк: многопроцессно, где можно (аудит п.4).
       calc_row чистый, параллелится чанками; запись результатов — всегда
       одним процессом. Любая проблема с Pool -> тихий откат на 1 процесс.
       В frozen-сборке (PyInstaller) Pool не используем: spawn там ненадёжен."""
    seq = lambda: [calc_row(r, st) for r in rows]
    if len(rows) < 2000 or os.environ.get('UC_ENGINE_NO_PARALLEL') or getattr(sys, 'frozen', False):
        return seq(), False
    try:
        import multiprocessing as mp
        workers = int(os.environ.get('UC_ENGINE_WORKERS') or min(4, os.cpu_count() or 1))
        if workers <= 1: return seq(), False
        step = max(500, -(-len(rows) // (workers * 4)))
        chunks = [rows[i:i + step] for i in range(0, len(rows), step)]
        with mp.Pool(workers) as pool:
            parts = pool.map(_calc_rows_chunk, [(c, st) for c in chunks])
        return [r for part in parts for r in part], True
    except Exception:
        return seq(), False

_ECO_FIELDS = ('price', 'eff_price', 'cost', 'sales', 'weight', 'length', 'width', 'height', 'volume', 'category',
               'multiplicity', 'ozon_commission', 'ozon_logistics', 'ozon_realfbs_delivery',
               'ozon_failed_cost', 'no_buy_pct', 'fixed_cost')

def _eco_hash(row, st):
    import hashlib
    payload = [row.get(k) for k in _ECO_FIELDS]
    raw = json.dumps([payload, st], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def recalc_catalog(conn, st, force=False):
    """Инкрементальный пересчёт (v12.9.119): строка пересчитывается только
       если изменились её расчётные входы или настройки экономики (хэш в
       eco_results.inputs_hash). force=True — полный пересчёт как раньше.
       Итоги ответа считаются по всей таблице результатов, семантика та же."""
    rows = [dict(r) for r in conn.execute('SELECT article,brand,price,eff_price,cost,sales,weight,length,width,height,volume,category,multiplicity,ozon_commission,ozon_logistics,ozon_realfbs_delivery,ozon_failed_cost,no_buy_pct,fixed_cost FROM products').fetchall()]
    old = {(r['article'], r['brand']): r['inputs_hash'] for r in
           conn.execute('SELECT article,brand,inputs_hash FROM eco_results')}
    todo, hashes = [], {}
    for row in rows:
        h = _eco_hash(row, st)
        hashes[(row['article'], row['brand'])] = h
        if force or old.get((row['article'], row['brand'])) != h: todo.append(row)
    results, parallel = _calc_all(todo, st)
    conn.executemany('''INSERT INTO eco_results(article,brand,total,profit,margin,roi,break_even,target,computed_at,inputs_hash)
        VALUES(?,?,?,?,?,?,?,?,datetime("now"),?)
        ON CONFLICT(article,brand) DO UPDATE SET total=excluded.total, profit=excluded.profit,
          margin=excluded.margin, roi=excluded.roi, break_even=excluded.break_even,
          target=excluded.target, computed_at=excluded.computed_at, inputs_hash=excluded.inputs_hash''',
        [(res['article'], row['brand'], res['total'], res['profit'], res['margin'],
          res['roi'], res['break_even'], res['target'], hashes[(row['article'], row['brand'])])
         for row, res in zip(todo, results)])
    alive = set(hashes)
    for key in old:
        if key not in alive: conn.execute('DELETE FROM eco_results WHERE article=? AND brand=?', key)
    conn.commit()
    agg = conn.execute('SELECT COUNT(*) n, SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END) prof, AVG(profit) avgp FROM eco_results').fetchone()
    n = agg['n'] or 0
    log_api(conn, 'recalcCatalog', 'sqlite', 'ok', f'{len(todo)} из {len(rows)} SKU')
    return {'recalculated': len(todo), 'skipped': len(rows) - len(todo), 'total_sku': len(rows),
            'profitable': agg['prof'] or 0,
            'avg_profit': rnd(agg['avgp'] or 0, 2) if n else 0, 'parallel': parallel}

# ---------------- импорт файла целиком + обогащение OE (v12.9.105) ----------------
def import_file_bytes(conn, filename, data, enrich_only=False):
    """Файл разбирает движок, а не браузер: CSV/XLSX/ZIP -> строки -> каталог.
       enrich_only (v12.9.145): файл не первый (не прайс) — только обогащение
       уже существующих SKU, новые строки не вставляются."""
    name = os.path.basename(str(filename or 'file'))
    files = files_from_zip(data) if name.lower().endswith('.zip') else [(name, data)]
    ensure_free_space(sum(len(b) for _, b in files))  # v12.9.144: отказ до записи, а не в середине
    total = 0; skipped = 0
    existing = None
    if enrich_only:
        existing = {_norm_pair(r[0], r[1]) for r in conn.execute('SELECT article,brand FROM products')}
    try:
        for fname, blob in files:
            rows = rows_from_xlsx_bytes(blob) if fname.lower().endswith('.xlsx') else rows_from_csv_bytes(blob)
            if existing is not None:
                kept = []
                for r in rows:
                    if _norm_pair(r.get('article', ''), r.get('brand', '')) in existing: kept.append(r)
                    elif str(r.get('article', '')).strip(): skipped += 1
                rows = kept
            total += import_rows(conn, rows, f'file:{name}', rebuild_fts=False)
        conn.execute("INSERT INTO products_fts(products_fts) VALUES('rebuild')")
        conn.commit()
    except Exception:
        try: conn.rollback()  # не оставлять полуприменённый импорт
        except Exception: pass
        raise
    log_api(conn, 'importFile', name, 'ok', f'строк {total}, вне прайса пропущено {skipped}')
    return {'file': name, 'imported': total, 'skipped_outside_price': skipped, 'enrich_only': bool(enrich_only)}

def _norm_key_part(v):
    """Как normArticle в приложении: верхний регистр, только буквы/цифры."""
    return re.sub(r'[^A-Z0-9А-ЯЁ]', '', str(v or '').upper())

def _norm_pair(article, brand):
    return _norm_key_part(article) + '|' + _norm_key_part(brand)

def _oe_codes(raw):
    out = []
    for part in re.split(r'[,;/|\s]+', str(raw or '').upper()):
        code = re.sub(r'[^A-Z0-9А-ЯЁ]', '', part)
        if code: out.append(code)
    return out

def enrich_oe(conn):
    """Обогащение по OE-графу в SQL: транзитивные группы (union-find по oe_links),
       заполняются только пустые поля; артикулы группы дописываются в аналоги."""
    conn.execute('DELETE FROM oe_links')
    prods = conn.execute('SELECT article,brand,name,weight,length,width,height,oe_numbers,analog_list FROM products').fetchall()
    by_key = {(r['article'], r['brand']): dict(r) for r in prods}
    oe_to_keys = {}
    for r in prods:
        for oe in _oe_codes(r['oe_numbers']):
            conn.execute('INSERT OR IGNORE INTO oe_links(oe,article,brand) VALUES(?,?,?)', (oe, r['article'], r['brand']))
            oe_to_keys.setdefault(oe, set()).add((r['article'], r['brand']))
    conn.commit()
    parent = {k: k for k in by_key}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: parent[rb] = ra
    for keys in oe_to_keys.values():
        keys = list(keys)
        for k in keys[1:]: union(keys[0], k)
    groups = {}
    for k in by_key: groups.setdefault(find(k), []).append(k)
    filled = {'name': 0, 'dims': 0, 'analog_list': 0}
    multi_groups = 0
    for members in groups.values():
        if len(members) < 2: continue
        multi_groups += 1
        rows = [by_key[k] for k in members]
        def dims_of(r): return (num(r['length']), num(r['width']), num(r['height']), num(r['weight']))
        complete = [r for r in rows if all(v > 0 for v in dims_of(r))]
        names = [r['name'] for r in rows if str(r['name'] or '').strip()]
        best_name = max(set(names), key=names.count) if names else ''
        for r in rows:
            updates = {}
            if not str(r['name'] or '').strip() and best_name:
                updates['name'] = best_name; filled['name'] += 1
            if complete and not all(v > 0 for v in dims_of(r)):
                same_art = [d for d in complete if d['article'] == r['article']]
                donor = same_art[0] if same_art else complete[0]
                d = dims_of(donor)
                cur = dims_of(r)
                # только пустые компоненты: уже заполненные значения не перетираем
                for i, f in enumerate(('length', 'width', 'height', 'weight')):
                    if not cur[i] > 0 and d[i] > 0: updates[f] = d[i]
                if updates: filled['dims'] += 1
            others = sorted({m[0] for m in members if m[0] != r['article']})
            if others:
                cur = {x.strip() for x in str(r['analog_list'] or '').split(',') if x.strip()}
                merged = sorted(cur | set(others))
                if merged != sorted(cur):
                    updates['analog_list'] = ', '.join(merged); filled['analog_list'] += 1
            if updates:
                sets = ', '.join(f'{k}=?' for k in updates)
                conn.execute(f'UPDATE products SET {sets} WHERE article=? AND brand=?',
                             (*updates.values(), r['article'], r['brand']))
    conn.commit()
    log_api(conn, 'enrichOe', 'sqlite', 'ok', f'групп {multi_groups}, заполнено {filled}')
    return {'groups': multi_groups, 'filled': filled,
            'oe_links': conn.execute('SELECT COUNT(*) c FROM oe_links').fetchone()['c']}

# ---------------- полное обогащение (Каталог V на движке, v12.9.110) ----------------
def import_donors(conn, rows, source):
    """Реестр доноров (аналог HVC.parts): записи справочных файлов, по ключу
       Артикул+Бренд, несколько источников на ключ допустимы."""
    n = 0
    for r in rows:
        art = str(r.get('article', '')).strip()
        if not art: continue
        conn.execute('''INSERT INTO donors(article,brand,source,name,category,tnved,applicability,warranty,country,
            weight,length,width,height,oe_numbers,barcode,image_url,multiplicity) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(article,brand,source) DO UPDATE SET
              name=CASE WHEN excluded.name<>'' THEN excluded.name ELSE donors.name END,
              category=CASE WHEN excluded.category<>'' THEN excluded.category ELSE donors.category END,
              tnved=CASE WHEN excluded.tnved<>'' THEN excluded.tnved ELSE donors.tnved END,
              applicability=CASE WHEN excluded.applicability<>'' THEN excluded.applicability ELSE donors.applicability END,
              warranty=CASE WHEN excluded.warranty<>'' THEN excluded.warranty ELSE donors.warranty END,
              country=CASE WHEN excluded.country<>'' THEN excluded.country ELSE donors.country END,
              weight=CASE WHEN excluded.weight>0 THEN excluded.weight ELSE donors.weight END,
              length=CASE WHEN excluded.length>0 THEN excluded.length ELSE donors.length END,
              width=CASE WHEN excluded.width>0 THEN excluded.width ELSE donors.width END,
              height=CASE WHEN excluded.height>0 THEN excluded.height ELSE donors.height END,
              oe_numbers=CASE WHEN excluded.oe_numbers<>'' THEN excluded.oe_numbers ELSE donors.oe_numbers END,
              barcode=CASE WHEN excluded.barcode<>'' THEN excluded.barcode ELSE donors.barcode END,
              image_url=CASE WHEN excluded.image_url<>'' THEN excluded.image_url ELSE donors.image_url END,
              multiplicity=CASE WHEN excluded.multiplicity>0 THEN excluded.multiplicity ELSE donors.multiplicity END''',
            (art, str(r.get('brand', '')).strip(), source, str(r.get('name', '')), str(r.get('category', '')),
             str(r.get('tnved', '')), str(r.get('applicability', '')), str(r.get('warranty', '')), str(r.get('country', '')),
             num(r.get('weight')), num(r.get('length')),
             num(r.get('width')), num(r.get('height')), str(r.get('oe_numbers', '')),
             str(r.get('barcode', '')), str(r.get('image_url', '')), num(r.get('multiplicity'))))
        n += 1
    conn.commit()
    return n

def _dims_of(r):
    return (num(r['length']), num(r['width']), num(r['height']), num(r['weight']))

def enrich_full(conn, cat_mode='artbrand', enrich_mode='auto'):
    """Полное обогащение по правилам приложения (HVC):
       - доноры: та же пара Артикул+Бренд (реестр donors) и транзитивная OE-группа;
       - категория/ТН ВЭД: по умолчанию только Артикул+Бренд (cat_mode='artbrand');
         по OE (cat_mode='oe') — только при единогласии доноров, конфликт = пропуск;
       - название/применимость: Артикул+Бренд, иначе самое частое в OE-группе;
       - габариты: цельный комплект той же пары, иначе меньший комплект OE-группы;
         совместимость с уже заполненными обязательна, заполняются только пустые;
       - аналоги: артикулы OE-группы (как enrich_oe). Заполненные поля не трогаем."""
    prods = [dict(r) for r in conn.execute(
        'SELECT article,brand,name,category,tnved,applicability,warranty,country,weight,length,width,height,oe_numbers,analog_list,group_articles,barcode,image_url,multiplicity FROM products')]
    donors = [dict(r) for r in conn.execute(
        'SELECT article,brand,name,category,tnved,applicability,warranty,country,weight,length,width,height,oe_numbers,barcode,image_url,multiplicity FROM donors')]
    # v12.9.145: ключи — как в браузере (normArticle): «F 100» и «F-100» одна пара.
    donors_by_key = {}
    for d in donors: donors_by_key.setdefault(_norm_pair(d['article'], d['brand']), []).append(d)
    # Карантин идентичностей (как HVC.identityUnsafe): один нормализованный ключ
    # у разных буквальных пар артикул+бренд — такие SKU не обогащаем и их OE не
    # даём связывать группы, иначе чужие данные протекут не в тот товар.
    _lit_by_norm = {}
    for r in prods: _lit_by_norm.setdefault(_norm_pair(r['article'], r['brand']), set()).add((r['article'], r['brand']))
    unsafe_norms = {k for k, v in _lit_by_norm.items() if len(v) > 1}
    quarantined = sum(1 for r in prods if _norm_pair(r['article'], r['brand']) in unsafe_norms)
    # OE-граф: продукты и доноры в одних группах (узел = ('p'|'d', article, brand, idx))
    nodes = [('p', i) for i in range(len(prods))] + [('d', i) for i in range(len(donors))]
    parent = {n: n for n in nodes}
    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: parent[rb] = ra
    oe_map = {}
    for kind, i in nodes:
        r = prods[i] if kind == 'p' else donors[i]
        if kind == 'p' and _norm_pair(r['article'], r['brand']) in unsafe_norms: continue
        for oe in _oe_codes(r['oe_numbers']): oe_map.setdefault(oe, []).append((kind, i))
    for lst in oe_map.values():
        for other in lst[1:]: union(lst[0], other)
    groups = {}
    for n in nodes: groups.setdefault(find(n), []).append(n)
    filled = {'name': 0, 'applicability': 0, 'category': 0, 'tnved': 0, 'warranty': 0, 'country': 0, 'dims': 0, 'analog_list': 0, 'group_articles': 0, 'barcode': 0, 'image_url': 0, 'multiplicity': 0}
    conflicts = {'category': 0, 'tnved': 0}
    def unanimous(values):
        vals = [str(v).strip() for v in values if str(v or '').strip()]
        uniq = set(vals)
        return (vals[0] if len(uniq) == 1 else None), len(uniq) > 1
    def frequent(values):
        vals = [str(v).strip() for v in values if str(v or '').strip()]
        return max(set(vals), key=vals.count) if vals else ''
    for members in groups.values():
        group_prods = [prods[i] for kind, i in members if kind == 'p']
        if not group_prods: continue
        group_donors = [donors[i] for kind, i in members if kind == 'd']
        for p in group_prods:
            if _norm_pair(p['article'], p['brand']) in unsafe_norms: continue  # карантин
            pair = donors_by_key.get(_norm_pair(p['article'], p['brand']), [])
            updates = {}
            if not str(p['name'] or '').strip():
                v = frequent([d['name'] for d in pair]) or frequent(
                    [d['name'] for d in group_donors] + [g['name'] for g in group_prods])
                if v: updates['name'] = v; filled['name'] += 1
            if not str(p['applicability'] or '').strip():
                v = frequent([d['applicability'] for d in pair]) or frequent(
                    [d['applicability'] for d in group_donors] + [g['applicability'] for g in group_prods])
                if v: updates['applicability'] = v; filled['applicability'] += 1
            for field in ('category', 'tnved'):
                _placeholders = {'без категории', 'разное', 'прочее', 'не определено'}
                _cur = str(p[field] or '').strip()
                if _cur and not (field == 'category' and _cur.lower() in _placeholders): continue
                _vals = [d[field] for d in pair if not (field == 'category' and str(d[field] or '').strip().lower() in _placeholders)]
                v, conf = unanimous(_vals)
                if conf: conflicts[field] += 1
                if not v and cat_mode in ('oe', 'auto'):
                    _pool = [d[field] for d in group_donors] + [g[field] for g in group_prods if g is not p]
                    if field == 'category': _pool = [x for x in _pool if str(x or '').strip().lower() not in _placeholders]
                    v, conf2 = unanimous(_pool)
                    if conf2: conflicts[field] += 1
                if v: updates[field] = v; filled[field] += 1
            # гарантия/страна: только точная пара справочника, единогласно (как ozonSourceAttributes)
            for field in ('warranty', 'country'):
                if str(p[field] or '').strip(): continue
                v, conf = unanimous([d[field] for d in pair])
                if v: updates[field] = v; filled[field] = filled.get(field, 0) + 1
            cur = _dims_of(p)
            if not all(v > 0 for v in cur):
                cands = []
                _oe_pool = (group_donors + group_prods) if enrich_mode in ('oe', 'auto') else []
                for d in pair + _oe_pool:
                    t = _dims_of(d)
                    if all(v > 0 for v in t): cands.append(t)
                # та же пара — приоритет; далее меньший комплект мерой браузера:
                # (объём л, наибольшая сторона, вес, сумма сторон)
                pair_cands = [_dims_of(d) for d in pair if all(v > 0 for v in _dims_of(d))]
                _measure = lambda t: (round(t[0] * t[1] * t[2] / 1000, 6), max(t[0], t[1], t[2]), t[3], t[0] + t[1] + t[2])
                pool = pair_cands + sorted(cands, key=_measure)
                for t in pool:
                    if all(not (c > 0) or c == tv for c, tv in zip(cur, t)):  # совместимость с заполненным
                        for i, f in enumerate(('length', 'width', 'height', 'weight')):
                            if not cur[i] > 0: updates[f] = t[i]
                        filled['dims'] += 1
                        break
            # штрихкод/фото/кратность — только та же пара донора (как HVC.enrichOne)
            if pair:
                if not str(p.get('barcode') or '').strip():
                    _bc = next((str(d['barcode']).strip() for d in pair if str(d.get('barcode') or '').strip()), '')
                    if _bc: updates['barcode'] = _bc; filled['barcode'] = filled.get('barcode', 0) + 1
                if not str(p.get('image_url') or '').strip():
                    _im = next((str(d['image_url']).strip() for d in pair if str(d.get('image_url') or '').strip()), '')
                    if _im: updates['image_url'] = _im; filled['image_url'] = filled.get('image_url', 0) + 1
                if not num(p.get('multiplicity')) > 0:
                    _mu = next((num(d['multiplicity']) for d in pair if num(d.get('multiplicity')) > 0), 0)
                    if _mu > 0: updates['multiplicity'] = _mu; filled['multiplicity'] = filled.get('multiplicity', 0) + 1
            others = sorted({g['article'] for g in group_prods if g['article'] != p['article']})
            if others:
                cur_set = {x.strip() for x in str(p['analog_list'] or '').split(',') if x.strip()}
                merged = sorted(cur_set | set(others))
                if merged != sorted(cur_set):
                    updates['analog_list'] = ', '.join(merged); filled['analog_list'] += 1
            if not str(p.get('group_articles') or '').strip():
                grp = sorted({g['article'] for g in group_prods if str(g['article'] or '').strip()})
                if len(grp) > 1:
                    updates['group_articles'] = ' / '.join(grp); filled['group_articles'] += 1
            if updates:
                sets = ', '.join(f'{k}=?' for k in updates)
                conn.execute(f'UPDATE products SET {sets} WHERE article=? AND brand=?',
                             (*updates.values(), p['article'], p['brand']))
    conn.commit()
    log_api(conn, 'enrichFull', 'sqlite', 'ok', f'cat_mode={cat_mode}, заполнено {filled}, конфликты {conflicts}')
    return {'cat_mode': cat_mode, 'filled': filled, 'conflicts': conflicts, 'donors': len(donors), 'quarantined': quarantined}

# ---------------- обобщённый разбор файлов (п.5 аудита, v12.9.111) ----------------
def _raw_table(filename, data):
    """Файл -> (заголовки, строки-списки) без привязки к каталогу.
       CSV — stdlib; XLSX — openpyxl, если есть; ZIP — первый файл внутри."""
    name = os.path.basename(str(filename or 'file'))
    if name.lower().endswith('.zip'):
        files = files_from_zip(data)
        if not files: raise RuntimeError('в ZIP нет CSV/XLSX')
        name, data = files[0]
    if name.lower().endswith('.xlsx'):
        # v12.9.147: как импорт каталога — openpyxl если есть, иначе stdlib
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            table = [list(r) for r in wb.active.iter_rows(values_only=True)]
        except ImportError:
            table = [list(r) for r in _xlsx_sheet_rows(data)]
    else:
        text = data.decode('utf-8-sig', errors='replace')
        if '\ufffd' in text[:400]:
            try: text = data.decode('cp1251')
            except Exception: pass
        first = text.split('\n', 1)[0]
        delim = ';' if first.count(';') >= first.count(',') and first.count(';') >= first.count('\t') else ('\t' if first.count('\t') > first.count(',') else ',')
        table = list(csv.reader(io.StringIO(text), delimiter=delim))
    table = [r for r in table if any(str(c).strip() for c in r if c is not None)]
    if not table: return [], []
    headers = [str(h).strip() if h is not None else '' for h in table[0]]
    return headers, table[1:]

def parse_file_bytes(conn, filename, data):
    """Разобрать файл в кэш парсинга: наружу — постранично через /parse/rows.
       Каталог не трогаем: это сырьё для импортов приложения (цены конкурентов,
       продажи, заказы, тарифы — у каждого свои правила применения)."""
    headers, table = _raw_table(filename, data)
    import uuid
    sid = uuid.uuid4().hex[:16]
    conn.execute('INSERT INTO parse_sessions(id,filename,headers,total,created) VALUES(?,?,?,?,datetime("now"))',
                 (sid, os.path.basename(str(filename or 'file')), json.dumps(headers, ensure_ascii=False), len(table)))
    conn.executemany('INSERT INTO parse_rows(session,idx,data) VALUES(?,?,?)',
                     [(sid, i, json.dumps({headers[j]: (r[j] if j < len(r) else '') for j in range(len(headers))},
                                           ensure_ascii=False, default=str)) for i, r in enumerate(table)])
    # держим только 5 последних разборов
    old = [r[0] for r in conn.execute('SELECT id FROM parse_sessions ORDER BY created DESC, rowid DESC LIMIT 100 OFFSET 5')]
    for o in old:
        conn.execute('DELETE FROM parse_sessions WHERE id=?', (o,))
        conn.execute('DELETE FROM parse_rows WHERE session=?', (o,))
    conn.commit()
    log_api(conn, 'parseFile', str(filename), 'ok', f'строк {len(table)}')
    return {'parse_id': sid, 'headers': headers, 'total': len(table)}

# ---------------- история цен и снапшоты (п.6 аудита, v12.9.112) ----------------
def price_changes(conn, days=30, limit=200):
    """Изменения цен за период: LAG по истории даёт предыдущую цену SKU."""
    days = max(1, min(3650, int(num(days) or 30)))
    rows = conn.execute('''SELECT article,brand,price,cost,ts,source,prev_price FROM (
            SELECT *, LAG(price) OVER (PARTITION BY article,brand ORDER BY ts,rowid) prev_price
            FROM price_history)
        WHERE ts >= datetime("now", ?) AND prev_price IS NOT NULL AND ABS(price-prev_price) > 1e-9
        ORDER BY ts DESC LIMIT ?''', (f'-{days} days', int(limit))).fetchall()
    agg = conn.execute('''SELECT COUNT(DISTINCT article || '|' || brand) sku,
            SUM(price > prev_price) rises, SUM(price < prev_price) falls FROM (
            SELECT *, LAG(price) OVER (PARTITION BY article,brand ORDER BY ts,rowid) prev_price
            FROM price_history)
        WHERE ts >= datetime("now", ?) AND prev_price IS NOT NULL AND ABS(price-prev_price) > 1e-9''',
        (f'-{days} days',)).fetchone()
    out = []
    for r in rows:
        d = dict(r)
        d['delta_pct'] = rnd((d['price'] - d['prev_price']) / d['prev_price'] * 100, 2) if d['prev_price'] else 0
        out.append(d)
    return {'days': days, 'changed_sku': agg[0] or 0, 'rises': agg[1] or 0, 'falls': agg[2] or 0, 'rows': out}

def make_snapshot(conn, note=''):
    total = conn.execute('SELECT COUNT(*) FROM products').fetchone()[0]
    cur = conn.execute('INSERT INTO snapshots(created,note,total) VALUES(datetime("now"),?,?)', (str(note)[:200], total))
    sid = cur.lastrowid
    conn.execute('INSERT INTO snapshot_rows(snapshot_id,article,brand,price,cost,stock) '
                 'SELECT ?,article,brand,price,cost,stock FROM products', (sid,))
    conn.commit()
    log_api(conn, 'snapshot', str(sid), 'ok', f'{total} SKU')
    return {'snapshot_id': sid, 'total': total}

def snapshot_diff(conn, id1, id2):
    q = lambda sql, args: conn.execute(sql, args).fetchall()
    added = q('SELECT a.article,a.brand,a.price FROM snapshot_rows a LEFT JOIN snapshot_rows b '
              'ON b.snapshot_id=? AND b.article=a.article AND b.brand=a.brand WHERE a.snapshot_id=? AND b.article IS NULL',
              (id1, id2))
    removed = q('SELECT a.article,a.brand,a.price FROM snapshot_rows a LEFT JOIN snapshot_rows b '
                'ON b.snapshot_id=? AND b.article=a.article AND b.brand=a.brand WHERE a.snapshot_id=? AND b.article IS NULL',
                (id2, id1))
    changed = q('SELECT a.article,a.brand,b.price old_price,a.price new_price FROM snapshot_rows a '
                'JOIN snapshot_rows b ON b.snapshot_id=? AND b.article=a.article AND b.brand=a.brand '
                'WHERE a.snapshot_id=? AND ABS(a.price-b.price) > 1e-9 ORDER BY ABS(a.price-b.price) DESC LIMIT 500',
                (id1, id2))
    return {'from': id1, 'to': id2, 'added': [dict(r) for r in added], 'removed': [dict(r) for r in removed],
            'price_changed': [dict(r) for r in changed]}

# ---------------- fuzzy-подсказки аналогов (п.7 аудита, v12.9.113) ----------------
def _norm_article(v):
    return re.sub(r'[^A-Z0-9А-ЯЁ]', '', str(v or '').upper())

def analog_suggestions(conn, limit=100):
    """ТОЛЬКО подсказки оператору (запрет авто-поиска аналогов v12.9.85 не тронут):
       ничего не записываем. Кандидаты для SKU без аналогов: тот же нормализованный
       артикул у другого бренда и похожие артикулы (опечатки, ratio>=0.86),
       блокирование по префиксу, пары с общим OE исключены (они уже связаны)."""
    import difflib
    prods = [dict(r) for r in conn.execute('SELECT article,brand,analog_list,oe_numbers FROM products')]
    oe_of = {}
    oe_pairs = set()
    by_oe = {}
    for p in prods:
        key = (p['article'], p['brand'])
        codes = set(_oe_codes(p['oe_numbers']))
        oe_of[key] = codes
        for oe in codes: by_oe.setdefault(oe, []).append(key)
    for keys in by_oe.values():
        for a in keys:
            for b in keys:
                if a != b: oe_pairs.add((a, b))
    blocks = {}
    for p in prods:
        n = _norm_article(p['article'])
        if len(n) >= 3: blocks.setdefault(n[:3], []).append(p)
    out = []
    seen = set()
    for lst in blocks.values():
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                a, b = lst[i], lst[j]
                ka, kb = (a['article'], a['brand']), (b['article'], b['brand'])
                na, nb = _norm_article(a['article']), _norm_article(b['article'])
                if abs(len(na) - len(nb)) > 2: continue
                if na == nb:
                    score, reason = 1.0, 'тот же артикул, другой бренд'
                else:
                    score = difflib.SequenceMatcher(None, na, nb).ratio()
                    if score < 0.86: continue
                    reason = 'похожий артикул (возможна опечатка)'
                for src, dst in ((a, b), (b, a)):
                    ks, kd = (src['article'], src['brand']), (dst['article'], dst['brand'])
                    if str(src['analog_list'] or '').strip(): continue       # аналоги уже есть
                    if (ks, kd) in oe_pairs or (ks, kd) in seen: continue    # уже связаны по OE
                    seen.add((ks, kd))
                    out.append({'article': src['article'], 'brand': src['brand'],
                                'candidate_article': dst['article'], 'candidate_brand': dst['brand'],
                                'score': rnd(score, 3), 'reason': reason})
    out.sort(key=lambda r: -r['score'])
    return {'suggestions': out[:int(limit)], 'total_found': len(out),
            'note': 'только подсказки оператору: аналоги автоматически не проставляются'}

# ---------------- очередь отправки на площадки ----------------
def enqueue(conn, kind, marketplace, items):
    n = 0
    for it in items:
        key = f"{kind}:{marketplace}:{it.get('article','')}:{it.get('idempotency','') or json.dumps(it, sort_keys=True, ensure_ascii=False)}"
        cur = conn.execute('''INSERT OR IGNORE INTO outbox(kind,marketplace,article,payload,idempotency_key,created_at)
                              VALUES(?,?,?,?,?,datetime("now"))''',
                           (kind, marketplace, it.get('article', ''), json.dumps(it, ensure_ascii=False), key))
        n += cur.rowcount
    conn.commit()
    return n

def _http_json(method, url, headers, payload, timeout=30):
    req = urlrequest.Request(url, method=method,
                             data=json.dumps(payload).encode('utf-8') if payload is not None else None,
                             headers={'Content-Type': 'application/json', **headers})
    with urlrequest.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode('utf-8') or '{}')

def process_outbox(limit=100):
    conn = db()
    sec = secrets()
    dry = str(get_settings(conn).get('dry_run', '1')) != '0'
    done, failed = 0, 0
    rows = conn.execute("SELECT * FROM outbox WHERE status IN ('pending','failed') AND attempts<5 ORDER BY id LIMIT ?", (limit,)).fetchall()
    for job in rows:
        payload = json.loads(job['payload'] or '{}')
        try:
            if dry:
                result = 'dry-run: запрос не отправлен (dry_run=1)'
            elif job['marketplace'] == 'OZON' and job['kind'] == 'prices':
                if not (sec.get('UC_OZON_CLIENT_ID') and sec.get('UC_OZON_API_KEY')):
                    raise RuntimeError('Нет ключей Ozon (UC_OZON_CLIENT_ID/UC_OZON_API_KEY)')
                status, resp = _http_json('POST', 'https://api-seller.ozon.ru/v1/product/import/prices',
                    {'Client-Id': sec['UC_OZON_CLIENT_ID'], 'Api-Key': sec['UC_OZON_API_KEY']},
                    {'prices': [{'offer_id': payload.get('article'), 'price': str(payload.get('price')),
                                 'old_price': str(payload.get('old_price', payload.get('price'))),
                                 'min_price': str(payload.get('min_price', payload.get('price')))}]})
                result = f'HTTP {status}'
            elif job['marketplace'] == 'OZON' and job['kind'] == 'stocks':
                if not (sec.get('UC_OZON_CLIENT_ID') and sec.get('UC_OZON_API_KEY')):
                    raise RuntimeError('Нет ключей Ozon')
                status, resp = _http_json('POST', 'https://api-seller.ozon.ru/v2/products/stocks',
                    {'Client-Id': sec['UC_OZON_CLIENT_ID'], 'Api-Key': sec['UC_OZON_API_KEY']},
                    {'stocks': [{'offer_id': payload.get('article'), 'stock': int(num(payload.get('stock'))),
                                 'warehouse_id': int(num(payload.get('warehouse_id')))}]})
                result = f'HTTP {status}'
            else:
                raise RuntimeError(f"Адаптер {job['marketplace']}/{job['kind']} ещё не реализован в движке")
            conn.execute("UPDATE outbox SET status='sent', attempts=attempts+1, sent_at=datetime('now'), last_error=? WHERE id=?",
                         (result, job['id']))
            done += 1
        except Exception as e:
            conn.execute("UPDATE outbox SET status='failed', attempts=attempts+1, last_error=? WHERE id=?",
                         (str(e)[:300], job['id']))
            failed += 1
        conn.commit()
    log_api(conn, 'processOutbox', 'local', 'ok', f'sent {done}, failed {failed}, dry={dry}')
    return {'sent': done, 'failed': failed, 'dry_run': dry}

# ---------------- папка входящих файлов + бэкапы + отчёт ----------------
def watch_folder_once(folder=None):
    folder = Path(folder or (DATA / 'inbox'))
    folder.mkdir(exist_ok=True)
    processed = folder / 'processed'; processed.mkdir(exist_ok=True)
    conn = db(); total = 0
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() not in ('.csv', '.xlsx', '.zip') or not f.is_file(): continue
        blob = f.read_bytes()
        files = files_from_zip(blob) if f.suffix.lower() == '.zip' else [(f.name, blob)]
        for name, data in files:
            rows = rows_from_xlsx_bytes(data) if name.lower().endswith('.xlsx') else rows_from_csv_bytes(data)
            total += import_rows(conn, rows, f'folder:{f.name}')
        dest = processed / f.name
        if dest.exists():  # B8: повторное имя не должно ронять перенос
            dest = processed / (f.stem + '-' + time.strftime('%Y%m%d-%H%M%S') + f.suffix)
        shutil.move(str(f), str(dest))
    if total: log_api(conn, 'watchFolder', str(folder), 'ok', f'строк {total}')
    return {'imported_rows': total}

def make_backup():
    dest_dir = DATA / 'backups'; dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / ('catalog-' + time.strftime('%Y%m%d-%H%M%S') + '.db')
    src = db(); dst = sqlite3.connect(dest)
    with dst: src.backup(dst)
    dst.close(); src.close()
    backups = sorted(dest_dir.glob('catalog-*.db'))
    for old in backups[:-14]: old.unlink(missing_ok=True)
    return {'backup': str(dest), 'kept': min(len(backups), 14)}

def summary_report(conn):
    agg = conn.execute('SELECT COUNT(*) n, ROUND(SUM(price*stock),2) stock_value FROM products').fetchone()
    outbox = conn.execute("SELECT status, COUNT(*) c FROM outbox GROUP BY status").fetchall()
    mail = conn.execute("SELECT COUNT(*) c FROM mail_log WHERE status='ok'").fetchone()
    return {'products': agg['n'], 'stock_value': agg['stock_value'],
            'outbox': {r['status']: r['c'] for r in outbox}, 'mail_imports_ok': mail['c']}

def dashboard_report(conn):
    """Сводка каталога одним SQL-проходом (аудит v12.9.107, п.3):
       агрегаты по eco_results и аномалии — вместо проходов по строкам вкладки."""
    base = conn.execute('SELECT COUNT(*) n, ROUND(SUM(price*stock),2) stock_value FROM products').fetchone()
    eco = conn.execute('SELECT COUNT(*) n, SUM(profit>0) profitable, ROUND(AVG(margin),2) avg_margin, '
                       'ROUND(SUM(profit),2) profit_units FROM eco_results').fetchone()
    an = conn.execute("SELECT SUM(price>0 AND cost>price) below_cost, SUM(length=0 OR width=0 OR height=0) no_dims, "
                      "SUM(oe_numbers='') no_oe, SUM(name='') no_name FROM products").fetchone()
    top = conn.execute('SELECT p.brand brand, ROUND(SUM(e.profit*p.sales),2) profit_month FROM eco_results e '
                       'JOIN products p ON p.article=e.article AND p.brand=e.brand '
                       'GROUP BY p.brand ORDER BY profit_month DESC LIMIT 5').fetchall()
    return {'products': base['n'], 'stock_value': base['stock_value'],
            'recalculated': eco['n'], 'profitable': eco['profitable'] or 0,
            'avg_margin': eco['avg_margin'], 'profit_units_sum': eco['profit_units'],
            'anomalies': {'below_cost': an['below_cost'] or 0, 'no_dims': an['no_dims'] or 0,
                          'no_oe': an['no_oe'] or 0, 'no_name': an['no_name'] or 0},
            'top_brands': [dict(r) for r in top]}

# ---------------- экспорт каталога (аудит v12.9.107, п.1; v12.9.108) ----------------
EXPORT_COLS = [('article','Артикул'),('brand','Бренд'),('name','Название'),('price','Цена'),('cost','Себестоимость'),
    ('stock','Остаток'),('sales','Продажи/мес'),('weight','Вес, кг'),('length','Длина, см'),('width','Ширина, см'),
    ('height','Высота, см'),('volume','Объём, л'),('oe_numbers','OE номера'),('analog_list','Аналоги'),
    ('total','Расходы всего'),('profit','Прибыль'),('margin','Маржа, %'),('roi','ROI, %'),
    ('break_even','Безубыток'),('target','Целевая цена')]
_EXPORT_SQL = ('SELECT p.article,p.brand,p.name,p.price,p.cost,p.stock,p.sales,p.weight,p.length,p.width,p.height,'
    'p.volume,p.oe_numbers,p.analog_list,e.total,e.profit,e.margin,e.roi,e.break_even,e.target '
    'FROM products p LEFT JOIN eco_results e ON e.article=p.article AND e.brand=p.brand ORDER BY p.article,p.brand')

def _filter_keys(rows, keys):
    if keys is None: return rows
    ks = {(str(a), str(b)) for a, b in keys}
    return [r for r in rows if (str(r['article'] or ''), str(r['brand'] or '')) in ks]

def export_catalog_csv_bytes(conn, enc='utf-8', keys=None):
    import csv as _csv
    buf = io.StringIO(); w = _csv.writer(buf, delimiter=';')
    w.writerow([h for _, h in EXPORT_COLS])
    for r in _filter_keys(conn.execute(_EXPORT_SQL).fetchall(), keys):
        w.writerow(['' if r[k] is None else r[k] for k, _ in EXPORT_COLS])
    text = buf.getvalue()
    if enc == 'cp1251': return text.encode('cp1251', errors='replace')
    return ('\ufeff' + text).encode('utf-8')

def _xml_esc(v):
    return (str(v).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))

def _xlsx_from_rows(headers, data_rows, sheet_name='Лист', header_rows=None, yellow=None):
    """Общий XLSX-писатель без openpyxl: zip из XML (stdlib).
       header_rows — служебные строки перед шапкой (официальный шаблон Ozon);
       yellow — множество (строка_данных_0based, колонка_0based) для жёлтой заливки."""
    import zipfile
    def col_letter(i):
        out = ''
        i += 1
        while i: i, rem = divmod(i - 1, 26); out = chr(65 + rem) + out
        return out
    rows_xml = []
    rn = 0
    for hrow in (header_rows or []):
        rn += 1
        cells = ''.join(f'<c r="{col_letter(i)}{rn}" t="inlineStr"><is><t>{_xml_esc(v)}</t></is></c>'
                        for i, v in enumerate(hrow) if v not in (None, ''))
        rows_xml.append(f'<row r="{rn}">{cells}</row>')
    rn += 1
    header = ''.join(f'<c r="{col_letter(i)}{rn}" t="inlineStr"><is><t>{_xml_esc(h)}</t></is></c>'
                     for i, h in enumerate(headers))
    rows_xml.append(f'<row r="{rn}">{header}</row>')
    yellow = yellow or set()
    for di, row in enumerate(data_rows):
        rn += 1
        cells = []
        for i, v in enumerate(row):
            if v is None or v == '': continue
            ref = f'{col_letter(i)}{rn}'
            st = ' s="1"' if (di, i) in yellow else ''
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cells.append(f'<c r="{ref}"{st}><v>{v}</v></c>')
            else:
                cells.append(f'<c r="{ref}"{st} t="inlineStr"><is><t>{_xml_esc(v)}</t></is></c>')
        rows_xml.append(f'<row r="{rn}">{"".join(cells)}</row>')
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             f'<sheetData>{"".join(rows_xml)}</sheetData></worksheet>')
    sheet_title = _xml_esc(str(sheet_name)[:31] or 'Лист')
    parts = {
        '[Content_Types].xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        'xl/styles.xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fills count="3"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FFFFFF99"/></patternFill></fill></fills>'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<borders count="1"><border/></borders>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
            '<xf numFmtId="0" fontId="0" fillId="2" borderId="0" applyFill="1"/></cellXfs></styleSheet>',
        '_rels/.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets><sheet name="{sheet_title}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        'xl/worksheets/sheet1.xml': sheet}
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, content in parts.items(): z.writestr(name, content)
    return out.getvalue()

def export_catalog_xlsx_bytes(conn, keys=None):
    rows = _filter_keys(conn.execute(_EXPORT_SQL).fetchall(), keys)
    return _xlsx_from_rows([h for _, h in EXPORT_COLS],
                           [[r[k] for k, _ in EXPORT_COLS] for r in rows], 'Каталог')

# ---------------- выгрузка Ozon, 46 колонок (этап 1, v12.9.115) ----------------
OZON_HEADERS = ['№','Артикул*','Название товара','Предельная цена без акций, руб.*','Зачёркнутая цена, руб.',
  'НДС, %*','Рассрочка','Ускоренный сбор отзывов','Сбор первых отзывов','SKU','Штрихкод (Серийный номер / EAN)',
  'ТН ВЭД коды ЕАЭС*','Вес в упаковке, г*','Ширина упаковки, мм*','Высота упаковки, мм*','Длина упаковки, мм*',
  'Ссылка на главное фото*','Ссылки на дополнительные фото','Артикул фото','Бренд*','Партномер (артикул производителя)',
  'Тип*','Название модели (для объединения в одну карточку)*','Нужен код маркировки*','Количество в упаковке, шт',
  'Вес товара, г','Класс опасности товара','Количество товара в УЕИ','Минимальное количество оптом','#Хештеги',
  'Аннотация','Rich-контент JSON','Объединить в похожие товары','OEM-номер','Альтернативные артикулы товара',
  'Количество, штук','Внутренний диаметр, мм','Материал','Вид техники','Цвет товара','Гарантия',
  'Страна-изготовитель','Комплектация','Количество заводских упаковок','Ошибка','Недочёты']

def _split_codes(raw):
    return [x for x in (p.strip() for p in re.split(r'[,;/|]+', str(raw or ''))) if x]

_ASSET_CACHE = {}
def _asset(name):
    if name not in _ASSET_CACHE:
        import json as _json
        data = None
        for base in (Path(__file__).resolve().parent, BUNDLE, DATA):
            try:
                fp = base / name
                if fp.exists(): data = _json.loads(fp.read_text(encoding='utf-8')); break
            except Exception: pass
        _ASSET_CACHE[name] = data
    return _ASSET_CACHE[name]

def ozon_template_rows():
    t = _asset('ozon_template.json')
    return t if isinstance(t, list) and len(t) == 4 else None

def _std_norm(v):
    return re.sub(r'\s+', ' ', re.sub(r'[()\[\]\-_,.\xab\xbb/\\]', ' ', str(v or '').lower())).strip()

_STD_INDEX = None
def _std_match(p):
    """Стандартные ОВХ: только ТОЧНОЕ совпадение нормализованного названия
       (категория, затем название) со словарём приложения, одна подпись
       значений. Fuzzy/contains из StdDims.match(review) не портируем."""
    global _STD_INDEX
    dims = _asset('std_dims.json')
    if not dims: return None
    if _STD_INDEX is None:
        _STD_INDEX = {}
        for d in dims:
            _STD_INDEX.setdefault(_std_norm(d.get('c')), []).append(d)
    for cand in (p.get('category'), p.get('name')):
        hits = _STD_INDEX.get(_std_norm(cand)) if _std_norm(cand) else None
        if not hits: continue
        sigs = {(num(h.get('l')), num(h.get('w')), num(h.get('h')), num(h.get('wt'))) for h in hits}
        if len(sigs) == 1:
            l, w, h, wt = next(iter(sigs))
            return {'length': l, 'width': w, 'height': h, 'weight': wt, 'source': hits[0].get('c', '')}
    return None

def import_ozon_pairs(conn, pairs):
    conn.execute('''CREATE TABLE IF NOT EXISTS ozon_pairs(category TEXT NOT NULL, type TEXT NOT NULL,
      PRIMARY KEY(category, type))''')
    n = 0
    for pr in pairs or []:
        cat = str(pr.get('category') or pr.get('cat') or '').strip()
        typ = str(pr.get('type') or pr.get('name') or '').strip()
        if cat and typ:
            conn.execute('INSERT OR IGNORE INTO ozon_pairs VALUES(?,?)', (cat, typ)); n += 1
    conn.commit()
    return {'ok': True, 'imported': n,
            'total': conn.execute('SELECT COUNT(*) FROM ozon_pairs').fetchone()[0]}

def _pairs_map(conn):
    try: rows = conn.execute('SELECT category,type FROM ozon_pairs').fetchall()
    except Exception: return {}
    out = {}
    for cat, typ in rows: out.setdefault(cat, []).append(typ)
    return out

def ozon_row(p, idx, vat='Не облагается', discount_pct=0, vehicle_type='Легковые автомобили'):
    return ozon_row_meta(p, idx, vat, discount_pct, vehicle_type)[0]

def ozon_row_meta(p, idx, vat='Не облагается', discount_pct=0, vehicle_type='Легковые автомобили',
                  pairs=None, chz_codes=None):
    """Строка шаблона Ozon из полей карточки. Правила приложения, которые
       портированы 1-в-1: цена не выдумывается (нет цены — пустая ячейка);
       зачёркнутая — только явная старая цена выше цены или выбранная
       продавцом надбавка; габариты сортируются длина>=ширина>=высота;
       вес в граммы, размеры в миллиметры; аннотация — описание или
       шаблон «Название. Артикул детали: … Производитель: …»."""
    art = str(p.get('article', '')).strip()
    name = str(p.get('name', '')).strip()
    brand = str(p.get('brand', '')).strip()
    price = num(p.get('price'))
    price_out = int(round(price)) if price > 0 else ''
    old = num(p.get('old_price'))
    if old > price and price > 0: old_out = int(round(old))
    elif discount_pct > 0 and price > 0: old_out = int(round(price * (1 + discount_pct / 100)))
    else: old_out = ''
    std_fields = []
    p = dict(p)
    if not all(num(p.get(k)) > 0 for k in ('length', 'width', 'height', 'weight')):
        std = _std_match(p)
        if std:
            key = {'length': 'length', 'width': 'width', 'height': 'height', 'weight': 'weight'}
            for k in ('length', 'width', 'height', 'weight'):
                if not num(p.get(k)) > 0 and std[key[k]] > 0:
                    p[k] = std[key[k]]; std_fields.append(k)
    ozon_type = str(p.get('ozon_type', '')).strip()
    ozon_cat = str(p.get('ozon_category', '')).strip()
    pair_bad = False
    if pairs:
        if not ozon_type and ozon_cat and len(pairs.get(ozon_cat, [])) == 1:
            ozon_type = pairs[ozon_cat][0]
        if ozon_type and not ozon_cat:
            cats = [c for c, ts in pairs.items() if ozon_type in ts]
            if len(cats) == 1: ozon_cat = cats[0]
        pair_bad = bool(ozon_type and ozon_cat and ozon_type not in pairs.get(ozon_cat, []))
    mark = str(p.get('mark_required', ''))
    tnved_digits = re.sub(r'\D', '', str(p.get('tnved', '')))
    chz_hit = bool(chz_codes) and any(tnved_digits.startswith(re.sub(r'\D', '', str(c))) for c in chz_codes if str(c).strip())
    if chz_hit and not mark: mark = 'Да'
    def grams(v): return int(round(num(v) * 1000)) if num(v) > 0 and round(num(v) * 1000) > 0 else ''
    def millis(v): return int(round(num(v) * 10)) if num(v) > 0 and round(num(v) * 10) > 0 else ''
    dims = [millis(p.get('length')), millis(p.get('width')), millis(p.get('height'))]
    if all(isinstance(d, int) for d in dims):
        dims.sort(reverse=True)  # длина — наибольшее, высота — наименьшее (документация Ozon)
        length_mm, width_mm, height_mm = dims
    else:
        width_mm, height_mm, length_mm = dims[1], dims[2], dims[0]
    oem = '; '.join(_split_codes(p.get('oe_numbers')))
    cross = '; '.join(c for c in _split_codes(p.get('cross_numbers') or p.get('group_articles'))
                      if c != art and c != oem)
    bnorm = _norm_article(brand).lower()
    hashtags = ('#автозапчасти #запчасти' + (' #' + bnorm if bnorm else '')).strip()
    annotation = (str(p.get('description', '')).strip() or f'{name}. Артикул детали: {art}. Производитель: {brand}.')[:6000]
    model = str(p.get('group_articles') or p.get('model') or art)
    errors, notes = [], []
    if not brand: errors.append('не заполнен бренд')
    if not ozon_type: errors.append('не определён тип Ozon')
    if pair_bad: errors.append('пара «категория/тип» не найдена в справочнике Ozon')
    if std_fields: notes.append('СТАНДАРТ (не измерено): ОВХ из справочника — ' + ', '.join(std_fields))
    if chz_hit: notes.append('ЧЗ по списку ТН ВЭД')
    if not name: errors.append('не заполнено название товара')
    _tnv = str(p.get('tnved', '')).strip()
    if not _tnv: notes.append('нет кода ТН ВЭД (Ozon требует для автозапчастей)')
    elif len(re.sub(r'\D', '', _tnv)) != 10: errors.append('ТН ВЭД должен быть 10 цифр')
    if not grams(p.get('weight')) or not all(isinstance(d, int) for d in (width_mm, height_mm, length_mm)):
        errors.append('не заполнены ОВХ (вес/габариты)')
    if not str(p.get('image_url', '')).strip(): notes.append('нет ссылки на главное фото — товар загрузится, но не выйдет в продажу, пока фото не добавят')
    if not str(p.get('barcode', '')).strip(): notes.append('нет штрихкода — Ozon не сможет принять поставку без него')
    if not price_out: errors.append('не заполнена цена')
    row = [idx, art, name, price_out, old_out, vat, '', '', '', str(p.get('ozon_sku', '')),
            str(p.get('barcode', '')), str(p.get('tnved', '')), grams(p.get('weight')), width_mm, height_mm, length_mm,
            str(p.get('image_url', '')), str(p.get('extra_photos', '')), '', brand,
            str(p.get('original_article', '')).strip() or art,
            ozon_type, model, mark,
            max(1, int(round(num(p.get('multiplicity')) or 1))),
            (round(num(p.get('net_weight')) * 1000, 6) if num(p.get('net_weight')) > 0 else ''),
            str(p.get('hazard_class', '')), '', '', hashtags, annotation,
            str(p.get('rich_content', ''))[:32767], str(p.get('group_articles', '')), oem, cross, '1',
            str(p.get('diameter', '')), str(p.get('material', '')), vehicle_type, str(p.get('color', '')),
            str(p.get('warranty', '')), str(p.get('country', '')),
            str(p.get('package_contents', '')).strip() or f'{name} - 1 шт., упаковка', '1',
            '; '.join(errors), '; '.join(notes)]
    cols = {'weight': 12, 'width': 13, 'height': 14, 'length': 15}
    return row, {cols[k] for k in std_fields}

def _ozon_rows_data(conn, keys=None, discount_pct=0, vat='Не облагается', chz_codes=None):
    pairs = _pairs_map(conn) or None
    rows = conn.execute('SELECT * FROM products ORDER BY article,brand').fetchall()
    out, yellow = [], set()
    for r in rows:
        d = dict(r)
        if keys is not None and (d['article'], d['brand']) not in keys: continue
        row, std_cols = ozon_row_meta(d, len(out) + 1, vat=vat, discount_pct=discount_pct,
                                      pairs=pairs, chz_codes=chz_codes)
        for c in std_cols: yellow.add((len(out), c))
        out.append(row)
    return out, yellow

def export_ozon_csv_bytes(conn, discount_pct=0, vat='Не облагается', enc='utf-8', keys=None, chz_codes=None):
    import csv as _csv
    buf = io.StringIO(); w = _csv.writer(buf, delimiter=';')
    w.writerow(OZON_HEADERS)
    for row in _ozon_rows_data(conn, keys, discount_pct, vat, chz_codes)[0]:
        w.writerow(row)
    text = buf.getvalue()
    if enc == 'cp1251': return text.encode('cp1251', errors='replace')
    return ('\ufeff' + text).encode('utf-8')

def export_ozon_xlsx_bytes(conn, discount_pct=0, vat='Не облагается', keys=None, chz_codes=None):
    rows, yellow = _ozon_rows_data(conn, keys, discount_pct, vat, chz_codes)
    tpl = ozon_template_rows()
    if tpl:
        return _xlsx_from_rows(tpl[1], rows, 'Ozon', header_rows=[tpl[0], tpl[2], tpl[3]], yellow=yellow)
    return _xlsx_from_rows(OZON_HEADERS, rows, 'Ozon', yellow=yellow)

# ---------------- HTTP ----------------
def _app_html_path():
    for cand in (BASE.parent / 'index.html', BUNDLE / 'index.html',
                 Path(sys.executable).resolve().parent / 'index.html', Path.cwd() / 'index.html'):
        if cand.exists(): return cand
    return None

_XLSX_JS = None

def _extract_xlsx(html):
    """v12.9.128: SheetJS выносится из inline-блока во внешний /lib/xlsx.js.
       У пользователя inline-блок не исполнялся (код текстом + Invalid or
       unexpected token) при байт-в-байт исправном файле — виновато
       взаимодействие библиотеки с HTML-парсером script-данных. Внешний
       скрипт HTML-парсер не трогает вовсе. На диске index.html прежний:
       открытие файлом работает как раньше."""
    global _XLSX_JS
    start = html.find('<script>/*! xlsx встроен офлайн')
    if start < 0: return html
    end = html.find('</script>', start)
    if end < 0: return html
    js = html[html.find('\n', start):end]
    if 'xlsx.js' not in js: return html
    _XLSX_JS = js.encode('utf-8')
    return html[:start] + '<script src="/lib/xlsx.js"></script>' + html[end + len('</script>'):]

_APP_HTML_CACHE = {'key': None, 'body': None}
def render_app_html():
    """Приложение с авто-токеном: страница отдана самим движком с его же адреса,
       поэтому токен можно вшить в HTML — пользователю не нужно ничего вставлять.
       Чужой сайт прочитать эту страницу не может (нет CORS-заголовка на /)."""
    app_file = _app_html_path()
    if app_file is None: return None
    try: key = (str(app_file), app_file.stat().st_mtime_ns, app_file.stat().st_size)
    except OSError: key = None
    if key and _APP_HTML_CACHE['key'] == key: return _APP_HTML_CACHE['body']
    html = app_file.read_text(encoding='utf-8')
    html = _extract_xlsx(html)
    inject = '<script>window.__UC_PY_TOKEN__=' + json.dumps(get_token()) + ';</script>'
    if '</head>' in html: html = html.replace('</head>', inject + '</head>', 1)
    else: html = inject + html
    body = html.encode('utf-8')
    if key: _APP_HTML_CACHE.update(key=key, body=body)
    return body

_TOKEN_CACHE = None
def get_token():
    global _TOKEN_CACHE
    if _TOKEN_CACHE: return _TOKEN_CACHE
    if not TOKEN_PATH.exists():
        TOKEN_PATH.write_text(os.urandom(18).hex(), encoding='utf-8')
    _TOKEN_CACHE = TOKEN_PATH.read_text(encoding='utf-8').strip()
    return _TOKEN_CACHE

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _host_ok(self):
        # A1 (аудит v12.9.133): без проверки Host вредоносный сайт через
        # DNS-rebinding читает страницу с вшитым токеном. Принимаем только
        # локальные имена; порт не сверяем — движок может быть на другом.
        h = (self.headers.get('Host', '') or '').strip().lower()
        host = h.rsplit(':', 1)[0] if ':' in h else h
        return host in ('127.0.0.1', 'localhost', '[::1]', '::1')
    def _send_disk_full(self):
        # «database or disk is full» пользователю ни о чём не говорит — объясняем
        import shutil as _sh
        try: free_mb = round(_sh.disk_usage(str(DATA)).free / 1048576)
        except Exception: free_mb = None
        try: db_mb = round(DB_PATH.stat().st_size / 1048576, 1) if DB_PATH.exists() else 0
        except Exception: db_mb = 0
        return self._send(507, {'ok': False, 'error':
            'Не хватает места на диске для базы движка (свободно ' + str(free_mb) + ' МБ, база каталога ' + str(db_mb) +
            ' МБ в папке engine_data рядом с движком). Освободите место на этом диске (минимум 1–2 ГБ: Очистка диска, Корзина), '
            'перезапустите движок и повторите. Каталог в приложении при этом не пострадал.'})
    def _deny_bad_host(self):
        if self._host_ok(): return False
        self._send(403, {'ok': False, 'error': 'Host не разрешён'})
        return True
    def _send_bytes(self, code, body, content_type, filename):
        # gzip только для текстовых типов: CSV/JSON/XML сжимаются кратно;
        # XLSX уже zip — повторное сжатие бесполезно.
        extra = {}
        if content_type.startswith('text/') or 'json' in content_type:
            body, extra = self._maybe_gzip(body)
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-UC-Token')
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        for k, v in extra.items(): self.send_header(k, v)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def _maybe_gzip(self, body):
        if len(body) < 1024 or 'gzip' not in (self.headers.get('Accept-Encoding', '') or ''): return body, {}
        import gzip as _gz
        return _gz.compress(body, compresslevel=6), {'Content-Encoding': 'gzip'}
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        body, extra = self._maybe_gzip(body)
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-UC-Token')
        for k, v in extra.items(): self.send_header(k, v)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def do_OPTIONS(self):
        if self._deny_bad_host(): return
        self._send(200, {'ok': True})
    def _auth(self):
        import hmac as _hmac
        return _hmac.compare_digest(self.headers.get('X-UC-Token', ''), get_token())
    def _body(self):
        ln = int(self.headers.get('Content-Length', 0) or 0)
        if ln > 50 * 1024 * 1024:  # A5: потолок JSON-тела
            raise ValueError('тело запроса больше 50 МБ')
        raw = self.rfile.read(ln) if ln else b'{}'
        try: return json.loads(raw.decode('utf-8') or '{}')
        except Exception: return {}
    def do_GET(self):
        if self._deny_bad_host(): return
        if self.path in ('/', '/index.html', '/app'):
            # одно окно: приложение отдаёт сам движок с того же адреса
            body = render_app_html()
            if body is not None:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                # v12.9.123: страницу приложения нельзя кэшировать — иначе после
                # обновления файлов браузер показывает старую копию (был случай:
                # баннер «SheetJS не загрузился» на уже исправленной версии).
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
                return
            return self._send(404, {'ok': False, 'error': 'index.html не найден рядом с движком'})
        if self.path == '/lib/xlsx.js':
            if _XLSX_JS is None:
                render_app_html()
            if _XLSX_JS is None: return self._send(404, {'ok': False, 'error': 'xlsx не найден в index.html'})
            self.send_response(200)
            self.send_header('Content-Type', 'application/javascript; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(_XLSX_JS)))
            self.end_headers(); self.wfile.write(_XLSX_JS)
            return
        if self.path == '/health':
            return self._send(200, {'ok': True, 'service': 'UC-PyEngine', 'version': VERSION})
        if self.path == '/diag':
            # v12.9.126: диагностика «что движок реально отдаёт» — для случаев,
            # когда у пользователя страница выглядит не так, как в репозитории.
            import hashlib
            info = {'engine_version': VERSION, 'frozen': bool(FROZEN)}
            ap = _app_html_path()
            info['app_path'] = str(ap) if ap else None
            try:
                import shutil as _sh
                info['disk_free_mb'] = round(_sh.disk_usage(str(DATA)).free / 1048576)
            except Exception: pass
            try: info['db_size_mb'] = round(DB_PATH.stat().st_size / 1048576, 1) if DB_PATH.exists() else 0
            except Exception: pass
            if ap:
                raw = ap.read_bytes()
                info['app_size'] = len(raw)
                info['app_sha256'] = hashlib.sha256(raw).hexdigest()[:16]
                txt = raw.decode('utf-8', errors='replace')
                info['xlsx_executable_script'] = '<script>/*! xlsx' in txt
                info['xlsx_textplain_block'] = 'id="xlsx-lib"' in txt
                info['has_token_inject_point'] = '</head>' in txt
            return self._send(200, {'ok': True, **info})
        if not self._auth(): return self._send(401, {'ok': False, 'error': 'X-UC-Token'})
        conn = db()
        if self.path == '/secrets/status':
            return self._send(200, {'ok': True, 'keys': sorted(k for k in secrets() if k.startswith('UC_SET_'))})
        if self.path == '/secrets/values':
            # B6: значения отдаются только авторизованному локальному клиенту и
            # только в память вкладки — на диск браузера они больше не пишутся.
            vals = {k[len('UC_SET_'):]: v for k, v in secrets().items() if k.startswith('UC_SET_') and v}
            return self._send(200, {'ok': True, 'values': vals})
        if self.path == '/report/summary': return self._send(200, {'ok': True, **summary_report(conn)})
        if self.path == '/report/dashboard': return self._send(200, {'ok': True, **dashboard_report(conn)})
        if self.path.startswith('/analogs/suggestions'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            return self._send(200, {'ok': True, **analog_suggestions(conn, (qs.get('limit') or ['100'])[0])})
        if self.path.startswith('/report/price-changes'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            return self._send(200, {'ok': True, **price_changes(conn, (qs.get('days') or ['30'])[0])})
        if self.path.startswith('/snapshots/diff'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            return self._send(200, {'ok': True, **snapshot_diff(conn, int(num((qs.get('from') or ['0'])[0])), int(num((qs.get('to') or ['0'])[0])))})
        if self.path == '/snapshots':
            rows = conn.execute('SELECT id,created,note,total FROM snapshots ORDER BY id DESC LIMIT 50').fetchall()
            return self._send(200, {'ok': True, 'rows': [dict(r) for r in rows]})
        if self.path.startswith('/parse/rows'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            sid = (qs.get('parse_id') or [''])[0]
            off = int(num((qs.get('offset') or ['0'])[0])); lim = min(5000, int(num((qs.get('limit') or ['1000'])[0])) or 1000)
            rows = conn.execute('SELECT data FROM parse_rows WHERE session=? ORDER BY idx LIMIT ? OFFSET ?', (sid, lim, off)).fetchall()
            total = conn.execute('SELECT total FROM parse_sessions WHERE id=?', (sid,)).fetchone()
            if total is None: return self._send(404, {'ok': False, 'error': 'parse_id не найден'})
            return self._send(200, {'ok': True, 'total': total[0], 'rows': [json.loads(r[0]) for r in rows]})
        if self.path.startswith('/export/ozon.xlsx'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            chz = [x for x in (qs.get('chz') or [''])[0].split(',') if x.strip()] or None
            data = export_ozon_xlsx_bytes(conn,
                discount_pct=num((qs.get('discount_pct') or ['0'])[0]),
                vat=(qs.get('vat') or ['Не облагается'])[0], chz_codes=chz)
            return self._send_bytes(200, data,
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'UC_ozon_engine.xlsx')
        if self.path.startswith('/export/ozon.csv'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            chz = [x for x in (qs.get('chz') or [''])[0].split(',') if x.strip()] or None
            return self._send_bytes(200, export_ozon_csv_bytes(conn,
                discount_pct=num((qs.get('discount_pct') or ['0'])[0]),
                vat=(qs.get('vat') or ['Не облагается'])[0],
                enc=(qs.get('enc') or ['utf-8'])[0], chz_codes=chz),
                'text/csv; charset=utf-8', 'UC_ozon_engine.csv')
        if self.path.startswith('/export/catalog'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            enc = (qs.get('enc') or ['utf-8'])[0]
            if '.xlsx' in self.path or (qs.get('format') or [''])[0] == 'xlsx':
                return self._send_bytes(200, export_catalog_xlsx_bytes(conn),
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'UC_catalog_engine.xlsx')
            return self._send_bytes(200, export_catalog_csv_bytes(conn, enc),
                'text/csv; charset=' + ('windows-1251' if enc == 'cp1251' else 'utf-8'), 'UC_catalog_engine.csv')
        if self.path.startswith('/search'):
            from urllib.parse import urlparse, parse_qs
            q = (parse_qs(urlparse(self.path).query).get('q', [''])[0] or '').strip()
            rows = conn.execute('''SELECT p.article,p.brand,p.name,p.price,p.stock FROM products p
                WHERE p.rowid IN (SELECT rowid FROM products_fts WHERE products_fts MATCH ?) LIMIT 100''',
                ('"' + q.replace('"', '') + '"',)).fetchall() if q else []
            return self._send(200, {'ok': True, 'rows': [dict(r) for r in rows]})
        if self.path.startswith('/catalog/products'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            off = int(num((qs.get('offset') or ['0'])[0])); lim = min(5000, int(num((qs.get('limit') or ['1000'])[0])) or 1000)
            rows = conn.execute('SELECT article,brand,name,price,cost,stock,sales,weight,length,width,height,volume,oe_numbers,analog_list,category,tnved,applicability,warranty,country,group_articles,cross_numbers,barcode,category_type,ozon_category,ozon_type,description FROM products ORDER BY article,brand LIMIT ? OFFSET ?', (lim, off)).fetchall()
            total = conn.execute('SELECT COUNT(*) c FROM products').fetchone()['c']
            return self._send(200, {'ok': True, 'total': total, 'rows': [dict(r) for r in rows]})
        if self.path.startswith('/catalog/results'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            off = int(num((qs.get('offset') or ['0'])[0])); lim = min(5000, int(num((qs.get('limit') or ['1000'])[0])) or 1000)
            rows = conn.execute('SELECT article,brand,total,profit,margin,roi,break_even,target FROM eco_results ORDER BY article,brand LIMIT ? OFFSET ?', (lim, off)).fetchall()
            total = conn.execute('SELECT COUNT(*) c FROM eco_results').fetchone()['c']
            return self._send(200, {'ok': True, 'total': total, 'rows': [dict(r) for r in rows]})
        if self.path == '/outbox':
            rows = conn.execute('SELECT id,kind,marketplace,article,status,attempts,last_error,created_at,sent_at FROM outbox ORDER BY id DESC LIMIT 200').fetchall()
            return self._send(200, {'ok': True, 'rows': [dict(r) for r in rows]})
        return self._send(404, {'ok': False, 'error': 'not found'})
    def do_POST(self):
        if self._deny_bad_host(): return
        if not self._auth(): return self._send(401, {'ok': False, 'error': 'X-UC-Token'})
        if self.path == '/import/file':
            # бинарное тело НЕЛЬЗЯ читать через _body() (JSON): читаем один раз здесь
            from urllib.parse import unquote
            fname = unquote(self.headers.get('X-Filename', 'file.csv'))
            ln = int(self.headers.get('Content-Length', 0) or 0)
            if ln > 200 * 1024 * 1024:  # A5: потолок файла загрузки
                return self._send(413, {'ok': False, 'error': 'файл больше 200 МБ'})
            data = self.rfile.read(ln) if ln else b''
            try:
                return self._send(200, {'ok': True, **import_file_bytes(db(), fname, data, enrich_only=(self.headers.get('X-Import-Mode', '') == 'enrich'))})
            except Exception as e:
                # v12.9.144: этот путь раньше возвращал сырой 'database or disk is full'
                if isinstance(e, DiskFullError) or 'disk is full' in str(e) or 'database or disk' in str(e):
                    return self._send_disk_full()
                return self._send(500, {'ok': False, 'error': str(e)[:300]})
        if self.path == '/parse/file':
            from urllib.parse import unquote
            fname = unquote(self.headers.get('X-Filename', 'file.csv'))
            ln = int(self.headers.get('Content-Length', 0) or 0)
            if ln > 200 * 1024 * 1024:  # A5: потолок файла загрузки
                return self._send(413, {'ok': False, 'error': 'файл больше 200 МБ'})
            data = self.rfile.read(ln) if ln else b''
            try:
                return self._send(200, {'ok': True, **parse_file_bytes(db(), fname, data)})
            except Exception as e:
                if isinstance(e, DiskFullError) or 'disk is full' in str(e) or 'database or disk' in str(e):
                    return self._send_disk_full()
                return self._send(500, {'ok': False, 'error': str(e)[:300]})
        try:
            body = self._body()
        except ValueError as e:
            return self._send(413, {'ok': False, 'error': str(e)})
        conn = db()
        try:
            if self.path == '/calc/batch':
                st = body.get('settings') or {}
                results = [calc_row(r, st) for r in (body.get('rows') or [])[:5000]]
                return self._send(200, {'ok': True, 'results': results})
            if self.path == '/import/rows':
                n = import_rows(conn, body.get('rows') or [], body.get('source', 'app'),
                                rebuild_fts=body.get('final') is not False)
                return self._send(200, {'ok': True, 'imported': n})
            if self.path == '/catalog/enrich':
                return self._send(200, {'ok': True, **enrich_oe(conn)})
            if self.path == '/donors/import':
                n = import_donors(conn, body.get('rows') or [], body.get('source', 'app'))
                return self._send(200, {'ok': True, 'imported': n})
            if self.path == '/catalog/enrich-full':
                return self._send(200, {'ok': True, **enrich_full(conn, body.get('cat_mode') or 'artbrand', body.get('enrich_mode') or 'auto')})
            if self.path == '/catalog/recalc':
                return self._send(200, {'ok': True, **recalc_catalog(conn, body.get('settings') or {}, force=bool(body.get('force')))})
            if self.path.startswith('/catalog/results'):
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                off = int(num((qs.get('offset') or ['0'])[0])); lim = min(5000, int(num((qs.get('limit') or ['1000'])[0])) or 1000)
                rows = conn.execute('SELECT article,brand,total,profit,margin,roi,break_even,target FROM eco_results ORDER BY article,brand LIMIT ? OFFSET ?', (lim, off)).fetchall()
                total = conn.execute('SELECT COUNT(*) c FROM eco_results').fetchone()['c']
                return self._send(200, {'ok': True, 'total': total, 'rows': [dict(r) for r in rows]})
            if self.path == '/snapshots':
                return self._send(200, {'ok': True, **make_snapshot(conn, body.get('note', ''))})
            if self.path == '/ozon/pairs/import':
                return self._send(200, import_ozon_pairs(conn, body.get('pairs') or []))
            if self.path == '/export/ozon.csv':
                keys = None
                if body.get('articles') is not None:
                    keys = {(str(a.get('article', '')), str(a.get('brand', ''))) for a in body['articles']}
                return self._send_bytes(200, export_ozon_csv_bytes(conn,
                    discount_pct=num(body.get('discount_pct')), vat=body.get('vat') or 'Не облагается', keys=keys,
                    chz_codes=body.get('chz_codes')),
                    'text/csv; charset=utf-8', 'UC_ozon_engine.csv')
            if self.path == '/export/ozon.xlsx':
                keys = None
                if body.get('articles') is not None:
                    keys = {(str(a.get('article', '')), str(a.get('brand', ''))) for a in body['articles']}
                return self._send_bytes(200, export_ozon_xlsx_bytes(conn,
                    discount_pct=num(body.get('discount_pct')), vat=body.get('vat') or 'Не облагается', keys=keys,
                    chz_codes=body.get('chz_codes')),
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'UC_ozon_engine.xlsx')
            if self.path.startswith('/export/catalog'):
                keys = None
                if body.get('articles') is not None:
                    keys = [(str(a.get('article', '')), str(a.get('brand', ''))) for a in body['articles']]
                if '.xlsx' in self.path:
                    return self._send_bytes(200, export_catalog_xlsx_bytes(conn, keys=keys),
                        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'UC_catalog_engine.xlsx')
                return self._send_bytes(200, export_catalog_csv_bytes(conn, body.get('enc') or 'utf-8', keys=keys),
                    'text/csv; charset=utf-8', 'UC_catalog_engine.csv')
            if self.path == '/outbox':
                n = enqueue(conn, body.get('kind', ''), body.get('marketplace', ''), body.get('items') or [])
                return self._send(200, {'ok': True, 'queued': n})
            if self.path == '/outbox/process':
                return self._send(200, {'ok': True, **process_outbox(int(num(body.get('limit', 100))) or 100)})
            if self.path == '/mail/check':
                return self._send(200, {'ok': True, **mail_check_once(get_settings(conn))})
            if self.path == '/folder/check':
                return self._send(200, {'ok': True, **watch_folder_once(body.get('folder'))})
            if self.path == '/backup':
                return self._send(200, {'ok': True, **make_backup()})
            if self.path == '/settings':
                for sk, sv in (body.get('secrets') or {}).items():
                    save_secret(str(sk), str(sv))  # A3: на Windows уйдёт в DPAPI
                for k, v in (body.get('settings') or {}).items():
                    conn.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                                 (str(k), str(v)))
                conn.commit()
                return self._send(200, {'ok': True})
        except Exception as e:
            if isinstance(e, DiskFullError) or 'disk is full' in str(e) or 'database or disk' in str(e):
                return self._send_disk_full()
            return self._send(500, {'ok': False, 'error': str(e)[:300]})
        return self._send(404, {'ok': False, 'error': 'not found'})

def register_protocol():
    """v12.9.129: протокол unitcontrol:// в HKCU (Windows, без админа).
       Ссылка из HTML, открытого файлом, запускает движок одним кликом:
       браузер спросит разрешение один раз. Не Windows / не вышло — тихо."""
    if sys.platform != 'win32': return False
    try:
        import winreg
        if FROZEN: cmd = f'"{sys.executable}" serve'
        else: cmd = f'"{sys.executable}" "{BASE / "uc_engine.py"}" serve'
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\unitcontrol') as k:
            winreg.SetValueEx(k, '', 0, winreg.REG_SZ, 'URL:UNIT CONTROL')
            winreg.SetValueEx(k, 'URL Protocol', 0, winreg.REG_SZ, '')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\unitcontrol\shell\open\command') as k:
            winreg.SetValueEx(k, '', 0, winreg.REG_SZ, cmd)
        return True
    except Exception:
        return False

def serve(port=8765):
    get_token()
    register_protocol()
    try:
        srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    except OSError:
        # уже запущен (например, клик по unitcontrol:// при живом движке):
        # просто открыть браузер и выйти
        import webbrowser
        print('Движок уже запущен — открываю браузер.')
        if not os.environ.get('UC_NO_BROWSER'): webbrowser.open(f'http://127.0.0.1:{port}/')
        return
    url = f'http://127.0.0.1:{port}/'
    print(f'UC PyEngine {VERSION}: {url}  (токен: {TOKEN_PATH})')
    print('Приложение открыто в браузере. Не закрывайте это окно, пока работаете; закрыть окно = остановить движок.')
    if not os.environ.get('UC_NO_BROWSER'):
        import threading, webbrowser
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    srv.serve_forever()

def watch_loop():
    conn = db()
    print('Планировщик запущен: почта + папка inbox + очередь отправки. Ctrl+C — стоп.')
    while True:
        try:
            st = get_settings(conn)
            print(time.strftime('%H:%M:%S'), watch_folder_once())
            try: print(time.strftime('%H:%M:%S'), mail_check_once(st))
            except Exception as e: print('почта:', e)
            print(time.strftime('%H:%M:%S'), process_outbox())
            if time.localtime().tm_hour == 3 and time.localtime().tm_min < 5: print(make_backup())
        except Exception as e:
            print('watch error:', e)
        time.sleep(300)

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    if FROZEN and len(sys.argv) == 1: sys.argv.append('serve')  # двойной клик по exe
    ap.add_argument('cmd', choices=['serve', 'watch', 'mail', 'folder', 'outbox', 'backup', 'calc'])
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--once', action='store_true')
    args = ap.parse_args()
    try:
        import multiprocessing as _mp
        _mp.freeze_support()  # Windows spawn / PyInstaller: дочерние процессы не должны стартовать сервер
    except Exception: pass
    if args.cmd == 'serve': serve(args.port)
    elif args.cmd == 'watch': watch_loop()
    elif args.cmd == 'mail': print(mail_check_once(get_settings(db())))
    elif args.cmd == 'folder': print(watch_folder_once())
    elif args.cmd == 'outbox': print(process_outbox())
    elif args.cmd == 'backup': print(make_backup())
    elif args.cmd == 'calc':
        demo = {'article': 'DEMO-CLT-001', 'price': 18700, 'cost': 11200, 'sales': 10}
        st = {'commission_pct': 14, 'transfer_pct': 1.5, 'last_mile': 25, 'handover': 10,
              'pack': 18, 'transit': 30, 'returns_per_unit': 2.17, 'tax_regime': 'usn_income_6', 'tax_pct': 6}
        print(calc_row(demo, st))
