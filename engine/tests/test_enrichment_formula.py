import json,math,pathlib,shutil,subprocess,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from enrichment_formula import evaluate,UNDEFINED

class FormulaParity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_browser_safe_parser(self):
        row={'price':125.5,'cost':'50,25','sales':3,'brand':'BOSCH','name':'😀abc','zero':0,'flag':True}
        expressions=['p.price*1.2','num(p.cost)+250','round(p.price/3,2)','round(-1.005,2)',
          'min(p.price,10,25)','max(p.price,10)','abs(-3)+ceil(2.2)+floor(2.9)+int(-2.8)',
          'pow(2,3)+sqrt(16)','if(p.price>100,p.price,p.missing.bad)','p.zero ? 10 : 20',
          'p.flag && p.price || 4','p.brand==p.brand','p.brand!=p.name','len(p.name)',
          'lower(p.brand)','upper(p.brand)','contains(p.brand,p.brand)','coalesce(p.missing,p.cost)',
          'isBlank(p.missing)','p.missing','true','pi()*2','e()','10%3','-10%3','1/0','1%0',
          'p.price>=100 ? 1 : 0','p.price<=100 ? 1 : 0','p.constructor','process.exit()',
          'p[0]','1;2','"text"','!p.flag','1..2','2**3','unknown(1)','if(0,unknown,42)']
        root=pathlib.Path(__file__).resolve().parents[2]
        expected=json.loads(subprocess.check_output(['node',str(root/'tests/enrichment-formula-reference.js')],input=json.dumps([{'expr':e,'row':row} for e in expressions]),text=True))
        for expr,want in zip(expressions,expected):
            try:
                value=evaluate(expr,row)
                got={'ok':True,'value':None if value is UNDEFINED or isinstance(value,float) and not math.isfinite(value) else value,'undefined':value is UNDEFINED}
            except Exception: got={'ok':False}
            with self.subTest(expr=expr): self.assertEqual(got,want)

    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_ordered_rules_actual_pipeline(self):
        from enrichment_rules import apply_rules
        from uc_engine import match_condition
        rules=[{'kind':'enrich','enabled':1,'field':'name','op':'contains','value':'filter','target_val':'price','formula':'num(p.cost)*2'},
               {'kind':'enrich','enabled':1,'field':'price','op':'gt','value':'100','target_val':'price','formula':'round(p.price+5,2)'},
               {'kind':'enrich','enabled':1,'field':'name','op':'contains','value':'filter','target_val':'category','formula':'upper(p.brand)'},
               {'kind':'enrich','enabled':1,'field':'name','op':'contains','value':'filter','target_val':'stock','formula':'p.constructor()'},
               {'kind':'enrich','enabled':1,'field':'name','op':'contains','value':'filter','target_val':'customCalc','formula':'p.price/num(p.sales)'}]
        rows=[{'article':'A','brand':'Brand','name':'filter','cost':60,'sales':3},
              {'article':'B','brand':'Brand','name':'filter','cost':60,'sales':3,'category':'Ручная'},
              {'article':'C','brand':'Brand','name':'filter','cost':60,'sales':3,'category':'Old','_categoryNameAutoValue':'Old'},
              {'article':'D','brand':'Brand','name':'other','cost':60,'sales':3}]
        ctx={'version':'rules-v1'}
        root=pathlib.Path(__file__).resolve().parents[2]
        expected=json.loads(subprocess.check_output(['node',str(root/'tests/enrichment-rules-reference.js')],input=json.dumps(dict(rows=rows,rules=rules,context=ctx)),text=True))
        actual=[apply_rules(row,rules,ctx,match_condition) for row in rows]
        self.assertEqual(actual,expected)

    def test_sql_rule_result_persistence_and_nonfinite(self):
        import sqlite3
        from uc_engine import enrich_rule_rows
        conn=sqlite3.connect(':memory:')
        rules=[dict(kind='enrich',enabled=1,field='name',op='eq',value='test',target_val='computed',formula='1/0')]
        response=enrich_rule_rows(conn,[dict(article='A',brand='B',name='test')],rules,{})['rows'][0]
        self.assertEqual(response['nonfinite'],{'computed':'positive'})
        self.assertIsNone(response['fields']['computed'])
        stored=json.loads(conn.execute('SELECT data FROM enrichment_rule_state').fetchone()[0])
        self.assertEqual(stored['nonfinite'],response['nonfinite'])
        conn.close()
