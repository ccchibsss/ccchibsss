const fs=require('fs'),vm=require('vm');
const html=fs.readFileSync(__dirname+'/../index.html','utf8');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const extract=name=>html.match(new RegExp('const '+name+' = \\{[\\s\\S]*?\\n\\};\\n'))[0];
const context={CATEGORY_TNVED_ROWS:input.rows,BASE_CATS:(input.base||[]).map(c=>[c]),nowISO:()=> '2026-01-01T00:00:00Z',S:{settings:{},cats:[],rules:[]}};vm.createContext(context);
const a=html.indexOf('const OzonNameLexicon = (() => {'), b=html.indexOf('\nif (typeof globalThis',a);
vm.runInContext(html.match(/function ozonSourceMap\(p\) \{[\s\S]*?\n\}/)[0]+'\n'+html.slice(a,b)+'\n'+extract('NameCategory')+'\n'+extract('OzonAuto')+'\n'+extract('CategoryTnved')+'\n'+extract('CsvNameMatcher')+'\n'+extract('CategoryKindAuto')+'\nthis.C=CsvNameMatcher;this.K=CategoryKindAuto;this.T=CategoryTnved;this.N=NameCategory;',context);
const clean=v=>v instanceof Set ? [...v] : v;
// Cross-context Maps/Sets are identified by their tag rather than instanceof.
const replacer=(k,v)=>Object.prototype.toString.call(v)==='[object Map]'?Object.fromEntries(v):Object.prototype.toString.call(v)==='[object Set]'?[...v]:v;
context.T.revision=input.revision||'test-v1';context.K.version='csv-kind-name-v1|'+context.T.revision;context.N.hasExplicitCategorySource=p=>!!p._categoryExplicitSource;
vm.runInContext("OzonAuto._index=()=>({heads:new Set()});this.ctx=NameCategory.prepare();this.ctx.version='ctx';",context);
const results=[];
for(const p of input.products) {
  let changed=null,marker=null,error=null;
  if(input.operation==='confirm') changed=context.K.confirm(p,!!input.categoryConfirmed);
  else if(input.operation==='hydrate') context.K.hydrate(p,p._categoryKindAuto);
  else if(input.operation==='explicit_import') context.K.explicitImport(p,p.category_type,(p._sources || {}).category_type);
  else if(input.operation==='cloud') {try {marker=context.K.markerForCloud(p);}catch(e){error=e.message;}}
  else context.K.apply(p,context.ctx,input.enabled);
  results.push({row:p,changed,marker,error});
}
process.stdout.write(JSON.stringify(input.operation ? results : input.products,replacer));
