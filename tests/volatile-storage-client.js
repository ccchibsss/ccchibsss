// Actual RAM fallback + actual HVC.load: no replacement collection shim.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(__dirname+'/../index.html','utf8');
const c={console,S:{settings:{},_volatileStorage:true,_dbOpenInfo:{name:'TimeoutError',message:'test timeout'}},Toast:{warn(){},err(){}},StorageCtl:{refresh(){}},num:x=>Number(x)||0};
vm.createContext(c);
const a=html.indexOf('function createVolatileDB()'),b=html.indexOf('/* При переполнении',a);
vm.runInContext(html.slice(a,b)+';this.db=createVolatileDB();',c);
vm.runInContext(html.slice(html.indexOf('const _normArticleCache ='),html.indexOf('/* Артикул — всегда текст.')),c);
const ha=html.indexOf('const HVC = {'),hb=html.indexOf('\n};\n/* OzonCat',ha)+3;
vm.runInContext(html.slice(ha,hb)+';this.H=HVC;',c);
let mode='browser';c.PyEngine={processingMode:()=>mode};
vm.runInContext(html.slice(html.indexOf('const BrowserImportIO = {'),html.indexOf('const BrowserApplyCheckpoint = {'))+';this.IO=BrowserImportIO;',c);
const db=c.db,plain=v=>JSON.parse(JSON.stringify(v));
(async()=>{
 assert.equal(await c.H.load(),0);assert(!c.S._hvcLoadError,'empty fallback must not fail on limit');
 for(let i=2003;i>=1;i--){await db.hvcParts.add({id:i,key:'A'+i+'|B',artikul:'A'+i,brand:'B',name:'Name'+i});await db.hvcCross.add({id:i,key:'OE'+i+'|A'+i+'|B',oeNorm:'OE'+i,artKey:'A'+i+'|B'});}
 const query=db.hvcParts.orderBy(':id');assert.equal((await query.limit(2).toArray()).length,2);assert.equal((await query.toArray()).length,2003,'limit must not mutate original collection');
 assert.deepEqual(plain((await db.hvcParts.where(':id').above(998).limit(3).toArray()).map(r=>r.id)),[999,1000,1001]);
 assert.equal(await c.H.load(),2003);assert(!c.S._hvcLoadError);assert.equal(c.H.parts.get('A2003|B').name,'Name2003');assert(c.H.byArt.get('A2003|B').has('OE2003'));
 assert.throws(()=>c.IO.assertStorage(),e=>e.name==='BrowserStorageUnavailable'&&e._ucImportNotStarted&&/test timeout/.test(e.message));
 mode='sql';assert.doesNotThrow(()=>c.IO.assertStorage());mode='browser';c.S._volatileStorage=false;assert.doesNotThrow(()=>c.IO.assertStorage());c.S._volatileStorage=true;
 // Verify production import entry guards run before file parsing/mapping.
 const readStart=html.indexOf('  async read(file, savedSourceId) {'),readEnd=html.indexOf('  guessProfile(',readStart);
 c.BrowserImportSources={exclusive:f=>f(),stage:()=>{throw Error('must not stage')}};c.withProgress=(a,b,f)=>f();c.Prog={step:()=>{throw Error('must not parse')}};
 vm.runInContext('this.I={'+html.slice(readStart,readEnd)+'};',c);
 await assert.rejects(()=>c.I.read({name:'blocked.csv'}),e=>e.name==='BrowserStorageUnavailable');
 const applyStart=html.indexOf('  apply() {\n    BrowserImportIO.assertStorage();'),applyEnd=html.indexOf('  /* v12.9.50 · СВЯЗАННЫЕ',applyStart);
 vm.runInContext('this.Apply={'+html.slice(applyStart,applyEnd)+'};',c);
 assert.throws(()=>c.Apply.apply(),e=>e.name==='BrowserStorageUnavailable');
 // Timeout diagnostics distinguish unresolved open from slow product count.
 const oa=html.indexOf('function idbOpenError('),ob=html.indexOf('let db = new Dexie(',oa);
 c.window={indexedDB:{open(){}}};c.setTimeout=(fn,ms)=>setTimeout(fn,Math.min(ms,2));c.clearTimeout=clearTimeout;
 vm.runInContext(html.slice(oa,ob),c);
 let closes=0;c.mainDb={open:()=>new Promise(()=>{}),close(){closes++},products:{count:()=>0}};
 const openTimeout=await c.checkAppDatabase(2);assert.equal(openTimeout.name,'TimeoutError');assert.equal(openTimeout.phase,'open');assert.equal(openTimeout.attempt,3);assert.equal(closes,3);
 c.mainDb.open=async()=>{};c.mainDb.products.count=()=>new Promise(()=>{});
 const countTimeout=await c.checkAppDatabase(2);assert.equal(countTimeout.phase,'count-products');assert(/Подсчёт товаров/.test(countTimeout.message));
 c.mainDb.products.count=async()=>7;const healthy=await c.checkAppDatabase(2);assert.equal(healthy.ok,true);assert.equal(healthy.count,7);
 console.log('OK: volatile HVC boot, numeric primary-key chunk reads >2000 rows, no false limit error, browser import blocked before parsing/mutation, SQL unaffected');
})().catch(e=>{console.error(e);process.exitCode=1});
