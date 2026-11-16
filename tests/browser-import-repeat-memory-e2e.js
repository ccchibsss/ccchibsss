// Diagnostic retention test: forced GC ONLY between completed operations.
const fs=require('fs'),http=require('http'),assert=require('assert');
const {chromium:pw}=require('playwright-core'),chromium=require('@sparticuz/chromium');
(async()=>{
 const html=fs.readFileSync(__dirname+'/../index.html'),server=http.createServer((q,r)=>{r.setHeader('Content-Type','text/html;charset=utf-8');r.end(html)});await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await pw.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||await chromium.executablePath(),args:chromium.args,headless:true});
  const page=await browser.newPage(),errors=[],n=Number(process.env.REPEAT_ROWS||5000);page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());await page.goto('http://127.0.0.1:'+server.address().port+'/#export');await page.waitForFunction(()=>S._bootReady||S._bootError,null,{timeout:60000});
  const cdp=await page.context().newCDPSession(page),samples=[];
  async function sample(label){const before=await cdp.send('Runtime.getHeapUsage');await cdp.send('HeapProfiler.collectGarbage');const after=await cdp.send('Runtime.getHeapUsage');samples.push({label,before,after});}
  const source=await page.evaluate(async n=>{
   S.rows=[];S.settings.autoStdDims=false;S.settings.autoOeAnomalyOnImport=false;S.settings.enrichRelatedOnImport=false;
   window.auditMap=()=>{S.pending.map=S.pending.headers.map((src,i)=>({src,field:['article','brand',S.pending.file==='price.csv'?'cost':'oe_numbers'][i],target:src,type:i===2&&S.pending.file==='price.csv'?'num':'text',enabled:true}));Import.normalize();Import.render();document.querySelector('#impKey').value='article+brand';document.querySelector('#impEnrichRelated').checked=false;};
   let text='Артикул;Бренд;Себестоимость\n';for(let i=0;i<n;i++)text+='A'+i+';B;12.5\n';await Import.read(new File([text],'price.csv',{type:'text/csv'}));auditMap();await Import.apply();
   text='Артикул;Бренд;OE-номера\n';for(let i=0;i<n*4;i++){const j=i%n;text+='A'+j+';B;OE'+j+'\n';}await Import.read(new File([text],'oe.csv',{type:'text/csv'}));return S.pending.sourceId;
  },n);
  for(let cycle=0;cycle<4;cycle++){
   const state=await page.evaluate(async({source,n})=>{
    if(!S.pending?.body?.length)await Import.read({name:'oe.csv'},source);auditMap();await Import.apply();
    for(let i=0;i<n;i++)if(S.rows[i].article!=='A'+i||S.rows[i].oe_numbers!=='OE'+i||S.rows[i].cost!==12.5)throw Error('repeat mismatch '+i);
    if(await db.meta.get(BrowserApplyCheckpoint.KEY)||await db.applyUndo.count())throw Error('checkpoint leak');
    return {rows:S.rows.length,parts:HVC.parts.size,oe:HVC.oe.size,cross:HVC.cross.size,cachePages:BrowserImportSources._keyPageCache?.size||0,cacheBytes:BrowserImportSources._keyCacheBytes||0,directories:BrowserImportSources._keyDirectories?.size||0,pending:S._econPending};
   },{source,n});
   assert.equal(state.rows,n);assert.equal(state.parts,n);assert.equal(state.oe,n);assert.equal(state.cross,n);assert(state.pending);assert(state.cachePages<=256);assert(state.cacheBytes<=32*1048576);assert(state.directories<=8);
   await sample('cycle-'+(cycle+1));samples.at(-1).state=state;
  }
  // Retained heap should stabilize after warm-up, not grow by a catalog per run.
  const warm=samples[1].after.usedSize,last=samples[3].after.usedSize;assert(last-warm<16*1048576,'retained heap grows >16MiB after warm-up');
  assert.equal(errors.length,0,errors.join('\n'));const result={rows:n,sourceRows:n*4,cycles:4,warmToLastBytes:last-warm,samples};if(process.env.REPEAT_MEMORY_OUTPUT)fs.writeFileSync(process.env.REPEAT_MEMORY_OUTPUT,JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1});
