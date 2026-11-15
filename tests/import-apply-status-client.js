const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(__dirname+'/../index.html','utf8');
const start=html.indexOf("  on('#impApply', 'onclick', async (e) => {"),end=html.indexOf("  on('#expRun'",start);
assert(start>0&&end>start);assert(html.includes('id="impApplyStatus" role="status"'));
// Diagnostic is a sibling of the scrollable body, directly before the footer.
assert(/<\/div>\s*<div id="impApplyStatus"[^>]*><\/div>\s*<div class="mfoot"><span class="hint mono" id="impMeta"/.test(html));
assert(html.includes('#mImport .mbody{min-height:0}'));
assert(html.includes('#mImport .mhead,#mImport .mfoot{flex-shrink:0}'));
let run,apply,toasts=0,open=true;const logs=[];const button={disabled:false},status={hidden:true,textContent:''};
const ctx={console:{error(){},info(...args){logs.push(args)}},S:{pending:{file:"cross.xlsx",body:[{}]}},$:s=>({'#impApply':button,'#impApplyStatus':status,'#mImport':{classList:{contains:()=>open}}}[s]),Import:{apply:()=>apply()},storageErrorText:e=>String(e?.message||e),Toast:{err(){toasts++}},on:(s,event,fn)=>run=fn};
vm.createContext(ctx);vm.runInContext(html.slice(start,end),ctx);
(async()=>{
 let reject,calls=0;apply=()=>{calls++;return new Promise((_,r)=>reject=r)};
 const pending=run();assert(button.disabled);assert(!status.hidden);await run();assert.equal(calls,1);assert.equal(logs.length,1);assert.equal(logs[0][1].file,'cross.xlsx');
 reject(Object.assign(new Error('SQL connection reset'),{_ucShown:true}));await pending;
 assert(!button.disabled);assert(status.textContent.includes('SQL connection reset'));assert.equal(toasts,0);
 apply=async()=>{throw new Error('<unsafe>')};await run();assert(status.textContent.includes('<unsafe>'));assert.equal(toasts,1);
 apply=async()=>{};await run();assert(status.textContent.includes('сопоставление'));
 open=false;await run();assert.equal(status.textContent,'');assert(status.hidden);assert(!button.disabled);assert(logs.some(x=>x[0].includes('мастер закрыт')));
 console.log('OK: import awaits failures, retains visible diagnostic, prevents duplicate clicks and restores button');
})().catch(e=>{console.error(e);process.exitCode=1});
