import copy,json,pathlib,shutil,subprocess,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine  # Registers the internal modules stored in the single engine file.
from ozon_preferred import OzonPreferred

class OzonPreferredParity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_composed_actual_browser(self):
        root=pathlib.Path(__file__).resolve().parents[2]
        path=root/'tests/ozon-preferred-reference.js'
        def js(data):return json.loads(subprocess.check_output(['node',str(path)],input=json.dumps(data),text=True))
        categories=[['Фильтры','Фильтр масляный','1234567890'],['Двигатель','Насос водяной','1234567890']]
        pairs=js(dict(categoryRows=categories,rows=[]))['pairs']
        row=dict(article='A',brand='B',name='Фильтр масляный',category='Фильтры',category_type='Фильтр масляный')
        variants=[row,{**row,'name':'Крышка для фильтра'},
            {**row,'ozon_type':'Manual','ozon_type_src':'manual','ozon_error':'conflict'},
            {**row,'ozon_type':'Imported'}, {**row,'categoryType':'Насос'},
            {**row,'_categoryKindStatus':'category_conflict'}, {**row,'oe_numbers':'A1'}]
        tree={'revision':'r1','allItems':[
            dict(cat='Автофильтры',type='Фильтр масляный',catId='1',typeId='2',vehicle=True,status='active'),
            dict(cat='Автотовары',type='Фильтр масляный',catId='3',typeId='2',vehicle=False,status='active')]}
        for snapshot in (None,tree):
            for enabled in (True,False):
                registry={'oe':{'A1':{'category':'Автофильтры','type':'Фильтр масляный'}}}
                ref=dict(pairs=pairs,category_rows=categories,category_revision='test',registry=registry,tree=snapshot)
                model=OzonPreferred(ref)
                # Include current drafts and stale name/category/version variants.
                draft,_=model.apply(row)
                marker=dict(version='csv-kind-name-v1|test',name=row['name'],brand='B',category='Фильтры',referenceCategory='Фильтры',type='Фильтр масляный',categoryMode='explicit',categoryMethod='',categoryRevision='',confirmed=False)
                marked={**row,'_categoryKindAuto':marker}
                rows=variants+[marked,{**marked,'name':'Changed'},{**marked,'_categoryKindAuto':{**marker,'confirmed':True}},{**marked,'_categoryTypeCleared':True},draft,{**draft,'name':'Насос водяной'}, {**draft,'category':'Двигатель'}, {**draft,'_ozonNameVersion':'old'}]
                data=dict(categoryRows=categories,rows=copy.deepcopy(rows),tree=snapshot,registry=registry,enabled=enabled)
                wants=js(data)['results']
                for p,want in zip(rows,wants):
                    actual,result=model.apply(p,enabled=enabled)
                    with self.subTest(row=p,tree=bool(snapshot),enabled=enabled):
                        self.assertEqual(dict(row=actual,result=result),want)
