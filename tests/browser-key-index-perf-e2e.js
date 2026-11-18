// Optional real Chromium randomized-input performance/parity probe.
const fs=require('fs'),http=require('http'),assert=require('assert');
const {chromium:pw}=require('playwright-core'),chromium=require('@sparticuz/chromium');
(async()=>{
 const html=fs.readFileSync(process.env.E2E_HTML||__dirname+'/../index.html');
 const server=http.createServer((req,res)=>{res.setHeader('Content-Type','text/html;charset=utf-8');res.end(html)});await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await pw.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||await chromium.executablePath(),args:chromium.args,headless:true});
  const page=await browser.newPage();if(process.env.PERF_TRACE)page.on('console',m=>console.log('[browser]',m.text()));const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await page.goto('http://127.0.0.1:'+server.address().port+'/#export');await page.waitForFunction(()=>S._bootReady||S._bootError,null,{timeout:60000});
  const result=await page.evaluate(async({n,unique,trace,ordered})=>{
   if(S._bootError)throw Error(JSON.stringify(S._bootError));
   const t=performance.now(),parts=['Артикул;Бренд;Цена\n'],expected=new Map();let seed=73;
   const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed};
   for(let i=0;i<n;i++){
    const k=random()%unique,key='A'+String(k).padStart(8,'0'),brand=k%13===0&&i%2?'OTHER':'BRAND',signature=k%17===0&&i%3?'99':'12';
    parts.push(key+';'+brand+';'+signature+'\n');
    const prior=expected.get(key);if(!prior)expected.set(key,{key,brand,signature,conflict:false});else{if(prior.brand!==brand||prior.signature!==signature)prior.conflict=true;}
   }
   const source=await BrowserImportSources.stage(new File(parts,'random.csv',{type:'text/csv'}));parts.length=0;
   const stageMs=Math.round(performance.now()-t),start=performance.now();if(trace)console.info('perf staged',stageMs);
   const build=BrowserImportSources.buildKeyPages;if(trace)BrowserImportSources.buildKeyPages=function(run,batches,merge,progress){return build.call(this,run,batches,merge,text=>{console.info(text);if(progress)progress(text)})};
   const describe=r=>({key:r[0],brand:r[1],signature:r[2]});
   const run=await BrowserImportSources.prepareKeys(source.id,'perf-source',describe,'perf');
   const buildMs=Math.round(performance.now()-start);let verified=0;
   const keys=[...expected.keys()];if(ordered)keys.sort();const look=performance.now();
   for(let off=0;off<keys.length;off+=1000){
    const batch=keys.slice(off,off+1000),found=await BrowserImportSources.lookupKeyPages(run,batch);
    for(const key of batch){const got=found.get(key),want=expected.get(key);if(!got||got.brand!==want.brand||got.signature!==want.signature||got.conflict!==want.conflict)throw Error('source parity '+key);verified++;}
   }
   const queryMs=Math.round(performance.now()-look),pages=await BrowserImportSources.database().keyPages.where('run').equals(run).count();
   let rows=keys.map((article,i)=>({article,brand:'BRAND',oe_numbers:''}));
   const targetStart=performance.now(),lookup=await BrowserCatalogLookup.create(rows,source.id),targetBuildMs=Math.round(performance.now()-targetStart),queryStart=performance.now();
   for(let off=0;off<rows.length;off+=1000){const batch=rows.slice(off,off+1000),got=await lookup.batch(batch,p=>p.article,p=>p.brand);for(const row of batch)if(got.idxArt.get(row.article)!==row||got.idx.get(row.article+'|BRAND')!==row)throw Error('target parity');}
   const targetQueryMs=Math.round(performance.now()-queryStart);await lookup.dispose();await BrowserImportSources.clearRun(run);
   if(await BrowserImportSources.database().keyPages.count())throw Error('temporary page leak');
   return {n,unique:expected.size,verified,pages,stageMs,buildMs,queryMs,targetBuildMs,targetQueryMs,elapsedMs:Math.round(performance.now()-t)};
  },{n:Number(process.env.PERF_ROWS||30000),unique:Number(process.env.PERF_KEYS||12000),trace:!!process.env.PERF_TRACE,ordered:!!process.env.PERF_SORTED});
  assert.equal(errors.length,0,errors.join('\n'));assert.equal(result.unique,result.verified);console.log(JSON.stringify(result));
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1});
