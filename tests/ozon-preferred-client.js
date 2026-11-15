const fs=require('fs'),vm=require('vm'),assert=require('assert'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const a=h.indexOf('  async enrichOzonPreferred(rows, options={}) {'),b=h.indexOf('  async enrichRules(',a);
const ctx={};vm.createContext(ctx);vm.runInContext('globalThis.P={'+h.slice(a,b)+'};',ctx);
ctx.S={settings:{}};const P=ctx.P;P.processingAvailable=async()=>{};P.ozonProcessingReference=()=>({});P.acquireOzonReference=async()=> 'ozon:test';P.releaseOzonReference=async()=>{};
(async()=>{
 const rows=[{article:'A',brand:'B',ozon_type:'old',_ozonNameStatus:'stale'},{article:'C',brand:'D',ozon_type:'old'}];
 const before=JSON.stringify(rows);
 P._fetch=async()=>({rows:[{article:'A',brand:'B',fields:{ozon_type:'NEW'},removed:[]},{article:'WRONG',brand:'D',fields:{},removed:[]}]});
 await assert.rejects(()=>P.enrichOzonPreferred(rows));assert.equal(JSON.stringify(rows),before);
 P._fetch=async()=>{throw new Error('offline')};await assert.rejects(()=>P.enrichOzonPreferred(rows));assert.equal(JSON.stringify(rows),before);
 P._fetch=async()=>({rows:rows.map(p=>({article:p.article,brand:p.brand,fields:{ozon_type:'NEW'},removed:['_ozonNameStatus']}))});
 await P.enrichOzonPreferred(rows);assert.equal(rows[0].ozon_type,'NEW');assert(!('_ozonNameStatus' in rows[0]));
 assert(h.includes('await PyEngine.enrichOzonPreferred(sqlBatch,{reference:ozonSqlReference});'));
 console.log('OK: SQL Ozon client validation and removals');
})().catch(e=>{console.error(e);process.exitCode=1});
