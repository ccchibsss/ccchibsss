const fs=require('fs'),vm=require('vm'),assert=require('assert'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const ctx={S:{rows:[],settings:{}},MarkStatus:{unknown:new Set()}};vm.createContext(ctx);
const a=h.indexOf('  encodeRuleRows('),b=h.indexOf('  async enrichCategoryKinds(',a);
const x=h.indexOf('  async checkMarkStatus(rows)'),y=h.indexOf('  async enrichCategoryTnved',x);
vm.runInContext('this.c={'+h.slice(a,b)+h.slice(x,y)+'};this.rows=[{article:"A",brand:"B",markStatus:new Date(0),markCode:Infinity,markRequired:NaN}];',ctx);
const c=ctx.c;c.processingAvailable=async()=>{};c.processingMode=()=> 'sql';
(async()=>{
 const rows=ctx.rows;ctx.S.rows=rows;
 c._fetch=async(path,opts)=>{const p=JSON.parse(opts.body);assert.equal(p.special_values.length,3);assert(p.special_values.some(e=>e.kind==='date'));return {rows:[{article:'A',brand:'B',fields:{markCompliant:true}}],unknown:['Date status']};};
 await c.checkMarkStatus(rows);assert.equal(rows[0].markCompliant,true);assert(ctx.MarkStatus.unknown.has('Date status'));
 const many=Array.from({length:1001},(_,i)=>({article:String(i),brand:'B'}));ctx.S.rows=many;ctx.MarkStatus.unknown.clear();let calls=0;
 c._fetch=async(path,opts)=>{if(++calls===2)throw Error('offline');return {rows:JSON.parse(opts.body).rows.map(p=>({...p,fields:{markCompliant:false}})),unknown:['pending']};};
 await assert.rejects(()=>c.checkMarkStatus(many),/offline/);assert(many.every(p=>!('markCompliant' in p)));assert.equal(ctx.MarkStatus.unknown.size,0);
 ctx.S.rows=rows;c._fetch=async()=>{rows[0].markStatus.setTime(1);return {rows:[{article:'A',brand:'B',fields:{markCompliant:false}}],unknown:[]};};
 await assert.rejects(()=>c.checkMarkStatus(rows),/изменились/);assert.equal(rows[0].markCompliant,true);
 c._fetch=async()=>({rows:[{article:'A',brand:'B',fields:{name:'overwrite'}}],unknown:[]});
 await assert.rejects(()=>c.checkMarkStatus(rows),/Неверный/);
 console.log('OK: typed mark-status dispatch, whole-call staging and stale Date rejection');
})().catch(e=>{console.error(e);process.exitCode=1});
