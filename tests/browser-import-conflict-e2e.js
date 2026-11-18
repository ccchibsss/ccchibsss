// Real multi-tab conflict + preserved staged input + new-tab recovery.
const fs=require('fs'),http=require('http'),assert=require('assert');
const {chromium:pw}=require('playwright-core'),chromium=require('@sparticuz/chromium');
(async()=>{
 const html=fs.readFileSync(__dirname+'/../index.html');
 const server=http.createServer((req,res)=>{res.setHeader('Content-Type','text/html;charset=utf-8');res.end(html)});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await pw.launch({executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||await chromium.executablePath(),args:chromium.args,headless:true});
  const context=await browser.newContext();await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const errors=[];context.on('page',p=>p.on('pageerror',e=>errors.push(e.message)));
  const stale=await context.newPage(),url='http://127.0.0.1:'+server.address().port+'/#export';
  const ready=p=>p.waitForFunction(()=>S._bootReady||S._bootError,null,{timeout:60000});
  await stale.goto(url);await ready(stale);
  await stale.evaluate(async()=>{
   /* Кто публикует ревизию: перехватываем присваивание токена и вызов
      catalogValue, чтобы в сообщении об ошибке был стек, а не только факт. */
   window.__rev=[];
   let tok=S._catalogToken;
   Object.defineProperty(S,'_catalogToken',{configurable:true,enumerable:true,
     get(){return tok;},
     set(v){ if(v!==tok) window.__rev.push('TOKEN '+(new Error().stack||'').split('\n').slice(2,7).join(' | ')); tok=v; }});
   /* Что решила сверка и почему. */
   const _sv=StorageCtl.saveVerifiedMetadata.bind(StorageCtl);
   StorageCtl.saveVerifiedMetadata=async function(rows,withId){
     let r; try { r=await _sv(rows,withId); } catch(e){ window.__rev.push('VERIFY threw '+e.name+': '+e.message); throw e; }
     window.__rev.push('VERIFY '+r+' reason='+String(this._verifiedReason)+' rows='+rows.length+' counts='+(S._cacheLastWrite&&S._cacheLastWrite.count));
     return r;
   };
   const _da=StorageCtl.saveDiffAtomic.bind(StorageCtl);
   StorageCtl.saveDiffAtomic=function(a){ window.__rev.push('DIFF fullWrite='+a.fullWrite+' rowCount='+a.rowCount+' changed='+(Array.isArray(a.changedList)?a.changedList.length:'нет')); return _da(a); };
   const _cv=StorageCtl.catalogValue.bind(StorageCtl);
   StorageCtl.catalogValue=(...a)=>{const v=_cv(...a);window.__rev.push('PUBLISH '+v.revision+' :: '+(new Error().stack||'').split('\n').slice(2,7).join(' | '));return v;};
   S.rows=[{id:1,article:'00001',brand:'Brand',cost:10,custom:{}}];S._econPending=true;
   S.settings.autoStdDims=false;S.settings.autoOeAnomalyOnImport=false;S.settings.enrichRelatedOnImport=false;
   if(!await persistNow())throw Error('seed save failed');
   const token=S._catalogToken;
   if(!await persistNow())throw Error('baseline verification failed');
   window.dispatchEvent(new PageTransitionEvent('pagehide'));await _persistQueue;
   if(S._catalogToken!==token){
     const d={token:[token,S._catalogToken],reason:String(StorageCtl._verifiedReason),mode:PyEngine.processingMode(),rows:S.rows.length,disk:await db.products.count(),stage:await db.products_stage.count(),lastWrite:S._cacheLastWrite,econPending:!!S._econPending,aux:!!S._cacheAuxError,hvc:!!S._hvcPersistError,pending:_persistPending,dirty:_persistDirty};
     const m=await db.meta.get('catalog'),mc=await db.meta.get('custom'),ms=await db.meta.get('settings'),mt=await db.meta.get('tariffs');
     d.catalogOnDisk=m&&m.value&&m.value.revision;
     d.customEqual=StorageCtl.same(mc&&mc.value,S.custom);
     d.settingsEqual=StorageCtl.same(ms&&ms.value,{...S.settings,lastPersistError:''});
     d.tariffsEqual=StorageCtl.same(mt&&mt.value,S.tariffs);
     d.settingsDisk=ms&&ms.value&&Object.keys(ms.value).filter(k=>JSON.stringify(ms.value[k])!==JSON.stringify(({...S.settings,lastPersistError:''})[k]));
     d.lastPersistError=String(S.settings.lastPersistError||'');
     d.rev=(window.__rev||[]).slice(-6);
     throw Error('unchanged baseline created a false revision · '+JSON.stringify(d));
   }
   await Import.read(new File(['Артикул;Бренд;Наименование\n00001;Brand;Imported title\n'],'enrich.csv',{type:'text/csv'}));
   S.pending.map=S.pending.headers.map((src,i)=>({src,field:['article','brand','name'][i],target:['Артикул','Бренд','Наименование'][i],enabled:true,type:'text'}));Import.normalize();Import.render();
   document.querySelector('#impKey').value='article+brand';document.querySelector('#impOe').classList.remove('on');document.querySelector('#impEnrichRelated').checked=false;
   window.originalSource=S.pending.sourceId;window.originalToken=S._catalogToken;window.originalMap=JSON.stringify(S.pending.map);
  });
  const writer=await context.newPage();await writer.goto(url);await ready(writer);
  await writer.evaluate(async()=>{S.rows[0].cost=77;S._econPending=true;if(!await persistNow())throw Error('writer save failed');});
  await stale.evaluate(()=>{S.rows[0].cost=99;}); // RAM-only edit must survive recovery.
  await stale.click('#impApply');await stale.waitForSelector('#impConflictActions:not([hidden])');
  assert(await stale.evaluate(async()=>S.rows[0].cost===99&&S.pending.sourceId===originalSource&&S._catalogToken===originalToken&&(await db.products.get(1)).cost===77&&!await db.meta.get(BrowserApplyCheckpoint.KEY)));
  // Blocked popup and sessionStorage failure must not navigate or mutate RAM.
  await stale.evaluate(()=>{const open=window.open;window.open=()=>null;try{ImportConflictRecovery.open();throw Error('expected blocked popup')}catch(e){if(!e.message.includes('заблокировал'))throw e}finally{window.open=open}});
  const popup=context.waitForEvent('page');await stale.click('#impConflictResume');const fresh=await popup;await fresh.waitForLoadState();await ready(fresh);
  await fresh.waitForFunction(()=>S.pending&&document.querySelector('#mImport').classList.contains('on'),null,{timeout:60000});
  assert(await fresh.evaluate(()=>S.rows[0].cost===77&&S.pending.file==='enrich.csv'&&S.pending.body.length===1&&document.querySelector('#impKey').value==='article+brand'&&!document.querySelector('#impOe').classList.contains('on')&&!document.querySelector('#impEnrichRelated').checked));
  assert.equal(await fresh.evaluate(()=>JSON.stringify(S.pending.map)),await stale.evaluate(()=>originalMap));
  await fresh.click('#impApply');await fresh.waitForFunction(()=>!document.querySelector('#impApply').disabled&&!document.querySelector('#mImport').classList.contains('on'),null,{timeout:120000});
  assert(await fresh.evaluate(async()=>S.rows[0].cost===77&&S.rows[0].name==='Imported title'&&(await db.products.get(1)).name==='Imported title'&&!await db.meta.get(BrowserApplyCheckpoint.KEY)));
  assert(await stale.evaluate(()=>S.rows[0].cost===99&&S.pending.sourceId===originalSource&&S._catalogToken===originalToken));
  assert.equal(errors.length,0,errors.join('\n'));
  console.log('OK: genuine two-tab conflict blocks Apply without writes; new tab restores staged source/mapping/options, imports onto latest disk state; stale RAM untouched');
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1});
