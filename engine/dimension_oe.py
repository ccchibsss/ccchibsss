"""AnomalyOE evidence/tuple guards for independent OE donor search.

The catalogue/HVC search index and apply lifecycle are not implemented here yet.
"""
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
    return model.signature(p,e)+'|'+'\x1f'.join(sorted(current_codes(p,False,mode)))+'|'+str(p.get('oeSource') or '')
