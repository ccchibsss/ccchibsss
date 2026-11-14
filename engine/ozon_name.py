"""Independent OzonAuto lexical name classifier over canonical type entries."""
import json
import pathlib
import re
from csv_kind_matcher import rewrite, name_lead, UNSAFE
from ozon_reference import strict_key

STOP=set('для или под над без при как the and на по of из в с a авто'.split())
ALIASES=dict(zip('filter oil air cabin fuel water brake pads pad disc pump headlight'.split(),
                 'фильтр масляный воздушный салонный топливный водяной тормозной колодки колодки диск насос фара'.split()))
EXPANSIONS=json.loads(pathlib.Path(__file__).with_name('ozon_name_expansions.json').read_text(encoding='utf8'))
MOTO=r'(?:мотоцикл|скутер|мопед|снегоход|квадроцикл|(?:^|\s)мото(?=\s|$))'
ADJ=r'(?:ый|ий|ой|ая|яя|ое|ее|ые|ие|ых|их|ого|его|ому|ему|ыми|ими|ую|юю)$'
BLOCKS={
 'ключ автомобильный':r'гаечн|рожков|накидн|торцев|динамометр|фильтр|съ[её]мн|шестигран|свечн|колесн|болт|гайк|трещотк',
 'насос автомобильный':r'омывател|топлив|масл|охлаж|водян|гидро|тормоз|откач|перекач|ручн|abs|абс|гур',
 'держатель автомобильный':r'тормоз|шланг|труб|выхлоп|глушител|топлив|амортизатор|двигател|подвеск|насос|радиатор|трансмисс|стартер|суппорт|шрус',
 'подушка автомобильная':r'амортизатор|радиатор|двигател|мотора|двс|подвеск|подрамник|рессор|редуктор|кпп|коробк[аиуы]?\s+передач|глушител|рулев|руля|безопасност|airbag|эйрб[еэ]г|аэрб[еэ]г'}


def expand(value):
    text=str(value or '')
    if re.search('водян[а-я]*',text,re.I):
        text=re.sub(r'(^|[^a-zа-я0-9])помп[а-я]*(?=$|[^a-zа-я0-9])',r'\1насос',text,flags=re.I)
    if re.search(r'сальник[а-я]*\s+(?:коленвал|распредвал)',text,re.I): text+=' двигателя'
    if re.search(MOTO,text,re.I): text+=' мототехника'
    for pattern,target in EXPANSIONS:
        text=re.sub(pattern,target.replace('$1',r'\g<1>'),text,flags=re.I)
    return text


def tokens(value,product=False,literal=False):
    text=str(value or '') if literal else expand(rewrite(value) if product else value)
    text=text.lower().replace('ё','е')
    text=re.sub(r'ремонтн[а-я]*\s+комплект[а-я]*','ремкомплект',text)
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
        multiple=re.search(r'\sи\s|\sand\s|\s\+\s|\s&\s|[а-яё]\s*[,;/+&]\s*(?=[а-яё])|\s+[–—]\s+',name,re.I) or re.search(r'^\s*(?:комплект|набор)(?=\s|$)',name.replace('ё','е'),re.I)
        if multiple:
            joined=re.search(r'^\s*(?:комплект|набор)(?=\s|$)',name,re.I) and re.search(r'\sи\s|\s\+\s|\s&\s',name,re.I)
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
