const fs=require('fs'),vm=require('vm');
const html=fs.readFileSync(__dirname+'/../index.html','utf8');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const extract=name=>html.match(new RegExp('const '+name+' = \\{[\\s\\S]*?\\n\\};\\n'))[0];
const context={CATEGORY_TNVED_ROWS:input.rows};vm.createContext(context);
vm.runInContext(extract('OzonAuto')+'\n'+extract('CategoryTnved')+'\n'+extract('CsvNameMatcher')+'\nthis.C=CsvNameMatcher;',context);
const clean=v=>v instanceof Set ? [...v] : v;
// Cross-context Maps/Sets are identified by their tag rather than instanceof.
const replacer=(k,v)=>Object.prototype.toString.call(v)==='[object Map]'?Object.fromEntries(v):Object.prototype.toString.call(v)==='[object Set]'?[...v]:v;
process.stdout.write(JSON.stringify({lex:input.texts.map(t=>({words:context.C.words(t),stem:context.C.stem(t),variant:context.C.variant(context.C.words(t))})),index:context.C.index()},replacer));
