import copy,json,pathlib,sqlite3,subprocess,sys,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'engine'))
import uc_engine as E

class FastPriceAndHvc(unittest.TestCase):
    def test_import_is_enrichment_only_in_both_modes(self):
        subprocess.check_call(['node',str(ROOT/'tests/import-enrichment-only-client.js')])
    def test_first_price_and_sql_client_routing(self):
        subprocess.check_call(['node',str(ROOT/'tests/import-fast-price-client.js')])
    def test_hvc_row_route_matches_actual_browser_and_reuses_reference(self):
        ref={'parts':[['P|B',{'artikul':'P','brand':'B','name':'pair','category':'Pair category','tnved':'111','barcode':'123','multiplicity':2,'image_url':'image','_dimensionEvidence':{'weight':2,'length':20,'width':20,'height':20}}]],'oe':[],'byArt':[],'byOe':[]}
        rows=[{'article':'P','brand':'B','name':'','category':'','weight':0,'length':0,'width':0,'height':0}]
        c=sqlite3.connect(':memory:')
        try:
            for mode in ['auto','artbrand','oe']:
                expected=json.loads(subprocess.check_output(['node',str(ROOT/'tests/hvc-reference.js')],input=json.dumps(dict(rows=rows,reference=ref,mode=mode,cat_mode='artbrand')),text=True))
                for repeat in range(2):
                    with patch.object(E.time,'strftime',return_value='2026-01-01T00:00:00Z'):
                        r=E.enrich_hvc_input_rows(c,rows,ref if repeat==0 else None,mode,'artbrand',reference_id=None if repeat==0 else r['reference_id'])
                    actual=copy.deepcopy(rows)
                    for p,result in zip(actual,r['rows']):
                        for k in result['removed']:p.pop(k,None)
                        p.update(E.decode_special(result['fields'],result['special_values']))
                    self.assertEqual(actual,expected)
        finally:c.close()
