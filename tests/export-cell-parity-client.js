// Паритет быстрых путей экспорта (v12.9.171) с прежними реализациями — байт в байт.
// Старые _xE/_txt/_cx/safeCsvText вшиты ниже ДОСЛОВНО из коммита 135a932:
// если кто-то ещё раз «ускорит» эти функции и молча изменит текст готовых
// файлов, этот тест упадёт. Именно так была поймана ошибка с юникод-пробелом
// впереди «=»: строка перестала получать апостроф и стала формулой в Excel.
// Запуск: node tests/export-cell-parity-client.js
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');
const grab=(a,b)=>{const i=h.indexOf(a),j=h.indexOf(b,i);assert(i>0&&j>i,'не найден фрагмент '+a);return h.slice(i,j);};

// ---- 1. текущие реализации из сборки ----
const ctx={console};
vm.createContext(ctx);
vm.runInContext([
  'var XLSX_CELL_MAX=32767;',
  'var XML_ILLEGAL_RE=/[\\u0000-\\u0008\\u000B\\u000C\\u000E-\\u001F\\uFFFE\\uFFFF]/;',
  grab('function needsCellClean','/* v12.9.171: однопроходное'),
  grab('const XESC','const XTXT_FAST_BAD'),            // XESC, xescFn, XESC_TEST
  grab('const XTXT_FAST_BAD','const utf8enc'),         // XTXT_FAST_BAD, XTXT_LEAD_UNICODE
  'const XCX_FAST_BAD = XTXT_FAST_BAD;',
  grab('function safeCsvText','function encodeCp1251Strict'),
  grab('function clampCellText','/* v12.1: диагностика выборки'),
  'const E={'+grab('  _xE(s) {','  _STY:')+grab('  _txt(v) {','  _cx(L, R, st, v, fml) {')+grab('  _cx(L, R, st, v, fml) {','  _sheetOpen(freezeXY) {')+'};',
  // новые _cx/_xE в сборке обращаются к объекту Exp — заводим его в окружении
  'const Exp=E;this.E=E;this.safeCsvText=safeCsvText;',
  // stripXmlIllegal/clampCellText тоже берём ИЗ СБОРКИ: именно здесь стоял
  // неглобальный XML_ILLEGAL_RE и терял все управляющие символы, кроме первого
  'this.strip=stripXmlIllegal;this.clamp=clampCellText;'
].join('\n'),ctx);
const E=ctx.E,safeNew=ctx.safeCsvText,stripNew=ctx.strip,clampNew=ctx.clamp;

// ---- 2. прежние реализации (дословно из 135a932) ----
const OLD_CELLS = "  _xE(s) { return String(s).replace(/[\\u0000-\\u0008\\u000B\\u000C\\u000E-\\u001F\\uFFFE\\uFFFF]/g, '�').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\"/g, '&quot;').replace(/\\r/g, '&#13;'); },\n  _txt(v) {\n    /* v12.2: Excel не принимает ячейку длиннее 32 767 символов — иначе\n       XLSX.write падает с «Text length must not exceed 32767 characters». */\n    const sv = clampCellText(v == null ? '' : v, XLSX_CELL_MAX);\n    if (!sv) return sv;\n    /* Excel trims leading spaces/control whitespace before deciding whether a\n       cell is a formula. Проверяем первый непробельный символ, а не только\n       sv[0], и всегда оставляем значение текстовым. */\n    const lead = (/^[\\s\\u00a0]*/.exec(sv) || [''])[0];\n    const c = sv.charAt(lead.length);\n    const trigger = c === '=' || c === '+' || c === '-' || c === '@' ||\n      c === '\\t' || c === '\\r' || c === '\\v' || c === '\\f';\n    return trigger ? (\"'\" + sv) : sv;\n  },\n  _cx(L, R, st, v, fml) {\n    const x = Exp._xE;\n    if (fml) {\n      return (typeof v === 'number')\n        ? `<c r=\"${L}${R}\" s=\"${st}\"><f>${x(fml)}</f><v>${v}</v></c>`\n        : `<c r=\"${L}${R}\" s=\"${st}\" t=\"str\"><f>${x(fml)}</f><v>${x(clampCellText(v == null ? '' : v, XLSX_CELL_MAX))}</v></c>`;\n    }\n    if (typeof v === 'number' && isFinite(v)) return `<c r=\"${L}${R}\" s=\"${st}\"><v>${v}</v></c>`;\n    const sv = String(v == null ? '' : v);\n    if (!sv) return '';\n    const safe = Exp._txt(sv);\n    /* стиль 9 — тот же базовый, но с quotePrefix=\"1\"; подставляем только там,\n       где не задан собственный стиль ячейки (0), чтобы не ломать форматы */\n    const st2 = (safe !== sv) ? 9 : st;\n    return `<c r=\"${L}${R}\" s=\"${st2}\" t=\"inlineStr\"><is><t xml:space=\"preserve\">${x(safe)}</t></is></c>`;\n  },";
const OLD_SAFE = "function safeCsvText(v) {\n  let s = stripXmlIllegal(v == null ? '' : v);\n  /* Текст из товаров или внешнего справочника не должен становиться формулой. */\n  if (/^[\\s\\u00a0]*[=+@]/u.test(s) || /^[ \\u00a0]*[\\t\\r\\n]/u.test(s) ||\n      (/^[\\s\\u00a0]*-/u.test(s) && !/^\\s*-\\d+(?:[.,]\\d+)?\\s*$/u.test(s))) s = \"'\" + s;\n  return s;\n}";

const oldStrip = v => String(v).replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\uFFFE\uFFFF]/g,' ');
/* Прежний _cx обращается к объекту Exp (так было в сборке), а _txt — через
   него же. Поэтому старые функции собираем ВНУТРИ одной функции-обёртки,
   где Exp — это тот же объект. */
const OldExp = new Function('clampCellText','XLSX_CELL_MAX',
  'const Exp = {' + OLD_CELLS + '}; return Exp;')(ctx.clampCellText, 32767);
const oldSafeFn = new Function('stripXmlIllegal','return (' + OLD_SAFE + ');')(oldStrip);

// ---- 3. значения: всё, где быстрый путь мог разойтись ----
const WS=['\u3000','\uFEFF','\u2028','\u2029','\u2000','\u2003','\u205F','\u1680','\u202F','\u00a0',' ','\t'];
const VALS=[
  '', ' ', 'обычное название', 'Амортизатор KYB', 'Амортизатор & < KYB > "кавычки"',
  '=SUM(A1)', '+7 900', '-5', '-5 шт', '@user', '  пробелы', '\u00a0nbsp', 'a\u0001b',
  'строка\rCR', 'таб\tтаб', '😀 эмодзи', 'x]]>y', '"кавычки"', '«ёлка»', '€ 12,50',
  'x'.repeat(32767), 'x'.repeat(32768), 'я'.repeat(40000),
  0, 12, 1.5, -5, -1e21, 1e21, NaN, Infinity, true, false, null, undefined,
  {a:1}, ['x',1]
];
for(const w of WS) for(const t of ['=1+1','+7 900','-5','@link','- 5','обычный','','=cmd|calc','-']) {
  VALS.push(w+t, w+w+t, 'x'+w+t);
}

// ---- 4. сравнение ----
let bad=0; const diffs=[];
const note=(what,v,a,b)=>{bad++;if(diffs.length<10)diffs.push({what,v,now:a,was:b});};

for(const v of VALS){ const now=E._xE(v),was=OldExp._xE(v); if(now!==was)note('_xE',v,now,was); }
for(const v of VALS){ const now=E._txt(v),was=OldExp._txt(v); if(now!==was)note('_txt',v,now,was); }
for(const v of VALS) for(const fml of [null,'A2*2','=1+1']) for(const st of [0,8]){
  const now=E._cx('C',5,st,v,fml),was=OldExp._cx('C',5,st,v,fml);
  if(now!==was)note('_cx fml='+fml+' st='+st,v,now,was);
}
for(const v of VALS){ const now=safeNew(v),was=oldSafeFn(v); if(now!==was)note('safeCsvText',v,now,was); }
/* stripXmlIllegal/clampCellText: раньше здесь стоял общий неглобальный
   XML_ILLEGAL_RE, и replace менял только ПЕРВЫЙ запрещённый символ — остальные
   попадали в XML файла. Проверяем строки с НЕСКОЛЬКИМИ такими символами. */
const CTRL=['\u0000','\u0001','\u0008','\u000B','\u000C','\u000E','\u001F','\uFFFE','\uFFFF'];
const dirty=[];
for(const a of CTRL)for(const b of CTRL){dirty.push('x'+a+'y'+b+'z','живой '+a+b+' текст',a+b);}
for(const v of VALS.concat(dirty)){
  const now=stripNew(v),was=String(v).replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\uFFFE\uFFFF]/g,' ');
  if(now!==was)note('stripXmlIllegal',v,now,was);
  const c1=clampNew(v,32767),c2=String(v==null?'':v).replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\uFFFE\uFFFF]/g,' ');
  const c3=c2.length>32767?(/[\uD800-\uDBFF]$/.test(c2.slice(0,32767))?c2.slice(0,32766):c2.slice(0,32767)):c2;
  if(c1!==c3)note('clampCellText',v,c1,c3);
}

if(bad){
  for(const d of diffs)console.error(d.what,'|',String(JSON.stringify(d.v)).slice(0,60),'\n  сейчас:',String(JSON.stringify(d.now)).slice(0,90),'\n  было:  ',String(JSON.stringify(d.was)).slice(0,90));
  throw new Error('расхождений с прежними реализациями: '+bad);
}
console.log('OK: паритет с прежними реализациями — '+VALS.length+' значений × (_xE, _txt, _cx с формулами и стилями, safeCsvText, stripXmlIllegal, clampCellText) + '+dirty.length+' строк с несколькими управляющими символами, 0 расхождений');
console.log('    включая юникод-пробелы (\\uFEFF, \\u2028, \\u3000…) впереди «=», «+», «-», «@» — регресс v12.9.171 закрыт тестом');
