const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(__dirname+'/../index.html','utf8');
let writes=[],removed=[],closed=0,aborted=0,quota=false,timers=[];
const writer={write:async blob=>{if(quota)throw Error('quota exceeded');writes.push(await blob.text())},close:async()=>closed++,abort:async()=>aborted++};
const dir={async *entries(){yield ['1-expired.xlsx',{}];yield ['unknown',{}]},removeEntry:async name=>removed.push(name),getFileHandle:async()=>({createWritable:async()=>writer,getFile:async()=>new Blob(writes)})};
const c={navigator:{storage:{getDirectory:async()=>({getDirectoryHandle:async()=>dir})}},crypto:{randomUUID:()=> 'test'},Blob,setTimeout:fn=>{timers.push(fn);return timers.length},Date};vm.createContext(c);
vm.runInContext(html.slice(html.indexOf('const BrowserExportSpool = {'),html.indexOf('const PyEngine = {'))+';this.spool=BrowserExportSpool;',c);
(async()=>{
 const disk=await c.spool.create();assert(disk.disk);await disk.write([new Blob(['part1']),new Blob(['part2'])]);const file=await disk.finish();assert.equal(await file.text(),'part1part2');assert.equal(closed,1);assert.deepEqual(removed,['1-expired.xlsx']);await timers.pop()();assert(removed.some(n=>n.endsWith('-test.xlsx')));assert(!removed.includes('unknown'));
 writes=[];const failed=await c.spool.create();quota=true;await assert.rejects(()=>failed.write([new Blob(['data'])]),/quota/);await failed.abort();assert.equal(aborted,1);quota=false;
 c.navigator.storage.getDirectory=undefined;const memory=await c.spool.create();assert(!memory.disk);await memory.write([new Blob(['portable'])]);const blob=await memory.finish('application/test');assert.equal(await blob.text(),'portable');assert.equal(blob.type,'application/test');
 const cancelled=await c.spool.create();await cancelled.write([new Blob(['discard'])]);await cancelled.abort();assert.equal((await cancelled.finish()).size,0);
 console.log('OK: disk-spooled export flush/close, expired-temp cleanup, no early deletion, quota failure abort, portable compressed Blob fallback');
})().catch(e=>{console.error(e);process.exitCode=1});
