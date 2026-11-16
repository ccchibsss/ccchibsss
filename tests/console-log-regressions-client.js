// Regression cases from the reported browser console, without hiding errors.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
(async()=>{
 const ctx={console,Set,Map,Blob,TextEncoder,Date,JSON,XLSX_CELL_MAX:32767,fmt:String,
 Prog:{step(){}},UCCancel:{check(){}},safeCsvText:String,exportCatalogCellValue:(c,p)=>c.src?c.src(p):p[c.k],
 $:id=>({value:id==='#expDelim'?';':'cp1251'}),encodeCp1251Strict:()=>{throw Error('must use UTF8')},
 PyEngine:{processingMode:()=> 'browser'},S:{settings:{}},storageErrorText:String};vm.createContext(ctx);
 const overflow=h.indexOf('  async xlsxTextOverflow('),overflowEnd=h.indexOf('  async streamXlsx(',overflow);
 const csv=h.indexOf('  async csvAsync('),csvEnd=h.indexOf('\n  /* XLSX:',csv);
 vm.runInContext('this.Exp={_yield:async()=>{},'+h.slice(overflow,overflowEnd)+h.slice(csv,csvEnd)+'};',ctx);
 const long='OE😀/'.repeat(10000),cat=[{k:'oe',n:'OE',rejectLongText:true,txt:1}],rows=[{oe:'short'},{oe:long}];
 assert((await ctx.Exp.xlsxTextOverflow(cat,rows)).includes('строка 3'));assert.equal(rows[1].oe,long);
 const blob=await ctx.Exp.csvAsync(cat,rows,null,undefined,undefined,{utf8:true});assert((await blob.text()).includes(long));
 assert.equal(await ctx.Exp.xlsxTextOverflow(cat,[{oe:'x'.repeat(32767)}]),'');
 // Exercise the real export orchestration: overflow => confirmation => UTF8
 // CSV, never ZIP construction; declining does not publish any file.
 const run=h.indexOf('  async _runImpl(forceRows)'),runEnd=h.indexOf('  /* Потоковая сборка ОДНОЙ книги XLSX',run);
 vm.runInContext('Object.assign(Exp,{'+h.slice(run,runEnd)+'});',ctx);
 let accepted=true,published=[],zipCalls=0;
 ctx.exportCatalog=()=>cat;ctx.exportColumnExcluded=()=>false;ctx.filterExportCategories=x=>x;ctx.exportCategoryNames=()=>new Set();ctx.ChzTnved={isFiltered:()=>false};
 ctx.$=id=>({value:id==='#expFmt'?'xlsx':id==='#expDelim'?';':'cp1251'});
 ctx.Toast={warn(){},ok(){},info(){}};ctx.withProgress=async(a,b,fn)=>fn(()=>{});ctx.mpTag=()=> 'ALL';ctx.askConfirm=async()=>accepted;
 Object.assign(ctx.Exp,{pick:{oe:true},activeMps:()=>new Set(),snap:async()=>{},_releaseAfterExport:async()=>{},download:(b,name)=>published.push({b,name}),streamXlsx:async()=>{zipCalls++;return new Blob(['xlsx'])}});
 await ctx.Exp._runImpl(rows);assert.equal(zipCalls,0);assert(published[0].name.endsWith('.csv'));assert((await published[0].b.text()).includes(long));
 published=[];accepted=false;await ctx.Exp._runImpl(rows);assert.equal(published.length,0);assert.equal(zipCalls,0);
 accepted=true;await ctx.Exp._runImpl([{oe:'short'}]);assert.equal(zipCalls,1);assert(published[0].name.endsWith('.xlsx'));
 // No implicit SQL localhost probe in browser mode; explicit SQL still probes.
 const status=h.indexOf('  async refreshStatus() {',h.indexOf('const PyEngine = {')),statusEnd=h.indexOf('  async askToken()',status);
 let requests=0,mode='browser';const el={style:{}};ctx.$=()=>el;
 vm.runInContext('this.engine={'+h.slice(status,statusEnd)+'};',ctx);
 Object.assign(ctx.engine,{processingMode:()=>mode,loadSecrets(){},health:async()=>{requests++;return false},_fileModeWatch(){}});
 await ctx.engine.refreshStatus();assert.equal(requests,0);assert(el.textContent.includes('браузерный'));
 mode='sql';await ctx.engine.refreshStatus();assert.equal(requests,1);
 // Memory pressure must not truncate the retry input during active Apply.
 const mem=h.indexOf('const MemGuard = {'),memEnd=h.indexOf('\n};',mem)+3;
 ctx.Toast={warn(){}};ctx.FWorker={release(){}};ctx.clearTariffLookupCache=()=>{};ctx.BrowserImportSources={active:new Set(['source'])};ctx.S.pending={body:[['retry']]};
 vm.runInContext(h.slice(mem,memEnd)+';this.M=MemGuard;',ctx);ctx.M.share=()=>0.4;
 ctx.M.relief(2,'test');assert.equal(ctx.S.pending.body.length,1);
 ctx.BrowserImportSources.active.clear();ctx.S._pipeActive=true;ctx.M._lastActionAt=0;ctx.M.relief(2,'test');assert.equal(ctx.S.pending.body.length,1);
 ctx.S._pipeActive=false;ctx.M._lastActionAt=0;ctx.M.relief(2,'test');assert.equal(ctx.S.pending.body.length,0);
 assert(!h.includes('sourceMappingURL=dexie.js.map'));assert(!h.includes('sourceMappingURL=chart.umd.js.map'));assert(h.includes('rel="icon" href="data:'));
 console.log('OK: reported console regressions: oversized OE preflight, complete Unicode CSV, browser-mode no SQL health probe, favicon/source maps');
})().catch(e=>{console.error(e);process.exitCode=1});
