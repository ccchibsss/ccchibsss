const fs=require('fs'),http=require('http'),assert=require('assert');
const {chromium:pw}=require('playwright-core'),ch=require('@sparticuz/chromium');
(async()=>{
 const server=http.createServer((q,r)=>{r.setHeader('Content-Type','text/html; charset=utf-8');r.end(fs.readFileSync(__dirname+'/../index.html'))});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await pw.launch({executablePath:await ch.executablePath(),args:ch.args,headless:true});const page=await browser.newPage();
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await page.goto('http://127.0.0.1:'+server.address().port);await page.waitForFunction(()=>S._bootReady||S._bootError);
  const result=await page.evaluate(async()=>{
   if(S._bootError||PyEngine.processingMode()!=='browser')throw Error('browser boot failed');
   const rows=Array.from({length:1001},(_,i)=>({article:String(i).padStart(8,'0'),brand:'B',name:i===0?'Unicode 😀 & < > " \r\n _x0041_ =1+2':'Product '+i,cost:12.5,weight:1,length:2,width:3,height:4,custom:{}}));
   S.rows=rows;S.view=rows;S.settings.autoCategoryByName=false;
   const read=async blob=>{const bytes=new Uint8Array(await blob.arrayBuffer()),wb=XLSX.read(bytes,{type:'array',cellStyles:true}),sheet=wb.Sheets[wb.SheetNames[0]];const files=fflate.unzipSync(bytes),xml=new TextDecoder().decode(files['xl/worksheets/sheet1.xml']);return{values:XLSX.utils.sheet_to_json(sheet,{header:1,raw:true,defval:''}),cells:Object.fromEntries(Object.entries(sheet).filter(([k])=>!k.startsWith('!')).map(([k,v])=>[k,[v.t,v.v]])),xml,bytes:bytes.length};};
   const opts={};
   const old=await read(await OzonExport._generateXlsxLegacy(rows,opts,null));
   const diskBlob=await OzonExport.generateXlsx(rows,opts,null);
   if(navigator.storage.getDirectory&&!(diskBlob instanceof File))throw Error('OPFS archive not disk backed');
   const current=await read(diskBlob);
   if(JSON.stringify(old.values)!==JSON.stringify(current.values)){const i=old.values.findIndex((r,i)=>JSON.stringify(r)!==JSON.stringify(current.values[i]));throw Error('worksheet value parity failed row '+i+' '+JSON.stringify([old.values[i],current.values[i]]));}
   if(JSON.stringify(old.cells)!==JSON.stringify(current.cells)){
    const keys=new Set([...Object.keys(old.cells),...Object.keys(current.cells)]);
    const bad=[...keys].filter(k=>JSON.stringify(old.cells[k])!==JSON.stringify(current.cells[k]));
    throw Error('cell type parity failed '+bad.slice(0,5).map(k=>k+':'+JSON.stringify([old.cells[k],current.cells[k]])).join(';'));
   }
   const cf=xml=>[...xml.matchAll(/<conditionalFormatting[^>]*>[\s\S]*?<\/conditionalFormatting>/g)].map(m=>m[0]);
   if(JSON.stringify(cf(old.xml))!==JSON.stringify(cf(current.xml)))throw Error('conditional formatting parity failed');
   if(old.xml.match(/<dimension[^>]*>/)[0]!==current.xml.match(/<dimension[^>]*>/)[0])throw Error('worksheet dimensions differ');
   // Regression: streaming must never hand product rows to SheetJS.
   const original=XLSX.utils.aoa_to_sheet;let max=0;
   XLSX.utils.aoa_to_sheet=(aoa,...args)=>{max=Math.max(max,aoa.length);if(aoa.length>OzonExport.HEADERS.length)throw Error('materialized product cells');return original(aoa,...args)};
   try{await OzonExport.generateXlsx(rows.slice(0,2),opts,null);}finally{XLSX.utils.aoa_to_sheet=original;}
   const getDirectory=navigator.storage.getDirectory;navigator.storage.getDirectory=undefined;
   try{const fallback=await read(await OzonExport.generateXlsx(rows.slice(0,2),opts,null));if(fallback.values.length!==6)throw Error('portable Blob fallback');}finally{navigator.storage.getDirectory=getDirectory;}
   return{diskBacked:diskBlob instanceof File,portableFallback:true,rows:rows.length,valuesAndTypesEqual:true,conditionalFormattingEqual:true,maxSheetJsRows:max,legacyBytes:old.bytes,streamBytes:current.bytes};
  });assert(result.valuesAndTypesEqual);console.log(JSON.stringify(result));
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1});
