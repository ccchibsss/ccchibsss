import copy
import json
import pathlib
import shutil
import subprocess
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine  # Registers the internal modules stored in the single engine file.
from hvc_enrichment import enrich_rows
import uc_engine as E


class HvcBrowserParity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node executes browser reference')
    def test_actual_browser_main_and_category_passes(self):
        parts = [
            ['P|B', {'artikul':'P','brand':'B','name':'pair','category':'Pair category','tnved':'111',
                     'barcode':'123','multiplicity':2,'image_url':'image',
                     '_dimensionEvidence':{'weight':2,'length':20,'width':20,'height':20}}],
            ['Q|B', {'artikul':'Q','brand':'B','name':'analog','category':'OE category',
                     '_dimensionEvidence':{'weight':1,'length':10,'width':10,'height':10}}]]
        reference = {'parts':parts, 'oe':[['OE1',{'name':'registry','category':'OE category','tnved':'222'}]],
                     'byArt':[['P|B',['OE1']],['Q|B',['OE1']]],'byOe':[['OE1',['P|B','Q|B']]]}
        root = pathlib.Path(__file__).resolve().parents[2]
        fields = ['name','applicability','category','tnved','weight','length','width','height',
                  'analog_list','group_articles','groupSize','barcode','multiplicity','image_url',
                  '_sources','_dimensionOeReview']
        for mode in ('artbrand','oe','auto'):
            for cat_mode in ('artbrand','oe','auto'):
                for columns in ({}, {'name':False,'weight':False,'analog_list':False}):
                    with self.subTest(mode=mode,cat_mode=cat_mode,columns=columns):
                        rows = [{'article':'P','brand':'B','oe_norm':'OE1','name':'','category':'',
                                 'weight':0,'length':0,'width':0,'height':0}]
                        fixture = dict(rows=rows,reference=reference,mode=mode,cat_mode=cat_mode,columns=columns)
                        browser = json.loads(subprocess.check_output(['node',str(root/'tests/hvc-reference.js')],
                            input=json.dumps(fixture), text=True))[0]
                        server = enrich_rows(copy.deepcopy(rows),reference,mode,cat_mode,columns,
                            '2026-01-01T00:00:00Z',E.num,E.rnd)[0]
                        self.assertEqual({k:server.get(k) for k in fields}, {k:browser.get(k) for k in fields})

    @unittest.skipUnless(shutil.which('node'), 'Node executes browser reference')
    def test_real_anomaly_gate_matches_server(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        variants = [
            ({}, {'weight':1,'length':10,'width':10,'height':10}, {}),
            ({'net_weight':2}, {'weight':1,'length':10,'width':10,'height':10}, {}),
            ({'net_weight':'bad'}, {'weight':1,'length':10,'width':10,'height':10}, {}),
            ({'net_weight':True}, {'weight':1,'length':10,'width':10,'height':10}, {}),
            ({}, {'weight':40,'length':1,'width':1,'height':1}, {}),
            ({'category':'Filter'}, {'weight':2,'length':10,'width':10,'height':10},
             {'limits':[{'category':'Filter','maxW':1,'maxL':100,'maxVol':100}]}),
            ({'volume':20,'_volumeExplicit':True}, {'weight':1,'length':10,'width':10,'height':10}, {}),
            ({'_sources':{'Прайс-лист':{'file':'old'}}}, {'weight':.5,'length':15,'width':10,'height':5}, {}),
            ({'length':12}, {'weight':1,'length':10,'width':10,'height':10}, {}),
        ]
        for extra, evidence, policy in variants:
            with self.subTest(extra=extra,evidence=evidence,policy=policy):
                reference = {'parts':[['P|B',{'artikul':'P','brand':'B','_dimensionEvidence':evidence}]],
                             'oe':[], 'byArt':[], 'byOe':[]}
                rows = [{'article':'P','brand':'B','weight':0,'length':0,'width':0,'height':0,**extra}]
                fixture = dict(rows=rows,reference=reference,mode='artbrand',cat_mode='artbrand',policy=policy)
                browser = json.loads(subprocess.check_output(['node',str(root/'tests/hvc-reference.js')],
                    input=json.dumps(fixture),text=True))[0]
                def allowed(p,t):
                    product = dict(p)
                    product['dimension_context'] = json.dumps({'sources':p.get('_sources',{}),
                        'explicitVolume':p.get('_volumeExplicit',False)})
                    return E._dimension_candidate_allowed(product,tuple(t[k] for k in ('length','width','height','weight')),policy)
                server = enrich_rows(rows,reference,'artbrand','artbrand',{},'2026-01-01T00:00:00Z',E.num,E.rnd,allowed)[0]
                keys = ['weight','length','width','height','_sources','_dimensionOeReview']
                self.assertEqual({k:server.get(k) for k in keys},{k:browser.get(k) for k in keys})

class HvcSkuSpecificCache(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node executes browser reference')
    def test_identical_oe_sets_never_reuse_self_excluding_analogs(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        keys = ['A|B', 'B|B', 'C|B']
        reference = dict(parts=[[key, dict(artikul=key[0], brand='B',multiplicity=1)] for key in keys],
                         oe=[['OE1', {}]], byArt=[[key, ['OE1']] for key in keys],
                         byOe=[['OE1', keys]])
        # Previously B/C reused A's cached list and included their own SKU.
        for order in (keys, list(reversed(keys)), ['B|B', 'A|B', 'C|B']):
            rows = [dict(article=key[0], brand='B', oe_norm='OE1',multiplicity=0) for key in order]
            fixture = dict(rows=rows, reference=reference, mode='auto', cat_mode='artbrand')
            js = json.loads(subprocess.check_output(['node',str(root/'tests/hvc-reference.js')],input=json.dumps(fixture),text=True))
            py = enrich_rows(copy.deepcopy(rows),reference,'auto','artbrand',{},'2026-01-01T00:00:00Z',E.num,E.rnd)
            self.assertEqual(py,js)
            for row in js:
                own = row['article']
                self.assertEqual(row['analog_list'], ', '.join(key[0] for key in keys if key[0]!=own))
                self.assertEqual(row['group_articles'].split(' / ')[0], own)
                self.assertEqual(len(set(row['group_articles'].split(' / '))),3)

    @unittest.skipUnless(shutil.which('node'), 'Node executes browser reference')
    def test_shared_multi_oe_candidate_cap_preserves_order(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        keys = ['P'+str(i)+'|B' for i in range(45)]
        second = keys[40:]+keys[:40]
        reference = dict(parts=[[key,dict(artikul=key.split('|')[0],brand='B',multiplicity=1)] for key in keys],
                         oe=[['OE1',{}],['OE2',{}]],byArt=[[key,['OE1','OE2']] for key in keys],
                         byOe=[['OE1',keys],['OE2',second]])
        rows = [dict(article=key.split('|')[0],brand='B',oe_norm='OE1 / OE2') for key in reversed(keys)]
        fixture=dict(rows=rows,reference=reference,mode='auto',cat_mode='artbrand')
        js=json.loads(subprocess.check_output(['node',str(root/'tests/hvc-reference.js')],input=json.dumps(fixture),text=True))
        py=enrich_rows(copy.deepcopy(rows),reference,'auto','artbrand',{},'2026-01-01T00:00:00Z',E.num,E.rnd)
        self.assertEqual(js,py)
        for row in js:
            expected=[]
            for key in keys[:40]+second[:40]:
                article=key.split('|')[0]
                if article!=row['article'] and article not in expected and len(expected)<40:expected.append(article)
            self.assertEqual(row['analog_list'],', '.join(expected))
