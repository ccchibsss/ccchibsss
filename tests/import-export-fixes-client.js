const fs=require('fs'),vm=require('vm'),assert=require('assert'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
(async()=>{
 const ctx={console,Set,Map,JSON,AbortController,setTimeout,clearTimeout,
 S:{rows:[{article:'001',brand:'B',price:0,cost:0,custom:{}}],settings:{},catalogVersion:1},
 num:v=>Number(v)||0,productVolumeIsExplicit:()=>false,tariffFor:()=>({}),tariffQuoteAudit:()=>null,
 currentPayoutSettings:()=>({pct:0}),forecastNoBuyRateInfo:()=>({rate:0}),
 withProgress:async(a,b,fn)=>fn(),Toast:{warn:()=>{},ok:()=>{}},fmt:String,
 OzonReference:{hasData:()=>true,entries:()=>[{cat:'cat',type:'type'}]},ozonDiscountPct:()=>0};
 vm.createContext(ctx);
 const a=h.indexOf('  async _syncCatalog('),b=h.indexOf('  async exportCatalog()',a);
 vm.runInContext('this.client={'+h.slice(a,b)+'};',ctx);
 let calls=[],failChunk=false;
 const p=ctx.client;
 p._fetch=async(path,opts)=>{const body=JSON.parse(opts.body);calls.push(body);assert.equal(path,'/catalog/sync');if(body.action==='begin')return {token:'t'};if(body.action==='chunk'&&failChunk)throw Error('network');return {};};
 await p._syncCatalog('test');assert.deepEqual(calls.map(c=>c.action),['begin','chunk','commit']);assert.equal(calls[1].rows[0].price,0);
 calls=[];failChunk=true;await assert.rejects(()=>p._syncCatalog(),/network/);assert(!calls.some(c=>c.action==='commit'));
 calls=[];failChunk=false;ctx.S.rows=[];await p._syncCatalog();assert.deepEqual(calls.map(c=>c.action),['begin','commit']);
 p._fetch=async(path,opts)=>{const body=JSON.parse(opts.body);if(body.action==='begin'){ctx.S.catalogVersion++;return {token:'t'}}throw Error('must not commit stale snapshot')};
 await assert.rejects(()=>p._syncCatalog(),/изменился/);
 // Ozon: fail closed on reference upload; reject edits while downloading.
 const x=h.indexOf('  async exportOzon('),y=h.indexOf('  async parseFile(',x);
 vm.runInContext('this.ozon={'+h.slice(x,y)+'};',ctx);
 const o=ctx.ozon;o.health=async()=>true;o.prepareOzonTyping=async()=>{};o._syncCatalog=async()=>{};o.processingMode=()=> 'sql';o.base=()=>'';o.token=()=>'';
 let fetched=false,clicked=false,changeBlob=false;
 ctx.fetch=async()=>{fetched=true;return {ok:true,blob:async()=>{if(changeBlob)ctx.S.catalogVersion++;return {}}}};
 ctx.document={createElement:()=>({click:()=>{clicked=true},remove:()=>{}}),body:{appendChild:()=>{}}};ctx.URL={createObjectURL:()=>'',revokeObjectURL:()=>{}};
 o._fetch=async()=>{throw Error('pairs offline')};await assert.rejects(()=>o.exportOzon('csv',[]),/pairs offline/);assert(!fetched&&!clicked);
 o._fetch=async(path,opts)=>{const body=JSON.parse(opts.body);assert.equal(body.replace,true);assert.deepEqual(body.pairs,[{category:'cat',type:'type'}]);return {}};
 changeBlob=true;await assert.rejects(()=>o.exportOzon('csv',[]),/изменились/);assert(!clicked);
 changeBlob=false;ctx.setTimeout=()=>0;await o.exportOzon('csv',[]);assert(clicked);
 // SQL parsing feeds the SAME preview/mapping code; no XLSX/CsvStream fallback.
 const r=h.indexOf('  async read(file) {',h.indexOf('const Import = {'));
 const start=h.indexOf('      let table = [];',r),end=h.indexOf("      if (!table.length)",start);
 ctx.PyEngine={processingAvailable:async()=>true,parseFile:async(f,opts)=>{assert.equal(opts.table,true);return Object.assign([['0001','x']],{headers:['Артикул','Extra']})}};
 vm.runInContext('this.readTable=async(file)=>{'+h.slice(start,end)+'return table;};',ctx);
 assert.deepEqual(JSON.parse(JSON.stringify(await ctx.readTable({name:'a.csv'}))),[['Артикул','Extra'],['0001','x']]);
 assert(h.includes('await PyEngine.processingAvailable(); Import.pick();'));
 // Paged parser must never pass a truncated file to the import wizard.
 const ps=h.indexOf('  async parseFile(f, options) {'),pe=h.indexOf('  async checkMarkStatus(',ps);
 vm.runInContext('this.parser={'+h.slice(ps,pe)+'};',ctx);
 const parser=ctx.parser;parser.base=()=>'';parser.token=()=>'';
 ctx.fetch=async(url,options)=>{assert.equal(options.headers['X-Catalog-Import'],'1');return {ok:true,json:async()=>({parse_id:'p',total:5001,headers:['2','1']})}};
 parser._fetch=async url=>({total:5001,rows:Array.from({length:url.includes('offset=0&')?5000:1},()=>({'2':'a','1':'b'}))});
 const parsed=await parser.parseFile({name:'price.csv'},{catalogImport:true});assert.equal(parsed.length,5001);assert.deepEqual(Array.from(parsed.headers),['2','1']);
 const matrix=await parser.parseFile({name:'price.csv'},{catalogImport:true,table:true});assert.equal(matrix.length,5001);assert.deepEqual(Array.from(matrix[0]),['a','b']);assert.deepEqual(Array.from(matrix.headers),['2','1']);
 parser._fetch=async()=>({total:5001,rows:[{}]});
 await assert.rejects(()=>parser.parseFile({name:'price.csv'},{catalogImport:true}),/Неполный разбор/);
 console.log('OK: exact staged SQL sync, unified SQL parsing/mapping, fail-closed Ozon and stale download guard');
})().catch(e=>{console.error(e);process.exitCode=1});
