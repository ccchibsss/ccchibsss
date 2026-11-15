import copy,json,math,pathlib,sqlite3,subprocess,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'engine'))
import uc_engine  # Registers the internal modules stored in the single engine file.
from enrichment_transport import encode_special,decode_special,equivalent
from uc_engine import enrich_rule_rows

class EnrichmentTransport(unittest.TestCase):
    def test_repeated_browser_rules_and_sql_transport(self):
        rows=[{'article':'A','brand':'B','name':'filter','flag':False,'custom':{'nested':[math.nan,math.inf,-math.inf]}}]
        sets=[[
            dict(kind='enrich',enabled=True,field='name',op='eq',value='filter',target_val='positive',formula='1/0'),
            dict(kind='enrich',enabled=True,field='name',op='eq',value='filter',target_val='negative',formula='-1/0*-1'),
            dict(kind='enrich',enabled=True,field='name',op='eq',value='filter',target_val='invalid',formula='sqrt(-1)'),
            dict(kind='enrich',enabled=True,field='name',op='eq',value='filter',target_val='flag',formula='1')],
            [dict(kind='enrich',enabled=True,field='name',op='eq',value='filter',target_val='result',formula='if(p.positive>100,42,0)'),
             dict(kind='enrich',enabled=True,field='name',op='eq',value='filter',target_val='clone',formula='p.custom'),
             dict(kind='enrich',enabled=True,field='positive',op='lt',value='1',target_val='infinityCondition',formula='99'),
             dict(kind='enrich',enabled=True,field='invalid',op='lt',value='1',target_val='nanCondition',formula='77')]]
        conn=sqlite3.connect(':memory:')
        try:
            for rules in sets*2:
                clean,sidecar=encode_special(rows)
                payload=dict(rows=clean,rules=rules,context={},special_values=sidecar,typed=True)
                want=json.loads(subprocess.check_output(['node',str(ROOT/'tests/enrichment-rules-reference.js')],input=json.dumps(payload,allow_nan=False),text=True))
                before=copy.deepcopy(clean)
                response=enrich_rule_rows(conn,clean,rules,{},sidecar)
                self.assertEqual(clean,before)
                for row,r in zip(rows,response['rows']):
                    for k in r['removed']:row.pop(k,None)
                    row.update(decode_special(r['fields'],r['special_values']))
                expected=decode_special(want['rows'],want['special_values'])
                self.assertTrue(equivalent(rows,expected),(rows,expected))
                json.dumps(response,allow_nan=False)
            self.assertEqual(rows[0]['result'],42)
            self.assertEqual(rows[0]['infinityCondition'],99)
            self.assertEqual(rows[0]['nanCondition'],77)
            self.assertIs(type(rows[0]['flag']),float)
            self.assertTrue(math.isnan(rows[0]['clone']['nested'][0]))
        finally:conn.close()

    def test_invalid_sidecar_rejected_without_sql_changes(self):
        conn=sqlite3.connect(':memory:')
        try:
            rows=[{'article':'A','brand':'B','x':None}]
            bad=[None,{},[{'path':[0,'x'],'kind':'bad'}],[{'path':[0,'no'],'kind':'positive'}],
                 [{'path':[0,'article'],'kind':'nan'}],[{'path':[0,'__proto__'],'kind':'nan'}],
                 [{'path':[0,'x'],'kind':'nan'}]*2]
            for entries in bad[1:]:
                with self.subTest(entries=entries):
                    with self.assertRaises(ValueError):enrich_rule_rows(conn,rows,[],{},entries)
                    self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='enrichment_rule_state'").fetchone())
        finally:conn.close()

    def test_actual_client_transport_and_atomic_batches(self):
        subprocess.check_call(['node',str(ROOT/'tests/enrichment-rules-client.js')])
