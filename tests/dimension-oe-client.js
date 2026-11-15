const fs=require('fs'),vm=require('vm'),assert=require('assert'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const rows=[{article:'A',brand:'B',weight:1000,dimensionAnomalyBlocked:true},{article:'C',brand:'D',weight:2000,dimensionAnomalyBlocked:true}];
const calls=[];let bad=false,offline=false,applyCount=0,savedSnapshot;
const ctx={S:{rows,catalogVersion:1,settings:{}},HVC:{ozonRevision:2,parts:new Map(),byOe:new Map(),oe:new Map(),cross:new Map()},
 STD:[],oeMode:()=> 'auto',confirm:()=>true,Toast:{info:()=>{},warn:()=>{}},
 AnomalyDetector:{limits:[],found:rows.map(p=>({p})),log:[],save:()=>{},renderLog:()=>{}},runPipeline:async()=>{calls.push('pipeline')}};
vm.createContext(ctx);
const obj=h.match(/const AnomalyOE = \{[\s\S]*?\n\};/)[0];
const a=h.indexOf('  dimensionOeSnapshot('),b=h.indexOf('  async fixDimensionUnits(',a);
vm.runInContext('globalThis.P={'+h.slice(a,b)+'};\n'+obj+';globalThis.O=AnomalyOE;',ctx);
ctx.PyEngine=ctx.P;ctx.P.processingMode=()=> 'sql';ctx.P.processingAvailable=async()=>{};
const O=ctx.O;O.render=()=>{};
ctx.P._fetch=async(url,o)=>{
 if(offline)throw Error('offline');const body=JSON.parse(o.body);calls.push(body.operation);
 if(body.operation==='find'){
   savedSnapshot=JSON.stringify(body.snapshot);
   return {token:'token',summary:{checked:2,noChoice:0,changed:0,pending:0,errors:0},preview:rows.map((p,i)=>({targetIndex:i,signature:'sig'+i,codes:['OE1'],status:'Предложение',choice:{tuple:{weight:1,length:10,width:10,height:10},source:'donor',link:{tier:'oe',oe:'OE1'}},link:{tier:'oe',oe:'OE1'}}))};
 }
 assert.equal(body.token,'token');assert.equal(JSON.stringify(body.snapshot),savedSnapshot);assert.deepEqual(body.selected,[0,1]);applyCount++;
 return {rows:rows.map((p,i)=>({targetIndex:i,article:bad&&i===1?'WRONG':p.article,brand:p.brand,fields:{weight:1,_dimensionOeReview:{source:'donor'}},removed:['dimensionAnomalyAck'],log:{article:p.article}}))};
};
(async()=>{
 await O.find({});assert.equal(O.preview[0].p,rows[0]);O.preview.forEach(x=>x.checked=true);
 const before=JSON.stringify(rows);bad=true;
 await assert.rejects(()=>O.apply({}));assert.equal(JSON.stringify(rows),before);assert.equal(ctx.AnomalyDetector.log.length,0);
 bad=false;offline=true;await assert.rejects(()=>O.apply({}));assert.equal(JSON.stringify(rows),before);offline=false;
 ctx.S.catalogVersion++;await assert.rejects(()=>O.apply({}));assert.equal(JSON.stringify(rows),before);
 await O.find({});O.preview.forEach(x=>x.checked=true);await O.apply({});assert.equal(rows[0].weight,1);assert.equal(rows[1].weight,1);assert(calls.includes('pipeline'));
 // Automatic find routes through the same SQL apply without any JS donor inference.
 ctx.S.catalogVersion++;ctx.AnomalyDetector.found=rows.map(p=>({p}));
 await O.find({automatic:true});assert(applyCount>=3);
 console.log('OK: SQL OE find/apply/automatic routing, stale/offline and atomic client validation');
})().catch(e=>{console.error(e);process.exitCode=1});
