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

    def test_nonstring_fields_whitespace_and_unknown_statuses(self):
        import sqlite3
        from uc_engine import check_mark_status_rows
        values=[None,False,True,0,12345678.0,[],['ok'],['unknown','status'],{},'\ufeffok\ufeff','\x1cok\x1c']
        rows=[]
        for field in ['markRequired','markCode','markStatus']:
            for v in values:
                rows.append(dict({'article':str(len(rows)),'brand':'B','markRequired':True,'markCode':'12345678','markStatus':'ok'},**{field:v}))
        settings={'autoHideMark':True,'markInvalidStatuses':['ok']}
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/mark-status-reference.js'
        expected=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps({'rows':rows,'settings':settings,'include_unknown':True}),text=True))
        conn=sqlite3.connect(':memory:')
        conn.execute('CREATE TABLE products(article TEXT,brand TEXT,visible TEXT,visible_reason TEXT)')
        try:
            response=check_mark_status_rows(conn,rows,settings)
            for p,r,want in zip(rows,response['rows'],expected['rows']):
                with self.subTest(row=p):
                    self.assertEqual({'row':{**p,**r['fields']},'result':r['result']},want)
            self.assertEqual(response['unknown'],expected['unknown'])
        finally:conn.close()

    def test_typed_route_matches_browser(self):
        import sqlite3,math,os
        from uc_engine import check_mark_status_rows
        from enrichment_transport import JSDate,encode_special,decode_special,equivalent
        values=[math.nan,math.inf,-math.inf,JSDate(0,'Thu Jan 01 1970 00:00:00 GMT+0000 (Coordinated Universal Time)','1970-01-01T00:00:00.000Z'),JSDate(None,'Invalid Date',None)]
        rows=[]
        for field in ['markRequired','markCode','markStatus']:
            for value in values:
                rows.append(dict({'article':str(len(rows)),'brand':'B','markRequired':True,'markCode':'12345678','markStatus':'ok'},**{field:value}))
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/mark-status-reference.js'
        for settings in [{'autoHideMark':True},{'autoHideMark':math.nan,'markInvalidStatuses':values[3]}]:
            clean,types=encode_special({'rows':rows,'settings':settings})
            expected=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps({**clean,'special_values':types,'include_unknown':True},allow_nan=False),text=True,env={**os.environ,'TZ':'UTC'}))
            conn=sqlite3.connect(':memory:')
            conn.execute('CREATE TABLE products(article TEXT,brand TEXT,visible TEXT,visible_reason TEXT)')
            try:
                result=check_mark_status_rows(conn,clean['rows'],clean['settings'],types)
                json.dumps(result,allow_nan=False)
                saved=json.loads(conn.execute('SELECT data FROM mark_status_settings').fetchone()[0])
                saved_types=json.loads(conn.execute('SELECT data FROM mark_status_setting_types').fetchone()[0])
                self.assertTrue(equivalent(decode_special(saved,saved_types),settings))
                for actual,want in zip(result['rows'],expected['rows']):
                    self.assertEqual(actual['result'],want['result'])
                    for k,v in actual['fields'].items():self.assertEqual(v,want['row'][k])
                self.assertEqual(result['unknown'],expected['unknown'])
            finally:conn.close()

    def test_actual_typed_client(self):
        subprocess.check_call(['node',str(pathlib.Path(__file__).resolve().parents[2]/'tests/mark-status-client.js')])
