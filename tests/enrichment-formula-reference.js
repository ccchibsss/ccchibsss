const fs=require('fs'),vm=require('vm'),html=fs.readFileSync(__dirname+'/../index.html','utf8');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const start=html.indexOf('const ExprLang = (function () {'),end=html.indexOf('/* Поля, где встреченный JS Date',start);
const context={};vm.createContext(context);vm.runInContext(html.slice(start,end)+';this.E=safeEvalFormula;',context);
process.stdout.write(JSON.stringify(input.map(x=>{try {let v=context.E(x.expr,{...x.row,p:x.row});return {ok:true,value:v===undefined?null:v,undefined:v===undefined};}catch(e){return {ok:false};}})));
