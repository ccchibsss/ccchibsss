"""Restricted browser ExprLang grammar. Never uses eval/exec."""
import math,re

UNDEFINED=object()
FORBID=set('''__proto__ constructor prototype getprototypeof setprototypeof defineproperty defineproperties getownpropertydescriptor getownpropertydescriptors getownpropertynames getownpropertysymbols isprototypeof hasownproperty propertyisenumerable __definegetter__ __definesetter__ __lookupgetter__ __lookupsetter__ caller callee arguments tosource valueof tostring tolocalestring toprimitivestring isview buffer object function reflect proxy symbol globalthis global window self top parent frames eval math json process module exports require'''.split())

def string(v):
    if v is UNDEFINED: return 'undefined'
    if v is None: return 'null'
    if v is True: return 'true'
    if v is False: return 'false'
    if isinstance(v,(int,float)) and math.isfinite(v) and v==int(v): return str(int(v))
    return str(v)

def truth(v): return False if v is UNDEFINED or v is None else bool(v) if not isinstance(v,(dict,list)) else True

def number(v):
    if v is UNDEFINED: return 0
    if v is None: return 0
    try: n=float(v.strip() or 0) if isinstance(v,str) else float(v)
    except (ValueError,TypeError): return 0
    return n if not math.isnan(n) else 0

def finite(v):
    n=number(v);return n if math.isfinite(n) else 0

def parsed(v):
    m=re.match(r'^[+-]?(?:\d+\.?\d*|\.\d+)',re.sub(r'\s+','',string(v)).replace(',','.'))
    return float(m[0]) if m else 0

def rounded(v,d=2):
    p=10**number(d);x=number(v)*p;a=abs(x)
    if .5-1e-9<a-math.floor(a)<.5: a=float(format(a,'.15g'))
    return (-1 if x<0 else 1)*math.floor(a+.5)/p

FUNCS={'pi':lambda:math.pi,'e':lambda:math.e,'num':parsed,'round':rounded,
 'min':lambda *a:min(map(number,a),default=math.inf),'max':lambda *a:max(map(number,a),default=-math.inf),
 'abs':lambda v:abs(finite(v)),'ceil':lambda v:math.ceil(finite(v)),'floor':lambda v:math.floor(finite(v)),
 'pow':lambda a,b:math.pow(finite(a),finite(b)),'sqrt':lambda v:math.sqrt(finite(v)),'int':lambda v:math.trunc(finite(v)),
 'len':lambda v:len(('' if v is None or v is UNDEFINED else string(v)).encode('utf-16-le'))//2,
 'lower':lambda v:('' if v is None or v is UNDEFINED else string(v)).lower(),
 'upper':lambda v:('' if v is None or v is UNDEFINED else string(v)).upper(),
 'contains':lambda h,n:('' if n is None or n is UNDEFINED else string(n)).lower() in ('' if h is None or h is UNDEFINED else string(h)).lower(),
 'isBlank':lambda v:v is None or v is UNDEFINED or v=='',
 'coalesce':lambda *a:next((v for v in a if v is not None and v is not UNDEFINED and v!=''),'')}
PRECEDENCE={'||':1,'&&':2,'==':3,'===':3,'!=':3,'!==':3,'<':4,'>':4,'<=':4,'>=':4,'+':5,'-':5,'*':6,'/':6,'%':6}

class Parser:
    def __init__(self,expr):
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
                while self.peek()=='.': self.pop();path.append(self.pop())
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
        for k in node[1]: v=v.get(k,UNDEFINED) if isinstance(v,dict) else UNDEFINED
        return v
    if kind=='unary': return number(run(node[2],scope))*(-1 if node[1]=='-' else 1)
    if kind=='ternary': return run(node[2] if truth(run(node[1],scope)) else node[3],scope)
    if kind=='call':
        name,args=node[1:]
        if name=='if':
            i=1 if args and truth(run(args[0],scope)) else 2
            return run(args[i],scope) if len(args)>i else ''
        return FUNCS[name](*(run(a,scope) for a in args))
    op=node[1];a=run(node[2],scope)
    if op=='&&': return run(node[3],scope) if truth(a) else a
    if op=='||': return a if truth(a) else run(node[3],scope)
    b=run(node[3],scope)
    if op in ('==','===','!=','!=='):
        equal=(type(a)==type(b) and a==b) or string(a)==string(b)
        return not equal if op.startswith('!') else equal
    x,y=number(a),number(b)
    if op=='+': return x+y
    if op=='-': return x-y
    if op=='*': return x*y
    if op=='/': return x/y if y else math.inf
    if op=='%': return math.fmod(x,y) if y else 0
    return {'<':lambda:x<y,'>':lambda:x>y,'<=':lambda:x<=y,'>=':lambda:x>=y}[op]()

def evaluate(expr,row):
    parser=Parser(str(expr or ''));node=parser.expression()
    if parser.peek(): raise ValueError('Лишний токен')
    return run(node,{**row,'p':row})
