const fs=require('fs'),vm=require('vm'),assert=require('assert');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');
const c={console,S:{rows:[]},HVC:{parts:new Map(),oe:new Map(),byArt:new Map(),byOe:new Map(),identityScope:()=>({}),keyOf:p=>p.article+'|'+p.brand,identityUnsafeKey:()=>false,identityUnsafe:()=>false,identityUnsafeOe:()=>false,EN_COLS:['name'],enCol:()=>true,enrichMode:()=> 'auto',enrichCatMode:()=> 'artbrand'},AnomalyDetector:{limits:[]},OE_DELIMITERS:{slash:{join:' / '}},oeMode:()=> 'slash'};
vm.createContext(c);
const a=h.indexOf('  async uploadHvcReference('),b=h.indexOf('  async enrichFull(',a);
vm.runInContext('this.P={'+h.slice(a,b)+'};',c);const P=c.P;
P.processingAvailable=async()=>true;P.processingMode=()=> 'sql';P.decodeRuleFields=f=>f;
let chunks=0,maxBytes=0,totalBytes=0,released=0,commits=0,failAt=-1,calls=0;
P._fetch=async(path,opts)=>{
 const size=Buffer.byteLength(opts.body);maxBytes=Math.max(maxBytes,size);totalBytes+=size;const p=JSON.parse(opts.body);
 if(path==='/catalog/hvc-reference'){
  if(p.action==='begin')return {token:'chunked:test'};
  if(p.action==='chunk'){chunks++;if(chunks===failAt)throw Error('connection reset');return {saved:p.items.length};}
  if(p.action==='commit'){commits++;return {reference_id:'chunked:test'};}
  if(p.action==='release'){released++;return {released:true};}
 }
 assert.equal(path,'/catalog/enrich-hvc-rows');assert.equal(p.reference,undefined);assert.equal(p.reference_id,'chunked:test');
 calls++;if(calls===failAt)throw Error('row reset');
 return {reference_id:'chunked:test',changed:p.rows.length,rows:p.rows.map(row=>({article:row.article,brand:row.brand,fields:{name:'SQL'},removed:[],special_values:[]}))};
};
(async()=>{
 // Optional >50 MiB graph reproduces the old single-request limit without
 // requiring a large fixture checked into Git.
 const n=process.env.HVC_LARGE_PROBE?55000:5000;
 const ref={parts:Array.from({length:n},(_,i)=>['P'+i+'|B',{name:'я'.repeat(600)}]),oe:[],byArt:[],byOe:[],unsafeKeys:[],unsafeOe:[],groupSeparator:' / '};
 await P.uploadHvcReference(ref);
 assert(chunks>1);assert(maxBytes<2*1024*1024);assert.equal(commits,1);
 if(process.env.HVC_LARGE_PROBE)assert(totalBytes>50*1024*1024);
 chunks=0;failAt=2;commits=0;await assert.rejects(()=>P.uploadHvcReference(ref),/connection reset/);assert.equal(commits,0);assert(released>=1);
 failAt=-1;c.S.rows=Array.from({length:1001},(_,i)=>({article:'A'+i,brand:'B',name:''}));
 calls=0;await P.enrichHvcRows(c.S.rows);assert.equal(calls,2);assert(c.S.rows.every(r=>r.name==='SQL'));
 c.S.rows.forEach(r=>r.name='');calls=0;failAt=2;
 await assert.rejects(()=>P.enrichHvcRows(c.S.rows),/row reset/);assert(c.S.rows.every(r=>r.name===''));
 // Full-enrichment buttons must use the same bounded row route and must
 // not announce success if canonical persistence fails.
 const fa=h.indexOf('  async enrichFull('),fb=h.indexOf('  async enrichOe()',fa);
 vm.runInContext('this.full={'+h.slice(fa,fb)+'};',c);
 let ok=0,fullCalls=0,saveFails=false;
 c.withProgress=async(a,b,fn)=>fn(()=>{});c.bumpVersion=()=>{};c.persistEconPending=()=>{};c.Table={paint:()=>{}};c.fmt=String;c.Toast={ok:()=>{ok++}};
 c.persistImportOrThrow=async()=>{if(saveFails)throw Error('save failed')};
 c.full.processingAvailable=async()=>true;c.full.enrichHvcRows=async rows=>{assert.strictEqual(rows,c.S.rows);fullCalls++;return 1};
 await c.full.enrichFull('oe');assert.equal(fullCalls,1);assert.equal(ok,1);
 saveFails=true;await assert.rejects(()=>c.full.enrichFull('oe'),/save failed/);assert.equal(ok,1);
 // Actual network wrapper reports the route; no blind retry of a POST.
 const na=h.indexOf('  async _fetch(path, opts) {'),nb=h.indexOf('  async health()',na);
 vm.runInContext('this.net={'+h.slice(na,nb)+'};',c);
 c.AbortController=AbortController;c.setTimeout=setTimeout;c.clearTimeout=clearTimeout;c.storageErrorText=e=>e.message;
 c.net.base=()=>'';c.net.token=()=>'';let attempts=0;
 c.fetch=async()=>{attempts++;throw TypeError('Failed to fetch')};
 await assert.rejects(()=>c.net._fetch('/catalog/hvc-reference',{}),/Нет ответа SQL: \/catalog\/hvc-reference/);assert.equal(attempts,1);
 console.log('OK: bounded HVC uploads, no inline graph, failed upload cleanup, whole-call row staging; max request bytes',maxBytes,'total probe bytes',totalBytes);
})().catch(e=>{console.error(e);process.exitCode=1});
