const fs=require('fs'),vm=require('vm'),assert=require('assert'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const a=h.indexOf('        if(isPriceFile){',h.indexOf('const Import = {')),b=h.indexOf('}else await runPipeline',a);assert(a>0&&b>a);
let saves=0;const ctx={S:{rows:[{article:'A'}]},isPriceFile:true,prog:()=>{},persistEconPending:()=>{},bumpVersion:()=>{},applyFilter:()=>{},Table:{paint:()=>{}},persistNow:async()=>{saves++;return true;}};
vm.createContext(ctx);vm.runInContext('this.first=async()=>{'+h.slice(a,b)+'}};',ctx);
(async()=>{
 await ctx.first();assert.equal(saves,1);assert(ctx.S._econPending);
 ctx.persistNow=async()=>false;await assert.rejects(()=>ctx.first(),/не сохранён/);
 const sqlImport=h.slice(h.indexOf('  importFile() {',h.indexOf('const PyEngine')),h.indexOf('async _syncCatalog('));
 assert(sqlImport.includes('if(isPriceFile){'));
 assert(sqlImport.includes("if(!await persistNow())throw new Error('Импорт не сохранён в SQLite')"));
 assert(!sqlImport.includes('catch (e) { try { Table.paint(); }'));
 assert(h.includes('if (!isPriceFile && touched.length)'));
 assert(h.includes('if (!isPriceFile && S.settings.autoOeAnomalyOnImport !== false)'));
 const x=h.indexOf('  async enrichAsync(list, prog, mode) {'),y=h.indexOf('  _now()',x);
 const hc={PyEngine:{processingMode:()=> 'sql',enrichHvcRows:async(rows)=>{assert.equal(rows.length,1);return 1;}},S:{rows:[{}]}};vm.createContext(hc);
 vm.runInContext('this.HVC={'+h.slice(x,y)+'};',hc);
 assert.equal(await hc.HVC.enrichAsync(hc.S.rows),1); // No browser helpers exist here.
 hc.PyEngine.enrichHvcRows=async()=>{throw Error('offline')};await assert.rejects(()=>hc.HVC.enrichAsync(hc.S.rows),/offline/);
 const loop=h.slice(h.indexOf('      for (let idx = start;',h.indexOf('function runPipeline')),h.indexOf("    if (sqlEnrichment && tnvedServerRows.length)"));
 assert(!loop.includes('await PyEngine.enrichRules([p]'));
 console.log('OK: first price only persists, SQL HVC has no browser fallback and rules are batched');
})().catch(e=>{console.error(e);process.exitCode=1});
