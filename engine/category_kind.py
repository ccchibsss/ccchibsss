"""Non-destructive CategoryKindAuto.apply lifecycle port."""
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
      'охлаждение':['система охлаждения','резинотехнические изделия','насосы и компрессоры'], 
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
