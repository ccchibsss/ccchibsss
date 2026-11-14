const fs=require('fs'),vm=require('vm'),h=fs.readFileSync(__dirname+'/../index.html','utf8'),input=JSON.parse(fs.readFileSync(0,'utf8'));
const ctx={};vm.createContext(ctx);
for(const n of ['RULE_FIELDS','RULE_OPS','POLICY_ACTIONS'])vm.runInContext(h.match(new RegExp('const '+n+' = \\{[\\s\\S]*?\\n\\};'))[0],ctx);
const start=h.indexOf('function matchCond('),end=h.indexOf('\n/*',start);
const numStart=h.indexOf('const num = '); // Use actual shared num implementation when available.
const numMatch=h.match(/(?:function num\([^]*?\n\}|const num = [^]*?\n\};)/);
if(!numMatch)throw Error('num source not found');
vm.runInContext(numMatch[0]+'\n'+h.slice(start,end),ctx);
const a=h.indexOf('          for (const e of ex) {');
const b=h.indexOf('          if(sqlEnrichment && enrichRules.length)',a);
// SQL guard is outside the original for loop in current pipeline.
const loopStart=a>=0?a:h.indexOf('          if(!sqlEnrichment) for (const e of ex) {');
const loop=h.slice(loopStart,b).replace('if(!sqlEnrichment) ','');
ctx.input=input;
vm.runInContext(`globalThis.results=input.rows.map(p=>{const ex=input.rules.filter(e=>e.enabled).sort((a,b)=>num(a.order_no)-num(b.order_no));p.excluded=false;p.deletePending=false;p.policyAction='';p.policyReason='';${loop}return p;});`,ctx);
process.stdout.write(JSON.stringify(ctx.results));
