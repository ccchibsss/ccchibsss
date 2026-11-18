// Пустая строка импорта (v12.9.171): решение обязано совпадать с прежним
// выражением !row.some(v => String(v ?? '').trim() !== '').
//
// История вопроса. В 12.9.171 проверку заменили быстрым признаком «в строке
// есть значение». Оказалось, это НЕ эквивалентно: ячейка из одних пробелов,
// табуляции или NBSP непустая как значение, но строка с ней считается пустой —
// такие строки переставали отбрасываться (2 326 расхождений из 21 656).
// Замену на дешёвый проход проверили и отвергли и по скорости: она оказалась на
// 20–70 % медленнее прежнего выражения, которое останавливается на первой же
// заполненной ячейке. В сборке осталось прежнее выражение, и этот тест следит,
// чтобы его снова не «оптимизировали» мимо поведения.
// Запуск: node tests/import-empty-row-client.js
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');

// Блок проверки вынимаем ИЗ СБОРКИ, а не переписываем в тесте заново.
const BLOCK=/if\(!row\.some\(v=>String\(v\?\?''\)\.trim\(\)!==''\)\)return;/;
const found=h.match(BLOCK);
assert(found,'в сборке нет прежней проверки пустой строки — её заменили, поведение надо доказать заново');
const skipNew=(()=>{
  const fn=new Function('row','let skip=false;'+found[0].replace(/\breturn;/,'{skip=true;}')+'return skip;');
  return row=>fn(row);
})();
// И убеждаемся, что других решений «строку пропустить» в consume нет.
const consumeStart=h.indexOf('const consume=row=>{');
assert(consumeStart>0,'не найден consume импорта');
const consumeEnd=h.indexOf('buffer.push(row);total++;',consumeStart);
assert(consumeEnd>consumeStart,'не найден конец consume');
const consumeBody=h.slice(consumeStart,consumeEnd);
/* В consume ровно два выхода «строку не берём»: проверка пустой строки и
   «ещё нет заголовков» (строка уходит в prefix). Появится третий — тест
   остановится: его поведение здесь не доказано. */
const returns=[...consumeBody.matchAll(/\breturn;/g)].length;
assert.equal(returns,2,'в consume изменилось число выходов — проверьте новый отдельно');

const skipOld=row=>!row.some(v=>String(v??'').trim()!=='');

// Корпус: типовые строки прайса + редкие типы + случайные сочетания.
const VALS=[[],[''],['   '],['\t'],['\n'],['\r\n'],['\u00a0'],['\ufeff'],['\u3000'],['\u200b'],[' \u00a0\t'],
  [null],['',null,''],['x'],[' x '],['0'],[-0],[0],[1],[-1],[NaN],[Infinity],[-Infinity],
  [false],[true],[false,true],['',''],[null,null,null],[' ','x'],['x',' '],
  [[],[]],[['']],[[null]],[{}],[{toString(){return ''}}],[{toString(){return 'x'}}],[10n],[Symbol('s')],[() => {}]];
for(let i=0;i<30000;i++){
  const row=[],n=Math.floor(Math.random()*6);
  for(let k=0;k<n;k++){
    const t=Math.random();
    if(t<0.3)row.push('');
    else if(t<0.45)row.push(' \t\u00a0'.slice(0,1+Math.floor(Math.random()*3)));
    else if(t<0.6)row.push(null);
    else if(t<0.7)row.push(undefined);
    else if(t<0.8)row.push(Math.random()<0.5?0:Math.floor(Math.random()*1e6));
    else if(t<0.9)row.push(Math.random()<0.5?'':'Текст '+i);
    else row.push(Math.random()<0.5?[]:'');
  }
  VALS.push(row);
}
let bad=0;
for(const row of VALS){
  const now=skipNew(row),was=skipOld(row);
  if(now!==was){
    bad++;
    if(bad<=8)console.error('расхождение',JSON.stringify(row),'пропустить старо:',was,'ново:',now);
  }
}
assert.equal(bad,0,'расхождений с прежним признаком: '+bad+' из '+VALS.length);
console.log('OK: признак пустой строки совпадает с прежним на '+VALS.length+' строках (0 расхождений):');
console.log('    строки из пробелов/табуляции/NBSP по-прежнему отбрасываются, числа и текст — нет');
