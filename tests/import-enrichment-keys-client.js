// Same unambiguous OE fallback for in-memory (SQL/legacy) and paged browser lookup.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(__dirname+'/../index.html','utf8');
const a={article:'A',brand:'B',oe_numbers:'OE1;SAME;ALIAS'},b={article:'C',brand:'D',oe_numbers:'OE2;SAME'};
const ctx={S:{rows:[a,b]},HVC:{normalizeKey:x=>String(x).trim().toUpperCase()},codeList:x=>String(x||'').split(';').map(x=>x.trim()).filter(Boolean),mergeCodeLists:(a,b)=>[a,b].filter(Boolean).join(';'),catalogLookup:null,oeMaps:[{col:0}],oeIdx:null,AMBIG:{},inputBatch:[]};
vm.createContext(ctx);
const start=html.indexOf('      const findByOe = async r => {'),end=html.indexOf('\n      };',start)+9;
vm.runInContext(html.slice(start,end)+';this.match=findByOe;',ctx);
const ma=html.indexOf('  findOe(row,maps) {'),mb=html.indexOf('  async related(',ma);
vm.runInContext('this.lookup={'+html.slice(ma,mb)+'};',ctx);
ctx.lookup.rows=[a,b];ctx.lookup._oeHits=new Map([['OE1',{pos:0}],['ALIAS',{pos:0}],['OE2',{pos:1}],['SAME',{pos:0,duplicate:true}]]);
(async()=>{
 for(const [input,expected] of [['OE1',a],['UNKNOWN;OE2',b],['ALIAS;OE1',a],['OE1;OE2',null],['SAME',null],['OE1;SAME',null],['UNKNOWN',null],['',null]]){
  assert.strictEqual(await ctx.match([input]),expected,input+' in-memory');
  assert.strictEqual(ctx.lookup.findOe([input],[{col:0}]),expected,input+' paged');
 }
 ctx.catalogLookup={ensureOe:async()=>{},oeBatch:async()=>{},findOe:(row,maps)=>ctx.lookup.findOe(row,maps)};
 assert.strictEqual(await ctx.match(['OE2']),b);
 console.log('OK: SKU/OE enrichment uses one consistent target across all supplied OE codes, never first arbitrary match');
})().catch(e=>{console.error(e);process.exitCode=1});
