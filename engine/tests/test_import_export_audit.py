"""Regression probes from the full import/export audit (real SQLite and files)."""
import io,json,pathlib,sys,tempfile,unittest,zipfile
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine as E

class ImportExportAudit(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=(E.DATA,E.DB_PATH)
        E.DATA=pathlib.Path(self.tmp.name);E.DB_PATH=E.DATA/'audit.db'
        self.c=E.db()
    def tearDown(self):
        self.c.close();E.DATA,E.DB_PATH=self.old;self.tmp.cleanup()
    def zip(self,files):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            for name,data in files:z.writestr(name,data)
        return out.getvalue()
    def test_zip_late_failure_rolls_back_all_files_and_history(self):
        E.import_rows(self.c,[{'article':'KEEP','price':10}],'seed')
        payload=self.zip([('good.csv',b'article;price\nNEW;20\n'),('broken.xlsx',b'not-xlsx')])
        with patch.object(E,'ensure_free_space'),self.assertRaises(Exception):
            E.import_file_bytes(self.c,'batch.zip',payload)
        self.assertEqual([r[0] for r in self.c.execute('SELECT article FROM products')],['KEEP'])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM price_history').fetchone()[0],1)
    def test_normalized_enrich_updates_existing_without_duplicate(self):
        E.import_rows(self.c,[{'article':'AB-12','brand':'Brand','price':10}],'seed')
        with patch.object(E,'ensure_free_space'):
            E.import_file_bytes(self.c,'enrich.csv',b'article;brand;name\nab12;BRAND;new name\n',enrich_only=True)
        rows=self.c.execute('SELECT article,brand,name FROM products').fetchall()
        self.assertEqual([tuple(r) for r in rows],[('AB-12','Brand','new name')])
    def test_cp1251_text_after_long_ascii_prefix_is_lossless(self):
        data=('article;name\n'+'A;'+'x'*500+'\nB;Привет\n').encode('cp1251')
        self.assertEqual(E.rows_from_csv_bytes(data)[1]['name'],'Привет')
    def test_xlsx_absolute_relationship_selects_actual_first_sheet(self):
        original=E._xlsx_workbook([{'name':'first','headers':['article'],'rows':[['FIRST']]},
                                  {'name':'second','headers':['article'],'rows':[['SECOND']]}])
        out=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(original)) as src,zipfile.ZipFile(out,'w') as dst:
            for name in src.namelist():
                data=src.read(name)
                if name=='xl/_rels/workbook.xml.rels':
                    data=data.replace(b'Target="worksheets/sheet1.xml"',b'Target="/xl/worksheets/z-first.xml"')
                dst.writestr('xl/worksheets/z-first.xml' if name=='xl/worksheets/sheet1.xml' else name,data)
        self.assertEqual(E._xlsx_sheet_rows(out.getvalue())[1][0],'FIRST')
    def test_empty_archive_is_not_successful_import(self):
        with patch.object(E,'ensure_free_space'),self.assertRaises(ValueError):
            E.import_file_bytes(self.c,'empty.zip',self.zip([('readme.txt','none')]))
    def test_generic_parse_cp1251_late_text_and_quoted_delimiter(self):
        text='article;name\nA;'+('x'*500)+'\nB;Привет\n'
        self.assertEqual(E._raw_table('data.csv',text.encode('cp1251'))[1][-1][1],'Привет')
        headers,rows=E._raw_table('data.csv',b'article,"name;with;semicolons"\nA,hello\n')
        self.assertEqual(headers,['article','name;with;semicolons'])
        self.assertEqual(rows,[['A','hello']])
    def test_xlsx_control_characters_are_valid_xml(self):
        import xml.etree.ElementTree as ET
        blob=E._xlsx_from_rows(['bad\x00header'],[['=not-a-formula\x01 & < >']])
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for name in z.namelist():
                if name.endswith(('.xml','.rels')):ET.fromstring(z.read(name))
            xml=z.read('xl/worksheets/sheet1.xml').decode()
        self.assertNotIn('<f>',xml)
        self.assertIn('=not-a-formula',xml)
    def test_enrich_ambiguous_identity_does_not_insert(self):
        E.import_rows(self.c,[{'article':'AB-12','brand':'B'},{'article':'AB12','brand':'B'}],'seed')
        with patch.object(E,'ensure_free_space'):
            result=E.import_file_bytes(self.c,'enrich.csv',b'article;brand;name\nab 12;b;do not guess\n',enrich_only=True)
        self.assertEqual(result['imported'],0)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM products').fetchone()[0],2)
    def test_empty_selection_exports_only_headers(self):
        import csv
        E.import_rows(self.c,[{'article':'A','brand':'B','price':1}],'seed')
        cols=[('article','article'),('brand','brand')]
        csv_data=E.export_catalog_csv_bytes(self.c,columns=cols,keys=[])
        self.assertEqual(list(csv.reader(io.StringIO(csv_data.decode('utf-8-sig')),delimiter=';')),[['article','brand']])
        self.assertEqual(E.rows_from_xlsx_bytes(E.export_catalog_xlsx_bytes(self.c,columns=cols,keys=[])),[])
    def test_csv_and_xlsx_roundtrip_text_codes_and_newlines(self):
        E.import_rows(self.c,[{'article':'00042','brand':'B','name':'a;"quote"\nПривет','price':12.5}],'seed')
        cols=[('article','Артикул'),('brand','Бренд'),('name','Название'),('price','Цена')]
        for delim in [';',',','\t','|']:
            out=E.rows_from_csv_bytes(E.export_catalog_csv_bytes(self.c,columns=cols,delimiter=delim))
            self.assertEqual(out[0]['article'],'00042')
            self.assertEqual(out[0]['name'],'a;"quote"\nПривет')
        out=E.rows_from_xlsx_bytes(E.export_catalog_xlsx_bytes(self.c,columns=cols))
        self.assertEqual(out[0]['article'],'00042');self.assertEqual(out[0]['price'],12.5)

    def test_reimport_kit_client_safety(self):
        import subprocess
        subprocess.check_call(['node',str(pathlib.Path(__file__).resolve().parents[2]/'tests/import-export-audit-client.js')])

    def test_generic_duplicate_headers_fail_before_session_is_written(self):
        with self.assertRaisesRegex(ValueError,'Повторяющиеся заголовки'):
            E.parse_file_bytes(self.c,'a.csv',b'article;name;name\nA;first;second\n')
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM parse_sessions').fetchone()[0],0)
