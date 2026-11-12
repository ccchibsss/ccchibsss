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
DATA = BASE / 'engine_data'
DATA.mkdir(exist_ok=True)
DB_PATH = DATA / 'catalog.db'
TOKEN_PATH = DATA / 'token.txt'
SECRETS_PATH = DATA / 'secrets.json'
VERSION = '12.9.106-pyengine-3'

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
                   num(st.get('processing', 0))]
    tax = calc_tax(price, sum(fixed_parts) + comm + transfer,
                   st.get('tax_regime', 'usn_income_6'), num(st.get('tax_pct', 6)),
                   num(st.get('tax_osno_share', 0)))
    total = rnd(sum(fixed_parts) + comm + transfer + tax)
    return {'total': total, 'commission': comm, 'transfer': transfer, 'tax': tax,
            'returns': rnd(returns), 'storage': storage}

def solve_prices(price, cost, st, target_margin=20.0, sales=1):
    """Целочисленный решатель: первое целое с прибылью >= 0 и >= целевой маржи.
       Как в приложении: при продажах 0 безубыток не выдумывается (0)."""
    if not (num(sales) > 0):
        return {'break_even': 0, 'target': 0}
    def profit(p):
        return rnd(p - ozon_unit(p, cost, st)['total'])
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
    L, W, H = num(row.get('length')), num(row.get('width')), num(row.get('height'))
    vol = num(row.get('volume')) or (L * W * H / 1000 if L and W and H else 0.0)
    st2 = dict(st); st2['_volume'] = vol
    u = ozon_unit(price, cost, st2)
    profit = rnd(price - u['total'])
    solved = solve_prices(price, cost, st2, num(st.get('target_margin', 20)), row.get('sales', 1))
    return {'article': row.get('article', ''), 'total': u['total'], 'profit': profit,
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
CREATE TABLE IF NOT EXISTS oe_links(oe TEXT NOT NULL, article TEXT NOT NULL, brand TEXT DEFAULT '',
  PRIMARY KEY(oe, article, brand));
CREATE INDEX IF NOT EXISTS ix_oe_links_article ON oe_links(article, brand);
CREATE TABLE IF NOT EXISTS eco_results(
  article TEXT NOT NULL, brand TEXT DEFAULT '', total REAL, profit REAL, margin REAL,
  roi REAL, break_even REAL, target REAL, computed_at TEXT DEFAULT '',
  PRIMARY KEY(article, brand));
CREATE TABLE IF NOT EXISTS api_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, action TEXT,
  endpoint TEXT, status TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS mail_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, subject TEXT,
  sender TEXT, filename TEXT, rows INTEGER, status TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(article, brand, name, oe_numbers, content='products', content_rowid='rowid');
'''
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn

def log_api(conn, action, endpoint, status, detail=''):
    conn.execute('INSERT INTO api_log(ts,action,endpoint,status,detail) VALUES(datetime("now"),?,?,?,?)',
                 (action, endpoint, status, str(detail)[:500]))
    conn.commit()

def get_settings(conn):
    return {r['key']: r['value'] for r in conn.execute('SELECT key,value FROM settings')}

def secrets():
    env = {k: os.environ.get(k) for k in
           ('UC_OZON_CLIENT_ID', 'UC_OZON_API_KEY', 'UC_WB_TOKEN', 'UC_MAIL_PASSWORD', 'UC_YM_TOKEN')}
    file_secrets = {}
    if SECRETS_PATH.exists():
        try: file_secrets = json.loads(SECRETS_PATH.read_text(encoding='utf-8'))
        except Exception: file_secrets = {}
    merged = dict(file_secrets)
    for k, v in env.items():
        if v: merged[k] = v
    return merged

# ---------------- импорт строк (CSV/XLSX/ZIP) ----------------
ALIASES = {
    'article': ('артикул', 'article', 'sku', 'код'), 'brand': ('бренд', 'brand', 'производитель'),
    'name': ('название', 'name', 'наименование'), 'price': ('цена', 'price'),
    'cost': ('себестоимость', 'cost', 'закупка'), 'stock': ('остаток', 'stock', 'количество'),
    'oe_numbers': ('oe', 'oem', 'ое', 'номер oe'), 'weight': ('вес', 'weight'),
    'length': ('длина', 'length'), 'width': ('ширина', 'width'), 'height': ('высота', 'height')}
def map_header(header):
    out = {}
    low = [str(h or '').strip().lower() for h in header]
    for field, names in ALIASES.items():
        for i, h in enumerate(low):
            if any(n in h for n in names): out[field] = i; break
    return out

def rows_from_csv_bytes(data):
    text = data.decode('utf-8-sig', errors='replace')
    if '\ufffd' in text[:400]:
        # как браузерный импорт: российские прайсы часто в windows-1251
        try: text = data.decode('cp1251')
        except Exception: pass
    delim = ';' if text.split('\n', 1)[0].count(';') >= text.split('\n', 1)[0].count(',') else ','
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows: return []
    mp = map_header(rows[0])
    if 'article' not in mp: return []
    out = []
    for r in rows[1:]:
        if not r or not str(r[mp['article']]).strip(): continue
        item = {}
        for f, i in mp.items():
            item[f] = r[i] if i < len(r) else ''
        out.append(item)
    return out

def rows_from_xlsx_bytes(data):
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError('openpyxl не установлен: pip install openpyxl (или присылайте CSV)')
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows: return []
    mp = map_header(rows[0])
    if 'article' not in mp: return []
    out = []
    for r in rows[1:]:
        if not r or r[mp['article']] in (None, ''): continue
        out.append({f: (r[i] if i < len(r) and r[i] is not None else '') for f, i in mp.items()})
    return out

def files_from_zip(data):
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if name.lower().endswith(('.csv', '.xlsx')):
                out.append((os.path.basename(name), z.read(name)))
    return out

def import_rows(conn, rows, source, rebuild_fts=True):
    n = 0
    for r in rows:
        art = str(r.get('article', '')).strip()
        if not art: continue
        conn.execute('''INSERT INTO products(article,brand,name,price,cost,stock,sales,weight,length,width,height,oe_numbers,source,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,datetime("now"))
            ON CONFLICT(article,brand) DO UPDATE SET
              name=COALESCE(NULLIF(excluded.name,''),products.name),
              price=CASE WHEN excluded.price>0 THEN excluded.price ELSE products.price END,
              cost=CASE WHEN excluded.cost>0 THEN excluded.cost ELSE products.cost END,
              stock=excluded.stock, sales=excluded.sales, weight=excluded.weight, length=excluded.length,
              width=excluded.width, height=excluded.height,
              oe_numbers=CASE WHEN excluded.oe_numbers<>'' THEN excluded.oe_numbers ELSE products.oe_numbers END,
              source=excluded.source, updated_at=datetime("now")''',
            (art, str(r.get('brand', '')).strip(), str(r.get('name', '')),
             num(r.get('price')), num(r.get('cost')), num(r.get('stock')), num(r.get('sales')), num(r.get('weight')),
             num(r.get('length')), num(r.get('width')), num(r.get('height')),
             str(r.get('oe_numbers', '')), source))
        n += 1
    if rebuild_fts:
        conn.execute("INSERT INTO products_fts(products_fts) VALUES('rebuild')")
    conn.commit()
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
def recalc_catalog(conn, st):
    """Экономика по ВСЕМ SKU каталога SQLite. Результат — в eco_results,
       наружу отдаётся постранично: браузеру не нужно держать расчёт у себя."""
    rows = conn.execute('SELECT article,brand,price,cost,sales,weight,length,width,height,volume FROM products').fetchall()
    conn.execute('DELETE FROM eco_results')
    n = profitable = 0
    total_profit = 0.0
    for r in rows:
        res = calc_row(dict(r), st)
        conn.execute('INSERT INTO eco_results(article,brand,total,profit,margin,roi,break_even,target,computed_at) VALUES(?,?,?,?,?,?,?,?,datetime("now"))',
                     (res['article'], r['brand'], res['total'], res['profit'], res['margin'], res['roi'], res['break_even'], res['target']))
        n += 1
        if res['profit'] > 0: profitable += 1
        total_profit += res['profit']
    conn.commit()
    log_api(conn, 'recalcCatalog', 'sqlite', 'ok', f'{n} SKU')
    return {'recalculated': n, 'profitable': profitable,
            'avg_profit': rnd(total_profit / n, 2) if n else 0}

# ---------------- импорт файла целиком + обогащение OE (v12.9.105) ----------------
def import_file_bytes(conn, filename, data):
    """Файл разбирает движок, а не браузер: CSV/XLSX/ZIP -> строки -> каталог."""
    name = os.path.basename(str(filename or 'file'))
    files = files_from_zip(data) if name.lower().endswith('.zip') else [(name, data)]
    total = 0
    for fname, blob in files:
        rows = rows_from_xlsx_bytes(blob) if fname.lower().endswith('.xlsx') else rows_from_csv_bytes(blob)
        total += import_rows(conn, rows, f'file:{name}', rebuild_fts=False)
    conn.execute("INSERT INTO products_fts(products_fts) VALUES('rebuild')")
    conn.commit()
    log_api(conn, 'importFile', name, 'ok', f'строк {total}')
    return {'file': name, 'imported': total}

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
        shutil.move(str(f), str(processed / f.name))
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

# ---------------- HTTP ----------------
def render_app_html():
    """Приложение с авто-токеном: страница отдана самим движком с его же адреса,
       поэтому токен можно вшить в HTML — пользователю не нужно ничего вставлять.
       Чужой сайт прочитать эту страницу не может (нет CORS-заголовка на /)."""
    app_file = BASE.parent / 'index.html'
    if not app_file.exists(): return None
    html = app_file.read_text(encoding='utf-8')
    inject = '<script>window.__UC_PY_TOKEN__=' + json.dumps(get_token()) + ';</script>'
    if '</head>' in html: html = html.replace('</head>', inject + '</head>', 1)
    else: html = inject + html
    return html.encode('utf-8')

def get_token():
    if not TOKEN_PATH.exists():
        TOKEN_PATH.write_text(os.urandom(18).hex(), encoding='utf-8')
    return TOKEN_PATH.read_text(encoding='utf-8').strip()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-UC-Token')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def do_OPTIONS(self): self._send(200, {'ok': True})
    def _auth(self):
        return self.headers.get('X-UC-Token', '') == get_token()
    def _body(self):
        ln = int(self.headers.get('Content-Length', 0) or 0)
        raw = self.rfile.read(ln) if ln else b'{}'
        try: return json.loads(raw.decode('utf-8') or '{}')
        except Exception: return {}
    def do_GET(self):
        if self.path in ('/', '/index.html', '/app'):
            # одно окно: приложение отдаёт сам движок с того же адреса
            body = render_app_html()
            if body is not None:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
                return
            return self._send(404, {'ok': False, 'error': 'index.html не найден рядом с движком'})
        if self.path == '/health':
            return self._send(200, {'ok': True, 'service': 'UC-PyEngine', 'version': VERSION})
        if not self._auth(): return self._send(401, {'ok': False, 'error': 'X-UC-Token'})
        conn = db()
        if self.path == '/report/summary': return self._send(200, {'ok': True, **summary_report(conn)})
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
            rows = conn.execute('SELECT article,brand,name,price,cost,stock,sales,weight,length,width,height,volume,oe_numbers,analog_list FROM products ORDER BY article,brand LIMIT ? OFFSET ?', (lim, off)).fetchall()
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
        if not self._auth(): return self._send(401, {'ok': False, 'error': 'X-UC-Token'})
        if self.path == '/import/file':
            # бинарное тело НЕЛЬЗЯ читать через _body() (JSON): читаем один раз здесь
            from urllib.parse import unquote
            fname = unquote(self.headers.get('X-Filename', 'file.csv'))
            ln = int(self.headers.get('Content-Length', 0) or 0)
            data = self.rfile.read(ln) if ln else b''
            try:
                return self._send(200, {'ok': True, **import_file_bytes(db(), fname, data)})
            except Exception as e:
                return self._send(500, {'ok': False, 'error': str(e)[:300]})
        body = self._body()
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
            if self.path == '/catalog/recalc':
                return self._send(200, {'ok': True, **recalc_catalog(conn, body.get('settings') or {})})
            if self.path.startswith('/catalog/results'):
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                off = int(num((qs.get('offset') or ['0'])[0])); lim = min(5000, int(num((qs.get('limit') or ['1000'])[0])) or 1000)
                rows = conn.execute('SELECT article,brand,total,profit,margin,roi,break_even,target FROM eco_results ORDER BY article,brand LIMIT ? OFFSET ?', (lim, off)).fetchall()
                total = conn.execute('SELECT COUNT(*) c FROM eco_results').fetchone()['c']
                return self._send(200, {'ok': True, 'total': total, 'rows': [dict(r) for r in rows]})
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
                for k, v in (body.get('settings') or {}).items():
                    conn.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                                 (str(k), str(v)))
                conn.commit()
                return self._send(200, {'ok': True})
        except Exception as e:
            return self._send(500, {'ok': False, 'error': str(e)[:300]})
        return self._send(404, {'ok': False, 'error': 'not found'})

def serve(port=8765):
    get_token()
    srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'UC PyEngine {VERSION}: http://127.0.0.1:{port}  (токен: {TOKEN_PATH})')
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
    ap.add_argument('cmd', choices=['serve', 'watch', 'mail', 'folder', 'outbox', 'backup', 'calc'])
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--once', action='store_true')
    args = ap.parse_args()
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
