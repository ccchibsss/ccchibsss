const fs=require('fs'),vm=require('vm'),assert=require('assert');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');
const c={console:{error:()=>{},warn:()=>{},info:()=>{}},setTimeout,clearTimeout,AbortController,
 S:{_bootReady:true,rows:[{article:'KEEP'}],pending:{body:[['KEEP']]},settings:{},custom:[],tariffs:[],cats:[],rules:[],excs:[]},
 nowISO:()=> 'test-time',num:Number,fmt:String,CONST:{CHUNKED_WRITE_ROWS:20000},performance,
 warnIfLowStorage:()=>{},HVC:{save:async()=>{}},Toast:{err:()=>{}},
 db:{transaction:async()=>{},open:async()=>{}}};
vm.createContext(c);
const start=h.indexOf('function storageErrorText('),end=h.indexOf('async function storageFreeInfo(',start);
vm.runInContext(h.slice(start,end),c);
(async()=>{
 for(const error of [
  {message:{error:{message:'disk full'}}},
  {type:'error',target:{error:{name:'QuotaExceededError',message:'disk full'}}},
  {name:'BulkError',failuresByPos:{7:{name:'DataCloneError',message:'disk full'}}},
  {inner:{cause:{message:'disk full'}}}
 ]){assert(c.storageErrorText(error).includes('disk full'));assert(!c.storageErrorText(error).includes('[object Object]'));}
 const cyclic={};cyclic.cause=cyclic;assert(c.storageErrorText(cyclic).includes('без сообщения'));
 assert(c.storageErrorText({code:507}).includes('507'));
 const throwing={get message(){throw Error('getter')}};assert.doesNotThrow(()=>c.storageErrorText(throwing));
 c.S._bootError={inner:{message:'database boot failed'}};
 await assert.rejects(()=>c.persistImportOrThrow('Прайс не сохранён'),/database boot failed/);
 delete c.S._bootError;
 const apply=h.slice(h.indexOf("return BrowserImportSources.exclusive(()=>withProgress('Применение импорта'"),h.indexOf('      const movedToCost',h.indexOf("return BrowserImportSources.exclusive(()=>withProgress('Применение импорта'")));
 assert(apply.includes('if(S._bootReady!==true||S._bootError)'));
 c.persistNow=async()=>{throw {message:{reason:'actual disk failure'}}};
 await assert.rejects(()=>c.persistImportOrThrow('Прайс не сохранён'),/actual disk failure/);
 assert.equal(c.S.pending.body.length,1);assert.equal(c.S.rows.length,1);
 // Actual IndexedDB persistence catch must preserve nested event errors.
 c.PyEngine={processingMode:()=> 'browser'};
 c.StorageCtl={mode:()=> 'economy',saveDiffAtomic:async()=>{throw {target:{error:{name:'QuotaExceededError',message:'full volume'}}}},isQuotaError:()=>true,refresh:()=>{}};
 vm.runInContext('Object.assign(StorageCtl,{'+h.slice(h.indexOf('  recordBytes('),h.indexOf('  *productBatches('))+'});',c);
 const a=h.indexOf('async function _persistNowImpl('),b=h.indexOf('\n}\n',a)+2;
 vm.runInContext(h.slice(a,b),c);
 assert.equal(await c._persistNowImpl(),false);
 assert(c.S._cacheWriteError.includes('QuotaExceededError'));assert(c.S._cacheWriteError.includes('full volume'));
 assert.equal(c.S._lastPersistFailure.engine,'browser');
 assert.equal(c.S.pending.body.length,1);
 // Actual API wrapper: structured JSON errors must not become [object Object].
 const x=h.indexOf('  async _fetch(path, opts) {'),y=h.indexOf('  async health()',x);
 vm.runInContext('this.client={'+h.slice(x,y)+'};',c);
 c.client.base=()=>'';c.client.token=()=>'';
 c.fetch=async()=>({ok:false,status:507,json:async()=>({error:{message:'server disk full',code:507}})});
 await assert.rejects(()=>c.client._fetch('/app/catalog',{}),/HTTP 507 \/app\/catalog: server disk full/);
 console.log('OK: nested Dexie/DOM/API errors retained, failed import input remains intact');
})().catch(e=>{console.error(e);process.exitCode=1});
