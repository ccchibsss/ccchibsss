const fs=require('fs'),vm=require('vm'),h=fs.readFileSync(__dirname+'/../index.html','utf8'),input=JSON.parse(fs.readFileSync(0,'utf8'));
const ctx={_normArticleCache:new Map(),_POW10:{},S:{settings:{oeDelimiter:input.mode||'auto'}}};vm.createContext(ctx);
const obj=n=>h.match(new RegExp('const '+n+' = \\{[\\s\\S]*?\\n\\};'))[0];
const fn=n=>{const a=h.indexOf('function '+n+'(');return h.slice(a,h.indexOf('\n}',a)+2)};
const val=n=>{const a=h.indexOf('const '+n+' = ');return h.slice(a,h.indexOf('\n};',a)+3)};
vm.runInContext(val('normArticle')+'\n'+val('round')+'\n'+obj('OE_DELIMITERS')+'\n'+['oeMode','splitCodeValues','codeList'].map(fn).join('\n')+'\n'+obj('DimPolicy')+'\nglobalThis.D=DimPolicy;',ctx);
process.stdout.write(JSON.stringify({links:(input.links||[]).map(x=>ctx.D.sourceAllowed(x.target,x.self?x.target:x.candidate,x.matchedCode)),
 similar:(input.similar||[]).map(([a,b])=>ctx.D.similarOe(a,b)),
 picks:(input.picks||[]).map(x=>ctx.D.pick(null,x.candidates,x.maxWeight==null?null:t=>Number(t.weight)<=x.maxWeight))}));
