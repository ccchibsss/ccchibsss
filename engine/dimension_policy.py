"""DimPolicy donor authorization and deterministic tuple selection."""
import math
import re
from decimal import Decimal, ROUND_HALF_UP
from dimension_quarantine import number, compact
from ozon_identity import key, codes

MAX_CODES=64
MAX_CANDIDATES=240
DIMS=('weight','length','width','height')


def loose_oe(value): return re.sub(r'(^|[^0-9])0+(?=[0-9])',r'\1',key(value))


def similar_oe(a,b):
    x,y=key(a),key(b)
    return bool(x and y and (x==y or (len(x)>=5 and len(y)>=5 and loose_oe(x)==loose_oe(y))))


def policy_codes(p,mode='auto'):
    raw=list(codes([p.get('oe_numbers'),p.get('oe_list')],mode))
    if not raw and p.get('oe_norm'):raw+=list(codes(p['oe_norm'],mode))
    ev=p.get('_dimensionAutoOeEvidence')
    if isinstance(ev,dict) and isinstance(ev.get('entries'),list):
        raw += [key(x['code']) for x in ev['entries'] if isinstance(x,dict) and x.get('code')]
    return list(dict.fromkeys(x for x in raw if x))[:MAX_CODES]


def article(p):return key(p.get('article') if p.get('article') is not None else p.get('artikul'))


def source_allowed(target,candidate,matched_code='',mode='auto'):
    if target is None or candidate is None or target is candidate:
        return dict(ok=False,tier='',oe='',reason='нет источника')
    a,b=article(target),article(candidate);ab,bb=key(target.get('brand')),key(candidate.get('brand'))
    if a and b and a==b and ab and bb and ab==bb:
        return dict(ok=True,tier='sku',oe='',reason='тот же артикул и бренд')
    ca,cb=policy_codes(target,mode),policy_codes(candidate,mode);mc=key(matched_code)
    oe=''
    if cb:
        for y in cb:
            if any(similar_oe(x,y) for x in ca) or (mc and similar_oe(y,mc) and any(similar_oe(x,mc) for x in ca)):
                oe=y;break
    elif mc and any(similar_oe(x,mc) for x in ca):oe=mc
    if oe:return dict(ok=True,tier='oe',oe=oe,reason='схожий OE '+oe)
    return dict(ok=False,tier='',oe='',reason='другой артикул без схожего OE — данные не переносятся')


def js_number(value):
    # Number(), not the localized num()/parseFloat used by ordinary OVH fields.
    if value is None:return 0.0
    if isinstance(value,bool):return float(value)
    try:
        if isinstance(value,str):
            s=value.strip()
            if not s:return 0.0
            if re.fullmatch(r'0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+',s):return float(int(s,0))
        return float(value)
    except (ValueError,TypeError):return float('nan')


def valid_tuple(t):
    return isinstance(t,dict) and all(k in t and math.isfinite(js_number(t[k])) and js_number(t[k])>0 for k in DIMS)


def tuple_key(t):
    def fixed(v):
        n=js_number(v)
        if abs(n)>=1e21:return compact(n)
        return format(Decimal.from_float(n).quantize(Decimal('0.000001'),rounding=ROUND_HALF_UP),'f')
    return '|'.join(fixed(t.get(k)) for k in DIMS)


def rounded(v,d):
    if not math.isfinite(v):return 0
    f=10**d;a=abs(v*f)
    if not math.isfinite(a):return math.copysign(float('inf'),v)
    frac=a-math.floor(a)
    if 0.5-1e-9<frac<0.5:a=float(format(a,'.15g'))
    return math.copysign(math.floor(a+0.5)/f,v)


def measure(t):
    l,w,h,wt=(js_number(t.get(k)) for k in ('length','width','height','weight'))
    return (rounded(l*w*h/1000,6),rounded(max(l,w,h),4),rounded(wt,6),rounded(l+w+h,4))


def pick(candidates,is_valid=None):
    seen=set();rows=[];rejected=0
    for c in candidates:
        if not c or not c.get('complete') or not valid_tuple(c.get('tuple')):continue
        k=str(c.get('identity','undefined'))+'|'+tuple_key(c['tuple'])
        if k in seen:continue
        seen.add(k)
        if is_valid and not is_valid(c['tuple']):rejected+=1;continue
        rows.append(c)
    rows.sort(key=lambda c:measure(c['tuple']))
    return dict(choice=rows[0] if rows else None,variants=len(rows),rejected=rejected)
