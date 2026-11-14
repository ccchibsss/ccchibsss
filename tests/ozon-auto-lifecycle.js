const fs=require('fs'),vm=require('vm'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const cases=JSON.parse(fs.readFileSync(0,'utf8'));
const a=h.indexOf('(function (root) {'), end="})(typeof globalThis !== 'undefined' ? globalThis : this);";
const results=cases.map(x=>{
const ctx={};vm.createContext(ctx);vm.runInContext(h.slice(a,h.indexOf(end,a)+end.length),ctx);
vm.runInContext(h.slice(h.indexOf('const OzonAuto = {'),h.indexOf("if (typeof globalThis !== 'undefined') globalThis.OzonAuto = OzonAuto;"))+'globalThis.OzonAuto=OzonAuto;',ctx);
const realApply=ctx.OzonCat.apply;
 ctx.S={settings:{autoCategoryByName:x.enabled!==false}};
 ctx.HVC={identityUnsafe:()=>!!x.unsafe,identityUnsafeOeFor:()=>false};
 ctx.OzonAuto._index=()=>({version:'v1'});
 ctx.OzonAuto.categorySignature=()=> 'sig';
 ctx.OzonAuto.detailWithCategory=()=>x.detail;
 ctx.OzonCat.apply=(p,o)=>realApply(p,{...o,registry:x.registry || {}});
 const row=x.row,result=ctx.OzonAuto.applyPreferred(row,{force:x.force,forceName:x.forceName});
 return {row,result};
});
process.stdout.write(JSON.stringify({results}));
