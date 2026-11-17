// Shipped HVC + Dexie: large registry page migration, exact reload, atomic save.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),fidb=require('fake-indexeddb');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');
const c={...fidb,console,setTimeout,clearTimeout,queueMicrotask,AbortController,structuredClone,performance,CustomEvent:class{},location:{protocol:'http:'},navigator:{},S:{settings:{},_bootReady:true},StorageCtl:{refresh(){},assertCatalogFresh:async()=>{},isQuotaError:()=>false},Toast:{warn(){},err(){}},num:x=>Number(x)||0};c.self=c;c.window=c;vm.createContext(c);
vm.runInContext([...h.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1],c);
vm.runInContext(h.slice(h.indexOf('const _normArticleCache ='),h.indexOf('/* Артикул — всегда текст.')),c);
const a=h.indexOf('const HVC = {'),b=h.indexOf('\n};\n/* OzonCat',a)+3;vm.runInContext(h.slice(a,b)+';this.H=HVC;',c);
const same=h.indexOf('  same(a, b,');vm.runInContext('Object.assign(StorageCtl,{'+h.slice(same,h.indexOf('  async saveDiffAtomic(',same))+'});this.rehome=x=>x==null?x:JSON.parse(JSON.stringify(x));',c);
vm.runInContext("this.db=new Dexie('hvc-pages-test');db.version(1).stores({hvcOe:'++id,&oeNorm',hvcParts:'++id,&key',hvcCross:'++id,&key',hvcPrices:'++id,&key',meta:'key',products:'++id',products_stage:'++id',cats:'++id',rules:'++id',excs:'++id',imports:'++id',applyUndo:'++id,table,[table+pos]'});",c);
const H=c.H,db=c.db,N=20003,tables=['hvcOe','hvcParts','hvcCross','hvcPrices'],names=['oe','parts','cross','prices','byArt','byOe','bySku','ozonApplicability'];
const plain=x=>JSON.parse(JSON.stringify(x));
const state=()=>JSON.stringify(names.map(name=>[name,[...H[name]].map(([k,v])=>[k,Object.prototype.toString.call(v)==='[object Set]'?[...v]:v])]));
(async()=>{
 await db.open();for(const name of [...tables,'meta'])db[name].hook('reading',c.rehome);
 vm.runInContext("HVC.oe.set('OE0',{name:'legacy'});HVC.parts.set('A0|BRAND',{artikul:'A0',brand:'BRAND',name:'legacy'});HVC.cross.set('OE0\\u001fA0|BRAND',{oeNorm:'OE0',artKey:'A0|BRAND'});HVC.prices.set('A0|BRAND',{cost:12.5});",c);
 assert(await H.save());assert(!await db.meta.get('hvcStorage'));await H.load();
 vm.runInContext(`for(let i=1;i<${N};i++){const key='A'+i+'|BRAND',oe='OE'+i;HVC.oe.set(oe,{name:'OE '+i,ozon_conflict:i===1});HVC.parts.set(key,{artikul:'A'+i,brand:'BRAND',name:'Part '+i,custom:{code:'00042'}});HVC.cross.set(oe+'\\u001f'+key,{oeNorm:oe,artKey:key});HVC.prices.set(key,{cost:12.5});}`,c);
 let largest=0;for(const name of tables){const put=db[name].put.bind(db[name]);db[name].put=row=>{largest=Math.max(largest,row.values?.length||0);return put(row)}}
 const legacy=await db.hvcOe.toArray();const failMigration=()=>{throw Error('migration quota')};db.hvcPrices.hook('creating',failMigration);
 assert.equal(await H.save(),false);assert.deepEqual(await db.hvcOe.toArray(),legacy);assert(!await db.meta.get('hvcStorage'));db.hvcPrices.hook('creating').unsubscribe(failMigration);
 assert(await H.save());assert.equal(largest,1000);for(const name of tables){assert.equal(await db[name].count(),21);const page=await db[name].get(21);assert.equal(page.values.length,3)}
 const format=await db.meta.get('hvcStorage');assert(tables.every(name=>format.value[name].count===N));
 assert.equal(await H.load(),N);const before=state();db.close();await db.open();assert.equal(await H.load(),N);assert.equal(state(),before);
 assert.equal(H.parts.get('A20002|BRAND').custom.code,'00042');assert(H.byArt.get('A20002|BRAND').has('OE20002'));assert(H.oe.get('OE1').ozon_conflict);
 let writes=0;const count=()=>writes++;for(const name of tables)for(const event of ['creating','updating','deleting'])db[name].hook(event,count);
 assert(await H.save());assert.equal(writes,0,'unchanged pages must not be rewritten');
 H.parts.get('A1234|BRAND').name='changed';assert(await H.save());assert.equal(writes,1,'one changed object rewrites one page');
 const snapshot=async()=>{const result={};for(const name of [...tables,'meta'])result[name]=plain(await db[name].toArray());return result};
 const stable=await snapshot();H.oe.get('OE1').name='uncommitted';H.prices.get('A1|BRAND').cost=99;
 const fail=()=>{throw Error('late page write failure')};db.hvcPrices.hook('updating',fail);assert.equal(await H.save(),false);assert.deepEqual(await snapshot(),stable);db.hvcPrices.hook('updating').unsubscribe(fail);await H.load();
 const loaded=state(),revision=H.ozonRevision,page=await db.hvcPrices.get(21);page.values.pop();await db.hvcPrices.put(page);
 assert.equal(await H.load(),0);assert.equal(state(),loaded);assert.equal(H.ozonRevision,revision);assert.equal(await H.save(),false);await db.hvcPrices.put(stable.hvcPrices[20]);await H.load();
 const duplicate=await db.hvcParts.get(2);duplicate.values[0].key='A0|BRAND';await db.hvcParts.put(duplicate);assert.equal(await H.load(),0);assert.equal(state(),loaded);await db.hvcParts.put(stable.hvcParts[1]);await H.load();
 await db.meta.delete('hvcStorage');assert.equal(await H.load(),0);assert.equal(state(),loaded);await db.meta.put(format);await H.load();
 const bad=plain(format);bad.value.hvcOe.format='future';await db.meta.put(bad);assert.equal(await H.load(),0);assert.equal(state(),loaded);await db.meta.put(format);await H.load();
 await db.hvcCross.delete(1);assert.equal(await H.load(),0);assert.equal(state(),loaded);await db.hvcCross.put(stable.hvcCross[0]);await H.load();
 // Actual Apply undo also restores packed registries AND their format marker.
 const checkpointStart=h.indexOf('const BrowserApplyCheckpoint = {'),checkpointEnd=h.indexOf('/* Temporary target identity indexes:',checkpointStart);
 c.uid=()=> 'packed-undo';c.persistNow=()=>H.save();
 vm.runInContext(h.slice(h.indexOf('const BrowserImportIO = {'),checkpointStart),c);
 vm.runInContext(h.slice(checkpointStart,checkpointEnd)+';this.C=BrowserApplyCheckpoint;',c);
 const owner=await c.C.begin();H.parts.get('A1234|BRAND').name='rollback this';assert(await H.save());
 await c.C.restore(owner);assert.equal(await H.load(),N);assert.equal(state(),loaded);assert.equal(await db.applyUndo.count(),0);
 // Previously packed registries stay packed after shrinking, including empty.
 for(const name of ['oe','parts','cross','prices'])H[name].clear();vm.runInContext("HVC.oe.set('ONLY',{name:'one'});",c);
 assert(await H.save());assert.equal(await db.hvcOe.count(),1);for(const name of tables.slice(1))assert.equal(await db[name].count(),0);assert.equal(await H.load(),0);assert.equal(H.oe.get('ONLY').name,'one');assert.equal(c.S._hvcLoadError,'');
 // Wide logical rows must shrink packed pageSize and reopen exactly.
 vm.runInContext("for(let i=0;i<30;i++)HVC.oe.set('W'+i,{name:'Ж'.repeat(20000)});",c);
 assert(await H.save());const wideFormat=(await db.meta.get('hvcStorage')).value.hvcOe;
 assert(wideFormat.pageSize<1000);
 for(const row of await db.hvcOe.toArray())assert(JSON.stringify(row).length*2<512*1024);
 db.close();await db.open();await H.load();assert.equal(H.oe.size,31);assert.equal(H.oe.get('W29').name,'Ж'.repeat(20000));
 await db.delete();console.log('OK: HVC pages <=1000, legacy migration, exact reopen, unchanged/one-page delta, atomic rollback, corrupt/duplicate/missing pages and metadata fail closed, shrink/empty');
})().catch(e=>{console.error(e);process.exitCode=1});
