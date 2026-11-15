import json
import pathlib
import shutil
import subprocess
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine  # Registers the internal modules stored in the single engine file.
from category_tnved import CategoryTnved

class CategoryTnvedParity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node executes browser reference')
    def test_actual_browser_apply(self):
        reference={'rows':[['Фильтры','Масляный','8421230000'],['Фильтры','Воздушный','8421310000'],
                           ['Conflict','Kind','1111111111'],['Conflict','Kind','2222222222']],
                   'revision':'test-v1','source':'Категории12131.csv'}
        marker={'revision':'test-v1','categoryKey':'фильтры','typeKey':'масляный','code':'8421230000'}
        base={'category':'Фильтры','category_type':'Масляный'}
        rows=[base, {**base,'tnved':'manual'}, {**base,'custom':{'ТН ВЭД':'imported'}},
              {**base,'custom':{'Вид категории':'Воздушный'}}, {**base,'_tnvedNoAutofill':True},
              {**base,'_categoryTypeCleared':True,'category_type':''},
              {'category':'Conflict','category_type':'Kind'},
              {**base,'_sources':'{"name":{"file":"price"}}'},
              {**base,'tnved':'8421230000','_categoryTnvedAuto':marker},
              {**base,'category_type':'Воздушный','tnved':'8421230000','_categoryTnvedAuto':marker,
               '_sources':{'tnved':{'file':'справочник: Категории12131.csv'},'name':{'file':'price'}}},
              {**base,'tnved':'8421230000','_categoryTnvedAuto':{**marker,'revision':'foreign'}},
              {**base,'tnved':'edited','_categoryTnvedAuto':marker}]
        kind={'version':'csv-kind-name-v1|test-v1','name':'Filter','brand':'B','category':'Other',
              'referenceCategory':'Фильтры','type':'Масляный','categoryMode':'name_auto',
              'categoryMethod':'dictionary','categoryRevision':'r','confirmed':False}
        rows += [
            {'name':'Filter','brand':'B','category':'Other','category_type':'Масляный','_categoryKindAuto':kind},
            {'name':'Changed','brand':'B','category':'Other','category_type':'Масляный','_categoryKindAuto':kind},
            {'name':'Changed','brand':'B','category':'Other','category_type':'Масляный','_categoryKindAuto':kind,
             'tnved':'8421230000','_categoryTnvedAuto':marker},
            {'name':'Changed','brand':'B','category':'Other','category_type':'Масляный',
             '_categoryKindAuto':{**kind,'confirmed':True}}]
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/category-tnved-reference.js'
        for enabled in (True,False):
            expected=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps({'rows':rows,'reference':reference,'enabled':enabled}),text=True))
            model=CategoryTnved(reference['rows'],reference['revision'],reference['source'])
            actual=[dict(zip(('row','result'),model.apply(p,enabled,'2026-01-01T00:00:00Z'))) for p in rows]
            self.assertEqual(actual,expected)

    def test_browser_numeric_codes_and_nonstring_inputs(self):
        reference={'rows':[['Фильтры','Масляный','8421230000']],'revision':'test','source':'test.csv'}
        values=[0,False,True,8421230000.0,1e21,[],[1],{},None,'']
        rows=[]
        for v in values:
            for field in ['tnved','category_type','category']:
                rows.append({'category':'Фильтры','category_type':'Масляный',field:v})
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/category-tnved-reference.js'
        expected=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps({'rows':rows,'reference':reference}),text=True))
        model=CategoryTnved(reference['rows'],reference['revision'],reference['source'])
        for i,p in enumerate(rows):
            with self.subTest(row=p):
                actual=dict(zip(('row','result'),model.apply(p,True,'2026-01-01T00:00:00Z')))
                self.assertEqual(actual,expected[i])
