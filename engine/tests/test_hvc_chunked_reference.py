import copy,json,pathlib,sqlite3,subprocess,sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine as E
from test_import_export_audit import ImportExportAudit

class HvcChunked(unittest.TestCase):
    setUp=ImportExportAudit.setUp
    tearDown=ImportExportAudit.tearDown
    def call(self,action,**kw):return E.hvc_reference_upload(self.c,dict(action=action,**kw))
    def test_chunked_matches_monolithic_reference_three_modes(self):
        reference={'parts':[['A|B',{'artikul':'A','brand':'B','name':'донор'}],['OTHER|B',{'artikul':'OTHER','brand':'B','category':'категория','_dimensionEvidence':{'weight':1,'length':10,'width':10,'height':10}}]],
            'oe':[['OE1',{'name':'OE donor','category':'OE category'}]],'byArt':[['A|B',['OE1']]],'byOe':[['OE1',['A|B','OTHER|B']]],
            'unsafeKeys':['BLOCK|B'],'unsafeOe':['BAD'],'groupSeparator':' ; '}
        token=self.call('begin',total=sum(len(reference[k]) for k in E._HVC_REFERENCE_FIELDS),groupSeparator=reference['groupSeparator'])['token']
        for part,field in enumerate(E._HVC_REFERENCE_FIELDS):
            self.call('chunk',token=token,part=part,field=field,items=reference[field])
        with self.assertRaisesRegex(ValueError,'не загружен полностью'):
            E.enrich_hvc_input_rows(self.c,[{'article':'A','brand':'B'}],reference_id=token)
        self.assertEqual(self.call('commit',token=token)['reference_id'],token)
        for mode in ['auto','artbrand','oe']:
            rows=[{'article':'A','brand':'B','name':'','oe_norm':'OE1'},{'article':'BLOCK','brand':'B','name':''}]
            with patch.object(E.time,'strftime',return_value='2026-01-01T00:00:00Z'):
                direct=E.enrich_hvc_input_rows(self.c,rows,reference,mode)
                chunked=E.enrich_hvc_input_rows(self.c,rows,mode=mode,reference_id=token)
            self.assertEqual(direct['rows'],chunked['rows'])
        with self.assertRaises(ValueError):self.call('chunk',token=token,part=0,field='parts',items=reference['parts'])
        self.call('release',token=token)
        with self.assertRaises(ValueError):E.enrich_hvc_input_rows(self.c,rows,reference_id=token)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM hvc_ref_chunks').fetchone()[0],0)
    def test_missing_part_and_wrong_count_never_publish(self):
        token=self.call('begin',total=2)['token']
        self.call('chunk',token=token,part=1,field='unsafeKeys',items=['A|B'])
        with self.assertRaises(ValueError):self.call('commit',token=token)
        self.call('chunk',token=token,part=0,field='unsafeKeys',items=['C|D'])
        self.call('commit',token=token)
        self.assertEqual(E._read_hvc_chunked_reference(self.c,token)['unsafeKeys'],['C|D','A|B'])
    def test_oversized_chunk_is_rejected_without_write(self):
        token=self.call('begin',total=1)['token']
        with self.assertRaisesRegex(ValueError,'больше 2 МБ'):
            self.call('chunk',token=token,part=0,field='parts',items=[['A|B',{'name':'я'*(2*1024*1024)}]])
        with self.assertRaises(ValueError):self.call('commit',token=token)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM hvc_ref_chunks').fetchone()[0],0)
    def test_actual_client_chunking_and_staging(self):
        subprocess.check_call(['node',str(pathlib.Path(__file__).resolve().parents[2]/'tests/hvc-chunked-client.js')])
    def test_http_chunked_reference_then_enrichment(self):
        import threading,urllib.request
        from http.server import ThreadingHTTPServer
        srv=ThreadingHTTPServer(('127.0.0.1',0),E.Handler)
        thread=threading.Thread(target=srv.serve_forever,daemon=True)
        def post(path,body):
            req=urllib.request.Request('http://127.0.0.1:'+str(srv.server_port)+path,data=json.dumps(body).encode(),headers={'X-UC-Token':'test-token','Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=10) as response:return json.loads(response.read())
        with patch.object(E,'get_token',return_value='test-token'):
            thread.start()
            try:
                token=post('/catalog/hvc-reference',{'action':'begin','total':1})['token']
                post('/catalog/hvc-reference',{'action':'chunk','token':token,'part':0,'field':'parts','items':[['A|B',{'name':'new name','artikul':'A','brand':'B'}]]})
                post('/catalog/hvc-reference',{'action':'commit','token':token})
                result=post('/catalog/enrich-hvc-rows',{'rows':[{'article':'A','brand':'B','name':''}],'reference_id':token})
                self.assertEqual(result['rows'][0]['fields']['name'],'new name')
                post('/catalog/hvc-reference',{'action':'release','token':token})
            finally:srv.shutdown();srv.server_close();thread.join(timeout=5)

del ImportExportAudit
