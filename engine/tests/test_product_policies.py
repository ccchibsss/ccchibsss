import copy,json,pathlib,sqlite3,subprocess,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine  # Registers the internal modules stored in the single engine file.
from product_policies import apply_policies
from uc_engine import match_condition,num,apply_product_policies

class PolicyParity(unittest.TestCase):
    def test_actual_browser_policy_loop(self):
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/product-policies-reference.js'
        rows=[{}, {'price':0},{'price':49},{'price':'1 234,50'},{'brand':'BMW','visible':True},
              {'brand':'other','visible':False,'visibleReason':'manual_off'}, {'markRequired':True},
              {'name':'Фильтр масляный','category':'Фильтры'},{'price':1000,'excluded':True,'deletePending':True}]
        groups=[[dict(enabled=True,field='markRequired',op='eq',value='true',action='hide')],[],[dict(enabled=True,field='price',op='lt',value=50,action='exclude')],
            [dict(enabled=True,field='brand',op='contains',value='bm',action='hide'),dict(enabled=True,field='price',op='empty',value='',action='warn')],
            [dict(enabled=True,field='name',op='regex',value='^фильтр',action='delete_mark',order_no=2),dict(enabled=True,field='category',op='eq',value='фильтры',action='warn',order_no=1)],
            [dict(enabled=True,field='brand',op='ne',value='bmw',action='exclude'),dict(enabled=False,field='price',op='empty',action='delete_mark')]]
        for rules in groups:
            expected=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps(dict(rows=rows,rules=rules)),text=True))
            for p,want in zip(rows,expected):
                with self.subTest(row=p,rules=rules):self.assertEqual(apply_policies(p,rules,match_condition,num),want)
        conn=sqlite3.connect(':memory:')
        result=apply_product_policies(conn,rows,groups[2])
        self.assertEqual(len(result['rows']),len(rows))
        self.assertTrue(result['rows'][1]['fields']['excluded'])
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM product_policy_state').fetchone()[0],3)
        conn.close()

    def test_order_prefix_numbers_and_null_reason_against_browser(self):
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/product-policies-reference.js'
        rows=[{'article':'A','brand':'B','name':'x'}]
        groups=[[
            dict(enabled=True,field='name',op='eq',value='x',action='hide',order_no='2 kg'),
            dict(enabled=True,field='name',op='eq',value='x',action='warn',order_no=1)],
            [dict(enabled=True,field='price',op='empty',value=None,action='warn')]]
        for rules in groups:
            expected=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps(dict(rows=rows,rules=rules)),text=True))
            conn=sqlite3.connect(':memory:')
            try:
                result=apply_product_policies(conn,rows,rules)
                for row,r,want in zip(rows,result['rows'],expected):self.assertEqual({**row,**r['fields']},want)
            finally:conn.close()
