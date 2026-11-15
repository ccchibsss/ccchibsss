import copy,json,pathlib,subprocess,sys,threading,unittest,urllib.request
from unittest.mock import patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine as E
from test_import_export_audit import ImportExportAudit

class OzonReferenceUpload(unittest.TestCase):
    setUp=ImportExportAudit.setUp
    tearDown=ImportExportAudit.tearDown
    def reference(self):
        return dict(pairs=[['Автофильтры','Фильтр масляный']],category_rows=[['Фильтры','Фильтр масляный','1234567890']],category_revision='test',identity={'rows':[{'article':'BAD','brand':'B'}],'parts':[['BAD|B',{'artikul':'WRONG'}]],'byArt':[['BAD|B',['OE1']]]})
    def upload(self,ref):
        text=json.dumps(ref,ensure_ascii=False);token=E.ozon_reference_upload(self.c,{'action':'begin','total':len(text.encode('utf-16-le'))//2})['token']
        E.ozon_reference_upload(self.c,dict(action='chunk',token=token,part=0,data=text))
        E.ozon_reference_upload(self.c,dict(action='commit',token=token))
        return token
    def test_parity_global_identity_cache_reload_release(self):
        ref=self.reference();ref['note']='😀';token=self.upload(ref)
        rows=[dict(article='A',brand='B',name='Фильтр масляный',category='Фильтры'),dict(article='OTHER',brand='B',name='Фильтр масляный',oe_numbers='OE1')]
        expected=E.enrich_ozon_preferred(self.c,rows,ref)
        actual=E.enrich_ozon_preferred(self.c,rows,reference_id=token)
        self.assertEqual(expected,actual)
        self.assertEqual(actual['rows'][1]['fields'],{})
        prepared=E._OZON_REFERENCE_CACHE[token][1]
        E.enrich_ozon_preferred(self.c,rows,reference_id=token)
        self.assertIs(E._OZON_REFERENCE_CACHE[token][1],prepared)
        E._OZON_REFERENCE_CACHE.clear()
        self.assertEqual(expected,E.enrich_ozon_preferred(self.c,rows,reference_id=token))
        E.ozon_reference_upload(self.c,dict(action='release',token=token))
        with self.assertRaises(ValueError):E.enrich_ozon_preferred(self.c,rows,reference_id=token)
    def test_incomplete_and_sealed_upload(self):
        token=E.ozon_reference_upload(self.c,dict(action='begin',total=99))['token']
        E.ozon_reference_upload(self.c,dict(action='chunk',token=token,part=1,data='{}'))
        with self.assertRaises(ValueError):E.ozon_reference_upload(self.c,dict(action='commit',token=token))
        with self.assertRaises(ValueError):E.enrich_ozon_preferred(self.c,[],reference_id=token)
        token=self.upload(self.reference())
        with self.assertRaises(ValueError):E.ozon_reference_upload(self.c,dict(action='chunk',token=token,part=0,data='{}'))
    def test_client(self):
        subprocess.check_call(['node',str(pathlib.Path(__file__).resolve().parents[2]/'tests/ozon-reference-upload-client.js')])
    def test_http(self):
        srv=ThreadingHTTPServer(('127.0.0.1',0),E.Handler);thread=threading.Thread(target=srv.serve_forever,daemon=True)
        def post(path,body):
            req=urllib.request.Request('http://127.0.0.1:'+str(srv.server_port)+path,data=json.dumps(body).encode(),headers={'X-UC-Token':'test-token','Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=10) as r:return json.loads(r.read())
        with patch.object(E,'get_token',return_value='test-token'):
            thread.start()
            try:
                text=json.dumps(self.reference());token=post('/catalog/ozon-reference',dict(action='begin',total=len(text)))['token']
                post('/catalog/ozon-reference',dict(action='chunk',token=token,part=0,data=text))
                post('/catalog/ozon-reference',dict(action='commit',token=token))
                self.assertEqual(post('/catalog/enrich-ozon-preferred',dict(reference_id=token,rows=[dict(article='A',brand='B')]))['rows'][0]['article'],'A')
                post('/catalog/ozon-reference',dict(action='release',token=token))
            finally:srv.shutdown();srv.server_close();thread.join(5)
