import json,pathlib,shutil,subprocess,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine  # Registers the internal modules stored in the single engine file.
from ozon_category import OzonCategoryClassifier

class OzonCategoryParity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_actual_browser_category_detail(self):
        root=pathlib.Path(__file__).resolve().parents[2]
        types=[dict(cat=c,name=t,catId=ci,typeId=ti) for c,t,ci,ti in [
            ('Автофильтры','Фильтр масляный',1,10),('Автотовары','Фильтр масляный',2,10),
            ('Запчасти для легковых автомобилей','Насос водяной',3,20),
            ('Автотовары','Насос водяной',4,20),('Автотовары','Насос автомобильный',4,21),
            ('Автотовары','Подушка автомобильная',4,22),('Запчасти для легковых автомобилей','Подушка двигателя',3,23),
            ('Запчасти для легковых автомобилей','Фильтр воздушный',3,24),
            ('Автотовары','Датчик',4,25),('Автотовары','Ремень ГРМ',4,26)]]
        reference=[['Фильтры','Фильтр масляный','1234567890'],['Охлаждение','Насос водяной','1234567890'],
            ['Система охлаждения','Насос водяной','1234567890'],['Подвеска','Подушка двигателя','1234567890'],
            ['Двигатель','Ремень ГРМ','1234567890'],['Электрика','Датчик давления','1234567890'],
            ['Прочее','Разные детали','1234567890']]
        rows=[]
        for cat,kind,_ in reference:
            for name in ['',kind,'Крышка для '+kind,'filter housing', 'Насос водяной', 'Фильтр воздушный','Датчик давления масла','Подушка двигателя']:
                rows.append(dict(category=cat,category_type=kind,name=name))
        rows += [dict(name='Фильтр масляный',category='Фильтры'),dict(name='Насос водяной',category='Система охлаждения'),
                 dict(name='Датчик',_categoryKindStatus='category_conflict',_categoryKindChoices=['A']),
                 dict(name='Датчик',_categoryKindStatus='ambiguous',_categoryKindDiscriminators=['давлен']),
                 dict(name='Фильтр масляный',category='Фильтры',category_type='Фильтр масляный',categoryType='Датчик')]
        def compare(ts):
            expected=json.loads(subprocess.check_output(['node',str(root/'tests/ozon-category-reference.js')],input=json.dumps(dict(types=ts,categoryRows=reference,rows=rows)),text=True))
            model=OzonCategoryClassifier(ts,reference,'test')
            for p,want in zip(rows,expected):
                with self.subTest(row=p,types=len(ts)): self.assertEqual(model.detail_with_category(p),want)
        compare(types)
        compare(types+[dict(cat='Автофильтры',name='Фильтр масляный',catId=9,typeId=10)])

    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_all_historical_types_with_internal_kind(self):
        root=pathlib.Path(__file__).resolve().parents[2]
        pairs=json.loads(subprocess.check_output(['node',str(root/'tests/ozon-classifier-reference.js')],input='[]',text=True))['pairs']
        types=[dict(cat=c,name=t) for c,t in pairs]
        reference=[['Test '+str(i),t,'1234567890'] for i,(c,t) in enumerate(pairs)]
        rows=[dict(name=t,category='Test '+str(i),category_type=t) for i,(c,t) in enumerate(pairs)]
        expected=json.loads(subprocess.check_output(['node',str(root/'tests/ozon-category-reference.js')],input=json.dumps(dict(types=types,categoryRows=reference,rows=rows)),text=True))
        model=OzonCategoryClassifier(types,reference,'test')
        for p,want in zip(rows,expected):
            with self.subTest(row=p): self.assertEqual(model.detail_with_category(p),want)
