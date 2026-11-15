import json,pathlib,shutil,subprocess,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine  # Registers the internal modules stored in the single engine file.
from category_kind import CategoryKind

class CategoryKindParity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_browser_apply_lifecycle(self):
        rows=[['Фильтры','Фильтр масляный','1111111111'],['Топливо','Насос топливный','2222222222']]
        marker=dict(version='csv-kind-name-v1|test-v1',name='Фильтр масляный',brand='B',category='Фильтры',referenceCategory='Фильтры',type='Фильтр масляный',categoryMode='explicit',categoryMethod='',categoryRevision='',confirmed=False)
        products=[{'name':'Фильтр масляный','brand':'B'},
                  {'name':'Фильтр масляный','category':'Custom'},
                  {'name':'Фильтр масляный','category':'Топливо'},
                  {'name':'Фильтр масляный','category':'Без категории','_categoryNameExplicit':True},
                  {'name':'Фильтр масляный','category_type':'Ручной'},
                  {'name':'Фильтр масляный','_categoryTypeCleared':True},
                  {'name':'Фильтр масляный','category_type':'A','custom':{'Вид категории':'B'}},
                  {'name':'Фильтр масляный','_categoryKindAuto':{'version':'foreign'}},
                  {'name':'Фильтр масляный','_sources':'{"name":{"file":"import"}}'}]
        for name in ('Фильтр масляный','Насос топливный','Unknown'):
            for confirmed in (True,False):
                products.append({'name':name,'brand':'B','category':'Фильтры','category_type':'Фильтр масляный','_categoryKindAuto':{**marker,'confirmed':confirmed}})
        products.append({'name':'Фильтр масляный','category_type':'edited','_categoryKindAuto':marker})
        products += [
            {'name':'Unknown','brand':'B','category':'Фильтры','category_type':'Фильтр масляный',
             '_categoryKindAuto':{**marker,'categoryMode':'csv_auto'},
             '_categoryNameAutoValue':'Фильтры','_categoryNameMethod':'csv_kind',
             '_sources':{'category_type':{'file':'по названию: Категории12131.csv'},'name':{'file':'price'}}},
            {'name':'Фильтр масляный','brand':'B','category':'Топливо','category_type':'Фильтр масляный',
             '_categoryKindAuto':{**marker,'confirmed':True}},
            {'name':'Фильтр масляный','category':'Фильтры','_categoryNameAutoValue':'Фильтры',
             '_categoryNameMethod':'enrich','_categoryNameRevision':'rule-v1'}]
        root=pathlib.Path(__file__).resolve().parents[2]
        for enabled in (True,False):
            expected=json.loads(subprocess.check_output(['node',str(root/'tests/category-kind-reference.js')],input=json.dumps(dict(rows=rows,products=products,enabled=enabled)),text=True))
            model=CategoryKind(rows,'test-v1')
            actual=[model.apply(p,{'version':'ctx'},enabled,lambda *args:False,'2026-01-01T00:00:00Z') for p in products]
            for p,a,e in zip(products,actual,expected):
                with self.subTest(enabled=enabled,row=p): self.assertEqual(a,e)

    def test_server_result_and_state_persisted(self):
        import sqlite3
        import uc_engine as E
        conn=sqlite3.connect(':memory:')
        conn.executescript("CREATE TABLE products(article TEXT,brand TEXT,category TEXT,category_type TEXT);"
                           "INSERT INTO products VALUES('A','B','','');")
        ref={'rows':[['Фильтры','Фильтр масляный','1111111111']],'revision':'test-v1','base_categories':['Топливо']}
        p={'article':'A','brand':'B','name':'Фильтр масляный','_categoryExplicitSource':False}
        result=E.enrich_category_kinds(conn,[p],ref,{'version':'ctx'},True)['rows'][0]
        self.assertEqual(result['fields']['category_type'],'Фильтр масляный')
        self.assertNotIn('_categoryExplicitSource',result['fields'])
        stored=json.loads(conn.execute('SELECT data FROM category_kind_state').fetchone()[0])
        self.assertEqual(stored,result['fields'])
        self.assertEqual(conn.execute('SELECT category,category_type FROM products').fetchone(),('Фильтры','Фильтр масляный'))
        confirmed=E.enrich_category_kinds(conn,[{**p,**result['fields']}],ref,{'version':'ctx'},True,'confirm',True)['rows'][0]
        self.assertTrue(confirmed['changed'])
        self.assertTrue(confirmed['fields']['_categoryKindAuto']['confirmed'])
        saved=json.loads(conn.execute('SELECT data FROM category_kind_state').fetchone()[0])
        self.assertEqual(saved['_categoryKindAuto']['categoryMode'],'explicit')
        with self.assertRaises(ValueError): E.enrich_category_kinds(conn,[p],ref,{},True,'unknown')
        next_row={**p,**result['fields'],'category':'Топливо'}
        response=E.enrich_category_kinds(conn,[next_row],ref,{'version':'ctx'},True)['rows'][0]
        self.assertIn('category_type',response['removed'])
        self.assertNotIn('_categoryKindAuto',response['fields'])
        conn.close()

    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_confirm_import_hydrate_cloud(self):
        rows=[['Фильтры','Фильтр масляный','1111111111']]
        model=CategoryKind(rows,'test-v1')
        marker=dict(version=model.version,name='Фильтр масляный',brand='B',category='Фильтры',referenceCategory='Фильтры',type='Фильтр масляный',categoryMode='csv_auto',categoryMethod='csv_kind',categoryRevision='ctx',confirmed=False)
        base={'article':'A','name':'Фильтр масляный','brand':'B','category':'Фильтры','category_type':'Фильтр масляный','_categoryKindAuto':marker,'_sources':{}}
        products=[base,{**base,'name':'Changed'},{**base,'category_type':'edited'},
                  {**base,'category_type':''},{**base,'_categoryKindAuto':{**marker,'confirmed':True}},
                  {**base,'_categoryKindAuto':{**marker,'version':'foreign'}},
                  {**base,'_categoryKindAuto':None}]
        root=pathlib.Path(__file__).resolve().parents[2]
        for operation in ('confirm','hydrate','explicit_import','cloud'):
            for category_confirmed in (False,True):
                expected=json.loads(subprocess.check_output(['node',str(root/'tests/category-kind-reference.js')],input=json.dumps(dict(rows=rows,products=products,operation=operation,categoryConfirmed=category_confirmed)),text=True))
                actual=[]
                for p in products:
                    row=p;changed=marker_out=error=None
                    if operation=='confirm': row,changed=model.confirm(p,category_confirmed,'2026-01-01T00:00:00Z')
                    elif operation=='hydrate': row=model.hydrate(p,p.get('_categoryKindAuto'))
                    elif operation=='explicit_import': row=model.explicit_import(p,p.get('category_type'),p['_sources'].get('category_type'))
                    else:
                        try: marker_out=model.marker_for_cloud(p)
                        except ValueError as exc: error=str(exc)
                    actual.append(dict(row=row,changed=changed,marker=marker_out,error=error))
                with self.subTest(operation=operation,category_confirmed=category_confirmed): self.assertEqual(actual,expected)

    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_real_client_confirm_transport(self):
        root=pathlib.Path(__file__).resolve().parents[2]
        subprocess.check_call(['node',str(root/'tests/category-kind-client.js')])
