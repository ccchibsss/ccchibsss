const fs=require('fs'),assert=require('assert'),vm=require('vm');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');
const a=h.indexOf('const Import = {'),b=h.indexOf('  _relatedRows(',a),source=h.slice(a,b);
assert(source.includes('S.settings.importLightMode = true;'));
assert(!source.includes('lightModeOn'));
const p=source.indexOf('}else await runPipeline(true, {');assert(p>0);
const end=source.indexOf('\n        });',p);assert(end>p);
const call=source.slice(p,end);assert(call.includes('skipEconomics: true,'));
assert(!source.includes('Dash.render()'));assert(!source.includes('UE.render()'));
assert(source.includes('Прайс: сохранение без обогащения и расчёта экономики'));
assert(/id="impLightMode"[^>]*checked disabled/.test(h));
// Execute actual option construction with legacy light-mode setting off,
// independently of browser/SQL selection.
const options=call.slice(call.indexOf('{'))+'\n}';
for(const mode of ['browser','sql']){
 const c={changedRows:new Set(),nothingChanged:false,smallDelta:false,changedTouched:1,dedup:0,changedList:[],prog:()=>{},S:{settings:{importLightMode:false}},PyEngine:{processingMode:()=>mode}};
 vm.createContext(c);const result=vm.runInContext('('+options+')',c);assert.strictEqual(result.skipEconomics,true);assert(result.persist);
}
assert(h.includes("${skipEcon ? 'обогащение' : 'расчёт'} SKU"));
console.log('OK: browser and SQL import always defer economics, including legacy settings; first price remains load-only');
