"""Independent AnomalyOE.find search over raw catalogue and HVC snapshots."""
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
                e=dict(kind='hvc',identity=ident,ref=part,evidence=ev,linkKey=key(c)+'\x1f'+art_key,partKey=art_key,code=c,tuple=t,complete=complete,tkey=tuple_key(t),
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
                    fmt=lambda n:format(number(n),',.0f').replace(',','\u00a0')
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
