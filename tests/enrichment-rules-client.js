const fs=require('fs'),vm=require('vm'),assert=require('assert'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const a=h.indexOf('  encodeRuleRows('),b=h.indexOf('  async enrichCategoryKinds(',a),ctx={S:{rows:[],catalogVersion:1}};
vm.createContext(ctx);vm.runInContext('this.client={'+h.slice(a,b)+'};',ctx);
const c=ctx.client;c.processingAvailable=async()=>true;c.processingMode=()=>'sql';
const rules=['result','cloned'].map(target_val=>({kind:'enrich',enabled:true,target_val}));
(async()=>{
 const p={article:'A',brand:'B',value:Infinity,nested:{items:[NaN,-Infinity]}};ctx.S.rows=[p];
 c._fetch=async(path,options)=>{
  assert.equal(path,'/catalog/enrich-rules');const input=JSON.parse(options.body);
  assert.equal(input.rows[0].value,null);assert.equal(input.special_values.length,3);
  return {rows:[{article:'A',brand:'B',fields:{result:null,cloned:{items:[null,null]}},removed:[],special_values:[
   {path:['result'],kind:'positive'},{path:['cloned','items',0],kind:'nan'},{path:['cloned','items',1],kind:'negative'}]}]};
 };
 await c.enrichRules([p],rules,{});assert.equal(p.result,Infinity);assert(Number.isNaN(p.cloned.items[0]));assert.equal(p.cloned.items[1],-Infinity);
 const rows=Array.from({length:1001},(_,i)=>({article:String(i),brand:'B'}));ctx.S.rows=rows;let calls=0;
 c._fetch=async(path,opts)=>{if(++calls===2)throw Error('offline');return {rows:JSON.parse(opts.body).rows.map(p=>({...p,fields:{result:42},removed:[]}))};};
 await assert.rejects(()=>c.enrichRules(rows,rules,{}),/offline/);assert(rows.every(p=>!('result' in p)));
 ctx.S.rows=[p];const before=p.result;
 c._fetch=async()=>({rows:[{article:'A',brand:'B',fields:{result:0},removed:['name']}]});
 await assert.rejects(()=>c.enrichRules([p],rules,{}),/Неверный/);assert.equal(p.result,before);
 c._fetch=async()=>({rows:[{article:'A',brand:'B',fields:{result:null},removed:[],special_values:[{path:['result'],kind:'bogus'}]}]});
 await assert.rejects(()=>c.enrichRules([p],rules,{}),/Неверный/);assert.equal(p.result,before);
 c._fetch=async()=>{p.value=-Infinity;return {rows:[{article:'A',brand:'B',fields:{result:0},removed:[]}]};};
 await assert.rejects(()=>c.enrichRules([p],rules,{}),/изменились/);assert.equal(p.result,before);
 c._fetch=async()=>{ctx.S.settings={changed:true};return {rows:[{article:'A',brand:'B',fields:{result:0},removed:[]}]};};
 await assert.rejects(()=>c.enrichRules([p],rules,{}),/изменились/);assert.equal(p.result,before);
 const encoded=c.encodeRuleRows([{article:'A',nested:{value:Infinity}}]);assert.equal(encoded.special_values[0].path[2],'value');
 assert.throws(()=>c.decodeRuleFields({a:null},[{path:['a'],kind:'nan'},{path:['a'],kind:'nan'}]));
 assert.throws(()=>c.decodeRuleFields({},[{path:['__proto__','x'],kind:'positive'}]));
 vm.runInContext("this.dateRows=[{article:'D',brand:'B',date:new Date(0),invalid:new Date(NaN)}];",ctx);
 const dates=ctx.dateRows;ctx.S.rows=dates;
 c._fetch=async(path,opts)=>{
  const input=JSON.parse(opts.body),entry=input.special_values.find(e=>e.path[1]==='date');
  assert.equal(entry.kind,'date');assert.equal(entry.milliseconds,0);
  return {rows:[{article:'D',brand:'B',fields:{result:input.rows[0].date,cloned:{date:input.rows[0].invalid}},removed:[],special_values:[
   {...entry,path:['result']},{...input.special_values.find(e=>e.path[1]==='invalid'),path:['cloned','date']}]}]};
 };
 await c.enrichRules(dates,rules,{});assert.equal(dates[0].result.getTime(),0);assert(Number.isNaN(dates[0].cloned.date.getTime()));
 c._fetch=async()=>{dates[0].date.setTime(1);return {rows:[{article:'D',brand:'B',fields:{result:42},removed:[]}]};};
 await assert.rejects(()=>c.enrichRules(dates,rules,{}),/изменились/);assert.equal(dates[0].result.getTime(),0);
 assert.throws(()=>c.decodeRuleFields({result:'2026-01-01T00:00:00.000Z'},[{path:['result'],kind:'date',milliseconds:0,text:'wrong'}]));
 console.log('OK: lossless SQL rule numbers, nested response types and whole-call client staging');
})().catch(e=>{console.error(e);process.exitCode=1});
