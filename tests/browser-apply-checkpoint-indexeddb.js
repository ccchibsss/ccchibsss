// Shipped Dexie + fake-indexeddb; no mock of transaction/rollback semantics.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),fidb=require('fake-indexeddb');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');let seq=0,cancel=false,confirm=true;
const c={...fidb,console,setTimeout,clearTimeout,queueMicrotask,AbortController,structuredClone,performance,CustomEvent:class{constructor(type){this.type=type}},location:{protocol:'http:'},navigator:{},S:{_volatileStorage:false},uid:()=>String(++seq),persistNow:async()=>true,UCCancel:{check(){if(cancel)throw Error('cancelled')}},askConfirm:async()=>confirm};c.window=c;c.self=c;vm.createContext(c);
vm.runInContext([...h.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1],c);
const a=h.indexOf('const BrowserApplyCheckpoint = {'),b=h.indexOf('const BrowserImportSources = {',a);vm.runInContext(h.slice(a,b)+';this.C=BrowserApplyCheckpoint;',c);
vm.runInContext("this.db=new Dexie('checkpoint-test');db.version(6).stores({products:'++id',products_stage:'++id',meta:'key',cats:'++id',rules:'++id',excs:'++id',imports:'++id',hvcOe:'++id,&oeNorm',hvcParts:'++id,&key',hvcCross:'++id,&key',hvcPrices:'++id,&key'});",c);
const schemaStart=h.indexOf('db.version(7).stores('),schemaEnd=h.indexOf('db.version(7).upgrade(() => {});',schemaStart)+'db.version(7).upgrade(() => {});'.length;vm.runInContext(h.slice(schemaStart,schemaEnd),c);
c.StorageCtl={assertCatalogFresh:()=>c.C.assertWriter()};const C=c.C,db=c.db;const plain=x=>JSON.parse(JSON.stringify(x));
async function readAll(){const out={};for(const n of C.TABLES)out[n]=plain(await db.table(n).toArray());return out;}
(async()=>{
 await db.open();
 await db.products.bulkAdd(Array.from({length:2503},(_,i)=>({id:i+1,article:String(i).padStart(8,'0'),custom:{value:'text'},oe_numbers:'A / B'})));
 await db.meta.bulkAdd([{key:'catalog',value:{revision:'initial'}},{key:'settings',value:{x:true}}]);
 await db.hvcOe.add({id:70,oeNorm:'OE1',article:'00001'});await db.hvcParts.add({id:4,key:'A|B',name:'part'});
 await db.hvcCross.add({id:9,key:'A|OE1'});await db.hvcPrices.add({id:12,key:'A|B',cost:123});
 await db.products_stage.add({id:3,article:'prior-draft'});await db.imports.add({id:10,name:'old'});await db.cats.add({id:5,name:'category'});
 const before=await readAll();
 let peak=0;const bulk=db.applyUndo.bulkAdd.bind(db.applyUndo);db.applyUndo.bulkAdd=async rows=>{peak=Math.max(peak,rows.length);return bulk(rows)};
 let owner=await C.begin();assert(peak<=1000);assert(await db.meta.get(C.KEY));assert.equal(C.owner,owner);
 await assert.rejects(()=>C.begin(),/уже используется/);
 // Guard rejects a second tab's writer and never changes its catalog token.
 C.owner=null;await assert.rejects(()=>C.assertWriter(),/другой вкладке/);C.owner=owner;await C.assertWriter();
 await db.products_stage.clear();await db.products_stage.add({article:'PARTIAL-DRAFT'});await db.products.clear();await db.products.add({id:9999,article:'PARTIAL'});await db.hvcOe.clear();await db.imports.add({name:'partial'});await db.meta.put({key:'settings',value:{bad:true}});
 // A failure during restore aborts the WHOLE restore and preserves checkpoint.
 const damaged=await readAll(),failRestore=()=>{throw Error('restore failure')};db.hvcCross.hook('creating',failRestore);
 await assert.rejects(()=>C.restore(owner),/restore failure/);assert.deepEqual(await readAll(),damaged);assert(await db.meta.get(C.KEY));assert(await db.applyUndo.count());db.hvcCross.hook('creating').unsubscribe(failRestore);
 await C.restore(owner);assert.deepEqual(await readAll(),before);assert.equal(await db.applyUndo.count(),0);assert.equal(C.owner,null);
 // Successful publication retains new rows and removes backup and marker.
 owner=await C.begin();await db.products.add({article:'COMMITTED'});await C.commit(owner);assert.equal(await db.products.count(),2504);assert(!await db.meta.get(C.KEY));assert.equal(await db.applyUndo.count(),0);
 // Cancellation or quota failure while taking checkpoint never publishes it.
 cancel=true;await assert.rejects(()=>C.begin(),/cancelled/);cancel=false;assert(!await db.meta.get(C.KEY));assert.equal(await db.applyUndo.count(),0);assert.equal(C.owner,null);
 let writes=0;db.applyUndo.bulkAdd=async rows=>{if(++writes===2)throw Error('quota');return bulk(rows)};await assert.rejects(()=>C.begin(),/quota/);db.applyUndo.bulkAdd=bulk;assert(!await db.meta.get(C.KEY));assert.equal(await db.applyUndo.count(),0);
 // Marker removal and backup cleanup also commit atomically.
 owner=await C.begin();const clear=db.applyUndo.clear.bind(db.applyUndo);db.applyUndo.clear=async()=>{throw Error('commit failure')};
 await assert.rejects(()=>C.commit(owner),/commit failure/);assert(await db.meta.get(C.KEY));assert(await db.applyUndo.count());db.applyUndo.clear=clear;await C.restore(owner);
 // Browser restart: restore requires confirmation and must not run if the
 // operation lock is still held in a live tab.
 const committed=await readAll();owner=await C.begin();await db.products.clear();C.owner=null;db.close();await db.open();
 c.navigator.locks={request:async(name,opts,fn)=>fn(null)};await assert.rejects(()=>C.recover(),/другой вкладке/);assert.equal(await db.products.count(),0);
 c.navigator.locks={request:async(name,opts,fn)=>fn({name})};confirm=false;await assert.rejects(()=>C.recover(),/требуется восстановление/);assert(await db.meta.get(C.KEY));
 confirm=true;await C.recover();assert.deepEqual(await readAll(),committed);assert(!await db.meta.get(C.KEY));
 // Execute the actual Import.apply orchestration, injecting an exception
 // immediately after checkpoint creation. Ensure catch restores BEFORE reload
 // and never clears the retry input or allows pagehide to persist dirty RAM.
 const applyStart=h.indexOf('  apply() {',h.indexOf('const Import = {')),applyEnd=h.indexOf('  _relatedRows(',applyStart);
 let reloads=0;c.location.reload=()=>reloads++;c.PyEngine={processingMode:()=> 'browser'};
 c.BrowserImportSources={exclusive:fn=>fn(),active:new Set()};c.Toast={warn(){},err(){}};
 c.withProgress=async(name,msg,fn)=>fn(()=>{});c.storageErrorText=String;
 let queuedFinished=false;const restoreMethod=C.restore;
 C.restore=async owner=>{assert(queuedFinished,'must drain already queued saves before restore');return restoreMethod.call(C,owner)};
 c.injectApplyFailure=()=>{c._persistQueue=new Promise(resolve=>setTimeout(async()=>{await db.products.add({article:'QUEUED-PARTIAL'});queuedFinished=true;resolve()},5));throw Error('injected apply failure')};
 vm.runInContext('this.Import={normalize(){},applyPriceIsCost(){return injectApplyFailure()},'+h.slice(applyStart,applyEnd)+'};',c);
 c.S.pending={artCol:0,body:[['RETRY']]};c.S._bootReady=true;
 const preApply=await readAll();await assert.rejects(()=>c.Import.apply(),/injected apply failure/);
 assert.equal(reloads,1);assert.equal(c.S._bootReady,false);assert.equal(c.S.pending.body.length,1);
 assert.deepEqual(await readAll(),preApply);assert(!await db.meta.get(C.KEY));assert.equal(C.owner,null);C.restore=restoreMethod;
 // Tampered/incomplete checkpoints fail closed without clearing live data.
 owner=await C.begin();await db.applyUndo.where('table').equals('products').first().then(r=>db.applyUndo.delete(r.id));
 const partial=await readAll();await assert.rejects(()=>C.restore(owner),/Неполная/);assert.deepEqual(await readAll(),partial);assert(await db.meta.get(C.KEY));
 await db.delete();
 // Source, SQL isolation and publication/error wiring remain explicit.
 const apply=h.slice(h.indexOf('  apply() {',h.indexOf('const Import = {')),h.indexOf('  _relatedRows(',h.indexOf('const Import = {')));
 assert(apply.includes("if(PyEngine.processingMode()==='browser')checkpoint=await BrowserApplyCheckpoint.begin()"));
 assert(apply.indexOf('await BrowserApplyCheckpoint.commit(checkpoint)')<apply.indexOf('try { body.length = 0; }'));
 assert(apply.includes('S._bootReady=false'));assert(apply.includes('await BrowserApplyCheckpoint.restore(checkpoint)'));
 console.log('OK: browser Apply undo checkpoint: bounded backup, atomic restore+failure rollback, quota/cancel, cross-tab writer guard, crash/reopen confirmation, commit and SQL isolation');
})().catch(e=>{console.error(e);process.exitCode=1});
