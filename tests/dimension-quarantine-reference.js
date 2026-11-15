const fs=require('fs'),vm=require('vm'),h=fs.readFileSync(__dirname+'/../index.html','utf8'),input=JSON.parse(fs.readFileSync(0,'utf8'));
const ctx={PyEngine:{processingMode:()=> 'browser'},_POW10:{},nowISO:()=> '2026-11-08T00:00:00Z'};vm.createContext(ctx);
const obj=n=>h.match(new RegExp('const '+n+' = \\{[\\s\\S]*?\\n\\};'))[0];
const fn=n=>{const a=h.indexOf('function '+n+'(');return h.slice(a,h.indexOf('\n}',a)+2)};
const val=n=>{const a=h.indexOf('const '+n+' = ');return h.slice(a,h.indexOf('\n};',a)+3)};
vm.runInContext(val('num')+'\n'+val('round')+'\n'+fn('productVolumeIsExplicit')+'\n'+fn('validCanonicalOvhNumber')+'\n'+obj('AnomalyDetector')+'\nglobalThis.A=AnomalyDetector;',ctx);
ctx._normArticleCache=new Map();ctx.S={settings:{oeDelimiter:input.oe_mode||'auto'}};
vm.runInContext(val('normArticle')+'\n'+obj('OE_DELIMITERS')+'\n'+['oeMode','splitCodeValues','codeList'].map(fn).join('\n')+'\n'+obj('AnomalyOE'),ctx);
ctx.A.limits=input.limits;
if(input.operation==='search' || input.operation==='oeApply') {
  vm.runInContext(obj('DimPolicy')+';globalThis.O=AnomalyOE;',ctx);
  ctx.S.rows=input.rows;ctx.S.catalogVersion=1;
  ctx.HVC={ozonRevision:1,parts:new Map(input.reference.parts||[]),oe:new Map(input.reference.oe||[]),
    byOe:new Map((input.reference.byOe||[]).map(([k,v])=>[k,new Set(v)])),cross:new Map(input.reference.cross||[])};
  ctx.STD=Object.entries(input.labels||{}).map(([k,n])=>({k,n}));
  ctx.A.found=input.targets.map(i=>({p:input.rows[i],_sel:true}));
  ctx.O.render=()=>{};if(input.operation==='search')ctx.O.apply=async()=>({changed:0});
  ctx.A.save=()=>{};ctx.A.renderLog=()=>{};ctx.A.log=[];ctx.confirm=()=>true;ctx.runPipeline=async()=>{};ctx.StorageCtl={refresh:()=>{}};
  ctx.fmt=(n,d=0)=>Number(n).toLocaleString('ru-RU',{minimumFractionDigits:d,maximumFractionDigits:d});
  ctx.Toast={info:()=>{},warn:()=>{}};ctx.withProgress=async(a,b,f)=>f(()=>{});
  (async()=>{await ctx.O.find({automatic:input.automatic===true});
    if(input.operation==='oeApply'){if(!input.automatic){for(const x of ctx.O.preview)if(x.choice)x.checked=true;await ctx.O.apply({});}process.stdout.write(JSON.stringify({rows:ctx.S.rows,log:ctx.A.log}));return;}
    const result=ctx.O.preview.map(x=>{const c=x.choice;let choice=null;if(c){choice={};for(const [k,v] of Object.entries(c)){if(['ref','evidence','owner'].includes(k))continue;choice[k]=k==='matchedCodes'?[...v]:v;}if(c.kind==='row')choice.donorIndex=input.rows.indexOf(c.ref);}
      return {targetIndex:input.rows.indexOf(x.p),signature:x.signature,codes:x.codes,status:x.status,choice,checked:false,hasRegistry:x.hasRegistry,link:x.link};});
    process.stdout.write(JSON.stringify(result));})().catch(e=>{console.error(e);process.exitCode=1;});
} else if(input.operation==='evidence') {
  vm.runInContext('globalThis.O=AnomalyOE;',ctx);
  process.stdout.write(JSON.stringify(input.rows.map(p=>({evidence:ctx.O.autoEvidence(p),codes:ctx.O.codes(p,false),direct:ctx.O.codes(p,true),
    tuple:ctx.O.tuple(p),tupleKey:ctx.O.tupleKey(ctx.O.tuple(p)),signature:ctx.O.targetSig(p),issueFree:ctx.O.issueFree(p,input.tuple)}))));
} else if(input.operation==='confirm' || input.operation==='fix') {
  Object.assign(ctx,{PyEngine:{processingMode:()=> 'browser'},fmt:v=>String(v),confirm:()=>!!input.approved,
    computeEconomics:()=>{},bumpVersion:()=>{},applyFilter:()=>{},persistNow:async()=>{},
    Table:{paint:()=>{}},Dash:{render:()=>{}},UE:{render:()=>{}},Toast:{warn:()=>{},ok:()=>{},info:()=>{}},runPipeline:async()=>{}});
  ctx.A.save=()=>{};ctx.A.finishQuarantine=()=>{};ctx.A.renderLog=()=>{};ctx.STD=Object.entries(input.labels||{}).map(([k,n])=>({k,n}));
  (async()=>{const results=[];for(let i=0;i<input.rows.length;i++){const p=input.rows[i];ctx.A.log=[];if(input.operation==='fix'){ctx.S.rows=[p];const f=ctx.A.entry(p);f.signature=input.signatures[i];f._sel=true;ctx.A.found=[f];await ctx.A.applyFix(true);}else await ctx.A.confirm(p);results.push({row:p,log:ctx.A.log});}process.stdout.write(JSON.stringify(results));})().catch(e=>{console.error(e);process.exitCode=1;});
} else process.stdout.write(JSON.stringify(input.rows.map(p=>{ctx.A.quarantineRow(p);return p;})));
