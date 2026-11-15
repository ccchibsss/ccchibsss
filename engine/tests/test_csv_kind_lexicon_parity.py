import json,pathlib,shutil,subprocess,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine  # Registers the internal modules stored in the single engine file.
import csv_kind_lexicon as L

class CsvKindLexiconParity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_actual_browser_lexicon_and_index(self):
        texts=['Ремни','поршнями','Воздушный','топливного','масляный','колодок','Крылья','Коврики','ручейковый',
               'oil','filter','для','123','ＦＩＬＴＥＲ','ремонтный комплект двигателя','передний рычаг',
               'масло','форсунки','система','щётка стеклоочистителя','',None]
        rows=[['Фильтры','Фильтр масляный','1111111111'],['Фильтры','Воздушные и салонные фильтры','2222222222'],
              ['Кузов','Крылья, арки / пороги','3333333333'],['Крепёж','Прочие детали','4444444444'],
              ['Тормоза','Диски и колодки тормозные','5555555555'],['Duplicate','Фильтр масляный','6666666666'],
              ['Invalid','Датчик','bad']]
        root=pathlib.Path(__file__).resolve().parents[2]
        expected=json.loads(subprocess.check_output(['node',str(root/'tests/csv-kind-lexicon-reference.js')],input=json.dumps({'texts':texts,'rows':rows}),text=True))
        actual={'lex':[{'words':L.words(t),'stem':L.stem(t),'variant':L.variant(L.words(t))} for t in texts], 'index':L.build_index(rows)}
        def canonical(v):
            if isinstance(v,set): return sorted(v)
            if isinstance(v,list): return [canonical(x) for x in v]
            if isinstance(v,dict): return {k:sorted(x) if k in ('categoryWords','features') else canonical(x) for k,x in v.items()}
            return v
        self.assertEqual(canonical(actual),canonical(expected))
