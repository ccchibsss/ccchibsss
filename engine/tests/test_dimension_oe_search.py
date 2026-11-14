import copy,json,pathlib,subprocess,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from dimension_oe_search import OeSearch
from dimension_quarantine import compact

class OeSearchParity(unittest.TestCase):
    def test_actual_browser_search(self):
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/dimension-quarantine-reference.js'
        target=dict(article='A',brand='B',category='C',weight=1000,length=10,width=10,height=10,dimensionAnomalyBlocked=True,oe_numbers='OE123')
        donor=dict(article='D',brand='B',category='C',weight=1,length=10,width=10,height=10,oe_numbers='OE123')
        ev=dict(weight=1,length=10,width=10,height=10,file='donor.csv',row=3,identity='D|B')
        part=dict(artikul='H',brand='B',category='C',oe_numbers='OE123',_dimensionEvidence={**ev,'identity':'H|B','singleRow':True,'oeCodes':['OE123']})
        references=[{},dict(byOe=[['OE123',['D|B']]]),dict(parts=[['H|B',part]],byOe=[['OE123',['H|B']]],oe=[['OE123',{}]])]
        scenarios=[([target],r) for r in references]
        scenarios += [([target,donor],references[1]),([target,{**donor,'_dimensionAutoEvidence':ev}],references[1]),
                      ([target,{**donor,'weight':2},{**donor,'article':'E','weight':1}],dict(byOe=[['OE123',['D|B','E|B']]])),
                      ([target,{**donor,'weight':None,'width':None}],references[1]),
                      ([target,{**donor,'dimensionAnomalyBlocked':True}],references[1]),
                      ([target,{**donor,'oe_numbers':'WRONG'}],references[1]),
                      ([{**target,'oe_numbers':''},{**donor,'article':'A','oe_numbers':''}],{}),
                      ([target,{**donor,'_dimensionOeReview':{}}],references[1]),
                      ([{**target,'net_weight':5},donor],references[1]),
                      ([target]+[{**donor,'article':'D'+str(i),'weight':1+i/100} for i in range(66)],dict(byOe=[['OE123',['D'+str(i)+'|B' for i in range(66)]]]))]
        hvc_ref=references[2]
        scenarios += [([target,{**donor,'article':'H','_dimensionAutoEvidence':{**ev,'identity':'H|B'}}],hvc_ref),
                      ([target,{**donor,'article':'H'}, {**donor,'article':'H'}],hvc_ref),
                      ([target,{**donor,'article':'H','excluded':True}],hvc_ref),
                      ([target,{**donor,'_dimensionAutoEvidence':{**ev,'weight':2}}],references[1]),
                      ([target,{**donor,'_dimensionAutoConflict':{}},{**donor,'article':'E','weight':2}],dict(byOe=[['OE123',['D|B','E|B']]])),
                      ([{**target,'volume':90,'_volumeExplicit':True},donor],references[1]),
                      ([{**target,'oe_numbers':'OE123 / SECOND'},donor],dict(parts=[['H|B',part]],byOe=[['OE123',['D|B','H|B']],['SECOND',['H|B']]])),
                      ([target,{**donor,'article':'A','oe_numbers':'WRONG'}],{})]
        for rows,reference in scenarios:
            for automatic in (False,True):
                data=dict(operation='search',rows=rows,reference=reference,targets=[0],limits=[],automatic=automatic)
                expected=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps(data),text=True))
                result=OeSearch(rows,reference,[]).find([0],automatic)
                with self.subTest(rows=len(rows),reference=reference,automatic=automatic):self.assertEqual(json.loads(compact(result)),expected)
