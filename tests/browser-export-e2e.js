// Real UI clicks + actual Chromium downloads, including failed/hung persistence.
const fs=require('fs'),http=require('http'),assert=require('assert');
const {chromium:pw}=require('playwright-core'),ch=require('@sparticuz/chromium');
(async()=>{
 const html=fs.readFileSync(__dirname+'/../index.html'),server=http.createServer((q,r)=>{r.setHeader('Content-Type','text/html; charset=utf-8');r.end(html)});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await pw.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||await ch.executablePath(),args:ch.args,headless:true});
  const page=await browser.newPage({acceptDownloads:true}),errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['error','warn'].includes(m.type()))console.log('browser:',m.text())});
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await page.goto('http://127.0.0.1:'+server.address().port);await page.waitForFunction(()=>S._bootReady||S._bootError);
  const n=Number(process.env.EXPORT_ROWS||1000);
  await page.evaluate(n=>{
   if(S._bootError)throw Error(S._bootError);
   window.showSaveFilePicker=undefined; // Exercise portable Blob/download path.
   S.rows=Array.from({length:n},(_,i)=>({id:i+1,article:String(i).padStart(8,'0'),brand:'Brand',name:'Товар '+i,cost:12.5,custom:{extra:'исходное😀'},oe_numbers:'OE'+i}));
   S.view=S.rows;S._econPending=true;S.settings.exportExclusions=false;S.settings.importLightMode=false;S._cacheWriteError='injected conflict';S._catalogConflict=true;
   _persistDirty=true;_persistPending=1;window.persistAttempts=0;
   persistNow=()=>{window.persistAttempts++;return new Promise(()=>{})};
   ensureEconomicsFor=()=>{throw Error('input-only export must not calculate economics')};
   Exp.activeMps();Exp.pick=Object.fromEntries(exportCatalog().map(c=>[c.k,['article','oe_norm_slash'].includes(c.k)]));
  },n);
  async function open(format){await page.evaluate(()=>Exp.open());await page.selectOption('#expFmt',format);await page.selectOption('#expScope','all');if(format==='csv')await page.selectOption('#expEnc','utf8')}
  async function download(action){const event=page.waitForEvent('download',{timeout:180000});await action();const file=await event.catch(async e=>{console.log(await page.locator('#toasts').innerText());console.log(await page.evaluate(()=>({onclick:document.querySelector('#expRun').onclick?.toString(),disabled:document.querySelector('#expRun').disabled,attempts:persistAttempts,errors:window.__errors,rows:S.rows.length,trace:window.trace,progress:document.querySelector('#prMsg').textContent})));throw e});assert.equal(await file.failure(),null);return {name:file.suggestedFilename(),bytes:fs.readFileSync(await file.path())}}
  await open('csv');const csv=await download(()=>page.click('#expRun'));assert(csv.name.endsWith('.csv'));assert.equal(csv.bytes.toString('utf8').trim().split('\r\n').length,n+1);assert(csv.bytes.toString('utf8').includes(String(n-1).padStart(8,'0')));
  await page.waitForFunction(()=>!document.querySelector('#expRun').disabled);assert.equal(await page.evaluate(()=>persistAttempts),0);
  // XLSX is a real ZIP workbook; read it with shipped SheetJS, not a mock.
  await open('xlsx');const xlsx=await download(()=>page.click('#expRun'));assert(xlsx.name.endsWith('.xlsx'));assert.equal(xlsx.bytes.readUInt16LE(0),0x4b50);
  const readback=await page.evaluate(bytes=>{const wb=XLSX.read(new Uint8Array(bytes),{type:'array'});const rows=XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]],{header:1,raw:true});return {count:rows.length,first:rows[1][0],last:rows[rows.length-1][0],allArticles:rows.slice(1).every((row,i)=>row[0]===String(i).padStart(8,'0'))}},Array.from(xlsx.bytes));
  assert.equal(readback.count,n+1);assert(readback.allArticles);assert.equal(readback.first,'00000000');assert.equal(readback.last,String(n-1).padStart(8,'0'));
  await page.waitForFunction(()=>!document.querySelector('#expRun').disabled);
  // Long normalized OE: actual confirmation dialog and CSV download.
  const expected=await page.evaluate(()=>{const long=Array.from({length:9000},(_,i)=>'LONG'+String(i).padStart(5,'0')).join(' / ');S.rows[0].oe_numbers=long;return normalizedOeForExport(S.rows[0])});assert(expected.length>32767);
  await open('csv');const longCsv=await download(()=>page.click('#expRun'));assert(longCsv.name.endsWith('.csv'));assert(longCsv.bytes.toString('utf8').includes(expected));
  await page.waitForFunction(()=>!document.querySelector('#expRun').disabled);
  await open('xlsx');await page.click('#expRun');await page.waitForSelector('#mGen.on');assert(await page.locator('#mgBody').innerText().then(t=>t.includes('32767')));
  const fallback=await download(()=>page.click('#mgApply'));assert(fallback.name.endsWith('.csv'));assert(fallback.bytes.toString('utf8').includes(expected));
  await page.waitForFunction(()=>!document.querySelector('#expRun').disabled);
  // Automatic click might be blocked by browser policy: ready URL still works
  // after the old 800ms lifetime and lets the user click a real visible link.
  await page.waitForTimeout(1200);const retry=await download(()=>page.locator('a[download]').last().click());assert.deepEqual(retry.bytes,fallback.bytes);
  // Declining keeps the export dialog open and publishes no new file.
  let unexpected=0;const observe=()=>unexpected++;page.on('download',observe);
  await open('xlsx');await page.click('#expRun');await page.waitForSelector('#mGen.on');await page.locator('#mGen [data-close]').first().click();
  await page.waitForFunction(()=>!document.querySelector('#expRun').disabled);assert(await page.locator('#mExport').evaluate(el=>el.classList.contains('on')));assert.equal(unexpected,0);page.off('download',observe);
  // Failure also keeps modal open, restores the button and does not clear data.
  await page.evaluate(()=>{window.savedCsv=Exp.csvAsync;Exp.csvAsync=async()=>{throw Error('injected export failure')}});
  await open('csv');await page.click('#expRun');await page.waitForFunction(()=>!document.querySelector('#expRun').disabled);
  assert(await page.locator('#mExport').evaluate(el=>el.classList.contains('on')));assert.equal(await page.evaluate(()=>S.rows.length),n);
  await page.evaluate(()=>{Exp.csvAsync=window.savedCsv});
  // Values-only XLSX has the same Excel limit; do not silently truncate it.
  await page.evaluate(()=>{document.querySelector('#mExport').classList.remove('on');UI.go('export');document.querySelector('#exportPanelData').style.display='block';document.querySelector('#dataExportFormat').value='xlsx'});
  await page.click('#dataExportRun');await page.waitForSelector('#mGen.on');const values=await download(()=>page.click('#mgApply'));assert(values.name.endsWith('.csv'));assert(values.bytes.toString('utf8').includes('LONG08999'));
  assert.equal(await page.evaluate(()=>persistAttempts),0);assert.equal(errors.length,0,errors.join('\n'));
  console.log(JSON.stringify({rows:n,csvBytes:csv.bytes.length,xlsxBytes:xlsx.bytes.length,xlsxReadback:readback,longOeLength:expected.length,overflowCsvBytes:fallback.bytes.length,manualRetry:true,declineKeepsModal:true,valuesOnlyCsv:true,persistAttempts:0}));
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1});
