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
