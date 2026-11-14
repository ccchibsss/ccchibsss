"""Ordered user enrichment rules, preserving explicit category assignments."""
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
