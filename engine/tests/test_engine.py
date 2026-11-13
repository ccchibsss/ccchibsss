# -*- coding: utf-8 -*-
import csv, io, os, sys, unittest, collections
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

class TestParallelRecalc(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp)
        E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
        self.st = {'commission_pct': 14, 'transfer_pct': 1.5, 'last_mile': 25, 'handover': 10,
                   'pack': 18, 'transit': 30, 'returns_per_unit': 2.17,
                   'tax_regime': 'usn_income_6', 'tax_pct': 6}
    def test_parallel_matches_sequential(self):
        rows = [{'article': f'A{i}', 'brand': 'B', 'price': 500 + (i % 5000),
                 'cost': 300 + (i % 3000), 'sales': i % 20} for i in range(2100)]
        E.import_rows(self.conn, rows, 'test')
        res = E.recalc_catalog(self.conn, self.st)
        self.assertEqual(res['recalculated'], 2100)
        # каждый результат параллельного пересчёта равен последовательному calc_row
        got = {(r[0], r[1]): r[2] for r in self.conn.execute('SELECT article,brand,profit FROM eco_results')}
        for row in rows[:50] + rows[-50:]:
            self.assertAlmostEqual(got[(row['article'], 'B')], E.calc_row(row, self.st)['profit'], delta=0.001)
    def test_no_parallel_env_fallback(self):
        import os
        os.environ['UC_ENGINE_NO_PARALLEL'] = '1'
        try:
            out, par = E._calc_all([{'article': 'X', 'price': 1000, 'cost': 500, 'sales': 1}] * 3, self.st)
            self.assertFalse(par)
            self.assertEqual(len(out), 3)
        finally:
            del os.environ['UC_ENGINE_NO_PARALLEL']

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

class TestExport(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp)
        E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
        E.import_rows(self.conn, [
            {'article': 'F100', 'brand': 'BOSCH', 'name': 'Фильтр & Co', 'price': 700, 'cost': 400, 'stock': 2}], 'test')
    def test_export_csv(self):
        data = E.export_catalog_csv_bytes(self.conn)
        self.assertTrue(data.startswith(b'\xef\xbb\xbf'))  # BOM для Excel
        text = data.decode('utf-8-sig')
        self.assertIn('Артикул;Бренд', text)
        self.assertIn('F100;BOSCH;Фильтр & Co;700', text)
        self.assertIn('F100;BOSCH', E.export_catalog_csv_bytes(self.conn, 'cp1251').decode('cp1251'))
    def test_export_xlsx_stdlib(self):
        import io as _io, zipfile
        data = E.export_catalog_xlsx_bytes(self.conn)
        z = zipfile.ZipFile(_io.BytesIO(data))  # валидный zip-контейнер XLSX
        self.assertIn('xl/worksheets/sheet1.xml', z.namelist())
        sheet = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
        self.assertIn('F100', sheet)
        self.assertIn('Фильтр &amp; Co', sheet)  # XML-экранирование
        self.assertIn('<v>700.0</v>', sheet)       # числа — числами, не строками

class TestEnrichFull(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp)
        E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
    def _prod(self, art):
        return self.conn.execute('SELECT name,category,tnved,applicability,length,weight FROM products WHERE article=?', (art,)).fetchone()
    def test_artbrand_donor_fills_and_conflict_skips(self):
        E.import_rows(self.conn, [{'article': 'F100', 'brand': 'BOSCH', 'price': 700, 'cost': 400, 'oe_numbers': 'OE1'}], 'test')
        E.import_donors(self.conn, [
            {'article': 'F100', 'brand': 'BOSCH', 'name': 'Фильтр масляный', 'category': 'Фильтры',
             'tnved': '8421230000', 'weight': 0.3, 'length': 10, 'width': 6, 'height': 6}], 'catalogV')
        E.import_donors(self.conn, [
            {'article': 'F100', 'brand': 'BOSCH', 'category': 'Двигатель'}], 'other')  # конфликт категории
        res = E.enrich_full(self.conn)
        row = self._prod('F100')
        self.assertEqual(row[0], 'Фильтр масляный')   # название от пары
        self.assertEqual(row[1], '')                   # категория: конфликт доноров — не берём
        self.assertEqual(row[2], '8421230000')         # ТН ВЭД от пары (конфликта нет)
        self.assertEqual(row[4], 10)                   # габариты цельным комплектом пары
        self.assertEqual(row[5], 0.3)
        self.assertEqual(res['conflicts']['category'], 1)
    def test_oe_category_only_in_oe_mode_and_unanimous(self):
        E.import_rows(self.conn, [
            {'article': 'F200', 'brand': 'MANN', 'price': 800, 'cost': 400, 'oe_numbers': 'OE9'},
            {'article': 'F300', 'brand': 'MAHLE', 'price': 900, 'cost': 500, 'oe_numbers': 'OE9', 'category': 'Фильтры'}], 'test')
        E.enrich_full(self.conn)  # artbrand по умолчанию: OE-категорию НЕ берём
        self.assertEqual(self._prod('F200')[1], '')
        E.enrich_full(self.conn, 'oe')  # oe-режим: доноры единогласны — берём
        self.assertEqual(self._prod('F200')[1], 'Фильтры')
    def test_dims_smallest_and_compatible(self):
        E.import_rows(self.conn, [
            {'article': 'F1', 'brand': 'B', 'price': 100, 'cost': 50, 'oe_numbers': 'OE5', 'length': 10},
            {'article': 'F2', 'brand': 'C', 'price': 100, 'cost': 50, 'oe_numbers': 'OE5',
             'weight': 1, 'length': 10, 'width': 5, 'height': 5},
            {'article': 'F3', 'brand': 'D', 'price': 100, 'cost': 50, 'oe_numbers': 'OE5',
             'weight': 2, 'length': 20, 'width': 10, 'height': 10}], 'test')
        E.enrich_full(self.conn, 'oe')
        row = self._prod('F1')
        self.assertEqual(row[4], 10)   # длина своя не тронута (совместима с меньшим комплектом)
        self.assertEqual(row[5], 1)    # вес — из меньшего комплекта группы (F2, не F3)

class TestParseFile(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp)
        E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
    def test_parse_csv_and_paging(self):
        res = E.parse_file_bytes(self.conn, 'comp.csv',
            'Артикул;Цена конкурента\nA1;100\nA2;200\nA3;300\n'.encode('utf-8'))
        self.assertEqual(res['total'], 3)
        self.assertEqual(res['headers'], ['Артикул', 'Цена конкурента'])
        rows = self.conn.execute('SELECT data FROM parse_rows WHERE session=? ORDER BY idx LIMIT 2 OFFSET 2',
                                 (res['parse_id'],)).fetchall()
        import json as _j
        self.assertEqual(_j.loads(rows[0][0])['Артикул'], 'A3')  # постраничность кэша
        # каталог парсингом не тронут
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM products').fetchone()[0], 0)
    def test_parse_cp1251_and_tab(self):
        res = E.parse_file_bytes(self.conn, 'comp.csv', 'Артикул\tЦена\nA1\t100\n'.encode('cp1251'))
        self.assertEqual(res['total'], 1)

class TestHistorySnapshots(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp)
        E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
        E.import_rows(self.conn, [{'article': 'F100', 'brand': 'BOSCH', 'price': 700, 'cost': 400, 'stock': 2}], 's1')
    def test_history_only_real_changes(self):
        E.import_rows(self.conn, [{'article': 'F100', 'brand': 'BOSCH', 'price': 700, 'cost': 400, 'stock': 5}], 's2')  # та же цена
        n = self.conn.execute('SELECT COUNT(*) FROM price_history').fetchone()[0]
        self.assertEqual(n, 1)  # только первичная запись, повтор без изменений не пишется
        E.import_rows(self.conn, [{'article': 'F100', 'brand': 'BOSCH', 'price': 770, 'cost': 400, 'stock': 5}], 's3')
        rep = E.price_changes(self.conn, 30)
        self.assertEqual(rep['changed_sku'], 1)
        self.assertEqual(rep['rises'], 1)
        self.assertEqual(rep['rows'][0]['delta_pct'], 10.0)
    def test_snapshot_diff(self):
        s1 = E.make_snapshot(self.conn, 'первый')['snapshot_id']
        E.import_rows(self.conn, [
            {'article': 'F100', 'brand': 'BOSCH', 'price': 800, 'cost': 400},
            {'article': 'F200', 'brand': 'MANN', 'price': 100, 'cost': 50}], 's2')
        s2 = E.make_snapshot(self.conn, 'второй')['snapshot_id']
        d = E.snapshot_diff(self.conn, s1, s2)
        self.assertEqual([r['article'] for r in d['added']], ['F200'])
        self.assertEqual(d['removed'], [])
        self.assertEqual(d['price_changed'][0]['new_price'], 800)

class TestAnalogSuggestions(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp)
        E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
        E.import_rows(self.conn, [
            {'article': 'ABC12345', 'brand': 'BOSCH', 'price': 100, 'cost': 50},
            {'article': 'ABC12346', 'brand': 'MANN', 'price': 100, 'cost': 50},    # опечатка в последней цифре
            {'article': 'ABC12345', 'brand': 'MAHLE', 'price': 100, 'cost': 50},   # тот же артикул, другой бренд
            {'article': 'ZZZ9999', 'brand': 'FEBI', 'price': 100, 'cost': 50},     # непохожий
            {'article': 'ABC12345', 'brand': 'FAG', 'price': 100, 'cost': 50, 'analog_list': 'X1'},  # аналоги уже есть
            {'article': 'DEF777', 'brand': 'BOSCH', 'price': 100, 'cost': 50, 'oe_numbers': 'OE1'},
            {'article': 'DEF778', 'brand': 'MANN', 'price': 100, 'cost': 50, 'oe_numbers': 'OE1'}], 'test')  # уже OE-связь
    def test_suggestions_only(self):
        res = E.analog_suggestions(self.conn)
        pairs = {(r['article'], r['brand'], r['candidate_article'], r['candidate_brand']) for r in res['suggestions']}
        self.assertIn(('ABC12345', 'BOSCH', 'ABC12346', 'MANN'), pairs)    # опечатка найдена
        self.assertIn(('ABC12345', 'BOSCH', 'ABC12345', 'MAHLE'), pairs)   # тот же артикул, бренд другой
        self.assertFalse(any(r['article'] == 'ZZZ9999' for r in res['suggestions']))   # непохожие молчат
        self.assertFalse(any(r['brand'] == 'FAG' for r in res['suggestions']))        # с аналогами не трогаем
        self.assertFalse(any(r['article'].startswith('DEF') for r in res['suggestions']))  # OE-связь исключена
        # главное: подсказки НИЧЕГО не записали
        row = self.conn.execute("SELECT analog_list FROM products WHERE article='ABC12345' AND brand='BOSCH'").fetchone()
        self.assertEqual(row[0], '')

class TestOzonExport(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp)
        E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
    def test_ozon_row_rules(self):
        p = {'article': 'F100', 'brand': 'BOSCH', 'name': 'Фильтр', 'price': 1000.4, 'cost': 500,
             'weight': 0.3, 'length': 6, 'width': 10, 'height': 8, 'tnved': '8421230000',
             'barcode': '4600000000001', 'image_url': 'http://x/1.jpg', 'ozon_type': 'Фильтр масляный',
             'oe_numbers': 'OE1, OE2', 'multiplicity': 2}
        r = E.ozon_row(p, 1)
        self.assertEqual(len(r), 46)
        self.assertEqual(r[3], 1000)          # цена округлена
        self.assertEqual(r[4], '')            # зачёркнутая не выдумывается
        self.assertEqual(r[12], 300)          # вес кг -> г
        self.assertEqual((r[13], r[14], r[15]), (80, 60, 100))  # Ш/В/Д мм, длина наибольшая
        self.assertEqual(r[21], 'Фильтр масляный')
        self.assertEqual(r[24], 2)            # кратность
        self.assertEqual(r[33], 'OE1; OE2')   # OEM через '; '
        self.assertEqual(r[30], 'Фильтр. Артикул детали: F100. Производитель: BOSCH.')
        self.assertEqual(r[44], '')           # ошибок нет
    def test_ozon_row_no_invented_price(self):
        r = E.ozon_row({'article': 'F1', 'brand': 'B', 'name': 'X', 'price': 0}, 1, discount_pct=30)
        self.assertEqual(r[3], '')            # нет цены — пустая ячейка даже со скидкой
        self.assertIn('не заполнена цена', r[44])
        r2 = E.ozon_row({'article': 'F1', 'brand': 'B', 'name': 'X', 'price': 100, 'old_price': 150}, 1)
        self.assertEqual(r2[4], 150)          # явная старая цена выше цены
        r3 = E.ozon_row({'article': 'F1', 'brand': 'B', 'name': 'X', 'price': 100}, 1, discount_pct=30)
        self.assertEqual(r3[4], 130)          # надбавка только по выбору продавца

class TestOzonStage2(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp)
        E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
        E.import_rows(self.conn, [
            {'article': 'F100', 'brand': 'BOSCH', 'price': 1000, 'cost': 500},
            {'article': 'F200', 'brand': 'MANN', 'price': 2000, 'cost': 900}], 'test')
    def test_donor_warranty_country(self):
        E.import_donors(self.conn, [{'article': 'F100', 'brand': 'BOSCH',
                                     'warranty': '12 месяцев', 'country': 'Германия'}], 'dict')
        E.enrich_full(self.conn)
        row = self.conn.execute("SELECT warranty,country FROM products WHERE article='F100'").fetchone()
        self.assertEqual(tuple(row), ('12 месяцев', 'Германия'))
    def test_ozon_scope_keys(self):
        data = E.export_ozon_csv_bytes(self.conn, keys={('F200', 'MANN')}).decode('utf-8-sig')
        self.assertIn('F200', data)
        self.assertNotIn('F100', data.split('\n')[1] if len(data.split('\n')) > 1 else '')
    def test_ozon_xlsx(self):
        import io as _io, zipfile
        data = E._xlsx_from_rows(E.OZON_HEADERS, E._ozon_rows_data(self.conn)[0], 'Ozon')
        z = zipfile.ZipFile(_io.BytesIO(data))
        sheet = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
        self.assertIn('Артикул*', sheet)
        self.assertIn('F100', sheet)

class TestOzonStage3(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp)
        E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
        E.import_rows(self.conn, [{'article': 'PAD1', 'brand': 'ATE', 'name': 'Колодки тормозные',
            'category': 'Тормозные колодки', 'price': 2500, 'cost': 1200, 'tnved': '8708309109',
            'ozon_category': 'Автотовары'}], 'test')
    def test_std_dims_exact_fill(self):
        # «Распредвал» — точная запись встроенного словаря приложения (50x10x10 см, 4 кг)
        row, yellow = E.ozon_row_meta({'article': 'X', 'brand': 'B', 'name': 'Распредвал',
            'category': 'Распредвал', 'price': 100}, 1)
        self.assertEqual(yellow, {12, 13, 14, 15})
        self.assertEqual(row[12], 4000)                 # вес 4 кг -> 4000 г
        self.assertEqual((row[13], row[14], row[15]), (100, 100, 500))  # Ш/В/Д мм
        self.assertIn('СТАНДАРТ', row[45])              # честная пометка «не измерено»
        # реальные данные не перетираются стандартом
        row2, yellow2 = E.ozon_row_meta({'article': 'X', 'brand': 'B', 'name': 'Распредвал',
            'category': 'Распредвал', 'price': 100, 'weight': 5, 'length': 60, 'width': 12, 'height': 12}, 1)
        self.assertEqual(yellow2, set())
        self.assertEqual(row2[12], 5000)
    def test_pairs_fill_and_validate(self):
        E.import_ozon_pairs(self.conn, [{'category': 'Автотовары', 'type': 'Колодки тормозные'}])
        pairs = E._pairs_map(self.conn)
        row, _ = E.ozon_row_meta({'article': 'X', 'brand': 'B', 'name': 'N', 'price': 100,
            'ozon_category': 'Автотовары'}, 1, pairs=pairs)
        self.assertEqual(row[21], 'Колодки тормозные')  # единственный тип категории подставлен
        row2, _ = E.ozon_row_meta({'article': 'X', 'brand': 'B', 'name': 'N', 'price': 100,
            'ozon_category': 'Автотовары', 'ozon_type': 'Чужой тип'}, 1, pairs=pairs)
        self.assertIn('справочнике Ozon', row2[44])     # невалидная пара — ошибка
    def test_chz_by_tnved(self):
        row, _ = E.ozon_row_meta({'article': 'X', 'brand': 'B', 'name': 'N', 'price': 100,
            'tnved': '8708309109'}, 1, chz_codes=['8708'])
        self.assertEqual(row[23], 'Да')
        self.assertIn('ЧЗ по списку', row[45])
    def test_template_and_xlsx(self):
        tpl = E.ozon_template_rows()
        self.assertEqual(len(tpl), 4)
        self.assertEqual(len(tpl[1]), 46)
        import io as _io, zipfile
        data = E.export_ozon_xlsx_bytes(self.conn)
        z = zipfile.ZipFile(_io.BytesIO(data))
        sheet = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
        self.assertIn('Название товара', sheet)         # шапка шаблона
        self.assertIn('xl/styles.xml', z.namelist())    # стили для заливки

class TestPerfBasics(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp)
        E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
    def test_wal_mode_on(self):
        mode = self.conn.execute('PRAGMA journal_mode').fetchone()[0]
        self.assertEqual(str(mode).lower(), 'wal')
    def test_gzip_helper(self):
        import gzip as _gz
        class FakeH: headers = {'Accept-Encoding': 'gzip, deflate'}
        body = b'{"ok": true, "data": "' + b'x' * 5000 + b'"}'
        out, extra = E.Handler._maybe_gzip(FakeH(), body)
        self.assertEqual(extra.get('Content-Encoding'), 'gzip')
        self.assertLess(len(out), len(body))
        self.assertEqual(_gz.decompress(out), body)
        small, extra2 = E.Handler._maybe_gzip(FakeH(), b'{}')
        self.assertEqual((small, extra2), (b'{}', {}))  # мелкие ответы не сжимаем

class TestIncrementalRecalc(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp)
        E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
        self.st = {'tax_mode': 'usn6', 'target_margin': 20, 'min_profit': 150}
        E.import_rows(self.conn, [
            {'article': f'A{i}', 'brand': 'B', 'name': 'Деталь', 'price': 1000 + i * 100,
             'cost': 500, 'sales': 10, 'weight': 0.3} for i in range(3)], 'test')
    def test_incremental_flow(self):
        r1 = E.recalc_catalog(self.conn, self.st)
        self.assertEqual(r1['recalculated'], 3)
        r2 = E.recalc_catalog(self.conn, self.st)
        self.assertEqual((r2['recalculated'], r2['skipped']), (0, 3))   # ничего не изменилось
        self.assertEqual(r2['profitable'], r1['profitable'])             # итоги по всей таблице
        E.import_rows(self.conn, [{'article': 'A1', 'brand': 'B', 'price': 5000, 'cost': 500}], 'test')
        r3 = E.recalc_catalog(self.conn, self.st)
        self.assertEqual((r3['recalculated'], r3['skipped']), (1, 2))   # только изменённая строка
        p = self.conn.execute("SELECT profit FROM eco_results WHERE article='A1'").fetchone()[0]
        self.assertGreater(p, 3000)                                      # результат правда обновился
        r4 = E.recalc_catalog(self.conn, {**self.st, 'target_margin': 30})
        self.assertEqual(r4['recalculated'], 3)                          # смена настроек — все строки
        r5 = E.recalc_catalog(self.conn, self.st, force=True)
        self.assertEqual(r5['recalculated'], 3)                          # force — полный пересчёт

class TestOneFilePaths(unittest.TestCase):
    def test_app_html_found_in_bundle(self):
        import tempfile, pathlib
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / 'index.html').write_text('<html>app</html>', encoding='utf-8')
        old_b, old_base = E.BUNDLE, E.BASE
        E.BUNDLE, E.BASE = tmp, tmp / 'engine'
        try:
            self.assertEqual(E._app_html_path(), tmp / 'index.html')
        finally:
            E.BUNDLE, E.BASE = old_b, old_base
    def test_assets_found_in_bundle(self):
        import tempfile, pathlib
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / 'ozon_template.json').write_text('[["g"],["h"],["m"],["x"]]', encoding='utf-8')
        old_b, old_data = E.BUNDLE, E.DATA
        E.BUNDLE, E.DATA = tmp, tmp / 'nope'
        E._ASSET_CACHE.pop('ozon_template.json', None)
        try:
            self.assertEqual(len(E.ozon_template_rows()), 4)
        finally:
            E.BUNDLE, E.DATA = old_b, old_data
            E._ASSET_CACHE.pop('ozon_template.json', None)

class TestDiag(unittest.TestCase):
    def test_diag_fields(self):
        import tempfile, pathlib, json as _json
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / 'index.html').write_text('<head></head><script>/*! xlsx lib */</script>', encoding='utf-8')
        old_b, old_base = E.BUNDLE, E.BASE
        E.BUNDLE, E.BASE = tmp, tmp / 'engine'
        try:
            p = E._app_html_path()
            txt = p.read_text(encoding='utf-8')
            self.assertTrue('<script>/*! xlsx' in txt)
            self.assertTrue(len(_json.dumps({'size': p.stat().st_size})) > 0)
        finally:
            E.BUNDLE, E.BASE = old_b, old_base

class TestExternalXlsx(unittest.TestCase):
    def test_extract_and_serve_markup(self):
        html = '<head></head><script>/*! xlsx встроен офлайн (v11) */\nvar XLSX={};/* xlsx.js */</script><script>app</script>'
        out = E._extract_xlsx(html)
        self.assertIn('<script src="/lib/xlsx.js"></script>', out)
        self.assertNotIn('var XLSX', out)
        self.assertIn(b'xlsx.js', E._XLSX_JS)
        self.assertEqual(E._extract_xlsx('<html>без либы</html>'), '<html>без либы</html>')

class TestSqlExportSelection(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp); E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
        E.import_rows(self.conn, [
            {'article': 'A1', 'brand': 'BOSCH', 'name': 'Фильтр', 'price': 1000, 'cost': 600},
            {'article': 'A2', 'brand': 'MANN', 'name': 'Фильтр 2', 'price': 2000, 'cost': 900}], 'test')
    def test_catalog_keys_filter(self):
        data = E.export_catalog_csv_bytes(self.conn, keys=[('A1', 'BOSCH')])
        self.assertIn('A1', data.decode('utf-8-sig'))
        self.assertNotIn('A2', data.decode('utf-8-sig'))
        x = E.export_catalog_xlsx_bytes(self.conn, keys=[('A2', 'MANN')])
        self.assertTrue(x.startswith(b'PK'))
    def test_ozon_xlsx_keys(self):
        x = E.export_ozon_xlsx_bytes(self.conn, keys={('A1', 'BOSCH')})
        self.assertTrue(x.startswith(b'PK'))

class TestAuditFixes133(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp); E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        E.TOKEN_PATH = pathlib.Path(self.tmp) / 'token.txt'; E._TOKEN_CACHE = None
        E.SECRETS_PATH = pathlib.Path(self.tmp) / 'secrets.json'
        self.conn = E.db()
    def test_volume_preserved(self):  # A2
        E.import_rows(self.conn, [{'article': 'V1', 'brand': 'B', 'price': 100, 'volume': 2.5}], 't')
        self.assertEqual(self.conn.execute("SELECT volume FROM products WHERE article='V1'").fetchone()[0], 2.5)
        E.import_rows(self.conn, [{'article': 'V1', 'brand': 'B', 'price': 100}], 't')  # без объёма — не затирать
        self.assertEqual(self.conn.execute("SELECT volume FROM products WHERE article='V1'").fetchone()[0], 2.5)
    def test_host_check_and_token(self):  # A1 + A7
        import threading, http.client
        from http.server import ThreadingHTTPServer
        srv = ThreadingHTTPServer(('127.0.0.1', 0), E.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            port = srv.server_address[1]
            c = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            c.request('GET', '/health', headers={'Host': 'evil.example.com'})
            self.assertEqual(c.getresponse().status, 403)
            c = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            c.request('GET', '/health')
            self.assertEqual(c.getresponse().status, 200)
        finally:
            srv.shutdown()
    def test_secret_roundtrip_passthrough(self):  # A3 (на не-Windows — passthrough)
        E.save_secret('UC_MAIL_PASSWORD', 'pw123')
        self.assertEqual(E.secrets().get('UC_MAIL_PASSWORD'), 'pw123')

class TestAudit2Fixes135(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp); E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
    def test_missing_fields_not_clobbered(self):  # B1
        E.import_rows(self.conn, [{'article': 'A1', 'brand': 'B', 'price': 1000, 'cost': 600,
                                   'stock': 50, 'sales': 10, 'weight': 1.5, 'length': 10, 'width': 10, 'height': 10}], 'full')
        E.import_rows(self.conn, [{'article': 'A1', 'brand': 'B', 'price': 1100}], 'price-only')
        r = self.conn.execute("SELECT price,stock,sales,weight,length FROM products WHERE article='A1'").fetchone()
        self.assertEqual(tuple(r), (1100.0, 50.0, 10.0, 1.5, 10.0))
        E.import_rows(self.conn, [{'article': 'A1', 'brand': 'B', 'stock': 0}], 'zero')  # явный 0 — честный
        self.assertEqual(self.conn.execute("SELECT stock FROM products WHERE article='A1'").fetchone()[0], 0.0)
    def test_zip_limits(self):  # B3
        import io as _io, zipfile
        buf = _io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            for i in range(201): z.writestr('f%d.csv' % i, 'a;b\n1;2\n')
        with self.assertRaises(ValueError): E.files_from_zip(buf.getvalue())
    def test_barcode_not_article(self):  # B7
        rows = E.rows_from_csv_bytes('Штрихкод;Артикул;Цена\n460001;ART1;100\n'.encode('utf-8'))
        self.assertEqual(rows[0]['article'], 'ART1')
    def test_db_reinit_same_path(self):  # B4: повторные db() не падают и схема готова
        c2 = E.db(); self.assertIsNotNone(c2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products'").fetchone())

class TestSecretsB6(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp); E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        E.SECRETS_PATH = pathlib.Path(self.tmp) / 'secrets.json'
        self.conn = E.db()
    def test_save_and_delete_secret(self):
        E.save_secret('UC_SET_wbApiToken', 'tok123')
        self.assertEqual(E.secrets().get('UC_SET_wbApiToken'), 'tok123')
        E.save_secret('UC_SET_wbApiToken', '')
        self.assertNotIn('UC_SET_wbApiToken', E.secrets())

class TestSupplierHeaders139(unittest.TestCase):
    def test_moskow_supplier_csv(self):
        # реальный формат поставщика: Бренд;Каталожный номер;Описание;Остаток;...;Цена;Штрихкод;ТН ВЭД (cp1251)
        text = ('Бренд;Каталожный номер;Описание;Остаток;Кратность отгрузки;Валюта;Цена;Штрихкод;ТН ВЭД\r\n'
                'METELLI;01-2497;Втулка клапана VOLVO;1;1;RUB;149.86;000403;8708999797\r\n'
                'KYB;441040;Амортизатор AUDI;2;1;RUB;4434.5;000441;\r\n')
        rows = E.rows_from_csv_bytes(text.encode('cp1251'))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['article'], '01-2497')
        self.assertEqual(rows[0]['brand'], 'METELLI')
        self.assertEqual(str(rows[0]['name']), 'Втулка клапана VOLVO')
        self.assertEqual(str(rows[0]['barcode']), '000403')
        self.assertEqual(float(str(rows[0]['price']).replace(',', '.')), 149.86)

class TestEnrichFields140(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp); E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
    def test_browser_enrichment_columns(self):
        text = ('Бренд;Каталожный номер;Описание;Себестоимость;Аналоги;Группа артикулов;Валюта;Мин. остаток;Объём;ID категории Ozon;Статус Честного знака;Невыкуп\r\n'
                'BOSCH;F100;Фильтр;600;F200;GRP1;RUB;5;1.25;12345;Не требуется;12\r\n')
        rows = E.rows_from_csv_bytes(text.encode('cp1251'))
        self.assertEqual(len(rows), 1)
        E.import_rows(self.conn, rows, 'test')
        r = self.conn.execute("SELECT cost,analog_list,group_articles,currency,min_stock,volume,ozon_description_category_id,mark_status,no_buy_pct FROM products WHERE article='F100'").fetchone()
        self.assertEqual(tuple(r), (600.0, 'F200', 'GRP1', 'RUB', 5.0, 1.25, '12345', 'Не требуется', 12.0))
    def test_new_fields_not_clobbered_when_absent(self):
        E.import_rows(self.conn, [{'article': 'A1', 'brand': 'B', 'currency': 'RUB', 'min_stock': 3}], 't')
        E.import_rows(self.conn, [{'article': 'A1', 'brand': 'B', 'price': 10}], 't')
        r = self.conn.execute("SELECT currency,min_stock FROM products WHERE article='A1'").fetchone()
        self.assertEqual(tuple(r), ('RUB', 3.0))

class TestXlsxStdlib141(unittest.TestCase):
    def test_engine_written_xlsx(self):
        # книга, записанная самим движком (inlineStr), читается без openpyxl
        data = E._xlsx_from_rows(['Артикул', 'Бренд', 'Цена'], [['F100', 'BOSCH', 700]], 'Лист')
        rows = E._xlsx_sheet_rows(data)
        self.assertEqual(rows[0][0], 'Артикул')
        self.assertEqual(rows[1][0], 'F100')
        self.assertEqual(rows[1][2], 700)
    def test_shared_strings_xlsx(self):
        import io as _io, zipfile
        buf = _io.BytesIO()
        ss = ('<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="4" uniqueCount="4">'
              '<si><t>Артикул</t></si><si><t>Цена</t></si><si><t>ART1</t></si><si><t>BOSCH</t></si></sst>')
        sheet = ('<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                 '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                 '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>1500</v></c></row></sheetData></worksheet>')
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('xl/sharedStrings.xml', ss); z.writestr('xl/worksheets/sheet1.xml', sheet)
        rows = E.rows_from_xlsx_bytes(buf.getvalue())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['article'], 'ART1')
        out = E.rows_from_xlsx_bytes(E._xlsx_from_rows(['Артикул', 'Бренд', 'Цена'], [['F100', 'BOSCH', 700]], 'Лист'))
        self.assertEqual(out[0]['article'], 'F100')

class TestDiskFull142(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp); E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        E.TOKEN_PATH = pathlib.Path(self.tmp) / 'token.txt'; E._TOKEN_CACHE = None
        self.conn = E.db()
    def test_diag_has_disk_fields(self):
        h = E.Handler.__new__(E.Handler)
        sent = {}
        h._send = lambda code, obj: sent.update(code=code, obj=obj)
        # эмулируем _send_disk_full без сокета
        E.Handler._send_disk_full(h)
        self.assertEqual(sent['code'], 507)
        self.assertIn('Не хватает места', sent['obj']['error'])

class TestProtocol(unittest.TestCase):
    def test_register_protocol_graceful(self):
        # на не-Windows и без реестра — тихий False, без исключений
        self.assertIn(E.register_protocol(), (True, False))

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


class TestDiskPreflight144(unittest.TestCase):
    def test_ensure_free_space_raises(self):
        import unittest.mock as mock
        U = collections.namedtuple('U', 'total used free')
        with mock.patch('shutil.disk_usage', return_value=U(10**9, 10**9, 1024)):
            self.assertRaises(E.DiskFullError, E.ensure_free_space, 1000)
    def test_import_file_rejects_before_write(self):
        import tempfile, pathlib
        tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(tmp); E.DB_PATH = pathlib.Path(tmp) / 't.db'
        conn = E.db()
        import unittest.mock as mock
        U = collections.namedtuple('U', 'total used free')
        with mock.patch('shutil.disk_usage', return_value=U(10**9, 10**9, 1024)):
            self.assertRaises(E.DiskFullError, E.import_file_bytes, conn, 'p.csv',
                'Артикул;Бренд;Цена\nF1;B;10\n'.encode('utf-8'))
        self.assertEqual(conn.execute('SELECT COUNT(*) c FROM products').fetchone()['c'], 0)

class TestSqlParity145(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        E.DATA = pathlib.Path(self.tmp); E.DB_PATH = pathlib.Path(self.tmp) / 't.db'
        self.conn = E.db()
    def test_enrich_only_first_file(self):
        E.import_file_bytes(self.conn, 'price.csv', 'Артикул;Бренд;Цена\nF100;BOSCH;700\n'.encode('utf-8'))
        res = E.import_file_bytes(self.conn, 'cross.csv',
            'Артикул;Бренд;Название\nF100;BOSCH;Фильтр\nF999;BOSCH;Чужой\n'.encode('utf-8'), enrich_only=True)
        self.assertEqual(res['skipped_outside_price'], 1)
        rows = self.conn.execute('SELECT article,name FROM products ORDER BY article').fetchall()
        self.assertEqual(len(rows), 1)  # новый SKU из второго файла не создан
        self.assertEqual(rows[0]['name'], 'Фильтр')  # а существующий обогатился
    def test_norm_keys_and_quarantine(self):
        E.import_rows(self.conn, [{'article': 'F 100', 'brand': 'BOSCH', 'oe_numbers': 'OE1'}], 't')
        E.import_donors(self.conn, [{'article': 'F-100', 'brand': 'bosch', 'name': 'Фильтр', 'category': 'Фильтры'}], 'd')
        res = E.enrich_full(self.conn)
        self.assertEqual(res['filled']['name'], 1)  # нормализованная пара совпала
        self.assertEqual(res['filled']['category'], 1)
    def test_quarantine_conflicting_norm(self):
        E.import_rows(self.conn, [{'article': 'A-1', 'brand': 'X', 'oe_numbers': 'OE9'},
                                  {'article': 'A 1', 'brand': 'X', 'name': 'Другой'}], 't')
        E.import_donors(self.conn, [{'article': 'A1', 'brand': 'X', 'name': 'Не должен попасть'}], 'd')
        res = E.enrich_full(self.conn)
        self.assertGreaterEqual(res['quarantined'], 2)
        got = self.conn.execute("SELECT name FROM products WHERE article='A-1'").fetchone()['name']
        self.assertEqual(got, '')  # спорная идентичность не обогатилась
    def test_calc_row_overrides_and_multiplicity(self):
        st = {'commission_pct': 14, 'transfer_pct': 1.5, 'last_mile': 25, 'handover': 10,
              'pack': 18, 'transit': 30, 'tax_regime': 'usn_income_6', 'tax_pct': 6, 'target_margin': 20}
        base = E.calc_row({'article': 'A', 'price': 1000, 'cost': 500, 'sales': 10}, st)
        own = E.calc_row({'article': 'A', 'price': 1000, 'cost': 500, 'sales': 10, 'ozon_commission': 30}, st)
        self.assertGreater(own['total'], base['total'])  # своя ставка SKU важнее настроек
        mult = E.calc_row({'article': 'A', 'price': 1000, 'cost': 100, 'sales': 10, 'multiplicity': 3}, st)
        plain = E.calc_row({'article': 'A', 'price': 1000, 'cost': 100, 'sales': 10}, st)
        self.assertGreater(mult['total'], plain['total'])  # кратность подняла себестоимость
    def test_group_articles_filled(self):
        E.import_rows(self.conn, [{'article': 'G1', 'brand': 'B', 'oe_numbers': 'OEG'},
                                  {'article': 'G2', 'brand': 'B', 'oe_numbers': 'OEG'}], 't')
        res = E.enrich_full(self.conn)
        self.assertEqual(res['filled']['group_articles'], 2)


class TestBrowserParity146(unittest.TestCase):
    ST = {'commission_pct': 14, 'transfer_pct': 1.5, 'last_mile': 25, 'handover': 10,
          'pack': 18, 'transit': 30, 'tax_regime': 'usn_income_6', 'tax_pct': 6, 'target_margin': 20,
          'ozon': {'fulfillment': 'FBS', 'logistics_manual': 100, 'processing': 0,
                   'last_mile': 25, 'handover_mode': 'sc', 'handover_fee': 10,
                   'units_per_shipment': 1, 'nonstd_enabled': True, 'nonstd_pct': 3, 'nonstd_cap': 280}}
    def test_browser_formula_hand_calc(self):
        # price 1000, cost 500: comm 140, transfer 15, logistics 100, last_mile 25,
        # handover 10, pack 18, transit 30, no_buy 0 -> parts 838, tax 6% = 60, total 898
        r = E.calc_row({'article': 'A', 'brand': 'B', 'price': 1000, 'cost': 500, 'sales': 10}, dict(self.ST))
        self.assertAlmostEqual(r['total'], 898, delta=0.011)
        self.assertAlmostEqual(r['profit'], 102, delta=0.011)
        self.assertEqual(r['brand'], 'B')
    def test_no_buy_and_nonstd(self):
        st = dict(self.ST); st['no_buy_pct'] = 0
        r = E.calc_row({'article': 'A', 'price': 1000, 'cost': 500, 'sales': 10,
                        'no_buy_pct': 10, 'weight': 30}, st)
        # failed=2*100+25=225; returns=225*10/90=25; nonstd=min(30,280)=30
        # parts=500+140+15+100+25+10+18+30+25+30=893; tax 60; total 953
        self.assertAlmostEqual(r['total'], 953, delta=0.011)
    def test_old_path_kept_without_ozon(self):
        st = {k: v for k, v in self.ST.items() if k != 'ozon'}
        r = E.calc_row({'article': 'A', 'price': 1000, 'cost': 500, 'sales': 10}, st)
        self.assertGreater(r['total'], 0)

class TestParityRecheck146(unittest.TestCase):
    ST = TestBrowserParity146.ST
    def test_default_and_category_no_buy(self):
        st = dict(self.ST); st['no_buy_pct'] = 8
        r = E.calc_row({'article': 'A', 'price': 1000, 'cost': 500, 'sales': 10}, st)
        # failed=225, returns=225*8/92=19.565..; parts=838+19.57=857.57, tax 60 -> 917.57
        self.assertAlmostEqual(r['total'], 917.57, delta=0.02)
        st2 = dict(st); st2['no_buy_by_category'] = {'Обувь': 20}
        r2 = E.calc_row({'article': 'A', 'price': 1000, 'cost': 500, 'sales': 10, 'category': 'Обувь'}, st2)
        self.assertGreater(r2['total'], r['total'])
    def test_fixed_monthly_divided_by_sales(self):
        r = E.calc_row({'article': 'A', 'price': 1000, 'cost': 500, 'sales': 10, 'fixed_cost': 100}, dict(self.ST))
        # фикс 100/мес при 10 продажах = 10/ед: parts 838+10=848, tax 60, total 908
        self.assertAlmostEqual(r['total'], 908, delta=0.011)
    def test_solver_no_buy_100(self):
        st = dict(self.ST); st['no_buy_pct'] = 100
        r = E.calc_row({'article': 'A', 'price': 1000, 'cost': 500, 'sales': 10}, st)
        self.assertEqual((r['break_even'], r['target']), (0, 0))

class TestHeaderMapping146(unittest.TestCase):
    def test_one_column_one_field(self):
        mp = E.map_header(['Код ТН ВЭД', 'Артикул', 'Бренд'])
        self.assertEqual(mp['article'], 1); self.assertEqual(mp['tnved'], 0)
        mp2 = E.map_header(['Артикул', 'Зачёркнутая цена', 'Цена'])
        self.assertEqual(mp2['old_price'], 1); self.assertEqual(mp2['price'], 2)
        mp3 = E.map_header(['Артикул', 'Весогабариты', 'Вес, кг'])
        self.assertEqual(mp3['dimensions_str'], 1); self.assertEqual(mp3['weight'], 2)
    def test_browser_fields_recognized(self):
        mp = E.map_header(['Артикул', 'Логистика Ozon, ₽/ед', 'Вес нетто, кг', 'Ozon realFBS доставка, ₽/ед'])
        self.assertEqual(mp.get('ozon_logistics'), 1)
        self.assertEqual(mp.get('net_weight'), 2)
        self.assertEqual(mp.get('ozon_realfbs_delivery'), 3)
    def test_supplier_file_still_maps(self):
        mp = E.map_header(['Бренд', 'Каталожный номер', 'Описание', 'Остаток', 'Кратность отгрузки', 'Валюта', 'Цена', 'Штрихкод', 'ТН ВЭД'])
        self.assertEqual(mp['article'], 1); self.assertEqual(mp['price'], 6); self.assertEqual(mp['tnved'], 8)
