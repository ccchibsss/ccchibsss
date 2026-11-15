"""Execute the actual SQL pipeline prelude, then the real SQLite policy route."""
import json,pathlib,sqlite3,subprocess,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'engine'))
from uc_engine import apply_product_policies

class PipelineOrder(unittest.TestCase):
    def test_date_cleanup_before_all_sql_classifiers_and_policies(self):
        cases=json.loads(subprocess.check_output(['node',str(ROOT/'tests/enrichment-pipeline-order.js')],text=True))
        for case in cases:
            rows=case['rows']
            # Browser policies receive numeric zero after the common Date guard.
            rules=[dict(enabled=True,field='price',op='lt',value=50,action='exclude')]
            expected=json.loads(subprocess.check_output(['node',str(ROOT/'tests/product-policies-reference.js')],input=json.dumps(dict(rows=rows,rules=rules)),text=True))
            conn=sqlite3.connect(':memory:')
            try:
                result=apply_product_policies(conn,rows,rules)
                for p,r,want in zip(rows,result['rows'],expected):self.assertEqual({**p,**r['fields']},want)
                price=next(r for p,r in zip(rows,result['rows']) if p.get('price')==0)
                self.assertTrue(price['fields']['excluded'])
            finally:conn.close()
