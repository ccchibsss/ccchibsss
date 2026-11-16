// Paged source-key index: arbitrary order, splits, cross-batch conflicts, atomicity.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),fidb=require('fake-indexeddb');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');const c={...fidb,console,setTimeout,clearTimeout,queueMicrotask,AbortController,structuredClone,performance,CustomEvent:class{},location:{protocol:'http:'},navigator:{}};c.window=c;c.self=c;vm.createContext(c);
vm.runInContext([...h.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1],c);
const a=h.indexOf('const BrowserImportSources = {'),b=h.indexOf('const Import = {',a);vm.runInContext(h.slice(a,b)+';this.B=BrowserImportSources;',c);
const B=c.B,plain=v=>JSON.parse(JSON.stringify(v));
(async()=>{
 const d=B.database(),expected=new Map();let high;
 let seed=197;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed};
 const input=Array.from({length:12000},(_,i)=>({key:'K'+String(random()%3503).padStart(6,'0'),brand:i%5?'B'+(random()%3):'',signature:'S'+(random()%4)}));
 input.push({key:'000FIRST',brand:'B',signature:''},{key:'ЯLAST',brand:'B',signature:''});
 for(let off=0;off<input.length;off+=271){
  const batch=input.slice(off,off+271);
  for(const item of batch){const p=expected.get(item.key);if(!p)expected.set(item.key,{...item,conflict:false});else{if(p.brand&&item.brand&&p.brand!==item.brand)p.conflict=true;if(p.signature!==item.signature)p.conflict=true;if(!p.brand&&item.brand)p.brand=item.brand;}}
  high=await B.writeKeyPages('random',batch,high);
  if(off%1897===0){const found=await B.lookupKeyPages('random',[...expected.keys(),'NOT-THERE']);assert.deepEqual(plain([...found].sort()),plain([...expected].sort()));}
 }
 const actual=await B.lookupKeyPages('random',[...expected.keys(),'NONE']);assert.deepEqual(plain([...actual].sort()),plain([...expected].sort()));
 const pages=await d.keyPages.where('run').equals('random').toArray();assert(pages.length<100);assert(pages.every(p=>p.records.length<=1000));
 // A locally conflicting group must remain conflicting when merged into an
 // existing page, even when its first signature equals the prior signature.
 high=await B.writeKeyPages('random',[{key:'LOCAL',brand:'',signature:'S0'}],high);
 high=await B.writeKeyPages('random',[{key:'LOCAL',brand:'B',signature:'S0'},{key:'LOCAL',brand:'B',signature:'S1'}],high);
 assert((await B.lookupKeyPages('random',['LOCAL'])).get('LOCAL').conflict);
 // Same key in a different namespace has independent evidence.
 await B.writeKeyPages('other',[{key:'LOCAL',brand:'B',signature:'S0'}]);assert(!(await B.lookupKeyPages('other',['LOCAL'])).get('LOCAL').conflict);
 // Deleting/replacing a leaf and then failing must roll back as one unit.
 const before=plain(await d.keyPages.where('run').equals('random').toArray()),fail=()=>{throw Error('page write failure')};d.keyPages.hook('creating',fail);
 await assert.rejects(()=>B.writeKeyPages('random',[{key:'LOCAL',brand:'OTHER',signature:'DIFFERENT'}],high),/page write failure/);d.keyPages.hook('creating').unsubscribe(fail);
 assert.deepEqual(plain(await d.keyPages.where('run').equals('random').toArray()),before);
 await d.runs.add({id:'random',source:'fixture',complete:true,storage:'key-pages-v1'});
 const descriptions=[...expected.values()];const conflicts=await B.conflicts('random',descriptions,r=>r);assert.equal(conflicts.size,[...expected.values()].filter(x=>x.conflict).length);
 await assert.rejects(()=>B.conflicts('random',[{key:'ABSENT'}],r=>r),/неполон/);
 const leaf=(await d.keyPages.where('run').equals('random').first());await d.keyPages.delete(['random',leaf.first]);await assert.rejects(()=>B.conflicts('random',[leaf.records[0]],r=>r),/неполон/);
 await B.clearRun('random');await B.clearRun('other');assert.equal(await d.keyPages.count(),0);
 // Old complete row-key indexes remain readable while new ones use pages.
 await d.runs.add({id:'old',source:'legacy',complete:true});await d.keys.add({run:'old',key:'A',conflict:true});assert((await B.conflicts('old',[{key:'A'}],r=>r)).has('A'));await B.clearRun('old');
 // Bulk external merge: >256 leaves forces three stable merge passes.
 B.BATCH=37;
 async function* chunks(){for(let off=0;off<input.length;off+=271)yield input.slice(off,off+271);}
 await B.buildKeyPages('bulk',chunks());
 const built=await B.lookupKeyPages('bulk',[...expected.keys(),'NONE']);assert.deepEqual(plain([...built].sort()),plain([...expected].sort()));
 const dense=await d.keyPages.where('run').equals('bulk').toArray();assert.equal(dense.length,Math.ceil(expected.size/B.BATCH));
 assert(dense.every(p=>p.records.length<=B.BATCH));assert.equal(await d.keyPages.where('run').startsWith('bulk:sort:').count(),0);
 assert(B._keyPageCache.size<=256);assert(B._keyCacheBytes<=32*1048576);
 B.invalidateKeyIndex('bulk'); // Simulate restart: on-disk format still readable.
 assert.deepEqual(plain([...(await B.lookupKeyPages('bulk',[...expected.keys()]))].sort()),plain([...expected].sort()));
 // Failure during the output pass must remove partial output and temp runs.
 const failBulk=(key,obj)=>{if(obj.run==='bulk-fail')throw Error('merge failure')};d.keyPages.hook('creating',failBulk);
 await assert.rejects(()=>B.buildKeyPages('bulk-fail',chunks()),/merge failure/);d.keyPages.hook('creating').unsubscribe(failBulk);
 assert.equal(await d.keyPages.where('run').startsWith('bulk-fail').count(),0);
 await assert.rejects(()=>B.buildKeyPages('bulk-cancel',chunks(),undefined,()=>{throw Error('cancel merge')}),/cancel merge/);
 assert.equal(await d.keyPages.where('run').startsWith('bulk-cancel').count(),0);
 // Mutable-page writer invalidates immutable-build directory/cache.
 await B.writeKeyPages('bulk',[{key:'LOCAL',brand:'B',signature:'NEW'}],'ЯLAST');assert(!B._keyDirectories.has('bulk'));
 await B.clearRun('bulk');assert.equal(await d.keyPages.count(),0);assert.equal(B._keyPageCache.size,0);
 await d.delete();console.log('OK: paged key index arbitrary order, page splits, conflict propagation, namespace isolation, atomic failure, missing-key fail-closed and legacy compatibility');
})().catch(e=>{console.error(e);process.exitCode=1});
