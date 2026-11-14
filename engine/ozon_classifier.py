"""Strict Ozon OE/applicability classification using a canonical historical pair list."""
import re
from category_tnved import text
from ozon_reference import OzonReference

MISSING=object()
CAT_KEYS=('ozon_category','ozonCategory','category_ozon','categoryOzon','category','cat')
TYPE_KEYS=('ozon_type','ozonType','type_ozon','typeOzon','type')
NESTED=('ozon','ozon_mapping','ozonMapping')
SIGNAL_KEYS=CAT_KEYS[:4]+TYPE_KEYS[:4]
def string(v): return text(v).strip() if not isinstance(v,(dict,list)) else '[object Object]' if isinstance(v,dict) else ','.join(map(string,v))
def norm(v): return re.sub('[^0-9a-zа-я]+',' ',string(v).lower().replace('ё','е')).strip()
def norm_oe(v): return re.sub('[^0-9A-ZА-ЯЁ]','',string(v).upper())
def hvc_key(v): return re.sub(r'\s+',' ',re.sub(r'[^0-9a-zа-яё`\-\s]','',string(v).replace("'",'').lower())).strip()
def first(v,keys): return next((v[k] for k in keys if string(v.get(k))),'')
def conflict(v): return isinstance(v,dict) and (bool(v.get('conflict') or v.get('ozon_conflict')) or any(isinstance(v.get(k),dict) and (v[k].get('conflict') or v[k].get('ozon_conflict')) for k in ('ozon','ozon_mapping')))
def declared(v):
    if isinstance(v,list): return len(v)>=2 and bool(string(v[0]) and string(v[1]))
    if not isinstance(v,dict): return False
    return any(declared(v.get(k)) for k in NESTED) or bool(string(first(v,CAT_KEYS)) and string(first(v,TYPE_KEYS)))
def signal(v):
    if isinstance(v,str): return bool(v.strip())
    if isinstance(v,list): return any(map(signal,v))
    if not isinstance(v,dict): return False
    return any(string(v.get(k)) for k in SIGNAL_KEYS) or any(signal(v.get(k)) for k in NESTED)
def tokens(p):
    out=[];seen=set()
    def add(v):
        if isinstance(v,list):
            for x in v: add(x)
            return
        for raw in re.split(r'[/;,\r\n|]+',string(v)):
            raw=raw.strip();key=norm_oe(raw)
            if key and key not in seen: seen.add(key);out.append(dict(raw=raw,key=key,hvc=hvc_key(raw)))
    for k in ('oe_numbers','oe_list','oe_norm','oe_number','oe'): add(p.get(k))
    return out

def get(store,keys):
    if not isinstance(store,dict): return MISSING
    return next((store[k] for k in keys if k and k in store),MISSING)

class OzonClassifier:
    def __init__(self,pairs,tree=None,scope='auto'):
        self.reference=OzonReference(tree,scope)
        self.groups={}
        for category,typ in pairs: self.groups.setdefault(norm(typ),[]).append({'category':category,'type':typ})
    def pair(self,v):
        if not v: return None
        if isinstance(v,list): return self.pair({'category':v[0],'type':v[1]}) if len(v)>=2 else self.pair(v[0])
        if isinstance(v,str):
            if self.reference.has_data:
                hit=self.reference.unique_type(v)
                return {'category':hit['cat'],'type':hit['name']} if hit else None
            matches=self.groups.get(norm(v),[])
            return matches[0] if len(matches)==1 else None
        if not isinstance(v,dict) or conflict(v): return None
        nested=first(v,NESTED)
        if nested:
            pair=self.pair(nested)
            if pair: return pair
            if declared(nested) or signal(nested) or conflict(nested): return None
        cat,typ=first(v,CAT_KEYS),first(v,TYPE_KEYS)
        if self.reference.has_data:
            hit=self.reference.find_pair(cat,typ) if cat else {'status':'valid','item':self.reference.unique_type(typ)}
            item=hit.get('item')
            return {'category':item['cat'],'type':item['type']} if hit['status']=='valid' and item else None
        matches=self.groups.get(norm(typ),[])
        if not matches: return None
        if not cat: return matches[0] if len(matches)==1 else None
        # Historical dictionary favors the first category; alternatives must be unique.
        if norm(cat)==norm(matches[0]['category']): return matches[0]
        same=[m for m in matches if norm(m['category'])==norm(cat)]
        return same[0] if len(same)==1 else None
    def classify(self,p,registry=None,applicability=None):
        ts=tokens(p);links=[]
        def none(reason):
            return dict(category='',type='',source='none',basis='none',score=0,matched=len(links),confidence='none',reason=reason,oe=links[0]['token']['raw'] if links else '',applicability='',tokens=len(ts))
        def success(hit,basis):
            return {**hit['mapping'],'source':'auto','basis':basis,'score':100 if basis=='oe' else 90,'matched':len(links),'confidence':'high','reason':'','oe':hit['oe'],'applicability':hit.get('applicability','')}
        if not ts: return none('no_oe')
        if registry is None: return none('no_oe_registry')
        stores=[registry[k] for k in ('oe','oeRegistry','oe_registry','registry') if registry.get(k)] or [registry]
        for token in ts:
            for store in stores:
                rec=get(store,[token['raw'],token['key'],token['key'].lower(),token['hvc'],norm(token['raw'])])
                if rec is not MISSING: links.append(dict(token=token,rec=rec));break
        if not links: return none('oe_not_found')
        if any(conflict(x['rec']) for x in links): return none('conflicting_oe_mappings')
        direct=[]
        for link in links:
            rec=link['rec'];pair=self.pair(rec)
            if pair: direct.append({'mapping':pair,'oe':link['token']['raw']})
            elif declared(rec) or signal(rec): return none('invalid_oe_mapping')
        def unique(hits):
            result=[]
            for hit in hits:
                if not any(x['mapping']==hit['mapping'] for x in result): result.append(hit)
            return result
        direct=unique(direct)
        if len(direct)>1: return none('conflicting_oe_mappings')
        if direct: return success(direct[0],'oe')
        hits=[];bad=False;ambiguous=False
        for link in links:
            rec=link['rec'] if isinstance(link['rec'],dict) else {};apps=[];seen=set()
            def add(v):
                if isinstance(v,list):
                    for x in v: add(x)
                    return
                if isinstance(v,dict): v=first(v,('key','value','applicability'))
                v=string(v);key=norm(v)
                if key and key not in seen: seen.add(key);apps.append(v)
            for k in ('applicability','applicability_text','vehicle_applicability','vehicle'): add(rec.get(k))
            add(p.get('applicability'))
            appstores=[rec[k] for k in ('ozonByApplicability','applicabilityMap','applicabilityReference') if rec.get(k)]
            appstores+=[applicability or {}]+[registry[k] for k in ('ozonApplicability','applicabilityReference','applicabilityMap','applicabilityDirectory') if registry.get(k)]
            for app in apps:
                tok=link['token'];groups=[[tok['key']+'|'+norm(app),tok['key']+'::'+norm(app),tok['hvc']+'|'+norm(app)],[app,norm(app)]]
                for keys in groups:
                    found=None;invalid=False;clash=False
                    for store in appstores:
                        raw=get(store,keys)
                        if raw is MISSING: continue
                        if conflict(raw): clash=True;break
                        pair=self.pair(raw)
                        if not pair and (declared(raw) or signal(raw)): invalid=True;break
                        if pair and found and pair!=found: clash=True;break
                        if pair: found=pair
                    if clash or invalid or found:
                        ambiguous|=clash;bad|=invalid
                        if found: hits.append(dict(mapping=found,oe=tok['raw'],applicability=app))
                        break
        if ambiguous: return none('conflicting_applicability_mappings')
        if bad: return none('invalid_applicability_mapping')
        hits=unique(hits)
        if len(hits)>1: return none('conflicting_applicability_mappings')
        return success(hits[0],'applicability') if hits else none('no_applicability_mapping')

    def signature(self,p,registry=None,reference_version=0):
        ts=tokens(p)
        if registry is None: stamp='none'
        else:
            oe=registry.get('oe');stamp=str(registry.get('ozonRevision') or registry.get('revision') or 0)+'.'+str(registry.get('size') or 0)
        ref_version=('tree:'+str(self.reference.snapshot.get('revision','undefined'))+':'+self.reference.scope) if self.reference.has_data else getattr(self,'historical_version','historical')
        out=[','.join(t['key'] for t in ts),norm(p.get('applicability')),stamp,str(reference_version),ref_version]
        stores=[] if registry is None else [registry[k] for k in ('oe','oeRegistry','oe_registry','registry') if registry.get(k)] or [registry]
        for token in ts:
            rec=MISSING
            for store in stores:
                rec=get(store,[token['raw'],token['key'],token['key'].lower(),token['hvc'],norm(token['raw'])])
                if rec is not MISSING: break
            if rec is MISSING: continue
            pair=self.pair(rec);mapping=pair['category']+'\x1f'+pair['type'] if pair else ''
            apps=[];seen=set()
            def add(v):
                if isinstance(v,list):
                    for x in v: add(x)
                    return
                if isinstance(v,dict): v=first(v,('key','value','applicability'))
                k=norm(v)
                if k and k not in seen: seen.add(k);apps.append(k)
            r=rec if isinstance(rec,dict) else {}
            for k in ('applicability','applicability_text','vehicle_applicability','vehicle'): add(r.get(k))
            add(p.get('applicability'))
            out.append(token['key']+'>'+mapping+'>'+','.join(apps))
        return '\x1e'.join(out)

    def apply(self,row,registry=None,applicability=None,force=False,reference_version=0):
        import copy
        p=copy.deepcopy(row)
        if not force and not p.get('ozon_type_src') and (p.get('ozon_type') or p.get('ozon_category')):
            p.update(ozon_type_src='import',ozon_type_basis='import',ozon_type_conf='unverified')
        if p.get('ozon_type_src') in ('manual','import') and (p.get('ozon_type') or p.get('ozon_category')):
            source=p['ozon_type_src']
            return p,dict(category=p.get('ozon_category') or '',type=p.get('ozon_type') or '',source=source,basis=source,score=0,matched=0,confidence='unverified' if source=='import' else 'manual',reason='',oe=p.get('ozon_oe') or '',applicability=p.get('ozon_applicability') or '')
        sig=self.signature(p,registry,reference_version)
        if not force and p.get('ozon_sig')==sig and p.get('ozon_type') and p.get('ozon_type_src')=='auto':
            score=p.get('ozon_type_score')
            return p,dict(category=p.get('ozon_category'),type=p['ozon_type'],source='auto',basis=p.get('ozon_type_basis') or 'oe',score=score if type(score) in (int,float) else 0,matched=0,confidence=p.get('ozon_type_conf') or 'high',reason='',oe=p.get('ozon_oe') or '',applicability=p.get('ozon_applicability') or '')
        r=self.classify(p,registry,applicability)
        p.update(ozon_category=r['category'] or '',ozon_type=r['type'] or '',ozon_type_src=r['source'],
            ozon_type_conf=r['confidence'],ozon_type_score=r['score'] or 0,ozon_type_basis=r['basis'] or 'none',
            ozon_oe=r['oe'] or '',ozon_applicability=r['applicability'] or '',ozon_error=r['reason'] or '',ozon_sig=sig)
        return p,r
