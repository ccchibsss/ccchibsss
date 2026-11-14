const fs=require('fs'),vm=require('vm');
const html=fs.readFileSync(__dirname+'/../index.html','utf8');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const extract=name=>html.match(new RegExp('const '+name+' = \\{[\\s\\S]*?\\n\\};\\n'))[0];
const source=html.match(/function ozonSourceMap\(p\) \{[\s\S]*?\n\}/)[0];
const context={CATEGORY_TNVED_ROWS:input.reference.rows,S:{settings:{autoCategoryByName:input.enabled!==false}},
  nowISO:()=> '2026-01-01T00:00:00Z'};
vm.createContext(context);
vm.runInContext(source+'\n'+extract('CategoryTnved')+'\n'+extract('CategoryKindAuto')+'\nthis.C=CategoryTnved;',context);
context.C.revision=input.reference.revision;
context.C.source=input.reference.source;
// CategoryKindAuto version is derived during evaluation from the browser revision.
vm.runInContext("CategoryKindAuto.version='csv-kind-name-v1|'+CategoryTnved.revision;",context);
const out=input.rows.map(p=>({row:p,result:context.C.apply(p)}));
process.stdout.write(JSON.stringify(out));
