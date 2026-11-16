// Shipped StorageCtl/Dexie: bounded primary-key merge before catalog writes.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),fidb=require('fake-indexeddb');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');let cancelAt=Infinity,checks=0;
const c={...fidb,console,setTimeout,clearTimeout,queueMicrotask,AbortController,structuredClone,performance,CustomEvent:class{},location:{protocol:'http:'},navigator:{},S:{rows:[],custom:[],settings:{},tariffs:[]},lsGet:()=>null,nowISO:()=>new Date().toISOString(),num:x=>Number(x)||0,fmt:String,catFp:rows=>({fp:'test',count:rows.length}),UCCancel:{check(){if(++checks===cancelAt)throw Error('cancelled')}}};c.self=c;c.window=c;vm.createContext(c);
vm.runInContext([...h.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1],c);
vm.runInContext("this.db=new Dexie('product-key-test');db.version(1).stores({products:'++id',meta:'key'});",c);
const a=h.indexOf('const StorageCtl = {'),b=h.indexOf('\n};',a)+3;vm.runInContext(h.slice(a,b)+';this.C=StorageCtl;',c);
const C=c.C,db=c.db,plain=x=>JSON.parse(JSON.stringify(x));let stale=false;
C.assertCatalogFresh=async()=>{if(stale)throw Error('stale catalog');return null};
const withId=row=>row;
const args=fullWrite=>({rowCount:c.S.rows.length,chunk:257,withId,slimChunk:(a,b)=>c.S.rows.slice(a,b),fullWrite});
async function reset(){await db.products.clear();await db.meta.clear();await db.products.bulkAdd(Array.from({length:3503},(_,i)=>({id:i+1,article:'OLD'+i,nested:{keep:'00042'}})));}
const read=async()=>plain(await db.products.toArray());
(async()=>{
 await db.open();
 let maxKeys=0,calls=0;const proto=db.Collection.prototype,original=proto.primaryKeys;
 proto.primaryKeys=function(...args){assert(this._ctx.limit<=1000,'unbounded primaryKeys read');calls++;return original.apply(this,args).then(keys=>{maxKeys=Math.max(maxKeys,keys.length);return keys})};
 for(const method of ['saveDiffAtomic','saveChunked']){
  await reset();
  // Reversed/sparse IDs cross batch boundaries, retain endpoints and introduce
  // new IDs both below and above the previous maximum. Source order is intact.
  c.S.rows=[{id:9001,article:'NEW'},...Array.from({length:1503},(_,i)=>({id:2503-i,article:'KEEP'+i,nested:{keep:'00042'}})),{id:0,article:'ZERO'},{id:3503,article:'LAST'}];
  const order=c.S.rows.map(r=>r.id),expected=plain(c.S.rows).sort((a,b)=>a.id-b.id);
  await C[method](args(true));assert.deepEqual(await read(),expected);assert.deepEqual(c.S.rows.map(r=>r.id),order);assert.equal(c.S._cacheLastWrite.deleted,1999);assert(!await db.meta.get('incomplete'));
  // Duplicate and invalid IDs are rejected before deleting any product or
  // publishing a chunked incomplete marker.
  for(const id of [NaN,{},true,undefined]){
   const before=await read();c.S.rows=[{id:1},{id}];await assert.rejects(()=>C[method](args(true)),/ID/);assert.deepEqual(await read(),before);assert(!await db.meta.get('incomplete'));
  }
  const before=await read();c.S.rows=[{id:7},{id:7}];await assert.rejects(()=>C[method](args(true)),/повторяющиеся/);assert.deepEqual(await read(),before);assert(!await db.meta.get('incomplete'));
  c.S.rows=[];await C[method](args(true));assert.equal(await db.products.count(),0);
 }
 assert(maxKeys<=1000);assert(calls>=10);
 // Native IDB ordering, not JavaScript string sorting or Set identity.
 const cmp=(a,b)=>c.Dexie.cmp(a,b);const keys=[['A',1],new Date(1234),'2',12,2,new Uint8Array([1,2])];
 assert.deepEqual(C.productIds(keys.map(id=>({id})),withId),keys.slice().sort(cmp));
 for(const pair of [[new Date(2),new Date(2)],[['A',1],['A',1]],[new Uint8Array([1]),new Uint8Array([1])]])assert.throws(()=>C.productIds(pair.map(id=>({id})),withId),/повторяющиеся/);
 // Whole atomic save rolls back deletions if its later write fails.
 await reset();const originalRows=await read();c.S.rows=[{id:1,article:'changed'}];const fail=()=>{throw Error('write failure')};db.products.hook('updating',fail);
 await assert.rejects(()=>C.saveDiffAtomic(args(true)),/write failure/);assert.deepEqual(await read(),originalRows);db.products.hook('updating').unsubscribe(fail);
 // Atomic cancellation rolls back all deletions; chunked cancellation retains
 // its incomplete marker and already committed deletion batches (Apply undo
 // is responsible for whole-operation recovery).
 for(const method of ['saveDiffAtomic','saveChunked']){
  await reset();c.S.rows=[{id:1,article:'keep'}];checks=0;cancelAt=2;
  await assert.rejects(()=>C[method](args(true)),/cancelled/);cancelAt=Infinity;
  if(method==='saveChunked'){assert(await db.meta.get('incomplete'));assert.deepEqual(await read(),originalRows.filter(r=>r.id===1||r.id>1000));}
  else{assert.deepEqual(await read(),originalRows);assert(!await db.meta.get('incomplete'));}
 }
 // Freshness is checked inside the scan/deletion transaction.
 await reset();stale=true;await assert.rejects(()=>C.reconcileProductKeys([]),/stale/);assert.deepEqual(await read(),originalRows);stale=false;
 // Freshness is rechecked for EVERY chunk, not just before the first one.
 await reset();const guard=C.assertCatalogFresh;let guards=0;
 C.assertCatalogFresh=async()=>{if(++guards===2)throw Error('new catalog revision')};
 await assert.rejects(()=>C.reconcileProductKeys([1]),/new catalog revision/);
 assert.deepEqual(await read(),originalRows.filter(r=>r.id===1||r.id>1000));C.assertCatalogFresh=guard;
 // A key-only scan never materializes complete stored product objects.
 await reset();let payloadReads=0;const observe=row=>{payloadReads++;return row};db.products.hook('reading',observe);
 await C.reconcileProductKeys(C.productIds(originalRows,withId));assert.equal(payloadReads,0);db.products.hook('reading').unsubscribe(observe);
 // A partial update must not delete unrelated products.
 c.S.rows=await db.products.toArray();c.S.rows[0].article='partial';await C.saveDiffAtomic({...args(false),changedList:[c.S.rows[0]]});assert.equal(await db.products.count(),3503);assert.equal((await db.products.get(1)).article,'partial');
 proto.primaryKeys=original;await db.delete();console.log('OK: bounded product keys <=1000, exact sparse/reordered key merge, invalid/duplicate ID preflight, atomic deletion/write/cancel rollback, freshness, partial updates');
})().catch(e=>{console.error(e);process.exitCode=1});
