# -*- coding: utf-8 -*-
"""
UNIT·CONTROL — локальный расчётный движок (Python + SQLite).

Запуск:
  python uc_engine.py serve            # HTTP 127.0.0.1:8765 (только локально)
  python uc_engine.py watch            # планировщик: почта + папка + очередь отправки
  python uc_engine.py mail --once      # одна проверка почты
  python uc_engine.py calc --demo      # самопроверка экономики на демо-строке

Зависимости: только стандартная библиотека. Для XLSX — openpyxl (необязательно).

Безопасность: сервер слушает только 127.0.0.1; все эндпоинты кроме /health
требуют заголовок X-UC-Token (токен в engine_data/token.txt, создаётся сам).
Ключи маркетплейсов и пароль почты читаются из переменных окружения или
engine_data/secrets.json (на Windows рекомендуется DPAPI-обёртка, см. README).
"""
# Internal modules live in this file; no extracted .py files are needed.
# Separate module namespaces preserve globals, imports and pickling identities.
# Explicit stdlib imports keep freezer dependency discovery working even though
# the internal module bodies are stored as source below.
import copy as _bundle_copy
import dataclasses as _bundle_dataclasses
import unicodedata as _bundle_unicodedata
import importlib.abc as _bundle_abc
import importlib.util as _bundle_util
import sys as _bundle_sys

_BUNDLED_SOURCES = {
    # ===== category_kind =====
    'category_kind': """\"\"\"Non-destructive CategoryKindAuto.apply lifecycle port.\"\"\"
import copy,json
from category_tnved import CategoryTnved,norm,text
from csv_kind_matcher import CsvKindMatcher
from name_category import apply as name_apply, MARKERS

ALIASES={
      'подвеска':['подвеска и рулевое управление'],
      'рулевое управление':['подвеска и рулевое управление','резинотехнические изделия','насосы и компрессоры','ремкомплекты'],
      'двигатель':['детали двигателя','ремни и ролики двигателя','резинотехнические изделия','фильтры','насосы и компрессоры','подшипники','свечи и высоковольтные провода'],
      'тормозная система':['детали крепежные','ремкомплекты','резинотехнические изделия'],
      'прокладки и уплотнения':['резинотехнические изделия','детали двигателя','детали кпп'],
      'ремни и ролики':['ремни и ролики двигателя'],
      'электрика и электроника':['электрооборудование','свечи и высоковольтные провода'],
      'электрические аксессуары':['электрооборудование'],
      'освещение':['детали кузова','электрооборудование'],
      'стеклоочистители':['детали кузова'],
      'охлаждение':['система охлаждения','резинотехнические изделия','насосы и компрессоры'],\x20
      'трансмиссия / кпп':['детали кпп'],
      'кузовные элементы':['детали кузова'],
      'крепеж и метизы':['детали крепежные'],
      'подушки и опоры':['резинотехнические изделия','подвеска и рулевое управление'],
      'топливная система':['насосы и компрессоры','электрооборудование','фильтры','резинотехнические изделия','ремкомплекты'],
      'подшипники':['подшипники','детали двигателя','детали кпп','подвеска и рулевое управление']
  }
SOURCE="по названию: Категории12131.csv"
def blank(v): return not text(v).strip() or text(v).strip().lower() in ("без категории","не определено")

def shape(m):
    keys=("version","name","brand","category","referenceCategory","type","categoryMode","categoryMethod","categoryRevision")
    return isinstance(m,dict) and all(isinstance(m.get(k),str) and len(m[k])<=4000 for k in keys) and isinstance(m.get("confirmed"),bool) and m.get("categoryMode") in ("explicit","name_auto","csv_auto","rule_auto")

class CategoryKind:
    def __init__(self,rows,revision,base_categories=()):
        self.tnved=CategoryTnved(rows,revision);self.matcher=CsvKindMatcher(rows)
        self.version='csv-kind-name-v1|'+revision
        self.known={norm(c) for c in base_categories}|{k[0] for k in self.tnved.index}
    def own(self,p): return shape(p.get('_categoryKindAuto')) and text(p.get('category_type'))==p['_categoryKindAuto']['type']
    def clear(self,p):
        if self.own(p) and not p['_categoryKindAuto']['confirmed']: p.pop('category_type',None)
        p.pop('_categoryKindAuto',None)
        sources=p.get('_sources')
        if isinstance(sources,dict) and isinstance(sources.get('category_type'),dict) and sources['category_type'].get('file')==SOURCE: sources.pop('category_type')
    def apply(self,row,context,enabled,match,at):
        p=copy.deepcopy(row); self._apply(p,context or {},enabled,match,at); return p
    def _apply(self,p,ctx,enabled,match,at):
        m=p.get('_categoryKindAuto')
        if m and (not shape(m) or m['version']!=self.version):
            p.update(_categoryKindStatus='foreign_marker',_categoryKindReason='Неизвестный источник вида: сохраните и проверьте его вручную');return
        owned=self.own(p)
        if m and not owned: p.pop('_categoryKindAuto',None);m=None
        if owned and m['confirmed']:
            if text(p.get('category'))!=m['category']: p.pop('_categoryKindAuto',None);p['_categoryKindStatus']='explicit'
            else: p['_categoryKindStatus']='confirmed'
            return
        if p.get('_categoryTypeCleared'):
            if owned: self.clear(p)
            p.update(_categoryKindStatus='disabled',_categoryKindChoices=[]);return
        explicit=self.tnved.type_info({**p,'category_type':''} if owned else p)
        if explicit['conflict']:
            if owned: self.clear(p)
            p.update(_categoryKindStatus='ambiguous',_categoryKindChoices=[],_categoryKindReason='В исходных данных указаны разные виды');return
        if explicit['value']:
            if owned and norm(explicit['value'])==norm(m['type']): m['confirmed']=True;p['_categoryKindStatus']='confirmed'
            elif owned: self.clear(p);p['_categoryKindStatus']='explicit'
            else: p['_categoryKindStatus']='explicit'
            p.update(_categoryKindChoices=[],_categoryKindReason='');return
        if not enabled:
            if owned and not self.tnved.kind_current(p): p['_categoryKindStatus']='stale'
            elif not owned: p['_categoryKindStatus']='disabled'
            return
        if owned and self.tnved.kind_current(p): p['_categoryKindStatus']='auto';return
        g=self.matcher.guess(p)
        if g['status']!='auto':
            if owned:
                self.clear(p)
                if m['categoryMode']=='csv_auto' and p.get('_categoryNameMethod')=='csv_kind' and p.get('category')==p.get('_categoryNameAutoValue'):
                    p['category']='Без категории'
                    for k in MARKERS: p.pop(k,None)
                    updated=name_apply(p,ctx,True,match);p.clear();p.update(updated)
            p.update(_categoryKindStatus=g['status'],_categoryKindChoices=g.get('choices',[])[:6],_categoryKindReason=g.get('reason',''),_categoryKindDiscriminators=g.get('discriminators',[])[:8]);return
        cat=text(p.get('category')); mode='explicit'
        auto=bool(p.get('_categoryNameAutoValue')) and cat==p['_categoryNameAutoValue']
        rule=auto and p.get('_categoryNameMethod') in ('rule','enrich')
        explicit_blank=(p.get('_categoryNameExplicit') or p.get('_categoryExplicitSource')) and bool(cat.strip())
        if blank(cat) and not explicit_blank:
            cat=g['category'];mode='csv_auto'
            p.update(category=cat,_categoryNameAutoValue=cat,_categoryNameSource=text(p.get('name')),_categoryNameBrand=text(p.get('brand')),
                     _categoryNameRevision=ctx.get('version',''),_categoryNameStatus='auto',_categoryNameMethod='csv_kind',_categoryNameChoices=[])
        elif auto and not rule: mode='name_auto'
        else:
            mode='rule_auto' if rule else 'explicit'
            compatible=norm(cat)==norm(g['category']) or norm(g['category']) in ALIASES.get(norm(cat),[])
            if not blank(cat) and norm(cat) in self.known and not compatible:
                if owned: self.clear(p)
                p.update(_categoryKindStatus='category_conflict',_categoryKindChoices=[g['category']+' / '+g['type']],_categoryKindReason='Название указывает на другую категорию словаря; сохранённая категория не изменена');return
        p['category_type']=g['type']
        p['_categoryKindAuto']={'version':self.version,'name':text(p.get('name')),'brand':text(p.get('brand')),'category':cat,
            'referenceCategory':g['category'],'type':g['type'],'categoryMode':mode,'categoryMethod':text(p.get('_categoryNameMethod')),
            'categoryRevision':text(p.get('_categoryNameRevision')),'confirmed':False}
        p.update(_categoryKindStatus='auto',_categoryKindChoices=[],_categoryKindReason='',_categoryKindDiscriminators=[])
        sources=p.get('_sources')
        if isinstance(sources,str):
            try: sources=json.loads(sources)
            except ValueError: sources={}
        p['_sources']=sources if isinstance(sources,dict) else {}
        p['_sources']['category_type']={'file':SOURCE,'date':at,'category':g['category'],'type':g['type'],'review':'требует проверки'}

    def confirm(self,row,category_confirmed=False,at=''):
        p=copy.deepcopy(row)
        if not self.own(p) or p['_categoryKindAuto']['confirmed'] or not self.tnved.kind_current(p): return p,False
        m=p['_categoryKindAuto'];m['confirmed']=True
        if category_confirmed: m.update(categoryMode='explicit',categoryMethod='',categoryRevision='')
        p.update(_categoryKindStatus='confirmed',_categoryKindReason='',_categoryKindChoices=[])
        sources=p.get('_sources')
        if isinstance(sources,str):
            try: sources=json.loads(sources)
            except ValueError: sources={}
        p['_sources']=sources if isinstance(sources,dict) else {}
        p['_sources']['category_type']={'file':'вручную: подтверждён вид из Категории12131.csv','date':at}
        return p,True

    def explicit_import(self,row,value,source):
        p=copy.deepcopy(row);m=p.get('_categoryKindAuto')
        if not text(value).strip() or not shape(m): return p
        if norm(value)==norm(m['type']): m['confirmed']=True;p['_categoryKindStatus']='confirmed'
        else: p.pop('_categoryKindAuto',None);p['_categoryKindStatus']='explicit'
        if isinstance(p.get('_sources'),dict):
            if source is None: p['_sources'].pop('category_type',None)
            else: p['_sources']['category_type']=copy.deepcopy(source)
        return p

    def marker_for_cloud(self,p):
        m=p.get('_categoryKindAuto')
        if not m: return None
        if not shape(m) or m['version']!=self.version:
            raise ValueError('Неизвестный источник вида для '+text(p.get('article') or 'SKU')+': сохраните резервную копию и проверьте вручную.')
        return copy.deepcopy(m) if self.own(p) else None

    def hydrate(self,row,marker):
        p=copy.deepcopy(row)
        if not marker: p.pop('_categoryKindAuto',None);return p
        m=copy.deepcopy(marker);p['_categoryKindAuto']=m
        if not text(p.get('category_type')) and not m.get('confirmed'): p['category_type']=m.get('type')
        current=self.tnved.kind_current(p)
        p['_categoryKindStatus']=('confirmed' if m.get('confirmed') else 'auto') if current else 'stale'
        if m.get('categoryMode') in ('name_auto','csv_auto','rule_auto') and p.get('category')==m.get('category'):
            p.update(_categoryNameAutoValue=m.get('category'),_categoryNameSource=m.get('name'),_categoryNameBrand=m.get('brand'),
                _categoryNameRevision=m.get('categoryRevision'),_categoryNameMethod=m.get('categoryMethod'),
                _categoryNameStatus='auto' if current else 'stale',_categoryNameChoices=[])
        return p
""",
    # ===== category_tnved =====
    'category_tnved': """\"\"\"Port of CategoryTnved apply/typeInfo/lookup provenance contract.\"\"\"
import copy
import re
import unicodedata
from enrichment_formula import string as js_string

TYPE_KEY = re.compile(r'^(?:вид[\\s_-]+категор(?:ии|изации)|тип[\\s_-]+категории|подкатегория|category[\\s_-]*type|sub[\\s_-]*category)$',re.I)
CODE_KEY = re.compile(r'^(?:тн[\\s_-]*вэд(?:[\\s_-]*(?:код|коды))?(?:[\\s_-]*еаэс)?|код[\\s_-]*тн[\\s_-]*(?:вэд|вд)(?:[\\s_-]*еаэс)?|тнвд(?:[\\s_-]*еаэс)?|tnved(?:[\\s_-]*eaes)?|hs[\\s_-]*code)$',re.I)
CODE_KEYS = ['tnved','tnved_eaes','tnvedEaes','hs_code','hsCode','ТН ВЭД код ЕАЭС','ТН ВЭД коды ЕАЭС','ТН ВЭД','Код ТН ВЭД','ТНВД']

def text(v):
    return '' if v is None else js_string(v)

def norm(v): return re.sub(r'\\s+',' ',unicodedata.normalize('NFKC',text(v)).strip().lower().replace('ё','е'))

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
""",
    # ===== csv_kind_lexicon =====
    'csv_kind_lexicon': """\"\"\"CsvNameMatcher lexical rules, ported from the browser reference.\"\"\"
import re
import unicodedata
from name_category import ALIASES, stem as base_stem
from category_tnved import norm

STOP=set(['и','или','для','под','над','на','к','по','от','без','с','из','в','the','and','of','for','авто','автомобильный','автомобильная','автомобильные','автомобилей','автомобиля','система','системы','систем','систему','новый','новая','новые','оригинал'])
WEAK=re.compile('^(?:передн|задн|верхн|нижн|лев|прав|боков|внутрен|наружн|внешн|нов|оригин|универс|комплект|набор|установ|креплен|крепеж|детал|запчаст|шт|размер|сторон|сбор|штуч|бренд|модел|компонент)')
STEM_RULES=[('^рем(?:ень|ен[ьяюем]|н(?:и|я|ей|ями|ях|ю|ем))$', 'ремень'), ('^порш(?:ень|ен[ьяюем]|н(?:и|я|ей|ями|ях|ю|ем))$', 'поршень'), ('^воздуш|^воздух', 'воздух'), ('^топлив', 'топлив'), ('^масл(?:о|а|у|ом|е|ы|ами|ах|ян[а-я]*)$', 'масл'), ('^салон', 'салон'), ('^тормоз', 'тормоз'), ('^двигател|^двс$', 'двигател'), ('^ступиц|^ступич', 'ступиц'), ('^накал', 'накал'), ('^дверн|^двер', 'двер'), ('^передн', 'передн'), ('^задн', 'задн'), ('^натяжн|^натяжител', 'натяж'), ('^рейк|^реек', 'рейк'), ('^крыл(?:о|а|у|е|ом|ья|ьев|ьям|ьями|ьях)$', 'крыл'), ('^ковр(?:ик[а-я]*|ы|ов|ам|ами|ах|а)?$', 'ковр'), ('^(?:поликлинов|ручейков)', 'ручейк')]

def stem(word):
    w=str(word or "").lower().replace("ё","е")
    w=ALIASES.get(w,w)
    for pattern,result in STEM_RULES:
        if re.search(pattern,w): return result
    return base_stem(w)

def words(value):
    s=unicodedata.normalize("NFKC",str(value or "")).lower().replace("ё","е")
    s=re.sub(r"ремонтн[а-я]*\\s+комплект[а-я]*","ремкомплект",s)
    return [w for w in re.sub("[^a-zа-я0-9]+"," ",s).split() if len(w)>=2 and not re.fullmatch("[0-9]+",w) and w not in STOP]

def head(ws):
    for w in ws:
        adj=not re.search("(?:ение|ание|тие|ствие)$",w) and re.search("(?:ый|ий|ой|ая|яя|ое|ее|ые|ие|ых|их|ого|его|ому|ему|ыми|ими|ую|юю)$",w)
        if adj or re.match("^(?:комплект|набор|оригинал)",w): continue
        k=stem(w)
        if len(k)>=2: return k
    return ""

def variant(ws):
    h=head(ws); needs=list(dict.fromkeys(stem(w) for w in ws if len(stem(w))>=2))
    return {"head":h,"needs":needs} if h and needs else None


def build_index(rows):
    by_head,by_exact,features={},{},set()
    def add(entry,ws,kind,seen):
        v=variant(ws)
        if not v: return
        key=v['head']+'|'+'|'.join(sorted(v['needs']))
        if key in seen: return
        seen.add(key)
        by_head.setdefault(v['head'],[]).append({'entry':entry,**v,'variantKind':kind})
        features.update(w for w in v['needs'] if len(w)>=3 and not WEAK.search(w))
    for category,typ,code,*_ in rows:
        if not category or not typ or not re.fullmatch('[0-9]{10}',str(code)): continue
        if re.search('прочие|другие|разные|различные|универсальные',typ,re.I):
            features.update(stem(w) for w in words(typ) if len(stem(w))>=3 and not WEAK.search(stem(w)))
            continue
        entry={'category':category,'type':typ,'code':code,'categoryWords':set(map(stem,words(category)))}
        by_exact.setdefault(norm(typ),[]).append(entry)
        pieces=[p.strip() for p in re.split(r'\\s+(?:и|или)\\s+|[/,;]+',typ,flags=re.I) if p.strip()]
        seen=set();add(entry,words(typ),'full',seen)
        if len(pieces)>1:
            all_words=list(map(words,pieces));first=all_words[0]
            for i,part in enumerate(all_words):
                if not part: continue
                if i==0 and len(first)==1 and any(len(a)>1 for a in all_words[1:]):
                    for right in all_words[1:]:
                        if len(right)>1: add(entry,first+right[1:],'shared',seen)
                elif i>0 and len(first)>1:
                    anchor=next((w for w in first if stem(w)==head(first)),first[0])
                    add(entry,[anchor]+part,'shared',seen)
                else: add(entry,part,'part',seen)
    return {'byHead':by_head,'byExact':by_exact,'features':features}
""",
    # ===== csv_kind_matcher =====
    'csv_kind_matcher': """\"\"\"Conservative CSV kind candidate ranking; no row mutations.\"\"\"
import json
import pathlib
import re
from csv_kind_lexicon import build_index, words, stem, head, WEAK
from category_tnved import norm

TEXT_RULES=[('(^|[^a-zа-яё0-9])опор[а-яё]*\\\\s+(?:двигател[а-яё]*|двс)(?=$|[^a-zа-яё0-9])', '$1подушка двигателя'), ('(^|[^a-zа-яё0-9])стойк[а-яё]*\\\\s+стабилизатор[а-яё]*(?=$|[^a-zа-яё0-9])', '$1тяга стабилизатора'), ('(^|[^a-zа-яё0-9])(?:насос[а-яё]*\\\\s+водян[а-яё]*|водян[а-яё]*\\\\s+насос[а-яё]*|насос[а-яё]*\\\\s+охлаждающ[а-яё]*\\\\s+жидкост[а-яё]*|помп[а-яё]*\\\\s+систем[а-яё]*\\\\s+охлаждени[а-яё]*)(?=$|[^a-zа-яё0-9])', '$1помпа водяная'), ('(^|[^a-zа-яё0-9])(?:щ[её]тк[а-яё]*\\\\s+дворник[а-яё]*|дворник[а-яё]*)(?=$|[^a-zа-яё0-9])', '$1щетка стеклоочистителя'), ('(^|[^a-zа-яё0-9])дмрв(?=$|[^a-zа-яё0-9])', '$1расходомер'), ('(^|[^a-zа-яё0-9])(?:рулев[а-яё]*\\\\s+наконечник[а-яё]*|наконечник[а-яё]*\\\\s+рулев[а-яё]*)(?=$|[^a-zа-яё0-9])', '$1наконечник рулевой тяги'), ('(^|[^a-zа-яё0-9])насос[а-яё]*\\\\s+гидроусилител[а-яё]*(?=$|[^a-zа-яё0-9])', '$1насос ГУР'), ('(^|[^a-zа-яё0-9])форсунк[а-яё]*\\\\s+стеклоомывател[а-яё]*(?=$|[^a-zа-яё0-9])', '$1форсунка омывателя'), ('(^|[^a-zа-яё0-9])сальник[а-яё]*\\\\s+(?:коленчат[а-яё]*\\\\s+вал[а-яё]*|коленвал[а-яё]*|распредвал[а-яё]*|распределительн[а-яё]*\\\\s+вал[а-яё]*)(?=$|[^a-zа-яё0-9])', '$1сальник двигателя'), ('(^|[^a-zа-яё0-9])болт[а-яё]*\\\\s+головк[а-яё]*\\\\s+блок[а-яё]*\\\\s+цилиндр[а-яё]*(?=$|[^a-zа-яё0-9])', '$1болт ГБЦ'), ('(^|[^a-zа-яё0-9])кольц[а-яё]*\\\\s+поршн[а-яё]*(?=$|[^a-zа-яё0-9])', '$1кольцо поршневое'), ('(^|[^a-zа-яё0-9])фильтр[а-яё]*\\\\s+(?:очистк[а-яё]*\\\\s+)?топлив[а-яё]*(?=$|[^a-zа-яё0-9])', '$1фильтр топливный'), ('(^|[^a-zа-яё0-9])фильтр[а-яё]*\\\\s+(?:моторн[а-яё]*\\\\s+)?масл[а-яё]*(?=$|[^a-zа-яё0-9])', '$1фильтр масляный'), ('(^|[^a-zа-яё0-9])фильтр[а-яё]*\\\\s+(?:очистк[а-яё]*\\\\s+)?воздух[а-яё]*(?=$|[^a-zа-яё0-9])', '$1фильтр воздушный'), ('(^|[^a-zа-яё0-9])прокладк[а-яё]*\\\\s+головк[а-яё]*\\\\s+блок[а-яё]*\\\\s+цилиндр[а-яё]*(?=$|[^a-zа-яё0-9])', '$1прокладка ГБЦ')]
UNSAFE='\\\\b(?:filter|pump|pad|pads|disc|caliper|motor|starter|alternator|mount|arm|sensor|coil|radiator|joint|wiper|link|belt)[\\\\s,;:()\\\\[\\\\]\\\\/_–—-]+(?:(?:wear|pressure|mounting|retaining|drive)\\\\s+)?(?:housing|bracket|gasket|seal|cover|cap|pulley|bearing|bushing|bush|boot|bolt|relay|sensor|switch|solenoid|wire|wiring|connector|harness|clip|adapter|fuse|wrench|tool|repair\\\\s+kit)\\\\b'
SENSITIVE=set(['клапан','форсунк','кронштей','крышк','заглушк','пробк','втулк','шестерн','пружин','трубк','патрубк','датчик','кольц','вал','вентилят','мотор','опор','подушк','пыльник','муфт','шкив','поршень','ремкомпл','накладк','решетк','реле','радиатор','насос','фильтр','шланг','тяга','тяг','рычаг','ролик','ламп','стекл'])
REWRITES=json.loads(pathlib.Path(__file__).with_name("csv_kind_rewrites.json").read_text(encoding="utf-8"))


def rewrite(value):
    text=str(value or '')
    for r in REWRITES:
        if r['needles'] and not all(n in text.lower() for n in r['needles']): continue
        text=re.sub(r['pattern'],lambda m:m[1]+r['target'],text,flags=re.I)
    return text


def texts(name):
    raw=str(name or ''); result=[raw,rewrite(raw)]; s=raw
    for pattern,target in TEXT_RULES:
        s=re.sub(pattern,target.replace('$1',r'\\g<1>'),s,flags=re.I)
    if s!=raw: result.append(s)
    x=rewrite(s)
    if x!=s: result.append(x)
    return list(dict.fromkeys(result))


def name_lead(name,brand):
    lead=re.split(r'(?:^|\\s)(?:для|под|от|на|к|for|совместим(?:ый|ая|ые|о)?|подходит|применимость)(?=\\s|$)',str(name or ''),flags=re.I)[0]
    brand=str(brand or '').strip()
    if brand and lead.lower().startswith(brand.lower()):
        suffix=lead[len(brand):]
        if re.match(r'^[\\s,:;/—–-]+',suffix): lead=re.sub(r'^[\\s,:;/—–-]+','',suffix)
    else:
        lead=re.sub(r'^([A-Z][A-Z0-9&._-]{1,29})[\\s,:;/—–-]+(?=[А-ЯЁа-яё])','',lead)
    return lead


def choices(entries): return [x['category']+' / '+x['type'] for x in entries[:6]]


class CsvKindMatcher:
    def __init__(self,rows): self.index=build_index(rows)

    def candidates(self,name,brand=''):
        name=str(name or '').strip(); brand=str(brand or '').strip(); idx=self.index
        if not name: return {'status':'empty','matches':[],'choices':[]}
        exact=idx['byExact'].get(norm(name))
        if exact: return {'status':'matches','matches':exact,'choices':choices(exact)}
        if re.search(UNSAFE,name_lead(name,brand),re.I|re.ASCII): return {'status':'none','matches':[],'choices':[]}
        matches={}; near={}; all_tokens={}
        for text in texts(name):
            hw=head(words(name_lead(text,brand))); tokens=set(map(stem,words(text)))
            if not hw: continue
            all_tokens.update(dict.fromkeys(map(stem,words(text))))
            for x in idx['byHead'].get(hw,[]):
                entry=x['entry']; key=(norm(entry['category']),norm(entry['type']))
                overlap=sum(n in tokens for n in x['needs'])
                if key not in near or overlap>near[key]['overlap']: near[key]={'entry':entry,'overlap':overlap,'need':len(x['needs'])}
                if not all(n in tokens for n in x['needs']): continue
                score=len(x['needs'])*100+(5 if text==name else 0)
                if key not in matches or score>matches[key]['score']: matches[key]={'entry':entry,'score':score,'needs':x['needs'],'head':hw}
        ranked=sorted(matches.values(),key=lambda x:-x['score'])
        multi=re.search(r'(?:\\sи\\s|\\sand\\s|\\s\\+\\s|\\s&\\s)|[а-яё]\\s*[,;/+&]\\s*(?=[а-яё])',name,re.I)
        if multi and ranked:
            present=[t for t in all_tokens if t in idx['byHead']]; top=[x for x in ranked if x['score']==ranked[0]['score']]
            if len(present)>1 and any(any(h!=x['head'] and h not in x['needs'] for h in present) for x in top):
                return {'status':'ambiguous','matches':[],'choices':choices([x['entry'] for x in top])}
        if ranked:
            top=[x for x in ranked if x['score']==ranked[0]['score']]
            if len(top)==1 and len(top[0]['needs'])==1:
                hit=top[0]; entry=hit['entry']
                if hit['head']=='ремкомпл' and re.search('пороги.*арки.*ремкомплекты',entry['type'],re.I):
                    return {'status':'ambiguous','matches':[],'choices':choices([entry]),'reason':'Название не подтверждает, что ремкомплект относится к порогам или аркам'}
                extra=[t for t in all_tokens if t in idx['features'] and t!=hit['head'] and t not in entry['categoryWords'] and not WEAK.search(t)]
                if hit['head'] in SENSITIVE and extra:
                    return {'status':'ambiguous','matches':[],'choices':choices([entry]),'discriminators':extra[:8],'reason':'Название уточняет систему или деталь, а вид в словаре слишком общий'}
            entries=[x['entry'] for x in top]
            return {'status':'matches','matches':entries,'choices':choices(entries)}
        possible=sorted(near.values(),key=lambda x:(-x['overlap'],x['need']))
        if possible: return {'status':'ambiguous','matches':[],'choices':choices([x['entry'] for x in possible]),'reason':'Название не уточняет вид достаточно для однозначного выбора'}
        return {'status':'none','matches':[],'choices':[]}

    def guess(self,p):
        got=self.candidates(p.get('name'),p.get('brand'))
        if got['status']!='matches': return got
        m=got['matches']; category=norm(p.get('category'))
        blank=not str(p.get('category') or '').strip() or str(p.get('category') or '').strip().lower() in ('без категории','не определено')
        if not blank and (not p.get('_categoryNameAutoValue') or p.get('category')!=p['_categoryNameAutoValue']):
            same=[x for x in m if norm(x['category'])==category]
            if same: m=same
        if len(m)>1 and len({norm(x['type']) for x in m})==1:
            title=set(map(stem,words(p.get('name'))))
            ranks=[sum(w in title and not WEAK.search(w) for w in x['categoryWords']) for x in m]
            best=max(ranks)
            if best>0 and ranks.count(best)==1: m=[m[ranks.index(best)]]
        if len(m)==1: return {'status':'auto','category':m[0]['category'],'type':m[0]['type'],'code':m[0]['code'],'choices':[]}
        return {'status':'ambiguous','choices':choices(m),'reason':'Название соответствует нескольким видам из Категории12131.csv'}
""",
    # ===== dimension_oe =====
    'dimension_oe': """\"\"\"AnomalyOE evidence/tuple guards for independent OE donor search.

The catalogue/HVC search index and apply lifecycle are not implemented here yet.
\"\"\"
import copy
from enrichment_formula import truth
from dimension_policy import DIMS
from dimension_quarantine import number, explicit, direct_codes, compact
from ozon_identity import pair, codes


def tuple_of(p):return {k:number(p.get(k)) for k in DIMS}


def full(t):return all(number(t.get(k))>0 for k in DIMS)


def exact_tuple(a,b):
    return isinstance(a,dict) and isinstance(b,dict) and all(number(a.get(k))==number(b.get(k)) for k in DIMS)


def tuple_key(t):return compact([t['weight']]+sorted([t[k] for k in ('length','width','height')],reverse=True))


def auto_evidence(p):
    e=p.get('_dimensionAutoEvidence')
    return e if isinstance(e,dict) and not truth(p.get('_dimensionAutoConflict')) and not truth(p.get('_dimensionOeReview')) and not p.get('_dimensionImportIssues') and e.get('file') and e.get('identity')==pair(p) and full(e) and exact_tuple(e,tuple_of(p)) else None


def current_codes(p,automatic=False,mode='auto'):
    if automatic:return direct_codes(p,mode)
    out=list(codes([p.get('oe_numbers'),p.get('oe_list')],mode))
    return out or list(codes(p.get('oe_norm'),mode))


def issue_free(model,p,t):
    exp=explicit(p)
    candidate={'category':p.get('category') or '',**t,'net_weight':p.get('net_weight'),
               'volume':p.get('volume') if exp else 0,'_volumeExplicit':bool(p.get('_volumeExplicit')),
               '_sources':copy.deepcopy(p.get('_sources') or {})}
    return not model.evaluate(candidate)['issues']


def target_signature(model,p,mode='auto'):
    e=model.evaluate(p)
    return model.signature(p,e)+'|'+'\\x1f'.join(sorted(current_codes(p,False,mode)))+'|'+str(p.get('oeSource') or '')
""",
    # ===== dimension_oe_apply =====
    'dimension_oe_apply': """\"\"\"Validated OE proposal application; leaves proposed packaging quarantined.\"\"\"
import copy
from dimension_oe_search import OeSearch,identity
from dimension_oe import exact_tuple,full,tuple_of,issue_free,current_codes,auto_evidence,target_signature
from dimension_policy import source_allowed,similar_oe,rounded
from dimension_quarantine import explicit
from enrichment_formula import truth
from ozon_identity import key


def live(search,entry,target,automatic):
    if entry['kind']=='row':
        i=entry.get('donorIndex')
        if not isinstance(i,int) or not 0<=i<len(search.rows):return False
        ref=search.rows[i]
    else:
        ref=dict(search.ref.get('parts') or []).get(entry.get('partKey'))
    if ref is None or ref is target:return False
    verdict=source_allowed(target,ref,entry.get('matchedCode',''),search.mode)
    if not verdict['ok']:return False
    def oe_ok(cs):return any(similar_oe(key(c),verdict['oe']) for c in cs)
    if entry['kind']=='row':
        if ref.get('excluded') or ref.get('dimensionAnomalyBlocked'):return False
        if verdict['tier']=='oe' and not oe_ok(current_codes(ref,automatic,search.mode)):return False
        if automatic and not auto_evidence(ref):return False
        t=tuple_of(ref)
        return full(t) and exact_tuple(t,entry['tuple']) and issue_free(search.model,ref,t)
    evidence=ref.get('_dimensionEvidence') or {}
    if automatic:
        if not evidence.get('singleRow') or not evidence.get('file') or evidence.get('identity')!=entry['identity']:return False
        if verdict['tier']=='oe' and not (isinstance(evidence.get('oeCodes'),list) and oe_ok(evidence['oeCodes'])):return False
        # The automatic owner restrictions are already rechecked by find().
    link=dict(search.ref.get('cross') or []).get(entry.get('linkKey'))
    code_ok=verdict['tier']=='sku' or bool(link and similar_oe(key(link.get('oeNorm')),verdict['oe']))
    return code_ok and full(tuple_of(evidence)) and exact_tuple(tuple_of(evidence),entry['tuple'])


def apply_choices(search,proposals,selected,automatic,timestamp):
    if len(selected)!=len(set(selected)):raise ValueError('Повторные предложения OE')
    chosen=[]
    for i in selected:
        if isinstance(i,bool) or not isinstance(i,int) or not 0<=i<len(proposals):raise ValueError('Неверный индекс предложения OE')
        x=proposals[i];p=search.rows[x['targetIndex']];c=x['choice']
        if not c or not p.get('dimensionAnomalyBlocked') or p.get('excluded') or (automatic and truth(p.get('_dimensionOeReview'))) or x['signature']!=target_signature(search.model,p,search.mode) or not live(search,c,p,automatic) or not issue_free(search.model,p,c['tuple']):
            raise ValueError('Предложения устарели; повторите поиск по OE')
        chosen.append((x,p,c))
    results=[]
    for x,source,c in chosen:
        p=copy.deepcopy(source)
        before={k:p[k] for k in ('weight','length','width','height','volume') if k in p}
        via='по схожему OE '+c['link']['oe'] if c['link'].get('oe') else 'по тому же артикулу и бренду'
        exp=explicit(p);p.update(c['tuple'])
        if not exp:p['volume']=rounded(p['length']*p['width']*p['height']/1000,4);p['_volumeExplicit']=False
        p.pop('dimensionAnomalyAck',None)
        if not isinstance(p.get('_sources'),dict):p['_sources']={}
        old_sources={}
        for k in ('weight','length','width','height'):
            label=search.labels.get(k,k)
            old_sources[k]=copy.deepcopy(p['_sources'].get(k) or p['_sources'].get(label))
            s={'file':('Автосверка ' if automatic else 'Подбор ')+via+' (нужна проверка): '+c['source'],'date':timestamp}
            p['_sources'][k]=s;p['_sources'][label]=copy.deepcopy(s)
        review={'oe':c['link'].get('oe') or '', 'source':c['source'],'at':timestamp,'before':before,'beforeSources':old_sources,
                'after':copy.deepcopy(c['tuple']),'oeProofVersion':1,'method':'авто при импорте' if automatic else 'вручную'}
        previous=p.get('_dimensionOeReview')
        if isinstance(previous,dict):
            history=previous.get('history') if isinstance(previous.get('history'),list) else []
            review['history']=(history+[{k:v for k,v in previous.items() if k!='history'}])[-20:]
        p['_dimensionOeReview']=review
        log={'ts':timestamp,'article':p.get('article'),'category':p.get('category'),'before':before,'after':copy.deepcopy(c['tuple']),
             'heuristic':('Автосверка ' if automatic else 'Подбор ')+via+' · '+c['source']+' · требуется проверка упаковки'}
        for k in ('article','category'):
            if k not in p:log.pop(k,None)
        results.append({'targetIndex':x['targetIndex'],'row':p,'log':log})
    return results
""",
    # ===== dimension_oe_search =====
    'dimension_oe_search': """\"\"\"Independent AnomalyOE.find search over raw catalogue and HVC snapshots.\"\"\"
import copy
from dimension_oe import tuple_of,full,auto_evidence,exact_tuple,tuple_key,current_codes,issue_free,target_signature
from dimension_policy import pick,source_allowed,MAX_CANDIDATES
from dimension_quarantine import DimensionQuarantine,number
from enrichment_formula import truth
from ozon_identity import key


def identity(p):return key(p.get('article') or p.get('artikul'))+'|'+key(p.get('brand'))


def row_source(p,labels):
    src=p.get('_sources') if isinstance(p.get('_sources'),dict) else {}
    origins=[src.get(k) or src.get(labels.get(k)) or (src.get('Вес, кг') if k=='weight' else None) for k in ('weight','length','width','height')]
    first=origins[0]
    file=first.get('file') if first and all(x and x.get('file') and x.get('file')==first.get('file') and x.get('date')==first.get('date') for x in origins) else ''
    return ' · '+str(file) if file else ' · общий исходный файл ОВХ не подтверждён'


class OeSearch:
    def __init__(self,rows,reference,limits,mode='auto',labels=None):
        self.rows=copy.deepcopy(rows);self.ref=copy.deepcopy(reference)
        self.model=DimensionQuarantine(limits,mode);self.mode=mode;self.labels=labels or {}

    def find(self,target_indices,automatic=False):
        rows=self.rows;parts=dict(self.ref.get('parts') or []);by_oe=dict(self.ref.get('byOe') or [])
        registry=dict(self.ref.get('oe') or [])
        targets=[(i,rows[i]) for i in target_indices]
        need=list(dict.fromkeys(c for _,p in targets for c in current_codes(p,automatic,self.mode)))
        needed=set(need);target_ids={identity(p) for _,p in targets}
        donor_keys=target_ids|{k for c in need for k in by_oe.get(key(c),[])}
        index={};by_identity={};owners={}
        def add(c,e):
            if c not in needed:return
            bucket=index.setdefault(c,{'entries':{},'overflow':False})
            if bucket['overflow']:return
            bucket['entries'].setdefault(e['ekey'],e)
            if len(bucket['entries'])>64:bucket['entries']={};bucket['overflow']=True
        def add_identity(e):
            ident=e['identity']
            if not ident or ident=='|' or ident not in target_ids:return
            bucket=by_identity.setdefault(ident,[])
            if len(bucket)<8 and not any(x['ref'] is e['ref'] and x['ekey']==e['ekey'] for x in bucket):bucket.append(e)
        for i,q in enumerate(rows):
            ident=identity(q)
            if ident not in donor_keys and not truth(q.get('_dimensionAutoOeEvidence')):continue
            cs=current_codes(q,automatic,self.mode);matches=[x for x in cs if x in needed]
            if automatic and ident and (ident in target_ids or matches):owners[ident]=None if ident in owners else q
            if not (matches or ident in target_ids) or q.get('excluded') or q.get('dimensionAnomalyBlocked') or (automatic and truth(q.get('_dimensionOeReview'))):continue
            t=tuple_of(q);complete=full(t);evidence=auto_evidence(q) if automatic else None
            if not ((complete and issue_free(self.model,q,t)) or (not complete and any(x>0 for x in t.values()))):continue
            prior=q.get('_dimensionAutoEvidence')
            conflict=truth(q.get('_dimensionAutoConflict')) or bool(prior and prior.get('identity')==ident and not exact_tuple(prior,t))
            source='Каталог: '+str(q.get('article') or 'без артикула')+(' · '+str(q['brand']) if q.get('brand') else '')
            source+=(' · '+str(evidence['file'])+' · строка данных '+str(evidence.get('row','undefined'))) if evidence else row_source(q,self.labels)
            e=dict(kind='row',identity=ident,ref=q,donorIndex=i,tuple=t,complete=complete,autoEligible=bool(evidence),conflicting=conflict,tkey=tuple_key(t),source=source)
            e['ekey']=ident+'|'+e['tkey']
            for c in matches:add(c,e)
            if complete:add_identity(e)
        for c in need:
            for art_key in by_oe.get(key(c),[]):
                part=parts.get(art_key);ev=part.get('_dimensionEvidence') if part else None
                if not ev:continue
                ident=identity(part);owner=owners.get(ident)
                if automatic and ident in owners and (not owner or owner.get('excluded') or owner.get('dimensionAnomalyBlocked') or truth(owner.get('_dimensionOeReview')) or key(c) not in current_codes(owner,True,self.mode) or not auto_evidence(owner) or not exact_tuple(owner,ev)):continue
                t=tuple_of(ev);complete=full(t)
                if not complete or not issue_free(self.model,{'category':part.get('category') or '', '_volumeExplicit':False},t):continue
                e=dict(kind='hvc',identity=ident,ref=part,evidence=ev,linkKey=key(c)+'\\x1f'+art_key,partKey=art_key,code=c,tuple=t,complete=complete,tkey=tuple_key(t),
                       autoEligible=bool(ev.get('singleRow') and ev.get('file') and ev.get('identity')==ident and isinstance(ev.get('oeCodes'),list) and key(c) in [key(x) for x in ev['oeCodes']]),
                       source='Каталог V: '+str(part.get('artikul') or '')+(' · '+str(part['brand']) if part.get('brand') else '')+(' · '+str(ev['file']) if ev.get('file') else ' · общий исходный файл ОВХ не подтверждён'))
                e['ekey']=ident+'|'+e['tkey']
                add(c,e)
                if ev.get('singleRow'):add_identity(e)
        result=[]
        for target_index,p in targets:
            cs=current_codes(p,automatic,self.mode);own=identity(p);candidates={};overflow=False
            def take(e,matched):
                nonlocal overflow
                if e['ref'] is p or not e['identity'] or e['identity']=='|':return
                k=e['ekey']
                if k not in candidates:
                    if len(candidates)>=MAX_CANDIDATES:overflow=True;return
                    candidates[k]={**e,'matchedCode':'','matchedCodes':[]}
                hit=candidates[k]
                if matched:
                    if matched not in hit['matchedCodes']:hit['matchedCodes'].append(matched)
                    if not hit['matchedCode']:hit['matchedCode']=matched
            has_registry=any(key(c) in registry for c in cs)
            for c in cs:
                bucket=index.get(c)
                if not bucket:continue
                if bucket['overflow']:overflow=True;continue
                for e in bucket['entries'].values():take(e,c)
            for e in by_identity.get(own,[]):take(e,'')
            candidate_list=list(candidates.values());allowed=[];denied=0
            for c in candidate_list:
                verdict=source_allowed(p,c['ref'],c['matchedCode'],self.mode)
                if verdict['ok']:c['link']=verdict;allowed.append(c)
                else:denied+=1
            complete=[c for c in allowed if c['complete']];partial=[c for c in allowed if not c['complete']]
            valid=[];seen=set();limit_rejected=0
            for c in complete:
                if c['tkey'] in seen:continue
                seen.add(c['tkey'])
                if not issue_free(self.model,p,c['tuple']):limit_rejected+=1;continue
                valid.append(c)
            eligible=[c for c in valid if c['autoEligible']] if automatic else valid
            picked=pick(eligible);choice=picked['choice']
            if not candidate_list:
                status='Нет OE-номера у SKU' if not cs and not by_identity.get(own) else ('Есть сводный OE-реестр, но нет цельной записи с известным источником' if has_registry else 'Нет полной локальной записи донора')
            elif overflow:status='Слишком много совпадений по OE; нужна ручная проверка'
            elif not allowed:status='Другой артикул без схожего OE — данные не переносятся'
            elif not valid:
                if not complete:status='Только неполные данные: вес и три стороны должны быть из одной записи'
                elif limit_rejected:
                    lim=self.model.limits.get(self.model.limit_key(p.get('category'))) or dict(category=p.get('category') or '',maxW=400,maxL=300,maxVol=1000)
                    fmt=lambda n:format(number(n),',.0f').replace(',','\\u00a0')
                    status=f"Не проходит лимиты категории «{lim.get('category') or p.get('category') or '—'}»: вес ≤ {fmt(lim.get('maxW'))} кг · габарит ≤ {fmt(lim.get('maxL'))} см · объём ≤ {fmt(lim.get('maxVol'))} л"
                else:status='Нет полной локальной записи донора'
            elif not choice:status='Нет подтверждённой полной исходной строки: загрузите данные донора заново'
            else:
                n=picked['variants'];status=f'Выбраны меньшие из {n} вариантов · проверьте упаковку' if n>1 else f'Предложение; {n} совпадение с теми же значениями'
                status+=' · тот же артикул и бренд' if choice['link']['tier']=='sku' else ' · схожий OE'
                if partial:status+=' · неполные записи не использованы'
                if denied:status+=f' · отклонено источников: {denied}'
            # Transport stable source locators, not object references or precomputed browser choices.
            clean=lambda c:{k:v for k,v in c.items() if k not in ('ref','evidence','owner')}
            result.append(dict(targetIndex=target_index,signature=target_signature(self.model,p,self.mode),codes=cs,status=status,
                               choice=clean(choice) if choice else None,checked=False,hasRegistry=has_registry,link=choice['link'] if choice else None))
        return result
""",
    # ===== dimension_policy =====
    'dimension_policy': """\"\"\"DimPolicy donor authorization and deterministic tuple selection.\"\"\"
import math
import re
from decimal import Decimal, ROUND_HALF_UP
from dimension_quarantine import number, compact
from ozon_identity import key, codes

MAX_CODES=64
MAX_CANDIDATES=240
DIMS=('weight','length','width','height')


def loose_oe(value): return re.sub(r'(^|[^0-9])0+(?=[0-9])',r'\\1',key(value))


def similar_oe(a,b):
    x,y=key(a),key(b)
    return bool(x and y and (x==y or (len(x)>=5 and len(y)>=5 and loose_oe(x)==loose_oe(y))))


def policy_codes(p,mode='auto'):
    raw=list(codes([p.get('oe_numbers'),p.get('oe_list')],mode))
    if not raw and p.get('oe_norm'):raw+=list(codes(p['oe_norm'],mode))
    ev=p.get('_dimensionAutoOeEvidence')
    if isinstance(ev,dict) and isinstance(ev.get('entries'),list):
        raw += [key(x['code']) for x in ev['entries'] if isinstance(x,dict) and x.get('code')]
    return list(dict.fromkeys(x for x in raw if x))[:MAX_CODES]


def article(p):return key(p.get('article') if p.get('article') is not None else p.get('artikul'))


def source_allowed(target,candidate,matched_code='',mode='auto'):
    if target is None or candidate is None or target is candidate:
        return dict(ok=False,tier='',oe='',reason='нет источника')
    a,b=article(target),article(candidate);ab,bb=key(target.get('brand')),key(candidate.get('brand'))
    if a and b and a==b and ab and bb and ab==bb:
        return dict(ok=True,tier='sku',oe='',reason='тот же артикул и бренд')
    ca,cb=policy_codes(target,mode),policy_codes(candidate,mode);mc=key(matched_code)
    oe=''
    if cb:
        for y in cb:
            if any(similar_oe(x,y) for x in ca) or (mc and similar_oe(y,mc) and any(similar_oe(x,mc) for x in ca)):
                oe=y;break
    elif mc and any(similar_oe(x,mc) for x in ca):oe=mc
    if oe:return dict(ok=True,tier='oe',oe=oe,reason='схожий OE '+oe)
    return dict(ok=False,tier='',oe='',reason='другой артикул без схожего OE — данные не переносятся')


def js_number(value):
    # Number(), not the localized num()/parseFloat used by ordinary OVH fields.
    if value is None:return 0.0
    if isinstance(value,bool):return float(value)
    try:
        if isinstance(value,str):
            s=value.strip()
            if not s:return 0.0
            if re.fullmatch(r'0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+',s):return float(int(s,0))
        return float(value)
    except (ValueError,TypeError):return float('nan')


def valid_tuple(t):
    return isinstance(t,dict) and all(k in t and math.isfinite(js_number(t[k])) and js_number(t[k])>0 for k in DIMS)


def tuple_key(t):
    def fixed(v):
        n=js_number(v)
        if abs(n)>=1e21:return compact(n)
        return format(Decimal.from_float(n).quantize(Decimal('0.000001'),rounding=ROUND_HALF_UP),'f')
    return '|'.join(fixed(t.get(k)) for k in DIMS)


def rounded(v,d):
    if not math.isfinite(v):return 0
    f=10**d;a=abs(v*f)
    if not math.isfinite(a):return math.copysign(float('inf'),v)
    frac=a-math.floor(a)
    if 0.5-1e-9<frac<0.5:a=float(format(a,'.15g'))
    return math.copysign(math.floor(a+0.5)/f,v)


def measure(t):
    l,w,h,wt=(js_number(t.get(k)) for k in ('length','width','height','weight'))
    return (rounded(l*w*h/1000,6),rounded(max(l,w,h),4),rounded(wt,6),rounded(l+w+h,4))


def pick(candidates,is_valid=None):
    seen=set();rows=[];rejected=0
    for c in candidates:
        if not c or not c.get('complete') or not valid_tuple(c.get('tuple')):continue
        k=str(c.get('identity','undefined'))+'|'+tuple_key(c['tuple'])
        if k in seen:continue
        seen.add(k)
        if is_valid and not is_valid(c['tuple']):rejected+=1;continue
        rows.append(c)
    rows.sort(key=lambda c:measure(c['tuple']))
    return dict(choice=rows[0] if rows else None,variants=len(rows),rejected=rejected)
""",
    # ===== dimension_quarantine =====
    'dimension_quarantine': """\"\"\"Independent AnomalyDetector quarantine decisions and acknowledgement signatures.\"\"\"
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
    s=re.sub(r'\\s+','',text(v));s=re.sub('%$','',s)
    if ',' in s and '.' in s:
        s=s.replace('.','').replace(',','.',1) if s.rfind(',')>s.rfind('.') else s.replace(',','')
    elif ',' in s: s=s.replace(',','') if s.count(',')>1 else s.replace(',','.')
    elif s.count('.')>1: s=s.replace('.','')
    m=re.match(r'^[+-]?(?:[0-9]+\\.?[0-9]*|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?',s)
    if not m: return 0
    n=float(m[0]);return n if math.isfinite(n) else 0


def valid(v):
    if v is None or v=='': return True
    if isinstance(v,bool): return False
    if isinstance(v,(int,float)): return math.isfinite(v)
    return bool(re.fullmatch(r'[+-]?(?:(?:[0-9]{1,3}(?:[\\s\\u00a0\\u202f][0-9]{3})+)|[0-9]+)(?:[.,][0-9]+)?|[+-]?[.,][0-9]+',text(v).strip()))


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
        parts=re.split(r'[;,|\\r\\n]+|\\s+/\\s+',p['oeSource']) if mode=='auto' else re.split({'newline':r'\\r?\\n','comma':',','semicolon':';','slash':'/','pipe':r'\\|'}.get(mode,r'[/;,\\n\\r|]+'),p['oeSource'])
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
    def limit_key(v): return re.sub(r'\\s+',' ',text(v).strip().lower().replace('ё','е'))

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
        \"\"\"Two-phase confirmation: re-evaluate at both preview and approval.\"\"\"
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
""",
    # ===== enrichment_formula =====
    'enrichment_formula': """\"\"\"Restricted browser ExprLang grammar. Never uses eval/exec.\"\"\"
import math,re
from enrichment_transport import JSDate

UNDEFINED=object()
FORBID=set('''__proto__ constructor prototype getprototypeof setprototypeof defineproperty defineproperties getownpropertydescriptor getownpropertydescriptors getownpropertynames getownpropertysymbols isprototypeof hasownproperty propertyisenumerable __definegetter__ __definesetter__ __lookupgetter__ __lookupsetter__ caller callee arguments tosource valueof tostring tolocalestring toprimitivestring isview buffer object function reflect proxy symbol globalthis global window self top parent frames eval math json process module exports require'''.split())

def string(v):
    if v is UNDEFINED: return 'undefined'
    if v is None: return 'null'
    if v is True: return 'true'
    if v is False: return 'false'
    if isinstance(v,float) and not math.isfinite(v): return 'NaN' if math.isnan(v) else 'Infinity' if v>0 else '-Infinity'
    if isinstance(v,dict): return '[object Object]'
    if isinstance(v,list): return ','.join('' if x is None or x is UNDEFINED else string(x) for x in v)
    if isinstance(v,(int,float)):
        if v==0:return '0'
        text=repr(float(v)).lower()
        if 1e-6<=abs(v)<1e21:
            from decimal import Decimal
            return format(Decimal(text),'f').rstrip('0').rstrip('.') if '.' in format(Decimal(text),'f') else format(Decimal(text),'f')
        if 'e' in text:
            mantissa,exponent=text.split('e');exponent=int(exponent)
            return mantissa.removesuffix('.0')+'e'+('+' if exponent>=0 else '-')+str(abs(exponent))
        return text.removesuffix('.0')
    return str(v)

def truth(v): return False if v is UNDEFINED or v is None or isinstance(v,float) and math.isnan(v) else bool(v) if not isinstance(v,(dict,list)) else True

# ECMAScript whitespace (Python also treats some C0 controls as whitespace).
JS_SPACE='\\u0009\\u000a\\u000b\\u000c\\u000d\\u0020\\u00a0\\u1680\\u2000\\u2001\\u2002\\u2003\\u2004\\u2005\\u2006\\u2007\\u2008\\u2009\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000\\ufeff'

def number(v,allow_date=False):
    if isinstance(v,JSDate):
        if not allow_date:raise ValueError('В формуле дата участвует в арифметике')
        return v.milliseconds or 0
    if v is UNDEFINED or v is None:return 0
    if isinstance(v,bool):return 1 if v else 0
    if isinstance(v,(int,float)):return v if not isinstance(v,float) or not math.isnan(v) else 0
    if isinstance(v,(dict,list)):v=string(v)
    if isinstance(v,str):
        text=v.strip(JS_SPACE)
        if not text:return 0
        if text in ('Infinity','+Infinity','-Infinity'):return -math.inf if text[0]=='-' else math.inf
        if re.fullmatch(r'0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+',text):
            try:return float(int(text,0))
            except OverflowError:return math.inf
        if not re.fullmatch(r'[+-]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?',text):return 0
        return float(text)
    return 0

def arithmetic(v):
    return v if isinstance(v,(int,float)) else number(v)

def finite(v):
    n=number(v);return n if math.isfinite(n) else 0

def parsed(v):
    if isinstance(v,JSDate):raise ValueError('В формуле дата участвует в арифметике (num)')
    m=re.match(r'^[+-]?(?:[0-9]+\\.?[0-9]*|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?',''.join(c for c in string(v) if c not in JS_SPACE).replace(',','.',1))
    n=float(m[0]) if m else 0
    return n if math.isfinite(n) else 0

def power(a,b):
    x,y=finite(a),finite(b)
    try:return math.pow(x,y)
    except OverflowError:return -math.inf if x<0 and float(y).is_integer() and int(y)%2 else math.inf
    except ValueError:
        if x==0 and y<0:return -math.inf if math.copysign(1,x)<0 and float(y).is_integer() and int(y)%2 else math.inf
        return math.nan

def square_root(v):
    n=finite(v)
    return math.sqrt(n) if n>=0 else math.nan

def rounded(v,d=2):
    dd=number(d,allow_date=True)
    try:p=10.0**dd
    except OverflowError:p=math.inf
    x=number(v)*p;a=abs(x)
    if p==0 or not math.isfinite(p) or math.isnan(x):return math.nan
    if math.isinf(x):return x
    if .5-1e-9<a-math.floor(a)<.5:a=float(format(a,'.15g'))
    return (-1 if x<0 else 1)*math.floor(a+.5)/p

FUNCS={'pi':lambda:math.pi,'e':lambda:math.e,'num':parsed,'round':rounded,
 'min':lambda *a:min(map(number,a),default=math.inf),'max':lambda *a:max(map(number,a),default=-math.inf),
 'abs':lambda v:abs(finite(v)),'ceil':lambda v:math.ceil(finite(v)),'floor':lambda v:math.floor(finite(v)),
 'pow':power,'sqrt':square_root,'int':lambda v:math.trunc(finite(v)),
 'len':lambda v:len(('' if v is None or v is UNDEFINED else string(v)).encode('utf-16-le',errors='surrogatepass'))//2,
 'lower':lambda v:('' if v is None or v is UNDEFINED else string(v)).lower(),
 'upper':lambda v:('' if v is None or v is UNDEFINED else string(v)).upper(),
 'contains':lambda h,n:('' if n is None or n is UNDEFINED else string(n)).lower() in ('' if h is None or h is UNDEFINED else string(h)).lower(),
 'isBlank':lambda v:v is None or v is UNDEFINED or v=='',
 'coalesce':lambda *a:next((v for v in a if v is not None and v is not UNDEFINED and v!=''),'')}
PRECEDENCE={'||':1,'&&':2,'==':3,'===':3,'!=':3,'!==':3,'<':4,'>':4,'<=':4,'>=':4,'+':5,'-':5,'*':6,'/':6,'%':6}

class Parser:
    def __init__(self,expr):
        if any(c.isspace() and c not in JS_SPACE for c in expr):raise ValueError('Недопустимый пробельный символ')
        expr=''.join(' ' if c in JS_SPACE else c for c in expr)
        if len(expr)>400 or not re.fullmatch(r'[0-9\\s.\\+\\-*/%(),<>=!&|?:_a-zA-Zа-яА-ЯёЁ]*',expr): raise ValueError('Недопустимая формула')
        self.tokens=[];pos=0
        pattern=re.compile(r'\\s+|(?:\\d[\\d.]*|\\.\\d[\\d.]*)|[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё_0-9]*|===|!==|<=|>=|==|!=|&&|\\|\\||[+*/%(),?:.<>-]')
        while pos<len(expr):
            m=pattern.match(expr,pos)
            if not m: raise ValueError('Неизвестный токен')
            if not m[0].isspace(): self.tokens.append(m[0])
            pos=m.end()
        self.pos=0
    def peek(self): return self.tokens[self.pos] if self.pos<len(self.tokens) else ''
    def pop(self):
        v=self.peek()
        if not v: raise ValueError('Конец формулы')
        self.pos+=1;return v
    def expect(self,v):
        if self.pop()!=v: raise ValueError('Ожидалось '+v)
    def expression(self,minimum=0):
        tk=self.pop()
        if tk in ('+','-'): node=('unary',tk,self.expression(7))
        elif tk=='(': node=self.expression();self.expect(')')
        elif tk[0].isdigit() or tk.startswith('.') and len(tk)>1: node=('number',float(tk))
        elif re.fullmatch('[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё_0-9]*',tk):
            if self.peek()=='(':
                if tk not in FUNCS and tk!='if': raise ValueError('Неизвестная функция')
                self.pop();args=[]
                if self.peek()!=')':
                    args.append(self.expression())
                    while self.peek()==',': self.pop();args.append(self.expression())
                self.expect(')');node=('call',tk,args)
            else:
                path=[tk]
                while self.peek()=='.':
                    self.pop();key=self.pop()
                    if not re.fullmatch('[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё_0-9]*',key):raise ValueError('Ожидалось имя поля')
                    path.append(key)
                if any(k.lower() in FORBID for k in path): raise ValueError('Запрещённое поле')
                node=('field',path)
        else: raise ValueError('Неожиданный токен')
        while self.peek() in PRECEDENCE and PRECEDENCE[self.peek()]>=minimum:
            op=self.pop();node=('binary',op,node,self.expression(PRECEDENCE[op]+1))
        if minimum==0 and self.peek()=='?':
            self.pop();yes=self.expression();self.expect(':');node=('ternary',node,yes,self.expression())
        return node

def run(node,scope):
    kind=node[0]
    if kind=='number': return node[1]
    if kind=='field':
        v=scope
        for k in node[1]:
            v=v.get(k,UNDEFINED) if isinstance(v,dict) else len(v) if isinstance(v,list) and k=='length' else UNDEFINED
        return v
    if kind=='unary': return arithmetic(run(node[2],scope))*(-1 if node[1]=='-' else 1)
    if kind=='ternary': return run(node[2] if truth(run(node[1],scope)) else node[3],scope)
    if kind=='call':
        name,args=node[1:]
        if name=='if':
            i=1 if args and truth(run(args[0],scope)) else 2
            return run(args[i],scope) if len(args)>i else ''
        values=[run(a,scope) for a in args]
        if name not in ('min','max','coalesce'):
            arity=0 if name in ('pi','e') else 2 if name in ('round','pow','contains') else 1
            values=(values+[UNDEFINED]*arity)[:arity]
            if name=='round' and values[1] is UNDEFINED:values[1]=2
        return FUNCS[name](*values)
    op=node[1]
    # Browser ExprLang evaluates the denominator first and does not evaluate
    # the numerator at all for a falsy divisor (including NaN and signed zero).
    if op in ('/','%'):
        y=arithmetic(run(node[3],scope))
        if not truth(y):return math.inf if op=='/' else 0
        x=arithmetic(run(node[2],scope))
        if op=='/':return x/y
        return math.nan if math.isinf(x) else math.fmod(x,y)
    a=run(node[2],scope)
    if op=='&&': return run(node[3],scope) if truth(a) else a
    if op=='||': return a if truth(a) else run(node[3],scope)
    b=run(node[3],scope)
    if op in ('==','===','!=','!=='):
        equal=(a is b if isinstance(a,(dict,list)) or isinstance(b,(dict,list)) else type(a)==type(b) and a==b) or string(a)==string(b)
        return not equal if op.startswith('!') else equal
    x=a if isinstance(a,(int,float)) else number(a)
    y=b if isinstance(b,(int,float)) else number(b)
    if op=='+': return x+y
    if op=='-': return x-y
    if op=='*': return x*y
    return {'<':lambda:x<y,'>':lambda:x>y,'<=':lambda:x<=y,'>=':lambda:x>=y}[op]()

def evaluate(expr,row):
    parser=Parser(str(expr or ''));node=parser.expression()
    if parser.peek(): raise ValueError('Лишний токен')
    return run(node,{**row,'p':row})
""",
    # ===== enrichment_rules =====
    'enrichment_rules': """\"\"\"Ordered user enrichment rules, preserving explicit category assignments.\"\"\"
import copy,math
from enrichment_formula import evaluate,UNDEFINED,string
from category_kind import blank


def apply_rules(row,rules,context,match):
    p=copy.deepcopy(row)
    for r in rules:
        if r.get('kind')!='enrich' or not r.get('enabled'): continue
        target=r.get('target_val')
        if not isinstance(target,str) or target.lower() in ('__proto__','constructor','prototype'): continue
        if target=='category' and (p.get('_categoryNameExplicit') or
            (p.get('category') and not blank(p['category']) and p['category']!=p.get('_categoryNameAutoValue'))): continue
        if not match(p,r.get('field'),r.get('op'),r.get('value')): continue
        try: value=evaluate(r.get('formula'),p)
        except (ValueError,TypeError,OverflowError,ZeroDivisionError): continue
        before=p.get(target,UNDEFINED)
        if value is UNDEFINED: p.pop(target,None)
        else: p[target]=value
        if target=='category':
            p['category']='' if value is UNDEFINED or value is None else string(value).strip()
            if p['category']!=before and p['category'].strip():
                p.update(_categoryNameAutoValue=p['category'],_categoryNameStatus='auto',_categoryNameMethod='enrich',
                    _categoryNameSource=string(p.get('name') or ''),_categoryNameBrand=string(p.get('brand') or ''),
                    _categoryNameRevision=(context or {}).get('version',''),_categoryNameChoices=[])
    return p
""",
    # ===== enrichment_transport =====
    'enrichment_transport': """\"\"\"Lossless nonfinite-number sidecars for JSON enrichment requests/responses.\"\"\"
import copy
import math
import re
from dataclasses import dataclass

KINDS={'nan':math.nan,'positive':math.inf,'negative':-math.inf}
FORBIDDEN={'__proto__','constructor','prototype'}


@dataclass(frozen=True)
class JSDate:
    milliseconds: object
    text: str
    json_value: object

    def __str__(self):return self.text


def date_value(value,entry):
    ms=entry.get('milliseconds');text=entry.get('text')
    if not isinstance(text,str) or len(text)>256:raise ValueError('Неверное строковое представление Date')
    if ms is None:
        if value is not None or text!='Invalid Date':raise ValueError('Неверный Invalid Date')
    elif type(ms) not in (int,float) or not math.isfinite(ms) or ms!=int(ms) or abs(ms)>8640000000000000 or not isinstance(value,str) or not re.fullmatch(r'(?:[0-9]{4}|[+-][0-9]{6})-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\\.[0-9]{3}Z',value):
        raise ValueError('Неверное значение Date')
    if ms is not None:
        year_s,month,day,hour,minute,second,milli=re.fullmatch(r'([+-]?[0-9]+)-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})\\.([0-9]{3})Z',value).groups()
        year,month,day,hour,minute,second,milli=map(int,(year_s,month,day,hour,minute,second,milli))
        canonical_year=f'{year:04}' if 0<=year<=9999 else ('+' if year>0 else '-')+f'{abs(year):06}'
        if year_s!=canonical_year or not 1<=month<=12 or not 0<=hour<24 or not 0<=minute<60 or not 0<=second<60:raise ValueError('Неканонический Date')
        leap=year%4==0 and (year%100!=0 or year%400==0)
        if not 1<=day<=[31,29 if leap else 28,31,30,31,30,31,31,30,31,30,31][month-1]:raise ValueError('Неверный день Date')
        # Proleptic Gregorian epoch conversion, including JS years outside
        # datetime's 1..9999 range. Python // is the required floor division.
        y=year-(month<=2);era=y//400;yoe=y-era*400
        doy=(153*(month+(-3 if month>2 else 9))+2)//5+day-1
        days=era*146097+yoe*365+yoe//4-yoe//100+doy-719468
        if (((days*24+hour)*60+minute)*60+second)*1000+milli!=ms:raise ValueError('Date не соответствует миллисекундам')
    return JSDate(ms,text,value)


def encode_special(value):
    entries=[]
    def visit(v,path):
        if isinstance(v,JSDate):
            entries.append({'path':path,'kind':'date','milliseconds':v.milliseconds,'text':v.text})
            return v.json_value
        if isinstance(v,float) and not math.isfinite(v):
            entries.append({'path':path,'kind':'nan' if math.isnan(v) else 'positive' if v>0 else 'negative'})
            return None
        if isinstance(v,dict):return {k:visit(x,path+[k]) for k,x in v.items()}
        if isinstance(v,list):return [visit(x,path+[i]) for i,x in enumerate(v)]
        return v
    return visit(value,[]),entries


def decode_special(value,entries):
    if not isinstance(entries,list):raise ValueError('Неверные типы чисел обогащения')
    output=copy.deepcopy(value);seen=set()
    for entry in entries:
        if not isinstance(entry,dict) or not isinstance(entry.get('kind'),str) or entry['kind'] not in (*KINDS,'date'):raise ValueError('Неверный специальный тип числа')
        path=entry.get('path')
        if not isinstance(path,list) or not path or len(path)>128 or any(type(k) not in (int,str) or isinstance(k,str) and k in FORBIDDEN for k in path):raise ValueError('Неверный путь специального числа')
        identity=tuple(path)
        if identity in seen:raise ValueError('Повторяющийся путь специального числа')
        seen.add(identity);parent=output
        for key in path[:-1]:
            if isinstance(parent,list) and type(key) is int and 0<=key<len(parent):parent=parent[key]
            elif isinstance(parent,dict) and isinstance(key,str) and key in parent:parent=parent[key]
            else:raise ValueError('Путь специального числа отсутствует')
        key=path[-1]
        if isinstance(parent,list) and type(key) is int and 0<=key<len(parent):pass
        elif isinstance(parent,dict) and isinstance(key,str) and key in parent:pass
        else:raise ValueError('Путь специального числа отсутствует')
        if entry['kind']=='date':parent[key]=date_value(parent[key],entry)
        else:
            if parent[key] is not None:raise ValueError('Специальное число должно заменять JSON null')
            parent[key]=KINDS[entry['kind']]
    return output


def equivalent(a,b):
    \"\"\"Value equality for copied JSON rows, treating preserved NaN as unchanged.\"\"\"
    if isinstance(a,bool) or isinstance(b,bool):return type(a) is type(b) and a==b
    if isinstance(a,dict) and isinstance(b,dict):return a.keys()==b.keys() and all(equivalent(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(equivalent(x,y) for x,y in zip(a,b))
    if isinstance(a,float) and isinstance(b,float) and math.isnan(a) and math.isnan(b):return True
    return a==b
""",
    # ===== export_custom =====
    'export_custom': """\"\"\"Independent general-export custom-cell conversion, matching exportCatalogCellValue.\"\"\"
import math
import re
from enrichment_formula import JS_SPACE, UNDEFINED, string


def export_number(value):
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        return value if math.isfinite(value) else 0
    if value is None or value is UNDEFINED or value=='':return 0
    text=''.join(c for c in string(value) if c not in JS_SPACE)
    if text.endswith('%'):text=text[:-1]
    comma,dot=',' in text,'.' in text
    if comma and dot:
        text=text.replace('.','').replace(',','.',1) if text.rfind(',')>text.rfind('.') else text.replace(',','')
    elif comma:text=text.replace(',','') if text.count(',')>1 else text.replace(',','.',1)
    elif text.count('.')>1:text=text.replace('.','')
    match=re.match(r'^[+-]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?',text.lstrip(JS_SPACE))
    n=float(match[0]) if match else 0
    return n if math.isfinite(n) else 0


def custom_cell(raw,key,formatted,date_keys=(),nonfinite_keys=(),textual=False,special=None):
    value=raw.get(key,UNDEFINED)
    if textual:
        if key in nonfinite_keys:return (special or {}).get(key,'Infinity')
        return '' if value is None or value is UNDEFINED else string(value)
    # Older descriptors without c.txt retain the generic formatter contract.
    if key in date_keys:return 0
    if key in nonfinite_keys:return 0 if formatted else None
    if formatted and value is not None and value is not UNDEFINED and value!='':return export_number(value)
    return None if value is UNDEFINED else value
""",
    # ===== export_formulas =====
    'export_formulas': """\"\"\"Independent catalogue Excel formula generation. No eval or browser formulas.\"\"\"
import math
import re

ROUND_FIELDS = dict(zip(
    'revenue cogs acquiring lastMile logistics scDelivery packaging storage returnStorage penalties nonStd lateShip listing returns tax perUnitNet'.split(),
    'effPrice costMult agencyFeePerSku buyerDeliveryUnit uLog uSc uPack storageUnit returnStorageUnit slaPenaltyPerUnit nonStdUnit lateShipUnit listingUnit uRet taxUnit netProfit'.split()))
PERCENT_FIELDS={'commission':'commPct','paymentTransfer':'acqPct','boost':'boostPct','cofin':'cofinPct'}
NET_FIELDS='revenue cogs commission specialFee acquiring paymentTransfer lastMile boost logistics scDelivery packaging storage processing returns returnStorage penalties listing tax cofin nonStd lateShip'.split()
TEMPLATES={
 'deficit':'{stock}-{minStock}',
 'shipReady':'IF(AND({stock}>0,{visible}="да",{stock}>={minStock}),"да","нет")',
 'status':'IF(OR({weight}<=0,{length}<=0,{width}<=0,{height}<=0),"Заблокировано системой",IF({excluded}="да","Исключён",IF({deletePending}="да","На удаление",IF(AND({markRequired}="да",{markCompliant}="нет"),"Ошибка маркировки",IF({visible}="нет",IF(OR({visibleReason}="virtual_stock_low",{visibleReason}="min_stock_threshold"),"Скрыт (мало остатка)","Скрыт (витрина)"),IF({deficit}<0,"Дефицит",IF({shipReady}="да","Готов к отгрузке","Норма")))))))',
 'specialFee':'IF({cheapFbsFlag}="да",ROUND(ROUND({effPrice}*{cheapFbsRate}/100,2),2),0)',
 'processing':'ROUND(({uTransitPack}+{prUnit}),2)',
 'costPerUnit':'ROUND({effPrice}-{netProfit},2)',
 'margin':'IFERROR(ROUND(IF({revenue}>0,{netProfit}/{revenue}*100,IFERROR({perUnitNet}/{price}*100,0)),1),0)',
 'roi':'IFERROR(ROUND(IF({cogs}>0,{netProfit}/{cogs}*100,IFERROR({perUnitNet}/{cost}*100,0)),1),0)',
 'costMult':'ROUND(MAX(0,{cost})*{multUsed},2)',
 'priceByMarkup':'ROUND({costMult}*(1+{markupPct}/100),2)',
 'markupOnCost':'IFERROR(IF({tgtPrice}>0,ROUND(({tgtPrice}/{costMult}-1)*100,1),""),"")',
 'markupMargin':'IFERROR(ROUND(({price}-{costMult})/{costMult}*100,1),0)',
 'markupProfit':'IFERROR(ROUND({netProfit}/{cogs}*100,1),0)',
}
FORMULA_KEYS=frozenset(TEMPLATES)|ROUND_FIELDS.keys()|PERCENT_FIELDS.keys()|{'volume','netProfit'}


def formula(key,row,refs,dim_unit='cm'):
    \"\"\"Missing selected dependency means a cached-value-only cell.\"\"\"
    class Refs(dict):
        def __missing__(self,k):return refs[k]+str(row)
    r=Refs()
    try:
        if key in ROUND_FIELDS:raw='ROUND('+r[ROUND_FIELDS[key]]+',2)'
        elif key in PERCENT_FIELDS:raw='ROUND(ROUND('+r['effPrice']+'*'+r[PERCENT_FIELDS[key]]+'/100,2),2)'
        elif key=='netProfit':raw='ROUND('+'-'.join(r[k] for k in NET_FIELDS if k not in ('specialFee','penalties') or k in refs)+',2)'
        elif key=='volume':raw=('IF({volumeExplicit}="да",{volumeInput},ROUND({length}*{width}*{height}/'+('1000000' if dim_unit=='mm' else '1000')+',4))').format_map(r)
        elif key in TEMPLATES:raw=TEMPLATES[key].format_map(r)
        else:return None
        return raw
    except KeyError:return None


def column_letter(index):
    text='';index+=1
    while index:index,n=divmod(index-1,26);text=chr(65+n)+text
    return text


def references(meta,sheets):
    refs={}
    for si,sheet in enumerate(sheets):
        name=sheet['name'].replace("'","''")
        for ci,index in enumerate(sheet['indices']):
            key=meta[index].get('key')
            if key=='article' and key in refs:continue
            refs[key]=('' if si==0 else "'"+name+"'!")+column_letter(ci)
    return refs


def cached_formula(key,row,refs,value,unavailable=False,dim_unit='cm'):
    if unavailable:return None
    raw=formula(key,row,refs,dim_unit)
    if raw and (len(raw)>8192 or re.search(r'[\\x00-\\x08\\x0b-\\x1f\\x7f\\[\\]{};`|]',raw) or not re.fullmatch(r'''[0-9A-Za-zА-Яа-яЁё_$.,:!<>=+\\-*/%()?'"\\s]+''',raw)):return None
    if raw and isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and not raw.upper().startswith('IFERROR('):
        raw='IFERROR('+raw+',"")'
    return raw

INVALID_FIELDS=frozenset(['revenue', 'cogs', 'commission', 'specialFee', 'acquiring', 'paymentTransfer', 'lastMile', 'boost', 'cofin', 'logistics', 'scDelivery', 'packaging', 'storage', 'processing', 'returns', 'returnStorage', 'penalties', 'nonStd', 'lateShip', 'listing', 'tax', 'netProfit', 'perUnitNet', 'margin', 'roi', 'costPerUnit', 'fcProfit', 'breakEvenPrice', 'tgtPrice', 'priceToSet', 'priceForApi', 'profitWB', 'marginWB', 'beWB', 'tgtWB', 'profitOzon', 'marginOzon', 'beOzon', 'tgtOzon', 'profitYM', 'marginYM', 'beYM', 'tgtYM', 'profitMM', 'marginMM', 'profitAvito', 'marginAvito', 'beAvito', 'tgtAvito', 'profitDiff', 'effPrice', 'contribution', 'breakEvenUnits', 'fcSales', 'fcRevenue', 'markupProfit', 'uRet', 'uLog', 'uSc', 'uPack', 'uTransitPack', 'storageUnit', 'taxUnit', 'listingUnit', 'prUnit', 'buyerDeliveryUnit', 'returnStorageUnit', 'nonStdUnit', 'lateShipUnit', 'logWB', 'retWB', 'ozonIsKgt', 'ozonLiters', 'dropoffOzon', 'midMileOzon', 'lastMileOzon', 'logOzon', 'retOzon', 'handOverOzon', 'realFbsServiceOzon', 'nonStdOzon', 'lateShipOzon', 'shipDiscOzon', 'retStoreOzon'])
YM_FIELDS=frozenset('returnLogK returnPerKg returnFixed returnStorageDays returnStoragePerDay slaPenaltyPerUnit tariffLastMileP tariffCategoryPath tariffSource tariffQuality tariffQuoteAgeDays tariffQuoteReasons'.split())
MARKET_FIELDS={prefix+suffix:mp for suffix,mp in [('WB','WB'),('Ozon','OZON'),('YM','YM'),('MM','MM'),('Avito','AVITO')] for prefix in ['profit','margin','be','tgt']}


def marketplace(key,group):
    if key in YM_FIELDS:return 'YM'
    if group=='ozn' or re.match(r'^ozon_',key,re.I) or re.search(r'^ozon[A-Z]|Ozon$',key):return 'OZON'
    for suffix,mp in [('WB','WB'),('YM','YM'),('MM','MM'),('Avito','AVITO')]:
        if key.endswith(suffix):return mp
    if key.startswith('cheapFbs'):return 'YM'
    return ''


def unavailable(p,key,group='calc'):
    from enrichment_formula import truth
    if truth(p.get('modelReviewRequired')) and group=='calc':return True
    if (truth(p.get('noBuyInconsistent')) or truth(p.get('modelReviewRequired'))) and key in INVALID_FIELDS:return True
    mp=MARKET_FIELDS.get(key)
    markets=p.get('mp') or {}
    if mp:
        result=markets.get(mp)
        if truth(p.get('noBuyInconsistent')) or truth(p.get('modelReviewRequired')) or result is None or truth(result.get('returnRateInvalid')) or truth(result.get('inputUnavailable')) or result.get('comparisonEligible') is False:return True
    selected=mp or (marketplace(key,group) if group=='calc' else '')
    result=markets.get(selected) or {}
    if selected and (truth(result.get('inputUnavailable')) or result.get('comparisonEligible') is False):return True
    if truth(p.get('priceInputsIncomplete')) and key in ('priceForApi','priceToSet','breakEvenPrice','tgtPrice'):return True
    return truth(p.get('missingTariffBlocked')) and not selected and key in INVALID_FIELDS


def prepare_options(meta,sheets,options):
    if not isinstance(options,dict) or type(options.get('enabled')) is not bool or options.get('dim_unit','cm') not in ('cm','mm'):
        raise ValueError('Неверные настройки Excel-формул')
    if not isinstance(meta,list) or any(not isinstance(m,dict) or not isinstance(m.get('key'),str) for m in meta):
        raise ValueError('Неверные описания колонок формул')
    for m in meta:
        if m.get('server_formula') and m['key'] not in FORMULA_KEYS:raise ValueError('Формула не поддерживается движком: '+m['key'])
    if not options['enabled']:return {}
    if not isinstance(sheets,list) or not 1<=len(sheets)<=10:raise ValueError('Неверные листы формул')
    for sheet in sheets:
        if not isinstance(sheet,dict) or not isinstance(sheet.get('name'),str) or not sheet['name'] or len(sheet['name'])>31 or re.search(r'[\\[\\]:*?/\\\\]',sheet['name']):raise ValueError('Неверное имя листа формул')
        indices=sheet.get('indices')
        if not isinstance(indices,list) or any(type(i) is not int or not 0<=i<len(meta) for i in indices) or len(set(indices))!=len(indices):raise ValueError('Неверные колонки листа формул')
    return references(meta,sheets)
""",
    # ===== hvc_enrichment =====
    'hvc_enrichment': """\"\"\"Server implementation of HVC.enrichOne using an explicit HVC reference snapshot.

References are inputs (parts/OE/byArt/byOe), never browser-computed enrichments.
The legacy donors API is deliberately not used: it cannot represent HVC's graph.
\"\"\"
import copy
import math
import re

DIMS = ('weight', 'length', 'width', 'height')
EXACT_PLACEHOLDERS = {'Без категории', 'Разное', 'Прочее', 'Не определено'}
PLACEHOLDERS = {'без категории', 'разное', 'прочее', 'не определено'}


def norm(value):
    return re.sub('[^A-Z0-9А-ЯЁ]', '', str(value or '').upper())


def enrich_rows(rows, reference, mode='auto', cat_mode='artbrand', columns=None,
                timestamp='', number=float, rounded=round, allowed=None):
    parts = dict(reference.get('parts') or [])
    registry = dict(reference.get('oe') or [])
    by_art = dict(reference.get('byArt') or [])
    by_oe = dict(reference.get('byOe') or [])
    unsafe = set(reference.get('unsafeKeys') or [])
    unsafe_oe = set(reference.get('unsafeOe') or [])
    separator = reference.get('groupSeparator', ' / ')
    columns = columns or {}
    def enabled(k): return bool(columns.get(k, True))
    def num(v):
        try: return number(v)
        except (ValueError, TypeError): return 0
    def meaningful(v, category=False):
        text = str(v or '').strip()
        return '' if category and text.lower() in PLACEHOLDERS else text
    def complete(t):
        return bool(t) and all(math.isfinite(num(t.get(k))) and num(t.get(k)) > 0 for k in DIMS)
    def measure(t):
        w, l, wi, h = (num(t.get(k)) for k in DIMS)
        return (rounded(l * wi * h / 1000, 6), rounded(max(l, wi, h), 4), rounded(w, 6), rounded(l + wi + h, 4))
    cache = {}
    def aggregate(key):
        oes = by_art.get(key, [])
        cache_key = tuple(oes)
        if cache_key in cache: return cache[cache_key]
        rep = None
        agg = {}
        categories = set()
        smallest = None
        smallest_oe = ''
        analogs, seen = [], set()
        self_art = key.split('|')[0]
        for oe in oes:
            record = registry.get(oe) if oe not in unsafe_oe else None
            # Same guard as _oeAggOf; tnved alone does not make a representative.
            if record and (record.get('name') or record.get('applicability') or (record.get('category') and str(record['category']).strip() not in EXACT_PLACEHOLDERS)
                           or record.get('length') or record.get('dimensions_str')):
                if rep is None: rep = record
            if record and record.get('category') and str(record['category']).strip() not in EXACT_PLACEHOLDERS: categories.add(str(record['category']).strip())
            per_oe = []
            per_seen = set()
            for holder in by_oe.get(oe, []):
                if holder in unsafe: continue
                part = parts.get(holder)
                if not part: continue
                evidence = part.get('_dimensionEvidence')
                if complete(evidence) and (smallest is None or measure(evidence) < measure(smallest)):
                    smallest, smallest_oe = evidence, oe
                for field in ('name', 'applicability', 'category', 'tnved'):
                    # Browser OE aggregate does not populate tnved from parts.
                    if field == 'tnved': continue
                    value = meaningful(part.get(field), field == 'category')
                    if not agg.get(field) and value: agg[field] = value
                if part.get('category') and str(part['category']).strip() not in EXACT_PLACEHOLDERS: categories.add(str(part['category']).strip())
                art = part.get('artikul') or part.get('article') or ''
                an = norm(art)
                if an and an not in per_seen:
                    per_seen.add(an)
                    if len(per_oe) < 40: per_oe.append((an, art))
            for an, art in per_oe:
                if an != self_art and an not in seen:
                    seen.add(an)
                    if len(analogs) < 40: analogs.append(art)
        result = {'rep': rep or {}, 'agg': agg, 'conflict': len(categories) > 1,
                  'smallest': smallest, 'smallestOe': smallest_oe, 'analogs': ', '.join(analogs)}
        cache[cache_key] = result
        return result
    result = []
    for source in rows:
        p = copy.deepcopy(source)
        key = norm(p.get('article')) + '|' + norm(p.get('brand'))
        if key in unsafe:
            result.append(p); continue
        pt = parts.get(key)
        raw_oe = str(p.get('oe_norm') or '').strip()
        known = any(oe in registry or oe in by_oe for oe in [raw_oe] + re.split(r'[/;,|\\s\\x01]+', raw_oe) if oe)
        pair_known = bool(norm(p.get('article')) and norm(p.get('brand')) and pt is not None)
        h = aggregate(key)
        def group():
            out, seen = [], set()
            def push(k):
                if len(out) >= 500 or k in unsafe: return
                part = parts.get(k)
                art = (part.get('artikul') or part.get('article')) if part else k.split('|')[0]
                an = norm(art)
                if an and an not in seen:
                    seen.add(an); out.append(art)
            push(key)
            for oe in by_art.get(key, []):
                holders = by_oe.get(oe, [])
                if len(holders) > 2000: continue
                for holder in holders: push(holder)
            return out
        def run_pass(selected, cat_only):
            if selected == 'oe' and not known: return
            if selected != 'oe' and not pair_known: return
            if not cat_only:
                if enabled('analog_list'): p['analog_list'] = h['analogs']
                if enabled('group_articles'):
                    entries = group()
                    p['group_articles'], p['groupSize'] = separator.join(entries), len(entries)
            for field in (('category', 'tnved') if cat_only else ('name', 'applicability')):
                occupied = meaningful(p.get(field))
                if field == 'category': occupied = occupied and occupied not in EXACT_PLACEHOLDERS
                if not enabled(field) or occupied: continue
                if selected == 'oe':
                    if field == 'category' and h['conflict']: continue
                    options = [(h['rep'].get(field), 'OE-реестр'), (h['agg'].get(field), 'аналоги по OE')]
                else:
                    options = [((pt or {}).get(field), 'Артикул + Бренд')]
                for value, label in options:
                    value = meaningful(value, field == 'category')
                    if value:
                        p[field] = value
                        p.setdefault('_sources', {})[field] = {'file': 'Каталог V (' + ('OE' if selected == 'oe' else 'Артикул + Бренд') + '): ' + label, 'date': timestamp}
                        break
            if cat_only: return
            candidates = []
            if pt and complete(pt.get('_dimensionEvidence')):
                candidates.append((pt['_dimensionEvidence'], 'снимок того же артикула и бренда', ''))
            if selected == 'oe' and complete(h['smallest']):
                candidates.append((h['smallest'], 'меньший комплект по схожему OE', h['smallestOe']))
            passing = []
            for t, label, oe in candidates:
                if any(num(p.get(k)) > 0 and num(p.get(k)) != num(t.get(k)) for k in DIMS): continue
                if allowed and not allowed(p, t): continue
                passing.append((t, label, oe))
            if (passing and not p.get('_dimensionOeReview') and not p.get('dimensionAnomalyBlocked')
                    and any(enabled(k) and num(p.get(k)) <= 0 for k in DIMS)):
                t, label, oe = min(passing, key=lambda x: measure(x[0]))
                before = {k: p.get(k, 0) for k in DIMS}
                for k in DIMS:
                    if enabled(k) and num(p.get(k)) <= 0:
                        p[k] = num(t[k])
                        p.setdefault('_sources', {})[k] = {'file': 'Каталог V: ' + label + ' (нужна проверка)', 'date': timestamp}
                p['_dimensionOeReview'] = {'oe': oe, 'source': 'Каталог V: ' + label + ' · сверьте упаковку',
                    'at': timestamp, 'before': before, 'after': {k: p.get(k, 0) for k in DIMS}}
                p.pop('dimensionAnomalyAck', None)
            if pt:
                if not p.get('multiplicity'): p['multiplicity'] = pt.get('multiplicity', 0)
                if not p.get('image_url') and pt.get('image_url'): p['image_url'] = pt['image_url']
                if enabled('barcode') and not p.get('barcode') and pt.get('barcode'): p['barcode'] = pt['barcode']
        for selected, cat_only in ((mode, False), (cat_mode, True)):
            passes = ('oe', 'artbrand') if selected == 'auto' else (selected,)
            for current in passes: run_pass(current, cat_only)
        result.append(p)
    return result
""",
    # ===== js_regex =====
    'js_regex': """\"\"\"Translate common non-Unicode ECMAScript RegExp constructs to Python re.

Used by matchCond (no flags other than i). No JavaScript runtime is invoked.
This is not a complete ECMAScript regexp implementation; see audit limitations.
\"\"\"
import re
from functools import lru_cache
from enrichment_formula import JS_SPACE


def utf16(text):
    data=text.encode('utf-16-le',errors='surrogatepass')
    return ''.join(chr(data[i]|data[i+1]<<8) for i in range(0,len(data),2))


def canonical(char):
    # ECMA Canonicalize without /u: uppercase, but do not fold a non-ASCII
    # code unit to ASCII or expand one code unit to several (e.g. sharp s).
    upper=char.upper()
    return char if len(upper)!=1 or ord(char)>=128 and ord(upper)<128 else upper


SPACE=''.join(re.escape(c) for c in JS_SPACE)
WORD='A-Za-z0-9_'


def class_pattern(p,start):
    \"\"\"Parse a legacy JS class as UTF-16 sets before case canonicalization.\"\"\"
    i=start;negative=i<len(p) and p[i]=='^'
    if negative:i+=1
    atoms=[]
    predefined={'d':set(map(ord,'0123456789')),
                'w':set(map(ord,'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_')),
                's':set(map(ord,JS_SPACE))}
    while i<len(p) and p[i]!=']':
        c=p[i];i+=1;dash=c=='-'
        if c=='\\\\':
            if i==len(p):raise ValueError('Trailing class escape')
            c=p[i];i+=1;dash=False
            if c.lower() in predefined:
                chars=predefined[c.lower()]
                atoms.append((chars if c.islower() else set(range(65536))-chars,None,False));continue
            if c in 'xu':
                n=2 if c=='x' else 4;digits=p[i:i+n]
                if len(digits)==n and re.fullmatch('[0-9a-fA-F]+',digits):c=chr(int(digits,16));i+=n
            elif c=='c' and i<len(p) and (p[i].isascii() and (p[i].isalnum() or p[i]=='_')):
                c=chr(ord(p[i].upper())%32);i+=1
            elif c in '01234567':
                digits=c
                while i<len(p) and p[i] in '01234567' and len(digits)<(3 if digits[0] in '0123' else 2):digits+=p[i];i+=1
                c=chr(int(digits,8))
            else:c={'b':'\\b','f':'\\f','n':'\\n','r':'\\r','t':'\\t','v':'\\v'}.get(c,c)
        atoms.append(({ord(c)},ord(c),dash))
    if i==len(p):raise ValueError('Unclosed character class')
    chars=set();j=0
    while j<len(atoms):
        if j+2<len(atoms) and atoms[j+1][2]:
            left,right=atoms[j][1],atoms[j+2][1]
            if left is not None and right is not None:
                if left>right:raise ValueError('Invalid class range')
                chars.update(range(left,right+1));j+=3;continue
        chars.update(atoms[j][0]);j+=1
    codes=sorted({ord(canonical(chr(n))) for n in chars})
    if not codes:return ('[\\\\s\\\\S]' if negative else '(?!)'),i+1
    # Compress the explicit set; escape every endpoint so Python class syntax
    # (including set-operation-looking punctuation) cannot alter its meaning.
    ranges=[];first=last=codes[0]
    def emit(a,b):
        esc=lambda n:'\\\\u%04x'%n
        return esc(a) if a==b else esc(a)+esc(b) if b==a+1 else esc(a)+'-'+esc(b)
    for n in codes[1:]:
        if n==last+1:last=n
        else:ranges.append(emit(first,last));first=last=n
    ranges.append(emit(first,last))
    return '['+('^' if negative else '')+''.join(ranges)+']',i+1


def capture_layout(p):
    starts={};ends={};names={};stack=[];i=0
    while i<len(p):
        c=p[i];i+=1
        if c=='\\\\':i+=1;continue
        if c=='[':
            while i<len(p) and p[i]!=']':
                if p[i]=='\\\\':i+=1
                i+=1
            i+=1;continue
        if c=='(':
            name=None
            capture=p[i:i+1]!='?'
            if p[i:i+2]=='?<' and p[i+2:i+3] not in ('=','!'):
                end=p.find('>',i+2)
                if end<0:raise ValueError('Invalid named capture')
                name=p[i+2:end];capture=True
            number=len(starts)+1 if capture else None
            if capture:
                starts[i-1]=number
                if name is not None:
                    if not name or not name.replace('$','_').isidentifier() or name in names:raise ValueError('Invalid or duplicate capture name')
                    names[name]=number
            stack.append(number)
        elif c==')':
            if not stack:raise ValueError('Unmatched closing group')
            number=stack.pop()
            if number is not None:ends[number]=i
    if stack:raise ValueError('Unclosed group')
    return starts,ends,names


def reference(number,position,ends):
    # In legacy JS a reference to a not-yet-participating capture succeeds
    # with the empty string. Python instead fails on unmatched captures.
    if ends.get(number,position+1)>position:return '(?:)'
    return '(?(js%d)(?P=js%d)|)'%(number,number)


@lru_cache(maxsize=512)
def compile_pattern(pattern):
    p=utf16(pattern);out=[];i=0
    captures,ends,names=capture_layout(p)
    while i<len(p):
        c=p[i];i+=1
        if c=='\\\\':
            if i==len(p):raise ValueError('Trailing escape')
            e=p[i];i+=1
            classes={'d':'0-9','D':'^0-9','w':WORD,'W':'^'+WORD,'s':SPACE,'S':'^'+SPACE}
            if e in classes:
                out.append('['+classes[e]+']');continue
            if e in ('b','B'):
                out.append('(?a:\\\\'+e+')');continue
            if e in ('x','u'):
                size=2 if e=='x' else 4;digits=p[i:i+size]
                if len(digits)==size and re.fullmatch('[0-9a-fA-F]+',digits):
                    out.append(re.escape(canonical(chr(int(digits,16)))));i+=size
                else:out.append(re.escape(canonical(e)))
                continue
            if e=='c':
                if i<len(p) and p[i].isascii() and p[i].isalpha():
                    out.append(re.escape(chr(ord(p[i].upper())%32)));i+=1
                else:out.append(re.escape('\\\\c'))
                continue
            if e in 'fnrtv':
                out.append(re.escape({'f':'\\f','n':'\\n','r':'\\r','t':'\\t','v':'\\v'}[e]));continue
            if e in '0123456789':
                end=i
                while end<len(p) and p[end] in '0123456789':end+=1
                digits=e+p[i:end];number=int(digits)
                if e!='0' and number<=len(captures):
                    out.append(reference(number,i-2,ends));i=end;continue
                if e in '01234567':
                    octal=e
                    while i<len(p) and p[i] in '01234567' and len(octal)<(3 if e in '0123' else 2):octal+=p[i];i+=1
                    out.append(re.escape(canonical(chr(int(octal,8)))))
                else:out.append(e)
                continue
            if e=='k' and i<len(p) and p[i]=='<' and names:
                end=p.find('>',i+1);name=p[i+1:end]
                if end<0 or name not in names:raise ValueError('Invalid named reference')
                out.append(reference(names[name],i-2,ends));i=end+1;continue
            # Identity escapes (\\a, \\z, ...) are literals in legacy JS mode.
            out.append(re.escape(canonical(e)));continue
        if c=='[':
            translated,i=class_pattern(p,i);out.append(translated);continue
        if c=='.':out.append('[^\\n\\r\\u2028\\u2029]');continue
        if c=='$':out.append('\\\\Z');continue
        if c=='(' and i-1 in captures:
            out.append('(?P<js%d>'%captures[i-1])
            if p[i:i+2]=='?<':i=p.index('>',i+2)+1
            continue
        if c=='(' and i<len(p) and p[i]=='?':
            if p[i:i+2] in ('?:','?=','?!'):out.append('('+p[i:i+2]);i+=2;continue
            if p[i:i+3] in ('?<=','?<!'):out.append('('+p[i:i+3]);i+=3;continue
            raise ValueError('Non-ECMAScript group')
        if c in '*+?}' and i<len(p) and p[i]=='+':raise ValueError('Possessive quantifier is not ECMAScript')
        out.append(canonical(c))
    return re.compile(''.join(out))


def search(pattern,text):
    try:return compile_pattern(pattern).search(''.join(map(canonical,utf16(text)))) is not None
    except (ValueError,re.error,OverflowError,RecursionError):return False
""",
    # ===== mark_status =====
    'mark_status': """\"\"\"MarkStatus.check and its pipeline hide action; independent of legal classification.\"\"\"
import copy
import re


from enrichment_formula import string, truth, JS_SPACE


def js_string(v):return '' if v is None else string(v)


def normalize(v): return js_string(v).strip(JS_SPACE).lower().replace('ё','е')

VALID = set(map(normalize, ['введён в оборот','введен в оборот','в обороте','активен','активно','проверен','валиден','валидный','valid','ok']))
INVALID = set(map(normalize, ['выведен из оборота','выведен','выбыл','выбытие','продан','продано','реализован',
    'списан','списание','возвращён','возвращен','возврат','аннулирован','отозван','отменён','отменен',
    'просрочен','истёк','истек','недействителен','не действителен','не введён в оборот','не введен в оборот',
    'ошибка маркировки','ошибка','error','invalid','expired','cancelled','canceled','withdrawn']))


def check(status, code, required, settings=None):
    if not truth(required): return {'ok':True,'kind':'skip'}
    cfg=settings or {}
    s=normalize(status)
    # JS String.length counts UTF-16 code units, not Python Unicode characters.
    has_code=len(js_string(code).strip(JS_SPACE).encode('utf-16-le',errors='surrogatepass'))//2>=8
    if cfg.get('markRequireCode') is not False and not has_code:
        return {'ok':False,'kind':'code','reason':'нет кода маркировки'}
    if not s: return {'ok':False,'kind':'empty','reason':'статус маркировки не указан'}
    def split(v): return {normalize(x) for x in re.split('[;,]',js_string(v)) if normalize(x)}
    if s in INVALID or s in split(cfg.get('markInvalidStatuses')):
        return {'ok':False,'kind':'invalid','reason':'недопустимый статус маркировки: '+js_string(status if truth(status) else '')}
    if s in VALID or s in split(cfg.get('markValidStatuses')): return {'ok':True,'kind':'valid'}
    return {'ok':True,'kind':'unknown'}


def apply(row, settings=None):
    p=copy.deepcopy(row)
    cfg=settings or {}
    outcome=check(p.get('markStatus'),p.get('markCode'),truth(p.get('markRequired')),cfg)
    p['markCompliant']=outcome['ok']
    if truth(cfg.get('autoHideMark')) and truth(p.get('markRequired')) and not outcome['ok']:
        p.update(visible=False,visibleReason='честный_знак',policyAction='Скрыть с витрины',policyReason=outcome['reason'])
    return p,outcome
""",
    # ===== name_category =====
    'name_category': """\"\"\"NameCategory selection and non-destructive apply, using raw dictionary inputs.\"\"\"
import copy
import re
from name_category_expansions import EXPANSIONS

ALIASES = dict(filter='фильтр', oil='масляный', air='воздушный', cabin='салонный', fuel='топливный', water='водяной', brake='тормозной', pads='колодки', pad='колодки', disc='диск', pump='насос', headlight='фара')
STOP = set('для или под над без при как the and на по of из в с a авто'.split())
MARKERS = ('_categoryNameAutoValue','_categoryNameSource','_categoryNameBrand','_categoryNameRevision','_categoryNameStatus','_categoryNameChoices','_categoryNameMethod')

def norm(v): return str(v or '').lower().replace('ё','е')
def words(v): return [w for w in re.sub('[^a-zа-я0-9]+',' ',norm(v)).split() if len(w)>=3]
def stem(word):
    x = word
    if re.fullmatch('[а-я]+',x):
        x = re.sub('(?:иями|ями|ами|ого|его|ому|ему|ыми|ими|иях|иях|ий|ый|ой|ая|яя|ое|ее|ые|ие|ых|их|ую|юю|ов|ев|ей|ам|ям|ах|ях)$','',x)
        if len(x)>=4: x=re.sub('[аеёиоуыэюяь]$','',x)
    if x=='колодок': x='колодк'
    return x[:8]

def tokens(value):
    text=str(value or '')
    if re.search('водян[а-я]*',text,re.I):
        text=re.sub(EXPANSIONS[0][0],r'\\g<1>насос',text,flags=re.I)
    if re.search('сальник[а-я]*\\s+(?:коленвал|распредвал)',text,re.I): text+=' двигателя'
    if re.search(r'(?:мотоцикл|скутер|мопед|снегоход|квадроцикл|(?:^|\\s)мото(?=\\s|$))',text,re.I): text+=' мототехника'
    for pattern,replacement in EXPANSIONS[1:]:
        text=re.sub(pattern,replacement.replace('$1',r'\\g<1>'),text,flags=re.I)
    text=re.sub('ремонтн[а-я]*\\s+комплект[а-я]*','ремкомплект',norm(text))
    return [ALIASES.get(w,w) for w in re.sub('[^a-zа-я0-9]+',' ',text).split()
            if len(ALIASES.get(w,w))>=2 and ALIASES.get(w,w) not in STOP and not re.match('^(автомобил|легков|машин)',ALIASES.get(w,w))]

def guess(p, context, match):
    name=str(p.get('name') or '').strip()
    if not name: return {'status':'empty','choices':[]}
    lower, brand=norm(name),norm(p.get('brand'))
    ws=words(name); stems=[stem(ALIASES.get(w,w)) for w in ws]
    dictionary=[]; anchors=set()
    for c in context.get('categories',[]):
        if not c.get('active') or not c.get('name'): continue
        terms=[words(t) for t in re.split('[|,;]',str(c.get('keywords') or ''))]; terms=[t for t in terms if t]
        cs=[[stem(ALIASES.get(w,w)) for w in term] for term in terms]
        dictionary.append((c,terms,cs))
        if c.get('kind')=='base': anchors.update(x for t in cs for x in t)
    title=tokens(name)
    if title and title[0].startswith('ремкомплект'): title.pop(0)
    head=''; known=set(context.get('heads',[]))
    for w in title:
        adj=not re.search('(?:ение|ание|тие|ствие)$',w) and re.search('(?:ый|ий|ой|ая|яя|ое|ее|ые|ие|ых|их|ого|его|ому|ему|ыми|ими|ую|юю)$',w)
        if adj or re.match('^(комплект|набор|оригинал)',w): continue
        k=stem(w)
        if k in known: head=k; break
    anchor=head if head in anchors and head not in ('рычаг','стойк','опор','тяг','кольц','подуш','подушк') else ''
    for r in context.get('rules',[]):
        if r.get('kind')=='cat' and r.get('enabled') and r.get('target_val') and match({'src':lower,'brand':brand},'brand' if r.get('field')=='brand' else 'src',r.get('op'),r.get('value')):
            return {'status':'auto','category':r['target_val'],'method':'rule','choices':[]}
    scores=[]
    for c,terms,cs in dictionary:
        if c.get('kind')=='base' and c['name']=='Фильтры' and not any(w.startswith(('фильтр','filter')) for w in ws): continue
        best=-1; unique=set()
        for term,ts in zip(terms,cs):
            if anchor and c.get('kind')=='base' and anchor not in ts: continue
            used=set()
            for part,part_stem in zip(term,ts):
                found=next((i for i,w in enumerate(ws) if i not in used and (w.startswith(part) or stems[i]==part_stem)),None)
                if found is None: break
                used.add(found)
            else:
                if c.get('kind')=='base' and c['name']=='Топливная система' and len(term)==1 and term[0] in ('форсунк','распылител'):
                    if re.search('(?:стекло)?омывател',lower) or not re.search(r'(?:топлив|дизел|бензин|инжектор|впрыск|fuel|injector|тнвд|газов|гбо|common[\\s-]*rail)',lower,re.I): continue
                if c.get('kind')=='base' and c['name']=='Жидкости и масла' and term==['масл'] and not any(re.fullmatch('(масло|масла|маслу|маслом)',w) for w in ws): continue
                unique.update(used); best=max(best,len(term)*1000+sum(min(len(x),12) for x in term)*10)
        if best>=0: scores.append((c['name'],best+min(len(unique),9)))
    scores.sort(key=lambda x:-x[1])
    if not scores: return {'status':'none','choices':[]}
    top=[x[0] for x in scores if x[1]==scores[0][1]]
    return {'status':'ambiguous','choices':top[:6]} if len(top)>1 else {'status':'auto','category':top[0],'method':'dictionary','choices':[]}

def apply(p,context,enabled,match):
    p=copy.deepcopy(p)
    auto=bool(p.get('_categoryNameAutoValue')) and p.get('category')==p['_categoryNameAutoValue']
    if p.get('_categoryNameAutoValue') and not auto:
        for k in MARKERS: p.pop(k,None)
    category=str(p.get('category') or '')
    blank=not category.strip() or category.strip().lower() in ('без категории','не определено')
    # Explicit-source recognition is passed as an input verdict from FIELD_ALIAS.
    if not auto and (not blank or ((p.get('_categoryNameExplicit') or p.get('_categoryExplicitSource')) and category.strip())): return p
    if not enabled:
        if auto and (p.get('_categoryNameSource')!=str(p.get('name') or '') or p.get('_categoryNameBrand')!=str(p.get('brand') or '')): p['_categoryNameStatus']='stale'
        return p
    if auto and p.get('_categoryNameSource')==str(p.get('name') or '') and p.get('_categoryNameBrand')==str(p.get('brand') or '') and p.get('_categoryNameRevision')==context.get('version') and p.get('_categoryNameStatus')!='stale': return p
    g=guess(p,context,match)
    p.update(_categoryNameSource=str(p.get('name') or ''),_categoryNameBrand=str(p.get('brand') or ''),_categoryNameRevision=context.get('version',''),_categoryNameStatus=g['status'],_categoryNameMethod=g.get('method',''),_categoryNameChoices=g.get('choices',[])[:6])
    if g.get('category'): p['category']=g['category']; p['_categoryNameAutoValue']=g['category']
    else:
        if auto or not category.strip(): p['category']='Без категории'
        p.pop('_categoryNameAutoValue',None)
    return p
""",
    # ===== name_category_expansions =====
    'name_category_expansions': """# Ordered lexical replacements from OzonAuto._expandRaw.
EXPANSIONS = [['(^|[^a-zа-я0-9])помп[а-я]*(?=$|[^a-zа-я0-9])', '$1насос'], ['(^|[^a-zа-яё0-9])фильтр[а-яё]*\\\\s+(?:очистк[а-яё]*\\\\s+)?топлив(?:а|о|у|ом|е|н[а-яё]*)(?=$|[^a-zа-яё0-9])', '$1фильтр топливный'], ['(^|[^a-zа-яё0-9])лямбда[\\\\s-]*зонд[а-яё]*(?=$|[^a-zа-яё0-9])', '$1датчик кислорода'], ['(^|[^a-zа-яё0-9])прокладк[а-яё]*\\\\s+головк[а-яё]*\\\\s+блок[а-яё]*\\\\s+цилиндр[а-яё]*(?=$|[^a-zа-яё0-9])', '$1прокладка ГБЦ'], ['(^|[^a-zа-яё0-9])прокладк[а-яё]*\\\\s+клапанн[а-яё]*\\\\s+крышк[а-яё]*(?=$|[^a-zа-яё0-9])', '$1прокладка клапанной крышки двигателя'], ['(^|[^a-zа-яё0-9])помп[а-яё]*\\\\s+охлажден[а-яё]*\\\\s+(?:двигател[а-яё]*|двс)(?=$|[^a-zа-яё0-9])', '$1насос водяной'], ['(^|[^a-zа-яё0-9])насос[а-яё]*\\\\s+охлаждающ[а-яё]*\\\\s+жидкост[а-яё]*(?=$|[^a-zа-яё0-9])', '$1насос водяной'], ['(^|[^a-zа-яё0-9])автоламп[а-яё]*(?=$|[^a-zа-яё0-9])', '$1лампа автомобильная'], ['(^|[^a-zа-яё0-9])трос[а-яё]*\\\\s+(?:ручник[а-яё]*|стояночн[а-яё]*\\\\s+тормоз[а-яё]*)(?=$|[^a-zа-яё0-9])', '$1трос ручного тормоза'], ['(^|[^a-zа-яё0-9])свеч[а-яё]*\\\\s+накал[а-яё]*(?=$|[^a-zа-яё0-9])', '$1свеча накаливания'], ['(^|[^a-zа-яё0-9])сайлент[\\\\s-]+блок[а-яё]*(?=$|[^a-zа-яё0-9])', '$1сайлентблок'], ['(^|[^a-zа-яё0-9])радиатор[а-яё]*\\\\s+(?:двигател[а-яё]*|двс)(?=$|[^a-zа-яё0-9])', '$1радиатор двигателя охлаждения'], ['(^|[^a-zа-яё0-9])форсунк[а-яё]*\\\\s+стеклоомывател[а-яё]*(?=$|[^a-zа-яё0-9])', '$1форсунка омывателя'], ['(^|[^a-zа-яё0-9])(?:жикл[её]р|распылител)[а-яё]*\\\\s+(?:стекло)?омывател[а-яё]*(?=$|[^a-zа-яё0-9])', '$1форсунка омывателя'], ['(^|[^a-zа-я0-9])бензонасос[а-я]*(?=$|[^a-zа-я0-9])', '$1насос топливный'], ['(^|[^a-zа-я0-9])дворник[а-я]*(?=$|[^a-zа-я0-9])', '$1щетка стеклоочистителя'], ['(^|[^a-zа-я0-9])маслофильтр[а-я]*(?=$|[^a-zа-я0-9])', '$1фильтр масляный'], ['(^|[^a-zа-я0-9])фильтр[а-я]*\\\\s+салон[а-я]*(?=$|[^a-zа-я0-9])', '$1фильтр салонный'], ['(^|[^a-zа-я0-9])фильтр[а-я]*\\\\s+масла(?=$|[^a-zа-я0-9])', '$1фильтр масляный'], ['(^|[^a-zа-я0-9])wiper\\\\s+blades?(?=$|[^a-zа-я0-9])', '$1щетка стеклоочистителя'], ['(^|[^a-zа-я0-9])spark\\\\s+plugs?(?=$|[^a-zа-я0-9])', '$1свеча зажигания'], ['(^|[^a-zа-я0-9])timing\\\\s+belts?(?=$|[^a-zа-я0-9])', '$1ремень грм'], ['(^|[^a-zа-я0-9])timing\\\\s+chains?(?=$|[^a-zа-я0-9])', '$1цепь грм']]
""",
    # ===== ozon_auto =====
    'ozon_auto': """\"\"\"Ozon preferred-assignment lifecycle; lexical inference is injected separately.

This is not yet a standalone name classifier. The detail callback must implement
OzonAuto.detailWithCategory, not supply browser-generated presentation values.
\"\"\"
import copy
import re

MARKERS = ('SourceName', 'SourceBrand', 'Version', 'Status', 'Choices',
           'SuggestedType', 'CategorySignature', 'Reason')
PREFIX = '_ozonName'


def apply_preferred(model, row, *, detail, version, category_signature,
                    registry=None, applicability=None, force=False,
                    enabled=True, force_name=False, identity_unsafe=False,
                    reference_version=0):
    p = copy.deepcopy(row)
    if identity_unsafe:
        return p, dict(category=p.get('ozon_category') or '', type=p.get('ozon_type') or '',
                       source=p.get('ozon_type_src') or 'none',
                       reason='неоднозначный SKU или OE-источник — автоматическая типизация пропущена')
    old = copy.deepcopy(p) if p.get('ozon_type_src') == 'keyword' and (p.get('ozon_type') or p.get('ozon_category')) else None
    if not p.get('ozon_type_src') and (p.get('ozon_type') or p.get('ozon_category')):
        p.update(ozon_type_src='import', ozon_type_basis='import', ozon_type_conf='unverified')
    p, r = model.apply(p, registry, applicability, force, reference_version)
    if r and r['source'] in ('auto', 'manual', 'import'):
        if r['source'] in ('manual', 'import'):
            p['ozon_error'] = ''
        for key in MARKERS:
            p.pop(PREFIX + key, None)
        return p, r
    if r and re.search(r'conflict|invalid_(?:oe|applicability)_mapping', r.get('reason', ''), re.I):
        p[PREFIX+'Status'] = 'oe_conflict' if re.search('conflict', r['reason'], re.I) else 'oe_invalid'
        p[PREFIX+'Choices'] = []
        for key in ('SourceName', 'SourceBrand', 'Version', 'CategorySignature', 'Reason'):
            p.pop(PREFIX+key, None)
        return p, r
    name, brand = str(p.get('name') or ''), str(p.get('brand') or '').strip()
    current = bool(old and old.get(PREFIX+'SourceName') == name and old.get(PREFIX+'SourceBrand') == brand
                   and old.get(PREFIX+'Version') == version and old.get(PREFIX+'CategorySignature') == category_signature)

    def result():
        return dict(category=p.get('ozon_category') or '', type=p.get('ozon_type') or '', source='keyword',
                    basis=p.get('ozon_type_basis') or 'keyword', score=p.get('ozon_type_score') or 0,
                    confidence='low', reason='', oe='', applicability='')

    def restore():
        for key in ('ozon_category', 'ozon_type'):
            if key in old:
                p[key] = old[key]
            else:
                p.pop(key, None)
        p.update(ozon_type_score=old.get('ozon_type_score') or 0, ozon_type_src='keyword',
                 ozon_type_conf='low', ozon_type_basis=old.get('ozon_type_basis') or 'keyword', ozon_error='')
        for key in ('ozon_description_category_id', 'ozon_type_id'):
            if old.get(key) is not None:
                p[key] = old[key]
            else:
                p.pop(key, None)
        for key, default in (('Choices', []), ('SuggestedType', ''), ('CategorySignature', ''), ('Reason', '')):
            p[PREFIX+key] = old.get(PREFIX+key) or default

    if not (enabled or force_name):
        if old:
            restore()
            p[PREFIX+'Status'] = (old.get(PREFIX+'Status') or 'auto') if current else 'stale'
            return p, result()
        if PREFIX+'SourceName' in p and any(p.get(PREFIX+k) != v for k,v in
                (('SourceName',name), ('SourceBrand',brand), ('Version',version), ('CategorySignature',category_signature))):
            p[PREFIX+'Status'] = 'stale'
        return p, r
    if current and old.get(PREFIX+'Status') != 'stale':
        restore()
        p[PREFIX+'Status'] = old.get(PREFIX+'Status') or 'auto'
        return p, result()
    d = detail(p)
    p.update({PREFIX+'SourceName':name, PREFIX+'SourceBrand':brand, PREFIX+'Version':version,
              PREFIX+'CategorySignature':category_signature, PREFIX+'Reason':d.get('reason') or '',
              PREFIX+'Status':d['status'], PREFIX+'Choices':(d.get('choices') or [])[:6],
              PREFIX+'SuggestedType':d.get('suggestedType') or ''})
    match = d.get('match')
    if not match:
        p.pop('ozon_description_category_id', None)
        p.pop('ozon_type_id', None)
        if d['status'] != 'category_ambiguous' or not d.get('suggestedType'):
            return p, r
        p.update(ozon_category='', ozon_type=d['suggestedType'], ozon_type_score=0)
    else:
        p.update(ozon_category=match['cat'], ozon_type=match['type'], ozon_type_score=match['score'])
        if match.get('catId') and match.get('typeId'):
            p.update(ozon_description_category_id=match['catId'], ozon_type_id=match['typeId'])
        else:
            p.pop('ozon_description_category_id', None)
            p.pop('ozon_type_id', None)
    p.update(ozon_type_src='keyword', ozon_type_conf='low', ozon_type_basis=d.get('basis') or 'keyword', ozon_error='')
    return p, result()
""",
    # ===== ozon_category =====
    'ozon_category': """\"\"\"Ozon name proposals checked against internal category/kind dictionary.\"\"\"
import re
from category_tnved import CategoryTnved, norm
from csv_kind_lexicon import stem as csv_stem, words as csv_words
from csv_kind_matcher import name_lead, UNSAFE
from ozon_name import OzonNameClassifier, tokens, stem, head
from ozon_reference import strict_key

PREFERENCE = {'фильтры': 'Автофильтры', 'детали крепежные': 'Автомобильный крепеж', 'автохимия и автокосметика': 'Автохимия и автокосметика', 'тормозная система': 'Запчасти для легковых автомобилей', 'подвеска': 'Запчасти для легковых автомобилей', 'подвеска и рулевое управление': 'Запчасти для легковых автомобилей', 'сцепление': 'Запчасти для легковых автомобилей', 'освещение': 'Запчасти для легковых автомобилей', 'трансмиссия / кпп': 'Запчасти для легковых автомобилей', 'детали кпп': 'Запчасти для легковых автомобилей', 'двигатель': 'Запчасти для легковых автомобилей', 'детали двигателя': 'Запчасти для легковых автомобилей', 'электрика и электроника': 'Запчасти для легковых автомобилей', 'электрооборудование': 'Запчасти для легковых автомобилей', 'свечи и высоковольтные провода': 'Запчасти для легковых автомобилей', 'система охлаждения': 'Запчасти для легковых автомобилей', 'насосы и компрессоры': 'Запчасти для легковых автомобилей', 'ремни и ролики двигателя': 'Запчасти для легковых автомобилей', 'подшипники': 'Запчасти для легковых автомобилей', 'ремкомплекты': 'Запчасти для легковых автомобилей', 'резинотехнические изделия': 'Запчасти для легковых автомобилей', 'тросы': 'Запчасти для легковых автомобилей', 'трубки': 'Запчасти для легковых автомобилей'}


def kind_key(value):
    ws=tokens(value,literal=True);h=head(ws)
    ns=sorted(set(stem(w) for w in ws if len(stem(w))>=2))
    return h+'\\x1f'+'\\x1e'.join(ns) if h and ns else ''


class OzonCategoryClassifier(OzonNameClassifier):
    def __init__(self,types,category_rows,revision):
        super().__init__(types)
        self.category=CategoryTnved(category_rows,revision)
        self.by_kind={};self.kind_categories={};self.csv_words=set()
        weak=r'^(?:передн|задн|верхн|нижн|лев|прав|боков|внутрен|наружн|внешн|оригин|нов|комплект|набор|универс|легков|автомобил|машин|модел|размер|сторон|детал|издел|проч|различн|раздел|категор)'
        for row in category_rows:
            self.kind_categories.setdefault(norm(row[1]),set()).add(norm(row[0]))
            for w in tokens(row[1],literal=True):
                k=stem(w)
                if len(k)>=3 and not re.fullmatch('[0-9]+',k) and not re.search(weak,k): self.csv_words.add(k)
        for e in self.entries:
            key=kind_key(e['type'])
            if key: self.by_kind.setdefault(key,[]).append(e)

    @staticmethod
    def auto(first):
        n=len(first['literalNeeds'])
        return dict(status='auto',choices=[],basis='category_dictionary',match={
            **{k:first[k] for k in ('cat','type','catId','typeId','score')},'hit':n,'need':n})

    def resolve_category(self,p,d,known=None):
        if d.get('status')!='category_ambiguous': return None
        preferred=PREFERENCE.get(norm(p.get('category')));typ=str(d.get('suggestedType') or '').strip()
        allowed={norm(x) for x in d.get('choices',[])}
        if not preferred or not typ or norm(preferred) not in allowed: return None
        selected=[x for x in (self.entries if known is None else known) if strict_key(x['type'])==strict_key(typ) and norm(x['cat']) in allowed and norm(x['cat'])==norm(preferred)]
        if not selected: return None
        pairs={self.pair_key(x) for x in selected}
        return self.auto(selected[0]) if len(pairs)==1 else None

    @staticmethod
    def pair_key(x):
        return (x['catId'],x['typeId']) if x['catId'] and x['typeId'] else (x['cat'],x['type'])

    def detail_with_category(self,p):
        named=self.detail(p);by_name=self.resolve_category(p,named) or named
        name_result={**by_name,'basis':by_name.get('basis') or 'keyword'}
        def ambiguous(choices,reason):
            return dict(status='ambiguous',choices=choices,basis='category_dictionary',reason=reason)
        if p.get('_categoryKindStatus')=='category_conflict':
            return ambiguous(p.get('_categoryKindChoices') or [],'Название противоречит сохранённой внутренней категории: проверьте товар')
        proposed=(by_name.get('match') or {}).get('type') or by_name.get('suggestedType') or ''
        discriminators=p.get('_categoryKindDiscriminators') or []
        if p.get('_categoryKindStatus')=='ambiguous' and proposed and discriminators:
            proposed_words={csv_stem(w) for w in csv_words(proposed)}
            if any(w not in proposed_words for w in discriminators):
                return ambiguous([proposed],'Название уточняет деталь, а предложенный тип Ozon слишком общий: проверьте вручную')
        info=self.category.type_info(p)
        if info['conflict']:
            return ambiguous([],'Разные виды категории в исходных данных: уточните вид до подбора Ozon')
        hit=self.category.lookup_for(p,info)
        if hit['status']!='match': return name_result
        kind=hit['type']
        if re.search(r'[/,;+&|]|\\s(?:и|или)\\s|прочие|разные|универсальн',kind,re.I): return name_result
        key=kind_key(kind);name_type=proposed
        if len(self.kind_categories.get(norm(kind),set()))>1:
            if name_type and kind_key(name_type)!=key: return name_result
            return ambiguous([name_type] if name_type else [],'Одинаковый вид встречается в разных внутренних категориях; уточните конкретную деталь')
        matches=self.by_kind.get(key,[])
        if not matches:
            if name_type:
                kind_words=tokens(kind,literal=True);kh=head(kind_words)
                required={csv_stem(w) for w in kind_words if stem(w)!=kh}
                cw=tokens(name_type,literal=True);ch=head(cw);cs={csv_stem(w) for w in cw}
                ah=head(tokens(kind,True))
                if not required.issubset(cs) or (ch!=kh and ch!=ah):
                    return ambiguous([name_type],'В доступном справочнике Ozon нет точного соответствия внутреннему виду; проверьте предложенный тип')
            return name_result
        types={}
        for x in matches: types.setdefault(strict_key(x['type']),x['type'])
        if len(types)!=1:
            return ambiguous(list(types.values())[:6],'Виду внутренней категории соответствуют несколько типов Ozon; выберите вручную')
        typ=next(iter(types.values()))
        choices=list(dict.fromkeys(x for x in [name_type,typ]+by_name.get('choices',[]) if x))[:6]
        if by_name['status']=='ambiguous' or (name_type and strict_key(name_type)!=strict_key(typ)):
            return ambiguous(choices,'Название товара и вид из Категории12131.csv допускают разные типы Ozon')
        name=str(p.get('name') or '');brand=str(p.get('brand') or '').strip()
        lead=name_lead(name,brand);ph=head(tokens(lead,True));kh=head(tokens(kind,literal=True))
        if not name.strip() or not ph or re.search(UNSAFE,lead,re.I|re.ASCII) or (ph!=kh and not(name_type and strict_key(name_type)==strict_key(typ))):
            return ambiguous([typ],'Вид из Категории12131.csv предлагает тип, но название товара не подтверждает его')
        kw={stem(w) for w in tokens(kind,literal=True)};tw={stem(w) for w in tokens(name,True)}
        fully=len(kw)>1 and kw.issubset(tw)
        if not fully and any(w in self.csv_words and w not in kw and w!=ph for w in tw):
            return ambiguous([typ],'В названии есть признаки другого вида детали: проверьте внутренний вид и тип Ozon')
        if len({self.pair_key(x) for x in matches})>1:
            d=dict(status='category_ambiguous',choices=list(dict.fromkeys(x['cat'] for x in matches))[:6],suggestedType=typ,basis='category_dictionary')
            return self.resolve_category(p,d,matches) or d
        return self.auto(matches[0])
""",
    # ===== ozon_classifier =====
    'ozon_classifier': """\"\"\"Strict Ozon OE/applicability classification using a canonical historical pair list.\"\"\"
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
def hvc_key(v): return re.sub(r'\\s+',' ',re.sub(r'[^0-9a-zа-яё`\\-\\s]','',string(v).replace("'",'').lower())).strip()
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
        for raw in re.split(r'[/;,\\r\\n|]+',string(v)):
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
            pair=self.pair(rec);mapping=pair['category']+'\\x1f'+pair['type'] if pair else ''
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
        return '\\x1e'.join(out)

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
""",
    # ===== ozon_identity =====
    'ozon_identity': """\"\"\"HVC identity guards from raw catalogue, parts and byArt snapshots.\"\"\"
import re
from category_tnved import text


def key(v): return re.sub('[^A-Z0-9А-ЯЁ]','',text(v).upper())
def pair(p): return key(p.get('article'))+'|'+key(p.get('brand'))


def codes(value,mode='auto'):
    values=value if isinstance(value,list) else [value]
    seen=set()
    pattern={'newline':r'\\r?\\n','comma':',','semicolon':';','slash':'/','pipe':r'\\|'}.get(mode,r'[/;,\\n\\r|]+')
    for value in values:
        raw_value=','.join(text(x) for x in value) if isinstance(value,list) else text(value)
        for raw in re.split(pattern,raw_value):
            raw=raw.strip();compact=re.sub(r'[\\s\\u00a0]','',raw)
            compact=re.sub(r'^р\\.?','',compact,flags=re.I)
            if re.fullmatch(r'[0-9]+[.,]0+',compact): raw=re.sub(r'[.,]0+$','',compact)
            normalized=key(raw)
            if normalized and normalized not in seen:
                seen.add(normalized);yield normalized


class IdentityGuard:
    def __init__(self,rows,reference):
        self.parts=dict(reference.get('parts') or [])
        self.unsafe=set();self.mode=reference.get('oe_mode','auto')
        for p in rows:
            if self.mismatch(p): self.unsafe.add(pair(p))
        by_art=dict(reference.get('byArt') or [])
        self.unsafe_oes={key(oe) for k in self.unsafe for oe in by_art.get(k,[])}

    def mismatch(self,p):
        part=self.parts.get(pair(p)) or {}
        return bool((part.get('artikul') and key(part['artikul'])!=key(p.get('article'))) or
                    (part.get('brand') and key(part['brand'])!=key(p.get('brand'))))

    def unsafe_for(self,p):
        return pair(p) in self.unsafe or self.mismatch(p) or any(
            oe in self.unsafe_oes for field in ('oe_numbers','oe_list','oe_norm') for oe in codes(p.get(field),self.mode))
""",
    # ===== ozon_name =====
    'ozon_name': """\"\"\"Independent OzonAuto lexical name classifier over canonical type entries.\"\"\"
import json
import pathlib
import re
from csv_kind_matcher import rewrite, name_lead, UNSAFE
from ozon_reference import strict_key

STOP=set('для или под над без при как the and на по of из в с a авто'.split())
ALIASES=dict(zip('filter oil air cabin fuel water brake pads pad disc pump headlight'.split(),
                 'фильтр масляный воздушный салонный топливный водяной тормозной колодки колодки диск насос фара'.split()))
EXPANSIONS=json.loads(pathlib.Path(__file__).with_name('ozon_name_expansions.json').read_text(encoding='utf8'))
MOTO=r'(?:мотоцикл|скутер|мопед|снегоход|квадроцикл|(?:^|\\s)мото(?=\\s|$))'
ADJ=r'(?:ый|ий|ой|ая|яя|ое|ее|ые|ие|ых|их|ого|его|ому|ему|ыми|ими|ую|юю)$'
BLOCKS={
 'ключ автомобильный':r'гаечн|рожков|накидн|торцев|динамометр|фильтр|съ[её]мн|шестигран|свечн|колесн|болт|гайк|трещотк',
 'насос автомобильный':r'омывател|топлив|масл|охлаж|водян|гидро|тормоз|откач|перекач|ручн|abs|абс|гур',
 'держатель автомобильный':r'тормоз|шланг|труб|выхлоп|глушител|топлив|амортизатор|двигател|подвеск|насос|радиатор|трансмисс|стартер|суппорт|шрус',
 'подушка автомобильная':r'амортизатор|радиатор|двигател|мотора|двс|подвеск|подрамник|рессор|редуктор|кпп|коробк[аиуы]?\\s+передач|глушител|рулев|руля|безопасност|airbag|эйрб[еэ]г|аэрб[еэ]г'}


def expand(value):
    text=str(value or '')
    if re.search('водян[а-я]*',text,re.I):
        text=re.sub(r'(^|[^a-zа-я0-9])помп[а-я]*(?=$|[^a-zа-я0-9])',r'\\1насос',text,flags=re.I)
    if re.search(r'сальник[а-я]*\\s+(?:коленвал|распредвал)',text,re.I): text+=' двигателя'
    if re.search(MOTO,text,re.I): text+=' мототехника'
    for pattern,target in EXPANSIONS:
        text=re.sub(pattern,target.replace('$1',r'\\g<1>'),text,flags=re.I)
    return text


def tokens(value,product=False,literal=False):
    text=str(value or '') if literal else expand(rewrite(value) if product else value)
    text=text.lower().replace('ё','е')
    text=re.sub(r'ремонтн[а-я]*\\s+комплект[а-я]*','ремкомплект',text)
    ws=re.sub('[^a-zа-я0-9]+',' ',text).split()
    if not literal: ws=[ALIASES.get(w,w) for w in ws]
    return [w for w in ws if len(w)>=2 and w not in STOP and not re.match('^(автомобил|легков|машин)',w)]


def stem(w):
    x=w
    if re.fullmatch('[а-я]+',x):
        x=re.sub(r'(?:иями|ями|ами|ого|его|ому|ему|ыми|ими|иях|иях|ий|ый|ой|ая|яя|ое|ее|ые|ие|ых|их|ую|юю|ов|ев|ей|ам|ям|ах|ях)$','',x)
        if len(x)>=4: x=re.sub('[аеёиоуыэюяь]$','',x)
    if x=='колодок': x='колодк'
    return x[:8]


def head(words):
    for w in words:
        if (not re.search('(?:ение|ание|тие|ствие)$',w) and re.search(ADJ,w)) or re.match('^(комплект|набор|оригинал)',w): continue
        return stem(w)
    return ''


def needs(words): return list(dict.fromkeys(stem(w) for w in words if len(stem(w))>=2))


class OzonNameClassifier:
    def __init__(self,types):
        self.entries=[]
        self.by_word={}
        self.heads=set()
        for t in types:
            typ=str(t.get('name') or t.get('type') or ''); cat=str(t.get('cat') or t.get('category') or '')
            ws=tokens(typ); ns=needs(ws)
            if not cat or not typ or not ns: continue
            literal=tokens(typ,literal=True); ln=needs(literal)
            e=dict(cat=cat,type=typ,head=head(ws) or ns[0],needs=ns,literalHead=head(literal) or (ln[0] if ln else ''),
                   literalNeeds=ln,path=t.get('path') or [],catId=t.get('catId') or '',typeId=t.get('typeId') or '',
                   score=len(ns)*1000+sum(min(len(x),8) for x in ns),typeKey=strict_key(typ))
            idx=len(self.entries);self.entries.append(e);self.heads.add(e['head'])
            for n in ns: self.by_word.setdefault(n,[]).append(idx)

    def detail(self,p):
        name=str(p.get('name') or '');brand=str(p.get('brand') or '').strip()
        raw=set(needs(tokens(name)));keys=set(needs(tokens(name,True)));literal=set(needs(tokens(name,literal=True)))
        if not keys and not raw: return dict(status='empty',choices=[])
        lead=name_lead(name,brand)
        if re.search(UNSAFE,lead,re.I|re.ASCII): return dict(status='none',choices=[])
        h=head(tokens(lead,True));rh=head(tokens(lead));lh=head(tokens(lead,literal=True))
        if h not in self.heads and rh not in self.heads: return dict(status='none',choices=[])
        candidates=list(dict.fromkeys(i for k in dict.fromkeys(needs(tokens(name,True))+needs(tokens(name))) for i in self.by_word.get(k,[])))
        matches=[];raw_matches=set();alias_matches=set()
        for i in candidates:
            t=self.entries[i]
            if t['typeKey'] in BLOCKS and re.search(BLOCKS[t['typeKey']],name,re.I): continue
            if re.search(MOTO,name,re.I) and not re.search('мото|снегоход|квадроцикл',' '.join([t['cat'],t['type']]+t['path']),re.I): continue
            r=all(n in raw for n in t['needs']);a=all(n in keys for n in t['needs'])
            if r or a:
                matches.append(i)
                if r: raw_matches.add(i)
                if a: alias_matches.add(i)
        multiple=re.search(r'\\sи\\s|\\sand\\s|\\s\\+\\s|\\s&\\s|[а-яё]\\s*[,;/+&]\\s*(?=[а-яё])|\\s+[–—]\\s+',name,re.I) or re.search(r'^\\s*(?:комплект|набор)(?=\\s|$)',name.replace('ё','е'),re.I)
        if multiple:
            joined=re.search(r'^\\s*(?:комплект|набор)(?=\\s|$)',name,re.I) and re.search(r'\\sи\\s|\\s\\+\\s|\\s&\\s',name,re.I)
            if len({self.entries[i]['head'] for i in matches})>1 or len({self.entries[i]['typeKey'] for i in matches})>1 or joined:
                return dict(status='ambiguous',choices=list(dict.fromkeys(self.entries[i]['type'] for i in matches))[:6])
        matches=[self.entries[i] for i in matches if (self.entries[i]['head']==rh and i in raw_matches) or (self.entries[i]['head']==h and i in alias_matches)]
        if not matches: return dict(status='none',choices=[])
        specificity=max(len(t['needs']) for t in matches)
        finalists=[t for t in matches if len(t['needs'])==specificity]
        surface=[t for t in finalists if t['literalHead']==lh and t['literalNeeds'] and all(n in literal for n in t['literalNeeds'])]
        raw_final=[t for t in finalists if t['head']==rh and all(n in raw for n in t['needs'])]
        finalists=surface or raw_final or finalists
        score=max(t['score'] for t in finalists);top=[t for t in finalists if t['score']==score]
        types=list(dict.fromkeys(t['type'] for t in top))
        if len(types)>1: return dict(status='ambiguous',choices=types[:6])
        first=top[0]
        pairs={(str(t['catId'] or t['cat']),str(t['typeId'] or t['type'])) for t in top}
        if len(pairs)>1: return dict(status='category_ambiguous',choices=list(dict.fromkeys(t['cat'] for t in top))[:6],suggestedType=first['type'])
        return dict(status='auto',choices=[],match={**{k:first[k] for k in ('cat','type','catId','typeId','score')},'hit':len(first['needs']),'need':len(first['needs'])})
""",
    # ===== ozon_preferred =====
    'ozon_preferred': """\"\"\"Compose independent Ozon strict, lexical, category and lifecycle ports.\"\"\"
import json
from category_tnved import norm
from category_kind import shape
from ozon_classifier import OzonClassifier
from ozon_category import OzonCategoryClassifier
from ozon_auto import apply_preferred


def compact(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'))


class OzonPreferred:
    def __init__(self,reference):
        self.reference=reference
        self.strict=OzonClassifier(reference['pairs'],reference.get('tree'),reference.get('scope','auto'))
        tree=self.strict.reference
        types=tree.entries if tree.has_data else [dict(cat=c,name=t) for c,t in reference['pairs']]
        self.strict.historical_version='historical:'+str(len(types))
        self.names=OzonCategoryClassifier(types,reference['category_rows'],reference['category_revision'])
        self.version='keyword-v6-csv-name|'+('tree:'+str(tree.snapshot.get('revision','undefined'))+':'+tree.scope if tree.has_data else 'historical:'+str(len(types)))

    def category_signature(self,p):
        tn=self.names.category
        info=tn.type_info(p);m=p.get('_categoryKindAuto');current=tn.kind_current(p)
        draft=shape(m) and str(p.get('category_type') or '')==m['type'] and not m['confirmed']
        flag=''
        if p.get('_categoryKindStatus')=='category_conflict': flag='category_conflict'
        elif p.get('_categoryKindStatus')=='ambiguous' and p.get('_categoryKindDiscriminators'):
            flag='|'.join(p['_categoryKindDiscriminators'])
        kind=compact([flag,m['referenceCategory'] if current else '', 'stale' if draft and not current else ''])
        return compact([tn.revision,norm(p.get('category')),norm(info['value']),bool(info['conflict']),bool(p.get('_categoryTypeCleared')),kind])

    def apply(self,p,*,force=False,force_name=False,enabled=True,identity_unsafe=False):
        return apply_preferred(self.strict,p,detail=self.names.detail_with_category,
            version=self.version,category_signature=self.category_signature(p),
            registry=self.reference.get('registry'),applicability=self.reference.get('applicability'),
            force=force,enabled=enabled,force_name=force_name,identity_unsafe=identity_unsafe,
            reference_version=self.reference.get('reference_version',0))
""",
    # ===== ozon_reference =====
    'ozon_reference': """\"\"\"OzonReference lookup over an already parsed raw tree snapshot.\"\"\"
import re
import unicodedata
from category_tnved import text


def strict_key(v): return re.sub(r'\\s+',' ',unicodedata.normalize('NFC',text(v)).lower()).strip()
def loose_key(v):
    s=unicodedata.normalize('NFKC',strict_key(v)).replace('ё','е')
    return re.sub(r'\\s+',' ',''.join(c if unicodedata.category(c)[0] in ('L','N') else ' ' for c in s)).strip()
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
""",
    # ===== price_solver =====
    'price_solver': """\"\"\"Port of index.html solveEcoInteger; keep behavior aligned, including scans.\"\"\"
import math

CAP = 10_000_000

def js_round(x):
    return math.floor(x + 0.5)


def solve_integer(initial, metric):
    cache = {}
    def evaluate(price):
        key = max(0, js_round(price))
        if key not in cache:
            value = metric(key)
            cache[key] = value if math.isfinite(value) else -math.inf
        return cache[key]
    start = max(0, min(CAP, js_round(initial)))
    def local_root(x):
        fx = evaluate(x)
        if fx >= 0 and (x == 0 or evaluate(x - 1) < 0): return x
        if fx < 0 and x < CAP and evaluate(x + 1) >= 0: return x + 1
        return None
    def first_crossing(lo, hi):
        if evaluate(lo) >= 0: return lo
        if evaluate(hi) < 0: return None
        width = hi - lo
        step = 25000 if width > 1000000 else 2500 if width > 100000 else 250 if width > 10000 else 25 if width > 1000 else 1
        prev = lo
        p = lo + step
        while True:
            pp = min(p, hi)
            if evaluate(pp) >= 0:
                return pp if pp - prev <= 1 else first_crossing(prev, pp)
            prev = pp
            if pp >= hi: return None
            p += step
    def scan_band(lo, hi):
        if evaluate(lo) >= 0: return lo
        width = hi - lo
        if width <= 0: return None
        step = 25000 if width > 1000000 else 2500 if width > 100000 else 250 if width > 10000 else 25 if width > 1000 else 4 if width > 256 else 1
        prev = lo
        p = lo + step
        while True:
            pp = min(p, hi)
            if evaluate(pp) >= 0: return first_crossing(prev, pp)
            prev = pp
            if pp >= hi: return None
            p += step
    root = local_root(start)
    if root is not None: return root
    if evaluate(start) < 0:
        prev = 0
        for gp in (0, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, CAP):
            if gp == start:
                prev = gp
                continue
            root = scan_band(prev, gp)
            if root is not None: return root
            prev = gp
    f_start = evaluate(start)
    second = min(CAP, max(start + 32, js_round(start * 1.2 + 1))) if f_start < 0 else max(0, js_round(start * 0.8))
    if second != start:
        slope = (evaluate(second) - f_start) / (second - start)
        if slope > 0 and math.isfinite(slope):
            candidate = max(0, min(CAP, js_round(start - f_start / slope)))
            if candidate != start and candidate != second:
                root = local_root(candidate)
                if root is not None: return root
    step = max(16, js_round(abs(start) * 0.25))
    if evaluate(start) >= 0:
        if start == 0 or evaluate(start - 1) < 0: return start
        hi, lo = start, max(0, start - step)
        while evaluate(lo) >= 0:
            hi = lo
            if lo == 0: return 0
            step *= 2
            lo = max(0, lo - step)
    else:
        lo, hi = start, min(CAP, start + step)
        guard = 0
        while evaluate(hi) < 0 and hi < CAP and guard < 40:
            guard += 1
            lo = hi
            step *= 2
            hi = min(CAP, lo + step)
        if evaluate(hi) < 0:
            for lo, hi in ((0, 10000), (10000, 100000), (100000, 1000000), (1000000, CAP)):
                root = scan_band(lo, hi)
                if root is not None: return root
            return CAP
    root = first_crossing(lo, hi)
    return hi if root is None else root


def stable_floor(guess, metric, discontinuity=0):
    edge = math.floor(discontinuity)
    if edge <= 0: return solve_integer(guess, metric)
    if metric(edge + 1) < 0: return solve_integer(edge + 1, metric)
    if metric(edge) < 0: return edge + 1
    if metric(0) >= 0: return 0
    lo, hi = 0, edge
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if metric(mid) >= 0: hi = mid
        else: lo = mid
    return hi
""",
    # ===== product_policies =====
    'product_policies': """\"\"\"Ordered product-policy actions, matching the browser pipeline.\"\"\"
import copy
from enrichment_formula import string as text

RULE_FIELDS = {'category': 'Категория', 'brand': 'Бренд', 'name': 'Название', 'article': 'Артикул', 'oe_numbers': 'OE-номера', 'price': 'Цена', 'cost': 'Себестоимость', 'weight': 'Вес', 'volume': 'Объём', 'stock': 'Остаток', 'minStock': 'Мин. остаток', 'sales': 'Продажи', 'noBuyPct': 'Прогноз невыкупа, %', 'markRequired': 'Требуется Честный знак', 'markStatus': 'Статус Честного знака', 'markCode': 'Код маркировки', 'visible': 'Видимость', 'src': 'Общий текст', 'category_src': 'Исходная категория'}
RULE_OPS = {'contains': 'содержит', '!contains': 'не содержит', 'eq': 'равно', 'ne': 'не равно', 'gt': 'больше', 'lt': 'меньше', 'startsWith': 'начинается с', 'regex': 'регулярное выражение', 'empty': 'пусто'}
POLICY_ACTIONS = {'exclude': 'Исключить из расчётов', 'hide': 'Скрыть с витрины', 'delete_mark': 'Пометить на удаление', 'warn': 'Только предупредить'}


def apply_policies(row,rules,match,number):
    p=copy.deepcopy(row)
    p.update(excluded=False,deletePending=False,policyAction='',policyReason='')
    active=sorted((r for r in rules if r.get('enabled')),key=lambda r:number(r.get('order_no')))
    for r in active:
        field=r.get('field');op=r.get('op');value=r.get('value')
        if not match(p,field,op,value): continue
        action=r.get('action') or 'exclude'
        p['policyAction']=POLICY_ACTIONS.get(action) or action
        p['policyReason']=f"{RULE_FIELDS.get(field) or field} {RULE_OPS.get(op) or op} {text(value) if 'value' in r else 'undefined'}"
        if action=='exclude': p['excluded']=True
        if action=='hide': p.update(visible=False,visibleReason='товарная_политика')
        if action=='delete_mark': p.update(deletePending=True,visible=False,visibleReason='ожидает_удаления')
    return p
""",
}

class _BundledModules(_bundle_abc.MetaPathFinder, _bundle_abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in _BUNDLED_SOURCES:
            return _bundle_util.spec_from_loader(fullname, self, origin=__file__)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        # Reference JSON files remain beside uc_engine.py, also in frozen builds.
        module.__file__ = __file__
        exec(compile(self.get_source(module.__name__),
                     str(__file__) + ':' + module.__name__, 'exec'), module.__dict__)

    def get_source(self, fullname):
        return _BUNDLED_SOURCES[fullname]

_bundle_sys.meta_path.insert(0, _BundledModules())
# ===== Main engine =====

import argparse, csv, email, imaplib, io, json, math, os, re, shutil, sqlite3, sys, time, zipfile
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps
from price_solver import stable_floor, js_round
from hvc_enrichment import enrich_rows as hvc_enrich_rows
from name_category import apply as apply_name_category, MARKERS as NAME_CATEGORY_MARKERS
from category_tnved import CategoryTnved
from category_kind import CategoryKind
from ozon_classifier import OzonClassifier
from enrichment_rules import apply_rules as apply_enrichment_rules
from enrichment_transport import encode_special, decode_special, equivalent
from export_custom import custom_cell, export_number
from export_formulas import prepare_options as prepare_formula_options, cached_formula, unavailable as formula_unavailable
from js_regex import search as js_regex_search
from enrichment_formula import string as formula_string, truth as formula_truth, JS_SPACE
from mark_status import apply as apply_mark_status
from email.header import decode_header
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import URLError

BASE = Path(__file__).resolve().parent
FROZEN = getattr(sys, 'frozen', False)
# v12.9.124: один файл. В frozen-сборке (PyInstaller --onefile) ресурсы лежат
# во временной распаковке _MEIPASS, а данные обязаны жить РЯДОМ с exe —
# иначе каталог и токен терялись бы при каждом закрытии.
BUNDLE = Path(getattr(sys, '_MEIPASS', BASE)) if FROZEN else BASE
DATA = (Path(sys.executable).resolve().parent / 'engine_data') if FROZEN else BASE / 'engine_data'
DATA.mkdir(exist_ok=True)
DB_PATH = DATA / 'catalog.db'
TOKEN_PATH = DATA / 'token.txt'
SECRETS_PATH = DATA / 'secrets.json'
VERSION = '12.9.156-pyengine-40'

class DiskFullError(Exception):
    """v12.9.144: на диске с базой не хватает места для безопасного импорта."""

MIN_FREE_FOR_IMPORT = 250 * 1024 * 1024

def ensure_free_space(need_bytes=0):
    """Предпроверка места ПЕРЕД записью в SQLite: лучше честный отказ до
       импорта, чем 'database or disk is full' в середине и полупустая база.
       Нужно: минимум 250 МБ и не меньше 4 размеров файла (строки в SQLite
       шире исходного CSV: индексы, FTS, история цен, WAL)."""
    import shutil as _sh
    try: free = _sh.disk_usage(str(DATA)).free
    except Exception: return
    need = max(MIN_FREE_FOR_IMPORT, int(need_bytes or 0) * 4)
    if free < need: raise DiskFullError(f'free={free} need={need}')

# ---------------- деньги и округление (Excel-стиль, как в приложении) ----------------
def rnd(x, d=2):
    q = Decimal(1).scaleb(-d)
    return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))

def num(v):
    if v is None: return 0.0
    if isinstance(v, (int, float)): return float(v)
    s = str(v).replace(' ', '').replace(' ', '').replace('%', '')
    if ',' in s and '.' in s:
        s = s.replace('.', '', 1).replace(',', '.') if s.rfind(',') > s.rfind('.') else s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '.') if s.count(',') == 1 else s.replace(',', '')
    elif s.count('.') > 1:
        s = s.replace('.', '')  # 12.345.678 — тысячные, как num() браузера
    try: return float(s)
    except ValueError: return 0.0

def vat_from_gross(amount, rate):
    return amount * rate / (100 + rate) if rate > 0 else 0.0

def calc_tax(price, costs, regime='usn_income_6', pct=6.0, osno_share=0.0):
    """Все налоговые режимы приложения, копейка в копейку (проверено тестами)."""
    p, c = max(0.0, num(price)), max(0.0, num(costs))
    if regime == 'usn_income_6': return rnd(p * 0.06)
    if regime in ('usn_income_vat_5', 'usn_income_7', 'usn_income_vat_7'):
        rate = 5 if regime.endswith('_5') else 7
        vat = vat_from_gross(p, rate)
        return rnd(vat + (p - vat) * 0.06)
    if regime == 'usn_income_expense_15': return rnd(max(0.0, p - c) * 0.15)
    if regime in ('usn_income_expense_vat_5', 'usn_income_expense_vat_7'):
        rate = 5 if regime.endswith('_5') else 7
        vat = vat_from_gross(p, rate)
        return rnd(vat + max(0.0, p - vat - c) * 0.15)
    if regime in ('osno_20', 'osno_22'):
        vat_out = vat_from_gross(p, 22)
        vat_in = vat_from_gross(c, 22) * min(100.0, max(0.0, osno_share)) / 100
        return rnd(max(0.0, vat_out - vat_in) + max(0.0, (p - vat_out) - (c - vat_in)) * 0.25)
    if regime == 'self_employed_4': return rnd(p * 0.04)
    if regime == 'self_employed_6': return rnd(p * 0.06)
    if regime == 'custom_profit': return rnd(max(0.0, p - c) * min(100.0, max(0.0, pct)) / 100)
    return rnd(p * min(100.0, max(0.0, pct if pct is not None else 6.0)) / 100)

def wb_base_logistics(v):
    v = max(0.0, num(v))
    if v <= 0: return 0.0
    if v <= 0.2: return 23.0
    if v <= 0.4: return 26.0
    if v <= 0.6: return 29.0
    if v <= 0.8: return 30.0
    if v <= 1: return 32.0
    return rnd(46 + (v - 1) * 14)

def wb_storage_month(volume, first_liter_day=0.15, coeff=1.0, days=30):
    """Ступенчатое хранение WB FBO: первый литр по ставке, далее 7/15."""
    v = max(0.0, num(volume))
    if v <= 0: return 0.0
    per_day = first_liter_day * min(v, 1) + first_liter_day * (7 / 15) * max(0.0, v - 1)
    return rnd(per_day * coeff * days)

# ---------------- экономика Ozon (паритет с приложением; эталон — золотые CSV) ----------------
def ozon_unit(price, cost, st):
    if isinstance(st.get('ozon'), dict):
        return _ozon_browser_unit(price, cost, st)
    comm = rnd(price * num(st.get('commission_pct', 14)) / 100)
    transfer = rnd(price * num(st.get('transfer_pct', 1.5)) / 100)
    failed_case = num(st.get('failed_case', 0))
    rate = min(100.0, max(0.0, num(st.get('no_buy_pct', 0))))
    returns = rnd(failed_case * rate / (100 - rate), 6) if rate < 100 else 0.0
    if num(st.get('returns_per_unit', 0)):
        returns = num(st.get('returns_per_unit'))
    vol = num(st.get('_volume', 0))
    storage = wb_storage_month(vol, num(st.get('storage_first_liter_day', 0.15)),
                               num(st.get('storage_coeff', 1)), num(st.get('storage_days', 30))) \
        if st.get('fulfillment') == 'FBO' else 0.0
    fixed_parts = [cost, num(st.get('last_mile', 25)), num(st.get('handover', 10)),
                   num(st.get('pack', 18)), num(st.get('transit', 30)), returns, storage,
                   num(st.get('processing', 0)), num(st.get('fixed_per_unit', 0))]
    tax = calc_tax(price, sum(fixed_parts) + comm + transfer,
                   st.get('tax_regime', 'usn_income_6'), num(st.get('tax_pct', 6)),
                   num(st.get('tax_osno_share', 0)))
    total = rnd(sum(fixed_parts) + comm + transfer + tax)
    return {'total': total, 'commission': comm, 'transfer': transfer, 'tax': tax,
            'returns': rnd(returns), 'storage': storage}

def _ozon_browser_unit(price, cost, st):
    """v12.9.146: Ozon — той же формулой, что evaluateOzon в браузере
       (calcMarketplacesEconomics): скидка за быструю отгрузку, ручной маршрут
       + обработка, сдача по режиму, хранение FBO за литр, невыкуп от полного
       расхода случая, нестандарт 3% с капом, поздняя отгрузка, хранение возврата.
       Настройки приходят в st['ozon'] из _settingsSnapshot приложения."""
    oz = st['ozon']
    scheme = str(oz.get('fulfillment') or 'FBS').upper()
    vol = num(st.get('_volume', 0))
    liters = max(0.01, vol) if vol > 0 else 0.0
    comm_base = num(st.get('commission_pct', 14))
    ship_disc = num(oz.get('ship_discount_pp')) if scheme == 'FBS' else 0.0
    comm = rnd(price * max(0.0, comm_base - ship_disc) / 100)
    transfer = rnd(price * num(st.get('transfer_pct', 1.5)) / 100)
    ads = rnd(price * num(oz.get('boost_pct')) / 100)
    cofin = rnd(price * num(oz.get('cofin_pct')) / 100)
    manual_log = rnd(num(st.get('_row_logistics', oz.get('logistics_manual'))) * num(oz.get('logistics_factor', 1)))
    processing = 0.0 if scheme == 'REALFBS' else num(oz.get('fbo_processing') if scheme == 'FBO' else oz.get('processing'))
    realfbs_del = rnd(num(st.get('_row_realfbs', 0)) * num(oz.get('logistics_factor', 1)))
    logistics = realfbs_del if scheme == 'REALFBS' else rnd(manual_log + processing)
    last_mile = 0.0 if scheme == 'REALFBS' else num(oz.get('last_mile', st.get('last_mile', 25)))
    units = max(1.0, num(oz.get('units_per_shipment')) or 1)
    handover = 0.0
    if scheme == 'FBS':
        mode = str(oz.get('handover_mode') or 'sc')
        if mode == 'sc_self': handover = 0.0
        elif mode == 'pvz_pct': handover = rnd(min(price * units * num(oz.get('pvz_pct')) / 100, num(oz.get('pvz_cap'))) / units)
        elif mode == 'courier': handover = rnd((num(oz.get('courier_trip')) / max(1.0, num(oz.get('courier_orders')) or 1) + num(oz.get('courier_order'))) / units + num(oz.get('courier_liter')) * liters)
        else: handover = rnd(num(oz.get('handover_fee', 10)) / units)
    storage = rnd(liters * num(oz.get('storage_per_l')) * num(oz.get('storage_days', 30))) if scheme == 'FBO' else 0.0
    rate = min(100.0, max(0.0, num(st.get('no_buy_pct', 0))))
    failed_override = num(st.get('failed_case')) > 0 or num(oz.get('failed_manual')) > 0
    realfbs_service = (num(oz.get('realfbs_service', 20)) / max(1.0, num(oz.get('realfbs_units')) or 1)) if scheme == 'REALFBS' else 0.0
    failed_case = num(st.get('failed_case')) or num(oz.get('failed_manual')) if failed_override else (
        realfbs_del + num(oz.get('realfbs_return')) + realfbs_service if scheme == 'REALFBS'
        else 2 * manual_log + last_mile + num(oz.get('return_handling')))
    returns = rnd(failed_case * rate / (100 - rate), 6) if rate < 100 else 0.0
    return_storage = 0.0 if failed_override else (
        rnd(num(oz.get('return_storage')) * rate / (100 - rate), 6) if scheme == 'FBS' and rate < 100 else 0.0)
    nonstd = 0.0
    if oz.get('nonstd_enabled', True) and scheme != 'REALFBS' and num(st.get('_weight', 0)) > 25:
        nonstd = rnd(min(price * num(oz.get('nonstd_pct', 3)) / 100, num(oz.get('nonstd_cap', 280))))
    late = rnd(price * num(oz.get('late_ship_pct')) / 100) if scheme == 'FBS' else 0.0
    pack = num(st.get('pack', 18))
    transit = num(st.get('transit', 30)) if scheme == 'FBS' else 0.0
    fixed = num(st.get('fixed_per_unit', 0))
    parts = [cost, comm, transfer, logistics, last_mile, handover, pack, transit,
             returns, return_storage, storage, ads, cofin, nonstd, late, fixed, realfbs_service]
    tax = calc_tax(price, sum(parts), st.get('tax_regime', 'usn_income_6'),
                   num(st.get('tax_pct', 6)), num(st.get('tax_osno_share', 0)))
    total = rnd(sum(parts) + tax)
    return {'total': total, 'commission': comm, 'transfer': transfer, 'tax': tax,
            'returns': rnd(returns + return_storage), 'storage': storage, '_expense_names': ['commission', 'paymentTransfer', 'lastMile', 'boost', 'cofin', 'logistics', 'scDelivery', 'packaging', 'processing', 'storage', 'returns', 'returnStorage', 'tax', 'nonStd', 'lateShip'], '_monthly_parts': [comm, transfer, last_mile, ads, cofin, logistics, handover, pack, transit + realfbs_service, storage, returns, return_storage, tax, nonstd, late], '_percent': comm + transfer + ads + cofin}

def wb_unit(price, cost, st):
    """v12.9.149: WB — формулой evaluateWb браузера: база логистики по объёму,
       складской коэффициент (СГТ без него, база 1000–3000), хранение FBO
       ступенчатое, доставка в СЦ по платному весу, невыкуп от полного расхода
       случая (ПВЗ-период — по объёму), комиссия/эквайринг/реклама/софин."""
    wb = st.get('wb') or {}
    scheme = str(wb.get('fulfillment') or 'FBS').upper()
    v = num(st.get('_volume', 0))
    dims = st.get('_dims') or (0, 0, 0)
    base = wb_base_logistics(v)
    sgt = num(st.get('_weight', 0)) > 25 or max(dims) > 200 or sum(dims) > 280
    coeff = 1.0 if sgt else num(wb.get('warehouse_coeff', 1.7))
    direct_base = min(3000.0, max(1000.0, base)) if sgt else base
    logistics = rnd(rnd(direct_base * coeff * num(wb.get('logistics_factor', 1))) + (num(wb.get('acceptance')) if scheme == 'FBO' else 0.0))
    storage = wb_storage_month(v, num(wb.get('storage_per_l', 0.15)), num(wb.get('storage_coeff', 1)), num(wb.get('storage_days', 30))) if scheme == 'FBO' else 0.0
    div = num(wb.get('vol_divisor')) or 5000
    _vol_kg = (dims[0] * dims[1] * dims[2] / div) if all(d > 0 for d in dims) else (v * 1000 / div if v > 0 else 0.0)
    billable = max(num(st.get('_weight', 0)), _vol_kg)
    sc_delivery = rnd(num(wb.get('sc_per_kg', 12)) * billable) if scheme == 'FBS' else 0.0
    rate = min(100.0, max(0.0, num(st.get('no_buy_pct', 0))))
    failed_manual = wb.get('failed_manual')
    if failed_manual is not None and str(failed_manual).strip() != '' and num(failed_manual) >= 0: failed_case = num(failed_manual)
    elif scheme == 'FBS':
        import datetime as _dt
        today = _dt.date.today()
        in_pvz = _dt.date(2026, 8, 7) <= today <= _dt.date(2027, 1, 31)
        failed_case = (rnd(25 if v <= 1 else 25 + (v - 1) * 4) if v > 0 else 0.0) if in_pvz else 0.0
    else:
        extra = num(wb.get('return_extra'))
        failed_case = rnd(base * coeff + extra) if extra > 0 else base
    returns = rnd(failed_case * rate / (100 - rate), 6) if rate < 100 else 0.0
    comm = rnd(price * num(wb.get('commission_pct', 15)) / 100)
    transfer = rnd(price * num(wb.get('acquiring_pct', 1.5)) / 100)
    ads = rnd(price * num(wb.get('boost_pct')) / 100)
    cofin = rnd(price * num(wb.get('cofin_pct')) / 100)
    pack = num(st.get('pack', 18)); transit = num(st.get('transit', 30)) if scheme == 'FBS' else 0.0
    fixed = num(st.get('fixed_per_unit', 0))
    parts = [cost, comm, transfer, logistics, sc_delivery, pack, transit, returns, storage, ads, cofin, fixed]
    tax = calc_tax(price, sum(parts), st.get('tax_regime', 'usn_income_6'), num(st.get('tax_pct', 6)), num(st.get('tax_osno_share', 0)))
    return {'total': rnd(sum(parts) + tax), 'commission': comm, 'transfer': transfer, 'tax': tax,
            'returns': rnd(returns), 'storage': storage, '_expense_names': ['commission', 'paymentTransfer', 'boost', 'cofin', 'logistics', 'scDelivery', 'packaging', 'processing', 'storage', 'returns', 'tax'], '_monthly_parts': [comm, transfer, ads, cofin, logistics, sc_delivery, pack, transit, storage, returns, tax], '_percent': comm + transfer + ads + cofin}

def _billable(st):
    dims = st.get('_dims') or (0, 0, 0); v = num(st.get('_volume', 0))
    div = num((st.get('wb') or {}).get('vol_divisor')) or num((st.get('ym') or {}).get('vol_divisor')) or 5000
    vol_kg = (dims[0] * dims[1] * dims[2] / div) if all(d > 0 for d in dims) else (v * 1000 / div if v > 0 else 0.0)
    return max(num(st.get('_weight', 0)), vol_kg), vol_kg

def mm_unit(price, cost, st):
    """Мегамаркет (evaluateMm): комиссия, эквайринг, лояльность, реклама;
       FBS — ручная логистика и СЦ, FBO — логистика в комиссии, хранение за единицу."""
    mm = st.get('mm') or {}
    scheme = str(mm.get('fulfillment') or 'FBS').upper()
    comm = rnd(price * num(mm.get('commission_pct', 12)) / 100)
    transfer = rnd(price * num(mm.get('acquiring_pct', 1.5)) / 100)
    cofin = rnd(price * num(mm.get('loyalty_pct')) / 100)
    ads = rnd(price * num(mm.get('boost_pct')) / 100)
    logistics = rnd(num(mm.get('fbs_logistics')) * num(mm.get('logistics_factor', 1))) if scheme == 'FBS' else 0.0
    billable, _vk = _billable(st)
    sc = rnd(num(mm.get('sc_per_kg', 12)) * billable) if scheme == 'FBS' else 0.0
    storage = num(mm.get('storage_per_unit')) if scheme == 'FBO' else 0.0
    rate = min(100.0, max(0.0, num(st.get('no_buy_pct', 0))))
    failed = num(mm.get('failed_manual')) if num(mm.get('failed_manual', -1)) >= 0 else num(mm.get('return_fee'))
    returns = rnd(failed * rate / (100 - rate), 6) if rate < 100 else 0.0
    parts = [cost, comm, transfer, logistics, sc, num(st.get('pack', 18)),
             num(st.get('transit', 30)) if scheme == 'FBS' else 0.0, returns, storage, ads, cofin,
             num(st.get('fixed_per_unit', 0))]
    tax = calc_tax(price, sum(parts), st.get('tax_regime', 'usn_income_6'), num(st.get('tax_pct', 6)), num(st.get('tax_osno_share', 0)))
    return {'total': rnd(sum(parts) + tax), 'commission': comm, 'transfer': transfer, 'tax': tax,
            'returns': rnd(returns), 'storage': storage, '_expense_names': ['commission', 'paymentTransfer', 'boost', 'cofin', 'logistics', 'scDelivery', 'packaging', 'processing', 'storage', 'returns', 'tax'], '_monthly_parts': [comm, transfer, ads, cofin, logistics, sc, num(st.get('pack', 18)), num(st.get('transit', 30)) if scheme == 'FBS' else 0, storage, returns, tax], '_percent': comm + transfer + ads + cofin}

def avito_unit(price, cost, st):
    """Авито (evaluateAvito): комиссия (с минимумом 1 ₽ при включённом профи),
       доставка/скидка продавца, размещение, невыкуп от расхода случая, реклама/софин."""
    av = st.get('avito') or {}
    nominal = rnd(price * num(av.get('commission_pct', 6)) / 100)
    comm = max(1.0, nominal) if av.get('pro_min_enabled') and price > 0 else nominal
    rate = min(100.0, max(0.0, num(st.get('no_buy_pct', 0))))
    failed = num(av.get('failed_manual')) if num(av.get('failed_manual', -1)) >= 0 else num(av.get('return_fee'))
    returns = rnd(failed * rate / (100 - rate), 6) if rate < 100 else 0.0
    ads = rnd(price * num(av.get('boost_pct')) / 100); cofin = rnd(price * num(av.get('cofin_pct')) / 100)
    parts = [cost, comm, rnd(num(av.get('logistics')) * num(av.get('logistics_factor', 1))), num(st.get('pack', 18)), num(av.get('listing_fee')),
             returns, ads, cofin, num(st.get('fixed_per_unit', 0))]
    tax = calc_tax(price, sum(parts), st.get('tax_regime', 'usn_income_6'), num(st.get('tax_pct', 6)), num(st.get('tax_osno_share', 0)))
    return {'total': rnd(sum(parts) + tax), 'commission': comm, 'transfer': 0.0, 'tax': tax,
            'returns': rnd(returns), 'storage': 0.0, '_expense_names': ['commission', 'boost', 'cofin', 'logistics', 'packaging', 'returns', 'tax', 'listing'], '_monthly_parts': [comm, ads, cofin, rnd(num(av.get('logistics')) * num(av.get('logistics_factor', 1))), num(st.get('pack', 18)), returns, tax, num(av.get('listing_fee'))], '_percent': comm + ads + cofin}

def _fbs_middle_mile(volume_liters):
    import math as _m
    liters = int(_m.ceil(max(0.0, num(volume_liters))))
    if not liters: return 0.0
    return rnd(min(5500.0, 92 + min(max(liters - 1, 0), 199) * 8 + max(liters - 200, 0) * 5))

def ym_unit(price, cost, st):
    """Яндекс Маркет (evaluateYm): размещение из тарифного снимка строки,
       средняя миля по объёму, последняя миля 5% с капом 1000, спецтариф 42%
       (<=300 ₽ и <=5 л до конца 2026), обработка FBS, невыкуп с хранением возврата."""
    ym = st.get('ym') or {}
    scheme = 'FBY' if str(ym.get('fulfillment') or 'FBS').upper() == 'FBO' else 'FBS'
    v = num(st.get('_volume', 0)); dims = st.get('_dims') or (0, 0, 0)
    billable, vol_kg = _billable(st)
    import datetime as _dt
    cheap = bool(ym.get('cheap_enabled', True)) and price > 0 and price <= 300 and v > 0 \
        and int(-(-v // 1)) <= 5 and _dt.date.today() <= _dt.date(2026, 12, 31) \
        and (all(d > 0 for d in dims) or v > 0)
    placement_pct = num(st['_ym_placement_pct']) if '_ym_placement_pct' in st else num(ym.get('fallback_placement', 47))
    placement = 0.0 if cheap else rnd(price * placement_pct / 100)
    special = rnd(price * 42 / 100) if cheap else 0.0
    middle = 0.0 if cheap else rnd(_fbs_middle_mile(v) * num(ym.get('logistics_factor', 1)))
    last_mile = 0.0 if cheap else rnd(min(price * 0.05, 1000))
    transfer = rnd(price * (num(st.get('_ym_transfer_pct')) or num(ym.get('payout_pct', 2.8))) / 100)
    agency = num(st.get('_ym_agency_fee')) or num(ym.get('agency_default', 0.12))
    ads = rnd(price * num(st.get('_ym_boost_pct')) / 100); cofin = rnd(price * num(ym.get('cofin_pct')) / 100)
    is_kgt = num(st.get('_weight', 0)) >= 15 or max(dims) >= 70
    if scheme == 'FBS':
        processing = num(ym.get('processing_manual')) if num(ym.get('processing_manual', -1)) >= 0 else (rnd(vol_kg * 10) if is_kgt else 25.0)
    else: processing = 0.0
    sc = rnd(num(ym.get('sc_per_kg', 12)) * billable) if scheme == 'FBS' else 0.0
    pack = 0.0 if scheme == 'FBY' else num(st.get('pack', 18))
    transit = num(st.get('transit', 30)) if scheme == 'FBS' else 0.0
    rate = min(100.0, max(0.0, num(st.get('_ym_no_buy_pct', st.get('no_buy_pct', 0)))))
    share = max(0.0, min(100.0, num(ym.get('same_city_pct')))) / 100 if scheme == 'FBS' else 0.0
    extra = num(ym.get('return_fixed')) + num(ym.get('extra_return_per_kg')) * billable
    failed_manual = num(ym.get('failed_manual', -1)) >= 0
    failed = num(ym.get('failed_manual')) if failed_manual else ((0.0 if cheap else middle * (1 - share) + num(ym.get('return_handling', 15))) + extra)
    returns = rnd(failed * rate / (100 - rate), 6) if rate < 100 else 0.0
    return_storage = 0.0 if failed_manual else rnd(num(ym.get('return_storage_days')) * num(ym.get('return_storage_per_day', 25)) * (rate / (100 - rate) if rate < 100 else 0.0), 6)
    storage = num(ym.get('storage_per_sale')) if scheme == 'FBY' else 0.0
    penalties = num(ym.get('penalties'))
    parts = [cost, placement, special, agency, transfer, last_mile, middle, sc, pack, transit,
             processing, returns, return_storage, storage, penalties, ads, cofin, num(st.get('fixed_per_unit', 0))]
    tax = calc_tax(price, sum(parts), st.get('tax_regime', 'usn_income_6'), num(st.get('tax_pct', 6)), num(st.get('tax_osno_share', 0)))
    return {'total': rnd(sum(parts) + tax), 'commission': placement, 'transfer': transfer, 'tax': tax,
            'returns': rnd(returns + return_storage), 'storage': storage, '_expense_names': ['commission', 'specialFee', 'acquiring', 'paymentTransfer', 'lastMile', 'boost', 'cofin', 'logistics', 'scDelivery', 'packaging', 'processing', 'storage', 'returns', 'returnStorage', 'penalties', 'tax'], '_monthly_parts': [placement, special, agency, transfer, last_mile, ads, cofin, middle, sc, pack, transit + processing, storage, returns, return_storage, penalties, tax], '_percent': placement + special + transfer + ads + cofin + (last_mile if price * 0.05 <= 1000 else 0)}

def _net_unit(price, cost, st, sales, unit_result):
    if '_monthly_parts' not in unit_result:
        return rnd(price - unit_result['total'])
    parts = unit_result['_monthly_parts']
    if sales <= 0:
        return rnd(price - cost - sum(parts), 4)
    monthly = sum(rnd(value * sales) for value in parts)
    fixed_month = num(st.get('_fixed_month', num(st.get('fixed_per_unit')) * sales))
    net = rnd(rnd(price * sales) - rnd(cost * sales) - monthly - max(0, fixed_month))
    return net / sales


def solve_prices(price, cost, st, target_margin=20.0, sales=1, unit=None):
    sales = max(0, num(sales))
    if sales <= 0 or num(st.get('no_buy_pct')) >= 100:
        return {'break_even': 0, 'target': 0}
    unit = unit or ozon_unit
    cache = {}
    def evaluate(p):
        if p not in cache: cache[p] = _net_unit(p, cost, st, sales, unit(p, cost, st))
        return cache[p]
    base = unit(price, cost, st)
    percent = num(base.get('_percent', base.get('commission', 0) + base.get('transfer', 0)))
    if st.get('tax_regime', 'usn_income_6') in ('usn_income_6', 'usn_income_7', 'usn_income_vat_5', 'usn_income_vat_7', 'self_employed_4', 'self_employed_6', 'custom'):
        percent += base['tax']
    rate = max(0, min(0.95, percent / price)) if price > 0 else 0
    fixed = price - _net_unit(price, cost, st, sales, base) - percent
    if not math.isfinite(fixed) or fixed < 0: fixed = max(1, cost)
    be_guess = max(0, js_round(fixed / max(0.005, 1 - rate)))
    margin = max(0, num(target_margin)) / 100
    target_guess = max(0, js_round(fixed / max(0.005, 1 - rate - margin)))
    edge = 300 if unit is ym_unit and (st.get('ym') or {}).get('cheap_enabled', True) and 0 < num(st.get('_volume')) <= 5 else 0
    be = stable_floor(be_guess, evaluate, edge)
    target = stable_floor(target_guess, lambda p: evaluate(p) - p * margin if p > 0 else -1, edge)
    return {'break_even': be, 'target': max(be, target)}

def _calculation_dimensions(row, settings):
    if not settings.get('calc_std_dims'): return row
    context = json.loads(row.get('dimension_context') or '{}')
    if context.get('blocked'): return row
    dictionary = settings.get('std_dims')
    if dictionary is None: dictionary = _asset('std_dims.json') or []
    normalize = lambda v: re.sub(r'\s+', ' ', re.sub(r'[()\[\]\-_,.„“”«»/\\]', ' ', str(v or '').lower())).strip()
    candidates = []
    for field in ('category_type', 'name', 'category'):
        key = normalize(row.get(field))
        if key:
            candidates.extend(d for d in dictionary if normalize(d.get('c')) == key)
    signatures = {tuple(rnd(num(d.get(k)), 6) for k in ('l', 'w', 'h', 'wt')) for d in candidates}
    if len(signatures) != 1: return row
    result = dict(row)
    for field, key in (('length', 'l'), ('width', 'w'), ('height', 'h'), ('weight', 'wt')):
        if num(result.get(field)) <= 0 and num(candidates[0].get(key)) > 0:
            result[field] = num(candidates[0][key])
    # A derived volume must follow temporary dimensions; explicit volume is kept.
    if not context.get('explicitVolume'):
        result['volume'] = num(result.get('length')) * num(result.get('width')) * num(result.get('height')) / 1000
    return result

def calc_row(row, st):
    row = _calculation_dimensions(row, st)
    price, cost = num(row.get('price')), num(row.get('cost'))
    if num(row.get('eff_price')) > 0: price = num(row.get('eff_price'))  # v12.9.149: промо-цена, как effPrice браузера
    # v12.9.145: паритет с браузером (calcMarketplacesEconomics/costWithMultiplicity):
    # себестоимость одного продаваемого SKU — с учётом кратности отгрузки,
    # а построчные тарифы SKU важнее общих настроек.
    if st.get('multiplicity_enabled', True):
        _mult = num(row.get('multiplicity'))
        if _mult > 1: cost = rnd(cost * _mult)
    L, W, H = num(row.get('length')), num(row.get('width')), num(row.get('height'))
    vol = num(row.get('volume')) or (L * W * H / 1000 if L and W and H else 0.0)
    st2 = dict(st); st2['_volume'] = vol; st2['_weight'] = num(row.get('weight'))
    st2['_dims'] = (num(row.get('length')), num(row.get('width')), num(row.get('height')))
    for field, (market, key) in ROW_ECO_OVERRIDES.items():
        if row.get(field) is not None and str(row[field]).strip() != '':
            value = max(0, num(row[field]))
            if market:
                st2[market] = {**(st2.get(market) or {}), key: value}
            else:
                st2[key] = value
    if num(row.get('ozon_commission')) > 0: st2['commission_pct'] = num(row.get('ozon_commission'))
    if row.get('no_buy_pct') is not None and str(row.get('no_buy_pct')).strip() != '': st2['no_buy_pct'] = num(row.get('no_buy_pct'))
    elif isinstance(st.get('no_buy_by_category'), dict) and str(row.get('category') or '') in st['no_buy_by_category']:
        st2['no_buy_pct'] = num(st['no_buy_by_category'][str(row.get('category'))])
    if num(row.get('ozon_failed_cost')) > 0: st2['failed_case'] = num(row.get('ozon_failed_cost'))
    # браузер: месячный фикс (SKU + общий/число SKU) делится на прогноз продаж
    _fixed_month = num(row.get('fixed_cost')) + num(st.get('fixed_monthly_per_sku'))
    st2['_fixed_month'] = _fixed_month
    if _fixed_month > 0:
        _sales = num(row.get('sales'))
        st2['fixed_per_unit'] = _fixed_month / _sales if _sales > 0 else _fixed_month
    if num(row.get('ozon_logistics')) > 0: st2['_row_logistics'] = num(row.get('ozon_logistics'))
    if num(row.get('ozon_realfbs_delivery')) > 0: st2['_row_realfbs'] = num(row.get('ozon_realfbs_delivery'))
    if num(row.get('ozon_logistics')) > 0 or num(row.get('ozon_realfbs_delivery')) > 0:
        # заданный маршрут SKU заменяет усреднённую пару «последняя миля + сдача»
        st2['last_mile'] = num(row.get('ozon_logistics')) + num(row.get('ozon_realfbs_delivery'))
        st2['handover'] = 0
    _scope = str(st.get('mp_scope') or '').upper()
    if _scope == 'ALL': _scope = 'YM'
    if row.get('ym_placement_pct') is not None: st2['_ym_placement_pct'] = num(row.get('ym_placement_pct'))
    if row.get('ym_transfer_pct') is not None: st2['_ym_transfer_pct'] = num(row.get('ym_transfer_pct'))
    if row.get('ym_agency_fee') is not None: st2['_ym_agency_fee'] = num(row.get('ym_agency_fee'))
    if row.get('ym_boost_pct') is not None: st2['_ym_boost_pct'] = num(row.get('ym_boost_pct'))
    if row.get('ym_return_pct') is not None: st2['_ym_no_buy_pct'] = num(row.get('ym_return_pct'))
    # What-If is scoped to the selected marketplace, as scenarioPct in JS.
    scenario = st.get('scenario') or {}
    market = {'WB': 'wb', 'MM': 'mm', 'AVITO': 'avito', 'YM': 'ym', 'OZON': 'ozon'}.get(_scope)
    if market and scenario:
        options = dict(st2.get(market) or {})
        for source, key in (('boostPct', 'boost_pct'), ('cofinPct', 'cofin_pct'), ('logisticsFactor', 'logistics_factor')):
            if scenario.get(source) is not None and scenario[source] != '':
                options[key] = max(0, num(scenario[source]))
        if market == 'mm' and 'cofin_pct' in options: options['loyalty_pct'] = options['cofin_pct']
        if market == 'ym':
            if scenario.get('ymCommissionPct') is not None: st2['_ym_placement_pct'] = max(0, num(scenario['ymCommissionPct']))
            if scenario.get('boostPct') is not None: st2['_ym_boost_pct'] = max(0, num(scenario['boostPct']))
        st2[market] = options
        if scenario.get('targetMargin') is not None: st2['target_margin'] = max(0, num(scenario['targetMargin']))
    _unit = {'WB': wb_unit, 'MM': mm_unit, 'AVITO': avito_unit, 'YM': ym_unit}.get(_scope, ozon_unit)
    u = _unit(price, cost, st2)
    net_unit = _net_unit(price, cost, st2, max(0, num(row.get('sales', 1))), u)
    profit = rnd(net_unit)
    total = rnd(price - net_unit)
    solved = solve_prices(price, cost, st2, num(st2.get('target_margin', 20)), row.get('sales', 1), unit=_unit)
    expenses = dict(zip(u.get('_expense_names', []), u.get('_monthly_parts', [])))
    if not expenses:
        expenses = {'commission': u['commission'], 'paymentTransfer': u['transfer'], 'tax': u['tax'], 'returns': u['returns'], 'storage': u['storage']}
    sales = max(0, num(row.get('sales', 1)))
    fields = {key: expenses.get(key, 0.0) for key in (
        'commission', 'specialFee', 'acquiring', 'paymentTransfer', 'logistics', 'lastMile',
        'scDelivery', 'packaging', 'processing', 'returns', 'returnStorage', 'penalties',
        'boost', 'cofin', 'tax', 'storage', 'listing', 'nonStd', 'lateShip')}
    fields.update({'revenue': price, 'cogs': cost, 'effPrice': price, 'costPerUnit': total,
                   'perUnitNet': profit, 'contribution': rnd(price - cost - sum(expenses.values()), 4),
                   'fixedTotal': _fixed_month, 'fixedTotalRaw': _fixed_month,
                   'mRevenue': rnd(price * sales), 'mCogs': rnd(cost * sales),
                   'mNetProfit': rnd(net_unit * sales) if sales > 0 else -_fixed_month})
    for name in ('Commission', 'LastMile', 'Logistics', 'Tax', 'Processing', 'Returns'):
        fields['m' + name] = rnd(expenses.get(name[0].lower() + name[1:], 0) * sales)
    return {'article': row.get('article', ''), 'brand': row.get('brand', ''), 'total': total, 'profit': profit,
            'margin': rnd(net_unit / price * 100, 1) if price else 0.0,
            'roi': rnd(net_unit / cost * 100, 1) if cost else 0.0,
            'commission': u['commission'], 'tax': u['tax'], 'returns': u['returns'],
            'storage': u['storage'], 'volume': rnd(vol, 4),
            'break_even': solved['break_even'], 'target': solved['target'], 'fields': fields}

# ---------------- SQLite ----------------
ROW_ECO_OVERRIDES = {
    'wb_commission': ('wb', 'commission_pct'), 'wb_failed_cost': ('wb', 'failed_manual'),
    'mm_commission': ('mm', 'commission_pct'), 'mm_logistics': ('mm', 'fbs_logistics'),
    'mm_failed_cost': ('mm', 'failed_manual'),
    'avito_commission': ('avito', 'commission_pct'), 'avito_failed_cost': ('avito', 'failed_manual'),
    'ym_processing_per_unit': ('ym', 'processing_manual'), 'ym_failed_cost': ('ym', 'failed_manual'),
    'pack_cost': (None, 'pack'), 'ym_cofin_pct': ('ym', 'cofin_pct'),
}

SCHEMA = '''
CREATE TABLE IF NOT EXISTS products(
  article TEXT NOT NULL, brand TEXT DEFAULT '', name TEXT DEFAULT '',
  price REAL DEFAULT 0, cost REAL DEFAULT 0, stock REAL DEFAULT 0, sales REAL DEFAULT 0,
  weight REAL DEFAULT 0, length REAL DEFAULT 0, width REAL DEFAULT 0, height REAL DEFAULT 0,
  volume REAL DEFAULT 0, oe_numbers TEXT DEFAULT '', analog_list TEXT DEFAULT '',
  source TEXT DEFAULT '', updated_at TEXT DEFAULT '',
  PRIMARY KEY(article, brand));
CREATE INDEX IF NOT EXISTS ix_products_oe ON products(oe_numbers);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS supplier_rules(email TEXT, file_pattern TEXT, profile TEXT);
CREATE TABLE IF NOT EXISTS outbox(
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, marketplace TEXT, article TEXT,
  payload TEXT, idempotency_key TEXT UNIQUE, status TEXT DEFAULT 'pending',
  attempts INTEGER DEFAULT 0, last_error TEXT DEFAULT '', created_at TEXT, sent_at TEXT);
CREATE TABLE IF NOT EXISTS price_history(article TEXT, brand TEXT DEFAULT '', price REAL, cost REAL,
  stock REAL, source TEXT, ts TEXT);
CREATE INDEX IF NOT EXISTS ix_price_history_key ON price_history(article, brand, ts);
CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, note TEXT, total INTEGER);
CREATE TABLE IF NOT EXISTS snapshot_rows(snapshot_id INTEGER, article TEXT, brand TEXT DEFAULT '',
  price REAL, cost REAL, stock REAL, PRIMARY KEY(snapshot_id, article, brand));
CREATE TABLE IF NOT EXISTS parse_sessions(id TEXT PRIMARY KEY, filename TEXT, headers TEXT,
  total INTEGER, created TEXT);
CREATE TABLE IF NOT EXISTS parse_rows(session TEXT, idx INTEGER, data TEXT,
  PRIMARY KEY(session, idx));
CREATE TABLE IF NOT EXISTS donors(article TEXT NOT NULL, brand TEXT DEFAULT '', source TEXT DEFAULT '',
  name TEXT DEFAULT '', category TEXT DEFAULT '', tnved TEXT DEFAULT '', applicability TEXT DEFAULT '',
  warranty TEXT DEFAULT '', country TEXT DEFAULT '',
  weight REAL DEFAULT 0, length REAL DEFAULT 0, width REAL DEFAULT 0, height REAL DEFAULT 0,
  oe_numbers TEXT DEFAULT '', PRIMARY KEY(article, brand, source));
CREATE TABLE IF NOT EXISTS oe_links(oe TEXT NOT NULL, article TEXT NOT NULL, brand TEXT DEFAULT '',
  PRIMARY KEY(oe, article, brand));
CREATE INDEX IF NOT EXISTS ix_oe_links_article ON oe_links(article, brand);
CREATE TABLE IF NOT EXISTS eco_results(
  article TEXT NOT NULL, brand TEXT DEFAULT '', total REAL, profit REAL, margin REAL,
  roi REAL, break_even REAL, target REAL, computed_at TEXT DEFAULT '',
  inputs_hash TEXT DEFAULT '',
  PRIMARY KEY(article, brand));
CREATE TABLE IF NOT EXISTS api_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, action TEXT,
  endpoint TEXT, status TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS mail_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, subject TEXT,
  sender TEXT, filename TEXT, rows INTEGER, status TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(article, brand, name, oe_numbers, content='products', content_rowid='rowid');
'''
_SCHEMA_DONE = set()
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try: conn.execute('PRAGMA busy_timeout=5000')
    except Exception: pass
    # v12.9.118: WAL кратно ускоряет массовые записи (импорт/обогащение) и не
    # блокирует чтение на время записи; synchronous=NORMAL безопасен при WAL.
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA temp_store=MEMORY')
    except Exception: pass
    if str(DB_PATH) in _SCHEMA_DONE:  # B4: схема и миграции — один раз на процесс
        return conn
    conn.executescript(SCHEMA)
    conn.execute('CREATE TABLE IF NOT EXISTS oe_registry(oe TEXT PRIMARY KEY, data TEXT NOT NULL)')
    if 'fields_json' not in {r[1] for r in conn.execute('PRAGMA table_info(eco_results)')}:
        conn.execute("ALTER TABLE eco_results ADD COLUMN fields_json TEXT DEFAULT '{}'")
    # миграция баз до v12.9.110: обогащаемые текстовые поля каталога
    ecols = {r[1] for r in conn.execute('PRAGMA table_info(eco_results)')}
    if 'inputs_hash' not in ecols:
        conn.execute("ALTER TABLE eco_results ADD COLUMN inputs_hash TEXT DEFAULT ''")
    cols = {r[1] for r in conn.execute('PRAGMA table_info(products)')}
    for col in ('dimension_review', 'dimension_context'):
        if col not in cols:
            conn.execute(f"ALTER TABLE products ADD COLUMN {col} TEXT DEFAULT '{{}}'")
    # Nullable overrides: NULL is unspecified; explicit zero is a valid tariff.
    for col in ROW_ECO_OVERRIDES:
        if col not in cols:
            conn.execute(f'ALTER TABLE products ADD COLUMN {col} REAL DEFAULT NULL')
    dcols = {r[1] for r in conn.execute('PRAGMA table_info(donors)')}
    for col in ('warranty', 'country'):
        if col not in dcols:
            conn.execute(f"ALTER TABLE donors ADD COLUMN {col} TEXT DEFAULT ''")
    cols = {r[1] for r in conn.execute('PRAGMA table_info(products)')}
    for col in ('category', 'tnved', 'applicability',
                'barcode', 'image_url', 'extra_photos', 'ozon_sku', 'ozon_type', 'ozon_category',
                'model', 'hazard_class', 'color', 'material', 'country', 'warranty', 'diameter',
                'package_contents', 'rich_content', 'description', 'mark_required',
                'group_articles', 'cross_numbers'):
        if col not in cols:
            conn.execute(f"ALTER TABLE products ADD COLUMN {col} TEXT DEFAULT ''")
    for col in ('multiplicity', 'net_weight', 'old_price'):
        if col not in cols:
            conn.execute(f"ALTER TABLE products ADD COLUMN {col} REAL DEFAULT 0")
    # v12.9.140: поля обогащения браузера, которых не было в SQLite
    for col in ('original_article', 'category_type', 'category_src', 'ozon_description_category_id',
                'ozon_type_id', 'visible_reason', 'mark_status', 'mark_code', 'dimensions_str', 'currency'):
        if col not in cols:
            conn.execute(f"ALTER TABLE products ADD COLUMN {col} TEXT DEFAULT ''")
    for col in ('ozon_commission', 'ozon_logistics', 'ozon_realfbs_delivery', 'ozon_failed_cost',
                'min_stock', 'no_buy_pct', 'fixed_cost'):
        if col not in cols:
            conn.execute(f"ALTER TABLE products ADD COLUMN {col} REAL DEFAULT 0")
    if 'eff_price' not in cols:
        conn.execute("ALTER TABLE products ADD COLUMN eff_price REAL DEFAULT 0")
    if 'visible' not in cols:
        conn.execute("ALTER TABLE products ADD COLUMN visible TEXT DEFAULT '1'")
    if 'excluded' not in cols:
        conn.execute("ALTER TABLE products ADD COLUMN excluded TEXT DEFAULT '0'")
    for col in ('ym_placement_pct', 'ym_transfer_pct', 'ym_agency_fee', 'ym_boost_pct', 'ym_return_pct'):
        if col not in cols:
            conn.execute(f"ALTER TABLE products ADD COLUMN {col} REAL DEFAULT 0")
    if 'ym_found' not in cols:
        conn.execute("ALTER TABLE products ADD COLUMN ym_found REAL DEFAULT 1")
    dcols = {r[1] for r in conn.execute('PRAGMA table_info(donors)')}
    for col, typ, dflt in (('barcode', 'TEXT', "''"), ('image_url', 'TEXT', "''"), ('multiplicity', 'REAL', '0')):
        if col not in dcols:
            conn.execute(f"ALTER TABLE donors ADD COLUMN {col} {typ} DEFAULT {dflt}")
    # B5: retention — история цен год, лог API 90 дней
    try:
        conn.execute("DELETE FROM price_history WHERE ts < datetime('now','-365 days')")
        conn.execute("DELETE FROM api_log WHERE ts < datetime('now','-90 days')")
    except Exception: pass
    conn.commit()
    _SCHEMA_DONE.add(str(DB_PATH))
    return conn

def log_api(conn, action, endpoint, status, detail=''):
    conn.execute('INSERT INTO api_log(ts,action,endpoint,status,detail) VALUES(datetime("now"),?,?,?,?)',
                 (action, endpoint, status, str(detail)[:500]))
    conn.commit()

def get_settings(conn):
    return {r['key']: r['value'] for r in conn.execute('SELECT key,value FROM settings')}

def _dpapi(data: bytes, protect: bool) -> bytes:
    # A3 (аудит v12.9.133): на Windows секреты хранятся зашифрованными DPAPI
    # (привязка к учётной записи пользователя); на прочих ОС — как есть.
    if os.name != 'nt': return data
    import ctypes, base64 as _b64
    class BLOB(ctypes.Structure):
        _fields_ = [('cbData', ctypes.c_ulong), ('pbData', ctypes.POINTER(ctypes.c_char))]
    if protect:
        raw = data
    else:
        try: raw = _b64.b64decode(data)
        except Exception: return data  # старый открытый формат — читаем как есть
    buf = ctypes.create_string_buffer(raw, len(raw))
    blob_in, blob_out = BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), BLOB()
    fn = (ctypes.windll.crypt32.CryptProtectData if protect
          else ctypes.windll.crypt32.CryptUnprotectData)
    if not fn(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        return data if not protect else (_b64.b64encode(data))
    out = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    import base64 as _b64
    return _b64.b64encode(out) if protect else out

def save_secret(key, value):
    cur = {}
    if SECRETS_PATH.exists():
        try: cur = json.loads(_dpapi(SECRETS_PATH.read_bytes(), False).decode('utf-8'))
        except Exception: cur = {}
    if value: cur[key] = value
    else: cur.pop(key, None)  # пустое значение = удалить секрет
    SECRETS_PATH.write_bytes(_dpapi(json.dumps(cur, ensure_ascii=False).encode('utf-8'), True))

def secrets():
    env = {k: os.environ.get(k) for k in
           ('UC_OZON_CLIENT_ID', 'UC_OZON_API_KEY', 'UC_WB_TOKEN', 'UC_MAIL_PASSWORD', 'UC_YM_TOKEN')}
    file_secrets = {}
    if SECRETS_PATH.exists():
        try: file_secrets = json.loads(_dpapi(SECRETS_PATH.read_bytes(), False).decode('utf-8'))
        except Exception: file_secrets = {}
    merged = dict(file_secrets)
    for k, v in env.items():
        if v: merged[k] = v
    return merged

# ---------------- импорт строк (CSV/XLSX/ZIP) ----------------
ALIASES = {
    'article': ('артикул', 'article', 'sku', 'каталожный номер', 'код товара', 'артикул продавца', 'артикул поставщика'),
    'brand': ('бренд', 'brand', 'производитель'),
    'name': ('название', 'name', 'наименование', 'описание'), 'price': ('цена', 'price'),
    'barcode': ('штрихкод', 'barcode', 'ean'), 'multiplicity': ('кратность', 'multiplicity'),
    'cost': ('себестоимость', 'cost', 'закупка'), 'stock': ('остаток', 'stock', 'количество'),
    'oe_numbers': ('oe', 'oem', 'ое', 'номер oe'), 'weight': ('вес', 'weight'),
    'sales': ('продажи', 'sales'), 'category': ('категор', 'category'),
    'tnved': ('тн вэд', 'тнвэд', 'tnved', 'hs code'), 'applicability': ('применяем', 'applicab', 'совмест'),
    'length': ('длина', 'length'), 'width': ('ширина', 'width'), 'height': ('высота', 'height'),
    # v12.9.140: поля обогащения браузерного импорта (STD/FIELD_ALIAS приложения)
    'volume': ('объём', 'объем', 'volume'), 'analog_list': ('аналоги', 'analog', 'кроссы'),
    'group_articles': ('группа артикулов', 'group'), 'cross_numbers': ('кросс-номера', 'кросс номера', 'cross'),
    'original_article': ('ориг. артикул', 'оригинальный артикул', 'original'), 'category_type': ('вид категории', 'тип категории', 'подкатегория'),
    'category_src': ('исходная категория', 'путь категории', 'breadcrumb'), 'currency': ('валюта', 'currency'),
    'warranty': ('гарантия', 'warranty'), 'country': ('страна-изготовитель', 'страна', 'country'),
    'image_url': ('ссылка на изображение', 'изображение', 'фото', 'image'), 'extra_photos': ('дополнительные фото', 'extra_photos'),
    'ozon_sku': ('sku ozon', 'ozon sku', 'ozon_sku'), 'ozon_category': ('категория ozon', 'ozon_category'),
    'ozon_type': ('тип ozon', 'ozon_type'), 'ozon_description_category_id': ('id категории ozon', 'description_category_id'),
    'ozon_type_id': ('id типа ozon', 'type_id'), 'model': ('модель', 'model'), 'color': ('цвет', 'color'),
    'material': ('материал', 'material'), 'description': ('аннотация', 'описание товара', 'description'),
    'dimensions_str': ('весогабариты', 'габариты', 'dimensions'), 'mark_required': ('нужен честный знак', 'требуется сертификат', 'маркировка'),
    'mark_status': ('статус честного знака', 'mark_status'), 'mark_code': ('код маркировки', 'mark_code'),
    'min_stock': ('мин. остаток', 'минимальный остаток', 'min_stock', 'неснижаемый'),
    'no_buy_pct': ('невыкуп', 'no_buy', 'возврат'), 'fixed_cost': ('фикс. расходы', 'fixed'),
    'ozon_commission': ('вознаграждение ozon', 'комиссия ozon', 'ozon_commission'),
    'ozon_logistics': ('логистика ozon', 'ozon_logistics', 'ozon logistics'),
    'ozon_realfbs_delivery': ('ozon_realfbs_delivery', 'доставка ozon realfbs', 'ozon realfbs доставка'),
    'net_weight': ('вес нетто', 'масса нетто', 'вес товара без упаковки', 'net_weight', 'net weight'),
    'old_price': ('зачёркнутая цена', 'зачеркнутая цена', 'старая цена', 'old_price')}
def map_header(header):
    """v12.9.146 (проверка №3): назначение колонок однозначное, как guessField
       браузера: одна колонка — одно поле. Раньше независимый проход по полям
       отдавал «Код ТН ВЭД» и в article, и в tnved, а «Зачёркнутую цену» —
       и в price, и в old_price. Побеждает лучшее совпадение (точное >
       начало > подстрока), при равенстве — порядок полей как объявлен."""
    low = [str(h or '').strip().lower() for h in header]
    cands = []  # (score, -len(alias), field_order, col, field): длинный алиас точнее
    for fo, (field, names) in enumerate(ALIASES.items()):
        for i, h in enumerate(low):
            if not h: continue
            if field == 'article' and 'штрих' in h: continue
            sc, best_len = -1, 0
            for n in names:
                if h == n: sc, best_len = 0, len(n); break
            if sc < 0:
                for n in names:
                    if h.startswith(n): sc, best_len = 1, max(best_len, len(n)); break
            if sc < 0:
                for n in names:
                    if n in h: sc, best_len = 2, max(best_len, len(n))
            if sc >= 0: cands.append((sc, -best_len, fo, i, field))
    out, used_cols, used_fields = {}, set(), set()
    for sc, _nl, fo, i, field in sorted(cands):
        if i in used_cols or field in used_fields: continue
        out[field] = i; used_cols.add(i); used_fields.add(field)
    return out

def _apply_units(item, mp, headers):
    """v12.9.147: единицы как в браузерном импорте (parseDimensionCm и вес):
       длина/ширина/высота в базе — сантиметры, вес — килограммы, объём — литры.
       Движок раньше писал число как есть: «Длина, мм» давала 10-кратную ошибку.
       Сводную ячейку габаритов («230x170x80») разбираем в Д/Ш/В, если пусты."""
    def hdr(f):
        i = mp.get(f)
        return str(headers[i]).lower() if i is not None and i < len(headers) else ''
    for f in ('length', 'width', 'height'):
        if f in item and num(item[f]) > 0:
            h = hdr(f)
            if 'мм' in h or 'mm' in h: item[f] = num(item[f]) / 10
    for f in ('weight', 'net_weight'):
        if f in item and num(item[f]) > 0:
            h = hdr(f)
            if 'грамм' in h or ', г' in h or '(г' in h or ' g' in h or h.rstrip().endswith('г'): item[f] = num(item[f]) / 1000
    if 'volume' in item and num(item['volume']) > 0:
        h = hdr('volume')
        if 'см3' in h or 'см³' in h or 'cm3' in h: item['volume'] = num(item['volume']) / 1000
        elif 'м3' in h or 'м³' in h or 'm3' in h: item['volume'] = num(item['volume']) * 1000
    ds = str(item.get('dimensions_str') or '').strip()
    if ds and not all(num(item.get(f)) > 0 for f in ('length', 'width', 'height')):
        parts = [x for x in re.split(r'[*x×х/|;]', ds.replace(',', '.')) if str(x).strip()]
        nums = []
        for x in parts[:3]:
            m = re.search(r'\d+(?:\.\d+)?', str(x))
            if m: nums.append(float(m.group(0)))
        if len(nums) == 3 and all(n > 0 for n in nums):
            k = 0.1 if ('мм' in hdr('dimensions_str') or 'mm' in hdr('dimensions_str')) else 1
            for f, v in zip(('length', 'width', 'height'), nums):
                if not num(item.get(f)) > 0: item[f] = v * k
    return item

def resolve_import_mapping(headers, mapping=None):
    if mapping is None: return map_header(headers)
    out={}
    for entry in mapping:
        if not entry.get('enabled',True) or not entry.get('field'): continue
        if entry.get('src') not in headers: continue
        field=entry['field']
        if field in out: raise ValueError('Повторное назначение поля: '+field)
        out[field]=headers.index(entry['src'])
    return out

def import_header_index(rows):
    # Import.read: first plausible header among the first nine nonempty rows.
    for i, row in enumerate(rows[:9]):
        filled=sum(bool(str(c if c is not None else '').strip()) for c in row)
        alpha=sum(bool(re.search('[а-яa-z]',str(c or ''),re.I)) for c in row)
        if filled>=2 and alpha>=filled*.4: return i
    return 0


def safe_csv_text(value):
    s='' if value is None else str(value)
    s=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]',' ',s)
    if (re.match(r'^[\s\u00a0]*[=+@]',s) or re.match(r'^[ \u00a0]*[\t\r\n]',s) or
        (re.match(r'^[\s\u00a0]*-',s) and not re.fullmatch(r'\s*-\d+(?:[.,]\d+)?\s*',s,flags=re.ASCII))):
        s="'"+s
    return s


def encode_csv(text, enc):
    if enc=='cp1251':
        try: return text.replace('₽','руб.').encode('cp1251')
        except UnicodeEncodeError as exc:
            raise ValueError('Windows-1251 не содержит часть символов. Выберите CSV UTF-8 или XLSX: подмена символов запрещена.') from exc
    return ('\ufeff'+text).encode('utf-8')

def rows_from_csv_bytes(data, mapping=None):
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        # Inspect the entire input, never silently replace characters after
        # a long ASCII preamble. Undefined cp1251 bytes fail explicitly.
        text = data.decode('cp1251')
    delim = ';' if text.split('\n', 1)[0].count(';') >= text.split('\n', 1)[0].count(',') else ','
    try:  # B9: Sniffer учитывает кавычки; fallback — эвристика по первой строке
        delim = csv.Sniffer().sniff(text[:2048], delimiters=';,\t|').delimiter
    except Exception: pass
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows: return []
    rows=[r for r in rows if any(str(c if c is not None else '').strip() for c in r)]
    if not rows: return []
    rows=rows[import_header_index(rows):]
    mp = resolve_import_mapping(rows[0], mapping)
    if 'article' not in mp: return []
    out = []
    for r in rows[1:]:
        if not r or mp['article'] >= len(r) or not str(r[mp['article']]).strip(): continue
        item = {}
        for f, i in mp.items():
            item[f] = r[i] if i < len(r) else ''
        out.append(_apply_units(item, mp, rows[0]))
    return out

def _xlsx_sheet_rows(data):
    """v12.9.141: чтение XLSX чистым stdlib (zip + XML) — движок собирается в
       exe без openpyxl, а импорт XLSX падал с «openpyxl не установлен».
       Понимает sharedStrings, inlineStr, числа и строки; первый лист книги."""
    import zipfile
    import xml.etree.ElementTree as ET
    NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    RNS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        shared = []
        if 'xl/sharedStrings.xml' in names:
            root = ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in root.findall(NS + 'si'):
                shared.append(''.join(t.text or '' for t in si.iter(NS + 't')))
        # целевой лист: первый из workbook.xml по rels, иначе sheet1
        sheet_path = 'xl/worksheets/sheet1.xml'
        try:
            wbroot = ET.fromstring(z.read('xl/workbook.xml'))
            rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
            relmap = {r.get('Id'): r.get('Target') for r in rels}
            first = wbroot.find(NS + 'sheets/' + NS + 'sheet')
            if first is not None:
                tgt = relmap.get(first.get(RNS + 'id'), '')
                if tgt:
                    import posixpath
                    sheet_path = posixpath.normpath(tgt.lstrip('/') if tgt.startswith('/') else posixpath.join('xl',tgt))
        except Exception: pass
        if sheet_path not in names:
            cand = sorted(n for n in names if n.startswith('xl/worksheets/sheet'))
            if not cand: return []
            sheet_path = cand[0]
        root = ET.fromstring(z.read(sheet_path))
    def col_idx(ref):
        n = 0
        for ch in ref:
            if ch.isalpha(): n = n * 26 + (ord(ch.upper()) - 64)
            else: break
        return n - 1
    rows = []
    for row_el in root.iter(NS + 'row'):
        cells = {}
        maxc = -1
        for c in row_el.findall(NS + 'c'):
            idx = col_idx(c.get('r', 'A1'))
            t = c.get('t')
            v = c.find(NS + 'v')
            val = None
            if t == 'inlineStr':
                is_el = c.find(NS + 'is')
                val = ''.join(x.text or '' for x in is_el.iter(NS + 't')) if is_el is not None else ''
            elif v is not None and v.text is not None:
                if t == 's':
                    try: val = shared[int(v.text)]
                    except Exception: val = ''
                elif t in ('str', 'e'):
                    val = v.text
                else:
                    try:
                        fv = float(v.text)
                        val = int(fv) if fv == int(fv) and '.' not in v.text else fv
                    except Exception: val = v.text
            if val is not None:
                cells[idx] = val; maxc = max(maxc, idx)
        if maxc >= 0:
            rows.append([cells.get(i, '') for i in range(maxc + 1)])
    return rows

def rows_from_xlsx_bytes(data, mapping=None):
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        try:
            ws = wb.worksheets[0]
            rows = list(ws.iter_rows(values_only=True))
        finally:
            wb.close()
    except ImportError:
        rows = _xlsx_sheet_rows(data)
    if not rows: return []
    rows=[r for r in rows if any(str(c if c is not None else '').strip() for c in r)]
    if not rows: return []
    rows=rows[import_header_index(rows):]
    mp = resolve_import_mapping(rows[0], mapping)
    if 'article' not in mp: return []
    out = []
    for r in rows[1:]:
        if not r or mp['article'] >= len(r) or r[mp['article']] in (None, ''): continue
        out.append(_apply_units({f: (r[i] if i < len(r) and r[i] is not None else '') for f, i in mp.items()}, mp, rows[0]))
    return out

def files_from_zip(data):
    # B3 (аудит №2): лимиты против zip-бомб — по числу файлов и распакованному объёму
    out = []; total = 0
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos = [i for i in z.infolist() if i.filename.lower().endswith(('.csv', '.xlsx'))]
        if len(infos) > 200: raise ValueError('в архиве больше 200 файлов данных')
        for info in infos:
            if info.file_size > 200 * 1024 * 1024: raise ValueError('файл в архиве больше 200 МБ: ' + info.filename)
            total += info.file_size
            if total > 500 * 1024 * 1024: raise ValueError('суммарный объём архива больше 500 МБ')
            out.append((os.path.basename(info.filename), z.read(info.filename)))
    return out

def import_rows(conn, rows, source, rebuild_fts=True, commit=True, history=True):
    n = 0
    for r in rows:
        art = str(r.get('article', '')).strip()
        if not art: continue
        brand = str(r.get('brand', '')).strip()
        old = conn.execute('SELECT price,cost,stock,sales,weight,length,width,height FROM products WHERE article=? AND brand=?', (art, brand)).fetchone()
        # B1 (аудит №2): поля, которых нет в строке источника, не трогаем —
        # ценовой файл без остатков не должен обнулять остатки/габариты.
        # Явно переданный 0 (ключ есть) — честное обновление.
        def eff(k):
            if k in r: return num(r.get(k))
            if old is None: return 0.0
            try: return float(old[k])
            except Exception: return 0.0
        conn.execute('''INSERT INTO products(article,brand,name,price,cost,stock,sales,weight,length,width,height,volume,oe_numbers,analog_list,category,tnved,applicability,barcode,image_url,extra_photos,ozon_sku,ozon_type,ozon_category,model,hazard_class,color,material,country,warranty,diameter,package_contents,rich_content,description,mark_required,group_articles,cross_numbers,multiplicity,net_weight,old_price,original_article,category_type,category_src,ozon_description_category_id,ozon_type_id,mark_status,mark_code,dimensions_str,currency,ozon_commission,ozon_logistics,ozon_realfbs_delivery,ozon_failed_cost,min_stock,no_buy_pct,fixed_cost,source,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime("now"))
            ON CONFLICT(article,brand) DO UPDATE SET
              name=COALESCE(NULLIF(excluded.name,''),products.name),
              price=CASE WHEN excluded.price>0 THEN excluded.price ELSE products.price END,
              cost=CASE WHEN excluded.cost>0 THEN excluded.cost ELSE products.cost END,
              stock=excluded.stock, sales=excluded.sales, weight=excluded.weight, length=excluded.length,
              width=excluded.width, height=excluded.height,
              volume=CASE WHEN excluded.volume>0 THEN excluded.volume ELSE products.volume END,
              oe_numbers=CASE WHEN excluded.oe_numbers<>'' THEN excluded.oe_numbers ELSE products.oe_numbers END,
              analog_list=CASE WHEN excluded.analog_list<>'' THEN excluded.analog_list ELSE products.analog_list END,
              category=CASE WHEN excluded.category<>'' THEN excluded.category ELSE products.category END,
              tnved=CASE WHEN excluded.tnved<>'' THEN excluded.tnved ELSE products.tnved END,
              applicability=CASE WHEN excluded.applicability<>'' THEN excluded.applicability ELSE products.applicability END,
              barcode=CASE WHEN excluded.barcode<>'' THEN excluded.barcode ELSE products.barcode END,
              image_url=CASE WHEN excluded.image_url<>'' THEN excluded.image_url ELSE products.image_url END,
              extra_photos=CASE WHEN excluded.extra_photos<>'' THEN excluded.extra_photos ELSE products.extra_photos END,
              ozon_sku=CASE WHEN excluded.ozon_sku<>'' THEN excluded.ozon_sku ELSE products.ozon_sku END,
              ozon_type=CASE WHEN excluded.ozon_type<>'' THEN excluded.ozon_type ELSE products.ozon_type END,
              ozon_category=CASE WHEN excluded.ozon_category<>'' THEN excluded.ozon_category ELSE products.ozon_category END,
              model=CASE WHEN excluded.model<>'' THEN excluded.model ELSE products.model END,
              hazard_class=CASE WHEN excluded.hazard_class<>'' THEN excluded.hazard_class ELSE products.hazard_class END,
              color=CASE WHEN excluded.color<>'' THEN excluded.color ELSE products.color END,
              material=CASE WHEN excluded.material<>'' THEN excluded.material ELSE products.material END,
              country=CASE WHEN excluded.country<>'' THEN excluded.country ELSE products.country END,
              warranty=CASE WHEN excluded.warranty<>'' THEN excluded.warranty ELSE products.warranty END,
              diameter=CASE WHEN excluded.diameter<>'' THEN excluded.diameter ELSE products.diameter END,
              package_contents=CASE WHEN excluded.package_contents<>'' THEN excluded.package_contents ELSE products.package_contents END,
              rich_content=CASE WHEN excluded.rich_content<>'' THEN excluded.rich_content ELSE products.rich_content END,
              description=CASE WHEN excluded.description<>'' THEN excluded.description ELSE products.description END,
              mark_required=CASE WHEN excluded.mark_required<>'' THEN excluded.mark_required ELSE products.mark_required END,
              group_articles=CASE WHEN excluded.group_articles<>'' THEN excluded.group_articles ELSE products.group_articles END,
              cross_numbers=CASE WHEN excluded.cross_numbers<>'' THEN excluded.cross_numbers ELSE products.cross_numbers END,
              multiplicity=CASE WHEN excluded.multiplicity>0 THEN excluded.multiplicity ELSE products.multiplicity END,
              net_weight=CASE WHEN excluded.net_weight>0 THEN excluded.net_weight ELSE products.net_weight END,
              old_price=CASE WHEN excluded.old_price>0 THEN excluded.old_price ELSE products.old_price END,
              original_article=CASE WHEN excluded.original_article<>'' THEN excluded.original_article ELSE products.original_article END,
              category_type=CASE WHEN excluded.category_type<>'' THEN excluded.category_type ELSE products.category_type END,
              category_src=CASE WHEN excluded.category_src<>'' THEN excluded.category_src ELSE products.category_src END,
              ozon_description_category_id=CASE WHEN excluded.ozon_description_category_id<>'' THEN excluded.ozon_description_category_id ELSE products.ozon_description_category_id END,
              ozon_type_id=CASE WHEN excluded.ozon_type_id<>'' THEN excluded.ozon_type_id ELSE products.ozon_type_id END,
              mark_status=CASE WHEN excluded.mark_status<>'' THEN excluded.mark_status ELSE products.mark_status END,
              mark_code=CASE WHEN excluded.mark_code<>'' THEN excluded.mark_code ELSE products.mark_code END,
              dimensions_str=CASE WHEN excluded.dimensions_str<>'' THEN excluded.dimensions_str ELSE products.dimensions_str END,
              currency=CASE WHEN excluded.currency<>'' THEN excluded.currency ELSE products.currency END,
              ozon_commission=CASE WHEN excluded.ozon_commission<>0 THEN excluded.ozon_commission ELSE products.ozon_commission END,
              ozon_logistics=CASE WHEN excluded.ozon_logistics<>0 THEN excluded.ozon_logistics ELSE products.ozon_logistics END,
              ozon_realfbs_delivery=CASE WHEN excluded.ozon_realfbs_delivery<>0 THEN excluded.ozon_realfbs_delivery ELSE products.ozon_realfbs_delivery END,
              ozon_failed_cost=CASE WHEN excluded.ozon_failed_cost<>0 THEN excluded.ozon_failed_cost ELSE products.ozon_failed_cost END,
              min_stock=CASE WHEN excluded.min_stock<>0 THEN excluded.min_stock ELSE products.min_stock END,
              no_buy_pct=CASE WHEN excluded.no_buy_pct<>0 THEN excluded.no_buy_pct ELSE products.no_buy_pct END,
              fixed_cost=CASE WHEN excluded.fixed_cost<>0 THEN excluded.fixed_cost ELSE products.fixed_cost END,
              source=excluded.source, updated_at=datetime("now")''',
            (art, str(r.get('brand', '')).strip(), str(r.get('name', '')),
             num(r.get('price')), num(r.get('cost')), eff('stock'), eff('sales'), eff('weight'),
             eff('length'), eff('width'), eff('height'), num(r.get('volume')),
             str(r.get('oe_numbers', '')), str(r.get('analog_list', '')), str(r.get('category', '')), str(r.get('tnved', '')),
             str(r.get('applicability', '')),
             str(r.get('barcode', '')), str(r.get('image_url', '')), str(r.get('extra_photos', '')),
             str(r.get('ozon_sku', '')), str(r.get('ozon_type', '')), str(r.get('ozon_category', '')),
             str(r.get('model', '')), str(r.get('hazard_class', '')), str(r.get('color', '')),
             str(r.get('material', '')), str(r.get('country', '')), str(r.get('warranty', '')),
             str(r.get('diameter', '')), str(r.get('package_contents', '')), str(r.get('rich_content', '')),
             str(r.get('description', '')), str(r.get('mark_required', '')), str(r.get('group_articles', '')),
             str(r.get('cross_numbers', '')), num(r.get('multiplicity')), num(r.get('net_weight')),
             num(r.get('old_price')),
             str(r.get('original_article', '')), str(r.get('category_type', '')), str(r.get('category_src', '')), str(r.get('ozon_description_category_id', '')), str(r.get('ozon_type_id', '')), str(r.get('mark_status', '')), str(r.get('mark_code', '')), str(r.get('dimensions_str', '')), str(r.get('currency', '')),
             eff('ozon_commission'), eff('ozon_logistics'), eff('ozon_realfbs_delivery'), eff('ozon_failed_cost'), eff('min_stock'), eff('no_buy_pct'), eff('fixed_cost'), source))
        if 'eff_price' in r:
            conn.execute('UPDATE products SET eff_price=? WHERE article=? AND brand=?',
                         (num(r.get('eff_price')), art, brand))
        if 'visible' in r:
            conn.execute('UPDATE products SET visible=? WHERE article=? AND brand=?',
                         ('0' if str(r.get('visible')).lower() in ('0', 'false', 'нет') else '1', art, brand))
        if 'excluded' in r:
            conn.execute('UPDATE products SET excluded=? WHERE article=? AND brand=?',
                         ('1' if str(r.get('excluded')).lower() in ('1', 'true', 'да') else '0', art, brand))
        for _ymf in ('ym_placement_pct', 'ym_transfer_pct', 'ym_agency_fee', 'ym_boost_pct', 'ym_return_pct', 'ym_found'):
            if _ymf in r:
                conn.execute(f'UPDATE products SET {_ymf}=? WHERE article=? AND brand=?',
                             (num(r.get(_ymf)), art, brand))
        for field in ('dimension_review', 'dimension_context'):
            if field in r:
                value = r[field] if isinstance(r[field], dict) else {}
                conn.execute(f'UPDATE products SET {field}=? WHERE article=? AND brand=?',
                             (json.dumps(value, ensure_ascii=False), art, brand))
        for field in ROW_ECO_OVERRIDES:
            if field in r:
                value = r[field]
                value = None if value is None or str(value).strip() == '' else max(0, num(value))
                conn.execute(f'UPDATE products SET {field}=? WHERE article=? AND brand=?', (value, art, brand))
        # история цен (п.6): только реальные изменения цены/себестоимости
        eff_price = num(r.get('price')) if num(r.get('price')) > 0 else (old['price'] if old else 0)
        eff_cost = num(r.get('cost')) if num(r.get('cost')) > 0 else (old['cost'] if old else 0)
        if history and eff_price > 0 and (not old or abs(old['price'] - eff_price) > 1e-9 or abs(old['cost'] - eff_cost) > 1e-9):
            conn.execute('INSERT INTO price_history(article,brand,price,cost,stock,source,ts) VALUES(?,?,?,?,?,?,datetime("now"))',
                         (art, brand, eff_price, eff_cost, eff('stock'), source))
        n += 1
    if rebuild_fts:
        conn.execute("INSERT INTO products_fts(products_fts) VALUES('rebuild')")
    if commit: conn.commit()
    if rebuild_fts and commit:  # финальный чанк: сжимаем WAL, иначе файл журнала растёт без bound
        try: conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        except Exception: pass
    return n

# ---------------- почта (IMAP) ----------------
def _decode_hdr(v):
    parts = decode_header(v or '')
    return ''.join(p.decode(enc or 'utf-8', errors='replace') if isinstance(p, bytes) else p
                   for p, enc in parts)
def mail_check_once(cfg=None, sec=None):
    cfg = cfg or {}
    sec = sec or secrets()
    host = cfg.get('imap_host') or os.environ.get('UC_IMAP_HOST', '')
    user = cfg.get('imap_user') or os.environ.get('UC_IMAP_USER', '')
    password = sec.get('UC_MAIL_PASSWORD') or os.environ.get('UC_IMAP_PASSWORD', '')
    if not (host and user and password):
        raise RuntimeError('Почта не настроена: нужны UC_IMAP_HOST, UC_IMAP_USER и пароль приложения (UC_MAIL_PASSWORD)')
    days = int(num(cfg.get('mail_days', 14))) or 14
    conn = db()
    rules = [dict(r) for r in conn.execute('SELECT email,file_pattern,profile FROM supplier_rules')]
    imported, seen = 0, 0
    m = imaplib.IMAP4_SSL(host)
    try:
        m.login(user, password)
        m.select('INBOX')
        since = time.strftime('%d-%b-%Y', time.gmtime(time.time() - days * 86400))
        _, data = m.search(None, f'(SINCE {since})')
        ids = data[0].split()[-200:]
        for mid in ids:
            _, msg_data = m.fetch(mid, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            sender = _decode_hdr(msg.get('From', ''))
            subject = _decode_hdr(msg.get('Subject', ''))
            for part in msg.walk():
                fname = _decode_hdr(part.get_filename() or '')
                if not fname or not fname.lower().endswith(('.csv', '.xlsx', '.zip')): continue
                seen += 1
                if rules and not any((not r['email'] or r['email'].lower() in sender.lower()) and
                                     (not r['file_pattern'] or re.search(re.escape(r['file_pattern']).replace(r'\*', '.*'), fname, re.I))
                                     for r in rules):
                    continue
                payload = part.get_payload(decode=True) or b''
                files = files_from_zip(payload) if fname.lower().endswith('.zip') else [(fname, payload)]
                for name, blob in files:
                    try:
                        rows = rows_from_xlsx_bytes(blob) if name.lower().endswith('.xlsx') else rows_from_csv_bytes(blob)
                        n = import_rows(conn, rows, f'mail:{sender} {name}')
                        imported += n
                        conn.execute('INSERT INTO mail_log(ts,subject,sender,filename,rows,status) VALUES(datetime("now"),?,?,?,?,?)',
                                     (subject, sender, name, n, 'ok'))
                        conn.commit()
                    except Exception as e:
                        conn.execute('INSERT INTO mail_log(ts,subject,sender,filename,rows,status) VALUES(datetime("now"),?,?,?,?,?)',
                                     (subject, sender, name, 0, 'err: ' + str(e)[:200]))
                        conn.commit()
    finally:
        try: m.logout()
        except Exception: pass
    log_api(conn, 'mailCheck', host, 'ok', f'вложений {seen}, строк {imported}')
    return {'attachments': seen, 'imported_rows': imported}

# ---------------- полный пересчёт каталога (v12.9.104) ----------------
def _calc_rows_chunk(task):
    rows, st = task
    return [calc_row(r, st) for r in rows]

def _calc_all(rows, st):
    """Пересчёт всех строк: многопроцессно, где можно (аудит п.4).
       calc_row чистый, параллелится чанками; запись результатов — всегда
       одним процессом. Любая проблема с Pool -> тихий откат на 1 процесс.
       В frozen-сборке (PyInstaller) Pool не используем: spawn там ненадёжен."""
    seq = lambda: [calc_row(r, st) for r in rows]
    if len(rows) < 2000 or os.environ.get('UC_ENGINE_NO_PARALLEL') or getattr(sys, 'frozen', False):
        return seq(), False
    try:
        import multiprocessing as mp
        workers = int(os.environ.get('UC_ENGINE_WORKERS') or min(4, os.cpu_count() or 1))
        if workers <= 1: return seq(), False
        step = max(500, -(-len(rows) // (workers * 4)))
        chunks = [rows[i:i + step] for i in range(0, len(rows), step)]
        with mp.Pool(workers) as pool:
            parts = pool.map(_calc_rows_chunk, [(c, st) for c in chunks])
        return [r for part in parts for r in part], True
    except Exception:
        return seq(), False

_ECO_FIELDS = ('name', 'category_type', 'dimension_context', 'price', 'eff_price', 'cost', 'sales', 'weight', 'length', 'width', 'height', 'volume', 'category', 'ym_placement_pct', 'ym_return_pct',
               'multiplicity', 'ozon_commission', 'ozon_logistics', 'ozon_realfbs_delivery',
               'ozon_failed_cost', 'no_buy_pct', 'fixed_cost', 'ym_transfer_pct', 'ym_agency_fee',
               'ym_boost_pct', 'ym_found') + tuple(ROW_ECO_OVERRIDES)

def _eco_hash(row, st):
    import hashlib
    payload = [row.get(k) for k in _ECO_FIELDS]
    raw = json.dumps(['expense-fields-v1', payload, st], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def whatif_catalog(conn, settings, scenario_settings, overrides=None, scenario_inputs=None):
    """Read-only comparison. Never replaces eco_results or product inputs."""
    by_cat = {}
    base_total = scenario_total = 0.0
    included = skipped = 0
    inputs = {_norm_pair(r.get('article'), r.get('brand')): r for r in (scenario_inputs or [])}
    for source in conn.execute('SELECT * FROM products ORDER BY rowid'):
        row = dict(source)
        if str(row.get('excluded', '0')).lower() in ('1', 'true', 'да'): continue
        context = json.loads(row.get('dimension_context') or '{}')
        if context.get('blocked') or context.get('modelReviewRequired') or context.get('noBuyInconsistent') or context.get('missingTariffBlocked'):
            skipped += 1; continue
        scope = str(settings.get('mp_scope', 'OZON')).upper()
        if scope in ('YM', 'ALL') and not num(row.get('ym_found', 1)):
            skipped += 1; continue
        scenario_row = dict(row)
        patch = inputs.get(_norm_pair(row['article'], row['brand']), {})
        for field in ('no_buy_pct', 'ym_return_pct', 'price', 'eff_price', 'sales'):
            if field in patch: scenario_row[field] = patch[field]
        rate_field = 'ym_return_pct' if scope in ('YM', 'ALL') else 'no_buy_pct'
        if num(row.get(rate_field)) >= 100 or num(scenario_row.get(rate_field)) >= 100:
            skipped += 1; continue
        base = calc_row(row, settings)
        scen = calc_row(scenario_row, {**scenario_settings, 'scenario': overrides or {}})
        category = str(row.get('category') or '—')
        bucket = by_cat.setdefault(category, {'base': 0.0, 'scen': 0.0})
        base_total += base['profit']; scenario_total += scen['profit']
        bucket['base'] += base['profit']; bucket['scen'] += scen['profit']
        included += 1
    return {'base': rnd(base_total), 'scen': rnd(scenario_total), 'delta': rnd(scenario_total - base_total),
            'pct': (scenario_total - base_total) / abs(base_total) * 100 if base_total else None,
            'included': included, 'skipped': skipped, 'byCat': by_cat}

def recalc_catalog(conn, st, force=False):
    """Инкрементальный пересчёт (v12.9.119): строка пересчитывается только
       если изменились её расчётные входы или настройки экономики (хэш в
       eco_results.inputs_hash). force=True — полный пересчёт как раньше.
       Итоги ответа считаются по всей таблице результатов, семантика та же."""
    rows = [dict(r) for r in conn.execute('SELECT * FROM products').fetchall()]
    rows = [r for r in rows if str(r.get('excluded', '0')).lower() not in ('1', 'true', 'да')]  # как пайплайн браузера
    if str(st.get('mp_scope') or '').upper() in ('YM', 'ALL'):
        # браузер: нет совместимого тарифа ЯМ — экономика строки не считается
        rows = [r for r in rows if num(r.get('ym_found', 1)) > 0]
    old = {(r['article'], r['brand']): r['inputs_hash'] for r in
           conn.execute('SELECT article,brand,inputs_hash FROM eco_results')}
    todo, hashes = [], {}
    for row in rows:
        h = _eco_hash(row, st)
        hashes[(row['article'], row['brand'])] = h
        if force or old.get((row['article'], row['brand'])) != h: todo.append(row)
    results, parallel = _calc_all(todo, st)
    conn.executemany('''INSERT INTO eco_results(article,brand,total,profit,margin,roi,break_even,target,computed_at,inputs_hash,fields_json)
        VALUES(?,?,?,?,?,?,?,?,datetime("now"),?,?)
        ON CONFLICT(article,brand) DO UPDATE SET total=excluded.total, profit=excluded.profit,
          margin=excluded.margin, roi=excluded.roi, break_even=excluded.break_even,
          target=excluded.target, computed_at=excluded.computed_at, inputs_hash=excluded.inputs_hash, fields_json=excluded.fields_json''',
        [(res['article'], row['brand'], res['total'], res['profit'], res['margin'],
          res['roi'], res['break_even'], res['target'], hashes[(row['article'], row['brand'])], json.dumps(res.get('fields', {}), ensure_ascii=False))
         for row, res in zip(todo, results)])
    alive = set(hashes)
    for key in old:
        if key not in alive: conn.execute('DELETE FROM eco_results WHERE article=? AND brand=?', key)
    conn.commit()
    agg = conn.execute('SELECT COUNT(*) n, SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END) prof, AVG(profit) avgp FROM eco_results').fetchone()
    n = agg['n'] or 0
    log_api(conn, 'recalcCatalog', 'sqlite', 'ok', f'{len(todo)} из {len(rows)} SKU')
    return {'recalculated': len(todo), 'skipped': len(rows) - len(todo), 'total_sku': len(rows),
            'profitable': agg['prof'] or 0,
            'avg_profit': rnd(agg['avgp'] or 0, 2) if n else 0, 'parallel': parallel}

# ---------------- импорт файла целиком + обогащение OE (v12.9.105) ----------------
def sync_catalog_snapshot(conn, body):
    """Stage normalized inputs and publish an exact snapshot atomically.
    Supplier import_rows semantics remain unchanged. Never mutate app_catalog.
    """
    import hashlib, secrets
    def fingerprint():
        h=hashlib.sha256()
        for row in conn.execute('SELECT * FROM products ORDER BY article,brand'):
            h.update(json.dumps(tuple(row),ensure_ascii=False,allow_nan=False).encode())
        return h.hexdigest()
    conn.execute('CREATE TABLE IF NOT EXISTS sync_upload(token TEXT PRIMARY KEY,base TEXT,total INTEGER,source TEXT,created REAL)')
    conn.execute('CREATE TABLE IF NOT EXISTS sync_parts(token TEXT,part INTEGER,data TEXT,PRIMARY KEY(token,part))')
    action=body.get('action')
    if action=='begin':
        total=body.get('total')
        if type(total) is not int or total<0:raise ValueError('Неверное число строк снимка')
        token=secrets.token_hex(24)
        import time
        with conn:
            conn.execute('DELETE FROM sync_parts WHERE token IN (SELECT token FROM sync_upload WHERE created<?)',(time.time()-86400,))
            conn.execute('DELETE FROM sync_upload WHERE created<?',(time.time()-86400,))
            conn.execute('INSERT INTO sync_upload VALUES(?,?,?,?,?)',(token,fingerprint(),total,str(body.get('source') or 'app-sync'),time.time()))
        return {'token':token}
    token=body.get('token')
    upload=conn.execute('SELECT base,total,source FROM sync_upload WHERE token=?',(token,)).fetchone()
    if not upload:raise ValueError('Снимок синхронизации не найден')
    if action=='chunk':
        part=body.get('part');rows=body.get('rows')
        if type(part) is not int or part<0 or not isinstance(rows,list) or not 0<len(rows)<=5000:raise ValueError('Неверная часть снимка')
        for row in rows:
            if not isinstance(row,dict) or not isinstance(row.get('article'),str) or not row['article'].strip():raise ValueError('Неверный SKU снимка')
            if not isinstance(row.get('brand',''),str):raise ValueError('Неверный бренд снимка')
        with conn:conn.execute('INSERT OR REPLACE INTO sync_parts VALUES(?,?,?)',(token,part,json.dumps(rows,ensure_ascii=False,allow_nan=False)))
        return {'saved':len(rows)}
    if action!='commit':raise ValueError('Неизвестная операция снимка')
    # BEGIN IMMEDIATE protects the fingerprint and publication against writers.
    conn.execute('BEGIN IMMEDIATE')
    try:
        if fingerprint()!=upload[0]:raise ValueError('Каталог движка изменился во время синхронизации; повторите операцию')
        parts=conn.execute('SELECT part FROM sync_parts WHERE token=? ORDER BY part',(token,)).fetchall()
        if [r[0] for r in parts]!=list(range(len(parts))):raise ValueError('Пропущена часть снимка')
        conn.execute('DELETE FROM products')
        conn.execute('DELETE FROM eco_results')
        count=0;seen=set()
        for part, in parts:
            rows=json.loads(conn.execute('SELECT data FROM sync_parts WHERE token=? AND part=?',(token,part)).fetchone()[0])
            for row in rows:
                key=(row['article'].strip(),row.get('brand','').strip())
                if key in seen:raise ValueError('Повторный ключ SKU в снимке')
                seen.add(key)
            count+=import_rows(conn,rows,upload[2],rebuild_fts=False,commit=False,history=False)
        if count!=upload[1]:raise ValueError('Неполный снимок каталога')
        conn.execute("INSERT INTO products_fts(products_fts) VALUES('rebuild')")
        conn.execute('DELETE FROM sync_parts WHERE token=?',(token,))
        conn.execute('DELETE FROM sync_upload WHERE token=?',(token,))
        conn.commit()
    except Exception:
        conn.rollback();raise
    return {'total':count}

def import_file_bytes(conn, filename, data, enrich_only=False, mapping=None):
    """Файл разбирает движок, а не браузер: CSV/XLSX/ZIP -> строки -> каталог.
       enrich_only (v12.9.145): файл не первый (не прайс) — только обогащение
       уже существующих SKU, новые строки не вставляются."""
    name = os.path.basename(str(filename or 'file'))
    files = files_from_zip(data) if name.lower().endswith('.zip') else [(name, data)]
    if not files: raise ValueError('В архиве нет CSV/XLSX файлов')
    ensure_free_space(sum(len(b) for _, b in files))  # v12.9.144: отказ до записи, а не в середине
    total = 0; skipped = 0; oe_matched = 0
    existing = None; oe_to_key = {}
    if enrich_only:
        existing = {}
        for a,b in conn.execute('SELECT article,brand FROM products'):
            existing.setdefault(_norm_pair(a,b),[]).append((a,b))
        for _a, _b, _oe in conn.execute('SELECT article,brand,oe_numbers FROM products'):
            for _c in _oe_codes(_oe): oe_to_key.setdefault(_c, set()).add((_a, _b))
    try:
        for fname, blob in files:
            rows = rows_from_xlsx_bytes(blob,mapping) if fname.lower().endswith('.xlsx') else rows_from_csv_bytes(blob,mapping)
            if existing is not None:
                kept = []
                for r in rows:
                    key=(str(r.get('article','')).strip(),str(r.get('brand','')).strip())
                    matches=existing.get(_norm_pair(*key),[])
                    if key in matches or len(matches)==1:
                        a,b=key if key in matches else matches[0]
                        kept.append(dict(r,article=a,brand=b));continue
                    if matches:
                        skipped+=1;continue  # ambiguous normalized identities must never insert a new SKU
                    # как findByOe браузера: уникальный OE -> та же карточка прайса
                    _keys = set()
                    for _c in _oe_codes(r.get('oe_numbers', '')): _keys |= oe_to_key.get(_c, set())
                    if len(_keys) == 1:
                        _ka, _kb = next(iter(_keys))
                        r = dict(r); r['article'], r['brand'] = _ka, _kb; oe_matched += 1; kept.append(r)
                    elif str(r.get('article', '')).strip(): skipped += 1
                rows = kept
            total += import_rows(conn, rows, f'file:{name}', rebuild_fts=False, commit=False)
        conn.execute("INSERT INTO products_fts(products_fts) VALUES('rebuild')")
        conn.commit()
    except Exception:
        try: conn.rollback()  # не оставлять полуприменённый импорт
        except Exception: pass
        raise
    log_api(conn, 'importFile', name, 'ok', f'строк {total}, вне прайса пропущено {skipped}')
    return {'file': name, 'imported': total, 'skipped_outside_price': skipped, 'enrich_only': bool(enrich_only), 'oe_matched': oe_matched}

def _norm_key_part(v):
    """Как normArticle в приложении: верхний регистр, только буквы/цифры."""
    return re.sub(r'[^A-Z0-9А-ЯЁ]', '', str(v or '').upper())

def _norm_pair(article, brand):
    return _norm_key_part(article) + '|' + _norm_key_part(brand)

def _oe_codes(raw):
    out = []
    for part in re.split(r'[,;/|\s]+', str(raw or '').upper()):
        code = re.sub(r'[^A-Z0-9А-ЯЁ]', '', part)
        if code: out.append(code)
    return out

def enrich_oe(conn):
    """Обогащение по OE-графу в SQL: транзитивные группы (union-find по oe_links),
       заполняются только пустые поля; артикулы группы дописываются в аналоги."""
    conn.execute('DELETE FROM oe_links')
    prods = conn.execute('SELECT article,brand,name,applicability,weight,length,width,height,oe_numbers,analog_list FROM products').fetchall()
    by_key = {(r['article'], r['brand']): dict(r) for r in prods}
    oe_to_keys = {}
    for r in prods:
        for oe in _oe_codes(r['oe_numbers']):
            conn.execute('INSERT OR IGNORE INTO oe_links(oe,article,brand) VALUES(?,?,?)', (oe, r['article'], r['brand']))
            oe_to_keys.setdefault(oe, set()).add((r['article'], r['brand']))
    conn.commit()
    parent = {k: k for k in by_key}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: parent[rb] = ra
    for keys in oe_to_keys.values():
        keys = list(keys)
        for k in keys[1:]: union(keys[0], k)
    groups = {}
    for k in by_key: groups.setdefault(find(k), []).append(k)
    filled = {'name': 0, 'applicability': 0, 'dims': 0, 'analog_list': 0}
    multi_groups = 0
    for members in groups.values():
        if len(members) < 2: continue
        multi_groups += 1
        rows = [by_key[k] for k in members]
        def dims_of(r): return (num(r['length']), num(r['width']), num(r['height']), num(r['weight']))
        complete = [r for r in rows if all(v > 0 for v in dims_of(r))]
        names = [r['name'] for r in rows if str(r['name'] or '').strip()]
        best_name = max(set(names), key=names.count) if names else ''
        for r in rows:
            updates = {}
            if not str(r['name'] or '').strip() and best_name:
                updates['name'] = best_name; filled['name'] += 1
            _apps = [x['applicability'] for x in rows if str(x['applicability'] or '').strip()]
            if not str(r['applicability'] or '').strip() and _apps:
                updates['applicability'] = max(set(_apps), key=_apps.count); filled['applicability'] += 1
            if complete and not all(v > 0 for v in dims_of(r)):
                same_art = [d for d in complete if d['article'] == r['article']]
                donor = same_art[0] if same_art else complete[0]
                d = dims_of(donor)
                cur = dims_of(r)
                # только пустые компоненты: уже заполненные значения не перетираем
                for i, f in enumerate(('length', 'width', 'height', 'weight')):
                    if not cur[i] > 0 and d[i] > 0: updates[f] = d[i]
                if updates: filled['dims'] += 1
            others = sorted({m[0] for m in members if m[0] != r['article']})
            if others:
                cur = {x.strip() for x in str(r['analog_list'] or '').split(',') if x.strip()}
                merged = sorted(cur | set(others))
                if merged != sorted(cur):
                    updates['analog_list'] = ', '.join(merged); filled['analog_list'] += 1
            if updates:
                sets = ', '.join(f'{k}=?' for k in updates)
                conn.execute(f'UPDATE products SET {sets} WHERE article=? AND brand=?',
                             (*updates.values(), r['article'], r['brand']))
    conn.commit()
    log_api(conn, 'enrichOe', 'sqlite', 'ok', f'групп {multi_groups}, заполнено {filled}')
    return {'groups': multi_groups, 'filled': filled,
            'oe_links': conn.execute('SELECT COUNT(*) c FROM oe_links').fetchone()['c']}

# ---------------- полное обогащение (Каталог V на движке, v12.9.110) ----------------
def import_donors(conn, rows, source):
    """Реестр доноров (аналог HVC.parts): записи справочных файлов, по ключу
       Артикул+Бренд, несколько источников на ключ допустимы."""
    n = 0
    for r in rows:
        art = str(r.get('article', '')).strip()
        if not art: continue
        conn.execute('''INSERT INTO donors(article,brand,source,name,category,tnved,applicability,warranty,country,
            weight,length,width,height,oe_numbers,barcode,image_url,multiplicity) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(article,brand,source) DO UPDATE SET
              name=CASE WHEN excluded.name<>'' THEN excluded.name ELSE donors.name END,
              category=CASE WHEN excluded.category<>'' THEN excluded.category ELSE donors.category END,
              tnved=CASE WHEN excluded.tnved<>'' THEN excluded.tnved ELSE donors.tnved END,
              applicability=CASE WHEN excluded.applicability<>'' THEN excluded.applicability ELSE donors.applicability END,
              warranty=CASE WHEN excluded.warranty<>'' THEN excluded.warranty ELSE donors.warranty END,
              country=CASE WHEN excluded.country<>'' THEN excluded.country ELSE donors.country END,
              weight=CASE WHEN excluded.weight>0 THEN excluded.weight ELSE donors.weight END,
              length=CASE WHEN excluded.length>0 THEN excluded.length ELSE donors.length END,
              width=CASE WHEN excluded.width>0 THEN excluded.width ELSE donors.width END,
              height=CASE WHEN excluded.height>0 THEN excluded.height ELSE donors.height END,
              oe_numbers=CASE WHEN excluded.oe_numbers<>'' THEN excluded.oe_numbers ELSE donors.oe_numbers END,
              barcode=CASE WHEN excluded.barcode<>'' THEN excluded.barcode ELSE donors.barcode END,
              image_url=CASE WHEN excluded.image_url<>'' THEN excluded.image_url ELSE donors.image_url END,
              multiplicity=CASE WHEN excluded.multiplicity>0 THEN excluded.multiplicity ELSE donors.multiplicity END''',
            (art, str(r.get('brand', '')).strip(), source, str(r.get('name', '')), str(r.get('category', '')),
             str(r.get('tnved', '')), str(r.get('applicability', '')), str(r.get('warranty', '')), str(r.get('country', '')),
             num(r.get('weight')), num(r.get('length')),
             num(r.get('width')), num(r.get('height')), str(r.get('oe_numbers', '')),
             str(r.get('barcode', '')), str(r.get('image_url', '')), num(r.get('multiplicity'))))
        n += 1
    conn.commit()
    return n

def _dims_of(r):
    return (num(r['length']), num(r['width']), num(r['height']), num(r['weight']))

def _dimension_candidate_allowed(product, dims, policy):
    """Numeric/category checks used by AnomalyDetector for a proposed tuple.
    Review and import blocks are supplied separately by the client snapshot.
    """
    l, w, h, weight = dims
    if not all(math.isfinite(x) and x > 0 for x in dims): return False
    key = lambda x: re.sub(r'\s+', ' ', str(x or '').strip().lower().replace('ё', 'е'))
    limit = next((x for x in policy.get('limits', []) if key(x.get('category')) == key(product.get('category'))),
                 {'maxW': 400, 'maxL': 300, 'maxVol': 1000})
    computed = l * w * h / 1000
    raw_net = product.get('net_weight')
    if isinstance(raw_net, bool): return False
    if raw_net is not None and raw_net != '':
        if isinstance(raw_net, (int, float)):
            if not math.isfinite(raw_net): return False
        elif not re.fullmatch(r'[+-]?(?:(?:\d{1,3}(?:[\s\u00a0\u202f]\d{3})+)|\d+)(?:[.,]\d+)?|[+-]?[.,]\d+', str(raw_net).strip()):
            return False
    net = num(raw_net)
    if net < 0 or net > weight + max(1e-9, weight * 1e-9): return False
    if not math.isfinite(computed) or weight / computed > 30: return False
    if weight > num(limit.get('maxW')) or max(l, w, h) > num(limit.get('maxL')): return False
    context = json.loads(product.get('dimension_context') or '{}')
    explicit = policy.get('explicit_volume', {}).get(_norm_pair(product['article'], product['brand']), context.get('explicitVolume', False))
    sources = context.get('sources') or {}
    if (weight, l, w, h) == (0.5, 15, 10, 5) and sources.get('Прайс-лист') and not any(sources.get(k) for k in ('weight', 'Вес, кг', 'Вес в упаковке, кг')):
        return False
    vol = num(product.get('volume')) if explicit else computed
    if vol < 0 or vol > num(limit.get('maxVol')): return False
    if explicit and vol > 0 and max(vol / computed, computed / vol) > 4: return False
    return True

def match_condition(row, field, op, value):
    v = row.get(field)
    if op == 'empty': return v is None or v == ''
    def js_string(x):return '' if x is None else formula_string(x)
    t = js_string(value).lower().strip(JS_SPACE)
    if not t or v is None or v == '': return False
    text = js_string(v).lower()
    if op == 'contains': return t in text
    if op == '!contains': return t not in text
    if op == 'eq': return text == t
    if op == 'ne': return text != t
    if op == 'startsWith': return text.startswith(t)
    if op == 'gt': return export_number(v) > export_number(t)
    if op == 'lt': return export_number(v) < export_number(t)
    if op == 'regex':
        return js_regex_search(t, js_string(v) if formula_truth(v) else '')
    return False


def _atomic_enrichment(fn):
    """Rollback a failed batch without committing/rolling back caller work."""
    @wraps(fn)
    def run(conn,*args,**kwargs):
        conn.execute('SAVEPOINT enrichment_batch')
        try:
            result=fn(conn,*args,**kwargs)
            conn.execute('RELEASE enrichment_batch')
            return result
        except Exception:
            conn.execute('ROLLBACK TO enrichment_batch')
            conn.execute('RELEASE enrichment_batch')
            raise
    return run


@_atomic_enrichment
def check_mark_status_rows(conn, rows, settings, special_values=None):
    if special_values is not None:
        decoded=decode_special({'rows':rows,'settings':settings},special_values)
        rows,settings=decoded['rows'],decoded['settings']
    conn.execute('CREATE TABLE IF NOT EXISTS mark_status_settings(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
    clean_settings,setting_types=encode_special(settings)
    conn.execute('INSERT OR REPLACE INTO mark_status_settings VALUES(1,?)',(json.dumps(clean_settings,ensure_ascii=False,allow_nan=False),))
    conn.execute('CREATE TABLE IF NOT EXISTS mark_status_setting_types(id INTEGER PRIMARY KEY CHECK(id=1),data TEXT NOT NULL)')
    conn.execute('INSERT OR REPLACE INTO mark_status_setting_types VALUES(1,?)',(json.dumps(setting_types,ensure_ascii=False,allow_nan=False),))
    result=[]; unknown=[]
    for source in rows:
        output,outcome=apply_mark_status(source,settings)
        fields={k:output[k] for k in ('markCompliant','visible','visibleReason','policyAction','policyReason') if k in output}
        status=source.get('markStatus')
        unknown_status=formula_string(status if formula_truth(status) else '').strip(JS_SPACE)
        if outcome['kind']=='unknown' and unknown_status not in unknown:
            unknown.append(unknown_status)
        if output.get('visible') is False:
            conn.execute("UPDATE products SET visible='0',visible_reason=? WHERE article=? AND brand=?",
                         (output.get('visibleReason',''),source.get('article',''),source.get('brand','')))
        fields,types=encode_special(fields)
        result.append({'article':source.get('article'),'brand':source.get('brand',''),'fields':fields,'special_values':types,'result':outcome})
    return {'rows':result,'unknown':unknown}

def _persist_product_context(conn, article, brand, updates, has_context):
    """Keep the product snapshot consumed by later HVC passes up to date."""
    if not has_context:return
    saved=conn.execute('SELECT dimension_context FROM products WHERE article=? AND brand=?',(article,brand)).fetchone()
    if saved is None:return
    try:context=json.loads(saved[0] or '{}')
    except (ValueError,TypeError):context={}
    if not isinstance(context,dict):context={}
    context.update(updates)
    conn.execute('UPDATE products SET dimension_context=? WHERE article=? AND brand=?',
                 (json.dumps(context,ensure_ascii=False),article,brand))


def _persist_enrichment_sources(conn,article,brand,fields,has_context):
    if '_sources' in fields:_persist_product_context(conn,article,brand,{'sources':fields['_sources']},has_context)


@_atomic_enrichment
def enrich_category_tnved(conn, rows, reference, enabled=True):
    conn.execute('CREATE TABLE IF NOT EXISTS category_tnved_reference(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
    if reference is not None:
        conn.execute('INSERT OR REPLACE INTO category_tnved_reference VALUES(1,?)',(json.dumps(reference,ensure_ascii=False),))
    saved=conn.execute('SELECT data FROM category_tnved_reference WHERE id=1').fetchone()
    if not saved: raise ValueError('Нет справочника категория/вид/ТН ВЭД')
    ref=json.loads(saved[0]); model=CategoryTnved(ref.get('rows',[]),ref.get('revision',''),ref.get('source','Категории12131.csv'))
    has_context=any(c[1]=='dimension_context' for c in conn.execute('PRAGMA table_info(products)'))
    result=[]
    timestamp=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    for source in rows:
        output,status=model.apply(source,enabled,timestamp)
        fields={k:output[k] for k in ('tnved','_categoryTnvedAuto','_sources') if k in output}
        removed=[k for k in ('tnved','_categoryTnvedAuto') if k not in output]
        conn.execute('UPDATE products SET tnved=? WHERE article=? AND brand=?',(output.get('tnved',''),source.get('article',''),source.get('brand','')))
        _persist_enrichment_sources(conn,source.get('article',''),source.get('brand',''),fields,has_context)
        result.append({'article':source.get('article'),'brand':source.get('brand',''),'fields':fields,'removed':removed,'result':status})
    return {'rows':result}

def dimension_oe_operation(conn, snapshot, operation='find', token=None, selected=None):
    import hashlib,secrets,datetime
    from dimension_oe_search import OeSearch
    from dimension_oe_apply import apply_choices
    from dimension_quarantine import compact
    from enrichment_formula import truth
    if operation not in ('find','apply'):raise ValueError('Неверная операция OE')
    rows=snapshot['rows'];automatic=snapshot.get('automatic') is True
    found=snapshot.get('found') or []
    indices=[f['index'] for f in found]
    if any(isinstance(i,bool) or not isinstance(i,int) or i<0 or i>=len(rows) for i in indices) or len(indices)!=len(set(indices)):
        raise ValueError('Неверные индексы карантина OE')
    marked=[f['index'] for f in found if f.get('selected')]
    valid=lambda i:rows[i].get('dimensionAnomalyBlocked') and not rows[i].get('excluded')
    all_targets=[i for i in indices if valid(i)]
    pending=sum(truth(rows[i].get('_dimensionOeReview')) for i in all_targets) if automatic else 0
    targets=[i for i in all_targets if not truth(rows[i].get('_dimensionOeReview'))] if automatic else [i for i in (marked if marked else indices) if valid(i)]
    fingerprint=hashlib.sha256(json.dumps(snapshot,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    conn.execute('CREATE TABLE IF NOT EXISTS dimension_oe_preview(token TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,created REAL NOT NULL)')
    if operation=='apply':
        old=conn.execute('SELECT fingerprint,created FROM dimension_oe_preview WHERE token=?',(token,)).fetchone()
        if old is None or old[0]!=fingerprint or time.time()-old[1]>3600:raise ValueError('Предложения устарели; повторите поиск по OE')
    search=OeSearch(rows,snapshot.get('reference') or {},snapshot.get('limits') or [],snapshot.get('mode','auto'),snapshot.get('labels'))
    proposals=search.find(targets,automatic)
    summary={'checked':len(proposals),'noChoice':sum(x['choice'] is None for x in proposals),'pending':pending,
        'noOe':sum(x['choice'] is None and x['status'].startswith('Нет OE') for x in proposals),
        'conflicts':sum(x['choice'] is None and x['status'].startswith(('Конфликт','Противореч','Слишком много')) for x in proposals),
        'smaller':sum(x['choice'] is not None and x['status'].startswith('Выбраны меньшие') for x in proposals),'errors':0,'changed':0}
    summary['other']=summary['noChoice']-summary['noOe']-summary['conflicts']
    if operation=='find':
        token=secrets.token_urlsafe(24)
        with conn:
            conn.execute('DELETE FROM dimension_oe_preview WHERE created<?',(time.time()-3600,))
            conn.execute('INSERT INTO dimension_oe_preview VALUES(?,?,?)',(token,fingerprint,time.time()))
        return {'token':token,'preview':proposals,'summary':summary}
    chosen=selected or []
    updates=apply_choices(search,proposals,chosen,automatic,datetime.datetime.now(datetime.timezone.utc).isoformat())
    keys=('weight','length','width','height','volume','_volumeExplicit','_sources','_dimensionOeReview','dimensionAnomalyAck')
    results=[{'targetIndex':u['targetIndex'],'article':u['row'].get('article',''),'brand':u['row'].get('brand',''),
              'fields':{k:u['row'][k] for k in keys if k in u['row']},'removed':[k for k in keys if k not in u['row']],'log':u['log']} for u in updates]
    results=json.loads(compact(results))
    with conn:
        conn.execute('CREATE TABLE IF NOT EXISTS dimension_oe_state(article TEXT,brand TEXT,data TEXT NOT NULL,PRIMARY KEY(article,brand))')
        for r in results:
            conn.execute('INSERT OR REPLACE INTO dimension_oe_state VALUES(?,?,?)',(r['article'],r['brand'],json.dumps(r['fields'],ensure_ascii=False)))
            f=r['fields']
            conn.execute('UPDATE products SET weight=?,length=?,width=?,height=?,volume=? WHERE article=? AND brand=?',
                tuple(f.get(k,0) for k in ('weight','length','width','height','volume'))+(r['article'],r['brand']))
        conn.execute('DELETE FROM dimension_oe_preview WHERE token=?',(token,))
    summary['changed']=len(results)
    return {'rows':results,'summary':summary}

def fix_dimension_units(conn, items, limits, mode='auto', approved=False, labels=None, timestamp=None):
    import datetime
    from dimension_quarantine import DimensionQuarantine, compact
    model=DimensionQuarantine(limits,mode)
    at=timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat()
    keys=('weight','length','width','height','volume','_volumeExplicit','_sources','_dimensionOeReview','dimensionAnomalyAck')
    results=[]
    for item in items:
        p=item['row']
        output,verdict=model.fix_units(p,at,item.get('signature'),approved,labels)
        results.append({'article':p.get('article',''),'brand':p.get('brand',''),
            'fields':json.loads(compact({k:output[k] for k in keys if k in output})),
            'removed':[k for k in keys if k not in output],'result':json.loads(compact(verdict))})
    if approved:
        with conn:
            conn.execute('CREATE TABLE IF NOT EXISTS dimension_unit_fix_state(article TEXT,brand TEXT,data TEXT NOT NULL,PRIMARY KEY(article,brand))')
            for r in results:
                if r['result']['status']!='applied':continue
                conn.execute('INSERT OR REPLACE INTO dimension_unit_fix_state VALUES(?,?,?)',(r['article'],r['brand'],json.dumps(r['fields'],ensure_ascii=False)))
                f=r['fields']
                conn.execute('UPDATE products SET weight=?,length=?,width=?,height=?,volume=? WHERE article=? AND brand=?',
                    tuple(f.get(k,0) for k in ('weight','length','width','height','volume'))+(r['article'],r['brand']))
    return {'rows':results}

def confirm_dimension_row(conn, row, limits, mode='auto', approved=False, expected_signature=None, timestamp=None):
    import datetime
    from dimension_quarantine import DimensionQuarantine, FLAGS, compact
    if approved and not isinstance(expected_signature,str):
        raise ValueError('Не передана подпись подтверждаемой аномалии')
    model=DimensionQuarantine(limits,mode)
    at=timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat()
    output,result=model.confirm(row,at,approved,expected_signature)
    keys=FLAGS+('_volumeExplicit','_dimensionOeReview')
    fields=json.loads(compact({k:output[k] for k in keys if k in output}))
    with conn:
        conn.execute('CREATE TABLE IF NOT EXISTS dimension_quarantine_state(article TEXT,brand TEXT,data TEXT NOT NULL,PRIMARY KEY(article,brand))')
        conn.execute('INSERT OR REPLACE INTO dimension_quarantine_state VALUES(?,?,?)',(row.get('article',''),row.get('brand',''),json.dumps(fields,ensure_ascii=False)))
    return {'article':row.get('article',''),'brand':row.get('brand',''),'fields':fields,
            'removed':[k for k in keys if k not in output],'result':json.loads(compact(result))}

def quarantine_dimension_rows(conn, rows, limits, mode='auto', timestamp=None):
    import datetime
    from dimension_quarantine import DimensionQuarantine, FLAGS, compact
    model=DimensionQuarantine(limits,mode)
    timestamp=timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat()
    has_context=any(c[1]=='dimension_context' for c in conn.execute('PRAGMA table_info(products)'))
    results=[]
    keys=FLAGS+('_volumeExplicit',)
    for p in rows:
        output=model.apply(p,timestamp)
        results.append({'article':p.get('article',''),'brand':p.get('brand',''),
            'fields':json.loads(compact({k:output[k] for k in keys if k in output})),'removed':[k for k in keys if k not in output]})
    with conn:
        conn.execute('CREATE TABLE IF NOT EXISTS dimension_quarantine_settings(id INTEGER PRIMARY KEY CHECK(id=1),data TEXT NOT NULL)')
        conn.execute('INSERT OR REPLACE INTO dimension_quarantine_settings VALUES(1,?)',(json.dumps({'limits':limits,'oe_mode':mode},ensure_ascii=False),))
        conn.execute('CREATE TABLE IF NOT EXISTS dimension_quarantine_state(article TEXT,brand TEXT,data TEXT NOT NULL,PRIMARY KEY(article,brand))')
        for r in results:
            updates={'blocked':bool(r['fields'].get('dimensionAnomalyBlocked'))}
            if '_volumeExplicit' in r['fields']:updates['explicitVolume']=r['fields']['_volumeExplicit']
            _persist_product_context(conn,r['article'],r['brand'],updates,has_context)
            conn.execute('INSERT OR REPLACE INTO dimension_quarantine_state VALUES(?,?,?)',(r['article'],r['brand'],json.dumps(r['fields'],ensure_ascii=False)))
    return {'rows':results}

def apply_product_policies(conn, rows, rules):
    from product_policies import apply_policies
    keys=('excluded','deletePending','policyAction','policyReason','visible','visibleReason')
    results=[]
    for p in rows:
        output=apply_policies(p,rules,match_condition,export_number)
        results.append({'article':p.get('article',''),'brand':p.get('brand',''),
                        'fields':{k:output[k] for k in keys if k in output}})
    with conn:
        conn.execute('CREATE TABLE IF NOT EXISTS product_policy_rules(id INTEGER PRIMARY KEY CHECK(id=1),data TEXT NOT NULL)')
        conn.execute('INSERT OR REPLACE INTO product_policy_rules VALUES(1,?)',(json.dumps(rules,ensure_ascii=False),))
        conn.execute('CREATE TABLE IF NOT EXISTS product_policy_state(article TEXT,brand TEXT,data TEXT NOT NULL,PRIMARY KEY(article,brand))')
        for r in results:
            conn.execute('INSERT OR REPLACE INTO product_policy_state VALUES(?,?,?)',(r['article'],r['brand'],json.dumps(r['fields'],ensure_ascii=False)))
    return {'rows':results}

# One active compiled Ozon reference; explicit release and SQLite-backed reload.
# Holding the lock through apply prevents shared classifier caches racing.
import threading
_OZON_REFERENCE_LOCK=threading.RLock()
_OZON_REFERENCE_CACHE={}

def ozon_reference_upload(conn,body):
    import secrets
    conn.execute('CREATE TABLE IF NOT EXISTS ozon_ref_upload(id TEXT PRIMARY KEY,total INTEGER NOT NULL,sealed INTEGER NOT NULL,created REAL NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS ozon_ref_chunks(id TEXT NOT NULL,part INTEGER NOT NULL,data TEXT NOT NULL,n INTEGER NOT NULL,PRIMARY KEY(id,part))')
    action=body.get('action')
    if action=='begin':
        total=body.get('total')
        if type(total) is not int or total<=0:raise ValueError('Неверный размер справочника Ozon')
        token='ozon:'+secrets.token_hex(24)
        with conn:
            conn.execute('DELETE FROM ozon_ref_chunks WHERE id IN (SELECT id FROM ozon_ref_upload WHERE created<?)',(time.time()-86400,))
            conn.execute('DELETE FROM ozon_ref_upload WHERE created<?',(time.time()-86400,))
            conn.execute('INSERT INTO ozon_ref_upload VALUES(?,?,0,?)',(token,total,time.time()))
        return {'token':token}
    token=body.get('token')
    # Use the same lock order as enrichment: resource lock, then SQLite write.
    with _OZON_REFERENCE_LOCK:
        with conn:
            conn.execute('UPDATE ozon_ref_upload SET sealed=sealed WHERE id=?',(token,))
            head=conn.execute('SELECT total,sealed FROM ozon_ref_upload WHERE id=?',(token,)).fetchone()
            if not head:raise ValueError('Справочник Ozon не найден')
            if action=='release':
                conn.execute('DELETE FROM ozon_ref_chunks WHERE id=?',(token,))
                conn.execute('DELETE FROM ozon_ref_upload WHERE id=?',(token,))
                _OZON_REFERENCE_CACHE.pop(token,None)
                return {'released':True}
            if action=='chunk':
                part=body.get('part');data=body.get('data')
                if head[1] or type(part) is not int or part<0 or not isinstance(data,str) or not data or len(data)>300000:raise ValueError('Неверная часть справочника Ozon')
                count=len(data.encode('utf-16-le'))//2
                conn.execute('INSERT OR REPLACE INTO ozon_ref_chunks VALUES(?,?,?,?)',(token,part,data,count))
                return {'saved':count}
            if action!='commit':raise ValueError('Неизвестная операция справочника Ozon')
            parts=conn.execute('SELECT part,n FROM ozon_ref_chunks WHERE id=? ORDER BY part',(token,)).fetchall()
            if [p[0] for p in parts]!=list(range(len(parts))) or sum(p[1] for p in parts)!=head[0]:raise ValueError('Неполный справочник Ozon')
            reference=json.loads(''.join(r[0] for r in conn.execute('SELECT data FROM ozon_ref_chunks WHERE id=? ORDER BY part',(token,))))
            if not isinstance(reference,dict) or not isinstance(reference.get('pairs'),list) or not isinstance(reference.get('category_rows'),list) or not isinstance(reference.get('identity'),dict) or not isinstance(reference['identity'].get('rows'),list):raise ValueError('Неверный справочник Ozon/идентичностей')
            conn.execute('UPDATE ozon_ref_upload SET sealed=1 WHERE id=?',(token,))
        _OZON_REFERENCE_CACHE.clear()
        _OZON_REFERENCE_CACHE[token]=(reference,None)
        return {'reference_id':token}

def enrich_ozon_preferred(conn,rows,reference=None,enabled=True,force=False,force_name=False,reference_id=None):
    if reference_id is None:return _apply_ozon_preferred(conn,rows,reference,enabled,force,force_name)
    from ozon_preferred import OzonPreferred
    from ozon_identity import IdentityGuard
    with _OZON_REFERENCE_LOCK:
        head=conn.execute('SELECT sealed FROM ozon_ref_upload WHERE id=?',(reference_id,)).fetchone()
        if not head or not head[0]:raise ValueError('Справочник Ozon не зафиксирован')
        cached=_OZON_REFERENCE_CACHE.get(reference_id)
        if cached is None:
            graph=json.loads(''.join(r[0] for r in conn.execute('SELECT data FROM ozon_ref_chunks WHERE id=? ORDER BY part',(reference_id,))))
            _OZON_REFERENCE_CACHE.clear();cached=(graph,None)
        graph,prepared=cached
        if prepared is None:prepared=(OzonPreferred(graph),IdentityGuard(graph['identity']['rows'],graph['identity']))
        _OZON_REFERENCE_CACHE[reference_id]=(graph,prepared)
        return _apply_ozon_preferred(conn,rows,graph,enabled,force,force_name,prepared=prepared,store_reference=False)

def _apply_ozon_preferred(conn, rows, reference, enabled=True, force=False, force_name=False, prepared=None, store_reference=True):
    from ozon_preferred import OzonPreferred
    from ozon_identity import IdentityGuard
    if not isinstance(reference,dict) or not isinstance(reference.get('pairs'),list) or not isinstance(reference.get('category_rows'),list) or not isinstance(reference.get('identity'),dict):
        raise ValueError('Не передан полный исходный справочник Ozon/категорий/идентичностей')
    identity=reference['identity']
    model,guard=prepared if prepared is not None else (OzonPreferred(reference),IdentityGuard(identity.get('rows',rows),identity))
    results=[]
    # Compute and validate the complete batch before any database mutation.
    for p in rows:
        output,verdict=model.apply(p,enabled=enabled,force=force,force_name=force_name,identity_unsafe=guard.unsafe_for(p))
        keys={k for k in set(p)|set(output) if k.startswith(('ozon_','_ozonName'))}
        results.append({'article':p.get('article',''),'brand':p.get('brand',''),
            'fields':{k:output[k] for k in keys if k in output},'removed':sorted(keys-set(output)), 'result':verdict})
    with conn:
        conn.execute('CREATE TABLE IF NOT EXISTS ozon_preferred_reference(id INTEGER PRIMARY KEY CHECK(id=1),data TEXT NOT NULL)')
        if store_reference:conn.execute('INSERT OR REPLACE INTO ozon_preferred_reference VALUES(1,?)',(json.dumps(reference,ensure_ascii=False),))
        conn.execute('CREATE TABLE IF NOT EXISTS ozon_preferred_state(article TEXT,brand TEXT,data TEXT NOT NULL,PRIMARY KEY(article,brand))')
        for r in results:
            conn.execute('INSERT OR REPLACE INTO ozon_preferred_state VALUES(?,?,?)',(r['article'],r['brand'],json.dumps(r['fields'],ensure_ascii=False)))
            if 'ozon_category' in r['fields'] or 'ozon_type' in r['fields']:
                conn.execute('UPDATE products SET ozon_category=?,ozon_type=? WHERE article=? AND brand=?',(r['fields'].get('ozon_category',''),r['fields'].get('ozon_type',''),r['article'],r['brand']))
    return {'rows':results}

def classify_ozon_rows(conn, rows, reference, operation='classify', force=False):
    if operation not in ('classify','apply_strict'): raise ValueError('Неизвестная операция Ozon')
    if not isinstance(reference,dict) or not isinstance(reference.get('pairs'),list):
        raise ValueError('Не передан канонический справочник Ozon')
    conn.execute('CREATE TABLE IF NOT EXISTS ozon_classification_reference(id INTEGER PRIMARY KEY CHECK(id=1),data TEXT NOT NULL)')
    conn.execute('INSERT OR REPLACE INTO ozon_classification_reference VALUES(1,?)',(json.dumps(reference,ensure_ascii=False),))
    model=OzonClassifier(reference['pairs'],reference.get('tree'),reference.get('scope','auto'))
    result=[]
    if operation=='apply_strict':
        conn.execute('CREATE TABLE IF NOT EXISTS ozon_classification_state(article TEXT,brand TEXT,data TEXT NOT NULL,PRIMARY KEY(article,brand))')
    for p in rows:
        article,brand=p.get('article',''),p.get('brand','')
        if operation=='apply_strict':
            output,verdict=model.apply(p,reference.get('registry'),reference.get('applicability'),force,reference.get('reference_version',0))
            fields={k:v for k,v in output.items() if k.startswith('ozon_')}
            conn.execute('INSERT OR REPLACE INTO ozon_classification_state VALUES(?,?,?)',
                (article,brand,json.dumps(fields,ensure_ascii=False)))
            conn.execute('UPDATE products SET ozon_category=?,ozon_type=? WHERE article=? AND brand=?',
                (output.get('ozon_category',''),output.get('ozon_type',''),article,brand))
            result.append({'article':article,'brand':brand,'fields':fields,'result':verdict})
        else:
            result.append({'article':article,'brand':brand,'result':model.classify(p,reference.get('registry'),reference.get('applicability'))})
    conn.commit()
    return {'rows':result}

@_atomic_enrichment
def enrich_rule_rows(conn, rows, rules, context, special_values=None):
    if special_values is not None:rows=decode_special(rows,special_values)
    conn.execute('CREATE TABLE IF NOT EXISTS enrichment_rule_state(article TEXT,brand TEXT,data TEXT NOT NULL,PRIMARY KEY(article,brand))')
    result=[]
    for row in rows:
        output=apply_enrichment_rules(row,rules,context,match_condition)
        keys=set(row)|set(output)
        changed={k for k in keys if not equivalent(row.get(k),output.get(k)) or (k in row)!=(k in output)}
        fields={k:output[k] for k in changed if k in output}
        nonfinite={k:('nan' if math.isnan(v) else 'positive' if v>0 else 'negative') for k,v in fields.items() if isinstance(v,float) and not math.isfinite(v)}
        fields,special_values_out=encode_special(fields);removed=[k for k in changed if k not in output]
        article,brand=row.get('article',''),row.get('brand','')
        conn.execute('INSERT OR REPLACE INTO enrichment_rule_state VALUES(?,?,?)',
            (article,brand,json.dumps({'fields':fields,'removed':removed,'nonfinite':nonfinite,'special_values':special_values_out},ensure_ascii=False)))
        result.append({'article':article,'brand':brand,'fields':fields,'removed':removed,'nonfinite':nonfinite,'special_values':special_values_out})
    return {'rows':result}

@_atomic_enrichment
def enrich_category_kinds(conn, rows, reference, context, enabled=True, operation='apply', category_confirmed=False):
    if operation not in ('apply','confirm','hydrate','explicit_import'): raise ValueError('Неизвестная операция вида')
    if not isinstance(reference,dict): raise ValueError('Не передан справочник видов')
    context=dict(context or {})
    context['categories']=sorted(context.get('categories',[]),key=lambda c:num(c.get('priority')))
    model=CategoryKind(reference.get('rows',[]),reference.get('revision',''),reference.get('base_categories',[]))
    conn.execute('CREATE TABLE IF NOT EXISTS category_kind_reference(id INTEGER PRIMARY KEY CHECK(id=1),data TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS category_kind_state(article TEXT,brand TEXT,data TEXT NOT NULL,PRIMARY KEY(article,brand))')
    conn.execute('INSERT OR REPLACE INTO category_kind_reference VALUES(1,?)',(json.dumps(reference,ensure_ascii=False),))
    has_context=any(c[1]=='dimension_context' for c in conn.execute('PRAGMA table_info(products)'))
    result=[]; at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    for row in rows:
        changed=None
        if operation=='confirm': output,changed=model.confirm(row,category_confirmed,at)
        elif operation=='hydrate': output=model.hydrate(row,row.get('_categoryKindAuto'))
        elif operation=='explicit_import':
            sources=row.get('_sources')
            output=model.explicit_import(row,row.get('category_type'),sources.get('category_type') if isinstance(sources,dict) else None)
        else: output=model.apply(row,context,enabled,match_condition,at)
        keys=set(row)|set(output)
        touched={k for k in keys if (k.startswith('_category') and k!='_categoryExplicitSource') or k in ('category','category_type','_sources')}
        fields={k:output[k] for k in touched if k in output}
        removed=[k for k in touched if k not in output]
        article,brand=row.get('article',''),row.get('brand','')
        conn.execute('UPDATE products SET category=?,category_type=? WHERE article=? AND brand=?',
            (output.get('category',''),output.get('category_type',''),article,brand))
        conn.execute('INSERT OR REPLACE INTO category_kind_state VALUES(?,?,?)',(article,brand,json.dumps(fields,ensure_ascii=False)))
        _persist_enrichment_sources(conn,article,brand,fields,has_context)
        result.append({'article':article,'brand':brand,'fields':fields,'removed':removed,'changed':changed})
    return {'rows':result}

@_atomic_enrichment
def enrich_name_categories(conn, rows, context, enabled=True):
    context = dict(context or {})
    context['categories'] = sorted(context.get('categories', []), key=lambda c: num(c.get('priority')))
    conn.execute('CREATE TABLE IF NOT EXISTS name_category_reference(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
    conn.execute('INSERT OR REPLACE INTO name_category_reference VALUES(1,?)', (json.dumps(context,ensure_ascii=False),))
    result = []
    for row in rows:
        output = apply_name_category(row, context, enabled, match_condition)
        fields = {k: output[k] for k in ('category',) + NAME_CATEGORY_MARKERS if k in output}
        removed = [k for k in NAME_CATEGORY_MARKERS if k not in output]
        conn.execute('UPDATE products SET category=? WHERE article=? AND brand=?',
                     (output.get('category',''), row.get('article',''), row.get('brand','')))
        result.append({'article':row.get('article'), 'brand':row.get('brand',''), 'fields':fields, 'removed':removed})
    return {'rows':result}

_HVC_REFERENCE_FIELDS = ('parts','oe','byArt','byOe','unsafeKeys','unsafeOe')

# HVC and canonical catalog writes share one queue, not nested queues with
# additive waits. Reads retain WAL concurrency.
def hvc_reference_upload(conn,body):
    return _bulk_write(_hvc_reference_upload_locked)(conn,body)

def _hvc_reference_upload_locked(conn, body):
    """Bounded, immutable SQLite reference chunks; no monolithic JSON upload."""
    import secrets
    conn.execute('CREATE TABLE IF NOT EXISTS hvc_ref_upload(id TEXT PRIMARY KEY,separator TEXT NOT NULL,total INTEGER NOT NULL,sealed INTEGER NOT NULL,created REAL NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS hvc_ref_chunks(id TEXT NOT NULL,part INTEGER NOT NULL,field TEXT NOT NULL,data TEXT NOT NULL,n INTEGER NOT NULL,PRIMARY KEY(id,part))')
    conn.execute('CREATE TABLE IF NOT EXISTS hvc_ref_indexed(id TEXT PRIMARY KEY)')
    conn.execute('CREATE TABLE IF NOT EXISTS hvc_ref_entries(id TEXT NOT NULL,part INTEGER NOT NULL,field TEXT NOT NULL,k TEXT NOT NULL,pos INTEGER NOT NULL,data TEXT NOT NULL,PRIMARY KEY(id,part,k))')
    conn.execute('CREATE INDEX IF NOT EXISTS hvc_ref_lookup ON hvc_ref_entries(id,field,k)')
    action=body.get('action')
    if action=='begin':
        total=body.get('total');sep=body.get('groupSeparator',' / ')
        if type(total) is not int or total<0 or not isinstance(sep,str) or len(sep)>100:raise ValueError('Неверный справочник HVC')
        token='chunked:'+secrets.token_hex(24)
        with conn:
            conn.execute('DELETE FROM hvc_ref_entries WHERE id IN (SELECT id FROM hvc_ref_upload WHERE created<?)',(time.time()-86400,))
            conn.execute('DELETE FROM hvc_ref_indexed WHERE id IN (SELECT id FROM hvc_ref_upload WHERE created<?)',(time.time()-86400,))
            conn.execute('DELETE FROM hvc_ref_chunks WHERE id IN (SELECT id FROM hvc_ref_upload WHERE created<?)',(time.time()-86400,))
            conn.execute('DELETE FROM hvc_ref_upload WHERE created<?',(time.time()-86400,))
            conn.execute('INSERT INTO hvc_ref_upload VALUES(?,?,?,0,?)',(token,sep,total,time.time()))
            conn.execute('INSERT INTO hvc_ref_indexed VALUES(?)',(token,))
        return {'token':token}
    token=body.get('token')
    upload=conn.execute('SELECT total,sealed FROM hvc_ref_upload WHERE id=?',(token,)).fetchone()
    if not upload:raise ValueError('Загрузка справочника HVC не найдена')
    if action=='release':
        with conn:
            conn.execute('DELETE FROM hvc_ref_entries WHERE id=?',(token,))
            conn.execute('DELETE FROM hvc_ref_indexed WHERE id=?',(token,))
            conn.execute('DELETE FROM hvc_ref_chunks WHERE id=?',(token,))
            conn.execute('DELETE FROM hvc_ref_upload WHERE id=?',(token,))
        return {'released':True}
    if action=='chunk':
        part=body.get('part');field=body.get('field');items=body.get('items')
        if upload[1]:raise ValueError('Справочник HVC уже зафиксирован')
        if type(part) is not int or part<0 or field not in _HVC_REFERENCE_FIELDS or not isinstance(items,list) or not 0<len(items)<=8000:raise ValueError('Неверная часть справочника HVC')
        if field in ('unsafeKeys','unsafeOe'):
            if any(not isinstance(v,str) for v in items):raise ValueError('Неверные ключи HVC')
        else:
            if any(not isinstance(v,list) or len(v)!=2 or not isinstance(v[0],str) for v in items):raise ValueError('Неверные записи HVC')
        encoded=json.dumps(items,ensure_ascii=False,allow_nan=False)
        if len(encoded.encode())>2*1024*1024:raise ValueError('Часть справочника HVC больше 2 МБ')
        scalar=field in ('unsafeKeys','unsafeOe')
        # Encode before acquiring SQLite's write lock, not in executemany's
        # lazy iterator while every other writer is blocked.
        entries=[(token,part,field,item if scalar else item[0],pos,
            json.dumps(True if scalar else item[1],ensure_ascii=False,allow_nan=False)) for pos,item in enumerate(items)]
        with conn:
            conn.execute('UPDATE hvc_ref_upload SET sealed=sealed WHERE id=?',(token,))
            current=conn.execute('SELECT sealed FROM hvc_ref_upload WHERE id=?',(token,)).fetchone()
            if not current or current[0]:raise ValueError('Справочник HVC уже закрыт')
            indexed=conn.execute('SELECT 1 FROM hvc_ref_indexed WHERE id=?',(token,)).fetchone()
            if indexed:
                conn.execute('DELETE FROM hvc_ref_entries WHERE id=? AND part=?',(token,part))
                conn.executemany('INSERT OR REPLACE INTO hvc_ref_entries VALUES(?,?,?,?,?,?)',entries)
            # Indexed snapshots keep data once; old snapshots retain their JSON.
            conn.execute('INSERT OR REPLACE INTO hvc_ref_chunks VALUES(?,?,?,?,?)',(token,part,field,'[]' if indexed else encoded,len(items)))
        return {'saved':len(items)}
    if action!='commit':raise ValueError('Неизвестная операция справочника HVC')
    with conn:
        conn.execute('UPDATE hvc_ref_upload SET sealed=sealed WHERE id=?',(token,))
        parts=conn.execute('SELECT part,n FROM hvc_ref_chunks WHERE id=? ORDER BY part',(token,)).fetchall()
        if [p[0] for p in parts]!=list(range(len(parts))) or sum(p[1] for p in parts)!=upload[0]:raise ValueError('Неполный справочник HVC')
        conn.execute('UPDATE hvc_ref_upload SET sealed=1 WHERE id=?',(token,))
    return {'reference_id':token}

def _read_hvc_chunked_reference(conn, reference_id, rows=None):
    try:head=conn.execute('SELECT separator,sealed FROM hvc_ref_upload WHERE id=?',(reference_id,)).fetchone()
    except sqlite3.OperationalError:head=None
    if not head or not head[1]:raise ValueError('Справочник HVC не загружен полностью')
    result={k:[] for k in _HVC_REFERENCE_FIELDS};result['groupSeparator']=head[0]
    try:indexed=conn.execute('SELECT 1 FROM hvc_ref_indexed WHERE id=?',(reference_id,)).fetchone()
    except sqlite3.OperationalError:indexed=None
    if indexed and rows is not None:
        def fetch(field,keys):
            keys=list(keys);values={}
            for offset in range(0,len(keys),400):
                batch=keys[offset:offset+400]
                sql='SELECT k,data FROM hvc_ref_entries INDEXED BY hvc_ref_lookup WHERE id=? AND field=? AND k IN ('+','.join('?' for _ in batch)+') ORDER BY part,pos'
                for key,data in conn.execute(sql,(reference_id,field,*batch)):values[key]=json.loads(data)
            return values
        norm=hvc_enrich_rows.__globals__['norm']
        keys={norm(p.get('article'))+'|'+norm(p.get('brand')) for p in rows}
        by_art=fetch('byArt',keys)
        oes={oe for codes in by_art.values() for oe in codes}
        for p in rows:
            raw=str(p.get('oe_norm') or '').strip()
            oes.add(raw);oes.update(re.split(r'[/;,|\s\x01]+',raw))
        by_oe=fetch('byOe',oes)
        holders=keys|{key for group in by_oe.values() for key in group}
        result.update(parts=fetch('parts',holders),oe=fetch('oe',oes),byArt=by_art,byOe=by_oe,
            unsafeKeys=list(fetch('unsafeKeys',holders)),unsafeOe=list(fetch('unsafeOe',oes)))
        return result
    if indexed:
        for field,key,data in conn.execute('SELECT field,k,data FROM hvc_ref_entries WHERE id=? ORDER BY part,pos',(reference_id,)):
            result[field].append(key if field in ('unsafeKeys','unsafeOe') else [key,json.loads(data)])
    else:
        # Backward-compatible read for uploads started before the index existed.
        for field,data in conn.execute('SELECT field,data FROM hvc_ref_chunks WHERE id=? ORDER BY part',(reference_id,)):
            result[field].extend(json.loads(data))
    return result

@_atomic_enrichment
def enrich_hvc_input_rows(conn, rows, reference=None, mode='auto', cat_mode='artbrand', columns=None, policy=None, reference_id=None):
    """Enrich exactly the supplied rows, not the whole normalized SQL catalog."""
    import hashlib
    conn.execute('CREATE TABLE IF NOT EXISTS hvc_input_reference(id TEXT PRIMARY KEY,data TEXT NOT NULL)')
    if reference is not None:
        encoded=json.dumps(reference,ensure_ascii=False,allow_nan=False)
        reference_id=hashlib.sha256(encoded.encode()).hexdigest()
        conn.execute('INSERT OR IGNORE INTO hvc_input_reference VALUES(?,?)',(reference_id,encoded))
    if isinstance(reference_id,str) and reference_id.startswith('chunked:'):
        graph=_read_hvc_chunked_reference(conn,reference_id,rows)
    else:
        saved=conn.execute('SELECT data FROM hvc_input_reference WHERE id=?',(reference_id,)).fetchone()
        if not saved:raise ValueError('Нет справочника HVC')
        graph=json.loads(saved[0])
    def allowed(p,t):
        candidate=dict(p)
        candidate['dimension_context']=json.dumps({'sources':p.get('_sources') or {},'blocked':bool(p.get('dimensionAnomalyBlocked'))},ensure_ascii=False)
        return _dimension_candidate_allowed(candidate,tuple(num(t[k]) for k in ('length','width','height','weight')),policy or {})
    output=hvc_enrich_rows(rows,graph,mode,cat_mode,columns,time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),num,rnd,allowed)
    results=[]
    for before,after in zip(rows,output):
        fields={k:v for k,v in after.items() if k not in before or not equivalent(before[k],v)}
        clean,types=encode_special(fields)
        results.append({'article':before.get('article'),'brand':before.get('brand',''),'fields':clean,'special_values':types,'removed':[k for k in before if k not in after]})
    return {'rows':results,'reference_id':reference_id,'changed':sum(bool(r['fields'] or r['removed']) for r in results)}

@_atomic_enrichment
def enrich_hvc(conn, reference=None, mode='auto', cat_mode='artbrand', columns=None, policy=None):
    """HVC snapshot route; keeps ordered graph and dimension evidence intact."""
    conn.execute('CREATE TABLE IF NOT EXISTS hvc_reference(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
    if reference is not None:
        conn.execute('INSERT OR REPLACE INTO hvc_reference VALUES(1,?)', (json.dumps(reference, ensure_ascii=False),))
    stored = conn.execute('SELECT data FROM hvc_reference WHERE id=1').fetchone()
    if stored is None: raise ValueError('Сначала синхронизируйте справочник HVC')
    reference = json.loads(stored[0])
    policy = policy or {}
    rows = []
    for row in conn.execute('SELECT * FROM products ORDER BY rowid'):
        p = dict(row)
        context = json.loads(p.get('dimension_context') or '{}')
        p['_sources'] = context.get('sources') or {}
        p['oe_norm'] = context.get('oeNorm') or ''
        p['dimensionAnomalyBlocked'] = bool(context.get('blocked'))
        review = json.loads(p.get('dimension_review') or '{}')
        if review: p['_dimensionOeReview'] = review
        rows.append(p)
    def allowed(p, t):
        candidate = dict(p)
        context = json.loads(candidate.get('dimension_context') or '{}')
        context['sources'] = p.get('_sources') or {}
        candidate['dimension_context'] = json.dumps(context, ensure_ascii=False)
        return _dimension_candidate_allowed(candidate, tuple(num(t[k]) for k in ('length','width','height','weight')), policy)
    enriched = hvc_enrich_rows(rows, reference, mode, cat_mode, columns,
        time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), num, rnd, allowed)
    fields = ('name','applicability','category','tnved','weight','length','width','height',
              'multiplicity','image_url','barcode','analog_list','group_articles')
    output = []
    for before, after in zip(rows, enriched):
        patch = {k: after[k] for k in fields if k in after and after[k] != before.get(k)}
        # Provenance is part of the result, not a client-side reconstruction.
        context = json.loads(after.get('dimension_context') or '{}')
        context['sources'] = after.get('_sources') or {}
        patch['dimension_context'] = json.dumps(context, ensure_ascii=False)
        patch['dimension_review'] = json.dumps(after.get('_dimensionOeReview') or {}, ensure_ascii=False)
        conn.execute('UPDATE products SET ' + ','.join(k+'=?' for k in patch) + ' WHERE article=? AND brand=?',
                     (*patch.values(), after['article'], after['brand']))
        output.append({**{k: after.get(k) for k in fields}, 'article': after['article'], 'brand': after['brand'],
            '_sources': after.get('_sources') or {}, '_dimensionOeReview': after.get('_dimensionOeReview'),
            'groupSize': after.get('groupSize')})
    return {'rows': output, 'processed': len(rows)}

def enrich_full(conn, cat_mode='artbrand', enrich_mode='auto', enrich_cols=None, dimension_policy=None, oe_registry=None):
    """Полное обогащение по правилам приложения (HVC):
       - доноры: та же пара Артикул+Бренд (реестр donors) и транзитивная OE-группа;
       - категория/ТН ВЭД: по умолчанию только Артикул+Бренд (cat_mode='artbrand');
         по OE (cat_mode='oe') — только при единогласии доноров, конфликт = пропуск;
       - название/применимость: Артикул+Бренд, иначе самое частое в OE-группе;
       - габариты: цельный комплект той же пары, иначе меньший комплект OE-группы;
         совместимость с уже заполненными обязательна, заполняются только пустые;
       - аналоги: артикулы OE-группы (как enrich_oe). Заполненные поля не трогаем."""
    dimension_policy = dimension_policy or {}
    reviews = []
    enabled = lambda field: enrich_cols is None or bool(enrich_cols.get(field, True))
    prods = [dict(r) for r in conn.execute(
        'SELECT article,brand,name,category,tnved,applicability,warranty,country,weight,length,width,height,oe_numbers,analog_list,group_articles,barcode,image_url,multiplicity,net_weight,volume,dimension_review,dimension_context FROM products')]
    donors = [dict(r) for r in conn.execute(
        'SELECT article,brand,name,category,tnved,applicability,warranty,country,weight,length,width,height,oe_numbers,barcode,image_url,multiplicity FROM donors')]
    # v12.9.145: ключи — как в браузере (normArticle): «F 100» и «F-100» одна пара.
    donors_by_key = {}
    for d in donors: donors_by_key.setdefault(_norm_pair(d['article'], d['brand']), []).append(d)
    # Карантин идентичностей (как HVC.identityUnsafe): один нормализованный ключ
    # у разных буквальных пар артикул+бренд — такие SKU не обогащаем и их OE не
    # даём связывать группы, иначе чужие данные протекут не в тот товар.
    _lit_by_norm = {}
    for r in prods: _lit_by_norm.setdefault(_norm_pair(r['article'], r['brand']), set()).add((r['article'], r['brand']))
    unsafe_norms = {k for k, v in _lit_by_norm.items() if len(v) > 1}
    quarantined = sum(1 for r in prods if _norm_pair(r['article'], r['brand']) in unsafe_norms)
    # OE-граф: продукты и доноры в одних группах (узел = ('p'|'d', article, brand, idx))
    nodes = [('p', i) for i in range(len(prods))] + [('d', i) for i in range(len(donors))]
    oe_map = {}
    for kind, i in nodes:
        r = prods[i] if kind == 'p' else donors[i]
        if kind == 'p' and _norm_pair(r['article'], r['brand']) in unsafe_norms: continue
        for oe in _oe_codes(r['oe_numbers']): oe_map.setdefault(oe, []).append((kind, i))
    # HVC._oeSetOf uses direct OE holders, not transitive connected components.
    groups = {}
    for i, product in enumerate(prods):
        members = [('p', i)]
        seen = set(members)
        for oe in _oe_codes(product['oe_numbers']):
            for node in oe_map.get(oe, []):
                if node not in seen:
                    seen.add(node); members.append(node)
        groups[i] = members
    if oe_registry is not None:
        conn.execute('DELETE FROM oe_registry')
        conn.executemany('INSERT OR REPLACE INTO oe_registry(oe,data) VALUES(?,?)',
                         [(str(r['oe']), json.dumps(r, ensure_ascii=False)) for r in oe_registry if str(r.get('oe', '')).strip()])
    registry = {r['oe']: json.loads(r['data']) for r in conn.execute('SELECT oe,data FROM oe_registry ORDER BY rowid')}

    filled = {'name': 0, 'applicability': 0, 'category': 0, 'tnved': 0, 'warranty': 0, 'country': 0, 'dims': 0, 'analog_list': 0, 'group_articles': 0, 'barcode': 0, 'image_url': 0, 'multiplicity': 0}
    conflicts = {'category': 0, 'tnved': 0}
    def unanimous(values):
        vals = [str(v).strip() for v in values if str(v or '').strip()]
        uniq = set(vals)
        return (vals[0] if len(uniq) == 1 else None), len(uniq) > 1
    def frequent(values):
        vals = [str(v).strip() for v in values if str(v or '').strip()]
        return vals[0] if vals else ''
    for target_index, members in groups.items():
        group_prods = [prods[i] for kind, i in members if kind == 'p']
        if not group_prods: continue
        group_donors = [donors[i] for kind, i in members if kind == 'd']
        for p in [prods[target_index]]:
            if _norm_pair(p['article'], p['brand']) in unsafe_norms: continue  # карантин
            pair = donors_by_key.get(_norm_pair(p['article'], p['brand']), [])
            updates = {}
            # artbrand never falls back to an OE donor. Auto runs OE first.
            oe_text = group_donors if enrich_mode in ('oe', 'auto') else []
            rep = next((registry[oe] for oe in _oe_codes(p['oe_numbers']) if oe in registry), {})
            pair_text = pair if enrich_mode in ('artbrand', 'auto') else []
            for field in ('name', 'applicability'):
                if enabled(field) and not str(p[field] or '').strip():
                    v = (str(rep.get(field) or '').strip() if enrich_mode in ('oe', 'auto') else '') or frequent([d[field] for d in oe_text]) or frequent([d[field] for d in pair_text])
                    if v: updates[field] = v; filled[field] += 1
            for field in ('category', 'tnved'):
                if not enabled(field): continue
                _placeholders = {'без категории', 'разное', 'прочее', 'не определено'}
                _cur = str(p[field] or '').strip()
                if _cur and not (field == 'category' and _cur.lower() in _placeholders): continue
                _vals = [d[field] for d in (pair if cat_mode in ('artbrand', 'auto') else []) if not (field == 'category' and str(d[field] or '').strip().lower() in _placeholders)]
                v, conf = unanimous(_vals)
                if conf: conflicts[field] += 1
                if not v and cat_mode in ('oe', 'auto'):
                    _pool = [rep.get(field)] + [d[field] for d in group_donors]
                    if field == 'category': _pool = [x for x in _pool if str(x or '').strip().lower() not in _placeholders]
                    v, conf2 = unanimous(_pool)
                    if conf2: conflicts[field] += 1
                if v: updates[field] = v; filled[field] += 1
            # гарантия/страна: только точная пара справочника, единогласно (как ozonSourceAttributes)
            for field in ('warranty', 'country'):
                if str(p[field] or '').strip(): continue
                v, conf = unanimous([d[field] for d in pair])
                if v: updates[field] = v; filled[field] = filled.get(field, 0) + 1
            cur = _dims_of(p)
            context = json.loads(p.get('dimension_context') or '{}')
            existing_review = json.loads(p.get('dimension_review') or '{}')
            blocked = bool(existing_review or context.get('blocked')) or _norm_pair(p['article'], p['brand']) in dimension_policy.get('blocked', [])
            if not blocked and any(enabled(f) and not cur[i] > 0 for i, f in enumerate(('length', 'width', 'height', 'weight'))):
                cands = []
                _oe_pool = (group_donors + group_prods) if enrich_mode in ('oe', 'auto') else []
                for d in pair + _oe_pool:
                    t = _dims_of(d)
                    if all(v > 0 for v in t): cands.append(t)
                # Minimum complete tuple, using the browser's ordering:
                # (объём л, наибольшая сторона, вес, сумма сторон)
                pair_cands = [_dims_of(d) for d in pair if all(v > 0 for v in _dims_of(d))]
                _measure = lambda t: (rnd(t[0] * t[1] * t[2] / 1000, 6), rnd(max(t[:3]), 4), rnd(t[3], 6), rnd(sum(t[:3]), 4))
                pool = sorted(pair_cands + cands, key=_measure)
                for t in pool:
                    if _dimension_candidate_allowed(p, t, dimension_policy) and all(not (c > 0) or c == tv for c, tv in zip(cur, t)):  # совместимость с заполненным
                        for i, f in enumerate(('length', 'width', 'height', 'weight')):
                            if enabled(f) and not cur[i] > 0: updates[f] = t[i]
                        filled['dims'] += 1
                        before = dict(zip(('length', 'width', 'height', 'weight'), cur))
                        after = {f: updates.get(f, v) for f, v in before.items()}
                        reviews.append({'article': p['article'], 'brand': p['brand'],
                            'before': before, 'after': after,
                            'source': 'Каталог V: комплект ОВХ · сверьте упаковку', 'at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
                        conn.execute('UPDATE products SET dimension_review=? WHERE article=? AND brand=?',
                                     (json.dumps(reviews[-1], ensure_ascii=False), p['article'], p['brand']))
                        break
            # штрихкод/фото/кратность — только та же пара донора (как HVC.enrichOne)
            if pair:
                if enabled('barcode') and not str(p.get('barcode') or '').strip():
                    _bc = next((str(d['barcode']).strip() for d in pair if str(d.get('barcode') or '').strip()), '')
                    if _bc: updates['barcode'] = _bc; filled['barcode'] = filled.get('barcode', 0) + 1
                if not str(p.get('image_url') or '').strip():
                    _im = next((str(d['image_url']).strip() for d in pair if str(d.get('image_url') or '').strip()), '')
                    if _im: updates['image_url'] = _im; filled['image_url'] = filled.get('image_url', 0) + 1
                if not num(p.get('multiplicity')) > 0:
                    _mu = next((num(d['multiplicity']) for d in pair if num(d.get('multiplicity')) > 0), 0)
                    if _mu > 0: updates['multiplicity'] = _mu; filled['multiplicity'] = filled.get('multiplicity', 0) + 1
            # Lists follow the direct holder order; HVC caps analogs at 40.
            active = (enrich_mode in ('oe', 'auto') and bool(_oe_codes(p['oe_numbers']))) or (enrich_mode in ('artbrand', 'auto') and bool(pair))
            if active:
                seen_articles = {_norm_key_part(p['article'])}
                analogs = []
                for donor in group_donors:
                    normalized = _norm_key_part(donor['article'])
                    if normalized and normalized not in seen_articles:
                        seen_articles.add(normalized)
                        if len(analogs) < 40: analogs.append(donor['article'])
                if enabled('analog_list'):
                    value = ', '.join(analogs)
                    if value != str(p['analog_list'] or ''):
                        updates['analog_list'] = value; filled['analog_list'] += 1
                if enabled('group_articles'):
                    group_articles = [p['article']]
                    group_seen = {_norm_key_part(p['article'])}
                    for oe in _oe_codes(p['oe_numbers']):
                        holders = oe_map.get(oe, [])
                        if len(holders) > 2000: continue
                        for kind, index in holders:
                            row = prods[index] if kind == 'p' else donors[index]
                            normalized = _norm_key_part(row['article'])
                            if normalized and normalized not in group_seen and len(group_articles) < 500:
                                group_seen.add(normalized); group_articles.append(row['article'])
                    value = dimension_policy.get('group_separator', ' / ').join(group_articles)
                    if value != str(p.get('group_articles') or ''):
                        updates['group_articles'] = value; filled['group_articles'] += 1
            updates = {k: v for k, v in updates.items() if enabled(k)}
            if updates:
                sets = ', '.join(f'{k}=?' for k in updates)
                conn.execute(f'UPDATE products SET {sets} WHERE article=? AND brand=?',
                             (*updates.values(), p['article'], p['brand']))
    conn.commit()
    log_api(conn, 'enrichFull', 'sqlite', 'ok', f'cat_mode={cat_mode}, заполнено {filled}, конфликты {conflicts}')
    return {'cat_mode': cat_mode, 'filled': filled, 'conflicts': conflicts, 'donors': len(donors), 'quarantined': quarantined, 'dimension_reviews': reviews}

# ---------------- обобщённый разбор файлов (п.5 аудита, v12.9.111) ----------------
def iter_raw_file_rows(filename,data):
    """Yield nonempty raw rows, keeping XLSX/CSV parsing buffers bounded."""
    name=str(filename or 'file')
    if not name.lower().endswith(('.csv','.xlsx','.zip')):raise ValueError('SQL-парсер поддерживает CSV, XLSX и ZIP с одним файлом. Сохраните XLS/ODS как XLSX.')
    if name.lower().endswith('.zip'):
        files=files_from_zip(data)
        if not files:raise RuntimeError('в ZIP нет CSV/XLSX')
        if len(files)!=1:raise ValueError('Для импорта с маппингом выберите один CSV/XLSX, а не архив с несколькими файлами')
        name,data=files[0]
    def nonempty(row):return any(str(v).strip() for v in row if v is not None)
    if name.lower().endswith('.xlsx'):
        try:import openpyxl
        except ImportError:
            for row in _xlsx_sheet_rows(data):
                if nonempty(row):yield list(row)
            return
        wb=openpyxl.load_workbook(io.BytesIO(data),read_only=True,data_only=True)
        try:
            for row in wb.worksheets[0].iter_rows(values_only=True):
                if nonempty(row):yield list(row)
        finally:wb.close()
    else:
        import codecs
        encoding='utf-8-sig'
        try:
            decoder=codecs.getincrementaldecoder(encoding)()
            for off in range(0,len(data),65536):decoder.decode(data[off:off+65536])
            decoder.decode(b'',final=True)
        except UnicodeDecodeError:encoding='cp1251'
        with io.TextIOWrapper(io.BytesIO(data),encoding=encoding,newline='') as stream:
            sample=stream.read(2048);stream.seek(0);first=sample.split('\n',1)[0]
            delim=';' if first.count(';')>=first.count(',') and first.count(';')>=first.count('\t') else ('\t' if first.count('\t')>first.count(',') else ',')
            try:delim=csv.Sniffer().sniff(sample,delimiters=';,\t|').delimiter
            except csv.Error:pass
            for row in csv.reader(stream,delimiter=delim):
                if nonempty(row):yield row

def _raw_table(filename,data):
    rows=iter(iter_raw_file_rows(filename,data))
    try:first=next(rows)
    except StopIteration:return [],[]
    return [str(h).strip() if h is not None else '' for h in first],list(rows)

# Queue heavy writes before SQLite; encoding/parsing stays outside the queue.
_SQL_BULK_WRITE_LOCK=threading.RLock()
def _bulk_write(fn):
    import functools
    @functools.wraps(fn)
    def queued(conn,*args,**kwargs):
        if not _SQL_BULK_WRITE_LOCK.acquire(timeout=60):raise ValueError('Очередь записи SQLite занята; операция не выполнена')
        previous=None
        try:
            previous=conn.execute('PRAGMA busy_timeout').fetchone()[0]
            conn.execute('PRAGMA busy_timeout=30000')
            return fn(conn,*args,**kwargs)
        finally:
            try:
                if previous is not None:conn.execute('PRAGMA busy_timeout='+str(int(previous)))
            finally:_SQL_BULK_WRITE_LOCK.release()
    return queued

def parse_file_bytes(conn,filename,data,catalog_import=False):
    import itertools,tempfile,uuid
    rows=iter(iter_raw_file_rows(filename,data))
    try:
        prefix=list(itertools.islice(rows,9 if catalog_import else 1))
        if prefix:
            hi=import_header_index(prefix) if catalog_import else 0
            headers=[str(v).strip() if v is not None else '' for v in prefix[hi]]
            if catalog_import:headers=[v or 'Колонка_'+str(i+1) for i,v in enumerate(headers)]
        else:hi=0;headers=[]
        if len(headers)!=len(set(headers)):raise ValueError('Повторяющиеся заголовки: переименуйте колонки перед импортом, иначе значения будут потеряны')
        sid=uuid.uuid4().hex[:16];total=0
        # Parse/encode completely before taking a write lock. Spool to disk,
        # not a second in-memory list of all encoded rows.
        with tempfile.TemporaryFile(mode='w+t',encoding='utf-8') as spool:
            for row in itertools.chain(prefix[hi+1:],rows):
                spool.write(json.dumps({headers[j]:(row[j] if j<len(row) else '') for j in range(len(headers))},ensure_ascii=False,default=str)+'\n');total+=1
            spool.seek(0)
            @_bulk_write
            def publish(conn):
                with conn:
                    conn.execute('INSERT INTO parse_sessions(id,filename,headers,total,created) VALUES(?,?,?,?,datetime("now"))',(sid,os.path.basename(str(filename or 'file')),json.dumps(headers,ensure_ascii=False),total))
                    pending=[]
                    for idx,line in enumerate(spool):
                        pending.append((sid,idx,line.rstrip('\n')))
                        if len(pending)==1000:
                            conn.executemany('INSERT INTO parse_rows(session,idx,data) VALUES(?,?,?)',pending);pending.clear()
                    if pending:conn.executemany('INSERT INTO parse_rows(session,idx,data) VALUES(?,?,?)',pending)
                    old=[r[0] for r in conn.execute('SELECT id FROM parse_sessions ORDER BY created DESC,rowid DESC LIMIT -1 OFFSET 5')]
                    for old_id in old:
                        conn.execute('DELETE FROM parse_rows WHERE session=?',(old_id,));conn.execute('DELETE FROM parse_sessions WHERE id=?',(old_id,))
                log_api(conn,'parseFile',str(filename),'ok',f'строк {total}')
            publish(conn)
        return {'parse_id':sid,'headers':headers,'total':total}
    finally:
        if hasattr(rows,'close'):rows.close()

# ---------------- история цен и снапшоты (п.6 аудита, v12.9.112) ----------------
def price_changes(conn, days=30, limit=200):
    """Изменения цен за период: LAG по истории даёт предыдущую цену SKU."""
    days = max(1, min(3650, int(num(days) or 30)))
    rows = conn.execute('''SELECT article,brand,price,cost,ts,source,prev_price FROM (
            SELECT *, LAG(price) OVER (PARTITION BY article,brand ORDER BY ts,rowid) prev_price
            FROM price_history)
        WHERE ts >= datetime("now", ?) AND prev_price IS NOT NULL AND ABS(price-prev_price) > 1e-9
        ORDER BY ts DESC LIMIT ?''', (f'-{days} days', int(limit))).fetchall()
    agg = conn.execute('''SELECT COUNT(DISTINCT article || '|' || brand) sku,
            SUM(price > prev_price) rises, SUM(price < prev_price) falls FROM (
            SELECT *, LAG(price) OVER (PARTITION BY article,brand ORDER BY ts,rowid) prev_price
            FROM price_history)
        WHERE ts >= datetime("now", ?) AND prev_price IS NOT NULL AND ABS(price-prev_price) > 1e-9''',
        (f'-{days} days',)).fetchone()
    out = []
    for r in rows:
        d = dict(r)
        d['delta_pct'] = rnd((d['price'] - d['prev_price']) / d['prev_price'] * 100, 2) if d['prev_price'] else 0
        out.append(d)
    return {'days': days, 'changed_sku': agg[0] or 0, 'rises': agg[1] or 0, 'falls': agg[2] or 0, 'rows': out}

def make_snapshot(conn, note=''):
    total = conn.execute('SELECT COUNT(*) FROM products').fetchone()[0]
    cur = conn.execute('INSERT INTO snapshots(created,note,total) VALUES(datetime("now"),?,?)', (str(note)[:200], total))
    sid = cur.lastrowid
    conn.execute('INSERT INTO snapshot_rows(snapshot_id,article,brand,price,cost,stock) '
                 'SELECT ?,article,brand,price,cost,stock FROM products', (sid,))
    conn.commit()
    log_api(conn, 'snapshot', str(sid), 'ok', f'{total} SKU')
    return {'snapshot_id': sid, 'total': total}

def snapshot_diff(conn, id1, id2):
    q = lambda sql, args: conn.execute(sql, args).fetchall()
    added = q('SELECT a.article,a.brand,a.price FROM snapshot_rows a LEFT JOIN snapshot_rows b '
              'ON b.snapshot_id=? AND b.article=a.article AND b.brand=a.brand WHERE a.snapshot_id=? AND b.article IS NULL',
              (id1, id2))
    removed = q('SELECT a.article,a.brand,a.price FROM snapshot_rows a LEFT JOIN snapshot_rows b '
                'ON b.snapshot_id=? AND b.article=a.article AND b.brand=a.brand WHERE a.snapshot_id=? AND b.article IS NULL',
                (id2, id1))
    changed = q('SELECT a.article,a.brand,b.price old_price,a.price new_price FROM snapshot_rows a '
                'JOIN snapshot_rows b ON b.snapshot_id=? AND b.article=a.article AND b.brand=a.brand '
                'WHERE a.snapshot_id=? AND ABS(a.price-b.price) > 1e-9 ORDER BY ABS(a.price-b.price) DESC LIMIT 500',
                (id1, id2))
    return {'from': id1, 'to': id2, 'added': [dict(r) for r in added], 'removed': [dict(r) for r in removed],
            'price_changed': [dict(r) for r in changed]}

# ---------------- fuzzy-подсказки аналогов (п.7 аудита, v12.9.113) ----------------
def _norm_article(v):
    return re.sub(r'[^A-Z0-9А-ЯЁ]', '', str(v or '').upper())

def analog_suggestions(conn, limit=100):
    """ТОЛЬКО подсказки оператору (запрет авто-поиска аналогов v12.9.85 не тронут):
       ничего не записываем. Кандидаты для SKU без аналогов: тот же нормализованный
       артикул у другого бренда и похожие артикулы (опечатки, ratio>=0.86),
       блокирование по префиксу, пары с общим OE исключены (они уже связаны)."""
    import difflib
    prods = [dict(r) for r in conn.execute('SELECT article,brand,analog_list,oe_numbers FROM products')]
    oe_of = {}
    oe_pairs = set()
    by_oe = {}
    for p in prods:
        key = (p['article'], p['brand'])
        codes = set(_oe_codes(p['oe_numbers']))
        oe_of[key] = codes
        for oe in codes: by_oe.setdefault(oe, []).append(key)
    for keys in by_oe.values():
        for a in keys:
            for b in keys:
                if a != b: oe_pairs.add((a, b))
    blocks = {}
    for p in prods:
        n = _norm_article(p['article'])
        if len(n) >= 3: blocks.setdefault(n[:3], []).append(p)
    out = []
    seen = set()
    for lst in blocks.values():
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                a, b = lst[i], lst[j]
                ka, kb = (a['article'], a['brand']), (b['article'], b['brand'])
                na, nb = _norm_article(a['article']), _norm_article(b['article'])
                if abs(len(na) - len(nb)) > 2: continue
                if na == nb:
                    score, reason = 1.0, 'тот же артикул, другой бренд'
                else:
                    score = difflib.SequenceMatcher(None, na, nb).ratio()
                    if score < 0.86: continue
                    reason = 'похожий артикул (возможна опечатка)'
                for src, dst in ((a, b), (b, a)):
                    ks, kd = (src['article'], src['brand']), (dst['article'], dst['brand'])
                    if str(src['analog_list'] or '').strip(): continue       # аналоги уже есть
                    if (ks, kd) in oe_pairs or (ks, kd) in seen: continue    # уже связаны по OE
                    seen.add((ks, kd))
                    out.append({'article': src['article'], 'brand': src['brand'],
                                'candidate_article': dst['article'], 'candidate_brand': dst['brand'],
                                'score': rnd(score, 3), 'reason': reason})
    out.sort(key=lambda r: -r['score'])
    return {'suggestions': out[:int(limit)], 'total_found': len(out),
            'note': 'только подсказки оператору: аналоги автоматически не проставляются'}

# ---------------- очередь отправки на площадки ----------------
def enqueue(conn, kind, marketplace, items):
    n = 0
    for it in items:
        key = f"{kind}:{marketplace}:{it.get('article','')}:{it.get('idempotency','') or json.dumps(it, sort_keys=True, ensure_ascii=False)}"
        cur = conn.execute('''INSERT OR IGNORE INTO outbox(kind,marketplace,article,payload,idempotency_key,created_at)
                              VALUES(?,?,?,?,?,datetime("now"))''',
                           (kind, marketplace, it.get('article', ''), json.dumps(it, ensure_ascii=False), key))
        n += cur.rowcount
    conn.commit()
    return n

def _http_json(method, url, headers, payload, timeout=30):
    req = urlrequest.Request(url, method=method,
                             data=json.dumps(payload).encode('utf-8') if payload is not None else None,
                             headers={'Content-Type': 'application/json', **headers})
    with urlrequest.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode('utf-8') or '{}')

def process_outbox(limit=100):
    conn = db()
    sec = secrets()
    dry = str(get_settings(conn).get('dry_run', '1')) != '0'
    done, failed = 0, 0
    rows = conn.execute("SELECT * FROM outbox WHERE status IN ('pending','failed') AND attempts<5 ORDER BY id LIMIT ?", (limit,)).fetchall()
    for job in rows:
        payload = json.loads(job['payload'] or '{}')
        try:
            if dry:
                result = 'dry-run: запрос не отправлен (dry_run=1)'
            elif job['marketplace'] == 'OZON' and job['kind'] == 'prices':
                if not (sec.get('UC_OZON_CLIENT_ID') and sec.get('UC_OZON_API_KEY')):
                    raise RuntimeError('Нет ключей Ozon (UC_OZON_CLIENT_ID/UC_OZON_API_KEY)')
                status, resp = _http_json('POST', 'https://api-seller.ozon.ru/v1/product/import/prices',
                    {'Client-Id': sec['UC_OZON_CLIENT_ID'], 'Api-Key': sec['UC_OZON_API_KEY']},
                    {'prices': [{'offer_id': payload.get('article'), 'price': str(payload.get('price')),
                                 'old_price': str(payload.get('old_price', payload.get('price'))),
                                 'min_price': str(payload.get('min_price', payload.get('price')))}]})
                result = f'HTTP {status}'
            elif job['marketplace'] == 'OZON' and job['kind'] == 'stocks':
                if not (sec.get('UC_OZON_CLIENT_ID') and sec.get('UC_OZON_API_KEY')):
                    raise RuntimeError('Нет ключей Ozon')
                status, resp = _http_json('POST', 'https://api-seller.ozon.ru/v2/products/stocks',
                    {'Client-Id': sec['UC_OZON_CLIENT_ID'], 'Api-Key': sec['UC_OZON_API_KEY']},
                    {'stocks': [{'offer_id': payload.get('article'), 'stock': int(num(payload.get('stock'))),
                                 'warehouse_id': int(num(payload.get('warehouse_id')))}]})
                result = f'HTTP {status}'
            else:
                raise RuntimeError(f"Адаптер {job['marketplace']}/{job['kind']} ещё не реализован в движке")
            conn.execute("UPDATE outbox SET status='sent', attempts=attempts+1, sent_at=datetime('now'), last_error=? WHERE id=?",
                         (result, job['id']))
            done += 1
        except Exception as e:
            conn.execute("UPDATE outbox SET status='failed', attempts=attempts+1, last_error=? WHERE id=?",
                         (str(e)[:300], job['id']))
            failed += 1
        conn.commit()
    log_api(conn, 'processOutbox', 'local', 'ok', f'sent {done}, failed {failed}, dry={dry}')
    return {'sent': done, 'failed': failed, 'dry_run': dry}

# ---------------- папка входящих файлов + бэкапы + отчёт ----------------
def watch_folder_once(folder=None):
    folder = Path(folder or (DATA / 'inbox'))
    folder.mkdir(exist_ok=True)
    processed = folder / 'processed'; processed.mkdir(exist_ok=True)
    conn = db(); total = 0
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() not in ('.csv', '.xlsx', '.zip') or not f.is_file(): continue
        blob = f.read_bytes()
        files = files_from_zip(blob) if f.suffix.lower() == '.zip' else [(f.name, blob)]
        for name, data in files:
            rows = rows_from_xlsx_bytes(data) if name.lower().endswith('.xlsx') else rows_from_csv_bytes(data)
            total += import_rows(conn, rows, f'folder:{f.name}')
        dest = processed / f.name
        if dest.exists():  # B8: повторное имя не должно ронять перенос
            dest = processed / (f.stem + '-' + time.strftime('%Y%m%d-%H%M%S') + f.suffix)
        shutil.move(str(f), str(dest))
    if total: log_api(conn, 'watchFolder', str(folder), 'ok', f'строк {total}')
    return {'imported_rows': total}

def make_backup():
    dest_dir = DATA / 'backups'; dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / ('catalog-' + time.strftime('%Y%m%d-%H%M%S') + '.db')
    src = db(); dst = sqlite3.connect(dest)
    with dst: src.backup(dst)
    dst.close(); src.close()
    backups = sorted(dest_dir.glob('catalog-*.db'))
    for old in backups[:-14]: old.unlink(missing_ok=True)
    return {'backup': str(dest), 'kept': min(len(backups), 14)}

def summary_report(conn):
    agg = conn.execute('SELECT COUNT(*) n, ROUND(SUM(price*stock),2) stock_value FROM products').fetchone()
    outbox = conn.execute("SELECT status, COUNT(*) c FROM outbox GROUP BY status").fetchall()
    mail = conn.execute("SELECT COUNT(*) c FROM mail_log WHERE status='ok'").fetchone()
    return {'products': agg['n'], 'stock_value': agg['stock_value'],
            'outbox': {r['status']: r['c'] for r in outbox}, 'mail_imports_ok': mail['c']}

def dashboard_report(conn):
    """Сводка каталога одним SQL-проходом (аудит v12.9.107, п.3):
       агрегаты по eco_results и аномалии — вместо проходов по строкам вкладки."""
    base = conn.execute('SELECT COUNT(*) n, ROUND(SUM(price*stock),2) stock_value FROM products').fetchone()
    eco = conn.execute('SELECT COUNT(*) n, SUM(profit>0) profitable, ROUND(AVG(margin),2) avg_margin, '
                       'ROUND(SUM(profit),2) profit_units FROM eco_results').fetchone()
    an = conn.execute("SELECT SUM(price>0 AND cost>price) below_cost, SUM(length=0 OR width=0 OR height=0) no_dims, "
                      "SUM(oe_numbers='') no_oe, SUM(name='') no_name FROM products").fetchone()
    top = conn.execute('SELECT p.brand brand, ROUND(SUM(e.profit*p.sales),2) profit_month FROM eco_results e '
                       'JOIN products p ON p.article=e.article AND p.brand=e.brand '
                       'GROUP BY p.brand ORDER BY profit_month DESC LIMIT 5').fetchall()
    return {'products': base['n'], 'stock_value': base['stock_value'],
            'recalculated': eco['n'], 'profitable': eco['profitable'] or 0,
            'avg_margin': eco['avg_margin'], 'profit_units_sum': eco['profit_units'],
            'anomalies': {'below_cost': an['below_cost'] or 0, 'no_dims': an['no_dims'] or 0,
                          'no_oe': an['no_oe'] or 0, 'no_name': an['no_name'] or 0},
            'top_brands': [dict(r) for r in top]}

# ---------------- экспорт каталога (аудит v12.9.107, п.1; v12.9.108) ----------------
EXPORT_COLS = [('article','Артикул'),('brand','Бренд'),('name','Название'),('price','Цена'),('cost','Себестоимость'),
    ('stock','Остаток'),('sales','Продажи/мес'),('weight','Вес, кг'),('length','Длина, см'),('width','Ширина, см'),
    ('height','Высота, см'),('volume','Объём, л'),('oe_numbers','OE номера'),('analog_list','Аналоги'),
    ('total','Расходы всего'),('profit','Прибыль'),('margin','Маржа, %'),('roi','ROI, %'),
    ('break_even','Безубыток'),('target','Целевая цена')]
_EXPORT_SQL = ('SELECT p.article,p.brand,p.name,p.price,p.cost,p.stock,p.sales,p.weight,p.length,p.width,p.height,'
    'p.volume,p.oe_numbers,p.analog_list,e.total,e.profit,e.margin,e.roi,e.break_even,e.target '
    'FROM products p LEFT JOIN eco_results e ON e.article=p.article AND e.brand=p.brand ORDER BY p.article,p.brand')

def _filter_keys(rows, keys):
    if keys is None: return rows
    ks = {(str(a), str(b)) for a, b in keys}
    return [r for r in rows if (str(r['article'] or ''), str(r['brand'] or '')) in ks]

def export_catalog_csv_bytes(conn, enc='utf-8', keys=None, columns=None, delimiter=';'):
    import csv as _csv
    if delimiter not in (';',',','\t','|'): raise ValueError('Неверный разделитель CSV')
    cols=columns if columns is not None else EXPORT_COLS
    rows=export_catalog_records(conn,keys)
    buf=io.StringIO(); w=_csv.writer(buf,delimiter=delimiter)
    w.writerow([safe_csv_text(h) for _,h in cols])
    for r in rows:
        values=[]
        for k,_ in cols:
            value=r.get(k)
            if isinstance(value,(int,float)) and not isinstance(value,bool) and delimiter==';': value=str(value).replace('.',',')
            values.append(safe_csv_text(value))
        w.writerow(values)
    return encode_csv(buf.getvalue(),enc)


def store_export_cells(conn, cells, columns, column_meta=None, formula_options=None, sheets=None):
    """Persist a request-scoped presentation snapshot. No arbitrary Python/SQL execution."""
    if not isinstance(columns,list) or any(not isinstance(c,list) or len(c)!=2 for c in columns):
        raise ValueError('Неверное описание экспортных колонок')
    if any(not isinstance(k,str) or not k or not isinstance(h,str) or k in ('__export_order','__export_formulas') for k,h in columns) or len({k for k,_ in columns})!=len(columns):
        raise ValueError('Неверные или повторяющиеся ключи экспортных колонок')
    if not isinstance(cells,list):raise ValueError('Неверные строки экспорта')
    if column_meta is not None and (not isinstance(column_meta,list) or len(column_meta)!=len(columns) or any(not isinstance(m,dict) for m in column_meta)):
        raise ValueError('Неверные метаданные экспортных колонок')
    refs=prepare_formula_options(column_meta,sheets,formula_options) if formula_options is not None else {}
    if formula_options is not None:
        identities=[(str(c.get('article','')),str(c.get('brand',''))) for c in cells if isinstance(c,dict)]
        if len(set(identities))!=len(identities):raise ValueError('Повторяющиеся SKU в экспорте с формулами')
        known={(str(r[0]),str(r[1])) for r in conn.execute('SELECT article,brand FROM products')}
        if any(key not in known for key in identities):raise ValueError('SKU экспорта отсутствует в SQLite; повторите синхронизацию')
    skipped=set()
    staged=[]
    for order,cell in enumerate(cells):
        if not isinstance(cell,dict):raise ValueError('Неверная строка экспорта')
        values=cell.get('values')
        if not isinstance(values,list) or len(values)!=len(columns): raise ValueError('Неполная строка экспорта')
        values=list(values)
        if column_meta is not None:
            raw=cell.get('custom',{});dates=cell.get('custom_dates',[]);nonfinite=cell.get('custom_nonfinite',[]);special=cell.get('custom_special',{})
            if not isinstance(raw,dict) or not isinstance(dates,list) or not isinstance(nonfinite,list) or any(not isinstance(k,str) for k in dates+nonfinite):raise ValueError('Неверные исходные пользовательские поля')
            if not isinstance(special,dict) or any(not isinstance(k,str) or v not in ('NaN','Infinity','-Infinity') for k,v in special.items()):raise ValueError('Неверные специальные числовые значения')
            for i,meta in enumerate(column_meta):
                key=meta.get('custom')
                if key is not None:
                    if not isinstance(key,str) or not key or meta.get('key')!='c_'+key:raise ValueError('Неверная пользовательская колонка')
                    values[i]=custom_cell(raw,key,meta.get('custom_format') is True,dates,nonfinite,meta.get('custom_text') is True,special)
        if any(isinstance(v,(list,dict)) for v in values): raise ValueError('Ячейка должна содержать скалярное значение')
        formulas=cell.get('formulas')
        if formulas is None:formulas=[None]*len(columns)
        if not isinstance(formulas,list) or len(formulas)!=len(columns): raise ValueError('Неполный набор формул')
        if any(f is not None and not isinstance(f,str) for f in formulas): raise ValueError('Формула должна быть строкой')
        if formula_options is not None:
            formulas=[None]*len(columns)
            context=cell.get('formula_context',{})
            if not isinstance(context,dict) or (context.get('mp') is not None and not isinstance(context['mp'],dict)) or any(not isinstance(v,dict) for v in (context.get('mp') or {}).values()):raise ValueError('Неверный контекст доступности формул')
            if formula_options['enabled']:
                for i,meta in enumerate(column_meta):
                    key=meta['key']
                    if not meta.get('server_formula') or formula_unavailable(context,key,meta.get('group') or 'calc'):continue
                    f=cached_formula(key,order+2,refs,values[i],dim_unit=formula_options.get('dim_unit','cm'))
                    formulas[i]=f
                    if f is None:skipped.add(key)
        data={c[0]:v for c,v in zip(columns,values)}
        data['__export_formulas']={c[0]:f for c,f in zip(columns,formulas) if f}
        data['__export_order']=order
        staged.append((str(cell.get('article','')),str(cell.get('brand','')),json.dumps(data,ensure_ascii=False,allow_nan=False)))
    # Validate/convert every row before replacing any request-scoped state.
    conn.execute('SAVEPOINT prepare_export_cells')
    try:
        conn.execute('CREATE TEMP TABLE IF NOT EXISTS export_cells(article TEXT,brand TEXT,data TEXT,PRIMARY KEY(article,brand))')
        conn.execute('DELETE FROM export_cells')
        conn.executemany('INSERT OR REPLACE INTO export_cells VALUES(?,?,?)',staged)
        conn.execute('RELEASE prepare_export_cells')
    except Exception:
        conn.execute('ROLLBACK TO prepare_export_cells')
        conn.execute('RELEASE prepare_export_cells')
        raise
    return {'skipped_formulas':sorted(skipped)}


def export_catalog_records(conn,keys=None):
    rows=conn.execute('SELECT p.*,e.total,e.profit,e.margin,e.roi,e.break_even,e.target,e.fields_json '
        'FROM products p LEFT JOIN eco_results e ON e.article=p.article AND e.brand=p.brand ORDER BY p.article,p.brand').fetchall()
    result=[]
    for raw in _filter_keys(rows,keys):
        row=dict(raw)
        try: extra=json.loads(row.pop('fields_json',None) or '{}')
        except (ValueError,TypeError): extra={}
        if isinstance(extra,dict):
            for k,v in extra.items():
                if k not in row: row[k]=v
        if conn.execute("SELECT 1 FROM sqlite_temp_master WHERE name='export_cells'").fetchone():
            saved=conn.execute('SELECT data FROM export_cells WHERE article=? AND brand=?',(row['article'],row['brand'])).fetchone()
            if saved: row.update(json.loads(saved[0]))
        result.append(row)
    if conn.execute("SELECT 1 FROM sqlite_temp_master WHERE name='export_cells'").fetchone():
        result=[r for r in result if '__export_order' in r]
        result.sort(key=lambda r:r['__export_order'])
    return result

def _xml_esc(v):
    text=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]',' ',str(v))
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))

def _xlsx_from_rows(headers, data_rows, sheet_name='Лист', header_rows=None, yellow=None, formulas=None):
    """Общий XLSX-писатель без openpyxl: zip из XML (stdlib).
       header_rows — служебные строки перед шапкой (официальный шаблон Ozon);
       yellow — множество (строка_данных_0based, колонка_0based) для жёлтой заливки."""
    import zipfile
    def col_letter(i):
        out = ''
        i += 1
        while i: i, rem = divmod(i - 1, 26); out = chr(65 + rem) + out
        return out
    rows_xml = []
    rn = 0
    for hrow in (header_rows or []):
        rn += 1
        cells = ''.join(f'<c r="{col_letter(i)}{rn}" t="inlineStr"><is><t>{_xml_esc(v)}</t></is></c>'
                        for i, v in enumerate(hrow) if v not in (None, ''))
        rows_xml.append(f'<row r="{rn}">{cells}</row>')
    rn += 1
    header = ''.join(f'<c r="{col_letter(i)}{rn}" t="inlineStr"><is><t>{_xml_esc(h)}</t></is></c>'
                     for i, h in enumerate(headers))
    rows_xml.append(f'<row r="{rn}">{header}</row>')
    yellow = yellow or set()
    for di, row in enumerate(data_rows):
        rn += 1
        cells = []
        for i, v in enumerate(row):
            formula=(formulas or {}).get((di,i))
            if (v is None or v == '') and not formula: continue
            ref = f'{col_letter(i)}{rn}'
            st = ' s="1"' if (di, i) in yellow else ''
            if formula:
                f=_xml_esc(formula.lstrip('='))
                numeric=isinstance(v,(int,float)) and not isinstance(v,bool)
                typ='' if numeric else ' t="str"'
                cached=_xml_esc('' if v is None else v)
                cells.append(f'<c r="{ref}"{st}{typ}><f>{f}</f><v>{cached}</v></c>')
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                cells.append(f'<c r="{ref}"{st}><v>{v}</v></c>')
            else:
                cells.append(f'<c r="{ref}"{st} t="inlineStr"><is><t>{_xml_esc(v)}</t></is></c>')
        rows_xml.append(f'<row r="{rn}">{"".join(cells)}</row>')
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             f'<sheetData>{"".join(rows_xml)}</sheetData></worksheet>')
    sheet_title = _xml_esc(str(sheet_name)[:31] or 'Лист')
    parts = {
        '[Content_Types].xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        'xl/styles.xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fills count="3"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FFFFFF99"/></patternFill></fill></fills>'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<borders count="1"><border/></borders>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
            '<xf numFmtId="0" fontId="0" fillId="2" borderId="0" applyFill="1"/></cellXfs></styleSheet>',
        '_rels/.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets><sheet name="{sheet_title}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        'xl/worksheets/sheet1.xml': sheet}
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, content in parts.items(): z.writestr(name, content)
    return out.getvalue()

def _export_styles(meta):
    import xml.etree.ElementTree as ET
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    root=ET.Element('styleSheet',xmlns=ns)
    fmts=ET.SubElement(root,'numFmts',count=str(len(meta)))
    for i,c in enumerate(meta): ET.SubElement(fmts,'numFmt',numFmtId=str(164+i),formatCode=c.get('format') or 'General')
    fonts=ET.SubElement(root,'fonts',count='2')
    for bold in (False,True):
        font=ET.SubElement(fonts,'font'); ET.SubElement(font,'sz',val='11'); ET.SubElement(font,'name',val='Calibri')
        if bold: ET.SubElement(font,'b')
    fills=ET.SubElement(root,'fills',count='3')
    for kind in ('none','gray125','solid'):
        fill=ET.SubElement(fills,'fill'); pattern=ET.SubElement(fill,'patternFill',patternType=kind)
        if kind=='solid': ET.SubElement(pattern,'fgColor',rgb='FFE8F1FF')
    borders=ET.SubElement(root,'borders',count='1'); ET.SubElement(borders,'border')
    xfs=ET.SubElement(root,'cellXfs',count=str(len(meta)+2))
    ET.SubElement(xfs,'xf',numFmtId='0',fontId='0',fillId='0',borderId='0')
    ET.SubElement(xfs,'xf',numFmtId='0',fontId='1',fillId='2',borderId='0',applyFill='1')
    for i in range(len(meta)): ET.SubElement(xfs,'xf',numFmtId=str(164+i),fontId='0',fillId='0',borderId='0',applyNumberFormat='1')
    dxfs=ET.SubElement(root,'dxfs',count='2')
    for bg,fg in [('FFE2F5EA','FF0E6B3A'),('FFFDE8EA','FF9E1B30')]:
        dxf=ET.SubElement(dxfs,'dxf'); font=ET.SubElement(dxf,'font')
        ET.SubElement(font,'b'); ET.SubElement(font,'color',rgb=fg)
        fill=ET.SubElement(dxf,'fill'); pattern=ET.SubElement(fill,'patternFill',patternType='solid')
        ET.SubElement(pattern,'fgColor',rgb=bg)
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)


def _format_export_sheet(xml,sheet,meta,protect):
    import xml.etree.ElementTree as ET
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    q=lambda s:'{'+ns+'}'+s
    root=ET.fromstring(xml); indices=sheet['indices']
    views=ET.Element(q('sheetViews')); view=ET.SubElement(views,q('sheetView'),workbookViewId='0')
    ET.SubElement(view,q('pane'),ySplit='1',topLeftCell='A2',activePane='bottomLeft',state='frozen')
    root.insert(0,views)
    cols=ET.Element(q('cols'))
    for ci,index in enumerate(indices,1):
        width=float(meta[index].get('width',14))
        if not 0<width<=255: raise ValueError('Неверная ширина колонки')
        ET.SubElement(cols,q('col'),min=str(ci),max=str(ci),width=str(width),customWidth='1')
    root.insert(1,cols)
    for row in root.findall(q('sheetData')+'/'+q('row')):
        for cell in row:
            letters=re.match('[A-Z]+',cell.get('r')).group(); ci=0
            for letter in letters: ci=ci*26+ord(letter)-64
            cell.set('s','1' if row.get('r')=='1' else str(indices[ci-1]+2))
    if protect: ET.SubElement(root,q('sheetProtection'),sheet='1',objects='1',scenarios='1',formatColumns='0',insertRows='0',deleteRows='0',sort='1',autoFilter='1')
    if indices:
        n=len(indices); last=''
        while n: n,r=divmod(n-1,26); last=chr(65+r)+last
        ET.SubElement(root,q('autoFilter'),ref=f'A1:{last}{len(sheet["rows"])+1}')
    # Browser financial rules: same thresholds/colors, resolved against this sheet's columns.
    scales={'margin':[0,15,30],'roi':[0,50,100],'deficit':[-20,0,20]}
    bars={'netProfit':'FF2FD6A3','specialFee':'FFFB923C','paymentTransfer':'FF38BDF8','acquiring':'FF5C9DFF',
          'price':'FF5C9DFF','effPrice':'FF38BDF8','stock':'FF2FD6A3','minStock':'FF98A2B3',
          'costPerUnit':'FFF7B32B','contribution':'FF8B7CFF','fixedTotal':'FF38BDF8','fcProfit':'FF8B7CFF',
          'sales':'FF2FD6A3','revenue':'FF5C9DFF','stockValue':'FFF7B32B','daysCover':'FF5C9DFF'}
    profit_keys={'netProfit','perUnitNet','fcProfit'}
    priority=0
    if sheet['rows']:
        for ci,index in enumerate(indices,1):
            key=meta[index].get('key'); n=ci; letter=''
            while n: n,r=divmod(n-1,26); letter=chr(65+r)+letter
            if key not in scales and key not in bars and key not in profit_keys: continue
            cf=ET.SubElement(root,q('conditionalFormatting'),sqref=f'{letter}2:{letter}{len(sheet["rows"])+1}')
            if key in scales:
                priority+=1
                rule=ET.SubElement(cf,q('cfRule'),type='colorScale',priority=str(priority)); scale=ET.SubElement(rule,q('colorScale'))
                for value in scales[key]: ET.SubElement(scale,q('cfvo'),type='num',val=str(value))
                for color in ['FFFF6B6B','FFFFD166','FF5FF0A6']: ET.SubElement(scale,q('color'),rgb=color)
            if key in profit_keys:
                for op,dxf in [('greaterThan',0),('lessThan',1)]:
                    priority+=1
                    rule=ET.SubElement(cf,q('cfRule'),type='cellIs',operator=op,dxfId=str(dxf),priority=str(priority))
                    ET.SubElement(rule,q('formula')).text='0'
            if key in bars:
                priority+=1
                rule=ET.SubElement(cf,q('cfRule'),type='dataBar',priority=str(priority)); bar=ET.SubElement(rule,q('dataBar'),showValue='1')
                ET.SubElement(bar,q('cfvo'),type='min'); ET.SubElement(bar,q('cfvo'),type='max')
                ET.SubElement(bar,q('color'),rgb=bars[key])
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)


def _xlsx_workbook(sheets, column_meta=None, protect=False):
    """Package worksheets produced by the common serializer into one workbook."""
    import xml.etree.ElementTree as ET
    main='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel='http://schemas.openxmlformats.org/package/2006/relationships'
    docrel='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    content='http://schemas.openxmlformats.org/package/2006/content-types'
    parts={}; sheet_xml=[]
    for i,sheet in enumerate(sheets,1):
        blob=_xlsx_from_rows(sheet['headers'],sheet['rows'],sheet['name'],formulas=sheet.get('formulas'))
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            if not parts: parts={n:archive.read(n) for n in archive.namelist()}
            xml=archive.read('xl/worksheets/sheet1.xml')
            if column_meta is not None:
                xml=_format_export_sheet(xml,sheet,column_meta,protect and i==1)
            sheet_xml.append(xml)
    if column_meta is not None:
        parts['xl/styles.xml']=_export_styles(column_meta)
    workbook=ET.fromstring(parts['xl/workbook.xml'])
    target=workbook.find('{'+main+'}sheets'); target.clear()
    relationships=ET.Element('{'+rel+'}Relationships')
    types=ET.fromstring(parts['[Content_Types].xml'])
    for child in list(types):
        if child.get('PartName','').startswith('/xl/worksheets/'): types.remove(child)
    for i,(sheet,xml) in enumerate(zip(sheets,sheet_xml),1):
        ET.SubElement(target,'{'+main+'}sheet',{'name':sheet['name'],'sheetId':str(i),'{'+docrel+'}id':'rId'+str(i)})
        ET.SubElement(relationships,'{'+rel+'}Relationship',{'Id':'rId'+str(i),'Type':docrel+'/worksheet','Target':f'worksheets/sheet{i}.xml'})
        ET.SubElement(types,'{'+content+'}Override',{'PartName':f'/xl/worksheets/sheet{i}.xml','ContentType':'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'})
        parts[f'xl/worksheets/sheet{i}.xml']=xml
    ET.SubElement(relationships,'{'+rel+'}Relationship',{'Id':'rIdStyles','Type':docrel+'/styles','Target':'styles.xml'})
    for path,root in [('xl/workbook.xml',workbook),('xl/_rels/workbook.xml.rels',relationships),('[Content_Types].xml',types)]:
        parts[path]=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
        for path,data in parts.items(): archive.writestr(path,data)
    return out.getvalue()


_DATA_EXPORT_SLOTS=threading.BoundedSemaphore(2)
def export_data_only_file(conn,columns,fmt,revision=None):
    """Two-pass disk snapshot and file output; returned file belongs to caller."""
    import tempfile
    if fmt not in ('csv','xlsx') or not isinstance(columns,list) or not columns:raise ValueError('Неверный формат или колонки')
    if any(not isinstance(c,dict) or not isinstance(c.get('key'),str) or not isinstance(c.get('name'),str) for c in columns):raise ValueError('Неверные колонки')
    if not _DATA_EXPORT_SLOTS.acquire(timeout=30):raise ValueError('Две выгрузки уже выполняются; повторите позже')
    output=None
    try:
        with tempfile.TemporaryFile(mode='w+t',encoding='utf-8') as snapshot:
            present=set();total=0
            def source(p,c):return (p.get('custom') or {}).get(c['key']) if c.get('custom') else p.get(c['key'])
            with conn:
                conn.execute('BEGIN')
                head=conn.execute('SELECT revision FROM app_catalog_head WHERE id=1').fetchone()
                if not head:raise ValueError('Каталог SQLite пуст')
                if revision is not None and revision!=head[0]:raise ValueError('Ревизия SQLite изменилась; повторите экспорт')
                for (raw,) in conn.execute('SELECT data FROM app_catalog_chunks WHERE revision=? ORDER BY part',(head[0],)):
                    chunk=json.loads(raw)
                    projected_batch=[]
                    for p in decode_special(chunk['rows'],chunk.get('special_values',[])):
                        # Project immediately; encode once per bounded SQL chunk,
                        # not once per cell/row. No calculation metadata in spool.
                        projected=[source(p,c) for c in columns]
                        present.update(i for i,v in enumerate(projected) if v is not None)
                        projected_batch.append(projected);total+=1
                    snapshot.write(json.dumps(projected_batch,ensure_ascii=False,default=str)+'\n')
            # End the read transaction BEFORE formatting or downloading, so a
            # slow client cannot pin old WAL pages indefinitely.
            if not total:raise ValueError('Каталог пуст')
            indices=[i for i,c in enumerate(columns) if c.get('custom') or i in present]
            cols=[columns[i] for i in indices]
            headers=[c['name']+(' [пользовательская: '+c['key']+']' if c.get('custom') else '') for c in cols]
            if fmt=='xlsx' and (len(cols)>16384 or total>1048575):raise ValueError('Превышен лимит XLSX; выберите CSV')
            def cell(v):
                if v is None:return ''
                if isinstance(v,bool):return 'true' if v else 'false'
                if isinstance(v,(dict,list)):return json.dumps(v,ensure_ascii=False,separators=(',',':'))
                if isinstance(v,float) and not math.isfinite(v):return str(v)
                return v
            snapshot.seek(0)
            values=([cell(row[i]) for i in indices] for line in snapshot for row in json.loads(line))
            output=tempfile.TemporaryFile(mode='w+b')
            if fmt=='csv':
                text=io.TextIOWrapper(output,encoding='utf-8-sig',newline='')
                try:
                    writer=csv.writer(text,delimiter=';',lineterminator='\r\n',quoting=csv.QUOTE_ALL)
                    writer.writerow([safe_csv_text(h) for h in headers])
                    for row in values:writer.writerow([safe_csv_text(v) for v in row])
                    text.flush()
                finally:text.detach()
            else:
                # Reuse the existing minimal workbook envelope, replacing only
                # sheet XML with a streaming ZIP member. No shared-string table.
                template=_xlsx_from_rows([],[],'Данные')
                with zipfile.ZipFile(io.BytesIO(template)) as src,zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as dst:
                    for name in src.namelist():
                        if name!='xl/worksheets/sheet1.xml':dst.writestr(name,src.read(name))
                    with dst.open('xl/worksheets/sheet1.xml','w',force_zip64=True) as sheet:
                        def write(text):sheet.write(text.encode('utf-8'))
                        write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>')
                        def letter(i):
                            out='';i+=1
                            while i:i,r=divmod(i-1,26);out=chr(65+r)+out
                            return out
                        letters=[letter(i) for i in range(len(cols))]
                        import itertools
                        for rn,row in enumerate(itertools.chain([headers],values),1):
                            write('<row r="'+str(rn)+'">')
                            for ci,v in enumerate(row):
                                if v is None or v=='':continue
                                ref=letters[ci]+str(rn)
                                if isinstance(v,(int,float)) and not isinstance(v,bool):write('<c r="'+ref+'"><v>'+str(v)+'</v></c>')
                                else:write('<c r="'+ref+'" t="inlineStr"><is><t xml:space="preserve">'+_xml_esc(v)+'</t></is></c>')
                            write('</row>')
                        write('</sheetData></worksheet>')
            output.seek(0);return output
    except BaseException:
        if output is not None:output.close()
        raise
    finally:_DATA_EXPORT_SLOTS.release()

def export_data_only(conn,columns,fmt):
    # Compatibility helper for direct callers/tests. HTTP uses the file path.
    with export_data_only_file(conn,columns,fmt) as output:return output.read()

def export_catalog_xlsx_bytes(conn, keys=None, columns=None, sheets=None, column_meta=None, protect=False):
    cols=columns if columns is not None else EXPORT_COLS
    rows=export_catalog_records(conn,keys)
    formulas={(ri,ci):r['__export_formulas'][k] for ri,r in enumerate(rows) for ci,(k,_) in enumerate(cols)
              if k in r.get('__export_formulas',{})}
    if sheets is not None:
        if not isinstance(sheets,list) or not 1<=len(sheets)<=10: raise ValueError('Неверный набор листов')
        names=set(); book=[]
        for sheet in sheets:
            name=sheet.get('name',''); indices=sheet.get('indices')
            if not isinstance(name,str) or not name or len(name)>31 or re.search(r'[\[\]:*?/\\]',name) or name.lower() in names:
                raise ValueError('Неверное имя листа')
            names.add(name.lower())
            if not isinstance(indices,list) or any(type(i) is not int or not 0<=i<len(cols) for i in indices): raise ValueError('Неверные колонки листа')
            book.append({'name':name,'indices':indices,'headers':[cols[i][1] for i in indices],
                'rows':[[r.get(cols[i][0]) for i in indices] for r in rows],
                'formulas':{(ri,ci):formulas[(ri,i)] for ri in range(len(rows)) for ci,i in enumerate(indices) if (ri,i) in formulas}})
        if column_meta is not None and (not isinstance(column_meta,list) or len(column_meta)!=len(cols) or any(not isinstance(c,dict) for c in column_meta)):
            raise ValueError('Неверные форматы колонок')
        return _xlsx_workbook(book,column_meta,protect)
    return _xlsx_from_rows([h for _,h in cols],[[r.get(k) for k,_ in cols] for r in rows],'Каталог',formulas=formulas)

# ---------------- выгрузка Ozon, 46 колонок (этап 1, v12.9.115) ----------------
OZON_HEADERS = ['№','Артикул*','Название товара','Предельная цена без акций, руб.*','Зачёркнутая цена, руб.',
  'НДС, %*','Рассрочка','Ускоренный сбор отзывов','Сбор первых отзывов','SKU','Штрихкод (Серийный номер / EAN)',
  'ТН ВЭД коды ЕАЭС*','Вес в упаковке, г*','Ширина упаковки, мм*','Высота упаковки, мм*','Длина упаковки, мм*',
  'Ссылка на главное фото*','Ссылки на дополнительные фото','Артикул фото','Бренд*','Партномер (артикул производителя)',
  'Тип*','Название модели (для объединения в одну карточку)*','Нужен код маркировки*','Количество в упаковке, шт',
  'Вес товара, г','Класс опасности товара','Количество товара в УЕИ','Минимальное количество оптом','#Хештеги',
  'Аннотация','Rich-контент JSON','Объединить в похожие товары','OEM-номер','Альтернативные артикулы товара',
  'Количество, штук','Внутренний диаметр, мм','Материал','Вид техники','Цвет товара','Гарантия',
  'Страна-изготовитель','Комплектация','Количество заводских упаковок','Ошибка','Недочёты']

def _split_codes(raw):
    return [x for x in (p.strip() for p in re.split(r'[,;/|]+', str(raw or ''))) if x]

_ASSET_CACHE = {}
def _asset(name):
    if name not in _ASSET_CACHE:
        import json as _json
        data = None
        for base in (Path(__file__).resolve().parent, BUNDLE, DATA):
            try:
                fp = base / name
                if fp.exists(): data = _json.loads(fp.read_text(encoding='utf-8')); break
            except Exception: pass
        _ASSET_CACHE[name] = data
    return _ASSET_CACHE[name]

def ozon_template_rows():
    t = _asset('ozon_template.json')
    return t if isinstance(t, list) and len(t) == 4 else None

def _std_norm(v):
    return re.sub(r'\s+', ' ', re.sub(r'[()\[\]\-_,.\xab\xbb/\\]', ' ', str(v or '').lower())).strip()

_STD_INDEX = None
def _std_match(p):
    """Стандартные ОВХ: только ТОЧНОЕ совпадение нормализованного названия
       (категория, затем название) со словарём приложения, одна подпись
       значений. Fuzzy/contains из StdDims.match(review) не портируем."""
    global _STD_INDEX
    dims = _asset('std_dims.json')
    if not dims: return None
    if _STD_INDEX is None:
        _STD_INDEX = {}
        for d in dims:
            _STD_INDEX.setdefault(_std_norm(d.get('c')), []).append(d)
    for cand in (p.get('category'), p.get('name')):
        hits = _STD_INDEX.get(_std_norm(cand)) if _std_norm(cand) else None
        if not hits: continue
        sigs = {(num(h.get('l')), num(h.get('w')), num(h.get('h')), num(h.get('wt'))) for h in hits}
        if len(sigs) == 1:
            l, w, h, wt = next(iter(sigs))
            return {'length': l, 'width': w, 'height': h, 'weight': wt, 'source': hits[0].get('c', '')}
    return None

def import_ozon_pairs(conn, pairs, replace=False):
    if not isinstance(pairs,list):raise ValueError('Неверный справочник категорий OZON')
    prepared=[]
    for pr in pairs:
        if not isinstance(pr,dict):raise ValueError('Неверная пара категорий OZON')
        cat = str(pr.get('category') or pr.get('cat') or '').strip()
        typ = str(pr.get('type') or pr.get('name') or '').strip()
        if not cat or not typ:
            if replace:raise ValueError('Пустая пара категорий OZON')
            continue
        prepared.append((cat,typ))
    with conn:
        conn.execute('CREATE TABLE IF NOT EXISTS ozon_pairs(category TEXT NOT NULL, type TEXT NOT NULL, PRIMARY KEY(category, type))')
        if replace:conn.execute('DELETE FROM ozon_pairs')
        conn.executemany('INSERT OR IGNORE INTO ozon_pairs VALUES(?,?)',prepared)
    return {'ok':True,'imported':len(prepared),'total':conn.execute('SELECT COUNT(*) FROM ozon_pairs').fetchone()[0]}

def _pairs_map(conn):
    try: rows = conn.execute('SELECT category,type FROM ozon_pairs').fetchall()
    except Exception: return {}
    out = {}
    for cat, typ in rows: out.setdefault(cat, []).append(typ)
    return out

def ozon_row(p, idx, vat='Не облагается', discount_pct=0, vehicle_type='Легковые автомобили'):
    return ozon_row_meta(p, idx, vat, discount_pct, vehicle_type)[0]

def ozon_row_meta(p, idx, vat='Не облагается', discount_pct=0, vehicle_type='Легковые автомобили',
                  pairs=None, chz_codes=None):
    """Строка шаблона Ozon из полей карточки. Правила приложения, которые
       портированы 1-в-1: цена не выдумывается (нет цены — пустая ячейка);
       зачёркнутая — только явная старая цена выше цены или выбранная
       продавцом надбавка; габариты сортируются длина>=ширина>=высота;
       вес в граммы, размеры в миллиметры; аннотация — описание или
       шаблон «Название. Артикул детали: … Производитель: …»."""
    art = str(p.get('article', '')).strip()
    name = str(p.get('name', '')).strip()
    brand = str(p.get('brand', '')).strip()
    price = num(p.get('price'))
    price_out = int(round(price)) if price > 0 else ''
    old = num(p.get('old_price'))
    if old > price and price > 0: old_out = int(round(old))
    elif discount_pct > 0 and price > 0: old_out = int(round(price * (1 + discount_pct / 100)))
    else: old_out = ''
    std_fields = []
    p = dict(p)
    if not all(num(p.get(k)) > 0 for k in ('length', 'width', 'height', 'weight')):
        std = _std_match(p)
        if std:
            key = {'length': 'length', 'width': 'width', 'height': 'height', 'weight': 'weight'}
            for k in ('length', 'width', 'height', 'weight'):
                if not num(p.get(k)) > 0 and std[key[k]] > 0:
                    p[k] = std[key[k]]; std_fields.append(k)
    ozon_type = str(p.get('ozon_type', '')).strip()
    ozon_cat = str(p.get('ozon_category', '')).strip()
    pair_bad = False
    if pairs:
        if not ozon_type and ozon_cat and len(pairs.get(ozon_cat, [])) == 1:
            ozon_type = pairs[ozon_cat][0]
        if ozon_type and not ozon_cat:
            cats = [c for c, ts in pairs.items() if ozon_type in ts]
            if len(cats) == 1: ozon_cat = cats[0]
        pair_bad = bool(ozon_type and ozon_cat and ozon_type not in pairs.get(ozon_cat, []))
    mark = str(p.get('mark_required', ''))
    tnved_digits = re.sub(r'\D', '', str(p.get('tnved', '')))
    chz_hit = bool(chz_codes) and any(tnved_digits.startswith(re.sub(r'\D', '', str(c))) for c in chz_codes if str(c).strip())
    if chz_hit and not mark: mark = 'Да'
    def grams(v): return int(round(num(v) * 1000)) if num(v) > 0 and round(num(v) * 1000) > 0 else ''
    def millis(v): return int(round(num(v) * 10)) if num(v) > 0 and round(num(v) * 10) > 0 else ''
    dims = [millis(p.get('length')), millis(p.get('width')), millis(p.get('height'))]
    if all(isinstance(d, int) for d in dims):
        dims.sort(reverse=True)  # длина — наибольшее, высота — наименьшее (документация Ozon)
        length_mm, width_mm, height_mm = dims
    else:
        width_mm, height_mm, length_mm = dims[1], dims[2], dims[0]
    oem = '; '.join(_split_codes(p.get('oe_numbers')))
    cross = '; '.join(c for c in _split_codes(p.get('cross_numbers') or p.get('group_articles'))
                      if c != art and c != oem)
    bnorm = _norm_article(brand).lower()
    hashtags = ('#автозапчасти #запчасти' + (' #' + bnorm if bnorm else '')).strip()
    annotation = (str(p.get('description', '')).strip() or f'{name}. Артикул детали: {art}. Производитель: {brand}.')[:6000]
    model = str(p.get('group_articles') or p.get('model') or art)
    errors, notes = [], []
    if not brand: errors.append('не заполнен бренд')
    if not ozon_type: errors.append('не определён тип Ozon')
    if pair_bad: errors.append('пара «категория/тип» не найдена в справочнике Ozon')
    if std_fields: notes.append('СТАНДАРТ (не измерено): ОВХ из справочника — ' + ', '.join(std_fields))
    if chz_hit: notes.append('ЧЗ по списку ТН ВЭД')
    if not name: errors.append('не заполнено название товара')
    _tnv = str(p.get('tnved', '')).strip()
    if not _tnv: notes.append('нет кода ТН ВЭД (Ozon требует для автозапчастей)')
    elif len(re.sub(r'\D', '', _tnv)) != 10: errors.append('ТН ВЭД должен быть 10 цифр')
    if not grams(p.get('weight')) or not all(isinstance(d, int) for d in (width_mm, height_mm, length_mm)):
        errors.append('не заполнены ОВХ (вес/габариты)')
    if not str(p.get('image_url', '')).strip(): notes.append('нет ссылки на главное фото — товар загрузится, но не выйдет в продажу, пока фото не добавят')
    if not str(p.get('barcode', '')).strip(): notes.append('нет штрихкода — Ozon не сможет принять поставку без него')
    if not price_out: errors.append('не заполнена цена')
    row = [idx, art, name, price_out, old_out, vat, '', '', '', str(p.get('ozon_sku', '')),
            str(p.get('barcode', '')), str(p.get('tnved', '')), grams(p.get('weight')), width_mm, height_mm, length_mm,
            str(p.get('image_url', '')), str(p.get('extra_photos', '')), '', brand,
            str(p.get('original_article', '')).strip() or art,
            ozon_type, model, mark,
            max(1, int(round(num(p.get('multiplicity')) or 1))),
            (round(num(p.get('net_weight')) * 1000, 6) if num(p.get('net_weight')) > 0 else ''),
            str(p.get('hazard_class', '')), '', '', hashtags, annotation,
            str(p.get('rich_content', ''))[:32767], str(p.get('group_articles', '')), oem, cross, '1',
            str(p.get('diameter', '')), str(p.get('material', '')), vehicle_type, str(p.get('color', '')),
            str(p.get('warranty', '')), str(p.get('country', '')),
            str(p.get('package_contents', '')).strip() or f'{name} - 1 шт., упаковка', '1',
            '; '.join(errors), '; '.join(notes)]
    cols = {'weight': 12, 'width': 13, 'height': 14, 'length': 15}
    return row, {cols[k] for k in std_fields}

def _ozon_rows_data(conn, keys=None, discount_pct=0, vat='Не облагается', chz_codes=None):
    pairs = _pairs_map(conn) or None
    rows = conn.execute('SELECT * FROM products ORDER BY article,brand').fetchall()
    out, yellow = [], set()
    for r in rows:
        d = dict(r)
        # v12.9.153: скрытые SKU (visible=false в приложении) в выгрузку Ozon не идут
        if str(d.get('visible', '1')).lower() in ('0', '0.0', 'false', 'нет'): continue
        if str(d.get('excluded', '0')).lower() in ('1', 'true', 'да'): continue
        if keys is not None and (d['article'], d['brand']) not in keys: continue
        row, std_cols = ozon_row_meta(d, len(out) + 1, vat=vat, discount_pct=discount_pct,
                                      pairs=pairs, chz_codes=chz_codes)
        for c in std_cols: yellow.add((len(out), c))
        out.append(row)
    return out, yellow

def export_ozon_csv_bytes(conn, discount_pct=0, vat='Не облагается', enc='utf-8', keys=None, chz_codes=None):
    import csv as _csv
    buf = io.StringIO(); w = _csv.writer(buf, delimiter=';')
    w.writerow(OZON_HEADERS)
    for row in _ozon_rows_data(conn, keys, discount_pct, vat, chz_codes)[0]:
        w.writerow([safe_csv_text(v) for v in row])
    text = buf.getvalue()
    return encode_csv(text,enc)

def export_ozon_xlsx_bytes(conn, discount_pct=0, vat='Не облагается', keys=None, chz_codes=None):
    rows, yellow = _ozon_rows_data(conn, keys, discount_pct, vat, chz_codes)
    tpl = ozon_template_rows()
    if tpl:
        return _xlsx_from_rows(tpl[1], rows, 'Ozon', header_rows=[tpl[0], tpl[2], tpl[3]], yellow=yellow)
    return _xlsx_from_rows(OZON_HEADERS, rows, 'Ozon', yellow=yellow)

# ---------------- HTTP ----------------
def _app_html_path():
    for cand in (BASE.parent / 'index.html', BUNDLE / 'index.html',
                 Path(sys.executable).resolve().parent / 'index.html', Path.cwd() / 'index.html'):
        if cand.exists(): return cand
    return None

_XLSX_JS = None

def _extract_xlsx(html):
    """v12.9.128: SheetJS выносится из inline-блока во внешний /lib/xlsx.js.
       У пользователя inline-блок не исполнялся (код текстом + Invalid or
       unexpected token) при байт-в-байт исправном файле — виновато
       взаимодействие библиотеки с HTML-парсером script-данных. Внешний
       скрипт HTML-парсер не трогает вовсе. На диске index.html прежний:
       открытие файлом работает как раньше."""
    global _XLSX_JS
    start = html.find('<script>/*! xlsx встроен офлайн')
    if start < 0: return html
    end = html.find('</script>', start)
    if end < 0: return html
    js = html[html.find('\n', start):end]
    if 'xlsx.js' not in js: return html
    _XLSX_JS = js.encode('utf-8')
    return html[:start] + '<script src="/lib/xlsx.js"></script>' + html[end + len('</script>'):]

_APP_HTML_CACHE = {'key': None, 'body': None}
def render_app_html():
    """Приложение с авто-токеном: страница отдана самим движком с его же адреса,
       поэтому токен можно вшить в HTML — пользователю не нужно ничего вставлять.
       Чужой сайт прочитать эту страницу не может (нет CORS-заголовка на /)."""
    app_file = _app_html_path()
    if app_file is None: return None
    try: key = (str(app_file), app_file.stat().st_mtime_ns, app_file.stat().st_size)
    except OSError: key = None
    if key and _APP_HTML_CACHE['key'] == key: return _APP_HTML_CACHE['body']
    html = app_file.read_text(encoding='utf-8')
    html = _extract_xlsx(html)
    inject = '<script>window.__UC_PY_TOKEN__=' + json.dumps(get_token()) + ';</script>'
    if '</head>' in html: html = html.replace('</head>', inject + '</head>', 1)
    else: html = inject + html
    body = html.encode('utf-8')
    if key: _APP_HTML_CACHE.update(key=key, body=body)
    return body

_TOKEN_CACHE = None
def get_token():
    global _TOKEN_CACHE
    if _TOKEN_CACHE: return _TOKEN_CACHE
    if not TOKEN_PATH.exists():
        TOKEN_PATH.write_text(os.urandom(18).hex(), encoding='utf-8')
    _TOKEN_CACHE = TOKEN_PATH.read_text(encoding='utf-8').strip()
    return _TOKEN_CACHE

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _host_ok(self):
        # A1 (аудит v12.9.133): без проверки Host вредоносный сайт через
        # DNS-rebinding читает страницу с вшитым токеном. Принимаем только
        # локальные имена; порт не сверяем — движок может быть на другом.
        h = (self.headers.get('Host', '') or '').strip().lower()
        host = h.rsplit(':', 1)[0] if ':' in h else h
        return host in ('127.0.0.1', 'localhost', '[::1]', '::1')
    def _send_disk_full(self):
        # «database or disk is full» пользователю ни о чём не говорит — объясняем
        import shutil as _sh
        try: free_mb = round(_sh.disk_usage(str(DATA)).free / 1048576)
        except Exception: free_mb = None
        try: db_mb = round(DB_PATH.stat().st_size / 1048576, 1) if DB_PATH.exists() else 0
        except Exception: db_mb = 0
        return self._send(507, {'ok': False, 'error':
            'Не хватает места на диске для базы движка (свободно ' + str(free_mb) + ' МБ, база каталога ' + str(db_mb) +
            ' МБ в папке engine_data рядом с движком). Освободите место на этом диске (минимум 1–2 ГБ: Очистка диска, Корзина), '
            'перезапустите движок и повторите. Каталог в приложении при этом не пострадал.'})
    def _deny_bad_host(self):
        if self._host_ok(): return False
        self._send(403, {'ok': False, 'error': 'Host не разрешён'})
        return True
    def _send_bytes(self, code, body, content_type, filename, export_warnings=None):
        # gzip только для текстовых типов: CSV/JSON/XML сжимаются кратно;
        # XLSX уже zip — повторное сжатие бесполезно.
        extra = {}
        if content_type.startswith('text/') or 'json' in content_type:
            body, extra = self._maybe_gzip(body)
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-UC-Token')
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        if export_warnings:
            self.send_header('Access-Control-Expose-Headers','X-UC-Export-Warnings')
            self.send_header('X-UC-Export-Warnings',json.dumps(export_warnings,separators=(',',':')))
        for k, v in extra.items(): self.send_header(k, v)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def _send_file(self,output,content_type,filename):
        output.seek(0,2);size=output.tell();output.seek(0)
        self.send_response(200)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
        self.send_header('Content-Length',str(size))
        self.send_header('Access-Control-Allow-Origin','*')
        self.end_headers()
        # No whole-file gzip copy; ZIP is already compressed. Caller closes
        # the temporary file even after disconnect/BrokenPipe.
        try:shutil.copyfileobj(output,self.wfile,1024*1024)
        except (BrokenPipeError,ConnectionResetError):return

    def _maybe_gzip(self, body):
        if len(body) < 1024 or 'gzip' not in (self.headers.get('Accept-Encoding', '') or ''): return body, {}
        import gzip as _gz
        return _gz.compress(body, compresslevel=6), {'Content-Encoding': 'gzip'}
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        body, extra = self._maybe_gzip(body)
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-UC-Token')
        for k, v in extra.items(): self.send_header(k, v)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def do_OPTIONS(self):
        if self._deny_bad_host(): return
        self._send(200, {'ok': True})
    def _auth(self):
        import hmac as _hmac
        return _hmac.compare_digest(self.headers.get('X-UC-Token', ''), get_token())
    def _body(self):
        ln = int(self.headers.get('Content-Length', 0) or 0)
        if ln > 50 * 1024 * 1024:  # A5: потолок JSON-тела
            raise ValueError('тело запроса больше 50 МБ')
        raw = self.rfile.read(ln) if ln else b'{}'
        try: return json.loads(raw.decode('utf-8') or '{}')
        except Exception: return {}
    def do_GET(self):
        if self._deny_bad_host(): return
        if self.path in ('/', '/index.html', '/app'):
            # одно окно: приложение отдаёт сам движок с того же адреса
            body = render_app_html()
            if body is not None:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                # v12.9.123: страницу приложения нельзя кэшировать — иначе после
                # обновления файлов браузер показывает старую копию (был случай:
                # баннер «SheetJS не загрузился» на уже исправленной версии).
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
                return
            return self._send(404, {'ok': False, 'error': 'index.html не найден рядом с движком'})
        if self.path == '/lib/xlsx.js':
            if _XLSX_JS is None:
                render_app_html()
            if _XLSX_JS is None: return self._send(404, {'ok': False, 'error': 'xlsx не найден в index.html'})
            self.send_response(200)
            self.send_header('Content-Type', 'application/javascript; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(_XLSX_JS)))
            self.end_headers(); self.wfile.write(_XLSX_JS)
            return
        if self.path == '/health':
            return self._send(200, {'ok': True, 'service': 'UC-PyEngine', 'version': VERSION})
        if self.path == '/diag':
            # v12.9.126: диагностика «что движок реально отдаёт» — для случаев,
            # когда у пользователя страница выглядит не так, как в репозитории.
            import hashlib
            info = {'engine_version': VERSION, 'frozen': bool(FROZEN)}
            ap = _app_html_path()
            info['app_path'] = str(ap) if ap else None
            try:
                import shutil as _sh
                info['disk_free_mb'] = round(_sh.disk_usage(str(DATA)).free / 1048576)
            except Exception: pass
            try: info['db_size_mb'] = round(DB_PATH.stat().st_size / 1048576, 1) if DB_PATH.exists() else 0
            except Exception: pass
            if ap:
                raw = ap.read_bytes()
                info['app_size'] = len(raw)
                info['app_sha256'] = hashlib.sha256(raw).hexdigest()[:16]
                txt = raw.decode('utf-8', errors='replace')
                info['xlsx_executable_script'] = '<script>/*! xlsx' in txt
                info['xlsx_textplain_block'] = 'id="xlsx-lib"' in txt
                info['has_token_inject_point'] = '</head>' in txt
            return self._send(200, {'ok': True, **info})
        if not self._auth(): return self._send(401, {'ok': False, 'error': 'X-UC-Token'})
        conn = db()
        if self.path == '/secrets/status':
            return self._send(200, {'ok': True, 'keys': sorted(k for k in secrets() if k.startswith('UC_SET_'))})
        if self.path == '/secrets/values':
            # B6: значения отдаются только авторизованному локальному клиенту и
            # только в память вкладки — на диск браузера они больше не пишутся.
            vals = {k[len('UC_SET_'):]: v for k, v in secrets().items() if k.startswith('UC_SET_') and v}
            return self._send(200, {'ok': True, 'values': vals})
        if self.path == '/report/summary': return self._send(200, {'ok': True, **summary_report(conn)})
        if self.path == '/report/dashboard': return self._send(200, {'ok': True, **dashboard_report(conn)})
        if self.path.startswith('/analogs/suggestions'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            return self._send(200, {'ok': True, **analog_suggestions(conn, (qs.get('limit') or ['100'])[0])})
        if self.path.startswith('/report/price-changes'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            return self._send(200, {'ok': True, **price_changes(conn, (qs.get('days') or ['30'])[0])})
        if self.path.startswith('/snapshots/diff'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            return self._send(200, {'ok': True, **snapshot_diff(conn, int(num((qs.get('from') or ['0'])[0])), int(num((qs.get('to') or ['0'])[0])))})
        if self.path == '/snapshots':
            rows = conn.execute('SELECT id,created,note,total FROM snapshots ORDER BY id DESC LIMIT 50').fetchall()
            return self._send(200, {'ok': True, 'rows': [dict(r) for r in rows]})
        if self.path.startswith('/parse/rows'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            sid = (qs.get('parse_id') or [''])[0]
            off = int(num((qs.get('offset') or ['0'])[0])); lim = min(5000, int(num((qs.get('limit') or ['1000'])[0])) or 1000)
            rows = conn.execute('SELECT data FROM parse_rows WHERE session=? AND idx>=? ORDER BY idx LIMIT ?', (sid, max(0,off), max(1,lim))).fetchall()
            total = conn.execute('SELECT total FROM parse_sessions WHERE id=?', (sid,)).fetchone()
            if total is None: return self._send(404, {'ok': False, 'error': 'parse_id не найден'})
            return self._send(200, {'ok': True, 'total': total[0], 'rows': [json.loads(r[0]) for r in rows]})
        if self.path.startswith('/export/ozon.xlsx'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            chz = [x for x in (qs.get('chz') or [''])[0].split(',') if x.strip()] or None
            data = export_ozon_xlsx_bytes(conn,
                discount_pct=num((qs.get('discount_pct') or ['0'])[0]),
                vat=(qs.get('vat') or ['Не облагается'])[0], chz_codes=chz)
            return self._send_bytes(200, data,
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'UC_ozon_engine.xlsx')
        if self.path.startswith('/export/ozon.csv'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            chz = [x for x in (qs.get('chz') or [''])[0].split(',') if x.strip()] or None
            return self._send_bytes(200, export_ozon_csv_bytes(conn,
                discount_pct=num((qs.get('discount_pct') or ['0'])[0]),
                vat=(qs.get('vat') or ['Не облагается'])[0],
                enc=(qs.get('enc') or ['utf-8'])[0], chz_codes=chz),
                'text/csv; charset=utf-8', 'UC_ozon_engine.csv')
        if self.path.startswith('/export/catalog'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            enc = (qs.get('enc') or ['utf-8'])[0]
            if '.xlsx' in self.path or (qs.get('format') or [''])[0] == 'xlsx':
                return self._send_bytes(200, export_catalog_xlsx_bytes(conn),
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'UC_catalog_engine.xlsx')
            return self._send_bytes(200, export_catalog_csv_bytes(conn, enc),
                'text/csv; charset=' + ('windows-1251' if enc == 'cp1251' else 'utf-8'), 'UC_catalog_engine.csv')
        if self.path.startswith('/search'):
            from urllib.parse import urlparse, parse_qs
            q = (parse_qs(urlparse(self.path).query).get('q', [''])[0] or '').strip()
            rows = conn.execute('''SELECT p.article,p.brand,p.name,p.price,p.stock FROM products p
                WHERE p.rowid IN (SELECT rowid FROM products_fts WHERE products_fts MATCH ?) LIMIT 100''',
                ('"' + q.replace('"', '') + '"',)).fetchall() if q else []
            return self._send(200, {'ok': True, 'rows': [dict(r) for r in rows]})
        if self.path.startswith('/app/catalog'):
            from urllib.parse import urlparse, parse_qs
            qs=parse_qs(urlparse(self.path).query)
            try:
                args={'part':int((qs.get('part') or ['0'])[0])}
                if 'revision' in qs:args['revision']=qs['revision'][0]
                return self._send(200,{'ok':True,**app_catalog_state(conn,'read',args)})
            except (ValueError,TypeError) as e:return self._send(409,{'ok':False,'error':str(e)})
        if self.path.startswith('/catalog/products'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            off = int(num((qs.get('offset') or ['0'])[0])); lim = min(5000, int(num((qs.get('limit') or ['1000'])[0])) or 1000)
            rows = conn.execute('SELECT article,brand,name,price,cost,stock,sales,weight,length,width,height,volume,oe_numbers,analog_list,category,tnved,applicability,warranty,country,group_articles,cross_numbers,barcode,category_type,ozon_category,ozon_type,description,dimension_review,dimension_context FROM products ORDER BY article,brand LIMIT ? OFFSET ?', (lim, off)).fetchall()
            total = conn.execute('SELECT COUNT(*) c FROM products').fetchone()['c']
            return self._send(200, {'ok': True, 'total': total, 'rows': [dict(r) for r in rows]})
        if self.path.startswith('/catalog/results'):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            off = int(num((qs.get('offset') or ['0'])[0])); lim = min(5000, int(num((qs.get('limit') or ['1000'])[0])) or 1000)
            rows = conn.execute('SELECT article,brand,total,profit,margin,roi,break_even,target,fields_json FROM eco_results ORDER BY article,brand LIMIT ? OFFSET ?', (lim, off)).fetchall()
            total = conn.execute('SELECT COUNT(*) c FROM eco_results').fetchone()['c']
            return self._send(200, {'ok': True, 'total': total, 'rows': [dict(r) for r in rows]})
        if self.path == '/outbox':
            rows = conn.execute('SELECT id,kind,marketplace,article,status,attempts,last_error,created_at,sent_at FROM outbox ORDER BY id DESC LIMIT 200').fetchall()
            return self._send(200, {'ok': True, 'rows': [dict(r) for r in rows]})
        return self._send(404, {'ok': False, 'error': 'not found'})
    def do_POST(self):
        if self._deny_bad_host(): return
        if not self._auth(): return self._send(401, {'ok': False, 'error': 'X-UC-Token'})
        if self.path == '/import/file':
            # бинарное тело НЕЛЬЗЯ читать через _body() (JSON): читаем один раз здесь
            from urllib.parse import unquote
            fname = unquote(self.headers.get('X-Filename', 'file.csv'))
            try: ln = int(self.headers.get('Content-Length', 0) or 0)
            except (ValueError,TypeError):return self._send(400, {'ok':False,'error':'Неверный Content-Length'})
            if ln<0:return self._send(400, {'ok':False,'error':'Неверный Content-Length'})
            if ln > 200 * 1024 * 1024:  # A5: потолок файла загрузки
                return self._send(413, {'ok': False, 'error': 'файл больше 200 МБ'})
            data = self.rfile.read(ln) if ln else b''
            try:
                return self._send(200, {'ok': True, **import_file_bytes(db(), fname, data, enrich_only=(self.headers.get('X-Import-Mode', '') == 'enrich'),
                    mapping=json.loads(unquote(self.headers['X-Import-Mapping'])) if self.headers.get('X-Import-Mapping') else None)})
            except Exception as e:
                # v12.9.144: этот путь раньше возвращал сырой 'database or disk is full'
                if isinstance(e, DiskFullError) or 'disk is full' in str(e) or 'database or disk' in str(e):
                    return self._send_disk_full()
                return self._send(500, {'ok': False, 'error': str(e)[:300]})
        if self.path == '/parse/file':
            from urllib.parse import unquote
            fname = unquote(self.headers.get('X-Filename', 'file.csv'))
            try: ln = int(self.headers.get('Content-Length', 0) or 0)
            except (ValueError,TypeError):return self._send(400, {'ok':False,'error':'Неверный Content-Length'})
            if ln<0:return self._send(400, {'ok':False,'error':'Неверный Content-Length'})
            if ln > 200 * 1024 * 1024:  # A5: потолок файла загрузки
                return self._send(413, {'ok': False, 'error': 'файл больше 200 МБ'})
            data = self.rfile.read(ln) if ln else b''
            try:
                return self._send(200, {'ok': True, **parse_file_bytes(db(), fname, data, catalog_import=self.headers.get('X-Catalog-Import')=='1')})
            except Exception as e:
                if isinstance(e, DiskFullError) or 'disk is full' in str(e) or 'database or disk' in str(e):
                    return self._send_disk_full()
                return self._send(500, {'ok': False, 'error': str(e)[:300]})
        try:
            body = self._body()
        except ValueError as e:
            return self._send(413, {'ok': False, 'error': str(e)})
        conn = db()
        try:
            if self.path == '/calc/batch':
                st = body.get('settings') or {}
                results = [calc_row(r, st) for r in (body.get('rows') or [])[:5000]]
                return self._send(200, {'ok': True, 'results': results})
            if self.path == '/catalog/sync':
                return self._send(200, {'ok':True, **sync_catalog_snapshot(conn,body)})
            if self.path == '/import/rows':
                n = import_rows(conn, body.get('rows') or [], body.get('source', 'app'),
                                rebuild_fts=body.get('final') is not False)
                return self._send(200, {'ok': True, 'imported': n})
            if self.path == '/app/catalog':
                return self._send(200,{'ok':True,**app_catalog_state(conn,body.get('action'),body)})
            if self.path == '/catalog/enrich':
                return self._send(200, {'ok': True, **enrich_oe(conn)})
            if self.path == '/donors/import':
                n = import_donors(conn, body.get('rows') or [], body.get('source', 'app'))
                return self._send(200, {'ok': True, 'imported': n})
            if self.path == '/catalog/hvc-reference':
                return self._send(200,{'ok':True,**hvc_reference_upload(conn,body)})
            if self.path == '/catalog/enrich-hvc-rows':
                return self._send(200,{'ok':True,**enrich_hvc_input_rows(conn,body.get('rows') or [],body.get('reference'),body.get('mode','auto'),body.get('cat_mode','artbrand'),body.get('columns'),body.get('policy'),body.get('reference_id'))})
            if self.path == '/catalog/check-mark-status':
                return self._send(200, {'ok':True, **check_mark_status_rows(conn, body.get('rows') or [], body.get('settings') or {}, body.get('special_values'))})
            if self.path == '/catalog/enrich-category-tnved':
                return self._send(200, {'ok':True, **enrich_category_tnved(conn, body.get('rows') or [],
                    body.get('reference'), body.get('enabled') is not False)})
            if self.path == '/catalog/dimension-oe':
                return self._send(200, {'ok':True, **dimension_oe_operation(conn,body.get('snapshot') or {},body.get('operation','find'),body.get('token'),body.get('selected'))})
            if self.path == '/catalog/fix-dimension-units':
                return self._send(200, {'ok':True, **fix_dimension_units(conn,body.get('items') or [],body.get('limits') or [],body.get('oe_mode','auto'),body.get('approved') is True,body.get('labels') or {})})
            if self.path == '/catalog/confirm-dimensions':
                return self._send(200, {'ok':True, **confirm_dimension_row(conn,body.get('row') or {},body.get('limits') or [],body.get('oe_mode','auto'),body.get('approved') is True,body.get('expected_signature'))})
            if self.path == '/catalog/quarantine-dimensions':
                return self._send(200, {'ok':True, **quarantine_dimension_rows(conn,body.get('rows') or [],body.get('limits') or [],body.get('oe_mode','auto'))})
            if self.path == '/catalog/apply-policies':
                return self._send(200, {'ok':True, **apply_product_policies(conn,body.get('rows') or [],body.get('rules') or [])})
            if self.path == '/catalog/ozon-reference':
                return self._send(200,{'ok':True,**ozon_reference_upload(conn,body)})
            if self.path == '/catalog/enrich-ozon-preferred':
                return self._send(200, {'ok':True, **enrich_ozon_preferred(conn,body.get('rows') or [],body.get('reference'),body.get('enabled') is not False,body.get('force') is True,body.get('force_name') is True,reference_id=body.get('reference_id'))})
            if self.path == '/catalog/classify-ozon':
                return self._send(200, {'ok':True, **classify_ozon_rows(conn,body.get('rows') or [],body.get('reference'),body.get('operation','classify'),body.get('force') is True)})
            if self.path == '/catalog/enrich-rules':
                return self._send(200, {'ok':True, **enrich_rule_rows(conn,body.get('rows') or [],
                    body.get('rules') or [],body.get('context') or {},body.get('special_values'))})
            if self.path == '/catalog/enrich-category-kind':
                return self._send(200, {'ok':True, **enrich_category_kinds(conn,body.get('rows') or [],
                    body.get('reference'),body.get('context') or {},body.get('enabled') is not False,
                    body.get('operation','apply'),body.get('category_confirmed') is True)})
            if self.path == '/catalog/enrich-name-category':
                return self._send(200, {'ok': True, **enrich_name_categories(conn,
                    body.get('rows') or [], body.get('context') or {}, body.get('enabled') is not False)})
            if self.path == '/catalog/enrich-hvc':
                return self._send(200, {'ok': True, **enrich_hvc(conn, body.get('reference'),
                    body.get('mode') or 'auto', body.get('cat_mode') or 'artbrand', body.get('columns'), body.get('policy'))})
            if self.path == '/catalog/enrich-full':
                return self._send(200, {'ok': True, **enrich_full(conn, body.get('cat_mode') or 'artbrand', body.get('enrich_mode') or 'auto', body.get('enrich_cols'), body.get('dimension_policy'), body.get('oe_registry'))})
            if self.path == '/catalog/whatif':
                return self._send(200, {'ok': True, **whatif_catalog(conn, body.get('settings') or {},
                    body.get('scenario_settings') or {}, body.get('overrides'), body.get('scenario_inputs'))})
            if self.path == '/catalog/recalc':
                return self._send(200, {'ok': True, **recalc_catalog(conn, body.get('settings') or {}, force=bool(body.get('force')))})
            if self.path.startswith('/catalog/results'):
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                off = int(num((qs.get('offset') or ['0'])[0])); lim = min(5000, int(num((qs.get('limit') or ['1000'])[0])) or 1000)
                rows = conn.execute('SELECT article,brand,total,profit,margin,roi,break_even,target,fields_json FROM eco_results ORDER BY article,brand LIMIT ? OFFSET ?', (lim, off)).fetchall()
                total = conn.execute('SELECT COUNT(*) c FROM eco_results').fetchone()['c']
                return self._send(200, {'ok': True, 'total': total, 'rows': [dict(r) for r in rows]})
            if self.path == '/snapshots':
                return self._send(200, {'ok': True, **make_snapshot(conn, body.get('note', ''))})
            if self.path == '/ozon/pairs/import':
                return self._send(200, import_ozon_pairs(conn, body.get('pairs') or [], replace=body.get('replace') is True))
            if self.path == '/export/ozon.csv':
                keys = None
                if body.get('articles') is not None:
                    keys = {(str(a.get('article', '')), str(a.get('brand', ''))) for a in body['articles']}
                return self._send_bytes(200, export_ozon_csv_bytes(conn,
                    discount_pct=num(body.get('discount_pct')), vat=body.get('vat') or 'Не облагается', keys=keys,
                    chz_codes=body.get('chz_codes')),
                    'text/csv; charset=utf-8', 'UC_ozon_engine.csv')
            if self.path == '/export/ozon.xlsx':
                keys = None
                if body.get('articles') is not None:
                    keys = {(str(a.get('article', '')), str(a.get('brand', ''))) for a in body['articles']}
                return self._send_bytes(200, export_ozon_xlsx_bytes(conn,
                    discount_pct=num(body.get('discount_pct')), vat=body.get('vat') or 'Не облагается', keys=keys,
                    chz_codes=body.get('chz_codes')),
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'UC_ozon_engine.xlsx')
            if self.path in ('/export/data-only.csv','/export/data-only.xlsx'):
                fmt='xlsx' if self.path.endswith('.xlsx') else 'csv'
                with export_data_only_file(conn,body.get('columns'),fmt,body.get('revision')) as output:
                    return self._send_file(output,'text/csv; charset=utf-8' if fmt=='csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','UC_data_only.'+fmt)
            if self.path.startswith('/export/catalog'):
                # Filter before generating row-relative formulas; filtering a
                # prepared snapshot afterwards would leave references shifted.
                if body.get('formula_options') is not None and body.get('articles') is not None:
                    wanted={(str(a.get('article','')),str(a.get('brand',''))) for a in body['articles']}
                    body['export_cells']=[c for c in body.get('export_cells',[]) if (str(c.get('article','')),str(c.get('brand',''))) in wanted]
                export_warnings=None
                if body.get('export_cells') is not None:
                    export_warnings=store_export_cells(conn,body['export_cells'],body.get('columns'),body.get('column_meta'),body.get('formula_options'),body.get('sheets'))
                else:
                    conn.execute('DROP TABLE IF EXISTS temp.export_cells')
                keys = None
                if body.get('articles') is not None:
                    keys = [(str(a.get('article', '')), str(a.get('brand', ''))) for a in body['articles']]
                if '.xlsx' in self.path:
                    return self._send_bytes(200, export_catalog_xlsx_bytes(conn, keys=keys, columns=body.get('columns'), sheets=body.get('sheets'), column_meta=body.get('column_meta'), protect=body.get('protect') is True),
                        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'UC_catalog_engine.xlsx',export_warnings)
                return self._send_bytes(200, export_catalog_csv_bytes(conn, body.get('enc') or 'utf-8', keys=keys, columns=body.get('columns'), delimiter=body.get('delimiter',';')),
                    'text/csv; charset=utf-8', 'UC_catalog_engine.csv')
            if self.path == '/outbox':
                n = enqueue(conn, body.get('kind', ''), body.get('marketplace', ''), body.get('items') or [])
                return self._send(200, {'ok': True, 'queued': n})
            if self.path == '/outbox/process':
                return self._send(200, {'ok': True, **process_outbox(int(num(body.get('limit', 100))) or 100)})
            if self.path == '/mail/check':
                return self._send(200, {'ok': True, **mail_check_once(get_settings(conn))})
            if self.path == '/folder/check':
                return self._send(200, {'ok': True, **watch_folder_once(body.get('folder'))})
            if self.path == '/backup':
                return self._send(200, {'ok': True, **make_backup()})
            if self.path == '/settings':
                for sk, sv in (body.get('secrets') or {}).items():
                    save_secret(str(sk), str(sv))  # A3: на Windows уйдёт в DPAPI
                for k, v in (body.get('settings') or {}).items():
                    conn.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                                 (str(k), str(v)))
                conn.commit()
                return self._send(200, {'ok': True})
        except Exception as e:
            if isinstance(e, DiskFullError) or 'disk is full' in str(e) or 'database or disk' in str(e):
                return self._send_disk_full()
            return self._send(500, {'ok': False, 'error': str(e)[:300]})
        return self._send(404, {'ok': False, 'error': 'not found'})

def register_protocol():
    """v12.9.129: протокол unitcontrol:// в HKCU (Windows, без админа).
       Ссылка из HTML, открытого файлом, запускает движок одним кликом:
       браузер спросит разрешение один раз. Не Windows / не вышло — тихо."""
    if sys.platform != 'win32': return False
    try:
        import winreg
        if FROZEN: cmd = f'"{sys.executable}" serve'
        else: cmd = f'"{sys.executable}" "{BASE / "uc_engine.py"}" serve'
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\unitcontrol') as k:
            winreg.SetValueEx(k, '', 0, winreg.REG_SZ, 'URL:UNIT CONTROL')
            winreg.SetValueEx(k, 'URL Protocol', 0, winreg.REG_SZ, '')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\unitcontrol\shell\open\command') as k:
            winreg.SetValueEx(k, '', 0, winreg.REG_SZ, cmd)
        return True
    except Exception:
        return False

def serve(port=8765):
    get_token()
    register_protocol()
    try:
        srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    except OSError:
        # уже запущен (например, клик по unitcontrol:// при живом движке):
        # просто открыть браузер и выйти
        import webbrowser
        print('Движок уже запущен — открываю браузер.')
        if not os.environ.get('UC_NO_BROWSER'): webbrowser.open(f'http://127.0.0.1:{port}/')
        return
    url = f'http://127.0.0.1:{port}/'
    print(f'UC PyEngine {VERSION}: {url}  (токен: {TOKEN_PATH})')
    print('Приложение открыто в браузере. Не закрывайте это окно, пока работаете; закрыть окно = остановить движок.')
    if not os.environ.get('UC_NO_BROWSER'):
        import threading, webbrowser
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    srv.serve_forever()

def watch_loop():
    conn = db()
    print('Планировщик запущен: почта + папка inbox + очередь отправки. Ctrl+C — стоп.')
    while True:
        try:
            st = get_settings(conn)
            print(time.strftime('%H:%M:%S'), watch_folder_once())
            try: print(time.strftime('%H:%M:%S'), mail_check_once(st))
            except Exception as e: print('почта:', e)
            print(time.strftime('%H:%M:%S'), process_outbox())
            if time.localtime().tm_hour == 3 and time.localtime().tm_min < 5: print(make_backup())
        except Exception as e:
            print('watch error:', e)
        time.sleep(300)


def app_catalog_state(conn,action,body):
    if action=='read':return _app_catalog_state(conn,action,body)
    return _bulk_write(_app_catalog_state)(conn,action,body)

def _app_catalog_state(conn, action, body):
    """Versioned complete application rows, separate from normalized calc tables."""
    import secrets
    conn.execute('CREATE TABLE IF NOT EXISTS app_catalog_head(id INTEGER PRIMARY KEY CHECK(id=1),revision TEXT NOT NULL,metadata TEXT NOT NULL,total INTEGER NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS app_catalog_chunks(revision TEXT NOT NULL,part INTEGER NOT NULL,data TEXT NOT NULL,PRIMARY KEY(revision,part))')
    conn.execute('CREATE TABLE IF NOT EXISTS app_catalog_upload(token TEXT PRIMARY KEY,base TEXT NOT NULL,total INTEGER NOT NULL,metadata TEXT NOT NULL,created REAL NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS app_catalog_chunk_sizes(revision TEXT NOT NULL,part INTEGER NOT NULL,n INTEGER NOT NULL,PRIMARY KEY(revision,part))')
    head=conn.execute('SELECT revision,metadata,total FROM app_catalog_head WHERE id=1').fetchone()
    current=head[0] if head else ''
    if action=='read':
        revision=body.get('revision',current)
        if revision!=current:raise ValueError('Каталог SQLite изменился во время чтения; повторите загрузку')
        part=body.get('part',0)
        if type(part) is not int or part<0:raise ValueError('Неверный номер части')
        chunk=conn.execute('SELECT data FROM app_catalog_chunks WHERE revision=? AND part=?',(revision,part)).fetchone()
        return {'revision':current,'metadata':json.loads(head[1]) if head and part==0 else {},'total':head[2] if head else 0,'chunk':json.loads(chunk[0]) if chunk else None,'exists':bool(head)}
    if action=='begin':
        total=body.get('total');metadata=body.get('metadata',{})
        if type(total) is not int or total<0 or not isinstance(metadata,dict):raise ValueError('Неверный каталог')
        if body.get('base','')!=current:raise ValueError('Каталог SQLite изменён другим клиентом; запись отменена')
        stale=[r[0] for r in conn.execute('SELECT token FROM app_catalog_upload WHERE created<?',(time.time()-86400,))]
        with conn:
            for old in stale:
                conn.execute('DELETE FROM app_catalog_chunks WHERE revision=?',(old,))
                conn.execute('DELETE FROM app_catalog_chunk_sizes WHERE revision=?',(old,))
                conn.execute('DELETE FROM app_catalog_upload WHERE token=?',(old,))
        token=secrets.token_hex(24)
        with conn:
            conn.execute('INSERT INTO app_catalog_upload VALUES(?,?,?,?,?)',(token,current,total,json.dumps(metadata,ensure_ascii=False,allow_nan=False),time.time()))
        return {'token':token}
    token=body.get('token','')
    upload=conn.execute('SELECT base,total,metadata FROM app_catalog_upload WHERE token=?',(token,)).fetchone()
    if not upload:raise ValueError('Загрузка каталога не найдена')
    if action=='chunk':
        part=body.get('part');chunk=body.get('chunk')
        if type(part) is not int or part<0 or not isinstance(chunk,dict) or not isinstance(chunk.get('rows'),list) or len(chunk['rows'])>1000:raise ValueError('Неверная часть каталога')
        types=chunk.get('special_values',[])
        # Ordinary price rows need validation, not a full deepcopy.
        decoded=decode_special(chunk['rows'],types) if types else chunk['rows']
        if not isinstance(types,list):raise ValueError('Неверные типы каталога')
        if any(not isinstance(row,dict) for row in decoded):raise ValueError('Неверная строка каталога')
        with conn:
            conn.execute('INSERT OR REPLACE INTO app_catalog_chunks VALUES(?,?,?)',(token,part,json.dumps(chunk,ensure_ascii=False,allow_nan=False)))
            conn.execute('INSERT OR REPLACE INTO app_catalog_chunk_sizes VALUES(?,?,?)',(token,part,len(decoded)))
        return {'saved':len(decoded)}
    if action!='commit':raise ValueError('Неизвестная операция каталога')
    # Lock and compare again inside the publishing transaction. Interrupted uploads
    # never replace the previous committed head (including an empty catalogue).
    with conn:
        conn.execute('UPDATE app_catalog_head SET revision=revision WHERE id=1')
        latest=conn.execute('SELECT revision FROM app_catalog_head WHERE id=1').fetchone()
        if (latest[0] if latest else '')!=upload[0]:raise ValueError('Конфликт версии каталога SQLite')
        chunks=conn.execute('SELECT c.part,s.n FROM app_catalog_chunks c LEFT JOIN app_catalog_chunk_sizes s ON s.revision=c.revision AND s.part=c.part WHERE c.revision=? ORDER BY c.part',(token,)).fetchall()
        if [r[0] for r in chunks]!=list(range(len(chunks))):raise ValueError('Пропущена часть каталога')
        # Pre-upgrade, unfinished uploads have no size record. Read only those
        # legacy chunks; new uploads never reparse the entire catalog at commit.
        total=0
        for part,count in chunks:
            if count is None:
                raw=conn.execute('SELECT data FROM app_catalog_chunks WHERE revision=? AND part=?',(token,part)).fetchone()[0]
                count=len(json.loads(raw)['rows'])
            total+=count
        if total!=upload[1]:raise ValueError('Неполная загрузка каталога')
        conn.execute('INSERT OR REPLACE INTO app_catalog_head VALUES(1,?,?,?)',(token,upload[2],upload[1]))
        conn.execute('DELETE FROM app_catalog_upload WHERE token=?',(token,))
        conn.execute('DELETE FROM app_catalog_chunks WHERE revision!=? AND revision NOT IN (SELECT token FROM app_catalog_upload)',(token,))
        conn.execute('DELETE FROM app_catalog_chunk_sizes WHERE revision!=? AND revision NOT IN (SELECT token FROM app_catalog_upload)',(token,))
    return {'revision':token,'total':upload[1]}


def run_sqlite_poc():
    """Run the historical standalone SQLite experiment explicitly, never on import."""
    # -*- coding: utf-8 -*-
    """PoC: юнит-экономика на Python + SQLite. Сверка с золотыми CSV приложения."""
    import csv, sqlite3, math, os
    from decimal import Decimal, ROUND_HALF_UP

    import pathlib
    DB = str(pathlib.Path(__file__).with_name('poc_catalog.db'))
    if os.path.exists(DB): os.remove(DB)
    db = sqlite3.connect(DB)
    db.executescript('''
    CREATE TABLE products(
      article TEXT PRIMARY KEY, price REAL, cost REAL,
      weight REAL, length REAL, width REAL, height REAL, sales REAL DEFAULT 0);
    CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE eco_results(
      article TEXT PRIMARY KEY, total_cost REAL, profit REAL,
      margin REAL, roi REAL, break_even REAL, target_price REAL);
    ''')
    # настройки из золотого файла (Ozon FBS): комиссия 14%, перевод 1.5%, налог УСН 6%
    for k, v in {'commission_pct':'14','transfer_pct':'1.5','last_mile':'25','handover':'10',
                 'pack':'18','transit':'30','returns_per_unit':'2.17','tax_regime':'usn_income_6',
                 'tax_pct':'6','target_margin':'20'}.items():
        db.execute('INSERT INTO settings VALUES(?,?)', (k, v))
    db.commit()
    cfg = {k: v for k, v in db.execute('SELECT key,value FROM settings')}

    def rnd(x, d=2):
        # Excel-стиль: половина от нуля, как round() в приложении
        q = Decimal(1).scaleb(-d)
        return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))

    def vat_from_gross(amount, rate):
        return amount * rate / (100 + rate) if rate > 0 else 0.0

    def calc_tax(price, costs, regime, pct=6.0, osno_share=0.0):
        p, c = max(0.0, price), max(0.0, costs)
        if regime == 'usn_income_6': return rnd(p * 0.06)
        if regime in ('usn_income_vat_5', 'usn_income_7', 'usn_income_vat_7'):
            rate = 5 if regime.endswith('_5') else 7
            vat = vat_from_gross(p, rate)
            return rnd(vat + (p - vat) * 0.06)
        if regime == 'usn_income_expense_15': return rnd(max(0.0, p - c) * 0.15)
        if regime in ('usn_income_expense_vat_5', 'usn_income_expense_vat_7'):
            rate = 5 if regime.endswith('_5') else 7
            vat = vat_from_gross(p, rate)
            return rnd(vat + max(0.0, p - vat - c) * 0.15)
        if regime in ('osno_20', 'osno_22'):
            vat_out = vat_from_gross(p, 22)
            vat_in = vat_from_gross(c, 22) * min(100.0, max(0.0, osno_share)) / 100
            return rnd(max(0.0, vat_out - vat_in) + max(0.0, (p - vat_out) - (c - vat_in)) * 0.25)
        if regime == 'custom_profit': return rnd(max(0.0, p - c) * pct / 100)
        return rnd(p * pct / 100)

    def wb_base_logistics(v):
        if v <= 0: return 0.0
        if v <= 0.2: return 23.0
        if v <= 0.4: return 26.0
        if v <= 0.6: return 29.0
        if v <= 0.8: return 30.0
        if v <= 1: return 32.0
        return rnd(46 + (v - 1) * 14)

    def ozon_unit(price, cost):
        comm = rnd(price * float(cfg['commission_pct']) / 100)
        transfer = rnd(price * float(cfg['transfer_pct']) / 100)
        fixed = (cost + float(cfg['last_mile']) + float(cfg['handover']) + float(cfg['pack'])
                 + float(cfg['transit']) + float(cfg['returns_per_unit']))
        tax = calc_tax(price, fixed + comm + transfer, cfg['tax_regime'], float(cfg['tax_pct']))
        total = rnd(fixed + comm + transfer + tax)
        return total, comm, transfer, tax

    def solve(price0, cost, target_margin_pct):
        # первое целое p с прибылью >= 0 (и >= целевой маржи), как решатель приложения
        def profit(p):
            total, *_ = ozon_unit(p, cost)
            return rnd(p - total)
        def margin_ok(p):
            return profit(p) - p * target_margin_pct / 100
        be = next((p for p in range(0, 2_000_000) if profit(p) >= 0), None)
        tgt = next((p for p in range(be or 0, 2_000_000) if margin_ok(p) >= 0), None)
        return be, tgt

    # --- загрузка золотого файла в SQLite ---
    def num(v):
        v = str(v or '').replace(' ', '').replace(',', '.')
        return float(v) if v else 0.0

    rows = list(csv.reader(open(str(pathlib.Path(__file__).resolve().parent.parent / 'UC_unit_economics_OZON_2026-11-06_filtered.csv'),
                                encoding='utf-8-sig'), delimiter=';'))
    hdr = rows[0]; ix = {h: i for i, h in enumerate(hdr)}
    for r in rows[1:]:
        db.execute('INSERT INTO products VALUES(?,?,?,?,?,?,?,?)',
                   (r[ix['Артикул']], num(r[ix['Цена, ₽/ед.']]), num(r[ix['Себестоимость, ₽']]),
                    num(r[ix['Вес, кг']]), num(r[ix['Длина, см']]), num(r[ix['Ширина, см']]),
                    num(r[ix['Высота, см']]), 10))
    db.commit()

    # --- расчёт из SQLite и сверка ---
    rec = list(csv.reader(open(str(pathlib.Path(__file__).resolve().parent.parent / 'UC_unit_economics_OZON_2026-11-06_recalculated.csv'),
                               encoding='utf-8-sig'), delimiter=';'))
    rix = {h: i for i, h in enumerate(rec[0])}
    manual_be = {r[0]: num(r[rix['Цена безубыточности (ручной пересчёт), руб']]) for r in rec[1:]}

    bad = 0
    for art, price, cost, w, L, W, H, sales in db.execute('SELECT * FROM products'):
        total, comm, transfer, tax = ozon_unit(price, cost)
        profit = rnd(price - total)
        margin = rnd(profit / price * 100, 1) if price else 0
        roi = rnd(profit / cost * 100, 1) if cost else 0
        be, tgt = solve(price, cost, float(cfg['target_margin']))
        db.execute('INSERT INTO eco_results VALUES(?,?,?,?,?,?,?)', (art, total, profit, margin, roi, be, tgt))
        # сверка с золотым файлом
        grow = next(r for r in rows[1:] if r[0] == art)
        checks = [(total, num(grow[ix['Все затраты на 1 ед., ₽']]), 'итого'),
                  (profit, num(grow[ix['ЧП на 1 ед., ₽']]), 'прибыль'),
                  (margin, num(grow[ix['Маржа, %']]), 'маржа'),
                  (roi, num(grow[ix['ROI, %']]), 'ROI'),
                  (be, manual_be[art], 'безубыток')]
        for got, want, name in checks:
            tol = 1.0 if name == 'безубыток' else 0.011  # решатель приложения целочисленный, ручная колонка — дробная
            if abs(got - want) > tol:
                bad += 1; print(f'РАСХОЖДЕНИЕ {art} {name}: python={got} эталон={want}')
    db.commit()
    n = db.execute('SELECT COUNT(*) FROM eco_results').fetchone()[0]
    print(f'PoC OK: {n} SKU посчитано в Python+SQLite, расхождений с эталоном: {bad}')
    print('пример:', db.execute("SELECT * FROM eco_results WHERE article='DEMO-CLT-001'").fetchone())
    print('налоги: УСН6 100000 ->', calc_tax(100000, 40000, 'usn_income_6'),
          '| УСН+НДС5 ->', calc_tax(100000, 40000, 'usn_income_vat_5'),
          '| ОСНО 1220/610 доля100 ->', calc_tax(1220, 610, 'osno_20', 6, 100))
    print('WB логистика 0.5л/2л:', wb_base_logistics(0.5), wb_base_logistics(2))
    print('размер БД:', os.path.getsize(DB), 'байт')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    if FROZEN and len(sys.argv) == 1: sys.argv.append('serve')  # двойной клик по exe
    ap.add_argument('cmd', choices=['serve', 'watch', 'mail', 'folder', 'outbox', 'backup', 'calc', 'poc'])
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--once', action='store_true')
    args = ap.parse_args()
    try:
        import multiprocessing as _mp
        _mp.freeze_support()  # Windows spawn / PyInstaller: дочерние процессы не должны стартовать сервер
    except Exception: pass
    if args.cmd == 'poc': run_sqlite_poc()
    elif args.cmd == 'serve': serve(args.port)
    elif args.cmd == 'watch': watch_loop()
    elif args.cmd == 'mail': print(mail_check_once(get_settings(db())))
    elif args.cmd == 'folder': print(watch_folder_once())
    elif args.cmd == 'outbox': print(process_outbox())
    elif args.cmd == 'backup': print(make_backup())
    elif args.cmd == 'calc':
        demo = {'article': 'DEMO-CLT-001', 'price': 18700, 'cost': 11200, 'sales': 10}
        st = {'commission_pct': 14, 'transfer_pct': 1.5, 'last_mile': 25, 'handover': 10,
              'pack': 18, 'transit': 30, 'returns_per_unit': 2.17, 'tax_regime': 'usn_income_6', 'tax_pct': 6}
        print(calc_row(demo, st))
