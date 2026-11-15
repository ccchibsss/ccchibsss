const fs=require('fs'),vm=require('vm'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const inputs=JSON.parse(fs.readFileSync(0,'utf8'));
const a=h.indexOf('const num = v => {'),b=h.indexOf('\n};',a)+3;
const start=h.indexOf('function exportCatalogCellValue('),end=h.indexOf('\n}',start)+2;
const ctx={exportCellUnavailable:()=>false,useF:false,XLSX_CELL_MAX:32767,cx:(letter,row,style,value)=>value,sty:()=>0};vm.createContext(ctx);
const cellStart=h.indexOf('    const cellFor = (p, R, c, letter) => {'),cellEnd=h.indexOf('    for (let i = 0; i < rows.length; i += CH)',cellStart);
vm.runInContext(h.slice(a,b)+'\n'+h.slice(start,end)+'\n'+h.slice(cellStart,cellEnd)+`;this.run=x=>{
 const p={custom:x.raw};for(const k of x.dates||[])p.custom[k]=new Date('2026-01-01T00:00:00Z');
 for(const k of x.nonfinite||[])p.custom[k]=(x.special||{})[k]==='NaN'?NaN:(x.special||{})[k]==='-Infinity'?-Infinity:Infinity;
 const c={k:'c_value',g:'custom',custom:'value',txt:!!x.textual,f:x.formatted?'@':''};
 const v=x.xlsx?cellFor(p,2,c,'A'):exportCatalogCellValue(c,p);
 return v===undefined?null:v;};`,ctx);
process.stdout.write(JSON.stringify(inputs.map(x=>ctx.run(x))));
