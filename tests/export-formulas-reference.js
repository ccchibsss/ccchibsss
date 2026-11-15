const fs=require('fs'),vm=require('vm'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const context={S:{settings:{},custom:[]},ChzTnved:{rules:()=>[]},dimFieldLabel:x=>x,supportedCustomColumn:()=>true};
vm.createContext(context);
const a=h.indexOf('function exportCatalog() {'),b=h.indexOf('/* Exact category names',a);
vm.runInContext(h.slice(a,b)+';this.columns=exportCatalog();',context);
for(const name of ['exportMarketplaceOf','marketplaceResultUnavailable','missingTariffExportUnavailable','exportCellUnavailable']){
 const s=h.indexOf('function '+name+'('),e=h.indexOf('\n}',s)+2;
 vm.runInContext(h.slice(s,e),context);
}
for(const key of ['INVALID_ECON_EXPORT_FIELDS','YM_EXPORT_ONLY_FIELDS','MARKET_ECON_FIELD_MP']){
 const s=h.indexOf('const '+key+' = '),e=h.indexOf(';',s)+1;vm.runInContext(h.slice(s,e),context);
}
const s=h.indexOf('  _sanitizeFormula(fs) {'),e=h.indexOf('  /* универсальная ячейка',s);
vm.runInContext('this.sanitizer={'+h.slice(s,e)+'};',context);
const result=input.map(x=>{
 context.currentDimUnit=()=>x.unit||'cm';
 const c=context.columns.find(c=>c.k===x.key);
 const unavailable=context.exportCellUnavailable(x.context||{},x.key,x.group||c?.g||'calc');
 if(x.availability)return unavailable;
 if(!c?.xl || unavailable)return null;
 const refs={...x.refs,__ymAbsent:k=>['specialFee','penalties'].includes(k)&&!(k in x.refs)};
 const strict=new Proxy(refs,{get(t,k){if(!(k in t))throw Error('missing');return t[k]}});
 try{let f=context.sanitizer._sanitizeFormula(c.xl(x.row||2,strict));
  if(f&&typeof x.value==='number'&&isFinite(x.value)&&!/^IFERROR\(/i.test(f))f=`IFERROR(${f},"")`;
  return f;
 }catch(e){return null;}
});
process.stdout.write(JSON.stringify({keys:context.columns.filter(c=>c.xl).map(c=>c.k),result}));
