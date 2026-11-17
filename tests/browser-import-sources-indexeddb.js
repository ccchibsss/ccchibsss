// Integration test uses the shipped Dexie build, not a replacement ORM.
// NODE_PATH=.arena/idb-tests/node_modules node tests/browser-import-sources-indexeddb.js
const fs=require('fs'),vm=require('vm'),assert=require('assert'),fidb=require('fake-indexeddb');
const h=fs.readFileSync(__dirname+'/../index.html','utf8'),lib=[...h.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1];
let seq=0,cancel=false,sql=false;
const c={...fidb,console,setTimeout,clearTimeout,queueMicrotask,AbortController,structuredClone,TextDecoder,Blob,performance,CustomEvent:class{constructor(t){this.type=t}},location:{protocol:'http:'},navigator:{},uid:p=>p+'-'+(++seq),PyEngine:{processingMode:()=>sql?'sql':'browser'},UCCancel:{check(){if(cancel)throw Error('cancelled')}},Prog:{msg(){},step(){}}};c.window=c;c.self=c;
vm.createContext(c);vm.runInContext(h.slice(h.indexOf('const BrowserImportIO = {'),h.indexOf('const BrowserApplyCheckpoint = {')),c);
vm.runInContext(lib,c);
const ca=h.indexOf('const CsvStream = {'),cb=h.indexOf('\n/* Воркер XLSX',ca);vm.runInContext(h.slice(ca,cb)+';this.Csv=CsvStream;',c);
const a=h.indexOf('const BrowserImportSources = {'),b=h.indexOf('const Import = {',a);vm.runInContext(h.slice(a,b)+';this.B=BrowserImportSources;',c);
const B=c.B;
const preStart=h.indexOf('      const sourceVariants=',h.indexOf('const Import = {')),preEnd=h.indexOf('      let sourceCollision=',preStart);
c.normArticle=v=>String(v??'').toUpperCase().replace(/[^A-Z0-9]/g,'');
vm.runInContext('this.conflictParity=async(body,sourceId,collisionRun,keyMode,mapped,STD)=>{const _mark=()=>{};const headers=[];const artMap=mapped.find(x=>x.target==="article"),brandMap=mapped.find(x=>x.target==="brand");'+h.slice(preStart,preEnd)+';if(!sourceId||!needsSourceIndex)return [...sourceConflicts];const s=await BrowserImportSources.source(sourceId);const found=new Set();for(let off=0;off<s.total;off+=1000)for(const k of await BrowserImportSources.conflicts(collisionRun,await BrowserImportSources.page(sourceId,off,Math.min(1000,s.total-off)),describeSource))found.add(k);return [...found];};',c);

function file(name,text){const f=new Blob([text]);f.name=name;return f}
const plain=v=>JSON.parse(JSON.stringify(v));
(async()=>{
 // Upgrade an actual v1 source DB in place: no reset or eager full migration.
 vm.runInContext("this.oldSourceDb=new Dexie('UC_BrowserImportSources');oldSourceDb.version(1).stores({sources:'id,status,created',rows:'[source+pos],source',keys:'[run+key],run',runs:'id,source,created'});",c);
 await c.oldSourceDb.open();await c.oldSourceDb.sources.add({id:'v1-source',status:'ready',created:0,total:2,headers:['a']});
 await c.oldSourceDb.rows.bulkAdd([{source:'v1-source',pos:0,cells:['00001']},{source:'v1-source',pos:1,cells:['00002']}]);c.oldSourceDb.close();
 assert.deepEqual(plain(await B.page('v1-source',0,2)),[['00001'],['00002']]);assert.equal(B.database().verno,4);await B.remove('v1-source');

 // Local guard, cross-tab Web Lock refusal, exception cleanup; never replay
 // the callback outside the lock after an operation failure.
 let unlock,entered=0;
 const held=B.exclusive(()=>new Promise(r=>unlock=r));
 await assert.rejects(()=>B.exclusive(async()=>{}),/Идёт импорт/);unlock();await held;assert(!B.busy);
 c.navigator.locks={request:async(name,opts,fn)=>fn(null)};
 await assert.rejects(()=>B.exclusive(async()=>entered++),/другой вкладке/);assert.equal(entered,0);assert(!B.busy);
 c.navigator.locks={request:async(name,opts,fn)=>fn({name})};
 await assert.rejects(()=>B.exclusive(async()=>{entered++;throw Error('one shot')}),/one shot/);assert.equal(entered,1);assert(!B.busy);
 delete c.navigator.locks;
 const n=Number(process.env.SOURCE_ROWS||12000);
 let text='Артикул;Бренд;OE\n';for(let i=0;i<n;i++)text+='A'+i+';B;OE'+i+'\n';
 text+='A0;OTHER;last\n';
 const first=await B.stage(file('one.csv',text)),second=await B.stage(file('two.csv','Артикул;Бренд;OE\nA0;B;"OE1\nOE2"\n'));
 assert.equal(first.total,n+1);assert.equal(first.preview.length,200);assert.equal(second.total,1);
 assert.equal(await B.database().rows.where('source').equals(first.id).count(),0);
 assert.equal(first.storage,'pages-v1');assert(await B.database().rowPages.where('source').equals(first.id).count()<Math.ceil((n+1)/1000)+Math.ceil(text.length/(256*1024))+2);
 assert.deepEqual(plain(await B.page(second.id,0,1)),[['A0','B','OE1\nOE2']]);
 const body=B.facade(first,first.preview);assert.equal(body.length,n+1);assert(!Array.isArray(body));assert.equal(body.slice(0,5).length,5);assert.equal(Object.keys(body).length,202);
 const describe=row=>({key:row[0],brand:row[1],signature:''});
 await B.prepareKeys(first.id,'run1',describe);
 assert((await B.conflicts('run1',await B.page(first.id,0,1000),describe)).has('A0'));
 assert(!(await B.conflicts('run1',await B.page(first.id,1000,1000),describe)).has('A1000'));
 // Execute the application's actual preflight code against an array and the
 // staged source; verify accumulated OE and standard-field conflicts match.
 const mapped=[{target:'article',col:0,m:{}},{target:'brand',col:1,m:{}},{target:'oe_numbers',col:2,m:{}}];
 const inMemory=await c.conflictParity(Array.from(await B.page(first.id,0,first.total)),null,null,'article',mapped,[{k:'article'},{k:'brand'},{k:'oe_numbers'}]);
 const onDisk=await c.conflictParity(body,first.id,'parity','article',mapped,[{k:'article'},{k:'brand'},{k:'oe_numbers'}]);
 assert.deepEqual(Array.from(onDisk).sort(),Array.from(inMemory).sort());await B.clearRun('parity');
 // Changing mapping/key mode builds a new index and does not reuse stale conflicts.
 const byPair=row=>({key:row[0]+'|'+row[1],brand:row[1],signature:''});
 await B.prepareKeys(first.id,'run2',byPair);assert.equal((await B.conflicts('run2',await B.page(first.id,0,1000),byPair)).size,0);
 await B.clearRun('run1');await B.clearRun('run2');assert.equal(await B.database().keys.count(),0);assert.equal(await B.database().keyPages.count(),0);
 // Standard-value conflicts across batches remain blocked, but OE/custom
 // columns accumulate and must not create the same conflict.
 let evidence='article;brand;value\n';for(let i=0;i<2001;i++)evidence+='X'+i+';B;first\n';evidence+='X0;B;second\n';
 const ev=await B.stage(file('evidence.csv',evidence)),evRows=await B.page(ev.id,0,ev.total);
 for(const target of ['name','oe_numbers',null])for(const mode of ['article','article+brand']){
  const mapping=[{target:'article',col:0,m:{}},{target:'brand',col:1,m:{}},{target,col:2,m:{}}],std=[{k:'name'},{k:'article'},{k:'brand'},{k:'oe_numbers'}];
  const expected=await c.conflictParity(evRows,null,null,mode,mapping,std),run='ev-'+target+'-'+mode;
  const actual=await c.conflictParity(B.facade(ev,ev.preview),ev.id,run,mode,mapping,std);
  assert.deepEqual(Array.from(actual).sort(),Array.from(expected).sort());assert.equal(actual.length,target==='name'?1:0);await B.clearRun(run);
 }
 await B.remove(ev.id);
 // Actual shipped XLSX worker protocol is pull-based: one <=1000-row block
 // per request, preserving leading zero strings and not dropping the tail.
 vm.runInContext([...h.matchAll(/<script>([\s\S]*?)<\/script>/g)][1][1],c);assert(c.XLSX);const wb=c.XLSX.utils.book_new(),matrix=[['article','brand','oe']];for(let i=0;i<2503;i++)matrix.push([String(i).padStart(6,'0'),'B','OE']);
 c.XLSX.utils.book_append_sheet(wb,c.XLSX.utils.aoa_to_sheet(matrix),'Sheet');const bytes=c.XLSX.write(wb,{type:'array',bookType:'xlsx'});
 const messages=[],w={XLSX:c.XLSX,Uint8Array,self:{postMessage:msg=>messages.push(msg)}};vm.createContext(w);
 const wa=h.indexOf('function BrowserSourceXlsxWorker() {'),we=h.indexOf('const Import = {',wa);vm.runInContext(h.slice(wa,we)+';BrowserSourceXlsxWorker();',w);
 w.self.onmessage({data:{type:'init',buf:bytes}});assert.equal(messages.length,1);let read=0;
 do{w.self.onmessage({data:{type:'next'}});const page=messages.at(-1);assert(!page.error);assert(page.rows.length<=1000);if(!read)assert.equal(page.rows[1][0],'000000');read+=page.rows.length;if(page.done)break;}while(true);
 assert.equal(read,2504);
 const originalXlsx=B.xlsx.bind(B);B.xlsx=async(f,onBatch)=>{for(let i=0;i<matrix.length;i+=1000)await onBatch(matrix.slice(i,i+1000))};
 const xs=await B.stage({name:'book.xlsx'});assert.equal(xs.total,2503);assert.equal((await B.page(xs.id,2502,1))[0][0],'002502');await B.remove(xs.id);B.xlsx=originalXlsx;
 // Cached indexes skip the full scan, survive release/reopen, and are
 // invalidated on a mapping change; interrupted runs cannot be reused.
 const cached=await B.prepareKeys(second.id,'cache1',describe,'mapping1');assert.equal(cached,'cache1');await B.releaseRun(cached);
 B.database().close();await B.database().open();
 const originalPage=B.page;B.page=async()=>{throw Error('unexpected source scan')};
 assert.equal(await B.prepareKeys(second.id,'unused',describe,'mapping1'),'cache1');B.page=originalPage;
 assert.equal(await B.prepareKeys(second.id,'cache2',describe,'mapping2'),'cache2');assert(!await B.database().runs.get('cache1'));
 await B.database().runs.add({id:'partial',source:second.id,fingerprint:'mapping3'});
 assert.equal(await B.prepareKeys(second.id,'cache3',describe,'mapping3'),'cache3');assert(!await B.database().runs.get('partial'));
 await B.clearRun('cache3');
 // The bounded compound-key reader returns exact keys for both dense and
 // sparse/overflowing ranges; it must never leak unrelated conflict records.
 const dense=Array.from({length:1100},(_,i)=>({run:'range-test',key:String(i).padStart(6,'0'),conflict:i%2===0}));
 await B.database().keys.bulkAdd(dense);
 const wanted=Array.from({length:40},(_,i)=>['range-test',String(i*20).padStart(6,'0')]);
 const exact=await B.readKeyBatch(B.database().keys,'[run+key]',wanted,r=>[r.run,r.key]);assert.equal(exact.length,40);
 const wantedText=new Set(wanted.map(k=>k[1]));assert(exact.every(r=>wantedText.has(r.key)));
 const contiguous=await B.readKeyBatch(B.database().keys,'[run+key]',dense.slice(10,50).map(r=>[r.run,r.key]),r=>[r.run,r.key]);assert.equal(contiguous.length,40);
 await B.database().keys.where('run').equals('range-test').delete();
 // Legacy row-per-record sources and new variable-length pages coexist.
 await B.database().sources.add({id:'legacy',status:'ready',total:3,headers:['a']});
 await B.database().rows.bulkAdd([0,1,2].map(pos=>({source:'legacy',pos,cells:['L'+pos]})));
 assert.deepEqual(plain(await B.page('legacy',1,2)),[['L1'],['L2']]);await B.remove('legacy');
 await B.database().sources.add({id:'variable',status:'ready',total:7,headers:['a'],storage:'pages-v1'});
 await B.database().rowPages.bulkAdd([{source:'variable',start:0,cells:[['0'],['1']]},{source:'variable',start:2,cells:[['2']]},{source:'variable',start:3,cells:[['3'],['4'],['5'],['6']]}]);
 for(let start=0;start<=7;start++)for(let count=0;count<=7-start;count++)assert.deepEqual(plain(await B.page('variable',start,count)),Array.from({length:count},(_,i)=>[String(start+i)]));
 await B.database().rowPages.delete(['variable',2]);await assert.rejects(()=>B.page('variable',0,7),/повреждён/);
 await B.database().rowPages.add({source:'variable',start:2,cells:[['2']]});await B.database().rowPages.add({source:'variable',start:1,cells:[['overlap']]});await assert.rejects(()=>B.page('variable',0,7),/повреждён/);await B.database().rowPages.delete(['variable',1]);
 await assert.rejects(()=>B.page('variable',6,2),/повреждён/);await assert.rejects(()=>B.page('variable',-1,2),/повреждён/);
 await B.database().sources.update('variable',{storage:'unknown-version'});await assert.rejects(()=>B.page('variable',0,1),/повреждён/);await B.remove('variable');
 // Reopen source after closing the DB: no file reread, no missing tail rows.
 B.database().close();await B.database().open();assert.equal((await B.source(first.id)).total,n+1);
 assert.equal((await B.page(first.id,n,1))[0][1],'OTHER');
 B.active.add(first.id);await assert.rejects(()=>B.remove(first.id),/применяется/);B.active.delete(first.id);
 const before=await B.database().sources.count();cancel=true;await assert.rejects(()=>B.stage(file('cancel.csv','a;b\n1;2\n')),/cancelled/);cancel=false;
 assert.equal(await B.database().sources.count(),before);
 await assert.rejects(()=>B.stage(file('broken.csv','article;brand\nA;"broken')),/незакрытая/);assert.equal(await B.database().sources.count(),before);
 await assert.rejects(()=>B.stage(file('duplicate.csv','article;article\nA;B\n')),/Повторяющиеся/);
 // Storage failure cannot silently fall back to a million-element array.
 const bulk=B.database().rowPages.add.bind(B.database().rowPages);B.database().rowPages.add=async()=>{throw Error('QuotaExceededError')};
 await assert.rejects(()=>B.stage(file('full.csv','article;brand\nA;B\n')),/QuotaExceeded/);B.database().rowPages.add=bulk;
 assert.equal(await B.database().sources.count(),before);
 const pageCount=await B.database().rowPages.count();let pageWrites=0;
 B.database().rowPages.add=async value=>{if(++pageWrites===2)throw Error('QuotaExceededAfterPage');return bulk(value)};
 await assert.rejects(()=>B.stage(file('partially-full.csv',text)),/QuotaExceededAfterPage/);B.database().rowPages.add=bulk;
 assert.equal(await B.database().rowPages.count(),pageCount);assert.equal(await B.database().sources.count(),before);
 sql=true;await assert.rejects(()=>B.stage(file('sql.csv','article;brand\nA;B\n')),/браузерном/);sql=false;
 await B.remove(first.id);assert.equal(await B.database().rows.where('source').equals(first.id).count(),0);assert.equal(await B.database().rowPages.where('source').equals(first.id).count(),0);assert.equal((await B.source(second.id)).total,1);
 const wideText='Ж'.repeat(20000),wide=await B.stage(file('wide.csv','article;brand;name\n'+Array.from({length:40},(_,i)=>'W'+i+';B;'+wideText).join('\n')));
 const widePages=await B.database().rowPages.where('source').equals(wide.id).sortBy('start');
 assert(widePages.length>1);assert(widePages.every(p=>JSON.stringify(p.cells).length*2<=512*1024));
 B.database().close();await B.database().open();
 const wideRows=await B.page(wide.id,3,35);assert.equal(wideRows.length,35);assert.equal(wideRows[34][0],'W37');assert(wideRows.every(row=>row[2]===wideText));
 await B.remove(wide.id);
 await B.remove(second.id);await B.database().delete();
 // Execute the production unique-touched membership check for repeated OE rows.
 const markStart=h.indexOf('          const firstChange=rowChanged&&!changedRows.has(p);'),markEnd=h.indexOf('          if (!keepVisibility',markStart);
 const pushStart=h.indexOf('          if (firstChange) touched.push(p);',markEnd),pushEnd=h.indexOf('\n',pushStart);
 vm.runInContext('this.uniqueTouched=()=>{const changedRows=new WeakSet(),touched=[],p={};for(let i=0;i<10000;i++){const rowChanged=true;'+h.slice(markStart,markEnd)+h.slice(pushStart,pushEnd)+'}return touched.length;};',c);assert.equal(c.uniqueTouched(),1);
 console.log('OK: operation locks, reusable indexes, unique touched rows; embedded Dexie source staging, bounded preview, independent tables, cross-batch conflicts, remapping, reopen, failure cleanup and SQL isolation; rows',n+2);
})().catch(e=>{console.error(e);process.exitCode=1});
