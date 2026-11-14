"""Ozon name proposals checked against internal category/kind dictionary."""
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
    return h+'\x1f'+'\x1e'.join(ns) if h and ns else ''


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
        if re.search(r'[/,;+&|]|\s(?:и|или)\s|прочие|разные|универсальн',kind,re.I): return name_result
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
