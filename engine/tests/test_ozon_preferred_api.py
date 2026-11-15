import copy,json,pathlib,sqlite3,subprocess,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from uc_engine import enrich_ozon_preferred
import uc_engine  # Registers the internal modules stored in the single engine file.
from ozon_identity import IdentityGuard

class OzonPreferredAPI(unittest.TestCase):
    def test_persistence_removals_and_identity(self):
        conn=sqlite3.connect(':memory:')
        conn.executescript("CREATE TABLE products(article TEXT,brand TEXT,ozon_category TEXT,ozon_type TEXT); INSERT INTO products VALUES('A','B','','');")
        reference=dict(pairs=[['Автофильтры','Фильтр масляный']],category_rows=[['Фильтры','Фильтр масляный','1234567890']],category_revision='test',identity={'rows':[{'article':'A','brand':'B'}]})
        p=dict(article='A',brand='B',name='Фильтр масляный',category='Фильтры',category_type='Фильтр масляный')
        before=copy.deepcopy(p)
        r=enrich_ozon_preferred(conn,[p],reference)['rows'][0]
        self.assertEqual(p,before)
        self.assertEqual(r['fields']['ozon_type_src'],'keyword')
        self.assertEqual(json.loads(conn.execute('SELECT data FROM ozon_preferred_state').fetchone()[0]),r['fields'])
        manual={**p,**r['fields'],'ozon_type_src':'manual','ozon_error':'conflict'}
        r=enrich_ozon_preferred(conn,[manual],reference)['rows'][0]
        self.assertIn('_ozonNameStatus',r['removed'])
        self.assertEqual(r['fields']['ozon_error'],'')
        bad=copy.deepcopy(reference)
        bad['identity'].update(parts=[['A|B',{'artikul':'WRONG'}]],byArt=[['A|B',['OE1']]])
        r=enrich_ozon_preferred(conn,[p],bad)['rows'][0]
        self.assertEqual(r['fields'],{})
        self.assertIn('неоднозначный',r['result']['reason'])
        other={**p,'article':'C','oe_numbers':'OE1'}
        self.assertTrue(IdentityGuard(bad['identity']['rows'],bad['identity']).unsafe_for(other))
        count=conn.execute('SELECT COUNT(*) FROM ozon_preferred_state').fetchone()[0]
        with self.assertRaises((TypeError,AttributeError)):
            enrich_ozon_preferred(conn,[p,None],reference)
        self.assertEqual(count,conn.execute('SELECT COUNT(*) FROM ozon_preferred_state').fetchone()[0])
        conn.close()

    def test_actual_sql_client_rejects_bad_batches(self):
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/ozon-preferred-client.js'
        subprocess.check_call(['node',str(path)])

    def test_client_background_settings_guard(self):
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/ozon-concurrent-settings-client.js'
        subprocess.check_call(['node',str(path)])
