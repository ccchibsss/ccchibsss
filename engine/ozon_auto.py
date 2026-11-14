"""Ozon preferred-assignment lifecycle; lexical inference is injected separately.

This is not yet a standalone name classifier. The detail callback must implement
OzonAuto.detailWithCategory, not supply browser-generated presentation values.
"""
import copy
import re

MARKERS = ('SourceName', 'SourceBrand', 'Version', 'Status', 'Choices',
           'SuggestedType', 'CategorySignature', 'Reason')
PREFIX = '_ozonName'


def apply_preferred(model, row, *, detail, version, category_signature,
                    registry=None, applicability=None, force=False,
                    enabled=True, force_name=False, identity_unsafe=False,
                    reference_version=0):
    p = copy.deepcopy(row)
    if identity_unsafe:
        return p, dict(category=p.get('ozon_category') or '', type=p.get('ozon_type') or '',
                       source=p.get('ozon_type_src') or 'none',
                       reason='неоднозначный SKU или OE-источник — автоматическая типизация пропущена')
    old = copy.deepcopy(p) if p.get('ozon_type_src') == 'keyword' and (p.get('ozon_type') or p.get('ozon_category')) else None
    if not p.get('ozon_type_src') and (p.get('ozon_type') or p.get('ozon_category')):
        p.update(ozon_type_src='import', ozon_type_basis='import', ozon_type_conf='unverified')
    p, r = model.apply(p, registry, applicability, force, reference_version)
    if r and r['source'] in ('auto', 'manual', 'import'):
        if r['source'] in ('manual', 'import'):
            p['ozon_error'] = ''
        for key in MARKERS:
            p.pop(PREFIX + key, None)
        return p, r
    if r and re.search(r'conflict|invalid_(?:oe|applicability)_mapping', r.get('reason', ''), re.I):
        p[PREFIX+'Status'] = 'oe_conflict' if re.search('conflict', r['reason'], re.I) else 'oe_invalid'
        p[PREFIX+'Choices'] = []
        for key in ('SourceName', 'SourceBrand', 'Version', 'CategorySignature', 'Reason'):
            p.pop(PREFIX+key, None)
        return p, r
    name, brand = str(p.get('name') or ''), str(p.get('brand') or '').strip()
    current = bool(old and old.get(PREFIX+'SourceName') == name and old.get(PREFIX+'SourceBrand') == brand
                   and old.get(PREFIX+'Version') == version and old.get(PREFIX+'CategorySignature') == category_signature)

    def result():
        return dict(category=p.get('ozon_category') or '', type=p.get('ozon_type') or '', source='keyword',
                    basis=p.get('ozon_type_basis') or 'keyword', score=p.get('ozon_type_score') or 0,
                    confidence='low', reason='', oe='', applicability='')

    def restore():
        for key in ('ozon_category', 'ozon_type'):
            if key in old:
                p[key] = old[key]
            else:
                p.pop(key, None)
        p.update(ozon_type_score=old.get('ozon_type_score') or 0, ozon_type_src='keyword',
                 ozon_type_conf='low', ozon_type_basis=old.get('ozon_type_basis') or 'keyword', ozon_error='')
        for key in ('ozon_description_category_id', 'ozon_type_id'):
            if old.get(key) is not None:
                p[key] = old[key]
            else:
                p.pop(key, None)
        for key, default in (('Choices', []), ('SuggestedType', ''), ('CategorySignature', ''), ('Reason', '')):
            p[PREFIX+key] = old.get(PREFIX+key) or default

    if not (enabled or force_name):
        if old:
            restore()
            p[PREFIX+'Status'] = (old.get(PREFIX+'Status') or 'auto') if current else 'stale'
            return p, result()
        if PREFIX+'SourceName' in p and any(p.get(PREFIX+k) != v for k,v in
                (('SourceName',name), ('SourceBrand',brand), ('Version',version), ('CategorySignature',category_signature))):
            p[PREFIX+'Status'] = 'stale'
        return p, r
    if current and old.get(PREFIX+'Status') != 'stale':
        restore()
        p[PREFIX+'Status'] = old.get(PREFIX+'Status') or 'auto'
        return p, result()
    d = detail(p)
    p.update({PREFIX+'SourceName':name, PREFIX+'SourceBrand':brand, PREFIX+'Version':version,
              PREFIX+'CategorySignature':category_signature, PREFIX+'Reason':d.get('reason') or '',
              PREFIX+'Status':d['status'], PREFIX+'Choices':(d.get('choices') or [])[:6],
              PREFIX+'SuggestedType':d.get('suggestedType') or ''})
    match = d.get('match')
    if not match:
        p.pop('ozon_description_category_id', None)
        p.pop('ozon_type_id', None)
        if d['status'] != 'category_ambiguous' or not d.get('suggestedType'):
            return p, r
        p.update(ozon_category='', ozon_type=d['suggestedType'], ozon_type_score=0)
    else:
        p.update(ozon_category=match['cat'], ozon_type=match['type'], ozon_type_score=match['score'])
        if match.get('catId') and match.get('typeId'):
            p.update(ozon_description_category_id=match['catId'], ozon_type_id=match['typeId'])
        else:
            p.pop('ozon_description_category_id', None)
            p.pop('ozon_type_id', None)
    p.update(ozon_type_src='keyword', ozon_type_conf='low', ozon_type_basis=d.get('basis') or 'keyword', ozon_error='')
    return p, result()
