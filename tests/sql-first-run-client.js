const fs=require('fs'),vm=require('vm'),assert=require('assert');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');
const c={S:{rows:[],settings:{secret:'keep',manualToken:'keep'},custom:[{key:'custom'}],catalogVersion:0},
 db:{products:{count:async()=>0},meta:{get:async()=>null}},codeFieldsToStr:()=>{},normalizeFormatSettings:()=>{},
 HVC:{load:async()=>{}},StorageCtl:{catalogToken:()=> 'empty'},askConfirm:async()=>{throw Error('no migration needed')},
 loadAll:async()=>{throw Error('must not read browser catalog without approval')}};
vm.createContext(c);
const a=h.indexOf('  async loadSqlCatalog() {'),b=h.indexOf('  processingMode()',a);
vm.runInContext('this.P={'+h.slice(a,b)+'};',c);
const P=c.P;P.readSqlCatalog=async()=>({exists:false,revision:'',rows:[],metadata:{}});
P.saveSqlCatalog=async()=>{throw Error('must not write empty catalog during hydration')};
(async()=>{
 await P.loadSqlCatalog();assert.equal(c.S.rows.length,0);assert.equal(c.S._sqlCatalogRevision,'');
 assert.equal(c.S.settings.secret,'keep');assert.equal(c.S.custom[0].key,'custom');assert.equal(c.S.catalogVersion,1);
 // Successful first boot allows the existing first-price persistence entry.
 c.S._bootReady=true;c.S.rows=[{article:'001'}];c.persistNow=async()=>true;
 vm.runInContext(h.slice(h.indexOf('function storageErrorText('),h.indexOf('async function storageFreeInfo(')),c);
 assert.equal(await c.persistImportOrThrow('Прайс не сохранён'),true);
 // A missing catalog must never wipe rows already present in memory.
 await assert.rejects(()=>P.loadSqlCatalog(),/во вкладке есть строки/);assert.equal(c.S.rows[0].article,'001');
 // Existing browser catalog still needs explicit migration approval.
 c.db.products.count=async()=>12;c.askConfirm=async()=>false;
 await assert.rejects(()=>P.loadSqlCatalog(),/отменён/);assert.equal(c.S.rows[0].article,'001');
 let migrated=false,saved=false;
 c.askConfirm=async()=>true;c.loadAll=async legacy=>{assert(legacy);migrated=true;c.S.rows=[{article:'BROWSER'}]};
 P.saveSqlCatalog=async()=>{saved=true};await P.loadSqlCatalog();assert(migrated&&saved);assert.equal(c.S.rows[0].article,'BROWSER');
 // SQL offline/malformed reads still fail closed and do not appear as empty.
 P.readSqlCatalog=async()=>{throw Error('HTTP 401')};
 await assert.rejects(()=>P.loadSqlCatalog(),/HTTP 401/);assert.equal(c.S.rows[0].article,'BROWSER');
 console.log('OK: empty SQLite first boot, first price save, protected memory, migration consent and offline rejection');
})().catch(e=>{console.error(e);process.exitCode=1});
