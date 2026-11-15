const fs=require('fs'),vm=require('vm'),assert=require('assert'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const a=h.indexOf('  async exportCatalogFormat('),b=h.indexOf('  async exportOzon(',a);
const columns=[{k:'article',n:'Код'},{k:'c_amount',n:'Число',custom:'amount',f:'@',txt:true},{k:'netProfit',n:'Прибыль',xl:()=>{throw Error('SQL must not execute browser formula generator')}}];
let request,success=false;
const ctx={S:{rows:[{article:'001',brand:'B',netProfit:123,custom:{amount:'12abc'}}]},
 currentDimUnit:()=>"cm",ensureEconomics:async()=>{},exportCatalog:()=>columns,Exp:{pick:{article:true,c_amount:true,netProfit:true},activeMps:()=>new Set()},
 exportColumnExcluded:()=>false,withProgress:async(a,b,f)=>f(),exportInputSheetKeys:()=>new Set(),COL_LET:i=>String.fromCharCode(65+i),YM_ONLY_EXPORT_FIELDS:new Set(),
 exportCatalogCellValue:(c,p)=>{assert(!c.custom,'SQL custom cells must not use browser conversion');return p[c.k]},
 $:()=>null,fmt:v=>String(v),Toast:{warn:()=>{},ok:()=>{success=true}}};
vm.createContext(ctx);vm.runInContext('this.client={'+h.slice(a,b)+'};',ctx);
const c=ctx.client;c.health=async()=>true;c._syncCatalog=async()=>{};c._fetch=async()=>{};
c.processingMode=()=> 'sql';c._settingsSnapshot=()=>({});c._download=async(path,body)=>{request=JSON.parse(JSON.stringify(body));};
(async()=>{
 assert.equal(await c.exportCatalogFormat('csv'),true);assert(success);
 assert.deepEqual(request.export_cells[0].values,['001',null,123]);
 assert.deepEqual(request.export_cells[0].custom,{amount:'12abc'});
 assert.equal(request.column_meta[1].custom,'amount');assert.equal(request.column_meta[1].custom_format,true);assert.equal(request.column_meta[1].custom_text,true);
 assert.deepEqual(request.export_cells[0].custom_dates,[]);
 assert.equal(request.export_cells[0].formulas,undefined);assert.equal(request.formula_options.enabled,false);
 assert.equal(request.column_meta[2].server_formula,true);
 await c.exportCatalogFormat('xlsx');assert.equal(request.formula_options.enabled,true);
 assert.deepEqual(request.sheets[0].indices,[0,1,2]);
 let downloaded=false;
 c._syncCatalog=async()=>{ctx.S.catalogVersion=(ctx.S.catalogVersion||0)+1;};
 c._download=async()=>{downloaded=true;};
 await assert.rejects(()=>c.exportCatalogFormat('csv'),/изменились/);assert(!downloaded);
 c._syncCatalog=async()=>{};
 c._download=async(path,body,filename,timeout,guard)=>{ctx.S.settings={changed:true};guard();downloaded=true;};
 await assert.rejects(()=>c.exportCatalogFormat('csv'),/изменились/);assert(!downloaded);
 // The actual downloader must recheck after the blob arrives, before a
 // link is created/clicked. No document/URL is supplied in this VM on purpose.
 Object.assign(ctx,{AbortController,setTimeout,clearTimeout,fetch:async()=>({ok:true,blob:async()=>({})})});
 const downloadStart=h.indexOf('  async _download('),downloadEnd=h.indexOf('  async exportCatalogFormat(',downloadStart);
 vm.runInContext('this.downloader={'+h.slice(downloadStart,downloadEnd)+'};',ctx);
 ctx.downloader.base=()=>'';ctx.downloader.token=()=>'';
 await assert.rejects(()=>ctx.downloader._download('/export/catalog.csv',{},'out.csv',1000,()=>{throw Error('stale download')}),/stale download/);
 let warning='',clicked=false;
 ctx.Toast.warn=(title,message)=>{warning=title+': '+message;};
 Object.assign(ctx,{setTimeout:()=>0,clearTimeout:()=>{},URL:{createObjectURL:()=> 'blob:test',revokeObjectURL:()=>{}},
 document:{createElement:()=>({click:()=>{clicked=true},remove:()=>{}}),body:{appendChild:()=>{}}},
 fetch:async()=>({ok:true,headers:{get:()=>JSON.stringify({skipped_formulas:['netProfit']})},blob:async()=>({})})});
 await ctx.downloader._download('/export/catalog.xlsx',{column_meta:[{key:'netProfit'}],columns:[['v','Прибыль']]},'out.xlsx');
 assert(clicked);assert(warning.includes('Прибыль'));
 console.log('OK: SQL custom export sends raw inputs, not browser-prepared cells');
})().catch(e=>{console.error(e);process.exitCode=1});
