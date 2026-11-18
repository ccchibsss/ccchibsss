const fs=require('fs'),vm=require('vm'),assert=require('assert'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const a=h.indexOf('const DataOnlyExport = {'),b=h.indexOf('\nconst Exp = {',a);assert(a>0&&b>a);
const source=h.slice(a,b);assert(!/await (?:ensureEconomics|.*prepareOzonTyping|.*_syncCatalog)/.test(source));
assert(h.includes('data-etab="data"'));assert(h.includes('id="exportPanelData"'));
let format='csv',mode='browser',blob,request,saves=0;
const button={disabled:false},rows=[{article:'00123',name:'=CMD()',custom:{extra:'OE;1'},netProfit:999,_t:{x:1},visible:false}];
const c={STD:[{k:'article',n:'Артикул'},{k:'name',n:'Название'},{k:'weight',n:'Вес'}],S:{rows,custom:[{key:'extra',name:'Своя'}]},Set,JSON,Blob,AbortController,setTimeout:fn=>{fn();return 1},clearTimeout(){},
 $:id=>id==='#dataExportRun'?button:{value:format},withProgress:async(a,b,f)=>f(),safeCsvText:v=>String(v??'').replace(/^=/,"'="),storageErrorText:String,Toast:{err:m=>{throw Error(m)}},
 PyEngine:{processingMode:()=>mode,processingAvailable:async()=>{},base:()=>'',token:()=> 'token'},persistNow:async()=>{saves++;return true},
 fetch:async(path,opts)=>{request={path,body:JSON.parse(opts.body)};return {ok:true,blob:async()=>new Blob(['SQL'])}},
 Exp:{download:b=>{blob=b}},
 URL:{createObjectURL:b=>{blob=b;return 'blob:test'},revokeObjectURL(){}},document:{createElement:()=>({click(){},remove(){}}),body:{appendChild(){}}},
 XLSX:{utils:{aoa_to_sheet:table=>{assert(!table[0].includes('netProfit'));return {}},sheet_add_aoa:(ws,table)=>{assert.equal(table[0][0],'00123')},book_new:()=>({}),book_append_sheet(){}},write:()=>new Uint8Array([1])}};
// Isolated UI contract stubs; real ZIP/OPFS values are checked in Chromium.
c.BrowserExportSpool={create:async()=>{let parts=[];return {write:async p=>parts.push(...p),finish:async type=>new Blob(parts,{type}),abort:async()=>{parts=[]}}}};
c.BrowserExportZip={create:async()=>({sheet:()=>({w(){},end(){}}),flush:async()=>{},add(){},finish:async()=>new Blob(['xlsx']),abort:async()=>{}})};
c.COL_LET=i=>String.fromCharCode(65+i);c.Exp._cx=()=>'';c.Exp._xE=String;c.Exp._sheetOpen=()=>'';c.Exp._stylesXml=()=>'';c.Exp._yield=async()=>{};
vm.createContext(c);vm.runInContext(source+';this.E=DataOnlyExport;',c);
(async()=>{
 await c.E.run();const csv=await blob.text();assert(csv.includes('00123'));assert(csv.includes("'=CMD()"));assert(csv.includes('OE;1'));assert(!csv.includes('netProfit'));assert(!csv.includes('999'));assert.equal(saves,0);assert(!button.disabled);
 format='xlsx';await c.E.run();assert(!button.disabled);
 mode='sql';await c.E.run();assert.equal(saves,1);assert.equal(request.path,'/export/data-only.xlsx');assert(request.body.columns.some(c=>c.custom));assert(!request.body.rows);
 let written='',closed=0,piped=0,aborted=0;
 c.window={showSaveFilePicker:async()=>({createWritable:async()=>({write:async text=>{written+=text},close:async()=>{closed++},abort:async()=>{aborted++}})})};
 mode='browser';format='csv';await c.E.run();assert(written.includes('00123'));assert(written.includes("'=CMD()"));assert.equal(closed,1);
 mode='sql';c.fetch=async()=>({ok:true,body:{pipeTo:async sink=>{piped++;await sink.close()}},blob:async()=>{throw Error('stream must not build blob')}});
 await c.E.run();assert.equal(piped,1);assert.equal(closed,2);assert(!button.disabled);
 // User cancellation of the destination picker performs no persistence/upload.
 const beforeSaves=saves;c.window.showSaveFilePicker=async()=>{throw Object.assign(Error('cancel'),{name:'AbortError'})};
 await c.E.run();assert.equal(saves,beforeSaves);assert(!button.disabled);
 // A failed writer aborts rather than publishing a partial CSV.
 c.window.showSaveFilePicker=async()=>({createWritable:async()=>({write:async()=>{throw Error('disk full')},abort:async()=>{aborted++}})});
 mode='browser';await assert.rejects(()=>c.E.run());assert.equal(aborted,1);assert(!button.disabled);
 console.log('OK: separate values-only export in browser and SQL, all rows, custom fields and no calculation path');
})().catch(e=>{console.error(e);process.exitCode=1});
