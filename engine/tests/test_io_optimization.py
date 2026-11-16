import csv,io,json,pathlib,sqlite3,subprocess,sys,tempfile,threading,unittest,zipfile
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine as E

class OptimizedIO(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=(E.DATA,E.DB_PATH)
        E.DATA=pathlib.Path(self.tmp.name);E.DB_PATH=E.DATA/'io.db';self.c=E.db()
    def tearDown(self):
        self.c.close();E.DATA,E.DB_PATH=self.old;self.tmp.cleanup()
    def seed(self,rows):
        token=E.app_catalog_state(self.c,'begin',dict(total=len(rows),metadata={},base=E.app_catalog_state(self.c,'read',{})['revision']))['token']
        for part,off in enumerate(range(0,len(rows),1000)):
            E.app_catalog_state(self.c,'chunk',dict(token=token,part=part,chunk={'rows':rows[off:off+1000]}))
        E.app_catalog_state(self.c,'commit',dict(token=token))
    def test_incremental_parser_header_encoding_and_failed_publication(self):
        raw=('Report\n\nАртикул;Бренд;Extra\n001;B;"a\nb"\n002;C;'+'я'*70000+'\n').encode('cp1251')
        r=E.parse_file_bytes(self.c,'price.csv',raw,catalog_import=True)
        values=[json.loads(row[0]) for row in self.c.execute('SELECT data FROM parse_rows WHERE session=? ORDER BY idx',(r['parse_id'],))]
        self.assertEqual(r['total'],2);self.assertEqual(values[0]['Артикул'],'001');self.assertEqual(values[0]['Extra'],'a\nb');self.assertEqual(values[1]['Extra'],'я'*70000)
        count=self.c.execute('SELECT COUNT(*) FROM parse_sessions').fetchone()[0]
        def broken(*args):
            yield ['article','name']
            for i in range(1500):yield [str(i),'row']
            raise ValueError('late parse failure')
        with patch.object(E,'iter_raw_file_rows',side_effect=broken):
            with self.assertRaisesRegex(ValueError,'late parse failure'):E.parse_file_bytes(self.c,'broken.csv',b'')
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM parse_sessions').fetchone()[0],count)
    def test_parser_rolls_back_failed_bulk_insert(self):
        self.c.executescript("CREATE TRIGGER fail_parse BEFORE INSERT ON parse_rows WHEN NEW.idx>=1000 BEGIN SELECT RAISE(ABORT,'test failure'); END;")
        raw=('article;name\n'+''.join(f'{i};row\n' for i in range(2000))).encode()
        with self.assertRaises(sqlite3.IntegrityError):E.parse_file_bytes(self.c,'fail.csv',raw)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM parse_sessions').fetchone()[0],0)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM parse_rows').fetchone()[0],0)
        self.assertEqual(self.c.execute('PRAGMA busy_timeout').fetchone()[0],5000)
    def test_export_snapshot_released_before_download_and_no_full_xml_builder(self):
        rows=[dict(article=f'{i:06}',name='=TEXT()',custom={'arr':['я','b']},netProfit=999) for i in range(2100)]
        self.seed(rows);cols=[dict(key='article',name='Артикул'),dict(key='name',name='Name'),dict(key='arr',name='Array',custom=True)]
        original=E._xlsx_from_rows
        def envelope(headers,values,*args,**kwargs):
            self.assertEqual(headers,[]);self.assertEqual(values,[])
            return original(headers,values,*args,**kwargs)
        with patch.object(E,'_xlsx_from_rows',side_effect=envelope):
            output=E.export_data_only_file(self.c,cols,'xlsx')
        try:
            self.assertFalse(self.c.in_transaction)
            self.seed([dict(article='NEW')])
            with zipfile.ZipFile(output) as z:
                xml=z.read('xl/worksheets/sheet1.xml').decode()
                self.assertEqual(xml.count('<row '),2101);self.assertIn('000000',xml);self.assertNotIn('<f>',xml);self.assertNotIn('NEW',xml)
        finally:output.close()
    def test_range_pages_http_and_streamed_export(self):
        import urllib.request
        from http.server import ThreadingHTTPServer
        r=E.parse_file_bytes(self.c,'rows.csv',('article;name\n'+''.join(f'{i:06};n\n' for i in range(5003))).encode())
        self.seed([dict(article='001',name='=CMD()')]);cols=[dict(key='article',name='Article'),dict(key='name',name='Name')]
        srv=ThreadingHTTPServer(('127.0.0.1',0),E.Handler);thread=threading.Thread(target=srv.serve_forever,daemon=True)
        def get(path,body=None):
            request=urllib.request.Request('http://127.0.0.1:'+str(srv.server_port)+path,data=None if body is None else json.dumps(body).encode(),headers={'X-UC-Token':'test','Content-Type':'application/json'})
            return urllib.request.urlopen(request,timeout=10)
        with patch.object(E,'get_token',return_value='test'):
            thread.start()
            try:
                for off,expected in [(0,5000),(5000,3),(5003,0)]:
                    with get('/parse/rows?parse_id='+r['parse_id']+'&offset='+str(off)+'&limit=5000') as response:
                        page=json.load(response);self.assertEqual(len(page['rows']),expected)
                        if expected:self.assertEqual(page['rows'][0]['article'],f'{off:06}')
                with get('/export/data-only.csv',{'columns':cols}) as response:
                    raw=response.read();self.assertEqual(int(response.headers['Content-Length']),len(raw));self.assertIsNone(response.headers.get('Content-Encoding'))
                    table=list(csv.reader(io.StringIO(raw.decode('utf-8-sig')),delimiter=';'));self.assertEqual(table[1],['001',"'=CMD()"])
            finally:srv.shutdown();srv.server_close();thread.join(5)
