import pathlib,sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from test_import_export_audit import ImportExportAudit
import uc_engine as E

class ExactCatalogSync(unittest.TestCase):
    setUp=ImportExportAudit.setUp
    tearDown=ImportExportAudit.tearDown
    def begin(self,rows):
        token=E.sync_catalog_snapshot(self.c,{'action':'begin','total':len(rows)})['token']
        if rows:E.sync_catalog_snapshot(self.c,{'action':'chunk','token':token,'part':0,'rows':rows})
        return token
    def commit(self,token):return E.sync_catalog_snapshot(self.c,{'action':'commit','token':token})
    def test_exact_zero_empty_deleted_and_no_extra_price_history(self):
        E.import_rows(self.c,[{'article':'A','brand':'B','name':'old','price':100,'cost':50,'volume':10},{'article':'DELETED','price':5}],'seed')
        token=self.begin([{'article':'A','brand':'B','name':'','price':0,'cost':0,'volume':0}])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM products').fetchone()[0],2)
        history=self.c.execute('SELECT COUNT(*) FROM price_history').fetchone()[0]
        self.commit(token)
        self.assertEqual([tuple(r) for r in self.c.execute('SELECT article,name,price,cost,volume FROM products')],[('A','',0,0,0)])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM price_history').fetchone()[0],history)
    def test_mid_commit_failure_restores_previous_catalog_and_fts(self):
        E.import_rows(self.c,[{'article':'KEEP','price':1}],'seed')
        token=self.begin([{'article':'A','price':10}])
        with patch.object(E,'import_rows',side_effect=RuntimeError('disk error')),self.assertRaisesRegex(RuntimeError,'disk error'):
            self.commit(token)
        self.assertEqual([r[0] for r in self.c.execute('SELECT article FROM products')],['KEEP'])
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM products_fts WHERE products_fts MATCH 'KEEP'").fetchone()[0],1)
        self.commit(token)
        self.assertEqual([r[0] for r in self.c.execute('SELECT article FROM products')],['A'])
    def test_concurrent_server_edit_rejects_commit(self):
        E.import_rows(self.c,[{'article':'A','price':1}],'seed')
        token=self.begin([{'article':'A','price':2}])
        E.import_rows(self.c,[{'article':'A','price':3}],'other writer')
        with self.assertRaisesRegex(ValueError,'изменился'):self.commit(token)
        self.assertEqual(self.c.execute('SELECT price FROM products').fetchone()[0],3)
    def test_incomplete_snapshot_and_duplicate_keys_never_publish(self):
        E.import_rows(self.c,[{'article':'KEEP','price':1}],'seed')
        token=E.sync_catalog_snapshot(self.c,{'action':'begin','total':2})['token']
        E.sync_catalog_snapshot(self.c,{'action':'chunk','token':token,'part':1,'rows':[{'article':'A'}]})
        with self.assertRaisesRegex(ValueError,'Пропущена'):self.commit(token)
        token=self.begin([{'article':'A'},{'article':'A'}])
        with self.assertRaisesRegex(ValueError,'Повторный'):self.commit(token)
        self.assertEqual([r[0] for r in self.c.execute('SELECT article FROM products')],['KEEP'])
    def test_empty_snapshot_really_clears_catalog(self):
        E.import_rows(self.c,[{'article':'A','price':1}],'seed')
        self.commit(self.begin([]))
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM products').fetchone()[0],0)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM eco_results').fetchone()[0],0)

    def test_ozon_reference_replacement_removes_stale_pairs(self):
        E.import_ozon_pairs(self.c,[{'category':'old','type':'old'}])
        E.import_ozon_pairs(self.c,[{'category':'new','type':'new'}],replace=True)
        self.assertEqual([tuple(r) for r in self.c.execute('SELECT * FROM ozon_pairs')],[('new','new')])
        with self.assertRaises(ValueError):E.import_ozon_pairs(self.c,[None],replace=True)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM ozon_pairs').fetchone()[0],1)
        E.import_ozon_pairs(self.c,[],replace=True)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM ozon_pairs').fetchone()[0],0)
    def test_actual_client_paths(self):
        import subprocess
        subprocess.check_call(['node',str(pathlib.Path(__file__).resolve().parents[2]/'tests/import-export-fixes-client.js')])

    def test_http_snapshot_and_export_roundtrip(self):
        import threading,urllib.request,json,csv,io
        from http.server import ThreadingHTTPServer
        srv=ThreadingHTTPServer(('127.0.0.1',0),E.Handler)
        thread=threading.Thread(target=srv.serve_forever,daemon=True)
        def post(path,body):
            req=urllib.request.Request('http://127.0.0.1:'+str(srv.server_port)+path,
                data=json.dumps(body).encode(),headers={'X-UC-Token':'audit-token','Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=10) as response:return response.read()
        with patch.object(E,'get_token',return_value='audit-token'):
            thread.start()
            try:
                token=json.loads(post('/catalog/sync',{'action':'begin','total':1}))['token']
                post('/catalog/sync',{'action':'chunk','token':token,'part':0,'rows':[{'article':'00042','brand':'B','price':0}]})
                self.assertEqual(json.loads(post('/catalog/sync',{'action':'commit','token':token}))['total'],1)
                data=post('/export/catalog.csv',{'articles':[{'article':'00042','brand':'B'}]})
                rows=list(csv.reader(io.StringIO(data.decode('utf-8-sig')),delimiter=';'))
                self.assertEqual(rows[1][0],'00042');self.assertEqual(len(rows),2)
            finally:
                srv.shutdown();srv.server_close();thread.join(timeout=5)

    def test_sql_catalog_parser_preamble_mapping_and_format_errors(self):
        import json
        result=E.parse_file_bytes(self.c,'price.csv','Отчёт\n\nАртикул;Бренд;Extra\n0001;B;text\n'.encode(),catalog_import=True)
        self.assertEqual(result['headers'],['Артикул','Бренд','Extra'])
        row=json.loads(self.c.execute('SELECT data FROM parse_rows WHERE session=?',(result['parse_id'],)).fetchone()[0])
        self.assertEqual(row['Артикул'],'0001');self.assertEqual(row['Extra'],'text')
        with self.assertRaisesRegex(ValueError,'SQL-парсер поддерживает'):E.parse_file_bytes(self.c,'bad.ods',b'PKbad',catalog_import=True)

del ImportExportAudit
