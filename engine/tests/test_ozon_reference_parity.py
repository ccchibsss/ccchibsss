import json,pathlib,shutil,subprocess,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine  # Registers the internal modules stored in the single engine file.
from ozon_reference import OzonReference
from ozon_classifier import OzonClassifier

class OzonReferenceParity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_actual_browser_tree_lookup(self):
        def item(cat,typ,cid,tid,status='active',vehicle=True):
            return dict(cat=cat,type=typ,catId=cid,typeId=tid,status=status,vehicle=vehicle,path=[cat])
        tree={'schema':'ozon-description-tree-v1','revision':'r1','allItems':[
            item('Категория','Тип ёж','1','10'),item('Категория','Дубликат','1','11'),item('Категория','Дубликат','1','12'),
            item('Категория','Отключён','1','13','disabled'),item('Категория','Неизвестен','1','14','unknown'),
            item('Категория','Конфликт','1','15','conflict'),item('Другое','Тип','2','20',vehicle=False)]}
        queries=[dict(category='Категория',type='Тип ёж'),dict(category=' КАТЕГОРИЯ ',type='ТИП ЁЖ'),
            dict(category='Категория',type='Тип еж'),dict(category='',type='Тип ёж'),dict(category='Нет',type='Нет'),
            dict(category='Категория',type='Дубликат'),dict(category='Категория',type='Дубликат',ids=dict(catId='1',typeId='12')),
            dict(category='Категория',type='Тип ёж',ids=dict(catId='1',typeId='11'))]
        for typ,tid in [('Отключён','13'),('Неизвестен','14'),('Конфликт','15')]:
            queries.append(dict(category='Категория',type=typ,ids=dict(catId='1',typeId=tid)))
        queries += [dict(category='Другое',type='Тип',ids=dict(catId='2',typeId='20'))]
        root=pathlib.Path(__file__).resolve().parents[2]
        for scope in ('auto','all'):
            expected=json.loads(subprocess.check_output(['node',str(root/'tests/ozon-reference-tree.js')],input=json.dumps(dict(tree=tree,scope=scope,queries=queries)),text=True))
            model=OzonReference(tree,scope)
            for q,e in zip(queries,expected):
                with self.subTest(scope=scope,query=q): self.assertEqual(model.find_pair(q['category'],q['type'],q.get('ids')),e)
        self.assertEqual(OzonReference().find_pair('A','B'),{'status':'no_reference'})

    def test_loaded_tree_rejects_historical_fallback(self):
        tree={'items':[dict(cat='New',type='Type',catId='1',typeId='2')]}
        model=OzonClassifier([['Old','Type']],tree)
        self.assertIsNone(model.pair({'category':'Old','type':'Type'}))
        self.assertEqual(model.pair({'category':'New','type':'Type'}),{'category':'New','type':'Type'})
        self.assertEqual(model.pair('Type'),{'category':'New','type':'Type'})

    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_tree_used_by_real_browser_classifier(self):
        tree={'items':[dict(cat='New',type='Type',catId='1',typeId='2')]}
        cases=[{'row':{'oe_numbers':'A'},'registry':{'oe':{'A':mapping}}} for mapping in
               ({'category':'New','type':'Type'},{'category':'Old','type':'Type'},'Type',{'ozon_type':'missing'})]
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/ozon-classifier-reference.js'
        result=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps(dict(tree=tree,cases=cases)),text=True))
        model=OzonClassifier(result['pairs'],tree)
        for case,want in zip(cases,result['results']):
            self.assertEqual(model.classify(case['row'],case['registry']),want)
