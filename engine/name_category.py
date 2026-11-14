"""NameCategory selection and non-destructive apply, using raw dictionary inputs."""
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
        text=re.sub(EXPANSIONS[0][0],r'\g<1>насос',text,flags=re.I)
    if re.search('сальник[а-я]*\s+(?:коленвал|распредвал)',text,re.I): text+=' двигателя'
    if re.search(r'(?:мотоцикл|скутер|мопед|снегоход|квадроцикл|(?:^|\s)мото(?=\s|$))',text,re.I): text+=' мототехника'
    for pattern,replacement in EXPANSIONS[1:]:
        text=re.sub(pattern,replacement.replace('$1',r'\g<1>'),text,flags=re.I)
    text=re.sub('ремонтн[а-я]*\s+комплект[а-я]*','ремкомплект',norm(text))
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
                    if re.search('(?:стекло)?омывател',lower) or not re.search(r'(?:топлив|дизел|бензин|инжектор|впрыск|fuel|injector|тнвд|газов|гбо|common[\s-]*rail)',lower,re.I): continue
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
