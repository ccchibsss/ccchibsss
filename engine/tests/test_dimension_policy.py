import copy,itertools,json,pathlib,random,subprocess,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from dimension_policy import source_allowed,similar_oe,pick

class DimensionPolicyParity(unittest.TestCase):
    def test_actual_browser_authorization_and_pick(self):
        root=pathlib.Path(__file__).resolve().parents[2]
        path=root/'tests/dimension-policy-reference.js'
        numbers=['','000123','123','A00123','A123','A124','00000','0','AB-001 / 2','АБ00123','AB00123']
        similar=list(itertools.product(numbers,repeat=2))
        products=[dict(article='A',brand='B',oe_numbers='OE000123 / ABC'),dict(article='A',brand='B'),
                  dict(article='A',brand=''),dict(article='C',brand='B',oe_numbers='OE123'),
                  dict(artikul='A',brand='B'),dict(article='',artikul='A',brand='B'),
                  dict(article='X',brand='B',oe_list=['OE000123','OE999']),
                  dict(article='Z',brand='B',_dimensionAutoOeEvidence={'entries':[{'code':'OE123'}]}),{}]
        links=[dict(target=a,candidate=b,matchedCode=code) for a,b in itertools.product(products,repeat=2) for code in ('','OE123','WRONG')]
        links.append(dict(target=products[0],candidate=products[0],self=True))
        rng=random.Random(123);picks=[]
        for i in range(60):
            candidates=[dict(identity='A'+str(j%3),complete=True,tuple=dict(weight=rng.randint(1,5),length=rng.randint(1,5),width=rng.randint(1,5),height=rng.randint(1,5))) for j in range(12)]
            candidates+=[candidates[0],dict(identity='partial',complete=False,tuple={'weight':0})]
            picks.append(dict(candidates=candidates,maxWeight=3 if i%2 else None))
        for mode in ('auto','slash','comma','semicolon','newline','pipe'):
            expected=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps(dict(links=links,similar=similar,picks=picks,mode=mode)),text=True))
            for x,want in zip(links,expected['links']):
                candidate=x['target'] if x.get('self') else copy.deepcopy(x['candidate'])
                with self.subTest(link=x,mode=mode):self.assertEqual(source_allowed(x['target'],candidate,x.get('matchedCode',''),mode),want)
            for x,want in zip(similar,expected['similar']):self.assertEqual(similar_oe(*x),want)
            for x,want in zip(picks,expected['picks']):
                valid=(lambda t:float(t['weight'])<=x['maxWeight']) if x['maxWeight'] is not None else None
                self.assertEqual(pick(x['candidates'],valid),want)

    def test_actual_browser_oe_evidence(self):
        from dimension_oe import auto_evidence,current_codes,tuple_of,tuple_key,issue_free,target_signature
        from dimension_quarantine import DimensionQuarantine,compact
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/dimension-quarantine-reference.js'
        base=dict(article='A',brand='B',weight=1,length=10,width=5,height=2,oe_numbers='OE0001 / OE2')
        evidence=dict(weight=1,length=10,width=5,height=2,file='source.csv',row=7,identity='A|B')
        p={**base,'_dimensionAutoEvidence':evidence}
        rows=[base,p,{**p,'weight':2},{**p,'brand':'Changed'},{**p,'_dimensionAutoConflict':{}},
              {**p,'_dimensionOeReview':{}},{**p,'_dimensionImportIssues':{'weight':{'reason':'bad'}}},
              {**p,'_dimensionAutoEvidence':{**evidence,'file':''}},
              {**p,'oe_numbers':'','oe_norm':'X / Y'},
              {**p,'oeSource':'OE0001 / OE2'},
              {**p,'_dimensionAutoOeEvidence':{'identity':'WRONG|B','entries':[]}},
              {**p,'_dimensionAutoOeEvidence':{'identity':'A|B','entries':[{'code':'OE0001','pieces':['OE0001']}]}}]
        t=dict(weight=1,length=10,width=5,height=2)
        for mode in ('auto','slash','comma'):
            wants=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps(dict(operation='evidence',rows=rows,limits=[],tuple=t,oe_mode=mode)),text=True))
            model=DimensionQuarantine([],mode)
            for row,want in zip(rows,wants):
                row=copy.deepcopy(row)
                actual=dict(evidence=auto_evidence(row),codes=current_codes(row,False,mode),direct=current_codes(row,True,mode),
                            tuple=tuple_of(row),tupleKey=tuple_key(tuple_of(row)),signature=target_signature(model,row,mode),issueFree=issue_free(model,row,t))
                with self.subTest(row=row,mode=mode):self.assertEqual(json.loads(compact(actual)),want)
