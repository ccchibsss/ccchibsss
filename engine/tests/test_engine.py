# -*- coding: utf-8 -*-
import csv, io, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import uc_engine as E

class TestCalc(unittest.TestCase):
    ST = {'commission_pct': 14, 'transfer_pct': 1.5, 'last_mile': 25, 'handover': 10,
          'pack': 18, 'transit': 30, 'returns_per_unit': 2.17,
          'tax_regime': 'usn_income_6', 'tax_pct': 6}
    def test_golden_12(self):
        path = os.path.join(os.path.dirname(__file__), '..', '..',
                            'UC_unit_economics_OZON_2026-11-06_filtered.csv')
        rows = list(csv.reader(open(path, encoding='utf-8-sig'), delimiter=';'))
        ix = {h: i for i, h in enumerate(rows[0])}
        for r in rows[1:]:
            got = E.calc_row({'article': r[0], 'price': E.num(r[ix['Цена, ₽/ед.']]),
                              'cost': E.num(r[ix['Себестоимость, ₽']]), 'sales': 10}, self.ST)
            self.assertAlmostEqual(got['total'], E.num(r[ix['Все затраты на 1 ед., ₽']]), delta=0.011, msg=r[0])
            self.assertAlmostEqual(got['profit'], E.num(r[ix['ЧП на 1 ед., ₽']]), delta=0.011, msg=r[0])
            self.assertAlmostEqual(got['margin'], E.num(r[ix['Маржа, %']]), delta=0.011, msg=r[0])
    def test_taxes(self):
        self.assertEqual(E.calc_tax(100000, 40000, 'usn_income_6'), 6000.0)
        self.assertEqual(E.calc_tax(100000, 40000, 'usn_income_vat_5'), 10476.19)
        self.assertEqual(E.calc_tax(1220, 610, 'osno_20', 6, 100), 235.0)
        self.assertEqual(E.calc_tax(1000, 400, 'custom_profit', 15), 90.0)
    def test_wb(self):
        self.assertEqual(E.wb_base_logistics(0.5), 29.0)
        self.assertEqual(E.wb_base_logistics(2), 60.0)
        self.assertAlmostEqual(E.wb_storage_month(1), 4.5)
        self.assertAlmostEqual(E.wb_storage_month(3), 8.7)
    def test_zero_sales_no_break_even(self):
        got = E.calc_row({'article': 'Z', 'price': 1000, 'cost': 500, 'sales': 0}, self.ST)
        self.assertEqual(got['break_even'], 0)

class TestData(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp)
        E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
    def test_csv_import_and_search(self):
        csv_text = 'Артикул;Бренд;Цена;Себестоимость\nA100;BOSCH;1000;600\n'
        rows = E.rows_from_csv_bytes(csv_text.encode('utf-8'))
        self.assertEqual(E.import_rows(self.conn, rows, 'test'), 1)
        # повторный импорт не плодит дубли (upsert по article+brand)
        E.import_rows(self.conn, rows, 'test')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM products').fetchone()[0], 1)
        found = self.conn.execute("SELECT rowid FROM products_fts WHERE products_fts MATCH 'A100'").fetchall()
        self.assertEqual(len(found), 1)
    def test_outbox_idempotent_dry_run(self):
        items = [{'article': 'A100', 'price': 1200, 'idempotency': 'x1'}]
        self.assertEqual(E.enqueue(self.conn, 'prices', 'OZON', items), 1)
        self.assertEqual(E.enqueue(self.conn, 'prices', 'OZON', items), 0)  # дубль отсечён
        res = E.process_outbox()
        self.assertEqual(res['sent'], 1)
        self.assertTrue(res['dry_run'])  # по умолчанию ничего реально не отправляется
    def test_zip_and_folder(self):
        buf = io.BytesIO()
        import zipfile
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('price.csv', 'Артикул;Цена\nB200;500\n')
        files = E.files_from_zip(buf.getvalue())
        self.assertEqual(files[0][0], 'price.csv')
        rows = E.rows_from_csv_bytes(files[0][1])
        self.assertEqual(rows[0]['article'], 'B200')

if __name__ == '__main__':
    unittest.main(verbosity=1)

class TestAppServing(unittest.TestCase):
    def test_token_injected_into_app(self):
        html = E.render_app_html()
        if html is None:
            self.skipTest('index.html не найден')
        self.assertIn(b'__UC_PY_TOKEN__', html)
        self.assertIn(b'</head>', html)


class TestRecalc(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp)
        E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
    def test_recalc_catalog(self):
        st = {'commission_pct': 14, 'transfer_pct': 1.5, 'last_mile': 25, 'handover': 10,
              'pack': 18, 'transit': 30, 'returns_per_unit': 2.17,
              'tax_regime': 'usn_income_6', 'tax_pct': 6}
        E.import_rows(self.conn, [
            {'article': 'DEMO-CLT-001', 'brand': 'X', 'price': 18700, 'cost': 11200, 'sales': 10},
            {'article': 'DEMO-FLT-001', 'brand': 'X', 'price': 890, 'cost': 410, 'sales': 10}], 'test')
        res = E.recalc_catalog(self.conn, st)
        self.assertEqual(res['recalculated'], 2)
        row = self.conn.execute("SELECT profit, break_even FROM eco_results WHERE article='DEMO-CLT-001'").fetchone()
        self.assertAlmostEqual(row[0], 3394.33, delta=0.011)
        self.assertEqual(row[1], 14377)

class TestDashboard(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp)
        E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
    def test_dashboard_report(self):
        E.import_rows(self.conn, [
            {'article': 'F100', 'brand': 'BOSCH', 'price': 700, 'cost': 900, 'stock': 2, 'oe_numbers': 'OE1'},
            {'article': 'F200', 'brand': 'MANN', 'price': 800, 'cost': 400, 'stock': 3}], 'test')
        d = E.dashboard_report(self.conn)
        self.assertEqual(d['products'], 2)
        self.assertEqual(d['stock_value'], 3800)
        self.assertEqual(d['anomalies']['below_cost'], 1)   # F100: себестоимость выше цены
        self.assertEqual(d['anomalies']['no_oe'], 1)        # F200 без OE

class TestImportEnrich(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp)
        E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
    def test_import_file_bytes(self):
        res = E.import_file_bytes(self.conn, 'price.csv',
            'Артикул;Бренд;Цена\nF100;BOSCH;700\n'.encode('utf-8'))
        self.assertEqual(res['imported'], 1)
    def test_http_import_file_no_hang(self):
        # регрессия v12.9.105: do_POST читал тело как JSON до обработчика файла -> зависание
        import pathlib, threading, urllib.request
        from http.server import ThreadingHTTPServer
        E.TOKEN_PATH = pathlib.Path(self.tmp) / 'token.txt'
        srv = ThreadingHTTPServer(('127.0.0.1', 0), E.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(
                f'http://127.0.0.1:{srv.server_address[1]}/import/file',
                data='Артикул;Бренд;Цена\nF100;BOSCH;700\n'.encode('utf-8'), method='POST',
                headers={'X-UC-Token': E.get_token(), 'X-Filename': 'price.csv',
                         'Content-Type': 'application/octet-stream'})
            import json as _json
            with urllib.request.urlopen(req, timeout=10) as r:
                self.assertEqual(_json.loads(r.read())['imported'], 1)
        finally:
            srv.shutdown()
    def test_import_csv_cp1251(self):
        # аудит v12.9.106: браузерный импорт умеет windows-1251 — движок обязан тоже
        res = E.import_file_bytes(self.conn, 'price.csv',
            'Артикул;Бренд;Цена\nF100;BOSCH;700\n'.encode('cp1251'))
        self.assertEqual(res['imported'], 1)
    def test_enrich_partial_dims_not_overwritten(self):
        # аудит v12.9.106: заполняются только пустые компоненты габаритов
        E.import_rows(self.conn, [
            {'article': 'F100', 'brand': 'BOSCH', 'price': 700, 'cost': 400,
             'weight': 0.3, 'length': 10, 'width': 6, 'height': 6, 'oe_numbers': 'OE1'},
            {'article': 'F200', 'brand': 'MANN', 'price': 800, 'cost': 450,
             'weight': 9.9, 'oe_numbers': 'OE1'}], 'test')  # вес свой, габаритов нет
        E.enrich_oe(self.conn)
        row = self.conn.execute("SELECT weight, length FROM products WHERE article='F200'").fetchone()
        self.assertEqual(row[0], 9.9)   # свой вес не перетёрт донором
        self.assertEqual(row[1], 10)    # пустая длина заполнена
    def test_enrich_transitive(self):
        E.import_rows(self.conn, [
            {'article': 'F100', 'brand': 'BOSCH', 'name': 'Фильтр', 'price': 700, 'cost': 400,
             'weight': 0.3, 'length': 10, 'width': 6, 'height': 6, 'oe_numbers': 'OE1'},
            {'article': 'F200', 'brand': 'MANN', 'name': '', 'price': 800, 'cost': 450, 'oe_numbers': 'OE1, OE2'},
            {'article': 'F300', 'brand': 'MAHLE', 'name': '', 'price': 900, 'cost': 500, 'oe_numbers': 'OE2'}], 'test')
        res = E.enrich_oe(self.conn)
        self.assertEqual(res['groups'], 1)  # F100-F200-F300 одна транзитивная группа
        row = self.conn.execute("SELECT name, analog_list FROM products WHERE article='F300'").fetchone()
        self.assertEqual(row[0], 'Фильтр')            # название подтянулось через цепочку OE
        self.assertIn('F100', row[1])                 # аналоги дописаны
        dims = self.conn.execute("SELECT length FROM products WHERE article='F200'").fetchone()
        self.assertEqual(dims[0], 10)                 # габариты заполнены от донора группы
