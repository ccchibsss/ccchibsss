import json,pathlib,shutil,subprocess,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from ozon_classifier import OzonClassifier

class OzonClassifierParity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_actual_browser_strict_oe_applicability(self):
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/ozon-classifier-reference.js'
        reference=json.loads(subprocess.check_output(['node',str(path)],input='[]',text=True))
        pairs=reference['pairs'];cat,typ=pairs[0];cat2,typ2=pairs[1]
        pair={'ozon_category':cat,'ozon_type':typ};other={'category':cat2,'type':typ2}
        cases=[dict(row={}),dict(row={'oe_numbers':'A-1'}),
            dict(row={'oe_numbers':'A-1'},registry={'oe':{}}),
            dict(row={'oe_numbers':'A-1'},registry={'oe':{'A1':pair}}),
            dict(row={'oe_numbers':'A-1 / B2'},registry={'oe':{'A1':pair,'B2':other}}),
            dict(row={'oe_numbers':'A1 / B2'},registry={'oe':{'A1':pair,'B2':pair}}),
            dict(row={'oe_numbers':'A1'},registry={'oe':{'A1':{'ozon':pair}}}),
            dict(row={'oe_numbers':'A1'},registry={'oe':{'A1':{'ozon':{'ozon_type':'bad'},**pair}}}),
            dict(row={'oe_numbers':'A1'},registry={'oe':{'A1':{'ozon_conflict':True,**pair}}}),
            dict(row={'oe_numbers':'A1'},registry={'oe':{'A1':{'category':'wrong','type':typ}}}),
            dict(row={'oe_numbers':'A1'},registry={'oe':{'A1':{'applicability':'Car'}}},applicability={'car':pair}),
            dict(row={'oe_numbers':'A1','applicability':'Car'},registry={'oe':{'A1':{}}},applicability={'A1|car':pair}),
            dict(row={'oe_numbers':'A1'},registry={'oe':{'A1':{'applicability':['Car','Truck']}}},applicability={'car':pair,'truck':other}),
            dict(row={'oe_numbers':'A1'},registry={'oe':{'A1':{'applicability':'Car','ozonByApplicability':{'car':pair}}}},applicability={'car':other}),
            dict(row={'oe_numbers':'A1'},registry={'oe':{'A1':{'applicability':'Car'}}},applicability={'car':{'ozon_type':'bad'}}),
            dict(row={'oe_numbers':['A-1','A1'],'oe_list':'B2'},registry={'oe':{'a-1':pair}})]
        result=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps(cases),text=True))
        model=OzonClassifier(pairs)
        for case,expected in zip(cases,result['results']):
            with self.subTest(case=case): self.assertEqual(model.classify(case['row'],case.get('registry'),case.get('applicability')),expected)

    def test_classifier_route_function_persists_reference(self):
        import sqlite3
        from uc_engine import classify_ozon_rows
        conn=sqlite3.connect(':memory:')
        ref={'pairs':[['Category','Type']],'registry':{'oe':{'A1':{'category':'Category','type':'Type'}}}}
        result=classify_ozon_rows(conn,[{'article':'SKU','brand':'B','oe_numbers':'A1'}],ref)
        self.assertEqual(result['rows'][0]['result']['source'],'auto')
        self.assertEqual(json.loads(conn.execute('SELECT data FROM ozon_classification_reference').fetchone()[0]),ref)
        conn.close()

    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_apply_preserves_manual_import_and_updates_provenance(self):
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/ozon-classifier-reference.js'
        ref=json.loads(subprocess.check_output(['node',str(path)],input='[]',text=True))
        cat,typ=ref['pairs'][0];registry={'revision':3,'oe':{'A1':{'category':cat,'type':typ}}}
        cases=[{'row':{'oe_numbers':'A1'},'registry':registry},
               {'row':{'oe_numbers':'A1','ozon_category':'Manual','ozon_type':'Chosen','ozon_type_src':'manual'},'registry':registry},
               {'row':{'oe_numbers':'A1','ozon_category':'Imported','ozon_type':'Chosen'},'registry':registry},
               {'row':{'oe_numbers':'A1','ozon_category':'Old','ozon_type':'Old','ozon_type_src':'keyword'},'registry':registry},
               {'row':{'oe_numbers':'Unknown','ozon_type':'Stale','ozon_type_src':'auto'},'registry':registry},
               {'row':{'oe_numbers':'A1','ozon_category':'Old','ozon_type':'Old'},'registry':registry,'force':True},
               {'row':{},'registry':registry}]
        result=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps(dict(operation='apply',cases=cases)),text=True))
        model=OzonClassifier(ref['pairs'])
        for case,want in zip(cases,result['results']):
            row,value=model.apply(case['row'],case.get('registry'),force=case.get('force',False))
            with self.subTest(case=case): self.assertEqual({'row':row,'result':value},want)

    def test_strict_apply_sql_persistence(self):
        import sqlite3
        from uc_engine import classify_ozon_rows
        conn=sqlite3.connect(':memory:')
        conn.executescript("CREATE TABLE products(article TEXT,brand TEXT,ozon_category TEXT,ozon_type TEXT);INSERT INTO products VALUES('SKU','B','','');")
        ref={'pairs':[['Category','Type']],'registry':{'oe':{'A1':{'category':'Category','type':'Type'}}}}
        row={'article':'SKU','brand':'B','oe_numbers':'A1'}
        output=classify_ozon_rows(conn,[row],ref,'apply_strict')['rows'][0]
        self.assertEqual(output['fields']['ozon_type_src'],'auto')
        self.assertEqual(conn.execute('SELECT ozon_category,ozon_type FROM products').fetchone(),('Category','Type'))
        self.assertEqual(json.loads(conn.execute('SELECT data FROM ozon_classification_state').fetchone()[0]),output['fields'])
        manual={**row,'ozon_category':'Manual','ozon_type':'ManualType','ozon_type_src':'manual'}
        output=classify_ozon_rows(conn,[manual],ref,'apply_strict',True)['rows'][0]
        self.assertEqual(output['fields']['ozon_type'],'ManualType')
        with self.assertRaises(ValueError): classify_ozon_rows(conn,[row],ref,'invalid')
        conn.close()
