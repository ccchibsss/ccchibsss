// Execute actual client methods: transport dispatch, successful confirmation and failure atomicity.
const assert=require('assert'),fs=require('fs'),vm=require('vm');
const html=fs.readFileSync(__dirname+'/../index.html','utf8');
const start=html.indexOf('  async enrichCategoryKinds('), end=html.indexOf('  async enrichNameCategories(',start);
const context={ozonSourceMap:p=>p._sources || {},CATEGORY_TNVED_ROWS:[['Cat','Kind','1111111111']],BASE_CATS:[['Cat']],
  CategoryTnved:{revision:'rev'},S:{cats:[],rules:[]},
  OzonAuto:{_index:()=>({heads:new Set()})},
  NameCategory:{hasExplicitCategorySource:()=>false,confirm:p=>{
    if(!p._categoryNameAutoValue) return false;
    p._categoryNameExplicit=true;delete p._categoryNameAutoValue;return true;
  }}};
vm.createContext(context);
vm.runInContext('this.client={'+html.slice(start,end)+'};',context);
const client=context.client;client.processingAvailable=async()=>true;
(async()=>{
  const p={article:'A',brand:'B',category:'Cat',category_type:'Kind',
    _categoryNameAutoValue:'Cat',_categoryKindAuto:{confirmed:false},_sources:{name:{file:'price'}}};
  const before=JSON.stringify(p);
  client._fetch=async()=>{throw Error('offline');};
  await assert.rejects(()=>client.confirmCategoryKind(p,true),/offline/);
  assert.strictEqual(JSON.stringify(p),before,'failure must not confirm original row');
  let request;
  client._fetch=async(url,options)=>{
    request=JSON.parse(options.body);
    assert.strictEqual(url,'/catalog/enrich-category-kind');
    return {rows:request.rows.map(row=>({article:row.article,brand:row.brand,
      fields:{category:row.category,category_type:row.category_type,_categoryNameExplicit:true,
        _categoryKindAuto:{confirmed:true},_sources:{category_type:{file:'confirmed'}}},
      removed:['_categoryNameAutoValue'],changed:true}))};
  };
  assert.strictEqual(await client.confirmCategoryKind(p,true),true);
  assert.strictEqual(request.operation,'confirm');assert.strictEqual(request.category_confirmed,true);
  assert.strictEqual(p._categoryKindAuto.confirmed,true);
  assert.strictEqual(p._categoryNameAutoValue,undefined);
  assert.strictEqual(p._categoryNameExplicit,true);
  const q={article:'Q',brand:'B'};
  client._fetch=async()=>({rows:[{article:'wrong',brand:'B',fields:{}}]});
  await assert.rejects(()=>client.enrichCategoryKinds(null,false,[q]),/Порядок/);
  assert.deepStrictEqual(q,{article:'Q',brand:'B'});
  const imported={article:'I',brand:'B',category_type:'Old',_categoryKindAuto:{type:'Old'},_sources:{name:{file:'price'}}};
  const importedBefore=JSON.stringify(imported);
  client._fetch=async()=>{throw Error('offline');};
  await assert.rejects(()=>client.importCategoryKind(imported,'New',{file:'import'}),/offline/);
  assert.strictEqual(JSON.stringify(imported),importedBefore);
  client._fetch=async(url,opts)=>{
    const req=JSON.parse(opts.body);request=req;
    assert.strictEqual(req.operation,'explicit_import');
    assert.strictEqual(req.rows[0].category_type,'New');
    assert.strictEqual(req.rows[0]._sources.category_type.file,'import');
    return {rows:[{article:'I',brand:'B',fields:{category_type:'New',_categoryKindStatus:'explicit',
      _sources:req.rows[0]._sources},removed:['_categoryKindAuto']}]};
  };
  await client.importCategoryKind(imported,'New',{file:'import'});
  assert.strictEqual(imported._categoryKindAuto,undefined);
  assert.strictEqual(imported.category_type,'New');
  assert.strictEqual(imported._sources.name.file,'price');
  const restored={article:'R',brand:'B',category_type:'Kind',_categoryKindAuto:{confirmed:false}};
  client._fetch=async(url,opts)=>{
    const req=JSON.parse(opts.body);assert.strictEqual(req.operation,'hydrate');
    return {rows:[{article:'R',brand:'B',fields:{_categoryKindStatus:'stale'},removed:[]}]};
  };
  await client.enrichCategoryKinds(null,false,[restored],'hydrate');
  assert.strictEqual(restored._categoryKindStatus,'stale');
  console.log('OK: SQL category kind client confirmation');
})().catch(e=>{console.error(e);process.exitCode=1;});
