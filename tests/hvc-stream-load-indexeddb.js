// Real shipped Dexie: bounded, snapshot-consistent HVC load with atomic publication.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),fidb=require('fake-indexeddb');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');
const c={...fidb,console,setTimeout,clearTimeout,queueMicrotask,AbortController,structuredClone,performance,CustomEvent:class{},location:{protocol:'http:'},navigator:{},S:{settings:{},_bootReady:true},StorageCtl:{refresh(){}},Toast:{warn(){},err(){}},num:x=>Number(x)||0};c.self=c;c.window=c;vm.createContext(c);
vm.runInContext([...h.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1],c);
vm.runInContext(h.slice(h.indexOf('const _normArticleCache ='),h.indexOf('/* Артикул — всегда текст.'))+';this.norm=normArticle;',c);
const a=h.indexOf('const HVC = {'),b=h.indexOf('\n};\n/* OzonCat',a)+3;vm.runInContext(h.slice(a,b)+';this.H=HVC;',c);
vm.runInContext("this.db=new Dexie('hvc-stream-test');db.version(1).stores({hvcOe:'++id,&oeNorm',hvcParts:'++id,&key',hvcCross:'++id,&key',hvcPrices:'++id,&key',meta:'key'});",c);
const H=c.H,db=c.db,N=3507,names=['oe','parts','cross','prices','byArt','byOe','bySku','ozonApplicability'];
const plain=x=>JSON.parse(JSON.stringify(x));const state=()=>plain({maps:Object.fromEntries(names.map(k=>[k,[...H[k]].map(([k,v])=>[k,v instanceof Set?[...v]:v])])),rules:H.rules,exclusions:H.exclusions,template:H.descTemplate,revision:H.ozonRevision});
(async()=>{
 await db.open();
 await db.hvcOe.bulkAdd(Array.from({length:N},(_,i)=>({oeNorm:'OE-'+i,name:'oe-'+i,ozon_conflict:i===0})));
 await db.hvcParts.bulkAdd(Array.from({length:N},(_,i)=>({key:'ART-'+i+'|Brand',artikul:'ART-'+i,brand:'Brand',name:'part-'+i,length:10})));
 await db.hvcPrices.bulkAdd(Array.from({length:N},(_,i)=>({key:'ART-'+i+'|Brand',cost:12.5})));
 await db.hvcCross.bulkAdd(Array.from({length:N},(_,i)=>({key:'OE'+i+'|ART'+i+'|BRAND'})));
 await db.hvcOe.add({oeNorm:'OE0',name:'',ozon_conflict:false,applicability:'cars'});
 await db.hvcParts.add({key:'ART 0|brand',artikul:'art 0',brand:'brand',name:'',length:0,weight:2});
 await db.hvcPrices.add({key:'ART 0|brand',cost:0});
 await db.hvcCross.add({key:'EXTRA\u001FART0|BRAND'});
 await db.meta.bulkAdd([{key:'hvcRules',value:{rules:{global_markup:7},exclusions:['test'],descTemplate:'template'}},{key:'ozonApplicability',value:[['cars',{category:'C',type:'T'}]]}]);
 const refs=Object.fromEntries(names.map(k=>[k,H[k]]));let maxBatch=0,collections=[];
 const proto=db.Collection.prototype,toArray=proto.toArray;
 proto.toArray=function(...args){collections.push({table:this._ctx.table.name,limit:this._ctx.limit});return toArray.apply(this,args).then(rows=>{maxBatch=Math.max(maxBatch,rows.length);return rows})};
 assert.equal(await H.load(),N);assert(maxBatch<=1000);assert(collections.length>16);assert(collections.every(c=>c.limit<=1000));proto.toArray=toArray;
 for(const name of names)assert.strictEqual(H[name],refs[name]);
 assert.equal(H.oe.size,N);assert.equal(H.prices.size,N);assert.equal(H.cross.size,N+1);assert.equal(H.parts.get('ART0|BRAND').name,'part-0');assert.equal(H.parts.get('ART0|BRAND').length,10);assert.equal(H.parts.get('ART0|BRAND').weight,2);
 assert.equal(H.oe.get('OE0').name,'oe-0');assert(H.oe.get('OE0').ozon_conflict);assert.equal(H.oe.get('OE0').applicability,'cars');assert.equal(H.prices.get('ART0|BRAND').cost,12.5);
 assert(H.bySku.get('ART0').has('ART0|BRAND'));assert(H.byArt.get('ART0|BRAND').has('EXTRA'));assert(H.byOe.get('EXTRA').has('ART0|BRAND'));assert.equal(H.ozonApplicability.get('cars').category,'C');
 assert.deepEqual(plain(H.rules),{global_markup:7});assert.equal(H.descTemplate,'template');
 // Inject a failure in the LAST registry, after earlier tables were consumed.
 const before=state(),oldCache={sentinel:true};H._identityCache=oldCache;
 await db.hvcParts.update(1,{name:'not published yet'});await db.meta.put({key:'hvcRules',value:{rules:{global_markup:99},exclusions:[],descTemplate:'new template'}});
 const fail=row=>{if(row.id===1501)throw Error('late read failure');return row};db.hvcPrices.hook('reading',fail);
 assert.equal(await H.load(),0);assert.deepEqual(state(),before);assert.strictEqual(H._identityCache,oldCache);assert(c.S._hvcLoadError.includes('late read failure'));assert.equal(await H.save(),false);
 db.hvcPrices.hook('reading').unsubscribe(fail);assert.equal(await H.load(),N);assert.equal(H.parts.get('ART0|BRAND').name,'not published yet');assert.equal(H.descTemplate,'new template');assert.equal(c.S._hvcLoadError,'');
 // A writer scheduled while the first table is read waits for ALL tables and
 // metadata, so publication cannot mix two registry revisions.
 let queued=false,writer;
 const queueWriter=row=>{if(!queued){queued=true;writer=c.Dexie.ignoreTransaction(()=>db.transaction('rw',db.hvcOe,db.hvcParts,db.hvcPrices,db.hvcCross,db.meta,async()=>{
  await db.hvcOe.update(2,{name:'new revision'});await db.hvcParts.update(2,{name:'new revision'});await db.meta.put({key:'hvcRules',value:{rules:{global_markup:100},descTemplate:'revision 100'}});
 }));}return row};
 db.hvcOe.hook('reading',queueWriter);await H.load();db.hvcOe.hook('reading').unsubscribe(queueWriter);
 assert.equal(H.oe.get('OE1').name,'oe-1');assert.equal(H.parts.get('ART1|BRAND').name,'part-1');assert.equal(H.rules.global_markup,99);await writer;
 await H.load();assert.equal(H.oe.get('OE1').name,'new revision');assert.equal(H.parts.get('ART1|BRAND').name,'new revision');assert.equal(H.rules.global_markup,100);
 const stable=state();
 const guardStart=h.indexOf('  async assertWriter() {',h.indexOf('const BrowserApplyCheckpoint = {')),guardEnd=h.indexOf('\n  async begin()',guardStart);
 vm.runInContext("this.BrowserApplyCheckpoint={KEY:'browserApplyCheckpoint',owner:null,"+h.slice(guardStart,guardEnd)+'};',c);
 await db.meta.put({key:'browserApplyCheckpoint',value:{owner:'other-tab'}});
 assert.equal(await H.load(),0);assert.deepEqual(state(),stable);
 c.BrowserApplyCheckpoint.owner='other-tab';assert.equal(await H.load(),N);assert.equal(c.S._hvcLoadError,'');
 await db.delete();console.log('OK: HVC streaming load <=1000 records, canonical/legacy merge parity, stable Map identities, snapshot consistency, late-failure preservation and Apply-owner guard');
})().catch(e=>{console.error(e);process.exitCode=1});
