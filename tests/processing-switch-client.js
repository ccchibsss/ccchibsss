const fs=require('fs'),vm=require('vm'),assert=require('assert'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
let mode='browser';const input={checked:false,disabled:false},status={textContent:''};
const ctx={lsGet:()=>mode,$:id=>id==='#btnProcessingMode'?input:status};vm.createContext(ctx);
const a=h.indexOf('  processingMode() {',h.indexOf('const PyEngine')),b=h.indexOf('  async toggleProcessingMode()',a);
vm.runInContext('this.P={'+h.slice(a,b)+'};',ctx);
(async()=>{
 const P=ctx.P;P.renderProcessingMode();assert.equal(input.checked,false);
 let finish;P.toggleProcessingMode=async()=>{assert.equal(input.checked,false);assert(input.disabled);await new Promise(r=>finish=r);mode='sql';};
 input.checked=true;const switching=P.changeProcessingMode(input);assert(!input.checked);assert(input.disabled);finish();await switching;
 assert(input.checked);assert(!input.disabled);assert(status.textContent.includes('SQLite'));
 P.toggleProcessingMode=async()=>{};input.checked=false;await P.changeProcessingMode(input);assert(input.checked);assert(!input.disabled);
 P.toggleProcessingMode=async()=>{throw Error('offline')};input.checked=false;
 await assert.rejects(()=>P.changeProcessingMode(input),/offline/);assert(input.checked);assert(!input.disabled);
 assert(/<input[^>]+role="switch"[^>]+id="btnProcessingMode"/.test(h));
 assert(h.includes('_mode.onchange = () => PyEngine.changeProcessingMode(_mode)'));
 for(const id of ['autoCategoryByName','impEnrichOnly','impLightMode','enAutoStdDims','plOptUpdatePrice']){
  assert(new RegExp('<input[^>]+role="switch"[^>]+id="'+id+'"').test(h));
 }
 for(const id of ['stdDimsSelectAll','ozWriteConsent','chkAllOrders']){
  const tag=h.match(new RegExp('<input[^>]+id="'+id+'"[^>]*>'))[0];assert(!tag.includes('uc-switch'));
 }
 assert(/<button[^>]+id="btnDiskImport"/.test(h));
 console.log('OK: accessible settings switches, pending state and cancel/error rollback');
})().catch(e=>{console.error(e);process.exitCode=1});
