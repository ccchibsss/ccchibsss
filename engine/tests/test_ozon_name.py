import json,pathlib,shutil,subprocess,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from ozon_name import OzonNameClassifier

class OzonNameParity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_actual_browser_name_detail(self):
        root=pathlib.Path(__file__).resolve().parents[2]
        pairs=json.loads(subprocess.check_output(['node',str(root/'tests/ozon-classifier-reference.js')],input='[]',text=True))['pairs']
        types=[dict(cat=c,name=t) for c,t in pairs]
        types += [dict(cat='A',name='Насос водяной',catId=1,typeId=2),dict(cat='B',name='Насос водяной',catId=3,typeId=2)]
        names=['','???','BOSCH фильтр масляный для Toyota','помпа водяная','oil filter','filter housing','комплект фильтр масляный и фильтр воздушный','насос топливный','форсунка стеклоомывателя','свеча накаливания','лямбда-зонд','прокладка головки блока цилиндров','подушка двигателя','держатель тормозного шланга','фильтр для мотоцикла','wiper blades','timing belt','помпа охлаждения двигателя']
        names += [t for c,t in pairs]+['Крышка для '+t for c,t in pairs[:25]]
        rows=[dict(name=n,brand='BOSCH') for n in names]
        expected=json.loads(subprocess.check_output(['node',str(root/'tests/ozon-name-reference.js')],input=json.dumps(dict(types=types,rows=rows)),text=True))
        model=OzonNameClassifier(types)
        for p,want in zip(rows,expected):
            with self.subTest(name=p['name']): self.assertEqual(model.detail(p),want)
