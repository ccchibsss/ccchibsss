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

    def test_indexed_read_only_decodes_requested_neighborhood(self):
        n=10000
        token=self.call('begin',total=n+2)['token']
        for part,offset in enumerate(range(0,n,1000)):
            self.call('chunk',token=token,part=part,field='parts',items=[[f'P{i}|B',{'name':f'name {i}'}] for i in range(offset,min(offset+1000,n))])
        self.call('chunk',token=token,part=10,field='byArt',items=[['P1|B',['OE']]])
        self.call('chunk',token=token,part=11,field='byOe',items=[['OE',['P1|B','P2|B']]])
        self.call('commit',token=token)
        loads=E.json.loads
        with patch.object(E.json,'loads',wraps=loads) as decode:
            graph=E._read_hvc_chunked_reference(self.c,token,[{'article':'P1','brand':'B'}])
        self.assertEqual(set(graph['parts']),{'P1|B','P2|B'})
        self.assertLess(decode.call_count,10)
        self.call('release',token=token)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM hvc_ref_entries').fetchone()[0],0)
    def test_upload_concurrency(self):
        subprocess.check_call(['node',str(pathlib.Path(__file__).resolve().parents[2]/'tests/hvc-upload-concurrency-client.js')])
    def test_legacy_chunk_reference_still_readable(self):
        token=self.call('begin',total=1)['token']
        self.c.execute('DELETE FROM hvc_ref_indexed WHERE id=?',(token,));self.c.commit()
        self.call('chunk',token=token,part=0,field='parts',items=[['A|B',{'name':'legacy'}]])
        self.call('commit',token=token)
        graph=E._read_hvc_chunked_reference(self.c,token,[{'article':'A','brand':'B'}])
        self.assertEqual(graph['parts'][0][1]['name'],'legacy')

    def test_indexed_subset_parity_for_connected_graph(self):
        ref={field:[] for field in E._HVC_REFERENCE_FIELDS}
        ref['groupSeparator']=' ; '
        rows=[]
        for i in range(80):
            key=f'P{i}|B';oe=f'OE{i%7}'
            ref['parts'].append([key,{'artikul':f'P{i}','brand':'B','name':f'donor {i}','category':f'cat {i%3}',
                '_dimensionEvidence':{'weight':1+i/100,'length':10,'width':10,'height':10}}])
            ref['byArt'].append([key,[oe]])
            rows.append({'article':f'P{i}','brand':'B','name':'','oe_norm':oe})
        ref['byOe']=[[f'OE{g}',[f'P{i}|B' for i in range(80) if i%7==g]] for g in range(7)]
        ref['oe']=[[f'OE{g}',{'name':f'OE donor {g}'}] for g in range(7)]
        ref['unsafeKeys']=['P0|B','P13|B'];ref['unsafeOe']=['OE3']
        token=self.call('begin',total=sum(len(ref[k]) for k in E._HVC_REFERENCE_FIELDS),groupSeparator=ref['groupSeparator'])['token']
        for part,field in enumerate(E._HVC_REFERENCE_FIELDS):self.call('chunk',token=token,part=part,field=field,items=ref[field])
        self.call('commit',token=token)
        for mode in ['auto','artbrand','oe']:
            for offset in range(0,len(rows),17):
                batch=rows[offset:offset+17]
                with patch.object(E.time,'strftime',return_value='2026-01-01T00:00:00Z'):
                    full=E.enrich_hvc_input_rows(self.c,batch,ref,mode)
                    indexed=E.enrich_hvc_input_rows(self.c,batch,mode=mode,reference_id=token)
                self.assertEqual(full['rows'],indexed['rows'])


del ImportExportAudit
