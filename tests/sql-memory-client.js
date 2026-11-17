// SQL transport memory regressions, actual client methods with deterministic API.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');
const ctx={console,TextEncoder,Uint8Array,Uint32Array,DataView,AbortController,setTimeout,clearTimeout,S:{rows:[],settings:{}},OE_DELIMITERS:{auto:{join:' / '}},oeMode:()=> 'auto',AnomalyDetector:{limits:[]}};
vm.createContext(ctx);
const ma=h.indexOf('const SqlMemory = {'),mb=h.indexOf('const PyEngine = {',ma);
vm.runInContext(h.slice(ma,mb)+';this.M=SqlMemory;',ctx);
for(const value of ['',null,{},[1,null,'Ж🚗'],{custom:{x:'a'.repeat(10000)},date:new Date(0),bad:Infinity}])assert.equal(ctx.M.digest(value),crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex'));
for(const value of [{a:undefined,b:null,c:[undefined,NaN,Infinity,new Date(0)]},'я😀'.repeat(300001),{toJSON(){return {x:42}}}, {a:{toJSON(){return {x:1,toJSON(){return 'not twice'}}}}}]){
 const chunks=[...ctx.M.jsonChunks(value)];assert.equal(chunks.join(''),JSON.stringify(value));assert(chunks.every(c=>c.length<=300000));
 for(let i=0;i<chunks.length-1;i++)assert(!/[\uD800-\uDBFF]$/.test(chunks[i]));
}
const lazy=ctx.M.jsonArray(new Map([['a',new Set(['x','y'])]]),([k,v])=>[k,ctx.M.jsonArray(v)]);
assert.equal([...ctx.M.jsonChunks(lazy)].join(''),'[["a",["x","y"]]]');
const circular={};circular.self=circular;assert.throws(()=>[...ctx.M.jsonChunks(circular)],/Циклический/);
const wide={name:'Описание '.repeat(100000),custom:{nested:'0'.repeat(100000)},article:'A'};
const compact=ctx.M.fieldGuard(JSON.stringify(wide));assert(compact.length<300);
assert.notEqual(compact,ctx.M.fieldGuard(JSON.stringify({...wide,name:wide.name+'!'})));
assert.equal(ctx.M.fieldGuard('{"x":1}'),'{"x":"=1"}');
let visits=0;const map=new Map([['a',new Set(['x'])],['b',new Set(['y'])]]),view=ctx.M.view(map,([k,v])=>{visits++;return[k,[...v]]});assert.equal(visits,0);assert.equal(view.length,2);assert.equal([...view].length,2);assert.equal(visits,2);
const ps=h.indexOf('  async parseFile(f, options) {'),pe=h.indexOf('  async checkMarkStatus(',ps);
vm.runInContext('this.parser={'+h.slice(ps,pe)+'};',ctx);
const parser=ctx.parser;parser.base=()=>'';parser.token=()=>'';
const total=20001,calls=[];ctx.fetch=async()=>({ok:true,json:async()=>({parse_id:'token',headers:['article','brand','custom'],total})});
parser._fetch=async path=>{const q=new URL('http://test'+path).searchParams,off=Number(q.get('offset')),n=Number(q.get('limit'));calls.push({off,n});return{total,rows:Array.from({length:Math.min(n,total-off)},(_,i)=>({article:String(off+i).padStart(8,'0'),brand:'B',custom:'value'}))};};
const plain=x=>JSON.parse(JSON.stringify(x));
(async()=>{
 const result=await parser.parseFile({name:'big.csv'},{table:true,catalogImport:true,paged:true});
 assert.equal(calls.length,1);assert.equal(calls[0].n,200);assert.equal(result.preview.length,200);assert.equal(result.body.length,total);assert.equal(result.body.slice(0,total).length,200);assert(!Array.isArray(result.body));
 let n=0,last;for await(const row of parser.iterateParsedSource(result.body._sqlSource)){n++;last=row;}
 assert.equal(n,total);assert.equal(last[0],'00020000');assert(Math.max(...calls.map(c=>c.n))<=4000);
 parser._fetch=async()=>({total:total+1,rows:[]});await assert.rejects(()=>parser.parsedSourcePage(result.body._sqlSource,0,1),/Неполный/);
 const a=h.indexOf('  async uploadHvcReference('),b=h.indexOf('  async enrichFull(',a);
 vm.runInContext('this.P={'+h.slice(a,b)+'};',ctx);const P=ctx.P;
 let mode='sql',fail=false,edit=false,structure='',uploaded=0;
 ctx.HVC={parts:new Map(),oe:new Map(),byArt:new Map(),byOe:new Map(),identityScope:()=>({}),identityUnsafeKey:()=>false,identityUnsafe:()=>false,identityUnsafeOe:()=>false,keyOf:p=>p.article+'|'+p.brand,EN_COLS:['name'],enCol:()=>true,enrichMode:()=> 'auto',enrichCatMode:()=> 'artbrand'};
 P.processingAvailable=async()=>true;P.processingMode=()=>mode;P.decodeRuleFields=x=>x;
 P._fetch=async(path,opts)=>{
  const body=JSON.parse(opts.body);
  if(path==='/catalog/hvc-reference'){
   if(body.action==='begin'){uploaded=0;return{token:'chunked:test'};}
   if(body.action==='chunk'){assert(body.items.length<=8000);uploaded+=body.items.length;return{saved:body.items.length};}
   return body.action==='commit'?{reference_id:'chunked:test'}:{};
  }
  assert.equal(path,'/catalog/enrich-hvc-rows');
  if(fail&&body.rows[0].article==='1000')throw Error('late failure');
  if(edit&&body.rows[0].article==='1000')ctx.S.rows[0].custom.keep='external edit';
  if(structure&&body.rows[0].article==='1000'){if(structure==='append')ctx.S.rows.push({article:'extra',brand:'B',name:''});else ctx.S.rows.pop();structure='';}
  return{reference_id:body.reference_id,changed:body.rows.length,rows:body.rows.map(p=>({article:p.article,brand:p.brand,fields:{name:'SQL '+p.article},removed:[]}))};
 };
 ctx.S.rows=Array.from({length:2001},(_,i)=>({article:String(i),brand:'B',custom:{keep:'00042'},name:''}));
 ctx.HVC.parts.set('0|B',{name:'donor'});ctx.HVC.byArt.set('0|B',new Set(['OE']));ctx.HVC.byOe.set('OE',new Set(['0|B']));ctx.HVC.oe.set('OE',{});
 let before=JSON.stringify(ctx.S.rows);fail=true;await assert.rejects(()=>P.enrichHvcRows(ctx.S.rows),/late failure/);assert.equal(JSON.stringify(ctx.S.rows),before);
 fail=false;edit=true;await assert.rejects(()=>P.enrichHvcRows(ctx.S.rows),/Каталог изменился/);assert(ctx.S.rows.every(p=>p.name===''));assert.equal(ctx.S.rows[0].custom.keep,'external edit');
 edit=false;
 for(const operation of ['append','remove']){
  const selected=ctx.S.rows.slice(0,2000);structure=operation;
  await assert.rejects(()=>P.enrichHvcRows(selected),/Каталог изменился/);assert(selected.every(p=>p.name===''));
  if(operation==='append')ctx.S.rows.pop();else ctx.S.rows.push({article:'2000',brand:'B',custom:{keep:'00042'},name:''});
 }
 assert.equal(await P.enrichHvcRows(ctx.S.rows),2001);assert(ctx.S.rows.every(p=>p.name==='SQL '+p.article));assert.equal(uploaded,4);assert.equal(ctx.S.rows[0].custom.keep,'external edit');
 console.log('OK: SQL paged source keeps 200 preview rows, repeatable complete iteration, SHA-256 guards, lazy HVC graph, no partial mutation on late failure or concurrent edit');
})().catch(e=>{console.error(e);process.exitCode=1});
