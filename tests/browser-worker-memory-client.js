const fs=require('fs'),vm=require('vm'),assert=require('assert');
const h=fs.readFileSync(__dirname+'/../index.html','utf8'),workers=[],urls=new Set(),timers=new Map();let sequence=0,fail='',fallbacks=0;
class Worker {
 constructor(){if(fail==='construct')throw Error('constructor');this.live=true;this.messages=[];this.inflight=null;workers.push(this);}
 postMessage(m){if(fail===m.type)throw Error('post failed');if(m.type==='rowsChunk'){assert(!this.inflight,'multiple unacknowledged chunks');assert(m.buf.byteLength<=1048576);this.inflight=m;}this.messages.push(m);}
 ack(overrides={}){const m=this.inflight;assert(m);this.inflight=null;this.onmessage({data:{type:'rowsAck',upload:m.upload,part:m.part,ver:m.v,last:m.last,...overrides}});}
 finish(){while(this.inflight)this.ack();}
 terminate(){this.live=false;this.messages=[];this.inflight=null;}
}
const c={console,Blob,TextEncoder,Worker,URL:{createObjectURL:()=>{const u='blob:'+ ++sequence;urls.add(u);return u},revokeObjectURL:u=>urls.delete(u)},S:{sort:{k:'article'},rows:Array.from({length:4001},(_,i)=>({article:String(i),name:'Wide '.repeat(20)})),catalogVersion:1,filter:{},settings:{}},setTimeout:fn=>{const id=++sequence;timers.set(id,fn);return id},clearTimeout:id=>timers.delete(id),syncApplyFilter:()=>fallbacks++,MemGuard:{check:()=>0}};
vm.createContext(c);const a=h.indexOf('const FWorker = (function () {'),b=h.indexOf('/* Диспетчер:',a);
vm.runInContext(h.slice(a,b)+';this.W=FWorker;',c);
for(const mode of ['construct','rowsChunk','filter','error','timeout','uploadTimeout','release'])for(let i=0;i<10;i++){
 fail=mode==='construct'?'construct':mode==='rowsChunk'?'rowsChunk':'';
 const loaded=c.W.setRowsIfNeeded(c.S.rows,i+1);assert.equal(urls.size,0,'blob URL leaked');
 if(['construct','rowsChunk'].includes(mode))assert(!loaded);
 else{
  assert(loaded);const w=workers.at(-1);assert.equal(w.messages.filter(m=>m.type==='rowsChunk').length,1);
  if(mode!=='uploadTimeout')w.finish();fail=mode==='filter'?'filter':'';
  const accepted=c.W.filter({},c.S.sort,i+1,()=>{});
  if(mode==='filter')assert(!accepted);
  else if(mode==='error')w.onerror();
  else if(mode==='timeout'||mode==='uploadTimeout'){for(const [id,fn] of [...timers]){timers.delete(id);fn();}}
  else c.W.release();
 }
 assert.equal(workers.filter(w=>w.live).length,0,mode+' left worker alive');assert.equal(timers.size,0,mode+' timer leak');
}
fail='';c.W.setRowsIfNeeded(c.S.rows,99);let callback=0;c.W.filter({},c.S.sort,99,()=>callback++);
const worker=workers.at(-1);assert(!worker.messages.some(m=>m.type==='filter'),'filter before upload ACK');
worker.finish();const message=worker.messages.at(-1);worker.onmessage({data:{type:'filter',id:message.id,idx:[0],ver:99}});assert.equal(callback,1);assert.equal(timers.size,0);c.W.release();
// Catalog changes between acknowledgements abort, never publish a mixed projection.
c.W.setRowsIfNeeded(c.S.rows,100);const stale=workers.at(-1);c.S.catalogVersion++;stale.ack();assert(!stale.live);assert.equal(timers.size,0);
// Refused upload must not dispatch filtering to a new, empty worker.
const fa=h.indexOf('function applyFilter() {'),fb=h.indexOf('\n}',fa)+2;
vm.runInContext(h.slice(fa,fb)+';this.apply=applyFilter;',c);c.workerFits=()=>true;
c.W.setRowsIfNeeded(c.S.rows,101);c.MemGuard.check=()=>2;const before=workers.length;c.apply();assert.equal(workers.length,before);assert.equal(workers.filter(w=>w.live).length,0);assert(fallbacks>0);
assert(!h.includes('OzonExport._stdExportRows'));
console.log('OK: one byte-bounded unacknowledged Worker chunk, filters wait for final ACK, stale catalog/upload timeout cleanup, no worker/URL/timer leaks');
