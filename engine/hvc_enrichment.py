"""Server implementation of HVC.enrichOne using an explicit HVC reference snapshot.

References are inputs (parts/OE/byArt/byOe), never browser-computed enrichments.
The legacy donors API is deliberately not used: it cannot represent HVC's graph.
"""
import copy
import math
import re

DIMS = ('weight', 'length', 'width', 'height')
EXACT_PLACEHOLDERS = {'Без категории', 'Разное', 'Прочее', 'Не определено'}
PLACEHOLDERS = {'без категории', 'разное', 'прочее', 'не определено'}


def norm(value):
    return re.sub('[^A-Z0-9А-ЯЁ]', '', str(value or '').upper())


def enrich_rows(rows, reference, mode='auto', cat_mode='artbrand', columns=None,
                timestamp='', number=float, rounded=round, allowed=None):
    parts = dict(reference.get('parts') or [])
    registry = dict(reference.get('oe') or [])
    by_art = dict(reference.get('byArt') or [])
    by_oe = dict(reference.get('byOe') or [])
    unsafe = set(reference.get('unsafeKeys') or [])
    unsafe_oe = set(reference.get('unsafeOe') or [])
    separator = reference.get('groupSeparator', ' / ')
    columns = columns or {}
    def enabled(k): return bool(columns.get(k, True))
    def num(v):
        try: return number(v)
        except (ValueError, TypeError): return 0
    def meaningful(v, category=False):
        text = str(v or '').strip()
        return '' if category and text.lower() in PLACEHOLDERS else text
    def complete(t):
        return bool(t) and all(math.isfinite(num(t.get(k))) and num(t.get(k)) > 0 for k in DIMS)
    def measure(t):
        w, l, wi, h = (num(t.get(k)) for k in DIMS)
        return (rounded(l * wi * h / 1000, 6), rounded(max(l, wi, h), 4), rounded(w, 6), rounded(l + wi + h, 4))
    cache = {}
    def aggregate(key):
        oes = by_art.get(key, [])
        cache_key = tuple(oes)
        if cache_key in cache: return cache[cache_key]
        rep = None
        agg = {}
        categories = set()
        smallest = None
        smallest_oe = ''
        analogs, seen = [], set()
        self_art = key.split('|')[0]
        for oe in oes:
            record = registry.get(oe) if oe not in unsafe_oe else None
            # Same guard as _oeAggOf; tnved alone does not make a representative.
            if record and (record.get('name') or record.get('applicability') or (record.get('category') and str(record['category']).strip() not in EXACT_PLACEHOLDERS)
                           or record.get('length') or record.get('dimensions_str')):
                if rep is None: rep = record
            if record and record.get('category') and str(record['category']).strip() not in EXACT_PLACEHOLDERS: categories.add(str(record['category']).strip())
            per_oe = []
            per_seen = set()
            for holder in by_oe.get(oe, []):
                if holder in unsafe: continue
                part = parts.get(holder)
                if not part: continue
                evidence = part.get('_dimensionEvidence')
                if complete(evidence) and (smallest is None or measure(evidence) < measure(smallest)):
                    smallest, smallest_oe = evidence, oe
                for field in ('name', 'applicability', 'category', 'tnved'):
                    # Browser OE aggregate does not populate tnved from parts.
                    if field == 'tnved': continue
                    value = meaningful(part.get(field), field == 'category')
                    if not agg.get(field) and value: agg[field] = value
                if part.get('category') and str(part['category']).strip() not in EXACT_PLACEHOLDERS: categories.add(str(part['category']).strip())
                art = part.get('artikul') or part.get('article') or ''
                an = norm(art)
                if an and an not in per_seen:
                    per_seen.add(an)
                    if len(per_oe) < 40: per_oe.append((an, art))
            for an, art in per_oe:
                if an != self_art and an not in seen:
                    seen.add(an)
                    if len(analogs) < 40: analogs.append(art)
        result = {'rep': rep or {}, 'agg': agg, 'conflict': len(categories) > 1,
                  'smallest': smallest, 'smallestOe': smallest_oe, 'analogs': ', '.join(analogs)}
        cache[cache_key] = result
        return result
    result = []
    for source in rows:
        p = copy.deepcopy(source)
        key = norm(p.get('article')) + '|' + norm(p.get('brand'))
        if key in unsafe:
            result.append(p); continue
        pt = parts.get(key)
        raw_oe = str(p.get('oe_norm') or '').strip()
        known = any(oe in registry or oe in by_oe for oe in [raw_oe] + re.split(r'[/;,|\s\x01]+', raw_oe) if oe)
        pair_known = bool(norm(p.get('article')) and norm(p.get('brand')) and pt is not None)
        h = aggregate(key)
        def group():
            out, seen = [], set()
            def push(k):
                if len(out) >= 500 or k in unsafe: return
                part = parts.get(k)
                art = (part.get('artikul') or part.get('article')) if part else k.split('|')[0]
                an = norm(art)
                if an and an not in seen:
                    seen.add(an); out.append(art)
            push(key)
            for oe in by_art.get(key, []):
                holders = by_oe.get(oe, [])
                if len(holders) > 2000: continue
                for holder in holders: push(holder)
            return out
        def run_pass(selected, cat_only):
            if selected == 'oe' and not known: return
            if selected != 'oe' and not pair_known: return
            if not cat_only:
                if enabled('analog_list'): p['analog_list'] = h['analogs']
                if enabled('group_articles'):
                    entries = group()
                    p['group_articles'], p['groupSize'] = separator.join(entries), len(entries)
            for field in (('category', 'tnved') if cat_only else ('name', 'applicability')):
                occupied = meaningful(p.get(field))
                if field == 'category': occupied = occupied and occupied not in EXACT_PLACEHOLDERS
                if not enabled(field) or occupied: continue
                if selected == 'oe':
                    if field == 'category' and h['conflict']: continue
                    options = [(h['rep'].get(field), 'OE-реестр'), (h['agg'].get(field), 'аналоги по OE')]
                else:
                    options = [((pt or {}).get(field), 'Артикул + Бренд')]
                for value, label in options:
                    value = meaningful(value, field == 'category')
                    if value:
                        p[field] = value
                        p.setdefault('_sources', {})[field] = {'file': 'Каталог V (' + ('OE' if selected == 'oe' else 'Артикул + Бренд') + '): ' + label, 'date': timestamp}
                        break
            if cat_only: return
            candidates = []
            if pt and complete(pt.get('_dimensionEvidence')):
                candidates.append((pt['_dimensionEvidence'], 'снимок того же артикула и бренда', ''))
            if selected == 'oe' and complete(h['smallest']):
                candidates.append((h['smallest'], 'меньший комплект по схожему OE', h['smallestOe']))
            passing = []
            for t, label, oe in candidates:
                if any(num(p.get(k)) > 0 and num(p.get(k)) != num(t.get(k)) for k in DIMS): continue
                if allowed and not allowed(p, t): continue
                passing.append((t, label, oe))
            if (passing and not p.get('_dimensionOeReview') and not p.get('dimensionAnomalyBlocked')
                    and any(enabled(k) and num(p.get(k)) <= 0 for k in DIMS)):
                t, label, oe = min(passing, key=lambda x: measure(x[0]))
                before = {k: p.get(k, 0) for k in DIMS}
                for k in DIMS:
                    if enabled(k) and num(p.get(k)) <= 0:
                        p[k] = num(t[k])
                        p.setdefault('_sources', {})[k] = {'file': 'Каталог V: ' + label + ' (нужна проверка)', 'date': timestamp}
                p['_dimensionOeReview'] = {'oe': oe, 'source': 'Каталог V: ' + label + ' · сверьте упаковку',
                    'at': timestamp, 'before': before, 'after': {k: p.get(k, 0) for k in DIMS}}
                p.pop('dimensionAnomalyAck', None)
            if pt:
                if not p.get('multiplicity'): p['multiplicity'] = pt.get('multiplicity', 0)
                if not p.get('image_url') and pt.get('image_url'): p['image_url'] = pt['image_url']
                if enabled('barcode') and not p.get('barcode') and pt.get('barcode'): p['barcode'] = pt['barcode']
        for selected, cat_only in ((mode, False), (cat_mode, True)):
            passes = ('oe', 'artbrand') if selected == 'auto' else (selected,)
            for current in passes: run_pass(current, cat_only)
        result.append(p)
    return result
