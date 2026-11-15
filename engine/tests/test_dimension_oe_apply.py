import copy,json,pathlib,sqlite3,subprocess,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from dimension_oe_search import OeSearch
from dimension_oe_apply import apply_choices
from dimension_quarantine import compact

class OeApplyParity(unittest.TestCase):
    def test_actual_browser_oe_apply(self):
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/dimension-quarantine-reference.js'
        target=dict(article='A',brand='B',category='C',weight=1000,length=10,width=10,height=10,dimensionAnomalyBlocked=True,oe_numbers='OE123')
        donor=dict(article='D',brand='B',category='C',weight=1,length=10,width=10,height=10,oe_numbers='OE123',
                   _dimensionAutoEvidence=dict(weight=1,length=10,width=10,height=10,file='f',row=1,identity='D|B'))
        part=dict(artikul='H',brand='B',oe_numbers='OE123',_dimensionEvidence=dict(weight=2,length=10,width=10,height=10,
            file='f',singleRow=True,identity='H|B',oeCodes=['OE123']))
        scenarios=[([target,donor],dict(byOe=[['OE123',['D|B']]])),
            ([target],dict(parts=[['H|B',part]],byOe=[['OE123',['H|B']]],cross=[['OE123\x1fH|B',{'oeNorm':'OE123'}]])),
            ([{**target,'_volumeExplicit':True,'volume':2},donor],dict(byOe=[['OE123',['D|B']]])),
            ([{**target,'_dimensionOeReview':{'source':'prev','history':[{'n':i} for i in range(24)]}},donor],dict(byOe=[['OE123',['D|B']]])),
            ([{**target,'oe_numbers':''},{**donor,'article':'A','oe_numbers':'','_dimensionAutoEvidence':{**donor['_dimensionAutoEvidence'],'identity':'A|B'}}],{})]
        labels={'weight':'Вес','length':'Длина','width':'Ширина','height':'Высота'}
        for rows,reference in scenarios:
            for automatic in (False,True):
                if automatic and rows[0].get('_dimensionOeReview'):continue
                expected=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps(dict(operation='oeApply',rows=rows,reference=reference,targets=[0],automatic=automatic,limits=[],labels=labels)),text=True))
                search=OeSearch(rows,reference,[],labels=labels);proposals=search.find([0],automatic)
                selected=[i for i,x in enumerate(proposals) if x['choice']]
                updates=apply_choices(search,proposals,selected,automatic,'2026-11-08T00:00:00Z')
                for u in updates:search.rows[u['targetIndex']]=u['row']
                actual=dict(rows=search.rows,log=[u['log'] for u in updates])
                with self.subTest(reference=reference,automatic=automatic):self.assertEqual(json.loads(compact(actual)),expected)

    def test_api_snapshot_guards_and_atomicity(self):
        from uc_engine import dimension_oe_operation
        conn=sqlite3.connect(':memory:')
        conn.executescript("CREATE TABLE products(article TEXT,brand TEXT,weight REAL,length REAL,width REAL,height REAL,volume REAL);INSERT INTO products VALUES('A','B',1000,10,10,10,1);")
        target=dict(article='A',brand='B',weight=1000,length=10,width=10,height=10,oe_numbers='OE123',dimensionAnomalyBlocked=True)
        donor=dict(article='D',brand='B',weight=1,length=10,width=10,height=10,oe_numbers='OE123')
        snap=dict(rows=[target,donor],reference={'byOe':[['OE123',['D|B']]]},found=[{'index':0,'selected':False}],automatic=False,limits=[],catalog_revision=1,hvc_revision=2)
        preview=dimension_oe_operation(conn,snap)
        token=preview['token'];self.assertIsNotNone(preview['preview'][0]['choice'])
        for changed in ({**snap,'catalog_revision':2},{**snap,'rows':[target,{**donor,'weight':2}]}):
            with self.assertRaises(ValueError):dimension_oe_operation(conn,changed,'apply',token,[0])
        with self.assertRaises(ValueError):dimension_oe_operation(conn,snap,'apply',token,[0,0])
        self.assertEqual(conn.execute('SELECT weight FROM products').fetchone()[0],1000)
        result=dimension_oe_operation(conn,snap,'apply',token,[0])
        self.assertEqual(result['summary']['changed'],1)
        self.assertEqual(conn.execute('SELECT weight FROM products').fetchone()[0],1)
        self.assertIn('_dimensionOeReview',result['rows'][0]['fields'])
        self.assertEqual(json.loads(conn.execute('SELECT data FROM dimension_oe_state').fetchone()[0]),result['rows'][0]['fields'])
        with self.assertRaises(ValueError):dimension_oe_operation(conn,snap,'apply',token,[0])
        expired=dimension_oe_operation(conn,snap)['token']
        conn.execute('UPDATE dimension_oe_preview SET created=0 WHERE token=?',(expired,));conn.commit()
        with self.assertRaises(ValueError):dimension_oe_operation(conn,snap,'apply',expired,[0])
        conn.close()

    def test_sql_client_find_apply_routes(self):
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/dimension-oe-client.js'
        subprocess.check_call(['node',str(path)])

    def test_revalidation_and_pending_automatic(self):
        from uc_engine import dimension_oe_operation
        target=dict(article='A',brand='B',weight=1000,length=10,width=10,height=10,dimensionAnomalyBlocked=True,oe_numbers='OE123')
        part=dict(artikul='H',brand='B',oe_numbers='OE123',_dimensionEvidence=dict(weight=1,length=10,width=10,height=10,
            singleRow=True,file='f',identity='H|B',oeCodes=['OE123']))
        ref=dict(parts=[['H|B',part]],byOe=[['OE123',['H|B']]])
        search=OeSearch([target],ref,[]);preview=search.find([0],True)
        self.assertIsNotNone(preview[0]['choice'])
        with self.assertRaises(ValueError):apply_choices(search,preview,[0],True,'now') # missing live cross link
        ref['cross']=[['OE123\x1fH|B',{'oeNorm':'WRONG'}]]
        search=OeSearch([target],ref,[]);preview=search.find([0],True)
        with self.assertRaises(ValueError):apply_choices(search,preview,[0],True,'now')
        ref['cross']=[['OE123\x1fH|B',{'oeNorm':'OE123'}]]
        search=OeSearch([target],ref,[]);preview=search.find([0],True)
        self.assertEqual(len(apply_choices(search,preview,[0],True,'now')),1)
        conn=sqlite3.connect(':memory:')
        snap=dict(rows=[target,{**target,'article':'P','_dimensionOeReview':{}}],reference=ref,found=[{'index':0},{'index':1}],automatic=True,limits=[])
        result=dimension_oe_operation(conn,snap)
        self.assertEqual(result['summary']['pending'],1)
        self.assertEqual(result['summary']['checked'],1)
        # A missing or repeated found index is rejected before state is persisted.
        for found in ([{'index':-1}],[{'index':0},{'index':0}]):
            with self.assertRaises(ValueError):dimension_oe_operation(conn,{**snap,'found':found})
        conn.close()
