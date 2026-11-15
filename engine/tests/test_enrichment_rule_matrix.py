"""Cross-product comparison with the actual browser rule loop, not a JS port."""
import copy,json,math,pathlib,sqlite3,subprocess,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'engine'))
from enrichment_transport import encode_special,decode_special,equivalent
from uc_engine import enrich_rule_rows

class EnrichmentRuleMatrix(unittest.TestCase):
    def test_values_functions_conditions_and_repeated_assignment(self):
        values=[None,False,True,0,-0.0,1,-2,0.1,1e-7,1e21,1e308,-1e308,5e-324,math.nan,math.inf,-math.inf,
                '', ' 12,5 kg','0x10','Infinity','1e309','-1e309','1e-309','001','ТЕСТ',[],[1],[None],{}, {'x':2}]
        expressions=['p.value','num(p.value)','round(p.value,2)','min(p.value,2)',
                     'max(p.value,-2)','abs(p.value)','ceil(p.value)','floor(p.value)',
                     'int(p.value)','sqrt(p.value)','pow(p.value,2)','len(p.value)',
                     'lower(p.value)','upper(p.value)','isBlank(p.value)',
                     'coalesce(p.value,7)','contains(p.value,p.value)',
                     'p.value+1','p.value-1','p.value*2','p.value/2','p.value%2',
                     'p.value==0','p.value===0','p.value!=0','p.value>0','p.value<=0',
                     'if(p.value,10,20)','p.value||7','p.value&&7','p.missing',
                     'if(0,p.missing.call,42)','round(1,p.value)','p.value.length','p.value.x',
                     'p.value%p.value','p.value/p.value','round(p.value,p.value)']
        rules=[dict(kind='enrich',enabled=True,field='name',op='eq',value='matrix',target_val='out'+str(i),formula=e) for i,e in enumerate(expressions)]
        for op in ['empty','contains','!contains','eq','ne','startsWith','gt','lt','regex']:
            rules.append(dict(kind='enrich',enabled=True,field='value',op=op,value='1',target_val='cond_'+op,formula='42'))
        rows=[dict(article=str(i),brand='B',name='matrix',value=v) for i,v in enumerate(values)]
        conn=sqlite3.connect(':memory:')
        try:
            for repeat in range(2):
                clean,types=encode_special(rows)
                payload=dict(rows=clean,rules=rules,context={},special_values=types,typed=True)
                reference=json.loads(subprocess.check_output(['node',str(ROOT/'tests/enrichment-rules-reference.js')],input=json.dumps(payload,allow_nan=False),text=True))
                def js_numbers(v):
                    if type(v) is int:return float(v)
                    if isinstance(v,dict):return {k:js_numbers(x) for k,x in v.items()}
                    if isinstance(v,list):return [js_numbers(x) for x in v]
                    return v
                expected=decode_special(js_numbers(reference['rows']),reference['special_values'])
                response=enrich_rule_rows(conn,clean,rules,{},types)
                for row,r in zip(rows,response['rows']):
                    for key in r['removed']:row.pop(key,None)
                    row.update(decode_special(r['fields'],r['special_values']))
                for i,(actual,want) in enumerate(zip(rows,expected)):
                    for key in actual.keys()|want.keys():
                        with self.subTest(repeat=repeat,value=repr(values[i]),key=key):
                            self.assertEqual(key in actual,key in want)
                            self.assertTrue(equivalent(actual.get(key),want.get(key)),(actual.get(key),want.get(key)))
        finally:conn.close()
