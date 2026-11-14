const fs=require('fs'),vm=require('vm'),assert=require('assert'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const a=h.indexOf('  async fixDimensionUnits('),b=h.indexOf('  async enrichSavedProduct(',a);
const ctx={AnomalyDetector:{limits:[]},oeMode:()=> 'auto',STD:[{k:'weight',n:'Вес'}]};vm.createContext(ctx);vm.runInContext('globalThis.P={'+h.slice(a,b)+'};',ctx);
const P=ctx.P;P.processingAvailable=async()=>{};
(async()=>{
 const entries=[{p:{article:'A',brand:'B',weight:1000},signature:'sig'},{p:{article:'C',brand:'D',weight:2000},signature:'sig2'}];
 const before=JSON.stringify(entries);
 const reply=()=>({rows:entries.map(e=>({article:e.p.article,brand:e.p.brand,fields:{weight:1},removed:['dimensionAnomalyAck'],result:{status:'applied'}}))});
 P._fetch=async()=>{const r=reply();r.rows[1].article='WRONG';return r};await assert.rejects(()=>P.fixDimensionUnits(entries,true));assert.equal(JSON.stringify(entries),before);
 P._fetch=async()=>{throw Error('offline')};await assert.rejects(()=>P.fixDimensionUnits(entries,true));assert.equal(JSON.stringify(entries),before);
 P._fetch=async(url,o)=>{const b=JSON.parse(o.body);assert.equal(b.items[0].signature,'sig');assert.equal(b.labels.weight,'Вес');return reply()};
 await P.fixDimensionUnits(entries,false);assert.equal(JSON.stringify(entries),before);
 await P.fixDimensionUnits(entries,true);assert.equal(entries[0].p.weight,1);
 assert(h.includes("if(PyEngine.processingMode()==='sql')return this.applyFixSql(selectedOnly);"));
 console.log('OK: SQL unit-fix preview, batch validation and approval');
})().catch(e=>{console.error(e);process.exitCode=1});
