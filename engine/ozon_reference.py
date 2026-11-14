"""OzonReference lookup over an already parsed raw tree snapshot."""
import re
import unicodedata
from category_tnved import text


def strict_key(v): return re.sub(r'\s+',' ',unicodedata.normalize('NFC',text(v)).lower()).strip()
def loose_key(v):
    s=unicodedata.normalize('NFKC',strict_key(v)).replace('ё','е')
    return re.sub(r'\s+',' ',''.join(c if unicodedata.category(c)[0] in ('L','N') else ' ' for c in s)).strip()
def valid_id(v):
    if isinstance(v,bool): return ''
    if isinstance(v,(int,float)): return str(int(v)) if v>0 and v<=9007199254740991 and int(v)==v else ''
    return v if isinstance(v,str) and re.fullmatch('[1-9][0-9]*',v) else ''

class OzonReference:
    def __init__(self,snapshot=None,scope='auto'):
        self.snapshot=snapshot or {};self.scope='all' if scope=='all' else 'auto'
        self.has_data=bool(self.snapshot.get('items') or self.snapshot.get('allItems'))
        self.entries=[];self.by_id={};self.exact={};self.strict={};self.loose={};self.by_type={}
        all_items=self.snapshot.get('allItems')
        if not isinstance(all_items,list): all_items=[{**r,'status':'active','vehicle':True} for r in self.snapshot.get('items',[])]
        for r in all_items:
            if isinstance(r,dict) and valid_id(r.get('catId')) and valid_id(r.get('typeId')):
                self.by_id.setdefault((text(r['catId']),text(r['typeId'])),[]).append(r)
        selected=[r for r in all_items if r.get('status')=='active' and (self.scope=='all' or r.get('vehicle'))] if isinstance(self.snapshot.get('allItems'),list) else self.snapshot.get('items',[])
        for r in selected:
            if not isinstance(r,dict) or not isinstance(r.get('cat'),str) or not isinstance(r.get('type'),str) or not valid_id(r.get('catId')) or not valid_id(r.get('typeId')): continue
            item={k:r[k] for k in ('cat','type','catId','typeId')};item.update(name=r['type'],path=r.get('path') or [])
            self.entries.append(item)
            for idx,key in ((self.exact,(r['cat'],r['type'])),(self.strict,(strict_key(r['cat']),strict_key(r['type']))),(self.loose,(loose_key(r['cat']),loose_key(r['type']))),(self.by_type,strict_key(r['type']))): idx.setdefault(key,[]).append(item)
    def unique_type(self,typ):
        matches=self.by_type.get(strict_key(typ),[])
        return matches[0] if len(matches)==1 else None
    def find_pair(self,category,typ,ids=None):
        if not self.has_data: return {'status':'no_reference'}
        c,t=text(category),text(typ)
        if not c.strip() or not t.strip(): return {'status':'missing'}
        with_ids=isinstance(ids,dict) and ids.get('catId') and ids.get('typeId')
        if with_ids:
            known=self.by_id.get((text(ids['catId']),text(ids['typeId'])),[])
            if any(x.get('status')=='conflict' for x in known): return {'status':'conflict'}
            if len(known)==1:
                x=known[0]
                if loose_key(x.get('cat'))!=loose_key(c) or loose_key(x.get('type'))!=loose_key(t): return {'status':'id_conflict'}
                if x.get('status') in ('disabled','unknown'): return {'status':x['status']}
                if self.scope=='auto' and not x.get('vehicle'): return {'status':'out_of_scope'}
        matches=self.exact.get((c,t))
        if matches is None: matches=self.strict.get((strict_key(c),strict_key(t)))
        if matches is None: matches=self.loose.get((loose_key(c),loose_key(t)))
        if not matches: return {'status':'not_found'}
        if with_ids:
            matches=[x for x in matches if x['catId']==text(ids['catId']) and x['typeId']==text(ids['typeId'])]
            if not matches: return {'status':'id_conflict'}
        if len(matches)!=1: return {'status':'ambiguous','choices':matches[:8]}
        return {'status':'valid','item':matches[0]}
