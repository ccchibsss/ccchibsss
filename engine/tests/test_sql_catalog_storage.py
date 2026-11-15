import json,pathlib,sqlite3,subprocess,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine as E

class SqlCatalogStorage(unittest.TestCase):
    def setUp(self):self.c=sqlite3.connect(':memory:')
    def tearDown(self):self.c.close()
    def call(self,action,**body):return E.app_catalog_state(self.c,action,body)
    def begin(self,rows,base=''):
        t=self.call('begin',base=base,total=len(rows),metadata={'rows':{'custom':['x']},'special_values':[]})['token']
        if rows:self.call('chunk',token=t,part=0,chunk={'rows':rows,'special_values':[]})
        return t
    def test_publish_reload_and_conflict(self):
        first=self.begin([{'article':'A','custom':{'a':1},'_sources':{'name':'import'}}])
        self.assertFalse(self.call('read')['exists'])
        rev=self.call('commit',token=first)['revision']
        self.assertEqual(self.call('read')['chunk']['rows'][0]['custom'],{'a':1})
        left=self.begin([{'article':'B'}],rev);right=self.begin([{'article':'C'}],rev)
        self.call('commit',token=left)
        with self.assertRaises(ValueError):self.call('commit',token=right)
        with self.assertRaises(ValueError):self.call('read',revision=rev)
        self.assertEqual(self.call('read')['chunk']['rows'][0]['article'],'B')
    def test_incomplete_upload_and_empty_catalog(self):
        t=self.call('begin',base='',total=2,metadata={})['token']
        self.call('chunk',token=t,part=1,chunk={'rows':[{}],'special_values':[]})
        with self.assertRaises(ValueError):self.call('commit',token=t)
        self.assertFalse(self.call('read')['exists'])
        empty=self.begin([]);self.call('commit',token=empty)
        self.assertTrue(self.call('read')['exists']);self.assertEqual(self.call('read')['total'],0)
    def test_types_are_retained(self):
        rows,types=E.encode_special([{'article':'A','value':float('inf')}])
        t=self.begin([])
        # Start a separate correctly sized upload.
        t=self.call('begin',base='',total=1,metadata={})['token']
        self.call('chunk',token=t,part=0,chunk={'rows':rows,'special_values':types})
        self.call('commit',token=t)
        page=self.call('read');restored=E.decode_special(page['chunk']['rows'],page['chunk']['special_values'])
        self.assertEqual(restored[0]['value'],float('inf'));json.dumps(page,allow_nan=False)
    def test_actual_client_storage_routing(self):
        subprocess.check_call(['node',str(pathlib.Path(__file__).resolve().parents[2]/'tests/sql-catalog-storage-client.js')])
    def test_commit_does_not_decode_uploaded_row_json(self):
        from unittest.mock import patch
        t=self.begin([{'article':str(i),'custom':{'x':'test'}} for i in range(1000)])
        with patch.object(E.json,'loads',side_effect=AssertionError('Commit reparsed row JSON')):
            self.call('commit',token=t)
        self.assertEqual(self.call('read')['total'],1000)

    def test_legacy_incomplete_upload_can_still_be_committed(self):
        t=self.begin([{'article':'old'}])
        self.c.execute('DELETE FROM app_catalog_chunk_sizes');self.c.commit()
        self.call('commit',token=t)
        self.assertEqual(self.call('read')['chunk']['rows'][0]['article'],'old')
