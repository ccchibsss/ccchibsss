"""Validated OE proposal application; leaves proposed packaging quarantined."""
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
