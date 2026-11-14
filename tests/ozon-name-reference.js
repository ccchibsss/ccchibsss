const fs=require('fs'),vm=require('vm'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const input=JSON.parse(fs.readFileSync(0,'utf8')),ctx={};vm.createContext(ctx);
const la=h.indexOf('const OzonNameLexicon = (() => {');
vm.runInContext(h.slice(la,h.indexOf('\nif (typeof globalThis',la))+';globalThis.OzonNameLexicon=OzonNameLexicon;',ctx);
vm.runInContext(h.slice(h.indexOf('const OzonAuto = {'),h.indexOf("if (typeof globalThis !== 'undefined') globalThis.OzonAuto = OzonAuto;"))+'globalThis.OzonAuto=OzonAuto;',ctx);
ctx.OzonReference={strictKey:v=>String(v||'').normalize('NFC').trim().toLowerCase().replace(/\s+/g,' '),version:()=> 'test'};
ctx.CategoryTnved={norm:v=>String(v||'').trim().toLowerCase()};ctx.CATEGORY_TNVED_ROWS=[];ctx.OZON_NAME_RULES_VERSION='test';ctx.OzonCat={TYPES:input.types};
process.stdout.write(JSON.stringify(input.rows.map(p=>ctx.OzonAuto.detail(p))));
