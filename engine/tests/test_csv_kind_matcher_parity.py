import json,pathlib,shutil,subprocess,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from csv_kind_matcher import CsvKindMatcher,texts

class CsvKindMatcherParity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_actual_browser_candidates_and_guess(self):
        rows=[['Фильтры','Фильтр масляный','1111111111'],['Фильтры','Фильтр воздушный','2222222222'],
              ['Топливо','Насос топливный','3333333333'],['Кузов','Пружина','4444444444'],
              ['Подвеска','Пружина','5555555555'],['Мотор','Датчик','6666666666'],
              ['Охлаждение','Прочие детали охлаждения','7777777777'],['Кузов','Пороги арки ремкомплекты','8888888888']]
        names=['','Фильтр масляный','Фильтр масла BOSCH','oil filter','oil filter housing','BOSCH Фильтр воздушный',
               'Насос','бензонасос','Пружина','Пружина подвески','Датчик охлаждения','Ремкомплект','Датчик',
               'Фильтр масляный и насос топливный','Неизвестная деталь','Фильтр для двигателя','ＦＩＬＴＥＲ',
               'опора двигателя','дмрв','щетки дворников','фильтр очистки воздуха']
        products=[{'name':n,'brand':'BOSCH'} for n in names]+[{'name':'Пружина','category':'Кузов'},
                 {'name':'Пружина','category':'Кузов','_categoryNameAutoValue':'Кузов'}]
        root=pathlib.Path(__file__).resolve().parents[2]
        expected=json.loads(subprocess.check_output(['node',str(root/'tests/csv-kind-matcher-reference.js')],input=json.dumps({'rows':rows,'products':products}),text=True))
        model=CsvKindMatcher(rows)
        actual=[{'texts':texts(p['name']),'candidates':model.candidates(p['name'],p.get('brand')),'guess':model.guess(p)} for p in products]
        def clean(v):
            if isinstance(v,set): return sorted(v)
            if isinstance(v,list): return [clean(x) for x in v]
            if isinstance(v,dict): return {k:sorted(x) if k=='categoryWords' else clean(x) for k,x in v.items()}
            return v
        for p,a,e in zip(products,actual,expected):
            with self.subTest(product=p): self.assertEqual(clean(a),clean(e))
