"""HVC identity guards from raw catalogue, parts and byArt snapshots."""
import re
from category_tnved import text


def key(v): return re.sub('[^A-Z0-9А-ЯЁ]','',text(v).upper())
def pair(p): return key(p.get('article'))+'|'+key(p.get('brand'))


def codes(value,mode='auto'):
    values=value if isinstance(value,list) else [value]
    seen=set()
    pattern={'newline':r'\r?\n','comma':',','semicolon':';','slash':'/','pipe':r'\|'}.get(mode,r'[/;,\n\r|]+')
    for value in values:
        raw_value=','.join(text(x) for x in value) if isinstance(value,list) else text(value)
        for raw in re.split(pattern,raw_value):
            raw=raw.strip();compact=re.sub(r'[\s\u00a0]','',raw)
            compact=re.sub(r'^р\.?','',compact,flags=re.I)
            if re.fullmatch(r'[0-9]+[.,]0+',compact): raw=re.sub(r'[.,]0+$','',compact)
            normalized=key(raw)
            if normalized and normalized not in seen:
                seen.add(normalized);yield normalized


class IdentityGuard:
    def __init__(self,rows,reference):
        self.parts=dict(reference.get('parts') or [])
        self.unsafe=set();self.mode=reference.get('oe_mode','auto')
        for p in rows:
            if self.mismatch(p): self.unsafe.add(pair(p))
        by_art=dict(reference.get('byArt') or [])
        self.unsafe_oes={key(oe) for k in self.unsafe for oe in by_art.get(k,[])}

    def mismatch(self,p):
        part=self.parts.get(pair(p)) or {}
        return bool((part.get('artikul') and key(part['artikul'])!=key(p.get('article'))) or
                    (part.get('brand') and key(part['brand'])!=key(p.get('brand'))))

    def unsafe_for(self,p):
        return pair(p) in self.unsafe or self.mismatch(p) or any(
            oe in self.unsafe_oes for field in ('oe_numbers','oe_list','oe_norm') for oe in codes(p.get(field),self.mode))
