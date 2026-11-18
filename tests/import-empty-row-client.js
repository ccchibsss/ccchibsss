// Пустая строка импорта: быстрый признак (v12.9.171) обязан совпадать с прежней
// проверкой «нет ни одной ячейки, у которой String(v).trim() !== ''».
// Именно здесь была ошибка: ячейка из одних пробелов/табуляции проходила быстрый
// путь как «значение», и строка больше не отбрасывалась.
// Запуск: node tests/import-empty-row-client.js
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');
const grab=(a,b)=>{const i=h.indexOf(a),j=h.indexOf(b,i);assert(i>0&&j>i,'не найден фрагмент '+a);return h.slice(i,j);};

const ctx={console};vm.createContext(ctx);
const xwsLine=grab('const XWS_ONLY','function encodeCp1251Strict');   // одна строка-константа
vm.runInContext(xwsLine+'\nthis.__xws=XWS_ONLY;',ctx);
// регулярка приходит из другого Realm'а (vm), поэтому instanceof RegExp здесь
// всегда false — проверяем по исходнику
assert(ctx.__xws&&typeof ctx.__xws.test==='function'&&ctx.__xws.source.includes('\\ufeff'),
  'константа XWS_ONLY найдена в сборке и включает NBSP/BOM');

// текущая логика consume (без побочных эффектов: только решение «пропустить»)
const skipNew=row=>{
  let plain=false;
  for(let i=0;i<row.length;i++){const v=row[i];if(v==null)continue;const t=typeof v;if(t==='number'||t==='boolean'){plain=1;break;}if(t==='string'&&v!==''&&!ctx.__xws.test(v)){plain=2;break;}}
  if(!plain&&!row.some(v=>String(v??'').trim()!==''))return true;
  return false;
};
const skipOld=row=>!row.some(v=>String(v??'').trim()!=='');

const VALS=[null,undefined,'','   ','\t','\n','\r\n','\u00a0','\ufeff','\u3000','0','0.0',0,-0,NaN,Infinity,
  false,true,'текст',' null ','NULL','\u0000','\u0001','  x  ',{},[''],['',''],{a:1}];
let cases=0,bad=0;
const check=row=>{cases++;if(skipOld(row)!==skipNew(row)){bad++;if(bad<8)console.log('расхождение',JSON.stringify(row),'пропустить старо:',skipOld(row),'ново:',skipNew(row));}};
for(const a of VALS)check([a]);
for(const a of VALS)for(const b of VALS){check([a,b]);check([undefined,a,undefined,b]);}
// случайные строки подлиннее
let seed=12345;const rnd=()=>{seed=(seed*1103515245+12345)&0x7fffffff;return VALS[seed%VALS.length];};
for(let i=0;i<30000;i++)check(Array.from({length:1+(i%7)},rnd));

assert.equal(bad,0);
console.log('OK: признак пустой строки совпадает с прежним на '+cases+' строках (0 расхождений):');
console.log('    строки из пробелов/табуляции/NBSP по-прежнему отбрасываются, числа и текст — нет');
