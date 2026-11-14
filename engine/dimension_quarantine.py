"""Independent AnomalyDetector quarantine decisions and acknowledgement signatures."""
import copy
import json
import math
import re
from enrichment_formula import truth
from category_tnved import text
from ozon_identity import codes, pair, key

FIELDS=('weight','net_weight','length','width','height','volume')
FLAGS=('dimensionAnomalyBlocked','dimensionAnomalySignature','dimensionAnomalyIssues',
       'dimensionAnomalyLimit','dimensionAnomalyAck','dimensionAnomalyAt')
EXT={'invalid_number','net_gt_gross','density_high','calc_overflow','import_rejected','import_missing'}
HARD={'negative','invalid_number','net_gt_gross','calc_overflow','import_missing'}


def number(v):
    if v is None or isinstance(v,bool): return 0
    if isinstance(v,(float,int)): return v if math.isfinite(v) else 0
    s=re.sub(r'\s+','',text(v));s=re.sub('%$','',s)
    if ',' in s and '.' in s:
        s=s.replace('.','').replace(',','.',1) if s.rfind(',')>s.rfind('.') else s.replace(',','')
    elif ',' in s: s=s.replace(',','') if s.count(',')>1 else s.replace(',','.')
    elif s.count('.')>1: s=s.replace('.','')
    m=re.match(r'^[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?',s)
    if not m: return 0
    n=float(m[0]);return n if math.isfinite(n) else 0


def valid(v):
    if v is None or v=='': return True
    if isinstance(v,bool): return False
    if isinstance(v,(int,float)): return math.isfinite(v)
    return bool(re.fullmatch(r'[+-]?(?:(?:[0-9]{1,3}(?:[\s\u00a0\u202f][0-9]{3})+)|[0-9]+)(?:[.,][0-9]+)?|[+-]?[.,][0-9]+',text(v).strip()))


def explicit(p):
    flag=p.get('_volumeExplicit')
    if flag is not None and flag!='':
        p['_volumeExplicit']=flag is True or (not isinstance(flag,bool) and flag==1) or bool(re.fullmatch('1|true',text(flag),re.I))
    else:
        sources=p.get('_sources') or {}
        if isinstance(sources,str):
            try: sources=json.loads(sources)
            except ValueError: sources={}
        ks=list(sources) if isinstance(sources,(dict,list)) else []
        p['_volumeExplicit']=(not ks or any(re.search('объ[её]м|volume|литр',k,re.I) for k in ks)) and number(p.get('volume'))>0
    return p['_volumeExplicit']


def direct_codes(p,mode):
    current=list(dict.fromkeys(list(codes(p.get('oe_numbers'),mode))+list(codes(p.get('oe_list'),mode))))
    if not current: current=list(codes(p.get('oe_norm'),mode))
    evidence=p.get('_dimensionAutoOeEvidence')
    if evidence and evidence.get('identity')!=pair(p): return []
    entries=evidence.get('entries') if isinstance(evidence,dict) and isinstance(evidence.get('entries'),list) else None
    if entries is None and p.get('oeSource'):
        parts=re.split(r'[;,|\r\n]+|\s+/\s+',p['oeSource']) if mode=='auto' else re.split({'newline':r'\r?\n','comma':',','semicolon':';','slash':'/','pipe':r'\|'}.get(mode,r'[/;,\n\r|]+'),p['oeSource'])
        entries=[dict(code=key(v),pieces=list(codes(v,mode))) for v in parts]
    if entries is None: return current
    return list(dict.fromkeys(e['code'] for e in entries if isinstance(e,dict) and e.get('code') and isinstance(e.get('pieces'),list) and e['pieces'] and all(x in current for x in e['pieces'])))


def compact(value):
    # JSON.stringify uses decimal notation for 1e-6 <= abs(n) < 1e21 and
    # exponent notation without zero-padded exponents outside that range.
    from decimal import Decimal
    def encode(v):
        if isinstance(v,bool) or v is None: return json.dumps(v)
        if isinstance(v,(int,float)):
            if not math.isfinite(v): return 'null'
            if v==0: return '0'
            if 1e-6<=abs(v)<1e21:
                if int(v)==v:return str(int(v))
                return format(Decimal(repr(v)),'f')
            mantissa,exponent=repr(float(v)).split('e')
            mantissa=mantissa.removesuffix('.0');exp=int(exponent)
            return mantissa+'e'+('+' if exp>=0 else '-')+str(abs(exp))
        if isinstance(v,dict): return '{'+','.join(json.dumps(k,ensure_ascii=False)+':'+encode(x) for k,x in v.items())+'}'
        if isinstance(v,list): return '['+','.join(encode(x) for x in v)+']'
        return json.dumps(v,ensure_ascii=False)
    return encode(value)


class DimensionQuarantine:
    def __init__(self,limits,mode='auto'):
        self.limits={};self.mode=mode
        for lim in limits:
            k=self.limit_key(lim.get('category'))
            if k and k not in self.limits: self.limits[k]=lim

    @staticmethod
    def limit_key(v): return re.sub(r'\s+',' ',text(v).strip().lower().replace('ё','е'))

    def evaluate(self,p):
        lim=self.limits.get(self.limit_key(p.get('category'))) or dict(category=text(p.get('category')),maxW=400,maxL=300,maxVol=1000)
        w,net,l,wi,h,pv=[number(p.get(k)) for k in FIELDS]
        exp=explicit(p);derived=l*wi*h/1000
        vol=pv if exp and pv>0 else derived or pv
        issues=[]
        def add(f,v,limit,t):issues.append(dict(field=f,val=v,limit=limit,type=t))
        for f,v in zip(FIELDS,(w,net,l,wi,h,pv)):
            if not valid(p.get(f)): add(f,text(p.get(f))[:120],0,'invalid_number')
            elif v<0: add(f,v,0,'negative')
        if w>0 and net>0 and net>w+max(1e-9,w*1e-9): add('net_weight',net,w,'net_gt_gross')
        rejected=p.get('_dimensionImportIssues')
        if isinstance(rejected,dict):
            for f in FIELDS:
                r=rejected.get(f)
                if not isinstance(r,dict):continue
                missing=f in ('weight','length','width','height') and not number(p.get(f))>0
                detail=text(r.get('reason') or 'ячейка отклонена')[:120]
                if r.get('value'):detail+=' · значение: '+text(r['value'])[:80]
                if r.get('file'):detail+=' · файл: '+text(r['file'])[:100]
                add(f,detail,0,'import_missing' if missing else 'import_rejected')
        if w>number(lim.get('maxW')):add('weight',w,number(lim.get('maxW')),'weight_high')
        max_dim=max(l,wi,h);computed=derived if l>0 and wi>0 and h>0 else 0
        if max_dim>number(lim.get('maxL')):add('dims',max_dim,number(lim.get('maxL')),'dim_high')
        if computed and not math.isfinite(computed):add('volume',0,0,'calc_overflow')
        if math.isfinite(computed) and computed>0 and w>0 and w/computed>30:add('density',w/computed,30,'density_high')
        if vol>number(lim.get('maxVol')):add('volume',vol,number(lim.get('maxVol')),'vol_high')
        if exp and pv>0 and computed>0 and max(pv/computed,computed/pv)>4:add('volume',pv,computed,'volume_mismatch')
        src=p.get('_sources') or {}
        if isinstance(src,dict) and w==0.5 and l==15 and wi==10 and h==5 and src.get('Прайс-лист') and not any(src.get(k) for k in ('weight','Вес, кг','Вес в упаковке, кг')):add('dims',0,0,'legacy_defaults')
        if truth(p.get('_dimensionOeReview')):add('dims',0,0,'oe_review')
        fix={};heuristic=[]
        max_w=number(lim.get('maxW'));max_l=number(lim.get('maxL'));max_v=number(lim.get('maxVol'))
        if w>max_w and w>=max_w*10 and 0<w/1000<=max_w and valid(p.get('net_weight')) and (net<=0 or net<=w/1000+max(1e-9,(w/1000)*1e-9)):
            fix['weight']=w/1000;heuristic.append('возможны граммы: масса /1000')
        if max_dim>max_l and max_dim>200 and l>0 and wi>0 and h>0:
            cl,cw,ch=l/10,wi/10,h/10;cvol=cl*cw*ch/1000
            ev=pv if exp and pv>0 else cvol
            mismatch=exp and ev>0 and cvol>0 and max(ev/cvol,cvol/ev)>4
            if max(cl,cw,ch)<=max_l and ev<=max_v and not mismatch:
                fix.update(length=cl,width=cw,height=ch);heuristic.append('возможны мм: все стороны /10')
        return dict(lim=lim,issues=issues,volume=vol,explicitVolume=exp,fix=fix,heuristic=', '.join(heuristic))

    def signature(self,p,e):
        lim=e['lim'];review=p.get('_dimensionOeReview')
        volume=e['volume'];rounded=(math.floor(abs(volume)*1e6+0.5)/1e6*(1 if volume>=0 else -1) if abs(volume)<1e300 else float('inf')) if math.isfinite(volume) else 0
        sig=dict(v=1,category=text(p.get('category')),**{k:number(p.get(k)) for k in ('weight','length','width','height')},
            volume=number(p.get('volume')) if e['explicitVolume'] else None,computedVolume=rounded,
            limits=dict(category=text(lim.get('category')),**{k:number(lim.get(k)) for k in ('maxW','maxL','maxVol')}),oeReview=None)
        if truth(review):
            sig['oeReview']=dict(oe=text(review.get('oe')),source=text(review.get('source')),currentOe=sorted(list(codes([p.get('oe_numbers'),p.get('oe_list')],self.mode))))
            if review.get('oeProofVersion')==1:sig['oeReview']['directOe']=sorted(direct_codes(p,self.mode))
        new=[i for i in e['issues'] if i['type'] in EXT]
        if new:
            ext=dict(v=2,issues=sorted(i['type']+':'+i['field'] for i in new),invalid=[[i['field'],text(p.get(i['field']))[:120]] for i in new if i['type']=='invalid_number'])
            if any(i['type']=='net_gt_gross' for i in new):ext['netWeight']=number(p.get('net_weight'))
            if any(i['type'] in ('import_rejected','import_missing') for i in new):
                ext['importReview']=[[k]+[text((p['_dimensionImportIssues'][k] or {}).get(f)) for f in ('file','field','value','reason','at')] for k in sorted(p['_dimensionImportIssues'])]
            sig['ext']=ext
        return compact(sig)

    def apply(self,row,timestamp):
        p=copy.deepcopy(row)
        if p.get('excluded') and not p.get('_dimensionImportIssues'):
            p['dimensionAnomalyBlocked']=False;return p
        e=self.evaluate(p)
        if not e['issues']:
            p['dimensionAnomalyBlocked']=False
            for k in FLAGS[1:]:p.pop(k,None)
            return p
        sig=self.signature(p,e)
        if p.get('dimensionAnomalySignature')!=sig:
            p.pop('dimensionAnomalyAck',None);p['dimensionAnomalyAt']=timestamp
        p['dimensionAnomalySignature']=sig;p['dimensionAnomalyIssues']=e['issues']
        lim=e['lim'];p['dimensionAnomalyLimit']=dict(category=text(lim.get('category')),**{k:number(lim.get(k)) for k in ('maxW','maxL','maxVol')})
        p['dimensionAnomalyBlocked']=any(i['type'] in HARD for i in e['issues']) or not (p.get('dimensionAnomalyAck') or {}).get('signature')==sig
        return p

    def confirm(self,row,timestamp,approved=False,expected_signature=None):
        """Two-phase confirmation: re-evaluate at both preview and approval."""
        p=copy.deepcopy(row)
        e=self.evaluate(p)
        if not e['issues']:return p,{'status':'clean'}
        if any(i['type'] in HARD for i in e['issues']):
            return self.apply(p,timestamp),{'status':'hard'}
        sig=self.signature(p,e)
        if sig!=p.get('dimensionAnomalySignature') or (expected_signature is not None and sig!=expected_signature):
            return self.apply(p,timestamp),{'status':'stale'}
        detail={'status':'ready','signature':sig,'values':{k:number(p.get(k)) for k in ('weight','net_weight','length','width','height')},
                'volume':e['volume'],'issues':e['issues']}
        if not approved:return p,detail
        p['dimensionAnomalyAck']={'signature':sig,'at':timestamp}
        if truth(p.get('_dimensionOeReview')):
            p['_dimensionOeReview']['reviewedAt']=timestamp
            p['_dimensionOeReview']['reviewedValues']={k:p[k] for k in ('weight','length','width','height','volume') if k in p}
        p=self.apply(p,timestamp)
        detail['status']='confirmed'
        detail['log']={'ts':timestamp,'article':p.get('article'),
                       'before':{**{k:number(p.get(k)) for k in ('weight','length','width','height')},'volume':e['volume']},
                       'after':{'confirmed':True},'heuristic':'Ручное подтверждение аномалии','category':p.get('category')}
        return p,detail


    def fix_units(self,row,timestamp,expected_signature,approved=False,labels=None):
        p=copy.deepcopy(row);e=self.evaluate(p)
        if not p.get('dimensionAnomalyBlocked') or expected_signature!=self.signature(p,e) or not e['fix']:
            return p,{'status':'skipped'}
        result={'status':'ready','signature':expected_signature,'fix':e['fix'],'heuristic':e['heuristic']}
        if not approved:return p,result
        before={k:p[k] for k in ('weight','length','width','height','volume') if k in p}
        p.update(e['fix'])
        if not e['explicitVolume'] and any(k in e['fix'] for k in ('length','width','height')):
            v=number(p.get('length'))*number(p.get('width'))*number(p.get('height'))/1000
            p['volume']=math.floor(v*1e4+0.5)/1e4;p['_volumeExplicit']=False
        if not isinstance(p.get('_sources'),dict):p['_sources']={}
        old_sources={};labels=labels or {}
        for k in e['fix']:
            label=labels.get(k,k)
            old_sources[k]=copy.deepcopy(p['_sources'].get(k) or p['_sources'].get(label))
            source={'file':'Предположение о единицах (проверить): '+e['heuristic'],'date':timestamp}
            p['_sources'][k]=source;p['_sources'][label]=copy.deepcopy(source)
        previous=p.get('_dimensionOeReview')
        review={'oe':'','source':'Предположение о единицах: '+e['heuristic'],'at':timestamp,
                'before':before,'beforeSources':old_sources,'after':copy.deepcopy(e['fix'])}
        if isinstance(previous,dict):
            snapshot={k:v for k,v in previous.items() if k!='history'}
            history=previous.get('history') if isinstance(previous.get('history'),list) else []
            review['history']=(history+[snapshot])[-20:]
        p['_dimensionOeReview']=review;p.pop('dimensionAnomalyAck',None)
        result.update(status='applied',log={'ts':timestamp,'article':p.get('article'),'before':before,
            'after':copy.deepcopy(e['fix']),'heuristic':e['heuristic'],'category':p.get('category')})
        return p,result
