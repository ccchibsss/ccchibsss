// Optional real Chromium test. Dependencies stay outside the tracked tree:
// npm install --prefix .arena/browser-tests playwright-core@1.58.2 @sparticuz/chromium@143.0.4 --no-save
// NODE_PATH=.arena/browser-tests/node_modules node tests/browser-import-e2e.js
const fs=require('fs'),http=require('http'),assert=require('assert');
const {chromium:playwright}=require('playwright-core'),chromium=require('@sparticuz/chromium');
const html=fs.readFileSync(__dirname+'/../index.html');
(async()=>{
 const server=http.createServer((req,res)=>{res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html)});await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser,deadline;
 try{
  browser=await playwright.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||await chromium.executablePath(),args:chromium.args,headless:true});
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')console.error('browser:',m.text());else if(process.env.E2E_PROGRESS&&m.type()==='info')console.log('browser:',m.text())});
  await page.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
  await page.goto('http://127.0.0.1:'+server.address().port);await page.waitForFunction(()=>S._bootReady||S._bootError,{},{timeout:60000});
  const evaluation=page.evaluate(async ({n,stageOnly})=>{
   if(S._bootError)throw Error(String(S._bootError));
   S.rows=[];S.view=[];S.settings.autoStdDims=false;S.settings.autoOeAnomalyOnImport=false;S.settings.enrichRelatedOnImport=false;
   const related=document.querySelector('#impEnrichRelated');if(related)related.checked=false;
   const stamps={},t=performance.now(),verifiedBaselines=[];const verify=StorageCtl.saveVerifiedMetadata;StorageCtl.saveVerifiedMetadata=async function(rows,...args){const equal=await verify.call(this,rows,...args);verifiedBaselines.push({rows:rows.length,equal});return equal};let diskBuilds=0;const create=BrowserCatalogLookup.create;BrowserCatalogLookup.create=async function(...args){diskBuilds++;return create.apply(this,args)};
   const phases=[];
   const instrument=(object,key,label)=>{const original=object[key];object[key]=async function(...args){const t=performance.now();try{return await original.apply(this,args)}finally{phases.push({phase:label,ms:Math.round(performance.now()-t)});}};};
   instrument(BrowserApplyCheckpoint,'begin','checkpoint');instrument(BrowserApplyCheckpoint,'commit','checkpoint-commit');
   instrument(BrowserCatalogLookup,'create','target-index');instrument(BrowserImportSources,'prepareKeys','source-index');
   instrument(BrowserImportSources,'stage','source-stage');instrument(HVC,'save','HVC-save');instrument(StorageCtl,'saveVerifiedMetadata','baseline-verify');
   let parts=['Артикул;Бренд;Себестоимость\n'];for(let i=0;i<n;i++)parts.push('A'+String(i).padStart(8,'0')+';Brand;12.5\n');
   await Import.read(new File(parts,'price.csv',{type:'text/csv'}));parts=null;
   const priceSource=S.pending.sourceId;
   if(stageOnly){
    parts=['Артикул;Бренд;OE-номера\n'];for(let i=0;i<n;i++)parts.push('A'+String(i).padStart(8,'0')+';Brand;OE'+i+'\n');
    await Import.read(new File(parts,'oe.csv',{type:'text/csv'}));parts=null;const oeSource=S.pending.sourceId;
    const p=await BrowserImportSources.page(priceSource,n-1,1),o=await BrowserImportSources.page(oeSource,n-1,1);
    if(p[0][0]!=='A'+String(n-1).padStart(8,'0')||o[0][2]!=='OE'+(n-1))throw Error('staging tail lost');
    if(S.rows.length)throw Error('staging must not mutate catalog');
    const d=BrowserImportSources.database(),pageCounts=[await d.rowPages.where('source').equals(priceSource).count(),await d.rowPages.where('source').equals(oeSource).count()];
    if(await d.rows.count())throw Error('new sources still use row-per-record format');
    if(n>=1000&&pageCounts.some(x=>x>n/10))throw Error('packed storage regression');
    d.close();await d.open();
    for(let off=0;off<n;off+=4000){
     const count=Math.min(4000,n-off),price=await BrowserImportSources.page(priceSource,off,count),oes=await BrowserImportSources.page(oeSource,off,count);
     for(let i=0;i<count;i++){const pos=off+i,article='A'+String(pos).padStart(8,'0');if(price[i][0]!==article||price[i][1]!=='Brand'||price[i][2]!=='12.5'||oes[i][0]!==article||oes[i][1]!=='Brand'||oes[i][2]!=='OE'+pos)throw Error('staged row mismatch at '+pos);}
    }
    await Import.read({name:'price.csv'},priceSource);if(S.pending.sourceId!==priceSource||S.pending.body.length!==n||Object.keys(S.pending.body).length>202)throw Error('staged source reopen failed');

    return {stageOnly:true,verifiedRows:n*2,reopened:true,sources:[(await BrowserImportSources.source(priceSource)).total,(await BrowserImportSources.source(oeSource)).total],pageCounts,phases,last:p[0][0],oe:o[0][2],catalogRows:S.rows.length,elapsedMs:Math.round(performance.now()-t)};
   }

   const mapping=fields=>{S.pending.map=S.pending.headers.map((src,i)=>({src,field:fields[i],target:STD.find(x=>x.k===fields[i]).n,enabled:true,type:fields[i]==='cost'?'num':'text'}));Import.normalize();document.querySelector('#impMode').value='upsert';document.querySelector('#impKey').value='article+brand';};
   mapping(['article','brand','cost']);await Import.apply();stamps.priceMs=Math.round(performance.now()-t);
   if(S.rows.length!==n)throw Error('price size '+S.rows.length);
   if(HVC.parts.size)throw Error('first price unexpectedly enriched HVC');
   const t2=performance.now();parts=['Артикул;Бренд;OE-номера\n'];for(let i=0;i<n;i++)parts.push('A'+String(i).padStart(8,'0')+';Brand;OE'+i+'\n');
   await Import.read(new File(parts,'oe.csv',{type:'text/csv'}));parts=null;const oeSource=S.pending.sourceId;mapping(['article','brand','oe_numbers']);await Import.apply();stamps.oeMs=Math.round(performance.now()-t2);
   if(S.rows.length!==n||!S.rows[n-1].oe_numbers.includes('OE'+(n-1)))throw Error('tail lost');
   if(diskBuilds!==1)throw Error('expected exactly one disk target index build, got '+diskBuilds);
   if(await db.meta.get(BrowserApplyCheckpoint.KEY))throw Error('undo marker remains');
   if(await BrowserImportSources.database().catalogKeys.count())throw Error('target index leaked');
   if(await db.applyUndo.count())throw Error('undo backup leaked');
   await Import.read({name:'oe.csv'},oeSource);if(S.pending.body.length!==n||Object.keys(S.pending.body).length>202)throw Error('saved mapping preview lost bounds');
   return {phases,verifiedBaselines,rows:S.rows.length,sources:[(await BrowserImportSources.source(priceSource)).total,(await BrowserImportSources.source(oeSource)).total],last:S.rows[n-1].article,oe:S.rows[n-1].oe_numbers,economicsPending:S._econPending,stamps,heap:performance.memory&&performance.memory.usedJSHeapSize};
  },{n:Number(process.env.E2E_ROWS||1000),stageOnly:process.env.E2E_STAGE_ONLY==='1'});
  const result=await Promise.race([evaluation,new Promise((_,reject)=>{deadline=setTimeout(()=>reject(Error('E2E deadline exceeded; run is incomplete')),Number(process.env.E2E_TIMEOUT_MS||180000))})]);
  if(!result.stageOnly){assert(result.economicsPending);assert(result.verifiedBaselines.some(x=>x.rows===Number(process.env.E2E_ROWS||1000)&&x.equal),'second Apply must verify the unchanged baseline');}assert.equal(errors.length,0,errors.join('\n'));console.log(JSON.stringify(result,null,2));
 }finally{clearTimeout(deadline);if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1});
