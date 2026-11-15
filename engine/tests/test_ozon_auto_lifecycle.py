import copy
import json
import pathlib
import shutil
import subprocess
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine  # Registers the internal modules stored in the single engine file.
from ozon_classifier import OzonClassifier
from ozon_auto import apply_preferred


class OzonAutoLifecycle(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node required')
    def test_actual_browser_lifecycle(self):
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/ozon-auto-lifecycle.js'
        def js(cases):
            return json.loads(subprocess.check_output(['node',str(path)],input=json.dumps(cases),text=True))
        pairs=json.loads(subprocess.check_output(['node',str(path.parent/'ozon-classifier-reference.js')],input='[]',text=True))['pairs']
        cat,typ=pairs[0]
        cases=[]
        details=[{'status':'none'}, {'status':'ambiguous','choices':['A','B'],'reason':'Choose'},
                 {'status':'category_ambiguous','suggestedType':'Type','choices':['C1','C2']},
                 {'status':'auto','match':{'cat':'C','type':'T','score':4}},
                 {'status':'auto','basis':'category_dictionary','match':{'cat':'C','type':'T','score':5,'catId':12,'typeId':34}}]
        old={'name':'Name','brand':'B','ozon_category':'OldC','ozon_type':'OldT','ozon_type_src':'keyword',
             '_ozonNameSourceName':'Name','_ozonNameSourceBrand':'B','_ozonNameVersion':'v1',
             '_ozonNameCategorySignature':'sig','_ozonNameStatus':'auto',
             'ozon_description_category_id':7,'ozon_type_id':8}
        for d in details:
            for row in ({},old,{**old,'name':'New'},{**old,'_ozonNameStatus':'stale'}):
                for enabled in (False,True):
                    cases.append(dict(row=copy.deepcopy(row),detail=d,enabled=enabled))
        for source in ('manual','import',''):
            cases.append(dict(row={**old,'ozon_type_src':source,'ozon_error':'conflict'},detail=details[0],force=True))
        for rec in ({'category':cat,'type':typ},{'category':'bad','type':'bad'},{'ozon_conflict':True}):
            cases.append(dict(row={**old,'oe_numbers':'A1'},registry={'oe':{'A1':rec}},detail=details[0]))
        cases.append(dict(row=old,unsafe=True,detail=details[0]))
        cases.append(dict(row={},enabled=False,forceName=True,detail=details[-1]))
        expected=js(copy.deepcopy(cases))['results']
        model=OzonClassifier(pairs)
        for case,want in zip(cases,expected):
            before=copy.deepcopy(case['row'])
            row,result=apply_preferred(model,case['row'],detail=lambda p:case['detail'],version='v1',category_signature='sig',
                registry=case.get('registry',{}),force=case.get('force',False),enabled=case.get('enabled',True),
                force_name=case.get('forceName',False),identity_unsafe=case.get('unsafe',False))
            with self.subTest(case=case):
                self.assertEqual({'row':row,'result':result},want)
                self.assertEqual(case['row'],before)
