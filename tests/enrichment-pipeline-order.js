const fs=require('fs'),vm=require('vm'),assert=require('assert'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const start=h.indexOf('      const sqlBatch=',h.indexOf('function runPipeline')),end=h.indexOf('      for (let idx = start;',start);
assert(start>0&&end>start);
const guard=h.match(/const NUMERIC_DATE_GUARD = \[[^]*?\];/)[0];
const ctx={};vm.createContext(ctx);
vm.runInContext(guard+`;this.run=async(full,delta,withRules=false)=>{
 const rows=NUMERIC_DATE_GUARD.map((field,i)=>({article:String(i),brand:'B',[field]:new Date('2026-01-01T00:00:00Z')}));
 const untouched={article:'unchanged',price:new Date(0)};rows.push(untouched);
 const S={rows},start=0,end=rows.length,sqlEnrichment=true,changedRows=delta?new Set(rows.slice(0,-1)):null,isChangedRow=p=>changedRows.has(p);
 const nameCategoryContext={},nameAutoEnabled=true,ozonSqlReference={},ex=[],enrichRules=withRules?[{}]:[],calls=[];
 const normArticle=v=>'normalized:'+v,HVC={ensureNorm:p=>{p.normalized=true;}};
 let snapshot;
 const check=(step,batch)=>{calls.push(step);for(const p of batch){for(const key of NUMERIC_DATE_GUARD)if(key in p)assertZero(p[key]);if(!p.normalized)throw Error('normalization missing');}};
 const PyEngine={
  enrichRules:async(b)=>check('rules',b),
  enrichNameCategories:async(c,e,b)=>check('name',b),
  enrichCategoryKinds:async(c,e,b)=>check('kind',b),
  enrichOzonPreferred:async(b)=>check('ozon',b),
  applyProductPolicies:async(b)=>{check('policies',b);snapshot=JSON.parse(JSON.stringify(b));}
 };
 ${h.slice(start,end)}
 return {rows:snapshot,calls,untouchedDate:untouched.price instanceof Date};
};`,ctx);
ctx.assertZero=v=>assert.strictEqual(v,0);
(async()=>{
 const output=[];
 for(const full of [true,false])for(const delta of [true,false])for(const withRules of [true,false]){
  const r=await ctx.run(full,delta,withRules);assert.deepStrictEqual(Array.from(r.calls),[...(full?['name','kind','ozon']:[]),'policies',...(withRules?['rules']:[]),...(full&&withRules?['ozon']:[])]);
  assert.equal(r.untouchedDate,delta);output.push({full,delta,...r});
 }
 // Name/kind processing must not also run ahead of the prelude elsewhere.
 const prefix=h.slice(h.indexOf('function runPipeline'),start);
 assert(!prefix.includes('await PyEngine.enrichNameCategories('));
 process.stdout.write(JSON.stringify(output));
})().catch(e=>{console.error(e);process.exitCode=1});
