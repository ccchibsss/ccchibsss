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
  const result=await page.evaluate(async()=>{
   if(S._bootError)throw Error(String(S._bootError));
   const n=1200,wide='Длинное название '.repeat(150);S.rows=[];
   S.settings.autoStdDims=false;S.settings.autoOeAnomalyOnImport=false;S.settings.enrichRelatedOnImport=false;
   async function apply(text,name,fields){
    await Import.read(new File([text],name,{type:'text/csv'}));
    const source=S.pending.sourceId;
    S.pending.map=S.pending.headers.map((src,i)=>({src,field:fields[i],target:src,type:fields[i]==='cost'?'num':'text',enabled:true}));
    Import.normalize();Import.render();document.querySelector('#impKey').value='article+brand';document.querySelector('#impEnrichRelated').checked=false;
    await Import.apply();return source;
   }
   const rows=Array.from({length:n},(_,i)=>'W'+i+';B;12.5;'+wide+i);
   const source=await apply('Артикул;Бренд;Себестоимость;Название\n'+rows.join('\n'),'price-wide.csv',['article','brand','cost','name']);
   const pages=await BrowserImportSources.database().rowPages.where('source').equals(source).toArray();
   if(pages.some(p=>JSON.stringify(p.cells).length*2>512*1024)||pages.length<3)throw Error('source pages not byte bounded');
   let checkpointPages=0;
   const begin=BrowserApplyCheckpoint.begin;
   BrowserApplyCheckpoint.begin=async function(){const owner=await begin.call(this);const pages=await db.applyUndo.where('table').equals('products').toArray();checkpointPages=pages.length;if(pages.some(p=>JSON.stringify(p.values).length*2>512*1024)||pages.length<3)throw Error('undo pages not byte bounded');return owner;};
   await apply('Артикул;Бренд;OE-номера\n'+Array.from({length:n},(_,i)=>'W'+i+';B;OE'+i).join('\n'),'oe-wide.csv',['article','brand','oe_numbers']);
   BrowserApplyCheckpoint.begin=begin;
   db.close();await db.open();const saved=await db.products.toArray();
   if(saved.length!==n||S.rows.length!==n)throw Error('row count');
   for(const row of saved){const i=Number(row.article.slice(1));if(row.name!==wide+i||row.oe_numbers!=='OE'+i||row.cost!==12.5)throw Error('field mismatch '+i);}
   if(await db.meta.get(BrowserApplyCheckpoint.KEY)||await db.applyUndo.count())throw Error('undo leaked');
   if(!S._econPending)throw Error('unexpected economics');
   return {rows:n,sourcePages:pages.length,checkpointPages,exactReopen:true,economicsPending:true};
  });
  assert.equal(errors.length,0,errors.join('\n'));console.log(JSON.stringify(result));
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1});
