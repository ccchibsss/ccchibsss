import csv,io,json,pathlib,sqlite3,subprocess,sys,unittest,zipfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine as E
class DataOnlyExport(unittest.TestCase):
    def test_canonical_values_no_formulas_or_economics(self):
        c=sqlite3.connect(':memory:')
        cols=[dict(key='article',name='Артикул'),dict(key='name',name='Название'),dict(key='weight',name='Вес'),dict(key='extra',name='Своя',custom=True)]
        token=E.app_catalog_state(c,'begin',dict(total=2,metadata={}))['token']
        rows=[dict(article='00123',name='=CMD()',visible=False,custom={'extra':'OE;1'},netProfit=999),dict(article='B',weight=2)]
        E.app_catalog_state(c,'chunk',dict(token=token,part=0,chunk={'rows':rows}))
        E.app_catalog_state(c,'commit',dict(token=token))
        raw=E.export_data_only(c,cols,'csv').decode('utf-8-sig');table=list(csv.reader(io.StringIO(raw),delimiter=';'))
        self.assertEqual(table[1],['00123',"'=CMD()",'','OE;1']);self.assertEqual(len(table),3)
        self.assertNotIn('999',raw)
        with zipfile.ZipFile(io.BytesIO(E.export_data_only(c,cols,'xlsx'))) as z:
            xml=z.read('xl/worksheets/sheet1.xml').decode()
            self.assertNotIn('<f>',xml);self.assertIn('00123',xml);self.assertIn('=CMD()',xml);self.assertNotIn('999',xml)
        self.assertEqual(c.execute('SELECT COUNT(*) FROM app_catalog_chunks').fetchone()[0],1)
        c.close()
    def test_client(self):
        subprocess.check_call(['node',str(pathlib.Path(__file__).resolve().parents[2]/'tests/data-only-export-client.js')])
