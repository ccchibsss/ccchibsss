"""Lossless nonfinite-number sidecars for JSON enrichment requests/responses."""
import copy
import math
import re
from dataclasses import dataclass

KINDS={'nan':math.nan,'positive':math.inf,'negative':-math.inf}
FORBIDDEN={'__proto__','constructor','prototype'}


@dataclass(frozen=True)
class JSDate:
    milliseconds: object
    text: str
    json_value: object

    def __str__(self):return self.text


def date_value(value,entry):
    ms=entry.get('milliseconds');text=entry.get('text')
    if not isinstance(text,str) or len(text)>256:raise ValueError('Неверное строковое представление Date')
    if ms is None:
        if value is not None or text!='Invalid Date':raise ValueError('Неверный Invalid Date')
    elif type(ms) not in (int,float) or not math.isfinite(ms) or ms!=int(ms) or abs(ms)>8640000000000000 or not isinstance(value,str) or not re.fullmatch(r'(?:[0-9]{4}|[+-][0-9]{6})-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z',value):
        raise ValueError('Неверное значение Date')
    if ms is not None:
        year_s,month,day,hour,minute,second,milli=re.fullmatch(r'([+-]?[0-9]+)-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})\.([0-9]{3})Z',value).groups()
        year,month,day,hour,minute,second,milli=map(int,(year_s,month,day,hour,minute,second,milli))
        canonical_year=f'{year:04}' if 0<=year<=9999 else ('+' if year>0 else '-')+f'{abs(year):06}'
        if year_s!=canonical_year or not 1<=month<=12 or not 0<=hour<24 or not 0<=minute<60 or not 0<=second<60:raise ValueError('Неканонический Date')
        leap=year%4==0 and (year%100!=0 or year%400==0)
        if not 1<=day<=[31,29 if leap else 28,31,30,31,30,31,31,30,31,30,31][month-1]:raise ValueError('Неверный день Date')
        # Proleptic Gregorian epoch conversion, including JS years outside
        # datetime's 1..9999 range. Python // is the required floor division.
        y=year-(month<=2);era=y//400;yoe=y-era*400
        doy=(153*(month+(-3 if month>2 else 9))+2)//5+day-1
        days=era*146097+yoe*365+yoe//4-yoe//100+doy-719468
        if (((days*24+hour)*60+minute)*60+second)*1000+milli!=ms:raise ValueError('Date не соответствует миллисекундам')
    return JSDate(ms,text,value)


def encode_special(value):
    entries=[]
    def visit(v,path):
        if isinstance(v,JSDate):
            entries.append({'path':path,'kind':'date','milliseconds':v.milliseconds,'text':v.text})
            return v.json_value
        if isinstance(v,float) and not math.isfinite(v):
            entries.append({'path':path,'kind':'nan' if math.isnan(v) else 'positive' if v>0 else 'negative'})
            return None
        if isinstance(v,dict):return {k:visit(x,path+[k]) for k,x in v.items()}
        if isinstance(v,list):return [visit(x,path+[i]) for i,x in enumerate(v)]
        return v
    return visit(value,[]),entries


def decode_special(value,entries):
    if not isinstance(entries,list):raise ValueError('Неверные типы чисел обогащения')
    output=copy.deepcopy(value);seen=set()
    for entry in entries:
        if not isinstance(entry,dict) or not isinstance(entry.get('kind'),str) or entry['kind'] not in (*KINDS,'date'):raise ValueError('Неверный специальный тип числа')
        path=entry.get('path')
        if not isinstance(path,list) or not path or len(path)>128 or any(type(k) not in (int,str) or isinstance(k,str) and k in FORBIDDEN for k in path):raise ValueError('Неверный путь специального числа')
        identity=tuple(path)
        if identity in seen:raise ValueError('Повторяющийся путь специального числа')
        seen.add(identity);parent=output
        for key in path[:-1]:
            if isinstance(parent,list) and type(key) is int and 0<=key<len(parent):parent=parent[key]
            elif isinstance(parent,dict) and isinstance(key,str) and key in parent:parent=parent[key]
            else:raise ValueError('Путь специального числа отсутствует')
        key=path[-1]
        if isinstance(parent,list) and type(key) is int and 0<=key<len(parent):pass
        elif isinstance(parent,dict) and isinstance(key,str) and key in parent:pass
        else:raise ValueError('Путь специального числа отсутствует')
        if entry['kind']=='date':parent[key]=date_value(parent[key],entry)
        else:
            if parent[key] is not None:raise ValueError('Специальное число должно заменять JSON null')
            parent[key]=KINDS[entry['kind']]
    return output


def equivalent(a,b):
    """Value equality for copied JSON rows, treating preserved NaN as unchanged."""
    if isinstance(a,bool) or isinstance(b,bool):return type(a) is type(b) and a==b
    if isinstance(a,dict) and isinstance(b,dict):return a.keys()==b.keys() and all(equivalent(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(equivalent(x,y) for x,y in zip(a,b))
    if isinstance(a,float) and isinstance(b,float) and math.isnan(a) and math.isnan(b):return True
    return a==b
