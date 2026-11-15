const fs=require('fs'),vm=require('vm'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const start=h.indexOf('const ExprLang = (function () {'),end=h.indexOf('/* Поля, где встреченный JS Date',start);
const condition=h.match(/function matchCond\(o, field, op, val\) \{[\s\S]*?\n\}/)[0];
const name=h.match(/const NameCategory = \{[\s\S]*?\n\};\n/)[0];
const a=h.indexOf('for (const r of enrichRules) {',h.indexOf('function runPipeline'));
const b=h.indexOf('          /* Правило обогащения могло',a);
const context={num:v=>Number(String(v??'').replace(',','.'))||0,round:(v,d=2)=>Math.round(v*10**d)/10**d};
vm.createContext(context);
const numStart=h.indexOf('const num = v => {'),numEnd=h.indexOf('\n};',numStart)+3;vm.runInContext(h.slice(numStart,numEnd),context);
vm.runInContext(h.slice(start,end)+'\n'+condition+'\n'+name+'\nthis.run=(p,enrichRules,nameCategoryContext)=>{'+h.slice(a,b)+';return p;};',context);
context.input=input;vm.runInContext(`for(const e of input.special_values||[]){let p=input.rows;for(const k of e.path.slice(0,-1))p=p[k];p[e.path.at(-1)]=e.kind==='date'?(e.milliseconds===null?new Date(NaN):new Date(e.milliseconds)):e.kind==='positive'?Infinity:e.kind==='negative'?-Infinity:NaN;}`,context);
const output=input.rows.map(p=>context.run(p,input.rules,input.context));
if(input.typed){const special_values=[];const walk=(v,path)=>{if(Object.prototype.toString.call(v)==='[object Date]'){special_values.push({path,kind:'date',milliseconds:Number.isFinite(v.getTime())?v.getTime():null,text:String(v)});}else if(typeof v==='number'&&!Number.isFinite(v)){special_values.push({path,kind:Number.isNaN(v)?'nan':v>0?'positive':'negative'});}else if(v&&typeof v==='object')for(const [k,x] of Object.entries(v))walk(x,path.concat(Array.isArray(v)?Number(k):k));};walk(output,[]);process.stdout.write(JSON.stringify({rows:output,special_values}));}
else process.stdout.write(JSON.stringify(output));
