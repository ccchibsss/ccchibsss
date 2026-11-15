const fs=require('fs'),vm=require('vm'),assert=require('assert'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
let mode='sql',writes=0,upload,revision='',fail=false;
const ctx={S:{rows:[],settings:{},catalogVersion:1,_bootReady:true},_persistDirty:true,_persistPending:0,
 lsGet:()=>mode,lsSet:(k,v)=>{mode=v},productVolumeIsExplicit:p=>p._volumeExplicit===true,
 codeFieldsToStr:()=>{},normalizeFormatSettings:()=>{},HVC:{load:async()=>{}},
 db:{meta:{get:async()=>null}},Toast:{warn:()=>{},err:()=>{},info:()=>{}},StorageCtl:{catalogToken:()=>'',withWriteLock:()=>{throw Error('SQL must not acquire IndexedDB lock')}},
 askConfirm:async()=>true};
vm.createContext(ctx);
const a=h.indexOf('  async saveSqlCatalog()'),b=h.indexOf('  async enrichBrowser(',a),x=h.indexOf('  encodeRuleRows('),y=h.indexOf('  async enrichRules(',x);
vm.runInContext('this.P={'+h.slice(a,b)+h.slice(x,y)+'};this.S.rows=[{article:"A",brand:"B",custom:{x:42},flag:Infinity,date:new Date(0),_categoryNameExplicit:true}];',ctx);
const P=ctx.P;
P._fetch=async(path,opts)=>{
 if(fail)throw Error('offline');
 if(path.startsWith('/app/catalog?')){const part=Number(new URL('http://test'+path).searchParams.get('part'));return {exists:!!revision,revision,total:upload?.total||0,metadata:upload?.metadata||{},chunk:upload?.chunks[part]||null};}
 const p=JSON.parse(opts.body);writes++;
 if(p.action==='begin'){upload={...p,chunks:[]};return {token:'t'};}
 if(p.action==='chunk'){upload.chunks[p.part]=p.chunk;return {};}
 if(p.action==='commit'){revision='r1';return {revision};}
 throw Error('unknown request');
};
(async()=>{
 await P.saveSqlCatalog();assert.equal(writes,3);
 assert.equal(ctx.S._sqlCatalogRevision,'r1');
 const restored=await P.readSqlCatalog();assert.equal(restored.rows[0].flag,Infinity);assert.equal(restored.rows[0].date.getTime(),0);assert.equal(restored.rows[0].custom.x,42);assert(restored.rows[0]._categoryNameExplicit);
 ctx.S.rows=[];await P.loadSqlCatalog();assert.equal(ctx.S.rows.length,1);
 fail=true;await assert.rejects(()=>P.saveSqlCatalog(),/offline/);assert.equal(mode,'sql');
 // Execute the actual persistence entry: neither the local writer nor its lock
 // may be touched when a selected SQL engine is offline.
 Object.assign(ctx,{PyEngine:P,_persistQueue:Promise.resolve(),_cancelPersistSoon:null});
 const start=h.indexOf('function persistNow(changedList)'),end=h.indexOf('async function storageFreeInfo',start);
 vm.runInContext(h.slice(start,end),ctx);
 await assert.rejects(()=>ctx.persistNow(),/offline/);
 assert(h.includes("if(!legacySqlMigration&&PyEngine.processingMode()==='sql')return PyEngine.loadSqlCatalog();"));
 assert(h.includes("if(PyEngine.processingMode()==='sql')return Import.pick();"));
 ctx._persistPending=0;ctx.S._bootReady=true;ctx.S._bootError=false;
 ctx.persistEconPending=()=>{};P.renderProcessingMode=()=>{};
 ctx.StorageCtl.withWriteLock=fn=>fn();
 ctx._persistNowImpl=async(list,force)=>{assert.equal(mode,'sql');assert.equal(force,true);return false;};
 await P.toggleProcessingMode();assert.equal(mode,'sql'); // failed target write
 ctx._persistNowImpl=async()=>true;
 await P.toggleProcessingMode();assert.equal(mode,'browser');
 P.health=async()=>true;P.verifyAuth=async()=> 'ok';
 await P.toggleProcessingMode();assert.equal(mode,'browser'); // SQL offline: no switch
 fail=false;await P.toggleProcessingMode();assert.equal(mode,'sql');
 // Bounded parallel upload: five parts, at most three in flight; commit
 // only after ALL workers have finished, even when one request fails.
 ctx.S.rows=Array.from({length:4501},(_,i)=>({article:String(i),brand:'B'}));
 let active=0,peak=0,commits=0,parts=[],breakPart=-1;
 P._fetch=async(path,opts)=>{
  const p=JSON.parse(opts.body);
  if(p.action==='begin')return {token:'parallel'};
  if(p.action==='commit'){assert.equal(active,0);commits++;return {revision:'parallel'};}
  active++;peak=Math.max(peak,active);
  try {await new Promise(r=>setTimeout(r,p.part%2?2:5));if(p.part===breakPart)throw Error('chunk failure');parts.push(p.part);return {};}
  finally{active--;}
 };
 await P.saveSqlCatalog();assert.equal(peak,3);assert.equal(commits,1);assert.deepEqual(parts.sort((a,b)=>a-b),[0,1,2,3,4]);
 parts=[];breakPart=1;commits=0;
 await assert.rejects(()=>P.saveSqlCatalog(),/chunk failure/);assert.equal(active,0);assert.equal(commits,0);
 console.log('OK: SQLite-only persistence, typed reload and no IndexedDB fallback');
})().catch(e=>{console.error(e);process.exitCode=1});
