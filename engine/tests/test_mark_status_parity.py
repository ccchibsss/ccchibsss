import json
import pathlib
import shutil
import subprocess
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from mark_status import apply


class MarkStatusParity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node executes browser reference')
    def test_status_and_pipeline_hide(self):
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/mark-status-reference.js'
        rows=[{'article':str(i),'markRequired':True,'markCode':'12345678','markStatus':status}
              for i,status in enumerate(['введён в оборот',' ВВЕДЕН В ОБОРОТ ','Продан','возвращён','unknown','custom valid','custom invalid','',None,True])]
        rows += [
            {'markRequired':False,'markCode':'','markStatus':'Продан'},
            {'markRequired':True,'markCode':'short','markStatus':'ok'},
            {'markRequired':True,'markCode':'😀😀😀😀','markStatus':'ok'},
            {'markRequired':True,'markCode':'12345678','markStatus':'ok','visible':False,'visibleReason':'other'},
            {'markRequired':True,'markCode':'12345678','markStatus':'invalid','policyReason':'previous'}]
        for settings in ({},{'autoHideMark':True},{'autoHideMark':True,'markRequireCode':False},
                         {'autoHideMark':True,'markValidStatuses':'custom valid;invalid','markInvalidStatuses':'custom invalid,ok'}):
            with self.subTest(settings=settings):
                expected=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps({'rows':rows,'settings':settings}),text=True))
                actual=[dict(zip(('row','result'),apply(p,settings))) for p in rows]
                self.assertEqual(actual,expected)
