const fs=require('fs'),vm=require('vm'),assert=require('assert');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');
const a=h.indexOf('  async enrichOzonPreferred('),b=h.indexOf('  prepareOzonTyping(',a);
const c={S:{rows:[],settings:{}}};vm.createContext(c);vm.runInContext('this.P={'+h.slice(a,b)+'};',c);
const P=c.P;let mode='sql',hook=()=>{},uploadHook=()=>{};
P.processingAvailable=async()=>{};P.processingMode=()=>mode;P.ozonProcessingReference=()=>({});
P.acquireOzonReference=async()=>{uploadHook();return 'ozon:test'};P.releaseOzonReference=async()=>{};
P._fetch=async(path,opts)=>{const body=JSON.parse(opts.body);assert.equal(body.enabled,true);for(const p of body.rows)for(const key of ['_t','_bw','mp','_stdDimsCalc'])assert(!(key in p));hook();return {rows:body.rows.map(p=>({article:p.article,brand:p.brand,fields:{ozon_type:'NEW'},removed:[]}))}};
function reset(){mode='sql';hook=()=>{};uploadHook=()=>{};c.S.settings={};c.S.rows=[{article:'A',brand:'B',ozon_type:'OLD'}];return c.S.rows}
(async()=>{
 let rows=reset();uploadHook=()=>{c.S.settings.lastPersistError=''};
 hook=()=>{c.S.settings.cloudSyncState={at:Date.now(),status:'synced'};c.S.settings.unitEconomicsSynced={A:1}};
 await P.enrichOzonPreferred(rows);assert.equal(rows[0].ozon_type,'NEW');
 rows=reset();hook=()=>{c.S.settings.autoCategoryByName=true};await P.enrichOzonPreferred(rows);assert.equal(rows[0].ozon_type,'NEW');
 rows=reset();hook=()=>{c.S.settings.autoCategoryByName=false};await assert.rejects(()=>P.enrichOzonPreferred(rows),/автокатегоризации/);assert.equal(rows[0].ozon_type,'OLD');
 rows=reset();hook=()=>{mode='browser'};await assert.rejects(()=>P.enrichOzonPreferred(rows),/режим обработки/);assert.equal(rows[0].ozon_type,'OLD');
 rows=reset();hook=()=>{c.S.rows=[]};await assert.rejects(()=>P.enrichOzonPreferred(rows),/каталог заменён/);assert.equal(rows[0].ozon_type,'OLD');
 rows=reset();hook=()=>{rows[0].name='edited'};await assert.rejects(()=>P.enrichOzonPreferred(rows),/строка A.*поля: name/);assert.equal(rows[0].ozon_type,'OLD');
 // Cached calculations and key insertion order do not change product inputs.
 rows=reset();rows[0]._t={tariff:1};rows[0].mp={ozon:{profit:1}};
 hook=()=>{rows[0]._t={tariff:2};rows[0]._bw=10;rows[0].mp={};rows[0]._stdDimsCalc={fields:['weight']}};
 await P.enrichOzonPreferred(rows);assert.equal(rows[0].ozon_type,'NEW');assert.equal(rows[0]._bw,10);
 rows=reset();rows[0].custom={a:1,b:2};
 hook=()=>{const p=rows[0];delete p.brand;p.brand='B';p.custom={b:2,a:1}};
 await P.enrichOzonPreferred(rows);assert.equal(rows[0].ozon_type,'NEW');
 for(const field of ['brand','oe_numbers','category','weight','ozon_type','_sources','custom']){
  rows=reset();hook=()=>{rows[0][field]=field==='ozon_type'?'MANUAL':{changed:true}};
  await assert.rejects(()=>P.enrichOzonPreferred(rows),e=>e.message.includes('поля: '+field));
  assert.notEqual(rows[0].ozon_type,'NEW');
 }
 // A late conflict must not apply any earlier staged Ozon response.
 rows=reset();rows.push(...Array.from({length:1000},(_,i)=>({article:'P'+i,brand:'B',ozon_type:'OLD'})));
 let n=0;hook=()=>{if(++n===2)rows[1000].name='changed'};
 await assert.rejects(()=>P.enrichOzonPreferred(rows),/поля: name/);assert(rows.every(p=>p.ozon_type==='OLD'));
 console.log('OK: Ozon ignores background metadata but rejects classifier, mode, catalog and row changes');
})().catch(e=>{console.error(e);process.exitCode=1});
