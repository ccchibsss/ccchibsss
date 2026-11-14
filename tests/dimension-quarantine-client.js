const fs=require('fs'),vm=require('vm'),assert=require('assert'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const a=h.indexOf('  async quarantineDimensions(rows) {'),b=h.indexOf('  async applyProductPolicies(',a);
const ctx={AnomalyDetector:{limits:[]},oeMode:()=> 'auto'};vm.createContext(ctx);vm.runInContext('globalThis.P={'+h.slice(a,b)+'};',ctx);
const P=ctx.P;P.processingAvailable=async()=>{};
(async()=>{
 const rows=[{article:'A',brand:'B',weight:NaN,dimensionAnomalyAck:{signature:'old'}},{article:'C',brand:'D'}];
 const before=JSON.stringify(rows);
 P._fetch=async(url,opts)=>{assert.equal(JSON.parse(opts.body).rows[0].weight,'NaN');return {rows:[{article:'A',brand:'B',fields:{dimensionAnomalyBlocked:true},removed:[]},{article:'WRONG',brand:'D',fields:{},removed:[]}]}};
 await assert.rejects(()=>P.quarantineDimensions(rows));assert.equal(JSON.stringify(rows),before);
 P._fetch=async()=>{throw Error('offline')};await assert.rejects(()=>P.quarantineDimensions(rows));assert.equal(JSON.stringify(rows),before);
 P._fetch=async()=>({rows:rows.map(p=>({article:p.article,brand:p.brand,fields:{dimensionAnomalyBlocked:true},removed:['dimensionAnomalyAck']}))});
 await P.quarantineDimensions(rows);assert(rows[0].dimensionAnomalyBlocked);assert(!('dimensionAnomalyAck' in rows[0]));
 assert(h.indexOf('if (sqlEnrichment) await PyEngine.quarantineDimensions(S.rows);')<h.indexOf('const result = await PyEngine.recalcAndApply(prog);'));
 console.log('OK: SQL dimension quarantine transport, validation and order');
})().catch(e=>{console.error(e);process.exitCode=1});
