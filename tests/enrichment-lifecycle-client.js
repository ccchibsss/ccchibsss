const fs=require('fs'),vm=require('vm'),assert=require('assert'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const a=h.indexOf('  prepareOzonTyping('),b=h.indexOf('  dimensionOeSnapshot(',a);
const ctx={S:{catalogVersion:1},OzonReference:{version:()=> 'tree:1:auto'},CategoryTnved:{revision:'rev'}};
ctx.TextEncoder=TextEncoder;vm.createContext(ctx);vm.runInContext(h.slice(h.indexOf('const SqlMemory = {'),h.indexOf('const PyEngine = {')),ctx);vm.runInContext('globalThis.P={'+h.slice(a,b)+'};',ctx);
const P=ctx.P;let mode='sql',calls=0;P.processingMode=()=>mode;
(async()=>{
 const row={article:'A',brand:'B',name:'Filter'},manual={article:'M',ozon_type:'Manual',ozon_type_src:'manual'};
 P.enrichOzonPreferred=async rows=>{calls++;assert.equal(rows.length,1);rows[0].ozon_type='Type';rows[0]._ozonNameStatus='auto';throw Error('offline');};
 await assert.rejects(()=>P.prepareOzonTyping([row,manual]));assert(!('ozon_type' in row));assert.equal(manual.ozon_type,'Manual');
 P.enrichOzonPreferred=async rows=>{rows[0].ozon_type='Type';ctx.S.catalogVersion++;};
 await assert.rejects(()=>P.prepareOzonTyping([row]));assert(!('ozon_type' in row));
 P.enrichOzonPreferred=async rows=>{rows[0].ozon_type='Type';row.name='Changed';};
 await assert.rejects(()=>P.prepareOzonTyping([row]));assert(!('ozon_type' in row));
 P.enrichOzonPreferred=async rows=>{rows[0].ozon_type='Type';rows[0]._ozonNameStatus='auto';};
 await P.prepareOzonTyping([row]);assert.equal(row.ozon_type,'Type');
 // Concurrent preview/validation must share completed typing, not reject
 // each other as stale or issue two identical server enrichments.
 const concurrent={article:'Q',brand:'B'};let requests=0,release;
 P.enrichOzonPreferred=async rows=>{requests++;await new Promise(r=>release=r);rows[0].ozon_type='Shared';};
 const first=P.prepareOzonTyping([concurrent]),second=P.prepareOzonTyping([concurrent]);
 await new Promise(r=>setImmediate(r));assert.equal(requests,1);release();
 await Promise.all([first,second]);assert.equal(requests,1);assert.equal(concurrent.ozon_type,'Shared');
 // Replacing the catalogue without incrementing a counter is still stale.
 const replaced={article:'R'};P.enrichOzonPreferred=async rows=>{rows[0].ozon_type='Wrong';ctx.S.rows=[];};
 await assert.rejects(()=>P.prepareOzonTyping([replaced]));assert(!replaced.ozon_type);
 ctx.HVC={ozonRevision:1};const referenceChanged={article:'H'};
 P.enrichOzonPreferred=async rows=>{rows[0].ozon_type='Wrong';ctx.HVC.ozonRevision++;};
 await assert.rejects(()=>P.prepareOzonTyping([referenceChanged]));assert(!referenceChanged.ozon_type);
 // Export uses the same cache-insensitive product comparison as import.
 const cached={article:'CACHE',custom:{a:1,b:2},_t:{old:true},mp:{profit:1}};
 P.enrichOzonPreferred=async rows=>{
   assert(!('_t' in rows[0]));assert(!('mp' in rows[0]));
   rows[0].ozon_type='Cached';cached._t={new:true};cached._bw=2;cached.mp={profit:3};
   cached.custom={b:2,a:1};
 };
 await P.prepareOzonTyping([cached]);assert.equal(cached.ozon_type,'Cached');assert.equal(cached._bw,2);
 // A failed draft operation must never mutate nested live source data.
 const isolated={article:'ISOLATED',custom:{vehicle:['original']},_sources:{category:{name:'original'}}};
 P.enrichOzonPreferred=async rows=>{
   rows[0].custom.vehicle.push('draft');rows[0]._sources.category.name='draft';throw Error('offline');
 };
 await assert.rejects(()=>P.prepareOzonTyping([isolated]),/offline/);
 assert.deepEqual(isolated.custom,{vehicle:['original']});assert.equal(isolated._sources.category.name,'original');
 // A real nested edit during a request is still a conflict, not overwritten.
 const edited={article:'EDITED',custom:{vehicle:['original']}};
 P.enrichOzonPreferred=async rows=>{rows[0].ozon_type='Wrong';edited.custom.vehicle.push('manual')};
 await assert.rejects(()=>P.prepareOzonTyping([edited]));assert(!edited.ozon_type);
 assert.deepEqual(edited.custom.vehicle,['original','manual']);
 mode='browser';P.enrichOzonPreferred=async()=>{throw Error('must not call server')};await P.prepareOzonTyping([{article:'X'}]);
 // Execute the actual cloud mapper and verify that SQL mode defers kind lifecycle.
 let deferred;
 Object.assign(ctx,{num:v=>Number(v)||0,nowISO:()=> 'now',optionalMarkBool:()=>undefined,
  CategoryTnved:{decodeCloud:()=>({}),hydrateCloud:(p,raw,defer)=>{deferred=defer;p._categoryKindAuto={type:'Kind'};}},
  OzonAssignmentCloud:{key:'_ozon',decode:()=>null},RecommendedPrice:{cloudKey:'_recommended',decode:()=>null}});
 const start=h.indexOf('function mapServerProduct('),end=h.indexOf('\n}',start)+2;
 vm.runInContext(h.slice(start,end)+';globalThis.mapProduct=mapServerProduct;',ctx);
 ctx.mapProduct({article:'A'},true);assert.equal(deferred,true);
 ctx.mapProduct({article:'A'});assert.equal(deferred,false);
 assert(h.includes("if(sqlHydration)await PyEngine.enrichCategoryKinds(null,false,pulledRows,'hydrate');\n        S.rows=pulledRows;"));
 for(const method of ['generateCsv','generateXlsx'])assert(h.includes('async '+method+'(rows, opts, prog) {\n    await PyEngine.prepareOzonTyping(rows);'));
 assert(h.includes("PyEngine.processingMode()!=='sql' && !p.ozon_type"));
 // Execute the real preview renderer up to its await boundary. A superseded
 // request must not touch DOM elements after typing finishes.
 const previewStart=h.indexOf('  renderInView() {',h.indexOf('const OzonExport = {'));
 const previewEnd=h.indexOf('  /* v12.1:',previewStart);
 let domWrites=0;const releases=[];
 ctx.PyEngine={prepareOzonTyping:()=>new Promise(r=>releases.push(r))};
 ctx.$=selector=>{if(selector==='#ozViewScope')return {value:'filter'};domWrites++;return null;};
 ctx.Toast={err:()=>{throw Error('unexpected preview failure')}};
 vm.runInContext('this.preview={'+h.slice(previewStart,previewEnd)+'};',ctx);
 ctx.preview.getRows=()=>[];
 const oldPreview=ctx.preview.renderInView(),newPreview=ctx.preview.renderInView();
 ctx.preview._renderInViewRequest++; // a later UI request supersedes both
 releases.forEach(r=>r());await Promise.all([oldPreview,newPreview]);assert.equal(domWrites,0);
 console.log('OK: SQL export typing and staged hydration lifecycle');
})().catch(e=>{console.error(e);process.exitCode=1});
