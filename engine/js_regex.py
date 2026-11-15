"""Translate common non-Unicode ECMAScript RegExp constructs to Python re.

Used by matchCond (no flags other than i). No JavaScript runtime is invoked.
This is not a complete ECMAScript regexp implementation; see audit limitations.
"""
import re
from functools import lru_cache
from enrichment_formula import JS_SPACE


def utf16(text):
    data=text.encode('utf-16-le',errors='surrogatepass')
    return ''.join(chr(data[i]|data[i+1]<<8) for i in range(0,len(data),2))


def canonical(char):
    # ECMA Canonicalize without /u: uppercase, but do not fold a non-ASCII
    # code unit to ASCII or expand one code unit to several (e.g. sharp s).
    upper=char.upper()
    return char if len(upper)!=1 or ord(char)>=128 and ord(upper)<128 else upper


SPACE=''.join(re.escape(c) for c in JS_SPACE)
WORD='A-Za-z0-9_'


def class_pattern(p,start):
    """Parse a legacy JS class as UTF-16 sets before case canonicalization."""
    i=start;negative=i<len(p) and p[i]=='^'
    if negative:i+=1
    atoms=[]
    predefined={'d':set(map(ord,'0123456789')),
                'w':set(map(ord,'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_')),
                's':set(map(ord,JS_SPACE))}
    while i<len(p) and p[i]!=']':
        c=p[i];i+=1;dash=c=='-'
        if c=='\\':
            if i==len(p):raise ValueError('Trailing class escape')
            c=p[i];i+=1;dash=False
            if c.lower() in predefined:
                chars=predefined[c.lower()]
                atoms.append((chars if c.islower() else set(range(65536))-chars,None,False));continue
            if c in 'xu':
                n=2 if c=='x' else 4;digits=p[i:i+n]
                if len(digits)==n and re.fullmatch('[0-9a-fA-F]+',digits):c=chr(int(digits,16));i+=n
            elif c=='c' and i<len(p) and (p[i].isascii() and (p[i].isalnum() or p[i]=='_')):
                c=chr(ord(p[i].upper())%32);i+=1
            elif c in '01234567':
                digits=c
                while i<len(p) and p[i] in '01234567' and len(digits)<(3 if digits[0] in '0123' else 2):digits+=p[i];i+=1
                c=chr(int(digits,8))
            else:c={'b':'\b','f':'\f','n':'\n','r':'\r','t':'\t','v':'\v'}.get(c,c)
        atoms.append(({ord(c)},ord(c),dash))
    if i==len(p):raise ValueError('Unclosed character class')
    chars=set();j=0
    while j<len(atoms):
        if j+2<len(atoms) and atoms[j+1][2]:
            left,right=atoms[j][1],atoms[j+2][1]
            if left is not None and right is not None:
                if left>right:raise ValueError('Invalid class range')
                chars.update(range(left,right+1));j+=3;continue
        chars.update(atoms[j][0]);j+=1
    codes=sorted({ord(canonical(chr(n))) for n in chars})
    if not codes:return ('[\\s\\S]' if negative else '(?!)'),i+1
    # Compress the explicit set; escape every endpoint so Python class syntax
    # (including set-operation-looking punctuation) cannot alter its meaning.
    ranges=[];first=last=codes[0]
    def emit(a,b):
        esc=lambda n:'\\u%04x'%n
        return esc(a) if a==b else esc(a)+esc(b) if b==a+1 else esc(a)+'-'+esc(b)
    for n in codes[1:]:
        if n==last+1:last=n
        else:ranges.append(emit(first,last));first=last=n
    ranges.append(emit(first,last))
    return '['+('^' if negative else '')+''.join(ranges)+']',i+1


def capture_layout(p):
    starts={};ends={};names={};stack=[];i=0
    while i<len(p):
        c=p[i];i+=1
        if c=='\\':i+=1;continue
        if c=='[':
            while i<len(p) and p[i]!=']':
                if p[i]=='\\':i+=1
                i+=1
            i+=1;continue
        if c=='(':
            name=None
            capture=p[i:i+1]!='?'
            if p[i:i+2]=='?<' and p[i+2:i+3] not in ('=','!'):
                end=p.find('>',i+2)
                if end<0:raise ValueError('Invalid named capture')
                name=p[i+2:end];capture=True
            number=len(starts)+1 if capture else None
            if capture:
                starts[i-1]=number
                if name is not None:
                    if not name or not name.replace('$','_').isidentifier() or name in names:raise ValueError('Invalid or duplicate capture name')
                    names[name]=number
            stack.append(number)
        elif c==')':
            if not stack:raise ValueError('Unmatched closing group')
            number=stack.pop()
            if number is not None:ends[number]=i
    if stack:raise ValueError('Unclosed group')
    return starts,ends,names


def reference(number,position,ends):
    # In legacy JS a reference to a not-yet-participating capture succeeds
    # with the empty string. Python instead fails on unmatched captures.
    if ends.get(number,position+1)>position:return '(?:)'
    return '(?(js%d)(?P=js%d)|)'%(number,number)


@lru_cache(maxsize=512)
def compile_pattern(pattern):
    p=utf16(pattern);out=[];i=0
    captures,ends,names=capture_layout(p)
    while i<len(p):
        c=p[i];i+=1
        if c=='\\':
            if i==len(p):raise ValueError('Trailing escape')
            e=p[i];i+=1
            classes={'d':'0-9','D':'^0-9','w':WORD,'W':'^'+WORD,'s':SPACE,'S':'^'+SPACE}
            if e in classes:
                out.append('['+classes[e]+']');continue
            if e in ('b','B'):
                out.append('(?a:\\'+e+')');continue
            if e in ('x','u'):
                size=2 if e=='x' else 4;digits=p[i:i+size]
                if len(digits)==size and re.fullmatch('[0-9a-fA-F]+',digits):
                    out.append(re.escape(canonical(chr(int(digits,16)))));i+=size
                else:out.append(re.escape(canonical(e)))
                continue
            if e=='c':
                if i<len(p) and p[i].isascii() and p[i].isalpha():
                    out.append(re.escape(chr(ord(p[i].upper())%32)));i+=1
                else:out.append(re.escape('\\c'))
                continue
            if e in 'fnrtv':
                out.append(re.escape({'f':'\f','n':'\n','r':'\r','t':'\t','v':'\v'}[e]));continue
            if e in '0123456789':
                end=i
                while end<len(p) and p[end] in '0123456789':end+=1
                digits=e+p[i:end];number=int(digits)
                if e!='0' and number<=len(captures):
                    out.append(reference(number,i-2,ends));i=end;continue
                if e in '01234567':
                    octal=e
                    while i<len(p) and p[i] in '01234567' and len(octal)<(3 if e in '0123' else 2):octal+=p[i];i+=1
                    out.append(re.escape(canonical(chr(int(octal,8)))))
                else:out.append(e)
                continue
            if e=='k' and i<len(p) and p[i]=='<' and names:
                end=p.find('>',i+1);name=p[i+1:end]
                if end<0 or name not in names:raise ValueError('Invalid named reference')
                out.append(reference(names[name],i-2,ends));i=end+1;continue
            # Identity escapes (\a, \z, ...) are literals in legacy JS mode.
            out.append(re.escape(canonical(e)));continue
        if c=='[':
            translated,i=class_pattern(p,i);out.append(translated);continue
        if c=='.':out.append('[^\n\r\u2028\u2029]');continue
        if c=='$':out.append('\\Z');continue
        if c=='(' and i-1 in captures:
            out.append('(?P<js%d>'%captures[i-1])
            if p[i:i+2]=='?<':i=p.index('>',i+2)+1
            continue
        if c=='(' and i<len(p) and p[i]=='?':
            if p[i:i+2] in ('?:','?=','?!'):out.append('('+p[i:i+2]);i+=2;continue
            if p[i:i+3] in ('?<=','?<!'):out.append('('+p[i:i+3]);i+=3;continue
            raise ValueError('Non-ECMAScript group')
        if c in '*+?}' and i<len(p) and p[i]=='+':raise ValueError('Possessive quantifier is not ECMAScript')
        out.append(canonical(c))
    return re.compile(''.join(out))


def search(pattern,text):
    try:return compile_pattern(pattern).search(''.join(map(canonical,utf16(text)))) is not None
    except (ValueError,re.error,OverflowError,RecursionError):return False
