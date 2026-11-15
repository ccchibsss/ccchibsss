import json,math,pathlib,shutil,subprocess,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine  # Registers the internal modules stored in the single engine file.
from enrichment_formula import evaluate,UNDEFINED

class FormulaParity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_coercion_arguments_and_nested_fields(self):
        values=[None,False,True,0,-0.0,1.25,1e-7,1e-6,1e20,1e21,'',' 12 ',
                '0x10','0b11','0o17','-0x1','1e3','1e','1_000','inf','Infinity',
                '1,25','2,5,6',' 1 e 2 ','\ufeff42','\x1c42','１２',
                [],[None],[2],['2'],[1,2],{}, {'a':1}, {'a':2},['x',None,['y','z']]]
        expressions=['p.v+1','-p.v','num(p.v)','round(p.v)','min(p.v,2)',
                     'max(p.v,2)','abs(p.v)','len(p.v)','lower(p.v)','upper(p.v)',
                     'contains(p.v,p.n)','p.v ? 1 : 2','p.v==p.other','p.v===p.other',
                     'p.v.length','p.v.a','p.v.1']
        cases=[{'expr':e,'row':{'v':v,'n':None,'other':other}}
               for v in values for other in [v,{},[]] for e in expressions]
        expressions=['pi(1,2)','e(1)','num()','round()','round(1,p.missing)',
                     'abs()','abs(-3,4)','sqrt()','pow()','pow(2)','pow(2,3,4)',
                     'len()','contains()','contains(p.name)','isBlank()','coalesce()',
                     'coalesce(p.missing,p.name)','min()','max()','lower()',
                     'pi(p.constructor)','if(0,p.constructor,2)',
                     '-sqrt(-1)','1/sqrt(-1)','1%sqrt(-1)','round(sqrt(-1))',
                     'p.items.length','p.name.length','1\ufeff+2','1\x1c+2',
                     'num(p.exp)','num(p.spaced)']
        cases += [{'expr':e,'row':{'items':[1,2,3],'name':'abc','exp':'1.25e+3','spaced':' 1 e 2 '}} for e in expressions]
        root=pathlib.Path(__file__).resolve().parents[2]
        expected=json.loads(subprocess.check_output(['node',str(root/'tests/enrichment-formula-reference.js')],input=json.dumps(cases),text=True),parse_int=float)
        for case,want in zip(cases,expected):
            try:
                value=evaluate(case['expr'],case['row'])
                got={'ok':True,'value':None if value is UNDEFINED or isinstance(value,float) and not math.isfinite(value) else value,'undefined':value is UNDEFINED}
            except Exception:got={'ok':False}
            with self.subTest(case=case):self.assertEqual(got,want)

    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_browser_safe_parser(self):
        row={'price':125.5,'cost':'50,25','sales':3,'brand':'BOSCH','name':'😀abc','zero':0,'flag':True}
        expressions=['p.price*1.2','num(p.cost)+250','round(p.price/3,2)','round(-1.005,2)',
          'min(p.price,10,25)','max(p.price,10)','abs(-3)+ceil(2.2)+floor(2.9)+int(-2.8)',
          'pow(2,3)+sqrt(16)','if(p.price>100,p.price,p.missing.bad)','p.zero ? 10 : 20',
          'p.flag && p.price || 4','p.brand==p.brand','p.brand!=p.name','len(p.name)',
          'lower(p.brand)','upper(p.brand)','contains(p.brand,p.brand)','coalesce(p.missing,p.cost)',
          'isBlank(p.missing)','p.missing','true','pi()*2','e()','10%3','-10%3','1/0','1%0',
          'sqrt(-1)','sqrt(-1)+1','sqrt(-1) ? 1 : 2','pow(0,-1)','pow(-2,0.5)',
          'pow(10,400)','pow(-10,401)','round(1,400)','round(1,-400)','round(1/0,2)','(1/0)%3',
          'lower(1/0)','len(sqrt(-1))','if(sqrt(-1),1,2)',
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
