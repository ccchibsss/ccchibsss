"""Composed browser/Python+SQLite enrichment smoke on repository demo SKUs.

Donor/category/Ozon references are explicit synthetic fixtures, NOT user data.
Each stage consumes the previous stage's output, including the second run.
"""
import copy,csv,json,pathlib,sqlite3,subprocess,sys,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'engine'))
import uc_engine as E
import uc_engine  # Registers the internal modules stored in the single engine file.
from hvc_enrichment import norm

AT='2026-01-01T00:00:00Z'


def browser(name,data):
    return json.loads(subprocess.check_output(['node',str(ROOT/'tests'/name)],input=json.dumps(data),text=True))


def apply_response(rows,response):
    assert len(rows)==len(response['rows'])
    for p,r in zip(rows,response['rows']):
        assert (p['article'],p['brand'])==(r['article'],r['brand'])
        for k in r.get('removed',[]):p.pop(k,None)
        p.update(r['fields'])


class EnrichmentCatalogFlow(unittest.TestCase):
    maxDiff=None
    def test_invalid_later_row_rolls_back_each_enrichment_batch(self):
        reference={'rows':[['Фильтры','Фильтр масляный','1234567890']],'revision':'test','source':'test.csv'}
        p=dict(article='A',brand='B',name='Фильтр масляный',category='Фильтры',category_type='Фильтр масляный',markRequired=True,markStatus='ошибка',markCode='12345678')
        operations=[
            lambda c:E.enrich_category_tnved(c,[p,None],reference),
            lambda c:E.enrich_category_kinds(c,[p,None],reference,{'version':'ctx'}),
            lambda c:E.enrich_name_categories(c,[p,None],{'version':'ctx','categories':[],'rules':[],'heads':[]}),
            lambda c:E.enrich_rule_rows(c,[p,None],[],{}),
            lambda c:E.check_mark_status_rows(c,[p,None],{'autoHideMark':True})]
        for operation in operations:
            conn=sqlite3.connect(':memory:')
            conn.execute('CREATE TABLE products(article TEXT,brand TEXT,category TEXT,category_type TEXT,tnved TEXT,visible TEXT,visible_reason TEXT,dimension_context TEXT)')
            conn.execute("INSERT INTO products VALUES('A','B','','','','1','','{}')")
            # Leave caller work uncommitted: a failed enrichment must not
            # roll this insertion back or commit it behind the caller's back.
            before=conn.execute('SELECT * FROM products').fetchall()
            try:
                with self.assertRaises((TypeError,AttributeError)):
                    operation(conn)
                self.assertEqual(conn.execute('SELECT * FROM products').fetchall(),before)
                self.assertEqual([r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")],['products'])
                self.assertTrue(conn.in_transaction)
                conn.rollback()
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM products').fetchone()[0],0)
            finally:conn.close()

    def test_hvc_write_failure_rolls_back_reference_and_rows(self):
        conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
        fields='name applicability category tnved weight length width height multiplicity image_url barcode analog_list group_articles'.split()
        conn.execute('CREATE TABLE products(article TEXT,brand TEXT,'+','.join(k+' TEXT' for k in fields)+',dimension_context TEXT,dimension_review TEXT)')
        conn.executemany("INSERT INTO products(article,brand,dimension_context,dimension_review) VALUES(?,'B','{}','{}')",[('A',),('B',)])
        conn.commit()
        conn.execute("CREATE TRIGGER fail_hvc BEFORE UPDATE ON products WHEN NEW.article='B' BEGIN SELECT RAISE(ABORT,'test HVC failure'); END")
        before=[tuple(r) for r in conn.execute('SELECT * FROM products')]
        reference={'parts':[['A|B',{'artikul':'A','brand':'B','name':'New name'}]],'oe':[],'byArt':[],'byOe':[]}
        try:
            with self.assertRaises(sqlite3.IntegrityError):E.enrich_hvc(conn,reference,'artbrand','artbrand')
            self.assertEqual([tuple(r) for r in conn.execute('SELECT * FROM products')],before)
            self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='hvc_reference'").fetchone())
        finally:conn.close()

    def test_repository_demo_catalog_composed_flow(self):
        with (ROOT/'UC_unit_economics_OZON_2026-11-06_filtered.csv').open(encoding='utf-8-sig',newline='') as source:
            # The checked-in demo export contains literal backslash-r/backslash-n.
            text=source.read().replace('\\r\\n','\n')
        samples=list(csv.DictReader(text.splitlines(),delimiter=';'))
        self.assertEqual(len(samples),12)
        categories=[['Фильтры','Фильтр масляный','1234567890'],['Топливо','Насос топливный','2345678901'],['Двигатель','Насос водяной','3456789012']]
        pairs=browser('ozon-preferred-reference.js',{'categoryRows':categories,'rows':[]})['pairs']
        names=['Фильтр масляный','Насос топливный','Насос водяной']
        rows=[];parts=[];by_art=[];by_oe=[];registry=[]
        for i,sample in enumerate(samples):
            article=sample['Артикул'];name=names[i%3];category=categories[i%3][0];oe='OE'+str(i)
            rows.append(dict(article=article,brand='DEMO',name='',category='',tnved='',applicability='',
                oe_norm=oe,oe_numbers=oe,weight=0,length=0,width=0,height=0,volume=0,
                multiplicity=1,image_url='',barcode='',analog_list='',group_articles=article,
                _sources={},cost=E.num(sample['Себестоимость, ₽']),price=0,stock=10))
            donor={'artikul':article,'brand':'DEMO','name':name,'category':category,'applicability':'Vehicle Model',
                '_dimensionEvidence':{k:E.num(sample[h]) for k,h in [('weight','Вес, кг'),('length','Длина, см'),('width','Ширина, см'),('height','Высота, см')]}}
            key=norm(article)+'|DEMO'
            parts.append([key,donor]);by_art.append([key,[oe]]);by_oe.append([oe,[key]])
            registry.append([oe,{'name':name,'category':category}])
        # Explicit/manual/blocked inputs are carried across all later stages.
        rows[1].update(name='Ручное название',category='Ручная категория',_categoryNameExplicit=True)
        rows[2].update(category_type='Ручной вид',tnved='9999999999')
        rows[3].update(ozon_type='Ручной тип',ozon_category='Ручная категория Ozon',ozon_type_src='manual')
        rows[4].update(_categoryTypeCleared=True)
        rows[5].update(markRequired=True,markStatus='ошибка',markCode='12345678')
        rows[6].update(dimensionAnomalyBlocked=True)
        reference=dict(parts=parts,oe=registry,byArt=by_art,byOe=by_oe)
        rules=[dict(kind='enrich',enabled=True,field='name',op='regex',value='фильтр|насос',target_val='price',formula='round(num(p.cost)*1.3,2)')]
        catref={'rows':categories,'revision':'test','source':'test.csv'}
        policies=[dict(enabled=True,field='name',op='contains',value='ручное',action='warn')]
        for mode in ['auto','artbrand','oe']:
            with self.subTest(mode=mode):
                conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
                hvcfields='name applicability category tnved weight length width height multiplicity image_url barcode analog_list group_articles'.split()
                conn.execute('CREATE TABLE products(article TEXT,brand TEXT,'+','.join(k+' '+('REAL' if k in ['weight','length','width','height','multiplicity'] else 'TEXT') for k in hvcfields)+',visible TEXT,visible_reason TEXT,category_type TEXT,ozon_category TEXT,ozon_type TEXT,dimension_context TEXT,dimension_review TEXT,PRIMARY KEY(article,brand))')
                js=copy.deepcopy(rows);py=copy.deepcopy(rows)
                for p in py:
                    keys=['article','brand']+hvcfields+['dimension_context','dimension_review']
                    data={**p,'dimension_context':json.dumps({'oeNorm':p['oe_norm'],'sources':p['_sources'],'blocked':p.get('dimensionAnomalyBlocked',False)}),'dimension_review':'{}'}
                    conn.execute('INSERT INTO products('+','.join(keys)+') VALUES('+','.join('?' for _ in keys)+')',[data[k] for k in keys])
                try:
                    for run in range(2):
                        js=browser('hvc-reference.js',dict(rows=js,reference=reference,mode=mode,cat_mode='artbrand'))
                        with patch.object(E.time,'strftime',return_value=AT):response=E.enrich_hvc(conn,reference,mode,'artbrand')
                        for p,r in zip(py,response['rows']):
                            p.update({k:v for k,v in r.items() if v is not None or k in p})
                        self.assertEqual([{k:(p.get(k),j.get(k)) for k in set(p)|set(j) if p.get(k)!=j.get(k) or (k in p)!=(k in j)} for p,j in zip(py,js)],[{} for _ in py],('hvc',mode,run))
                        self.assertGreaterEqual(sum(p['weight']>0 for p in py),10)
                        self.assertTrue(all(p['name'] for p in py))
                        js=browser('enrichment-rules-reference.js',dict(rows=js,rules=rules,context={'version':'ctx'}))
                        apply_response(py,E.enrich_rule_rows(conn,py,rules,{'version':'ctx'}))
                        self.assertEqual(py,js,('rules',mode,run))
                        js=browser('category-kind-reference.js',dict(rows=categories,products=js,revision='test',enabled=True))
                        with patch.object(E.time,'strftime',return_value=AT):apply_response(py,E.enrich_category_kinds(conn,py,catref,{'version':'ctx'}))
                        self.assertEqual(py,js,('kind',mode,run))
                        js=[r['row'] for r in browser('ozon-preferred-reference.js',dict(rows=js,categoryRows=categories,registry={'oe':{}}))['results']]
                        ozref=dict(registry={'oe':{}},pairs=pairs,category_rows=categories,category_revision='test',identity={'rows':py})
                        apply_response(py,E.enrich_ozon_preferred(conn,py,ozref))
                        self.assertEqual([{k:(p.get(k),j.get(k)) for k in set(p)|set(j) if p.get(k)!=j.get(k) or (k in p)!=(k in j)} for p,j in zip(py,js)],[{} for _ in py],('ozon',mode,run))
                        js=[r['row'] for r in browser('category-tnved-reference.js',dict(rows=js,reference=catref))]
                        with patch.object(E.time,'strftime',return_value=AT):apply_response(py,E.enrich_category_tnved(conn,py,catref))
                        self.assertEqual(py,js,('tnved',mode,run))
                        js=browser('dimension-quarantine-reference.js',dict(rows=js,limits=[]))
                        apply_response(py,E.quarantine_dimension_rows(conn,py,[],timestamp='2026-11-08T00:00:00Z'))
                        self.assertEqual(py,js,('quarantine',mode,run))
                        js=[r['row'] for r in browser('mark-status-reference.js',dict(rows=js,settings={'autoHideMark':True}))]
                        apply_response(py,E.check_mark_status_rows(conn,py,{'autoHideMark':True}))
                        self.assertEqual(py,js,('mark',mode,run))
                        js=browser('product-policies-reference.js',dict(rows=js,rules=policies))
                        apply_response(py,E.apply_product_policies(conn,py,policies))
                        self.assertEqual(py,js,('policies',mode,run))
                        self.assertEqual(py[1]['name'],'Ручное название')
                        self.assertEqual(py[1]['category'],'Ручная категория')
                        self.assertEqual(py[2]['tnved'],'9999999999')
                        self.assertEqual(py[3]['ozon_type_src'],'manual')
                        self.assertEqual(py[3]['ozon_type'],'Ручной тип')
                finally:conn.close()
