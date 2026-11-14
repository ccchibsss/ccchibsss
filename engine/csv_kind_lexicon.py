"""CsvNameMatcher lexical rules, ported from the browser reference."""
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
    s=re.sub(r"ремонтн[а-я]*\s+комплект[а-я]*","ремкомплект",s)
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
        pieces=[p.strip() for p in re.split(r'\s+(?:и|или)\s+|[/,;]+',typ,flags=re.I) if p.strip()]
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
