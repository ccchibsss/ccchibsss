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
 await d.delete();console.log('OK: paged key index arbitrary order, page splits, conflict propagation, namespace isolation, atomic failure, missing-key fail-closed and legacy compatibility');
})().catch(e=>{console.error(e);process.exitCode=1});
