const fs=require('fs'),vm=require('vm'),assert=require('assert');
const h=fs.readFileSync(__dirname+'/../index.html','utf8'),c={console,S:{settings:{},rows:[]}};
vm.createContext(c);const a=h.indexOf('  async acquireOzonReference('),b=h.indexOf('  prepareOzonTyping(',a);
vm.runInContext('this.P={'+h.slice(a,b)+'};',c);const P=c.P;P.processingAvailable=async()=>{};
let begins=0,commits=0,releases=0,maxBytes=0,rowCalls=0,failRow=-1,failUpload=false,text='';
P._fetch=async(path,opts)=>{
 maxBytes=Math.max(maxBytes,Buffer.byteLength(opts.body));const p=JSON.parse(opts.body);
 if(path==='/catalog/ozon-reference'){
  if(p.action==='begin'){begins++;text='';return {token:'ozon:test'}}
  if(p.action==='chunk'){if(failUpload)throw Error('upload failed');text+=p.data;return {saved:p.data.length}}
  if(p.action==='commit'){commits++;assert.doesNotThrow(()=>JSON.parse(text));return {reference_id:'ozon:test'}}
  if(p.action==='release'){releases++;return {}}
 }
 assert.equal(path,'/catalog/enrich-ozon-preferred');assert.equal(p.reference,undefined);assert.equal(p.reference_id,'ozon:test');
 if(++rowCalls===failRow)throw Error('row failed');
 return {rows:p.rows.map(r=>({article:r.article,brand:r.brand,fields:{ozon_type:'NEW'},removed:[]}))};
};
(async()=>{
 const n=process.env.OZON_LARGE_PROBE?55000:3000;
 const ref={pairs:[],category_rows:[],identity:{rows:[],parts:Array.from({length:n},(_,i)=>['A'+i,{name:'я😀'.repeat(250)}])}};
 await P.acquireOzonReference(ref);assert(maxBytes<2*1024*1024);if(process.env.OZON_LARGE_PROBE)assert(Buffer.byteLength(text)>50*1024*1024);
 assert.deepEqual(JSON.parse(text),ref);await P.acquireOzonReference(ref);assert.equal(begins,1);await P.releaseOzonReference(ref);assert.equal(releases,1);
 failUpload=true;await assert.rejects(()=>P.acquireOzonReference(ref),/upload failed/);assert.equal(commits,1);assert.equal(releases,2);failUpload=false;
 const small={pairs:[],category_rows:[],identity:{rows:[]}};
 const rows=Array.from({length:1001},(_,i)=>({article:String(i),brand:'B',ozon_type:'OLD'}));c.S.rows=rows;
 P.ozonProcessingReference=()=>small;
 rowCalls=0;failRow=2;await assert.rejects(()=>P.enrichOzonPreferred(rows),/row failed/);assert(rows.every(r=>r.ozon_type==='OLD'));
 failRow=-1;await P.enrichOzonPreferred(rows,{reference:small});const sharedBegins=begins;
 await P.enrichOzonPreferred(rows,{reference:small});assert.equal(begins,sharedBegins);assert(rows.every(r=>r.ozon_type==='NEW'));await P.releaseOzonReference(small);
 console.log('OK: chunked Ozon reference, Unicode roundtrip, session reuse, cleanup and whole-call staging; max request bytes',maxBytes);
})().catch(e=>{console.error(e);process.exitCode=1});
