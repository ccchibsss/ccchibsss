import json,pathlib,sqlite3,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine as E

class ExportCursor(unittest.TestCase):
    def test_joined_presentation_and_constant_query_count(self):
        conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
        try:
            conn.executescript('CREATE TABLE products(article TEXT,brand TEXT,name TEXT,PRIMARY KEY(article,brand));'
                'CREATE TABLE eco_results(article TEXT,brand TEXT,total REAL,profit REAL,margin REAL,roi REAL,break_even REAL,target REAL,fields_json TEXT,PRIMARY KEY(article,brand));'
                'CREATE TEMP TABLE export_cells(article TEXT,brand TEXT,data TEXT,PRIMARY KEY(article,brand));')
            conn.executemany('INSERT INTO products VALUES(?,?,?)',[(str(i),'B','Product') for i in range(2000)])
            conn.executemany('INSERT INTO eco_results(article,brand,profit,fields_json) VALUES(?,?,?,?)',[(str(i),'B',2,json.dumps({'extra':i,'name':'must not override'})) for i in range(2000)])
            conn.executemany('INSERT INTO export_cells VALUES(?,?,?)',[(str(i),'B',json.dumps({'name':'saved '+str(i),'__export_order':1999-i})) for i in range(2000)])
            statements=[];conn.set_trace_callback(statements.append)
            rows=E.export_catalog_records(conn)
            self.assertEqual(len(rows),2000);self.assertEqual(rows[0]['article'],'1999');self.assertEqual(rows[-1]['article'],'0')
            self.assertEqual(rows[0]['name'],'saved 1999');self.assertEqual(rows[0]['extra'],1999)
            self.assertEqual(len([q for q in statements if q.lstrip().upper().startswith('SELECT')]),2)
            self.assertEqual([r['article'] for r in E.export_catalog_records(conn,[('2','B'),('3','B')])],['3','2'])
            conn.execute('DELETE FROM export_cells');self.assertEqual(E.export_catalog_records(conn),[])
            conn.execute('DROP TABLE export_cells');rows=E.export_catalog_records(conn,[('2','B')])
            self.assertEqual(rows[0]['name'],'Product');self.assertEqual(rows[0]['extra'],2)
        finally:conn.close()
