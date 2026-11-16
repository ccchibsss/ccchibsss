// Integration test uses the shipped Dexie build, not a replacement ORM.
// NODE_PATH=.arena/idb-tests/node_modules node tests/browser-import-sources-indexeddb.js
const fs=require('fs'),vm=require('vm'),assert=require('assert'),fidb=require('fake-indexeddb');
const h=fs.readFileSync(__dirname+'/../index.html','utf8'),lib=[...h.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1];
let seq=0,cancel=false,sql=false;
const c={...fidb,console,setTimeout,clearTimeout,queueMicrotask,AbortController,structuredClone,TextDecoder,Blob,performance,CustomEvent:class{constructor(t){this.type=t}},location:{protocol:'http:'},navigator:{},uid:p=>p+'-'+(++seq),PyEngine:{processingMode:()=>sql?'sql':'browser'},UCCancel:{check(){if(cancel)throw Error('cancelled')}},Prog:{msg(){},step(){}}};c.window=c;c.self=c;
vm.createContext(c);vm.runInContext(lib,c);
const ca=h.indexOf('const CsvStream = {'),cb=h.indexOf('\n/* Воркер XLSX',ca);vm.runInContext(h.slice(ca,cb)+';this.Csv=CsvStream;',c);
const a=h.indexOf('const BrowserImportSources = {'),b=h.indexOf('const Import = {',a);vm.runInContext(h.slice(a,b)+';this.B=BrowserImportSources;',c);
const B=c.B;
const preStart=h.indexOf('      const sourceVariants=',h.indexOf('const Import = {')),preEnd=h.indexOf('      let sourceCollision=',preStart);
c.normArticle=v=>String(v??'').toUpperCase().replace(/[^A-Z0-9]/g,'');
vm.runInContext('this.conflictParity=async(body,sourceId,collisionRun,keyMode,mapped,STD)=>{const artMap=mapped.find(x=>x.target==="article"),brandMap=mapped.find(x=>x.target==="brand");'+h.slice(preStart,preEnd)+';if(!sourceId)return [...sourceConflicts];const s=await BrowserImportSources.source(sourceId);const found=new Set();for(let off=0;off<s.total;off+=1000)for(const k of await BrowserImportSources.conflicts(collisionRun,await BrowserImportSources.page(sourceId,off,Math.min(1000,s.total-off)),describeSource))found.add(k);return [...found];};',c);

function file(name,text){const f=new Blob([text]);f.name=name;return f}
const plain=v=>JSON.parse(JSON.stringify(v));
(async()=>{
 const n=Number(process.env.SOURCE_ROWS||12000);
 let text='Артикул;Бренд;OE\n';for(let i=0;i<n;i++)text+='A'+i+';B;OE'+i+'\n';
 text+='A0;OTHER;last\n';
 const first=await B.stage(file('one.csv',text)),second=await B.stage(file('two.csv','Артикул;Бренд;OE\nA0;B;"OE1\nOE2"\n'));
 assert.equal(first.total,n+1);assert.equal(first.preview.length,200);assert.equal(second.total,1);
 assert.equal(await B.database().rows.where('source').equals(first.id).count(),n+1);
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
 await B.clearRun('run1');await B.clearRun('run2');assert.equal(await B.database().keys.count(),0);
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
 // Reopen source after closing the DB: no file reread, no missing tail rows.
 B.database().close();await B.database().open();assert.equal((await B.source(first.id)).total,n+1);
 assert.equal((await B.page(first.id,n,1))[0][1],'OTHER');
 B.active.add(first.id);await assert.rejects(()=>B.remove(first.id),/применяется/);B.active.delete(first.id);
 const before=await B.database().sources.count();cancel=true;await assert.rejects(()=>B.stage(file('cancel.csv','a;b\n1;2\n')),/cancelled/);cancel=false;
 assert.equal(await B.database().sources.count(),before);
 await assert.rejects(()=>B.stage(file('broken.csv','article;brand\nA;"broken')),/незакрытая/);assert.equal(await B.database().sources.count(),before);
 await assert.rejects(()=>B.stage(file('duplicate.csv','article;article\nA;B\n')),/Повторяющиеся/);
 // Storage failure cannot silently fall back to a million-element array.
 const bulk=B.database().rows.bulkAdd.bind(B.database().rows);B.database().rows.bulkAdd=async()=>{throw Error('QuotaExceededError')};
 await assert.rejects(()=>B.stage(file('full.csv','article;brand\nA;B\n')),/QuotaExceeded/);B.database().rows.bulkAdd=bulk;
 assert.equal(await B.database().sources.count(),before);
 sql=true;await assert.rejects(()=>B.stage(file('sql.csv','article;brand\nA;B\n')),/браузерном/);sql=false;
 await B.remove(first.id);assert.equal(await B.database().rows.where('source').equals(first.id).count(),0);assert.equal((await B.source(second.id)).total,1);
 await B.remove(second.id);await B.database().delete();
 console.log('OK: embedded Dexie source staging, bounded preview, independent tables, cross-batch conflicts, remapping, reopen, failure cleanup and SQL isolation; rows',n+2);
})().catch(e=>{console.error(e);process.exitCode=1});
