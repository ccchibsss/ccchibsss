"""Restricted browser ExprLang grammar. Never uses eval/exec."""
import math,re
from enrichment_transport import JSDate

UNDEFINED=object()
FORBID=set('''__proto__ constructor prototype getprototypeof setprototypeof defineproperty defineproperties getownpropertydescriptor getownpropertydescriptors getownpropertynames getownpropertysymbols isprototypeof hasownproperty propertyisenumerable __definegetter__ __definesetter__ __lookupgetter__ __lookupsetter__ caller callee arguments tosource valueof tostring tolocalestring toprimitivestring isview buffer object function reflect proxy symbol globalthis global window self top parent frames eval math json process module exports require'''.split())

def string(v):
    if v is UNDEFINED: return 'undefined'
    if v is None: return 'null'
    if v is True: return 'true'
    if v is False: return 'false'
    if isinstance(v,float) and not math.isfinite(v): return 'NaN' if math.isnan(v) else 'Infinity' if v>0 else '-Infinity'
    if isinstance(v,dict): return '[object Object]'
    if isinstance(v,list): return ','.join('' if x is None or x is UNDEFINED else string(x) for x in v)
    if isinstance(v,(int,float)):
        if v==0:return '0'
        text=repr(float(v)).lower()
        if 1e-6<=abs(v)<1e21:
            from decimal import Decimal
            return format(Decimal(text),'f').rstrip('0').rstrip('.') if '.' in format(Decimal(text),'f') else format(Decimal(text),'f')
        if 'e' in text:
            mantissa,exponent=text.split('e');exponent=int(exponent)
            return mantissa.removesuffix('.0')+'e'+('+' if exponent>=0 else '-')+str(abs(exponent))
        return text.removesuffix('.0')
    return str(v)

def truth(v): return False if v is UNDEFINED or v is None or isinstance(v,float) and math.isnan(v) else bool(v) if not isinstance(v,(dict,list)) else True

# ECMAScript whitespace (Python also treats some C0 controls as whitespace).
JS_SPACE='\u0009\u000a\u000b\u000c\u000d\u0020\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff'

def number(v,allow_date=False):
    if isinstance(v,JSDate):
        if not allow_date:raise ValueError('В формуле дата участвует в арифметике')
        return v.milliseconds or 0
    if v is UNDEFINED or v is None:return 0
    if isinstance(v,bool):return 1 if v else 0
    if isinstance(v,(int,float)):return v if not isinstance(v,float) or not math.isnan(v) else 0
    if isinstance(v,(dict,list)):v=string(v)
    if isinstance(v,str):
        text=v.strip(JS_SPACE)
        if not text:return 0
        if text in ('Infinity','+Infinity','-Infinity'):return -math.inf if text[0]=='-' else math.inf
        if re.fullmatch(r'0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+',text):
            try:return float(int(text,0))
            except OverflowError:return math.inf
        if not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?',text):return 0
        return float(text)
    return 0

def arithmetic(v):
    return v if isinstance(v,(int,float)) else number(v)

def finite(v):
    n=number(v);return n if math.isfinite(n) else 0

def parsed(v):
    if isinstance(v,JSDate):raise ValueError('В формуле дата участвует в арифметике (num)')
    m=re.match(r'^[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?',''.join(c for c in string(v) if c not in JS_SPACE).replace(',','.',1))
    n=float(m[0]) if m else 0
    return n if math.isfinite(n) else 0

def power(a,b):
    x,y=finite(a),finite(b)
    try:return math.pow(x,y)
    except OverflowError:return -math.inf if x<0 and float(y).is_integer() and int(y)%2 else math.inf
    except ValueError:
        if x==0 and y<0:return -math.inf if math.copysign(1,x)<0 and float(y).is_integer() and int(y)%2 else math.inf
        return math.nan

def square_root(v):
    n=finite(v)
    return math.sqrt(n) if n>=0 else math.nan

def rounded(v,d=2):
    dd=number(d,allow_date=True)
    try:p=10.0**dd
    except OverflowError:p=math.inf
    x=number(v)*p;a=abs(x)
    if p==0 or not math.isfinite(p) or math.isnan(x):return math.nan
    if math.isinf(x):return x
    if .5-1e-9<a-math.floor(a)<.5:a=float(format(a,'.15g'))
    return (-1 if x<0 else 1)*math.floor(a+.5)/p

FUNCS={'pi':lambda:math.pi,'e':lambda:math.e,'num':parsed,'round':rounded,
 'min':lambda *a:min(map(number,a),default=math.inf),'max':lambda *a:max(map(number,a),default=-math.inf),
 'abs':lambda v:abs(finite(v)),'ceil':lambda v:math.ceil(finite(v)),'floor':lambda v:math.floor(finite(v)),
 'pow':power,'sqrt':square_root,'int':lambda v:math.trunc(finite(v)),
 'len':lambda v:len(('' if v is None or v is UNDEFINED else string(v)).encode('utf-16-le',errors='surrogatepass'))//2,
 'lower':lambda v:('' if v is None or v is UNDEFINED else string(v)).lower(),
 'upper':lambda v:('' if v is None or v is UNDEFINED else string(v)).upper(),
 'contains':lambda h,n:('' if n is None or n is UNDEFINED else string(n)).lower() in ('' if h is None or h is UNDEFINED else string(h)).lower(),
 'isBlank':lambda v:v is None or v is UNDEFINED or v=='',
 'coalesce':lambda *a:next((v for v in a if v is not None and v is not UNDEFINED and v!=''),'')}
PRECEDENCE={'||':1,'&&':2,'==':3,'===':3,'!=':3,'!==':3,'<':4,'>':4,'<=':4,'>=':4,'+':5,'-':5,'*':6,'/':6,'%':6}

class Parser:
    def __init__(self,expr):
        if any(c.isspace() and c not in JS_SPACE for c in expr):raise ValueError('Недопустимый пробельный символ')
        expr=''.join(' ' if c in JS_SPACE else c for c in expr)
        if len(expr)>400 or not re.fullmatch(r'[0-9\s.\+\-*/%(),<>=!&|?:_a-zA-Zа-яА-ЯёЁ]*',expr): raise ValueError('Недопустимая формула')
        self.tokens=[];pos=0
        pattern=re.compile(r'\s+|(?:\d[\d.]*|\.\d[\d.]*)|[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё_0-9]*|===|!==|<=|>=|==|!=|&&|\|\||[+*/%(),?:.<>-]')
        while pos<len(expr):
            m=pattern.match(expr,pos)
            if not m: raise ValueError('Неизвестный токен')
            if not m[0].isspace(): self.tokens.append(m[0])
            pos=m.end()
        self.pos=0
    def peek(self): return self.tokens[self.pos] if self.pos<len(self.tokens) else ''
    def pop(self):
        v=self.peek()
        if not v: raise ValueError('Конец формулы')
        self.pos+=1;return v
    def expect(self,v):
        if self.pop()!=v: raise ValueError('Ожидалось '+v)
    def expression(self,minimum=0):
        tk=self.pop()
        if tk in ('+','-'): node=('unary',tk,self.expression(7))
        elif tk=='(': node=self.expression();self.expect(')')
        elif tk[0].isdigit() or tk.startswith('.') and len(tk)>1: node=('number',float(tk))
        elif re.fullmatch('[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё_0-9]*',tk):
            if self.peek()=='(':
                if tk not in FUNCS and tk!='if': raise ValueError('Неизвестная функция')
                self.pop();args=[]
                if self.peek()!=')':
                    args.append(self.expression())
                    while self.peek()==',': self.pop();args.append(self.expression())
                self.expect(')');node=('call',tk,args)
            else:
                path=[tk]
                while self.peek()=='.':
                    self.pop();key=self.pop()
                    if not re.fullmatch('[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё_0-9]*',key):raise ValueError('Ожидалось имя поля')
                    path.append(key)
                if any(k.lower() in FORBID for k in path): raise ValueError('Запрещённое поле')
                node=('field',path)
        else: raise ValueError('Неожиданный токен')
        while self.peek() in PRECEDENCE and PRECEDENCE[self.peek()]>=minimum:
            op=self.pop();node=('binary',op,node,self.expression(PRECEDENCE[op]+1))
        if minimum==0 and self.peek()=='?':
            self.pop();yes=self.expression();self.expect(':');node=('ternary',node,yes,self.expression())
        return node

def run(node,scope):
    kind=node[0]
    if kind=='number': return node[1]
    if kind=='field':
        v=scope
        for k in node[1]:
            v=v.get(k,UNDEFINED) if isinstance(v,dict) else len(v) if isinstance(v,list) and k=='length' else UNDEFINED
        return v
    if kind=='unary': return arithmetic(run(node[2],scope))*(-1 if node[1]=='-' else 1)
    if kind=='ternary': return run(node[2] if truth(run(node[1],scope)) else node[3],scope)
    if kind=='call':
        name,args=node[1:]
        if name=='if':
            i=1 if args and truth(run(args[0],scope)) else 2
            return run(args[i],scope) if len(args)>i else ''
        values=[run(a,scope) for a in args]
        if name not in ('min','max','coalesce'):
            arity=0 if name in ('pi','e') else 2 if name in ('round','pow','contains') else 1
            values=(values+[UNDEFINED]*arity)[:arity]
            if name=='round' and values[1] is UNDEFINED:values[1]=2
        return FUNCS[name](*values)
    op=node[1]
    # Browser ExprLang evaluates the denominator first and does not evaluate
    # the numerator at all for a falsy divisor (including NaN and signed zero).
    if op in ('/','%'):
        y=arithmetic(run(node[3],scope))
        if not truth(y):return math.inf if op=='/' else 0
        x=arithmetic(run(node[2],scope))
        if op=='/':return x/y
        return math.nan if math.isinf(x) else math.fmod(x,y)
    a=run(node[2],scope)
    if op=='&&': return run(node[3],scope) if truth(a) else a
    if op=='||': return a if truth(a) else run(node[3],scope)
    b=run(node[3],scope)
    if op in ('==','===','!=','!=='):
        equal=(a is b if isinstance(a,(dict,list)) or isinstance(b,(dict,list)) else type(a)==type(b) and a==b) or string(a)==string(b)
        return not equal if op.startswith('!') else equal
    x=a if isinstance(a,(int,float)) else number(a)
    y=b if isinstance(b,(int,float)) else number(b)
    if op=='+': return x+y
    if op=='-': return x-y
    if op=='*': return x*y
    return {'<':lambda:x<y,'>':lambda:x>y,'<=':lambda:x<=y,'>=':lambda:x>=y}[op]()

def evaluate(expr,row):
    parser=Parser(str(expr or ''));node=parser.expression()
    if parser.peek(): raise ValueError('Лишний токен')
    return run(node,{**row,'p':row})
