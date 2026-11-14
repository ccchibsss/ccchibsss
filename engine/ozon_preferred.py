"""Compose independent Ozon strict, lexical, category and lifecycle ports."""
import json
from category_tnved import norm
from category_kind import shape
from ozon_classifier import OzonClassifier
from ozon_category import OzonCategoryClassifier
from ozon_auto import apply_preferred


def compact(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'))


class OzonPreferred:
    def __init__(self,reference):
        self.reference=reference
        self.strict=OzonClassifier(reference['pairs'],reference.get('tree'),reference.get('scope','auto'))
        tree=self.strict.reference
        types=tree.entries if tree.has_data else [dict(cat=c,name=t) for c,t in reference['pairs']]
        self.strict.historical_version='historical:'+str(len(types))
        self.names=OzonCategoryClassifier(types,reference['category_rows'],reference['category_revision'])
        self.version='keyword-v6-csv-name|'+('tree:'+str(tree.snapshot.get('revision','undefined'))+':'+tree.scope if tree.has_data else 'historical:'+str(len(types)))

    def category_signature(self,p):
        tn=self.names.category
        info=tn.type_info(p);m=p.get('_categoryKindAuto');current=tn.kind_current(p)
        draft=shape(m) and str(p.get('category_type') or '')==m['type'] and not m['confirmed']
        flag=''
        if p.get('_categoryKindStatus')=='category_conflict': flag='category_conflict'
        elif p.get('_categoryKindStatus')=='ambiguous' and p.get('_categoryKindDiscriminators'):
            flag='|'.join(p['_categoryKindDiscriminators'])
        kind=compact([flag,m['referenceCategory'] if current else '', 'stale' if draft and not current else ''])
        return compact([tn.revision,norm(p.get('category')),norm(info['value']),bool(info['conflict']),bool(p.get('_categoryTypeCleared')),kind])

    def apply(self,p,*,force=False,force_name=False,enabled=True,identity_unsafe=False):
        return apply_preferred(self.strict,p,detail=self.names.detail_with_category,
            version=self.version,category_signature=self.category_signature(p),
            registry=self.reference.get('registry'),applicability=self.reference.get('applicability'),
            force=force,enabled=enabled,force_name=force_name,identity_unsafe=identity_unsafe,
            reference_version=self.reference.get('reference_version',0))
