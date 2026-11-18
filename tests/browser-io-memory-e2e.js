// Real browser checks: sequential ZIP entries, OPFS draining, failure cleanup,
// values-only XLSX and pull-based disk XLSX import. Optional old-build parity.
const fs=require('fs'),http=require('http'),assert=require('assert');
const {chromium:pw}=require('playwright-core'),ch=require('@sparticuz/chromium');
(async()=>{
 const html=fs.readFileSync(__dirname+'/../index.html','utf8');
 const baseline=process.env.E2E_BASE_HTML?fs.readFileSync(process.env.E2E_BASE_HTML,'utf8'):'';
 const method=(name,end)=>baseline?baseline.slice(baseline.indexOf(name),baseline.indexOf(end,baseline.indexOf(name))):'';
 const old={ozcsv:method('  async generateCsv(','\n  /* audit.2:'),xlsx:method('  async streamXlsx(','\n  /* Кодирование строки'),csv:method('  async csvAsync(','\n  /* XLSX:'),report:method('  async reportBlob(','  async report() {')};
 const server=http.createServer((q,r)=>{r.setHeader('Content-Type','text/html;charset=utf-8');r.end(html)});await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await pw.launch({executablePath:await ch.executablePath(),args:ch.args,headless:true});const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await page.goto('http://127.0.0.1:'+server.address().port+'/#export');await page.waitForFunction(()=>S._bootReady||S._bootError);
  const result=await page.evaluate(async({old,n})=>{
   if(S._bootError)throw Error('boot failed');
   const originalCreate=BrowserExportSpool.create,zipAdd=fflate.Zip.prototype.add;
   let writes=0,maxWrite=0,aborts=0,closed=0,activeEntries=0,maxActive=0;
   BrowserExportSpool.create=async function(){const sink=await originalCreate.call(this);return{...sink,write:async blobs=>{writes++;maxWrite=Math.max(maxWrite,blobs.reduce((s,b)=>s+(b.size??b.byteLength),0));return sink.write(blobs)},finish:async type=>{closed++;return sink.finish(type)},abort:async()=>{aborts++;return sink.abort()}}};
   fflate.Zip.prototype.add=function(file){activeEntries++;maxActive=Math.max(maxActive,activeEntries);const push=file.push;file.push=function(data,final){const result=push.call(this,data,final);if(final)activeEntries--;return result};return zipAdd.call(this,file)};
   const rows=Array.from({length:n},(_,i)=>({id:i+1,article:String(i).padStart(8,'0'),brand:'B',name:'Unicode 😀 & < > "\r\n '+i,cost:12.5,weight:1,length:2,width:3,height:4,category:'C',price:25,custom:{extra:i%2?'=1+2':'OE;1 _x0041_ \u0001',flag:i%2===0}}));
   S.rows=rows;S.view=rows;S.custom=[{key:'extra',name:'Своя',type:'text'},{key:'flag',name:'Флаг',type:'bool'}];S.settings.exportExclusions=false;
   const cat=[{k:'article',n:'Артикул',txt:true},{k:'name',n:'Название',txt:true},{k:'cost',n:'Закупка',f:'0.00'},{k:'price',n:'Цена',f:'0.00'},{k:'weight',n:'Вес',f:'0.00'},{k:'netProfit',n:'Прибыль',f:'0.00',xl:(r,ref)=>`=${ref.price}${r}-${ref.cost}${r}`}];
   const inspect=async blob=>{const bytes=new Uint8Array(await blob.arrayBuffer()),zip=fflate.unzipSync(bytes);return Object.fromEntries(Object.keys(zip).sort().map(k=>[k,new TextDecoder().decode(zip[k])]));};
   const same=(a,b,label)=>{if(JSON.stringify(a)!==JSON.stringify(b))throw Error(label+' differs');};
   const t=performance.now(),blob=await Exp.streamXlsx(cat,rows,()=>{}),current=await inspect(blob);
   if(navigator.storage.getDirectory&&!(blob instanceof File))throw Error('XLSX not disk-backed');
   if(maxActive!==1)throw Error('concurrent ZIP entries '+maxActive);
   const book=XLSX.read(await blob.arrayBuffer(),{type:'array'});
   if(XLSX.utils.sheet_to_json(book.Sheets['Юнит-экономика'],{header:1}).length!==n+1)throw Error('main row count');
   if(XLSX.utils.sheet_to_json(book.Sheets['Вводы и ставки'],{header:1}).length!==n+1)throw Error('input row count');
   const formulaCells=Object.entries(book.Sheets['Юнит-экономика']).filter(([k,v])=>v&&v.f);
   if(formulaCells.length!==n||formulaCells[0][1].f===formulaCells[n-1][1].f)throw Error('row-specific formulas missing');
   const xlsxMs=Math.round(performance.now()-t);
   // Disable instrumentation for old asynchronous compression workers.
   fflate.Zip.prototype.add=zipAdd;
   if(old.xlsx){const legacy=(0,eval)('({'+old.xlsx+'})');same(current,await inspect(await legacy.streamXlsx.call(Exp,cat,rows,null)),'all XLSX XML entries');}
   const csv=await Exp.csvAsync(cat,rows,null);
   if(old.csv){const legacy=(0,eval)('({'+old.csv+'})');const a=new Uint8Array(await csv.arrayBuffer()),b=new Uint8Array(await (await legacy.csvAsync.call(Exp,cat,rows,null)).arrayBuffer());if(a.length!==b.length||a.some((v,i)=>v!==b[i])){let k=a.findIndex((v,i)=>v!==b[i]);throw Error('CSV differs '+JSON.stringify({lengths:[a.length,b.length],at:k,a:Array.from(a.slice(Math.max(0,k-10),k+30)),b:Array.from(b.slice(Math.max(0,k-10),k+30))}));}}
   const ozcsv=await OzonExport.generateCsv(rows,{fmt:'csv_utf8'},null);
   if(old.ozcsv){const legacy=(0,eval)('({'+old.ozcsv+'})');const expected=await legacy.generateCsv.call(OzonExport,rows,{fmt:'csv_utf8'},null);same(Array.from(new Uint8Array(await ozcsv.arrayBuffer())),Array.from(new Uint8Array(await expected.arrayBuffer())),'Ozon CSV bytes');}
   const report=await OzonReference.reportBlob(rows,()=>{});
   if(old.report){const legacy=(0,eval)('({'+old.report+'})');same(await inspect(report),await inspect(await legacy.reportBlob.call(OzonReference,rows,null)),'category-report XML');}
   let downloaded;const download=Exp.download;Exp.download=b=>{downloaded=b};document.querySelector('#dataExportFormat').value='xlsx';S._econPending=true;
   const aoa=XLSX.utils.sheet_add_aoa;XLSX.utils.sheet_add_aoa=()=>{throw Error('must not materialize all cells')};
   try{await DataOnlyExport.run();}finally{XLSX.utils.sheet_add_aoa=aoa;Exp.download=download;}
   if(!downloaded)throw Error('values-only download missing');
   const dw=XLSX.read(await downloaded.arrayBuffer(),{type:'array'}),actual=XLSX.utils.sheet_to_json(dw.Sheets['Данные'],{header:1,raw:true,defval:''});
   const specs=DataOnlyExport.specs(),present=specs.filter(c=>c.custom||rows.some(p=>p[c.key]!==undefined));
   const expected=rows.map(p=>present.map(c=>DataOnlyExport.value(p,c)));
   if(JSON.stringify(actual.slice(1))!==JSON.stringify(expected)){const k=expected.findIndex((r,i)=>JSON.stringify(r)!==JSON.stringify(actual[i+1]));throw Error('values-only row '+k+' '+JSON.stringify({actual:actual[k+1],expected:expected[k],cols:present.map(c=>c.key)}));}if(!S._econPending)throw Error('values-only calculated economics');
   // Quota and cancellation must abort partial ZIPs, with no published file.
   let diskWrites=0;BrowserExportSpool.create=async()=>({disk:true,write:async()=>{if(++diskWrites===2)throw Error('injected quota')},finish:async()=>{throw Error('partial file published')},abort:async()=>{aborts++}});
   const before=aborts;try{await Exp.streamXlsx(cat,rows,()=>{});throw Error('quota not raised')}catch(e){if(!String(e).includes('injected quota'))throw e}if(aborts!==before+1)throw Error('quota cleanup');
   BrowserExportSpool.create=originalCreate;
   const getDirectory=navigator.storage.getDirectory;navigator.storage.getDirectory=undefined;
   try{const portable=await Exp.streamXlsx(cat,rows.slice(0,2),()=>{});if(!(portable instanceof Blob)||portable instanceof File)throw Error('portable export fallback');const wb=XLSX.read(await portable.arrayBuffer(),{type:'array'});if(!wb.Sheets['Вводы и ставки'])throw Error('portable input sheet');}finally{navigator.storage.getDirectory=getDirectory;}
   let cancelAborts=0;const cancelCheck=UCCancel.check;
   BrowserExportSpool.create=async()=>({disk:true,write:async()=>{},finish:async()=>{throw Error('cancelled file published')},abort:async()=>{cancelAborts++}});
   UCCancel.check=()=>{throw Object.assign(Error('injected cancellation'),{_ucCancelled:true})};
   try{await Exp.streamXlsx(cat,rows,()=>{});throw Error('cancel ignored')}catch(e){if(!e._ucCancelled)throw e}finally{UCCancel.check=cancelCheck;BrowserExportSpool.create=originalCreate;}
   if(cancelAborts!==1)throw Error('cancel did not abort ZIP');
   // Disk reader: worksheet retained in worker, at most one batch delivered
   // while consumer is deliberately slow; blank rows do not count as data.
   const sourceRows=[['Артикул','Бренд','Цена'],...Array.from({length:5001},(_,i)=>i===1000?[]:['A'+i,'B',12.5])];
   const wb=XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet(sourceRows),'Price');
   const session=await DiskImport._xlsxBegin(new File([XLSX.write(wb,{type:'array',bookType:'xlsx'})],'price.xlsx'));
   let received=0,atFlush=0,flushes=0;DiskImport._abort=false;
   const total=await session.drain(()=>{received++},async()=>{atFlush=received;await new Promise(r=>setTimeout(r,10));if(received!==atFlush)throw Error('worker flooded receiver');flushes++;});
   if(total!==5000||received!==5000||flushes<5||DiskImport._sessions.size)throw Error('disk import totals/cleanup');
   return{rows:n,xlsxMs,opfs:blob instanceof File,writes,maxWrite,maxActive,aborts,closed,legacyParity:!!old.xlsx,valuesOnlyCells:true,diskImportRows:total,diskImportFlushes:flushes};
  },{old,n:Number(process.env.E2E_ROWS||1200)});
  assert.equal(errors.length,0,errors.join('\n'));console.log(JSON.stringify(result));
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1});
