import json,os,pathlib,sqlite3,subprocess,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'engine'))
from enrichment_transport import JSDate,decode_special,encode_special,equivalent
from uc_engine import enrich_rule_rows

class EnrichmentDates(unittest.TestCase):
    def test_actual_browser_date_rules_and_repeated_sql_transport(self):
        raw=[dict(article='A',brand='B',name='date',date='2026-01-01T00:00:00.000Z',invalid=None,
                  nested={'date':'2026-01-01T00:00:00.000Z'},result=123)]
        sidecar=[dict(path=[0,'date'],kind='date',milliseconds=1767225600000,text='Thu Jan 01 2026 00:00:00 GMT+0000 (Coordinated Universal Time)'),
                 dict(path=[0,'invalid'],kind='date',milliseconds=None,text='Invalid Date'),
                 dict(path=[0,'nested','date'],kind='date',milliseconds=1767225600000,text='Thu Jan 01 2026 00:00:00 GMT+0000 (Coordinated Universal Time)')]
        expressions=['p.date','p.invalid','p.nested','p.date+1','-p.date','p.date>0','num(p.date)',
                     'round(p.date)','min(1,p.date)','abs(p.date)','sqrt(p.date)','ceil(p.date)',
                     'pow(p.date,2)','int(p.date)','len(p.date)','lower(p.date)','upper(p.invalid)',
                     'contains(p.date,p.date)','isBlank(p.invalid)','coalesce(p.date,1)',
                     'if(0,p.date+1,42)','if(p.date,42,0)','p.date==p.date','round(1,p.date)',
                     'num(p.invalid)','p.invalid ? 1 : 2','pi(p.date)','p.date.missing','p.date/0','num(p.date)/0','p.date%0',
                     'num(p.date)%0','p.date/2','0/p.date']
        conn=sqlite3.connect(':memory:')
        try:
            for expression in expressions:
                rows=decode_special(raw,sidecar)
                rules=[dict(kind='enrich',enabled=True,field='name',op='eq',value='date',target_val='result',formula=expression)]
                for run in range(2):
                    clean,types=encode_special(rows)
                    payload=dict(rows=clean,special_values=types,rules=rules,context={},typed=True)
                    want=json.loads(subprocess.check_output(['node',str(ROOT/'tests/enrichment-rules-reference.js')],input=json.dumps(payload,allow_nan=False),text=True,env={**os.environ,'TZ':'UTC'}))
                    response=enrich_rule_rows(conn,clean,rules,{},types)
                    for row,r in zip(rows,response['rows']):
                        for k in r['removed']:row.pop(k,None)
                        row.update(decode_special(r['fields'],r['special_values']))
                    expected=decode_special(want['rows'],want['special_values'])
                    with self.subTest(expression=expression,run=run):self.assertTrue(equivalent(rows,expected),(rows,expected))
                    json.dumps(response,allow_nan=False)
        finally:conn.close()

    def test_full_js_date_range_and_timezone_text_roundtrip(self):
        for tz in ['UTC','Europe/Moscow']:
            script="const ms=[-8640000000000000,-62167219200000,0,1767225600000,8640000000000000];process.stdout.write(JSON.stringify(ms.map(n=>{const d=new Date(n);return {value:d.toJSON(),entry:{path:['date'],kind:'date',milliseconds:n,text:String(d)}}})));"
            cases=json.loads(subprocess.check_output(['node','-e',script],text=True,env={**os.environ,'TZ':tz}))
            for case in cases:
                with self.subTest(tz=tz,case=case):
                    decoded=decode_special({'date':case['value']},[case['entry']])
                    value,entries=encode_special(decoded)
                    self.assertEqual(value,{'date':case['value']});self.assertEqual(entries,[case['entry']])
                    self.assertEqual(str(decoded['date']),case['entry']['text'])
        with self.assertRaises(ValueError):decode_special({'date':'2026-01-01T00:00:00.000Z'},[dict(path=['date'],kind='date',milliseconds=0,text='wrong')])

    def test_invalid_date_metadata(self):
        for entry in [dict(milliseconds=True,text='x'),dict(milliseconds=1.5,text='x'),
                      dict(milliseconds=8640000000000001,text='x'),dict(milliseconds=None,text='not invalid')]:
            with self.subTest(entry=entry):
                with self.assertRaises(ValueError):decode_special({'value':None},[dict(entry,path=['value'],kind='date')])
