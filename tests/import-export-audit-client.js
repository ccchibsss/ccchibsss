const fs=require('fs'),vm=require('vm'),assert=require('assert');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');
(async()=>{
 const downloads=[];
 const ctx={Blob,Date,Set,Map,console,S:{rows:[{article:'00042',brand:'B',name:'=HYPERLINK("bad")',custom:{extra:'@payload'}}]},
 warnQuarantinedBeforeExport:()=>{},Toast:{warn:()=>{},ok:()=>{}},fmt:String,
 exportCatalog:()=>[{k:'article',n:'Артикул'},{k:'brand',n:'Бренд'},{k:'name',n:'Название'},{k:'extra',n:'Доп',g:'custom',custom:'extra'}]};
 vm.createContext(ctx);
 for(const name of ['stripXmlIllegal','safeCsvText']){
  const a=h.indexOf('function '+name+'('),b=h.indexOf('\n}',a)+2;vm.runInContext(h.slice(a,b),ctx);
 }
 /* stripXmlIllegal и safeCsvText используют константы, объявленные рядом:
    XML_ILLEGAL_RE (уже есть в сборке) и XCSV_SLOW (быстрый путь v12.9.171). */
 vm.runInContext(h.slice(h.indexOf('const XCSV_SLOW'),h.indexOf('\n',h.indexOf('const XCSV_SLOW'))+1),ctx);
 if(!('XML_ILLEGAL_RE' in ctx)) vm.runInContext('var XML_ILLEGAL_RE=/[\\u0000-\\u0008\\u000B\\u000C\\u000E-\\u001F\\uFFFE\\uFFFF]/;',ctx);
 const a=h.indexOf('  async downloadReimportKit() {'),b=h.indexOf('\n  open() {',a);
 vm.runInContext('this.Exp={rows:()=>S.rows,_yield:async()=>{},download:(blob,name)=>capture(blob,name),'+h.slice(a,b)+'};',Object.assign(ctx,{capture:(blob,name)=>downloads.push({blob,name})}));
 await ctx.Exp.downloadReimportKit();
 assert.equal(downloads.length,2);
 for(const file of downloads){const text=await file.blob.text();assert(text.includes('00042'));assert(text.includes("'=HYPERLINK"));}
 assert((await downloads[1].blob.text()).includes("'@payload"));
 console.log('OK: reimport kit retains text SKU and neutralizes formula triggers');
})().catch(e=>{console.error(e);process.exitCode=1});
