import copy,json,pathlib,subprocess,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from dimension_quarantine import DimensionQuarantine, compact

class DimensionQuarantineParity(unittest.TestCase):
    def test_actual_browser_quarantine(self):
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/dimension-quarantine-reference.js'
        limits=[dict(category='Фильтры',maxW=15,maxL=80,maxVol=50)]
        base=dict(article='A',brand='B',category='  ФИЛЬТРЫ  ',weight=1,length=10,width=10,height=10)
        rows=[{},base,{**base,'weight':20},{**base,'length':90},{**base,'width':-2},
            {**base,'weight':'bad'},{**base,'weight':True},{**base,'net_weight':2},
            {**base,'weight':'1 234,50'},{**base,'volume':90,'_volumeExplicit':True},
            {**base,'_sources':{'volume':{'file':'f'}},'volume':9},
            {**base,'weight':50,'length':1,'width':1,'height':1},
            {**base,'weight':0.5,'length':15,'height':5,'_sources':{'Прайс-лист':{'file':'old'}}},
            {**base,'excluded':True,'weight':100,'dimensionAnomalyAck':{'signature':'old'}},
            {**base,'_dimensionImportIssues':{'weight':{'file':'bad.csv','value':'oops','reason':'не число','field':'Вес','at':'now'}}},
            {**base,'weight':0,'excluded':True,'_dimensionImportIssues':{'weight':{'reason':'нет'}}},
            {**base,'dimensionAnomalyAck':{'signature':'old'},'dimensionAnomalySignature':'old'},
            {**base,'weight':20,'dimensionAnomalySignature':'old','dimensionAnomalyAck':{'signature':'old'}}]
        model=DimensionQuarantine(limits)
        acked=model.apply({**base,'weight':20},'2026-11-08T00:00:00Z')
        acked['dimensionAnomalyAck']={'signature':acked['dimensionAnomalySignature']}
        hard=model.apply({**base,'net_weight':2},'2026-11-08T00:00:00Z');hard['dimensionAnomalyAck']={'signature':hard['dimensionAnomalySignature']}
        review={**base,'_dimensionOeReview':{'oe':'A/B','source':'file','oeProofVersion':1},'oe_numbers':'A/B / C','oeSource':'A/B / C'}
        rows += [review,{**review,'_dimensionAutoOeEvidence':{'identity':'OTHER|B','entries':[]}},
                 {**review,'_dimensionAutoOeEvidence':{'identity':'A|B','entries':[{'code':'AB','pieces':['A','B']}]}}]
        rows += [{**base,'weight':1e21},{**base,'length':1e200,'height':1e200}, {**base,'weight':'NaN'},{**base,'net_weight':1e-7}, {**base,'oe_numbers':'A / A','oe_list':'A','_dimensionOeReview':{'oe':'A','source':'file'}}]
        rows += [acked,{**acked,'weight':21},hard]
        expected=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps(dict(rows=rows,limits=limits)),text=True))
        for p,want in zip(rows,expected):
            with self.subTest(row=p):self.assertEqual(json.loads(compact(model.apply(p,'2026-11-08T00:00:00Z'))),want)

    def test_sql_persistence_and_client(self):
        import sqlite3
        from uc_engine import quarantine_dimension_rows
        conn=sqlite3.connect(':memory:')
        p=dict(article='A',brand='B',weight=900,length=10,width=10,height=10)
        result=quarantine_dimension_rows(conn,[p],[],timestamp='2026-11-08T00:00:00Z')
        fields=result['rows'][0]['fields']
        self.assertTrue(fields['dimensionAnomalyBlocked'])
        self.assertEqual(json.loads(conn.execute('SELECT data FROM dimension_quarantine_state').fetchone()[0]),fields)
        p.update(fields);p['weight']=1
        result=quarantine_dimension_rows(conn,[p],[],timestamp='2026-11-08T00:00:00Z')
        self.assertFalse(result['rows'][0]['fields']['dimensionAnomalyBlocked'])
        self.assertIn('dimensionAnomalySignature',result['rows'][0]['removed'])
        conn.close()
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/dimension-quarantine-client.js'
        subprocess.check_call(['node',str(path)])

    def test_actual_browser_confirmation_lifecycle(self):
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/dimension-quarantine-reference.js'
        model=DimensionQuarantine([]);at='2026-11-08T00:00:00Z'
        base=dict(article='A',brand='B',category='C',weight=900,length=10,width=10,height=10)
        current=model.apply(base,at)
        review=model.apply({**base,'_dimensionOeReview':{'oe':'A1','source':'f'}},at)
        rows=[{},base,current,{**current,'weight':901},review,model.apply({**base,'net_weight':1000},at)]
        for approved in (False,True):
            expected=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps(dict(operation='confirm',approved=approved,rows=rows,limits=[])),text=True))
            for p,want in zip(rows,expected):
                output,result=model.confirm(p,at,approved)
                with self.subTest(row=p,approved=approved):
                    self.assertEqual(json.loads(compact(dict(row=output,log=[result['log']] if 'log' in result else []))),want)
        output,status=model.confirm(current,at,True,'wrong-signature')
        self.assertEqual(status['status'],'stale')
        self.assertNotIn('dimensionAnomalyAck',output)
        import sqlite3
        from uc_engine import confirm_dimension_row
        conn=sqlite3.connect(':memory:')
        r=confirm_dimension_row(conn,current,[],approved=True,expected_signature=current['dimensionAnomalySignature'],timestamp=at)
        self.assertEqual(r['result']['status'],'confirmed')
        self.assertFalse(r['fields']['dimensionAnomalyBlocked'])
        self.assertEqual(json.loads(conn.execute('SELECT data FROM dimension_quarantine_state').fetchone()[0]),r['fields'])
        conn.close()

    def test_confirmation_client_and_saved_product_routing(self):
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/dimension-confirm-client.js'
        subprocess.check_call(['node',str(path)])

    def test_actual_browser_unit_fixes(self):
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/dimension-quarantine-reference.js'
        limits=[dict(category='C',maxW=15,maxL=80,maxVol=50)]
        model=DimensionQuarantine(limits);at='2026-11-08T00:00:00Z'
        base=dict(article='A',brand='B',category='C',weight=1,length=10,width=10,height=10,volume=1)
        variants=[base,{**base,'weight':1500},{**base,'weight':1500,'net_weight':2},
            {**base,'weight':1500,'net_weight':'bad'},{**base,'length':300,'width':100,'height':100,'_volumeExplicit':False},
            {**base,'length':300,'width':100,'height':100,'volume':1000,'_volumeExplicit':True},
            {**base,'length':300,'width':100,'height':100,'weight':1500,'_volumeExplicit':False},
            {**base,'weight':1500,'_dimensionOeReview':{'oe':'OLD','source':'previous','history':[{'oe':'earliest'}]},'_sources':{'Вес':{'file':'old'}}},
            {**base,'weight':1500,'_dimensionOeReview':{'oe':'OLD','history':[{'i':i} for i in range(25)]}}]
        rows=[model.apply(p,at) for p in variants]
        rows += [{**rows[1],'weight':1600}, {**rows[1],'dimensionAnomalyBlocked':False}]
        signatures=[p.get('dimensionAnomalySignature','') for p in rows]
        labels={'weight':'Вес','length':'Длина','width':'Ширина','height':'Высота'}
        for approved in (False,True):
            expected=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps(dict(operation='fix',approved=approved,rows=rows,limits=limits,signatures=signatures,labels=labels)),text=True))
            for p,sig,want in zip(rows,signatures,expected):
                output,result=model.fix_units(p,at,sig,approved,labels)
                with self.subTest(row=p,approved=approved):
                    self.assertEqual(json.loads(compact(dict(row=output,log=[result['log']] if 'log' in result else []))),want)

    def test_unit_fix_persistence_and_client(self):
        import sqlite3
        from uc_engine import fix_dimension_units
        model=DimensionQuarantine([]);at='2026-11-08T00:00:00Z'
        p=model.apply(dict(article='A',brand='B',weight=4000,length=10,width=10,height=10,volume=1),at)
        item={'row':p,'signature':p['dimensionAnomalySignature']}
        conn=sqlite3.connect(':memory:')
        conn.executescript("CREATE TABLE products(article TEXT,brand TEXT,weight REAL,length REAL,width REAL,height REAL,volume REAL);INSERT INTO products VALUES('A','B',4000,10,10,10,1);")
        preview=fix_dimension_units(conn,[item],[],timestamp=at)
        self.assertEqual(preview['rows'][0]['result']['status'],'ready')
        self.assertEqual(conn.execute('SELECT weight FROM products').fetchone()[0],4000)
        stale={'row':{**p,'weight':5000},'signature':item['signature']}
        self.assertEqual(fix_dimension_units(conn,[stale],[],approved=True,timestamp=at)['rows'][0]['result']['status'],'skipped')
        out=fix_dimension_units(conn,[item],[],approved=True,timestamp=at)
        self.assertEqual(conn.execute('SELECT weight FROM products').fetchone()[0],4)
        self.assertEqual(json.loads(conn.execute('SELECT data FROM dimension_unit_fix_state').fetchone()[0]),out['rows'][0]['fields'])
        conn.close()
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/dimension-unit-fix-client.js'
        subprocess.check_call(['node',str(path)])
