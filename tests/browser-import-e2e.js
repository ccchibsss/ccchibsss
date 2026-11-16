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
  const evaluation=page.evaluate(async ({n,stageOnly,preflight,targetIndex})=>{
   if(S._bootError)throw Error(String(S._bootError));
   S.rows=[];S.view=[];S.settings.autoStdDims=false;S.settings.autoOeAnomalyOnImport=false;S.settings.enrichRelatedOnImport=false;
   const related=document.querySelector('#impEnrichRelated');if(related)related.checked=false;
   const stamps={},t=performance.now(),verifiedBaselines=[];const verify=StorageCtl.saveVerifiedMetadata;StorageCtl.saveVerifiedMetadata=async function(rows,...args){const equal=await verify.call(this,rows,...args);verifiedBaselines.push({rows:rows.length,equal});return equal};let diskBuilds=0;const targetRuns=[];const create=BrowserCatalogLookup.create;BrowserCatalogLookup.create=async function(...args){diskBuilds++;const result=await create.apply(this,args);targetRuns.push(result.run);return result};
   const phases=[];
   const instrument=(object,key,label)=>{const original=object[key];object[key]=async function(...args){const t=performance.now();console.info('[E2E] start '+label);try{return await original.apply(this,args)}finally{const phase={phase:label,ms:Math.round(performance.now()-t)};phases.push(phase);console.info('[E2E] end '+JSON.stringify(phase));}};};
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

    const keyPageCounts=[];let verifiedKeys=0;
    if(preflight){
     for(const [id,price] of [[priceSource,true],[oeSource,false]]){
      const describe=row=>({key:normArticle(row[0])+'|'+normArticle(row[1]),brand:normArticle(row[1]),signature:JSON.stringify(['','',price?String(row[2]).trim():''])});
      const run=await BrowserImportSources.prepareKeys(id,uid('preflight'),describe,'browser-million-key-pages');
      keyPageCounts.push(await d.keyPages.where('run').equals(run).count());d.close();await d.open();
      for(let off=0;off<n;off+=4000){const rows=await BrowserImportSources.page(id,off,Math.min(4000,n-off));if((await BrowserImportSources.conflicts(run,rows,describe)).size)throw Error('unexpected preflight conflict');verifiedKeys+=rows.length;}
      await BrowserImportSources.clearRun(run);
     }
    }
    let targetVerified=0,targetKeyPages=0;
    if(targetIndex){
     let targetRows=[];
     for(let off=0;off<n;off+=4000)for(const row of await BrowserImportSources.page(priceSource,off,Math.min(4000,n-off)))targetRows.push({article:row[0],brand:row[1]});
     const lookup=await BrowserCatalogLookup.create(targetRows,priceSource);
     targetKeyPages=await d.keyPages.where('run').equals(lookup.run+':pair').count()+await d.keyPages.where('run').equals(lookup.run+':article').count();
     for(let off=0;off<n;off+=4000){
      const input=await BrowserImportSources.page(priceSource,off,Math.min(4000,n-off)),found=await lookup.batch(input,r=>normArticle(r[0]),r=>normArticle(r[1]));
      for(let i=0;i<input.length;i++){const a=normArticle(input[i][0]),k=a+'|'+normArticle(input[i][1]);if(found.idx.get(k)!==targetRows[off+i]||found.idxArt.get(a)!==targetRows[off+i]||found.duplicatePair.has(k)||found.duplicateArt.has(a))throw Error('target index mismatch at '+(off+i));targetVerified++;}
     }
     await lookup.dispose();targetRows=[];if(await d.keyPages.count())throw Error('temporary paged index leaked');
    }
    return {stageOnly:true,targetVerified,targetKeyPages,preflight,verifiedKeys,keyPageCounts,verifiedRows:n*2,reopened:true,sources:[(await BrowserImportSources.source(priceSource)).total,(await BrowserImportSources.source(oeSource)).total],pageCounts,phases,last:p[0][0],oe:o[0][2],catalogRows:S.rows.length,elapsedMs:Math.round(performance.now()-t)};
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
   for(const run of targetRuns)for(const kind of ['pair','article','oe'])if(await BrowserImportSources.database().keyPages.where('run').equals(run+':'+kind).count())throw Error('paged target index leaked');
   if(await db.applyUndo.count())throw Error('undo backup leaked');
   const registrySizes=['oe','parts','cross','prices'].map(key=>HVC[key].size),registryRefs=['oe','parts','cross','prices'].map(key=>HVC[key]);
   const reloaded=await HVC.load();
   if(S._hvcLoadError||reloaded!==registrySizes[1]||['oe','parts','cross','prices'].some((key,i)=>HVC[key].size!==registrySizes[i]||HVC[key]!==registryRefs[i]))throw Error('HVC reload changed registry contents/identity');
   if(!HVC.byArt.get(HVC.keyOf(S.rows[n-1]))?.has('OE'+(n-1)))throw Error('HVC reload lost last OE link');
   await Import.read({name:'oe.csv'},oeSource);if(S.pending.body.length!==n||Object.keys(S.pending.body).length>202)throw Error('saved mapping preview lost bounds');
   return {hvcReloaded:true,phases,verifiedBaselines,rows:S.rows.length,sources:[(await BrowserImportSources.source(priceSource)).total,(await BrowserImportSources.source(oeSource)).total],last:S.rows[n-1].article,oe:S.rows[n-1].oe_numbers,economicsPending:S._econPending,stamps,heap:performance.memory&&performance.memory.usedJSHeapSize};
  },{n:Number(process.env.E2E_ROWS||1000),stageOnly:process.env.E2E_STAGE_ONLY==='1',preflight:process.env.E2E_PREFLIGHT==='1',targetIndex:process.env.E2E_TARGET_INDEX==='1'});
  const result=await Promise.race([evaluation,new Promise((_,reject)=>{deadline=setTimeout(()=>reject(Error('E2E deadline exceeded; run is incomplete')),Number(process.env.E2E_TIMEOUT_MS||180000))})]);
  if(!result.stageOnly){assert(result.economicsPending);assert(result.verifiedBaselines.some(x=>x.rows===Number(process.env.E2E_ROWS||1000)&&x.equal),'second Apply must verify the unchanged baseline');}assert.equal(errors.length,0,errors.join('\n'));console.log(JSON.stringify(result,null,2));
 }finally{clearTimeout(deadline);if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1});
