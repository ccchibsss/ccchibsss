// Actual Python+SQLite HTTP engine + Chromium, no browser calculation fallback.
const fs=require('fs'),path=require('path'),os=require('os'),{spawn}=require('child_process'),assert=require('assert');
const {chromium:pw}=require('playwright-core'),chromiumModule=require('@sparticuz/chromium'),chromium=chromiumModule.default||chromiumModule;
(async()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'uc-sql-paged-'));let browser,child;
 try{
  child=spawn('python',['-u','-c',`import sys,pathlib\nsys.path.insert(0,'engine')\nimport uc_engine as E\nE.DATA=pathlib.Path(sys.argv[1]);E.DB_PATH=E.DATA/'catalog.db';E.TOKEN_PATH=E.DATA/'token.txt';E._TOKEN_CACHE='test-only-token'\ns=E.ThreadingHTTPServer(('127.0.0.1',0),E.Handler)\nprint(s.server_port,flush=True)\ns.serve_forever()`,tmp],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','pipe']});
  let stderr='';child.stderr.on('data',d=>stderr+=d.toString());
  const port=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('engine startup timeout '+stderr)),30000);child.once('exit',code=>{clearTimeout(timer);reject(Error('engine exited '+code+' '+stderr))});child.stdout.once('data',d=>{clearTimeout(timer);resolve(Number(d.toString().trim().split('\n')[0]))});});
  browser=await pw.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||await chromium.executablePath(),args:chromium.args,headless:true});
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{localStorage.setItem('uc.processingMode','sql');document.addEventListener('DOMContentLoaded',()=>{S.settings.pyEngineUrl=location.origin;localStorage.setItem('uc.settings',JSON.stringify({pyEngineUrl:location.origin}));},{once:true});});
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await page.goto('http://127.0.0.1:'+port+'/#export');await page.waitForFunction(()=>S._bootReady||S._bootError,null,{timeout:60000});
  const result=await page.evaluate(async()=>{
   if(S._bootError||PyEngine.processingMode()!=='sql')throw Error('SQL boot failed '+JSON.stringify(S._bootError));
   const n=1200,wide='Длинное название '.repeat(30);S.settings.autoStdDims=false;S.settings.autoOeAnomalyOnImport=false;S.settings.enrichRelatedOnImport=false;
   async function apply(name,fields,rows,customName='UserFlag'){
    const heads=fields.map(f=>f||customName);
    await Import.read(new File([[heads,...rows].map(r=>r.map(v=>'"'+String(v).replace(/"/g,'""')+'"').join(';')).join('\n')],name,{type:'text/csv'}));
    if(!S.pending.body._sqlSource||Array.isArray(S.pending.body)||S.pending.body.slice(0,999999).length>200||S.pending.body.length!==rows.length||S.pending.sourceId)throw Error('SQL file materialized');
    S.pending.map=fields.map((field,i)=>({src:heads[i],field:field||'',target:heads[i],enabled:true,type:field==='cost'?'num':'text'}));
    Import.normalize();Import.render();document.querySelector('#impKey').value='article+brand';document.querySelector('#impEnrichRelated').checked=false;await Import.apply();
    if(S._cacheWriteError||S._bootError)throw Error('SQL persistence failed '+String(S._cacheWriteError||S._bootError));
   }
   await apply('price.csv',['article','brand','cost','name','oe_numbers','barcode',null],Array.from({length:n},(_,i)=>['A'+i,'B','12.5',wide+i,'PRE'+i,'00000'+i,'user'+i]));
   if(HVC.parts.size||!S._econPending)throw Error('first price enriched/economics computed');
   const rows=Array.from({length:5000},(_,j)=>{const i=j%n;return ['A'+i,'B','SQL '+i,'OE'+i];});rows.push(['A0','B','CONFLICT','BAD']);
   await apply('enrichment.csv',['article','brand','name','oe_numbers'],rows);
   const persisted=await PyEngine.readSqlCatalog();if(persisted.rows.length!==n||S.rows.length!==n)throw Error('catalog size');
   for(const list of [S.rows,persisted.rows])for(const row of list){
    const i=Number(row.article.slice(1)),oe=codeList(row.oe_numbers).sort();
    if(row.cost!==12.5||row.barcode!=='00000'+i||!Object.values(row.custom||{}).includes('user'+i)||row.name!==(i===0?wide+i:'SQL '+i)||JSON.stringify(oe)!==JSON.stringify((i===0?['PRE0']:['PRE'+i,'OE'+i]).sort()))throw Error('field/conflict mismatch '+i);
   }
   await apply('oe-only.csv',['oe_numbers',null],[['PRE1','red'],['PRE2; PRE3','ambiguous'],['UNKNOWN','unmatched'],['PRE4','green']],'Color');
   await apply('sku-column.csv',['article','brand',null],[['A5','B','cotton']],'Material');
   await apply('oe-supplier.csv',['article','brand','oe_numbers',null],[['OTHER','OTHERBRAND','PRE6','steel']],'Material');
   const enriched=await PyEngine.readSqlCatalog();
   for(const list of [S.rows,enriched.rows]){
    if(list.length!==n)throw Error('enrichment created SKU');
    const row=i=>list.find(p=>p.article==='A'+i&&p.brand==='B');
    if(row(1).custom.Color!=='red'||row(4).custom.Color!=='green'||row(2).custom.Color||row(3).custom.Color||row(5).custom.Material!=='cotton'||row(6).custom.Material!=='steel')throw Error('new columns did not follow SKU/OE key');
    if(!Object.values(row(6).custom).includes('user6'))throw Error('existing custom value lost');
   }
   if(!S.custom.some(c=>c.key==='Color')||!S.custom.some(c=>c.key==='Material'))throw Error('column registration missing');
   if(await db.products.count())throw Error('SQL wrote browser catalog');
   if((await indexedDB.databases()).some(d=>d.name==='UC_BrowserImportSources'))throw Error('SQL staged source in browser');
   if(!S._econPending)throw Error('economics calculated');
   return{rows:n,sourceRows:rows.length,previewLimit:200,sqlPersistence:true,newColumnsBySkuAndOe:true,ambiguousOeSkipped:true,crossBatchConflict:true,browserCatalogRows:0,economicsPending:true};
  });
  const cdp=await page.context().newCDPSession(page);
  async function heap(){await cdp.send('HeapProfiler.collectGarbage');return (await cdp.send('Runtime.getHeapUsage')).usedSize;}
  await page.evaluate(()=>{window.__probeFile=new File(['article;brand;name\n'+Array.from({length:20001},(_,i)=>'P'+i+';B;'+('Wide '+i+' ').repeat(120)).join('\n')],'heap.csv',{type:'text/csv'});});
  const base=await heap();
  await page.evaluate(async()=>{window.__probeResult=await PyEngine.parseFile(window.__probeFile,{catalogImport:true,table:true});});
  const legacy=(await heap())-base;
  await page.evaluate(()=>{delete window.__probeResult;});const pagedBase=await heap();
  await page.evaluate(async()=>{window.__probeResult=await PyEngine.parseFile(window.__probeFile,{catalogImport:true,table:true,paged:true});if(window.__probeResult.body.length!==20001)throw Error('probe rows');});
  const paged=(await heap())-pagedBase;
  assert(paged<legacy*.7,'paged retained heap not reduced: '+JSON.stringify({legacy,paged}));
  result.parseRetainedHeapBytes={legacy,paged,rows:20001};
  await page.evaluate(()=>{
   delete window.__probeResult;delete window.__probeFile;
   window.__graph=new Map(Array.from({length:6000},(_,i)=>['P'+i,{name:('Wide '+i+' ').repeat(180)}]));
  });
  const graphBase=await heap();
  await page.evaluate(()=>{window.__legacyJson=JSON.stringify({identity:{parts:[...window.__graph]}});});
  const legacyGraph=(await heap())-graphBase;
  await page.evaluate(()=>{delete window.__legacyJson;});const streamBase=await heap();
  await page.evaluate(()=>{window.__stream=SqlMemory.jsonChunks({identity:{parts:SqlMemory.jsonArray(window.__graph)}});});
  let streamPeak=0,done=false;
  while(!done){
   done=await page.evaluate(()=>{const item=window.__stream.next();window.__chunk=item.value;return item.done;});
   streamPeak=Math.max(streamPeak,(await heap())-streamBase);
  }
  await page.evaluate(()=>{delete window.__stream;delete window.__chunk;delete window.__graph;});
  assert(streamPeak<legacyGraph*.7,'streamed graph heap not reduced '+JSON.stringify({legacyGraph,streamPeak}));
  result.referenceRetainedHeapBytes={legacy:legacyGraph,streamPeak,entries:6000};

  await page.evaluate(()=>{window.__guardRows=Array.from({length:5000},(_,i)=>({article:'P'+i,custom:{text:('Wide '+i+' ').repeat(180)}}));});
  const guardBase=await heap();
  await page.evaluate(()=>{window.__legacyGuards=window.__guardRows.map(p=>JSON.stringify(p));});
  const legacyGuards=(await heap())-guardBase;
  await page.evaluate(()=>{delete window.__legacyGuards;});const hashBase=await heap();
  await page.evaluate(()=>{window.__compactGuard=SqlMemory.rowsGuard(window.__guardRows);if(!window.__compactGuard.matches(window.__guardRows))throw Error('guard mismatched');});
  const compactGuards=(await heap())-hashBase;
  assert(compactGuards<legacyGuards*.7,'guard heap not reduced '+JSON.stringify({legacyGuards,compactGuards}));
  result.guardRetainedHeapBytes={legacy:legacyGuards,compact:compactGuards,rows:5000};
  await page.evaluate(()=>{delete window.__compactGuard;delete window.__guardRows;});
  assert.equal(errors.length,0,errors.join('\n'));console.log(JSON.stringify(result));
 }finally{if(browser)await browser.close();if(child){child.kill('SIGTERM');await new Promise(resolve=>{if(child.exitCode!==null)return resolve();child.once('exit',resolve);setTimeout(()=>{child.kill('SIGKILL');resolve();},3000).unref()});}fs.rmSync(tmp,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1});
