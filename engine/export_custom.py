"""Independent general-export custom-cell conversion, matching exportCatalogCellValue."""
import math
import re
from enrichment_formula import JS_SPACE, UNDEFINED, string


def export_number(value):
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        return value if math.isfinite(value) else 0
    if value is None or value is UNDEFINED or value=='':return 0
    text=''.join(c for c in string(value) if c not in JS_SPACE)
    if text.endswith('%'):text=text[:-1]
    comma,dot=',' in text,'.' in text
    if comma and dot:
        text=text.replace('.','').replace(',','.',1) if text.rfind(',')>text.rfind('.') else text.replace(',','')
    elif comma:text=text.replace(',','') if text.count(',')>1 else text.replace(',','.',1)
    elif text.count('.')>1:text=text.replace('.','')
    match=re.match(r'^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?',text.lstrip(JS_SPACE))
    n=float(match[0]) if match else 0
    return n if math.isfinite(n) else 0


def custom_cell(raw,key,formatted,date_keys=(),nonfinite_keys=(),textual=False,special=None):
    value=raw.get(key,UNDEFINED)
    if textual:
        if key in nonfinite_keys:return (special or {}).get(key,'Infinity')
        return '' if value is None or value is UNDEFINED else string(value)
    # Older descriptors without c.txt retain the generic formatter contract.
    if key in date_keys:return 0
    if key in nonfinite_keys:return 0 if formatted else None
    if formatted and value is not None and value is not UNDEFINED and value!='':return export_number(value)
    return None if value is UNDEFINED else value
