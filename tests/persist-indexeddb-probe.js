// Optional integration probe: npm install fake-indexeddb in a scratch prefix;
// run with NODE_PATH pointing at that prefix/node_modules. No browser/UI emulation.
const fs=require('fs'),vm=require('vm'),assert=require('assert');const fidb=require('fake-indexeddb');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');const lib=[...h.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1];
const c={...fidb,location:{protocol:'http:'},console,setTimeout,clearTimeout,queueMicrotask,AbortController,structuredClone,performance,CustomEvent:class{constructor(type){this.type=type}},navigator:{},S:{rows:[],settings:{},custom:[],tariffs:[],cats:[],rules:[],excs:[],_catalogToken:'нет_метаданных'},lsGet:()=>null,lsSet:()=>true,nowISO:()=>new Date().toISOString(),num:x=>Number(x)||0,fmt:String,catFp:rows=>({fp:'probe',count:rows.length}),PyEngine:{processingMode:()=> 'browser'},warnIfLowStorage:()=>{},HVC:{save:async()=>{}},CONST:{CHUNKED_WRITE_ROWS:20000,DEXIE_ATOMIC_ROWS:20000},Toast:{err:console.error}};c.window=c;c.self=c;
vm.createContext(c);vm.runInContext(lib,c);
vm.runInContext("this.db=new Dexie('probe');db.version(1).stores({products:'++id',products_stage:'++id',meta:'key',cats:'++id',rules:'++id',excs:'++id'});",c);
const a=h.indexOf('const StorageCtl = {'),b=h.indexOf('\n};',a)+3;vm.runInContext(h.slice(a,b)+';this.StorageCtl=StorageCtl;StorageCtl.refresh=()=>{};',c);
vm.runInContext(h.slice(h.indexOf('function storageErrorText('),h.indexOf('async function persistImportOrThrow(')),c);
const x=h.indexOf('async function _persistNowImpl('),y=h.indexOf('\n}\n',x)+2;vm.runInContext(h.slice(x,y),c);
(async()=>{
 await c.db.open();
 for(const mode of ['economy','staged'])for(const n of [1,21001,...(process.env.LARGE_PRICE_PROBE?[124236]:[])]){
  c.StorageCtl._mode=mode;
  c.S.rows=Array.from({length:n},(_,i)=>({article:String(i),custom:{code:'00042'},price:10}));
  assert.equal(await c._persistNowImpl(),true,c.S._cacheWriteError);
  assert.equal(await c.db.products.count(),n);
  c.db.close();await c.db.open();
  assert.equal((await c.db.products.orderBy('id').first()).custom.code,'00042');
  console.log('PASS embedded Dexie + fake-indexeddb:',mode,n,'rows; reopened and read back');
 }
 c.db.close();
})().catch(e=>{console.error(e);process.exitCode=1});
