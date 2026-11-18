// Real Chromium: transient read abort, atomic rollback retry, manual recovery.
const fs=require('fs'),http=require('http'),assert=require('assert');
const {chromium:pw}=require('playwright-core'),chromium=require('@sparticuz/chromium');
(async()=>{
 const html=fs.readFileSync(__dirname+'/../index.html'),server=http.createServer((q,r)=>{r.setHeader('Content-Type','text/html;charset=utf-8');r.end(html)});await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await pw.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||await chromium.executablePath(),args:chromium.args,headless:true});
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await page.goto('http://127.0.0.1:'+server.address().port+'/#export');
  const ready=()=>page.waitForFunction(()=>S._bootReady||S._bootError,null,{timeout:60000});await ready();
  await page.evaluate(async()=>{
   S.rows=[];S.settings.autoStdDims=false;S.settings.autoOeAnomalyOnImport=false;S.settings.enrichRelatedOnImport=false;
   await Import.read(new File(['Артикул;Бренд;Себестоимость\nA1;B;10\nA2;B;20\n'],'price.csv',{type:'text/csv'}));
   S.pending.map=S.pending.headers.map((src,i)=>({src,field:['article','brand','cost'][i],target:src,enabled:true,type:i===2?'num':'text'}));Import.normalize();Import.render();document.querySelector('#impKey').value='article+brand';await Import.apply();
  });
  async function prepare(cost,mode){await page.evaluate(async({cost,mode})=>{
   let text='Артикул;Бренд;Себестоимость\n';for(let i=0;i<5001;i++)text+='A'+(i%2+1)+';B;'+cost+'\n';
   await Import.read(new File([text],'update.csv',{type:'text/csv'}));
   S.pending.map=S.pending.headers.map((src,i)=>({src,field:['article','brand','cost'][i],target:src,enabled:true,type:i===2?'num':'text'}));Import.normalize();Import.render();document.querySelector('#impKey').value='article+brand';
   window.probe={reads:0,restores:0};sessionStorage.setItem('abortProbe','{}');
   const B=BrowserImportSources,read=B.readConflicts;
   B.readConflicts=async function(...args){
    probe.reads++;sessionStorage.setItem('abortProbe',JSON.stringify(probe));
    if(mode==='key-repair'){
     if(probe.reads===2){const table=this.database().keyPages,page=await table.where('run').equals(args[0]).first();delete page.records[0].conflict;await table.put(page);this.invalidateKeyIndex(args[0]);}
     return read.apply(this,args);
    }
    if(probe.reads>=2&&(mode!=='transient'||probe.reads===2)){
     const d=this.database();return d.transaction('r',d.keyPages,tx=>d.keyPages.limit(1).toArray().then(()=>{tx.abort();throw Object.assign(Error('injected read abort'),{name:'AbortError'})}));
    }
    return read.apply(this,args);
   };
   if(mode==='late-restore'){
    const atomic=BrowserApplyCheckpoint.restoreAtomic;
    BrowserApplyCheckpoint.restoreAtomic=async function(owner){await atomic.call(this,owner);probe.restores++;sessionStorage.setItem('abortProbe',JSON.stringify(probe));if(probe.restores===1)throw Object.assign(Error('late restore abort'),{name:'AbortError'});};
   }else if(mode!=='transient'&&mode!=='key-repair'){
    window.abortRestoreHook=(key,obj,tx)=>{if(mode==='manual'||probe.restores===0){probe.restores++;sessionStorage.setItem('abortProbe',JSON.stringify(probe));tx.abort()}};
    db.products.hook('creating',abortRestoreHook);
   }
  },{cost,mode});}
  // One abort after the first 4000 rows: retry only read; Apply succeeds.
  await prepare(77,'transient');await page.click('#impApply');
  await page.waitForFunction(()=>!document.querySelector('#impApply').disabled&&!document.querySelector('#mImport').classList.contains('on'),null,{timeout:60000});
  assert(await page.evaluate(async()=>probe.reads===3&&S.rows.every(p=>p.cost===77)&&!await db.meta.get(BrowserApplyCheckpoint.KEY)));
  // Reset functions by reload, keeping the real persisted catalog/source DB.
  await page.reload();await ready();
  // Persistent read abort exhausts 3 attempts; first restore aborts after
  // clears begin, second atomic restore succeeds and reloads the app.
  await prepare(88,'rollback');const nav=page.waitForEvent('load');await page.click('#impApply');await nav;await ready();
  assert(await page.evaluate(async()=>{const p=JSON.parse(sessionStorage.getItem('abortProbe'));return p.reads===4&&p.restores===1&&S.rows.every(r=>r.cost===77)&&!await db.meta.get(BrowserApplyCheckpoint.KEY)}));
  // Both reading and all automatic restore attempts abort. Keep backup and
  // block saves, then let the user retry restoration without clearing IDB.
  await prepare(99,'manual');await page.click('#impApply');await page.waitForSelector('#impRestoreActions:not([hidden])',{timeout:60000});
  assert(await page.evaluate(async()=>!S._bootReady&&!!S._bootError&&!!await db.meta.get(BrowserApplyCheckpoint.KEY)&&await db.applyUndo.count()>0&&S.pending.body.length===5001&&await persistNow()===false));
  await page.evaluate(()=>db.products.hook('creating').unsubscribe(abortRestoreHook));
  const restored=page.waitForEvent('load');await page.click('#impRestoreRetry');await restored;await ready();
  assert(await page.evaluate(async()=>S.rows.every(r=>r.cost===77)&&!await db.meta.get(BrowserApplyCheckpoint.KEY)&&await db.applyUndo.count()===0));
  // Malformed source index after one batch is repaired without replaying Apply.
  await prepare(101,'key-repair');await page.click('#impApply');
  await page.waitForFunction(()=>!document.querySelector('#impApply').disabled&&!document.querySelector('#mImport').classList.contains('on'),null,{timeout:60000});
  assert(await page.evaluate(()=>S.rows.every(r=>r.cost===101)&&probe.reads===3));
  await page.reload();await ready();
  // A late abort after COMMITTED rollback is recovered via its durable receipt.
  await prepare(102,'late-restore');const receiptNav=page.waitForEvent('load');await page.click('#impApply');await receiptNav;await ready();
  assert(await page.evaluate(async()=>{const p=JSON.parse(sessionStorage.getItem('abortProbe'));return p.restores===2&&S.rows.every(r=>r.cost===101)&&!await db.meta.get(BrowserApplyCheckpoint.KEY)&&!!await db.meta.get('browserApplyRestoreReceipt');}));
  assert.equal(errors.length,0,errors.join('\n'));
  console.log('OK: real read transaction abort resumes without replaying Apply; persistent read failure + first atomic restore abort recover; exhausted restores preserve backup/block saves; manual restore succeeds');
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1});
