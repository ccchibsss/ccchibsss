// Real Chromium: wide UTF-16 values, source byte paging and variable undo pages.
const fs=require('fs'),http=require('http'),assert=require('assert');
const {chromium:pw}=require('playwright-core'),chromium=require('@sparticuz/chromium');
(async()=>{
 const html=fs.readFileSync(__dirname+'/../index.html');
 const server=http.createServer((q,r)=>{r.setHeader('Content-Type','text/html;charset=utf-8');r.end(html)});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await pw.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||await chromium.executablePath(),args:chromium.args,headless:true});
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await page.goto('http://127.0.0.1:'+server.address().port+'/#export');
  await page.waitForFunction(()=>S._bootReady||S._bootError,null,{timeout:60000});
  const result=await page.evaluate(async preenriched=>{
   if(S._bootError)throw Error(String(S._bootError));
   const n=1200,wide='Длинное название '.repeat(150);S.rows=[];
   S.settings.autoStdDims=false;S.settings.autoOeAnomalyOnImport=false;S.settings.enrichRelatedOnImport=false;
   // Fault injection, NOT reproduction of a corrupt Chromium profile: a
   // first-file storage failure must surface before CSV parsing or mutation.
   const sourceTable=BrowserImportSources.database().sources,addSource=sourceTable.add.bind(sourceTable),priorPending=S.pending;
   const unavailable=Object.assign(Error('AbortError DataError Failed to read large IndexedDB value'),{name:'DatabaseClosedError'});
   sourceTable.add=async()=>{throw unavailable};let diagnosed=false;
   try{await Import.read(new File(['Артикул;Бренд\nA;B\n'],'first-fails.csv',{type:'text/csv'}));}
   catch(error){diagnosed=error.cause===unavailable&&error._ucImportStorage?.operation==='sources.add'&&error._ucImportStorage?.parsedRows===0&&error._ucImportStorage?.writtenRows===0&&error._ucShown===true;}
   finally{sourceTable.add=addSource;}
   if(!diagnosed||S.pending!==priorPending||S.rows.length||BrowserImportSources.busy||BrowserImportSources.active.size)throw Error('initial storage failure not isolated/diagnosed');

   async function apply(text,name,fields){
    await Import.read(new File([text],name,{type:'text/csv'}));
    const source=S.pending.sourceId;
    const numeric=new Set(['cost','weight','length','width','height']);
    S.pending.map=S.pending.headers.map((src,i)=>({src,field:fields[i]||'',target:src,type:numeric.has(fields[i])?'num':'text',enabled:true}));
    Import.normalize();Import.render();document.querySelector('#impKey').value='article+brand';document.querySelector('#impEnrichRelated').checked=false;
    await Import.apply();return source;
   }
   const applicability='Применимость к автомобилю '.repeat(80);
   const fields=['article','brand','cost','name'];
   const headers=['Артикул','Бренд','Себестоимость','Название'];
   if(preenriched){fields.push('oe_numbers','applicability','barcode','weight','length','width','height','category','tnved',null);headers.push('OE-номера','Применимость','Штрихкод','Вес','Длина','Ширина','Высота','Категория','ТН ВЭД','UserFlag');}
   const rows=Array.from({length:n},(_,i)=>['W'+i,'B','12.5',wide+i,...(preenriched?['PRE'+i,applicability+i,'00000'+i,'0.5','20','10','5','Запчасти','8708999709','user'+i]:[])].join(';'));
   const source=await apply(headers.join(';')+'\n'+rows.join('\n'),'price-wide.csv',fields);
   const verify=row=>{
    const i=Number(row.article.slice(1));
    if(row.name!==wide+i||row.cost!==12.5)throw Error('price fields mismatch '+i);
    if(preenriched&&(row.applicability!==applicability+i||row.barcode!=='00000'+i||row.weight!==0.5||row.length!==20||row.width!==10||row.height!==5||row.category!=='Запчасти'||row.tnved!=='8708999709'||!Object.values(row.custom||{}).includes('user'+i)))throw Error('preenriched price fields mismatch '+i);
   };
   for(const row of S.rows){verify(row);if(preenriched&&row.oe_numbers!=='PRE'+Number(row.article.slice(1)))throw Error('first price OE changed');}
   if(HVC.parts.size!==0||!S._econPending)throw Error('first price unexpectedly enriched/calculated');
   const pages=await BrowserImportSources.database().rowPages.where('source').equals(source).toArray();
   if(pages.some(p=>JSON.stringify(p.cells).length*2>512*1024)||pages.length<3)throw Error('source pages not byte bounded');
   let checkpointPages=0;
   const begin=BrowserApplyCheckpoint.begin;
   BrowserApplyCheckpoint.begin=async function(){const owner=await begin.call(this);const pages=await db.applyUndo.where('table').equals('products').toArray();checkpointPages=pages.length;if(pages.some(p=>JSON.stringify(p.values).length*2>512*1024)||pages.length<3)throw Error('undo pages not byte bounded');return owner;};
   await apply('Артикул;Бренд;OE-номера\n'+Array.from({length:n},(_,i)=>'W'+i+';B;OE'+i).join('\n'),'oe-wide.csv',['article','brand','oe_numbers']);
   BrowserApplyCheckpoint.begin=begin;
   db.close();await db.open();const saved=await db.products.toArray();
   if(saved.length!==n||S.rows.length!==n)throw Error('row count');
   for(const row of saved){
    verify(row);const i=Number(row.article.slice(1)),actual=codeList(row.oe_numbers).sort(),expected=(preenriched?['PRE'+i,'OE'+i]:['OE'+i]).sort();
    if(JSON.stringify(actual)!==JSON.stringify(expected))throw Error('OE accumulation mismatch '+i);
   }
   const reloaded=await HVC.load();if(reloaded!==n||S._hvcLoadError)throw Error('HVC reopen failed');
   for(const row of saved){const i=Number(row.article.slice(1)),links=HVC.byArt.get(HVC.keyOf(row));if(!links?.has('OE'+i)||(preenriched&&!links.has('PRE'+i)))throw Error('HVC lost OE '+i);}
   if(await db.meta.get(BrowserApplyCheckpoint.KEY)||await db.applyUndo.count())throw Error('undo leaked');
   if(!S._econPending)throw Error('unexpected economics');
   return {rows:n,initialStorageFailureHandled:true,preenrichedPrice:preenriched,sourcePages:pages.length,checkpointPages,exactReopen:true,economicsPending:true};
  },process.env.E2E_PRICE_ENRICHED==='1');
  assert.equal(errors.length,0,errors.join('\n'));console.log(JSON.stringify(result));
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1});
