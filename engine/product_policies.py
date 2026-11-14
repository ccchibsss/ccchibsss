"""Ordered product-policy actions, matching the browser pipeline."""
import copy
from category_tnved import text

RULE_FIELDS = {'category': 'Категория', 'brand': 'Бренд', 'name': 'Название', 'article': 'Артикул', 'oe_numbers': 'OE-номера', 'price': 'Цена', 'cost': 'Себестоимость', 'weight': 'Вес', 'volume': 'Объём', 'stock': 'Остаток', 'minStock': 'Мин. остаток', 'sales': 'Продажи', 'noBuyPct': 'Прогноз невыкупа, %', 'markRequired': 'Требуется Честный знак', 'markStatus': 'Статус Честного знака', 'markCode': 'Код маркировки', 'visible': 'Видимость', 'src': 'Общий текст', 'category_src': 'Исходная категория'}
RULE_OPS = {'contains': 'содержит', '!contains': 'не содержит', 'eq': 'равно', 'ne': 'не равно', 'gt': 'больше', 'lt': 'меньше', 'startsWith': 'начинается с', 'regex': 'регулярное выражение', 'empty': 'пусто'}
POLICY_ACTIONS = {'exclude': 'Исключить из расчётов', 'hide': 'Скрыть с витрины', 'delete_mark': 'Пометить на удаление', 'warn': 'Только предупредить'}


def apply_policies(row,rules,match,number):
    p=copy.deepcopy(row)
    p.update(excluded=False,deletePending=False,policyAction='',policyReason='')
    active=sorted((r for r in rules if r.get('enabled')),key=lambda r:number(r.get('order_no')))
    for r in active:
        field=r.get('field');op=r.get('op');value=r.get('value')
        if not match(p,field,op,value): continue
        action=r.get('action') or 'exclude'
        p['policyAction']=POLICY_ACTIONS.get(action) or action
        p['policyReason']=f"{RULE_FIELDS.get(field) or field} {RULE_OPS.get(op) or op} {text(value) if 'value' in r else 'undefined'}"
        if action=='exclude': p['excluded']=True
        if action=='hide': p.update(visible=False,visibleReason='товарная_политика')
        if action=='delete_mark': p.update(deletePending=True,visible=False,visibleReason='ожидает_удаления')
    return p
