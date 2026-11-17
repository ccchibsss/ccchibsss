// Force only the main DB to be unavailable; do not replace application fallback.
const fs=require('fs'),http=require('http'),assert=require('assert');
const {chromium:pw}=require('playwright-core'),chromium=require('@sparticuz/chromium');
(async()=>{
 const html=fs.readFileSync(__dirname+'/../index.html');const server=http.createServer((q,r)=>{r.setHeader('Content-Type','text/html;charset=utf-8');r.end(html)});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await pw.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||await chromium.executablePath(),args:chromium.args,headless:true});
  const page=await browser.newPage(),errors=[],hvcErrors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.text().includes('[UC] HVC load:'))hvcErrors.push(m.text())});
  await page.addInitScript(()=>{
   const open=IDBFactory.prototype.open;
   IDBFactory.prototype.open=function(name,...args){if(name==='UC_YM_UnitEconomics')throw new DOMException('Test main DB unavailable','SecurityError');return open.call(this,name,...args);};
  });
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await page.goto('http://127.0.0.1:'+server.address().port+'/#export');
  await page.waitForFunction(()=>S._bootReady||S._bootError,null,{timeout:60000});
  const result=await page.evaluate(async()=>{
   if(!S._bootReady||S._bootError||!S._volatileStorage||S._dbReady||S._hvcLoadError)throw Error('invalid fallback boot '+JSON.stringify(S._bootError||S._hvcLoadError));
   if(S._dbOpenInfo.name!=='SecurityError'||S._dbOpenInfo.phase!=='open')throw Error('original open error lost');
   if(!document.querySelector('#impApply').disabled)throw Error('Apply enabled in RAM fallback');
   const pending=S.pending;let readBlocked=false,applyBlocked=false;
   try{await Import.read(new File(['Артикул;Бренд\nA;B\n'],'blocked.csv',{type:'text/csv'}));}catch(e){readBlocked=e.name==='BrowserStorageUnavailable'&&e._ucImportNotStarted;}
   try{await Import.apply();}catch(e){applyBlocked=e.name==='BrowserStorageUnavailable'&&e._ucImportNotStarted;}
   if(!readBlocked||!applyBlocked||S.pending!==pending||S.rows.length||BrowserImportSources.busy||BrowserImportSources.active.size)throw Error('import touched fallback state');
   const databases=await indexedDB.databases();if(databases.some(d=>d.name==='UC_BrowserImportSources'))throw Error('blocked import still staged file');
   return {volatileBoot:true,hvcLoadError:S._hvcLoadError||null,readBlocked,applyBlocked,sourceDatabaseCreated:false};
  });
  assert.equal(errors.length,0,errors.join('\n'));assert.equal(hvcErrors.length,0,hvcErrors.join('\n'));console.log(JSON.stringify(result));
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1});
