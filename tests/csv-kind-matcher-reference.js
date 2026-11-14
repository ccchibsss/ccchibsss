const fs=require('fs'),vm=require('vm');
const html=fs.readFileSync(__dirname+'/../index.html','utf8');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const extract=name=>html.match(new RegExp('const '+name+' = \\{[\\s\\S]*?\\n\\};\\n'))[0];
const context={CATEGORY_TNVED_ROWS:input.rows};vm.createContext(context);
const a=html.indexOf('const OzonNameLexicon = (() => {'), b=html.indexOf('\nif (typeof globalThis',a);
vm.runInContext(html.slice(a,b)+'\n'+extract('NameCategory')+'\n'+extract('OzonAuto')+'\n'+extract('CategoryTnved')+'\n'+extract('CsvNameMatcher')+'\nthis.C=CsvNameMatcher;',context);
const clean=v=>v instanceof Set ? [...v] : v;
// Cross-context Maps/Sets are identified by their tag rather than instanceof.
const replacer=(k,v)=>Object.prototype.toString.call(v)==='[object Map]'?Object.fromEntries(v):Object.prototype.toString.call(v)==='[object Set]'?[...v]:v;
process.stdout.write(JSON.stringify(input.products.map(p=>({texts:context.C.texts(p.name),candidates:context.C.candidates(p.name,p.brand),guess:context.C.guess(p)})),replacer));
