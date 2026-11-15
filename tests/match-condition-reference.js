const fs=require('fs'),vm=require('vm'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const source=h.match(/function matchCond\(o, field, op, val\) \{[\s\S]*?\n\}/)[0];
const context={num:v=>Number(String(v??'').replace(',','.'))||0};vm.createContext(context);
const numStart=h.indexOf('const num = v => {'),numEnd=h.indexOf('\n};',numStart)+3;vm.runInContext(h.slice(numStart,numEnd),context);
vm.runInContext(source+';this.run=matchCond;',context);
process.stdout.write(JSON.stringify(input.map(x=>x.direct?(()=>{try{return new RegExp(x.pattern,'i').test(x.v)}catch(e){return false}})():context.run({v:x.v},'v',x.op||'regex',x.pattern))));
