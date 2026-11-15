import io,json,pathlib,sqlite3,subprocess,sys,unittest,zipfile,csv
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine  # Registers the internal modules stored in the single engine file.
from export_custom import custom_cell
import uc_engine as E

class ExportCustom(unittest.TestCase):
    def test_actual_client_raw_custom_request(self):
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/export-custom-client.js'
        subprocess.check_call(['node',str(path)])

    def test_actual_browser_custom_conversion(self):
        values=['00042','text','12,5','1.234,56','1,234.56','12.345.678','1,2,3','12abc',
                ' 2 500 %','1e3','1e','inf','Infinity','0x10','😀','\ufeff42','\x1c42',
                0,False,True,None,'',[],[1,2],{}, {'x':2}]
        cases=[{'raw':{'value':v},'formatted':formatted} for v in values for formatted in [True,False]]
        cases += [dict(c,textual=True) for c in cases]
        cases += [{'raw':{'value':'2026-01-01T00:00:00.000Z'},'dates':['value'],'formatted':True,'textual':True}]
        cases += [{'raw':{'value':None},'nonfinite':['value'],'formatted':True,'textual':True,'special':{'value':v}} for v in ['NaN','Infinity','-Infinity']]
        cases += [{'raw':{},'formatted':True},{'raw':{},'formatted':False},
                  {'raw':{'value':'date'},'dates':['value'],'formatted':True},
                  {'raw':{'value':'date'},'dates':['value'],'formatted':False},
                  {'raw':{'value':None},'nonfinite':['value'],'formatted':True},
                  {'raw':{'value':None},'nonfinite':['value'],'formatted':False}]
        cases += [dict(c,xlsx=True) for c in cases if c.get('textual')]
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/export-custom-reference.js'
        expected=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps(cases),text=True))
        for case,want in zip(cases,expected):
            with self.subTest(case=case):self.assertEqual(custom_cell(case['raw'],'value',case['formatted'],case.get('dates',[]),case.get('nonfinite',[]),case.get('textual',False),case.get('special')),want)

    def test_text_custom_snapshot_preserves_codes(self):
        conn=sqlite3.connect(':memory:')
        try:
            columns=[['text','Текст']]
            meta=[{'key':'c_text','custom':'text','custom_format':True,'custom_text':True}]
            E.store_export_cells(conn,[{'article':'A','values':[0],'custom':{'text':'00042 текст'}}],columns,meta)
            data=json.loads(conn.execute('SELECT data FROM export_cells').fetchone()[0])
            self.assertEqual(data['text'],'00042 текст')
            for bad in [[['x','X'],['x','Y']],[['__export_order','X']],[[[], 'X']]]:
                with self.assertRaises(ValueError):E.store_export_cells(conn,[],bad)
            with self.assertRaises(ValueError):E.store_export_cells(conn,[{'values':['x'],'formulas':[]}],columns)
        finally:conn.close()

    def test_sql_custom_preparation_and_snapshot_failure_atomicity(self):
        conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
        conn.executescript("CREATE TABLE products(article TEXT,brand TEXT);"
            "CREATE TABLE eco_results(article TEXT,brand TEXT,total REAL,profit REAL,margin REAL,roi REAL,break_even REAL,target REAL,fields_json TEXT);"
            "INSERT INTO products VALUES('001','B'),('001','C');")
        columns=[['__export_0','Код'],['__export_1','Пользовательское'],['__export_2','Вычисляемое']]
        meta=[{'key':'article'},{'key':'c_amount','custom':'amount','custom_format':True},{'key':'netProfit'}]
        rows=[{'article':'001','brand':'B','values':['001',999,123],'custom':{'amount':'1.234,56'}},
              {'article':'001','brand':'C','values':['001',999,456],'custom':{'amount':'12abc'}}]
        try:
            E.store_export_cells(conn,rows,columns,meta)
            records=E.export_catalog_records(conn)
            self.assertEqual([r['__export_1'] for r in records],[1234.56,12])
            self.assertEqual([r['__export_2'] for r in records],[123,456])
            blob=E.export_catalog_csv_bytes(conn,columns=columns)
            parsed=list(csv.reader(io.StringIO(blob.decode('utf-8-sig')),delimiter=';'))
            self.assertEqual(parsed[1],['001','1234,56','123'])
            blob=E.export_catalog_xlsx_bytes(conn,columns=columns)
            with zipfile.ZipFile(io.BytesIO(blob)) as z:self.assertIn('<v>1234.56</v>',z.read('xl/worksheets/sheet1.xml').decode())
            before=conn.execute('SELECT * FROM export_cells').fetchall()
            with self.assertRaises(ValueError):E.store_export_cells(conn,[rows[0],dict(rows[1],values=[1])],columns,meta)
            self.assertEqual(conn.execute('SELECT * FROM export_cells').fetchall(),before)
            with self.assertRaises(ValueError):E.store_export_cells(conn,rows,columns,[{}, {'key':'other','custom':'amount'},{}])
            self.assertEqual(conn.execute('SELECT * FROM export_cells').fetchall(),before)
            conn.execute("CREATE TEMP TRIGGER fail_export BEFORE INSERT ON export_cells WHEN NEW.brand='C' BEGIN SELECT RAISE(ABORT,'test write failure'); END")
            with self.assertRaises(sqlite3.IntegrityError):E.store_export_cells(conn,rows,columns,meta)
            self.assertEqual(conn.execute('SELECT * FROM export_cells').fetchall(),before)
        finally:conn.close()
