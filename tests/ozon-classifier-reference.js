const fs=require('fs'),vm=require('vm'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const a=h.indexOf('(function (root) {'),b=h.indexOf("})(typeof globalThis !== 'undefined' ? globalThis : this);",a)+"})(typeof globalThis !== 'undefined' ? globalThis : this);".length;
const context={};vm.createContext(context);vm.runInContext(h.slice(a,b),context);
if(input.tree) {
  vm.runInContext(h.match(/const OzonReference = \{[\s\S]*?\n\};\n/)[0]+';globalThis.OzonReference=OzonReference;',context);
  context.OzonReference._ref=input.tree;
  context.S={settings:{ozonReferenceScope:input.scope || 'auto'}};
}
const C=context.OzonCat;
const pairs=C.TYPES.map(x=>[x.cat,x.name]);
process.stdout.write(JSON.stringify({pairs,results:(input.cases || input).map(x=>{const opts={registry:x.registry,applicabilityReference:x.applicability,force:!!x.force}; if(input.operation==='apply') {const row=x.row;const result=C.apply(row,opts);return {row,result};}return C.classify(x.row,opts);})}));
