"""Conservative CSV kind candidate ranking; no row mutations."""
import json
import pathlib
import re
from csv_kind_lexicon import build_index, words, stem, head, WEAK
from category_tnved import norm

TEXT_RULES=[('(^|[^a-zа-яё0-9])опор[а-яё]*\\s+(?:двигател[а-яё]*|двс)(?=$|[^a-zа-яё0-9])', '$1подушка двигателя'), ('(^|[^a-zа-яё0-9])стойк[а-яё]*\\s+стабилизатор[а-яё]*(?=$|[^a-zа-яё0-9])', '$1тяга стабилизатора'), ('(^|[^a-zа-яё0-9])(?:насос[а-яё]*\\s+водян[а-яё]*|водян[а-яё]*\\s+насос[а-яё]*|насос[а-яё]*\\s+охлаждающ[а-яё]*\\s+жидкост[а-яё]*|помп[а-яё]*\\s+систем[а-яё]*\\s+охлаждени[а-яё]*)(?=$|[^a-zа-яё0-9])', '$1помпа водяная'), ('(^|[^a-zа-яё0-9])(?:щ[её]тк[а-яё]*\\s+дворник[а-яё]*|дворник[а-яё]*)(?=$|[^a-zа-яё0-9])', '$1щетка стеклоочистителя'), ('(^|[^a-zа-яё0-9])дмрв(?=$|[^a-zа-яё0-9])', '$1расходомер'), ('(^|[^a-zа-яё0-9])(?:рулев[а-яё]*\\s+наконечник[а-яё]*|наконечник[а-яё]*\\s+рулев[а-яё]*)(?=$|[^a-zа-яё0-9])', '$1наконечник рулевой тяги'), ('(^|[^a-zа-яё0-9])насос[а-яё]*\\s+гидроусилител[а-яё]*(?=$|[^a-zа-яё0-9])', '$1насос ГУР'), ('(^|[^a-zа-яё0-9])форсунк[а-яё]*\\s+стеклоомывател[а-яё]*(?=$|[^a-zа-яё0-9])', '$1форсунка омывателя'), ('(^|[^a-zа-яё0-9])сальник[а-яё]*\\s+(?:коленчат[а-яё]*\\s+вал[а-яё]*|коленвал[а-яё]*|распредвал[а-яё]*|распределительн[а-яё]*\\s+вал[а-яё]*)(?=$|[^a-zа-яё0-9])', '$1сальник двигателя'), ('(^|[^a-zа-яё0-9])болт[а-яё]*\\s+головк[а-яё]*\\s+блок[а-яё]*\\s+цилиндр[а-яё]*(?=$|[^a-zа-яё0-9])', '$1болт ГБЦ'), ('(^|[^a-zа-яё0-9])кольц[а-яё]*\\s+поршн[а-яё]*(?=$|[^a-zа-яё0-9])', '$1кольцо поршневое'), ('(^|[^a-zа-яё0-9])фильтр[а-яё]*\\s+(?:очистк[а-яё]*\\s+)?топлив[а-яё]*(?=$|[^a-zа-яё0-9])', '$1фильтр топливный'), ('(^|[^a-zа-яё0-9])фильтр[а-яё]*\\s+(?:моторн[а-яё]*\\s+)?масл[а-яё]*(?=$|[^a-zа-яё0-9])', '$1фильтр масляный'), ('(^|[^a-zа-яё0-9])фильтр[а-яё]*\\s+(?:очистк[а-яё]*\\s+)?воздух[а-яё]*(?=$|[^a-zа-яё0-9])', '$1фильтр воздушный'), ('(^|[^a-zа-яё0-9])прокладк[а-яё]*\\s+головк[а-яё]*\\s+блок[а-яё]*\\s+цилиндр[а-яё]*(?=$|[^a-zа-яё0-9])', '$1прокладка ГБЦ')]
UNSAFE='\\b(?:filter|pump|pad|pads|disc|caliper|motor|starter|alternator|mount|arm|sensor|coil|radiator|joint|wiper|link|belt)[\\s,;:()\\[\\]\\/_–—-]+(?:(?:wear|pressure|mounting|retaining|drive)\\s+)?(?:housing|bracket|gasket|seal|cover|cap|pulley|bearing|bushing|bush|boot|bolt|relay|sensor|switch|solenoid|wire|wiring|connector|harness|clip|adapter|fuse|wrench|tool|repair\\s+kit)\\b'
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
        s=re.sub(pattern,target.replace('$1',r'\g<1>'),s,flags=re.I)
    if s!=raw: result.append(s)
    x=rewrite(s)
    if x!=s: result.append(x)
    return list(dict.fromkeys(result))


def name_lead(name,brand):
    lead=re.split(r'(?:^|\s)(?:для|под|от|на|к|for|совместим(?:ый|ая|ые|о)?|подходит|применимость)(?=\s|$)',str(name or ''),flags=re.I)[0]
    brand=str(brand or '').strip()
    if brand and lead.lower().startswith(brand.lower()):
        suffix=lead[len(brand):]
        if re.match(r'^[\s,:;/—–-]+',suffix): lead=re.sub(r'^[\s,:;/—–-]+','',suffix)
    else:
        lead=re.sub(r'^([A-Z][A-Z0-9&._-]{1,29})[\s,:;/—–-]+(?=[А-ЯЁа-яё])','',lead)
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
        multi=re.search(r'(?:\sи\s|\sand\s|\s\+\s|\s&\s)|[а-яё]\s*[,;/+&]\s*(?=[а-яё])',name,re.I)
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
