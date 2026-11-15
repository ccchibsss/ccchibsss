"""MarkStatus.check and its pipeline hide action; independent of legal classification."""
import copy
import re


from enrichment_formula import string, truth, JS_SPACE


def js_string(v):return '' if v is None else string(v)


def normalize(v): return js_string(v).strip(JS_SPACE).lower().replace('ё','е')

VALID = set(map(normalize, ['введён в оборот','введен в оборот','в обороте','активен','активно','проверен','валиден','валидный','valid','ok']))
INVALID = set(map(normalize, ['выведен из оборота','выведен','выбыл','выбытие','продан','продано','реализован',
    'списан','списание','возвращён','возвращен','возврат','аннулирован','отозван','отменён','отменен',
    'просрочен','истёк','истек','недействителен','не действителен','не введён в оборот','не введен в оборот',
    'ошибка маркировки','ошибка','error','invalid','expired','cancelled','canceled','withdrawn']))


def check(status, code, required, settings=None):
    if not truth(required): return {'ok':True,'kind':'skip'}
    cfg=settings or {}
    s=normalize(status)
    # JS String.length counts UTF-16 code units, not Python Unicode characters.
    has_code=len(js_string(code).strip(JS_SPACE).encode('utf-16-le',errors='surrogatepass'))//2>=8
    if cfg.get('markRequireCode') is not False and not has_code:
        return {'ok':False,'kind':'code','reason':'нет кода маркировки'}
    if not s: return {'ok':False,'kind':'empty','reason':'статус маркировки не указан'}
    def split(v): return {normalize(x) for x in re.split('[;,]',js_string(v)) if normalize(x)}
    if s in INVALID or s in split(cfg.get('markInvalidStatuses')):
        return {'ok':False,'kind':'invalid','reason':'недопустимый статус маркировки: '+js_string(status if truth(status) else '')}
    if s in VALID or s in split(cfg.get('markValidStatuses')): return {'ok':True,'kind':'valid'}
    return {'ok':True,'kind':'unknown'}


def apply(row, settings=None):
    p=copy.deepcopy(row)
    cfg=settings or {}
    outcome=check(p.get('markStatus'),p.get('markCode'),truth(p.get('markRequired')),cfg)
    p['markCompliant']=outcome['ok']
    if truth(cfg.get('autoHideMark')) and truth(p.get('markRequired')) and not outcome['ok']:
        p.update(visible=False,visibleReason='честный_знак',policyAction='Скрыть с витрины',policyReason=outcome['reason'])
    return p,outcome
