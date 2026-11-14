import copy
import json
import pathlib
import shutil
import subprocess
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from name_category import apply
from uc_engine import match_condition


class NameCategoryBrowserParity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node executes real browser implementation')
    def test_selection_and_apply(self):
        root=pathlib.Path(__file__).resolve().parents[2]
        categories=[
            {'active':True,'name':'Фильтры','kind':'base','keywords':'фильтр;filter','priority':1},
            {'active':True,'name':'Топливная система','kind':'base','keywords':'форсунк;насос топлив','priority':2},
            {'active':True,'name':'Жидкости и масла','kind':'base','keywords':'масл','priority':3},
            {'active':True,'name':'Cooling','keywords':'насос водян','priority':4},
            {'active':True,'name':'Choice A','keywords':'шайба','priority':5},
            {'active':True,'name':'Choice B','keywords':'шайба','priority':5}]
        rows=[{'article':str(i),'name':name,'brand':'B','category':''} for i,name in enumerate([
            'Фильтр масла','Масляный насос','Масло моторное','Форсунка омывателя',
            'Форсунка топливная','Помпа водяная','Салонный','Шайба','Unknown',''])]
        rows += [
            {'article':'manual','name':'Фильтр','category':'Manual'},
            {'article':'explicit','name':'Фильтр','category':'Без категории','_categoryNameExplicit':True},
            {'article':'external','name':'Unknown','category':'Manual','_categoryNameAutoValue':'Old','_categoryNameSource':'Old'},
            {'article':'stale','name':'Unknown','category':'Фильтры','_categoryNameAutoValue':'Фильтры','_categoryNameSource':'Фильтр','_categoryNameBrand':'B'}]
        for enabled in (True,False):
            fixture={'categories':categories,'rules':[],'heads':['фильтр','насос','форсунк','масл'], 'rows':copy.deepcopy(rows),'enabled':enabled}
            expected=json.loads(subprocess.check_output(['node',str(root/'tests/name-category-reference.js')],input=json.dumps(fixture),text=True))
            context={**fixture,'version':expected['version']}
            actual=[apply(p,context,enabled,match_condition) for p in rows]
            self.assertEqual(actual,expected['rows'])
