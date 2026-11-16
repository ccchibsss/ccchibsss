// Optional integration probe: npm install fake-indexeddb in a scratch prefix;
// run with NODE_PATH pointing at that prefix/node_modules. No browser/UI emulation.
const fs=require('fs'),vm=require('vm'),assert=require('assert');const fidb=require('fake-indexeddb');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');const lib=[...h.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1];
const c={...fidb,location:{protocol:'http:'},console,setTimeout,clearTimeout,queueMicrotask,AbortController,structuredClone,performance,CustomEvent:class{constructor(type){this.type=type}},navigator:{},S:{rows:[],settings:{},custom:[],tariffs:[],cats:[],rules:[],excs:[],_catalogToken:'нет_метаданных'},lsGet:()=>null,lsSet:()=>true,nowISO:()=>new Date().toISOString(),num:x=>Number(x)||0,fmt:String,catFp:rows=>({fp:'probe',count:rows.length}),PyEngine:{processingMode:()=> 'browser'},warnIfLowStorage:()=>{},HVC:{save:async()=>{}},CONST:{CHUNKED_WRITE_ROWS:20000,DEXIE_ATOMIC_ROWS:20000},Toast:{err:console.error}};c.window=c;c.self=c;
vm.createContext(c);vm.runInContext(lib,c);
vm.runInContext("this.db=new Dexie('probe');db.version(1).stores({products:'++id',products_stage:'++id',meta:'key',cats:'++id',rules:'++id',excs:'++id',hvcOe:'++id,&oeNorm',hvcParts:'++id,&key',hvcCross:'++id,&key',hvcPrices:'++id,&key'});",c);
const a=h.indexOf('const StorageCtl = {'),b=h.indexOf('\n};',a)+3;vm.runInContext(h.slice(a,b)+';this.StorageCtl=StorageCtl;StorageCtl.refresh=()=>{};',c);
vm.runInContext(h.slice(h.indexOf('function storageErrorText('),h.indexOf('async function persistImportOrThrow(')),c);
const x=h.indexOf('async function _persistNowImpl('),y=h.indexOf('\n}\n',x)+2;vm.runInContext(h.slice(x,y),c);
(async()=>{
 await c.db.open();
 // fake-indexeddb clones into Node's realm; real IDB clones into the page.
 vm.runInContext('this.rehome=row=>row==null?row:JSON.parse(JSON.stringify(row));',c);
 c.db.products.hook('reading',c.rehome);
 for(const mode of ['economy','staged'])for(const n of [1,21001,...(process.env.LARGE_PRICE_PROBE?[124236]:[])]){
  c.StorageCtl._mode=mode;
  vm.runInContext('S.rows=Array.from({length:'+n+'},(_,i)=>({article:String(i),custom:{code:"00042"},price:10}));',c);
  assert.equal(await c._persistNowImpl(),true,c.S._cacheWriteError);
  assert.equal(await c.db.products.count(),n);
  c.db.close();await c.db.open();
  assert.equal((await c.db.products.orderBy('id').first()).custom.code,'00042');
  let productWrites=0;const update=()=>{productWrites++},create=()=>{productWrites++},del=()=>{productWrites++};
  c.db.products.hook('updating',update);c.db.products.hook('creating',create);c.db.products.hook('deleting',del);
  let release,started;const start=new Promise(r=>started=r);
  c.HVC.save=async()=>{started();await new Promise(r=>release=r);return true;};
  let finished=false;const verify=c._persistNowImpl(undefined,false,true).then(ok=>{assert(ok);finished=true});
  await start;assert(!finished,'persist must await HVC');assert.equal(productWrites,0,'unchanged baseline must not write products');release();await verify;
  assert.equal(c.S._cacheLastWrite.verified,n);c.HVC.save=async()=>true;
  // A direct nested edit with no dirty notification must force a write.
  c.S.rows[0].custom.code='edited';assert(await c._persistNowImpl(undefined,false,true));assert(productWrites>0);assert.equal((await c.db.products.get(c.S.rows[0].id)).custom.code,'edited');
  c.S.rows[0].custom.code='00042';assert(await c._persistNowImpl(undefined,false,true));
  c.db.products.hook('updating').unsubscribe(update);c.db.products.hook('creating').unsubscribe(create);c.db.products.hook('deleting').unsubscribe(del);

  console.log('PASS embedded Dexie + fake-indexeddb:',mode,n,'rows; reopened and read back');
 }
 // Conservative mismatch/freshness cases must never authorize a skip.
 const source=c.S.rows,token=c.S._catalogToken;
 const oldId=source[1].id;source[1].id=source[0].id;assert.equal(await c.StorageCtl.saveVerifiedMetadata(source,p=>p),false);source[1].id=oldId;
 delete source[1].id;assert.equal(await c.StorageCtl.saveVerifiedMetadata(source,p=>p),false);source[1].id=oldId;
 assert.equal(await c.StorageCtl.saveVerifiedMetadata(source.slice(1),p=>p),false);
 await c.db.products_stage.add({article:'draft'});assert.equal(await c.StorageCtl.saveVerifiedMetadata(source,p=>p),false);await c.db.products_stage.clear();
 c.S._catalogToken='stale';await assert.rejects(()=>c.StorageCtl.saveVerifiedMetadata(source,p=>p),/Каталог изменился/);c.S._catalogToken=token;
 console.log('PASS verified baseline fails closed for duplicate/missing IDs, count changes, draft and stale revision');
 // Execute actual HVC.save against real transactional stores.
 const hs=h.indexOf('  async save() {',h.indexOf('const HVC = {')),he=h.indexOf('  async load() {',hs);
 vm.runInContext('this.realHVC={'+h.slice(hs,he)+'};Object.assign(HVC,{save:realHVC.save,oe:new Map(),parts:new Map(),cross:new Map(),prices:new Map(),ozonApplicability:new Map(),rules:[],exclusions:[],descTemplate:""});S._bootReady=true;for(let i=0;i<4003;i++){HVC.oe.set("OE"+i,{name:"N"+i});HVC.parts.set("A"+i+"|B",{name:"P"+i});}',c);
 for(const name of ['hvcOe','hvcParts','hvcCross','hvcPrices'])c.db[name].hook('reading',c.rehome);
 assert(await c.HVC.save());const stable=(await c.db.hvcOe.where('oeNorm').equals('OE1').first()).id;
 let writes=0;const count=()=>{writes++};for(const name of ['hvcOe','hvcParts','hvcCross','hvcPrices'])for(const event of ['creating','updating','deleting'])c.db[name].hook(event,count);
 assert(await c.HVC.save());assert.equal(writes,0,'unchanged HVC must not be rewritten');
 c.HVC.oe.delete('OE0');c.HVC.oe.get('OE1').name='changed';c.HVC.oe.set('ADDED',{name:'new'});
 assert(await c.HVC.save());assert.equal((await c.db.hvcOe.where('oeNorm').equals('OE1').first()).id,stable);assert.equal(await c.db.hvcOe.where('oeNorm').equals('OE0').count(),0);assert.equal((await c.db.hvcOe.where('oeNorm').equals('OE1').first()).name,'changed');
 const before=await c.db.hvcOe.toArray();c.HVC.oe.set('PROVISIONAL',{name:'not committed'});c.HVC.parts.set('FAIL|B',{name:'fail'});
 const fail=()=>{throw Error('injected registry failure')};c.db.hvcParts.hook('creating',fail);
 assert.equal(await c.HVC.save(),false);assert.deepEqual(await c.db.hvcOe.toArray(),before);assert(c.S._hvcPersistError.includes('injected registry failure'));c.db.hvcParts.hook('creating').unsubscribe(fail);
 console.log('PASS actual HVC bounded save: no unchanged writes, stable IDs, add/update/delete, multi-registry atomic rollback');
 c.db.close();
})().catch(e=>{console.error(e);process.exitCode=1});
