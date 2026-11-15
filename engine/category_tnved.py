"""Port of CategoryTnved apply/typeInfo/lookup provenance contract."""
import copy
import re
import unicodedata
from enrichment_formula import string as js_string

TYPE_KEY = re.compile(r'^(?:вид[\s_-]+категор(?:ии|изации)|тип[\s_-]+категории|подкатегория|category[\s_-]*type|sub[\s_-]*category)$',re.I)
CODE_KEY = re.compile(r'^(?:тн[\s_-]*вэд(?:[\s_-]*(?:код|коды))?(?:[\s_-]*еаэс)?|код[\s_-]*тн[\s_-]*(?:вэд|вд)(?:[\s_-]*еаэс)?|тнвд(?:[\s_-]*еаэс)?|tnved(?:[\s_-]*eaes)?|hs[\s_-]*code)$',re.I)
CODE_KEYS = ['tnved','tnved_eaes','tnvedEaes','hs_code','hsCode','ТН ВЭД код ЕАЭС','ТН ВЭД коды ЕАЭС','ТН ВЭД','Код ТН ВЭД','ТНВД']

def text(v):
    return '' if v is None else js_string(v)

def norm(v): return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',text(v)).strip().lower().replace('ё','е'))

class CategoryTnved:
    def __init__(self, rows, revision, source='Категории12131.csv'):
        self.revision,self.source=revision,source
        self.index={}
        for category,kind,code,*_ in rows:
            category,kind,code=(text(x).strip() for x in (category,kind,code))
            if not category or not kind or not re.fullmatch(r'[0-9]{10}',code): continue
            key=(norm(category),norm(kind))
            old=self.index.get(key)
            if old and old['code']!=code: old['conflict']=True
            if not old: self.index[key]={'category':category,'type':kind,'code':code,'categoryKey':key[0],'typeKey':key[1],'conflict':False}
    def lookup(self,category,kind):
        if not norm(category) or not norm(kind): return {'status':'incomplete'}
        hit=self.index.get((norm(category),norm(kind)))
        if not hit: return {'status':'not_found'}
        if hit['conflict']: return {'status':'ambiguous'}
        return {'status':'match',**{k:v for k,v in hit.items() if k!='conflict'}}
    def kind_current(self,p):
        m=p.get('_categoryKindAuto')
        keys=['version','name','brand','category','referenceCategory','type','categoryMode','categoryMethod','categoryRevision']
        if not isinstance(m,dict) or not all(isinstance(m.get(k),str) and len(m[k])<=4000 for k in keys): return False
        if not isinstance(m.get('confirmed'),bool) or m['categoryMode'] not in ('explicit','name_auto','csv_auto','rule_auto'): return False
        if m['version']!='csv-kind-name-v1|'+self.revision or text(p.get('category_type'))!=m['type'] or text(p.get('category'))!=m['category'] or p.get('_categoryTypeCleared'): return False
        if self.lookup(m['referenceCategory'],m['type'])['status']!='match': return False
        return m['confirmed'] or (text(p.get('name'))==m['name'] and text(p.get('brand'))==m['brand'])
    def type_info(self,p):
        if p.get('_categoryTypeCleared') and not text(p.get('category_type')).strip(): return {'value':'','conflict':False}
        found={}
        def add(v):
            if isinstance(v,(dict,list)) or v is None: return
            v=text(v).strip()
            if norm(v): found.setdefault(norm(v),v)
        m=p.get('_categoryKindAuto')
        stale=isinstance(m,dict) and not m.get('confirmed') and text(p.get('category_type'))==m.get('type') and not self.kind_current(p)
        if not stale: add(p.get('category_type'))
        for k in ('categoryType','sub_category'): add(p.get(k))
        for box in (p.get('custom'),p.get('enriched'),p.get('attributes')):
            if isinstance(box,dict):
                for k,v in box.items():
                    if TYPE_KEY.fullmatch(k.strip()): add(v)
        result={'value':next(iter(found.values())) if len(found)==1 else '', 'conflict':len(found)>1}
        if stale: result['stale']=True
        return result
    def lookup_for(self,p,info):
        if info['conflict']: return {'status':'ambiguous_type'}
        hit=self.lookup(p.get('category'),info['value'])
        if hit['status']=='match': return hit
        m=p.get('_categoryKindAuto')
        if m and self.kind_current(p) and norm(m['type'])==norm(info['value']):
            via=self.lookup(m['referenceCategory'],info['value'])
            if via['status']=='match': return {**via,'viaName':True}
        return hit
    def find_code(self,p,skip=False):
        for box in (p,p.get('custom'),p.get('enriched'),p.get('attributes')):
            if not isinstance(box,dict): continue
            for key in CODE_KEYS+[k for k in box if k not in CODE_KEYS and CODE_KEY.fullmatch(k.strip())]:
                if skip and box is p and key=='tnved': continue
                v=box.get(key)
                if v is not None and not isinstance(v,(dict,list)) and text(v).strip(): return text(v).strip()
        return ''
    def current(self,p):
        a=p.get('_categoryTnvedAuto')
        if not isinstance(a,dict) or text(p.get('tnved')).strip()!=text(a.get('code')) or self.find_code(p,True): return False
        info=self.type_info(p)
        if info['conflict'] or info.get('stale'): return False
        hit=self.lookup_for(p,info)
        return hit['status']=='match' and a.get('revision')==self.revision and all(a.get(k)==hit[k] for k in ('categoryKey','typeKey','code'))
    def apply(self,source,enabled=True,timestamp=''):
        p=copy.deepcopy(source); a=p.get('_categoryTnvedAuto')
        if a and (not isinstance(a,dict) or a.get('revision')!=self.revision): return p,{'status':'foreign_marker'}
        if a and text(p.get('tnved')).strip()!=text(a.get('code')): p.pop('_categoryTnvedAuto',None); a=None
        if a and self.current(p): return p,{'status':'auto','code':text(a['code'])}
        if a and p.get('_categoryKindAuto') and not self.kind_current(p) and not enabled: return p,{'status':'stale'}
        if a:
            if text(p.get('tnved')).strip()==text(a.get('code')): p.pop('tnved',None)
            p.pop('_categoryTnvedAuto',None)
            sm=p.get('_sources') or {}
            if isinstance(sm,str):
                import json
                try: sm=json.loads(sm)
                except ValueError: sm={}
            for k in ('tnved','ТН ВЭД код ЕАЭС'):
                if isinstance(sm.get(k),dict) and sm[k].get('file')=='справочник: '+self.source: sm.pop(k)
            p['_sources']=sm
        if p.get('_tnvedNoAutofill'): return p,{'status':'disabled'}
        info=self.type_info(p)
        if info['conflict'] or info.get('stale'): return p,{'status':'ambiguous_type'}
        hit=self.lookup_for(p,info)
        if hit['status']!='match': return p,hit
        explicit=self.find_code(p)
        if explicit: return p,{'status':'preserved','code':explicit}
        p['tnved']=hit['code']
        p['_categoryTnvedAuto']={'revision':self.revision,**{k:hit[k] for k in ('categoryKey','typeKey','code')}}
        if not isinstance(p.get('_sources'),dict):
            import json
            try: p['_sources']=json.loads(p['_sources']) if isinstance(p.get('_sources'),str) else {}
            except ValueError: p['_sources']={}
            if not isinstance(p['_sources'],dict): p['_sources']={}
        p['_sources']['tnved']={'file':'справочник: '+self.source,'date':timestamp,'category':hit['category'],'type':hit['type'],'review':'требует проверки'}
        return p,{'status':'filled','code':hit['code']}
