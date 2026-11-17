// Real first-price Apply, saved catalog reopen and restored calculation route.
const fs=require('fs'),os=require('os'),path=require('path'),assert=require('assert'),{spawn}=require('child_process');
const {chromium:pw}=require('playwright-core'),ch=require('@sparticuz/chromium');
(async()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'uc-first-price-'));let child,browser;
 try{
  child=spawn('python',['-u','-c',`import sys,pathlib\nsys.path.insert(0,'engine')\nimport uc_engine as E\nE.DATA=pathlib.Path(sys.argv[1]);E.DB_PATH=E.DATA/'catalog.db';E.TOKEN_PATH=E.DATA/'token.txt';E._TOKEN_CACHE='test-only-token'\ns=E.ThreadingHTTPServer(('127.0.0.1',0),E.Handler)\nprint(s.server_port,flush=True)\ns.serve_forever()`,tmp],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','pipe']});
  let stderr='';child.stderr.on('data',d=>stderr+=d);
  const port=await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(Error('startup timeout '+stderr)),30000);child.once('exit',code=>{clearTimeout(t);reject(Error('engine exit '+code+' '+stderr))});child.stdout.once('data',d=>{clearTimeout(t);resolve(Number(String(d).trim().split('\n')[0]))});});
  const results=[];
  for(const mode of ['browser','sql']){
   browser=await pw.launch({executablePath:await ch.executablePath(),args:ch.args,headless:true});
   const context=await browser.newContext(),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(mode=>{localStorage.setItem('uc.processingMode',mode);document.addEventListener('DOMContentLoaded',()=>{if(mode==='sql')S.settings.pyEngineUrl=location.origin;},{once:true});},mode);
   await page.route('**/*',async route=>{
    const url=new URL(route.request().url());if(url.hostname!=='127.0.0.1')return route.abort();
    if(route.request().isNavigationRequest()&&url.pathname==='/'){
     const response=await route.fetch();let html=await response.text();const marker='  UI.boot().then(() => {';assert(html.includes(marker));
     const spies=`window.__calls={pipeline:0,economics:0,hvc:0,ozon:0,recalc:0};
      const wrap=(o,k,label)=>{const fn=o[k];o[k]=function(...args){window.__calls[label]++;return fn.apply(this,args)}};
      const pipelineBefore=runPipeline;runPipeline=function(...args){window.__calls.pipeline++;return pipelineBefore(...args)};
      const economyBefore=ensureEconomics;ensureEconomics=function(...args){window.__calls.economics++;return economyBefore(...args)};
      wrap(HVC,'enrichAsync','hvc');wrap(PyEngine,'enrichOzonPreferred','ozon');wrap(PyEngine,'recalcAndApply','recalc');
     `;
     return route.fulfill({response,body:html.replace(marker,spies+'\n'+marker)});
    }
    return route.continue();
   });
   const url='http://127.0.0.1:'+port+'/#data',n=Number(process.env.E2E_ROWS||1200);
   await page.goto(url);await page.waitForFunction(()=>S._bootReady||S._bootError,null,{timeout:90000});
   const result=await page.evaluate(async n=>{
    if(S._bootError||S.rows.length)throw Error('expected empty ready catalog');
    const start=performance.now();
    const csv='article;brand;cost;name;oe_numbers\n'+Array.from({length:n},(_,i)=>['A'+i,'B','123.45','Фильтр '+i,'OE'+i].join(';')).join('\n');
    await Import.read(new File([csv],'price.csv',{type:'text/csv'}));
    S.pending.map=['article','brand','cost','name','oe_numbers'].map(field=>({src:field,field,target:field,enabled:true,type:field==='cost'?'num':'text'}));
    Import.normalize();Import.render();document.querySelector('#impKey').value='article+brand';await Import.apply();
    UI.go('data');await new Promise(r=>setTimeout(r,100));
    if(S.rows.length!==n||!S._econPending||S._cacheWriteError||S._bootError)throw Error('first price state invalid');
    if(Object.values(window.__calls).some(Boolean))throw Error('first price triggered work '+JSON.stringify(window.__calls));
    if(HVC.parts.size)throw Error('first price became donor registry');
    return{importMs:Math.round(performance.now()-start),calls:{...window.__calls},rows:n};
   },n);
   for(const hash of ['#data','#unit','#dashboard']){
    const start=Date.now();await page.evaluate(hash=>history.replaceState(null,'',hash),hash);await page.reload();await page.waitForFunction(()=>S._bootReady||S._bootError,null,{timeout:90000});
    await page.waitForTimeout(150);
    const reopened=await page.evaluate(()=>({error:String(S._bootError||''),rows:S.rows.length,pending:S._econPending,view:UI.current(),calls:window.__calls,first:S.rows[0]&&{article:S.rows[0].article,cost:S.rows[0].cost,name:S.rows[0].name,ozon_type:S.rows[0].ozon_type||''}}));
    assert.equal(reopened.error,'');assert.equal(reopened.rows,n);assert(reopened.pending);assert.equal(reopened.view,'data');assert(Object.values(reopened.calls).every(v=>v===0),JSON.stringify(reopened));assert.deepEqual(reopened.first,{article:'A0',cost:123.45,name:'Фильтр 0',ozon_type:''});
    result[hash.slice(1)+'ReopenMs']=Date.now()-start;
   }
   // Explicit calculation navigation still requests economics (stub only here).
   await page.evaluate(async()=>{let requested=0;ensureEconomics=async()=>{requested++;return false};UI.go('unit');await new Promise(r=>setTimeout(r,100));if(requested!==1)throw Error('explicit economics navigation disabled');});
   assert.equal(errors.length,0,errors.join('\n'));results.push({mode,...result});await browser.close();browser=null;
  }
  console.log(JSON.stringify(results));
 }finally{if(browser)await browser.close();if(child){child.kill('SIGTERM');await new Promise(r=>{if(child.exitCode!==null)return r();child.once('exit',r);setTimeout(()=>{child.kill('SIGKILL');r()},3000).unref()});}fs.rmSync(tmp,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1});
