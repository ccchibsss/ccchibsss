// Real Apply parity: paged IndexedDB lookup vs original array/RAM lookup,
// plus independent expectations for inputs, collisions and enrichment output.
const fs=require('fs'),http=require('http'),assert=require('assert');
const {chromium:pw}=require('playwright-core'),chromium=require('@sparticuz/chromium');
(async()=>{
 const html=fs.readFileSync(process.env.E2E_HTML||__dirname+'/../index.html'),server=http.createServer((q,r)=>{r.setHeader('Content-Type','text/html;charset=utf-8');r.end(html)});await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  const results={};
  for(const mode of ['array','staged']){
  browser=await pw.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||await chromium.executablePath(),args:chromium.args,headless:true});

   const context=await browser.newContext(),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
   await page.goto('http://127.0.0.1:'+server.address().port+'/#export');await page.waitForFunction(()=>S._bootReady||S._bootError,null,{timeout:60000});
   results[mode]=await page.evaluate(async mode=>{
    if(S._bootError)throw Error(JSON.stringify(S._bootError));
    S.rows=[];S.view=[];S.settings.autoStdDims=false;S.settings.autoOeAnomalyOnImport=false;S.settings.enrichRelatedOnImport=true;S.settings.priceIsCost=false;
    S.settings.enrichCols={name:true,applicability:true,category:true,tnved:true,weight:true,length:true,width:true,height:true};
    const numeric=new Set(['cost','weight','length','width','height']);
    async function apply(file,fields,body,key='article+brand'){
     const headers=fields.map(f=>f||'UserFlag');
     if(mode==='staged'){
      const quote=v=>'"'+String(v??'').replace(/"/g,'""')+'"';
      await Import.read(new File([[headers,...body].map(r=>r.map(quote).join(';')).join('\n')],file,{type:'text/csv'}));
     }else S.pending={file,headers,body,rows:body.slice(0,5)};
     S.pending.map=fields.map((field,i)=>({src:headers[i],field:field||'',target:field?(STD.find(s=>s.k===field)?.n||field):'UserFlag',type:numeric.has(field)?'num':'text',enabled:true,def:''}));
     Import.normalize();Import.render();document.querySelector('#impKey').value=key;document.querySelector('#impMode').value='upsert';document.querySelector('#impKeepVisibility').checked=true;document.querySelector('#impEnrichOnly').checked=true;document.querySelector('#impEnrichRelated').checked=true;
     await Import.apply();if(S._bootError||S._cacheWriteError)throw Error(String(S._bootError||S._cacheWriteError));
    }
    const columns=['article','brand','name','cost','oe_numbers','applicability','weight','length','width','height','category','tnved','barcode',null];
    const row=(article,brand,name='',cost='',oe='',app='',weight='',length='',width='',height='',category='',tnved='',barcode='',custom='')=>[article,brand,name,cost,oe,app,weight,length,width,height,category,tnved,barcode,custom];
    await apply('price.csv',['article','brand','cost','name'],[['0001','B1','10','Original'],['0002','B1','20',''],['0003','B1','30',''],['0004','B1','40',''],['DUP','B1','50',''],['DUP','B2','60',''],['DONOR','B1','70',''],['TARGET','B1','80','Keep']]);
    const price={parts:HVC.parts.size,rows:S.rows.length,costs:S.rows.map(p=>p.cost),pending:S._econPending};
    const source=[row('0001','B1','Name1','77','A11 / A12','Car1','0.5','20','10','5','Запчасти','8708999709','00000000123','user1'),row('0002','B1','','','OE2'),row('0003','B1','ConflictA','33','BAD'),row('0004','B1','Good','44','OE4'),row('DUP','','AMBIG','777'),row('DONOR','B1','Donor','','SHARED1','','0.8','4','5','6','Запчасти'),row('TARGET','B1','','','SHARED1')];
    for(let i=0;i<4100;i++)source.push(row('OUTSIDE'+i,'OTHER','','1.5'));
    source.push(row('00-01','b1','Name1','77','A13','Car2','0.5','20','10','5','Запчасти','8708999709','00000000123','user2'),row('0003','B1','ConflictB','33','BAD'),row('0004','B1','Good','44','OE4'));
    await apply('fields.csv',columns,source);
    const fields=['article','brand','originalArticle','name','cost','oe_numbers','oe_list','oe_norm','applicability','weight','length','width','height','category','tnved','barcode','analog_list','group_articles','custom','dimensionAnomalyBlocked','_dimensionImportIssues'];
    const snapshot=()=>S.rows.map(p=>Object.fromEntries(fields.map(k=>[k,k==='dimensionAnomalyBlocked'?!!p[k]:k==='_dimensionImportIssues'?JSON.parse(JSON.stringify(p[k]??null,(key,value)=>key==='at'?undefined:value)):(p[k]??null)]))).sort((a,b)=>(a.article+'|'+a.brand).localeCompare(b.article+'|'+b.brand));
    const enriched=snapshot();
    await apply('oe-fallback.csv',['article','brand','name','cost','oe_numbers'],[['FOREIGN','NEW','By unique OE','55','OE2'],['NO-MATCH','NEW','No','999','SHARED1']]);
    const fallback=snapshot();
    await apply('brand-conflict.csv',['article','brand','name','cost'],[['0004','B1','Wrong','88'],['0004','B2','Wrong','88']],'article');
    const conflict=snapshot();
    await apply('invalid-dim.csv',['article','brand','weight'],[['0001','B1','oops']]);const invalid=snapshot();
    const memory=JSON.stringify(invalid);db.close();await db.open();await loadAll();
    if(JSON.stringify(snapshot())!==memory)throw Error('Persist/reopen differs from memory');
    return {price,enriched,fallback,conflict,invalid,rows:S.rows.length,checkpoint:!!await db.meta.get(BrowserApplyCheckpoint.KEY),pending:S._econPending};
   },mode);
   assert.equal(errors.length,0,errors.join('\n'));await browser.close();browser=null;
  }
  assert.deepStrictEqual(results.staged,results.array,'staged lookup must match array/RAM Apply exactly');
  if(process.env.E2E_ACCURACY_OUTPUT)fs.writeFileSync(process.env.E2E_ACCURACY_OUTPUT,JSON.stringify(results,null,2));
  const r=results.staged,get=(rows,a,b='B1')=>rows.find(p=>p.article===a&&p.brand.toUpperCase()===b.toUpperCase());
  assert.equal(r.price.parts,0);assert.equal(r.price.rows,8);assert(r.price.pending);assert.equal(r.rows,8);assert(!r.checkpoint);assert(r.pending);
  const first=get(r.enriched,'0001');assert.equal(first.originalArticle,'0001');assert.equal(first.cost,77);assert.equal(first.name,'Name1');assert.equal(first.barcode,'00000000123');assert.equal(first.weight,0.5);assert.equal(first.length,20);assert.equal(first.width,10);assert.equal(first.height,5);assert.equal(first.tnved,'8708999709');assert.equal(first.custom.UserFlag,'user2');
  for(const oe of ['A11','A12','A13'])assert(first.oe_numbers.includes(oe));assert(first.applicability.includes('Car1'));assert(first.applicability.includes('Car2'));
  assert.equal(get(r.enriched,'0002').cost,20);assert.equal(get(r.enriched,'0003').cost,30);assert.equal(get(r.enriched,'0003').name,'');assert.equal(get(r.enriched,'0004').cost,44);
  assert.equal(get(r.enriched,'DUP').cost,50);assert.equal(get(r.enriched,'DUP','B2').cost,60);
  assert.equal(get(r.enriched,'TARGET').name,'Keep');assert.equal(get(r.enriched,'TARGET').weight,0.8);assert.equal(get(r.enriched,'TARGET').analog_list,'DONOR');assert.equal(get(r.enriched,'DONOR').analog_list,'TARGET');
  assert.equal(get(r.fallback,'0002').cost,55);assert.equal(get(r.fallback,'0002').name,'By unique OE');// analog_list is rebuilt from registered graph holders, not an outside SKU.
  assert.equal(get(r.fallback,'0002').originalArticle,'0002');assert.deepStrictEqual(r.conflict,r.fallback);
  assert.equal(get(r.invalid,'0001').weight,0.5);assert(get(r.invalid,'0001')._dimensionImportIssues.weight);
  if(process.env.E2E_ACCURACY_OUTPUT)fs.writeFileSync(process.env.E2E_ACCURACY_OUTPUT,JSON.stringify(results,null,2));
  console.log('OK: staged-vs-array full Apply parity + independent expectations: 8 SKU, 4110 source rows, 4 subsequent files, all selected fields and reopen; no first-price enrichment, cross-batch conflicts, normalized keys, ambiguous brands/OE, donor dimensions, unique OE fallback, custom fields, invalid dimensions, economics pending');
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1});
