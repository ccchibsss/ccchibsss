const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(__dirname+'/../index.html','utf8');
const ctx={TextEncoder,console,S:{rows:[],settings:{}},num:x=>Number(x)||0,economicScope:()=> 'OZON'};
vm.createContext(ctx);vm.runInContext(html.slice(html.indexOf('const SqlMemory = {'),html.indexOf('const PyEngine = {'))+';this.M=SqlMemory;',ctx);
for(const mutate of [r=>r.push({}),r=>r.pop(),r=>{r[0].custom.text+='!'},r=>{delete r[0]},r=>r.reverse()]){
 const rows=[{article:'A',custom:{text:'0'.repeat(100000)}},{article:'B'}],guard=ctx.M.rowsGuard(rows);
 assert(guard.matches(rows));assert(!guard.matches(rows.slice()));mutate(rows);assert(!guard.matches(rows));
}
const start=html.indexOf('async function scenarioProfit(');
// Extract balanced function via the following top-level definition boundary.
const body=html.slice(start,html.indexOf('\n}',start)+2);
vm.runInContext(body+';this.scenario=scenarioProfit;',ctx);
let change=()=>{};
ctx.PyEngine={processingMode:()=> 'sql',processingAvailable:async()=>{},_settingsSnapshot:()=>({}),_syncCatalog:async()=>{},_fetch:async()=>{change();return{base:100,scen:110}}};
(async()=>{
 ctx.S.rows=Array.from({length:1001},(_,i)=>({article:'A'+i,brand:'B',price:12,sales:2,custom:{text:'Wide '.repeat(1000)}}));
 assert.equal((await ctx.scenario(1,1,0,0)).scen,110);
 change=()=>{ctx.S.rows[1000].custom.text+='edited'};await assert.rejects(()=>ctx.scenario(1,1,0,0),/Данные изменились/);
 change=()=>{ctx.S.rows.push({article:'NEW'})};await assert.rejects(()=>ctx.scenario(1,1,0,0),/Данные изменились/);
 change=()=>{ctx.S.settings.manual=1};await assert.rejects(()=>ctx.scenario(1,1,0,0),/Данные изменились/);
 const wa=html.indexOf('  async run() {',html.indexOf('const WhatIf = {')),wb=html.indexOf('  renderDelta() {',wa);
 assert(wa>0&&wb>wa);vm.runInContext('this.WhatIf={'+html.slice(wa,wb)+'};',ctx);
 ctx.S.settings={};ctx.S.tariffs={list:[]};ctx.S.cats=[];
 ctx.WhatIf.shadow={settings:{_wiMarket:'OZON',_wi:{tax:null,markup:null,volDiv:null,pack:null,unred:null}}};
 ctx.WhatIf.renderDelta=()=>{};ctx.WhatIf.renderChart=()=>{};
 ctx.forecastNoBuyRateInfo=()=>({rate:1});ctx.tariffFor=()=>({});
 ctx.Uint32Array=class extends Uint32Array{constructor(n){assert.notEqual(n,ctx.S.rows.length*3,'SQL allocated browser row-mark buffer');super(n)}};
 change=()=>{};assert.equal((await ctx.WhatIf.run()).scen,110);
 change=()=>{ctx.S.rows[0].custom.text+='changed'};await assert.rejects(()=>ctx.WhatIf.run(),/Данные изменились/);
 console.log('OK: bounded per-row guards reject nested edits, removals, sparse deletion, reorder and replacement; actual SQL scenario preserves conflict checks');
})().catch(e=>{console.error(e);process.exitCode=1});
