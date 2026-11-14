import copy
import json
import pathlib
import shutil
import subprocess
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
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
