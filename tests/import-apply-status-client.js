const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(__dirname+'/../index.html','utf8');
const start=html.indexOf("  on('#impApply', 'onclick', async (e) => {"),end=html.indexOf("  on('#expRun'",start);
assert(start>0&&end>start);assert(html.includes('id="impApplyStatus" role="status"'));
let run,apply,toasts=0,open=true;const button={disabled:false},status={hidden:true,textContent:''};
const ctx={console:{error(){}},$:s=>({'#impApply':button,'#impApplyStatus':status,'#mImport':{classList:{contains:()=>open}}}[s]),Import:{apply:()=>apply()},storageErrorText:e=>String(e?.message||e),Toast:{err(){toasts++}},on:(s,event,fn)=>run=fn};
vm.createContext(ctx);vm.runInContext(html.slice(start,end),ctx);
(async()=>{
 let reject,calls=0;apply=()=>{calls++;return new Promise((_,r)=>reject=r)};
 const pending=run();assert(button.disabled);assert(!status.hidden);await run();assert.equal(calls,1);
 reject(Object.assign(new Error('SQL connection reset'),{_ucShown:true}));await pending;
 assert(!button.disabled);assert(status.textContent.includes('SQL connection reset'));assert.equal(toasts,0);
 apply=async()=>{throw new Error('<unsafe>')};await run();assert(status.textContent.includes('<unsafe>'));assert.equal(toasts,1);
 apply=async()=>{};await run();assert(status.textContent.includes('сопоставление'));
 open=false;await run();assert.equal(status.textContent,'');assert(!button.disabled);
 console.log('OK: import awaits failures, retains visible diagnostic, prevents duplicate clicks and restores button');
})().catch(e=>{console.error(e);process.exitCode=1});
