// Единицы весогабаритов: граммы/килограммы и миллиметры/сантиметры у разных
// брендов приводятся к одному виду (кг и см) без угадывания.
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const h = fs.readFileSync(__dirname + '/../index.html', 'utf8');

/* Вырезаем функции по балансу фигурных скобок: index.html — один файл, и
   подключать его целиком в тест нельзя. */
function grab(sig) {
  const i = h.indexOf(sig);
  assert(i >= 0, 'не найдено: ' + sig);
  let d = 0;
  for (let j = i; j < h.length; j++) {
    const c = h[j];
    if (c === '{') d++;
    else if (c === '}') { d--; if (!d) return h.slice(i, j + 1); }
  }
  throw new Error('незакрытая функция: ' + sig);
}
const lines = h.split('\n');
/* num / _POW10 / round вырезаем по границам объявлений: срез по номерам строк
   ломался при любой вставке выше и давал SyntaxError вместо понятной ошибки. */
const lineOf = sig => { const i = lines.findIndex(l => l.startsWith(sig)); assert(i >= 0, 'не найдено: ' + sig); return i; };
const utils = lines.slice(lineOf('const num = v => {'), lineOf('function debounce(')).join('\n');

const modStart = h.indexOf('/* ===== ЕДИНИЦЫ ВЕСОГАБАРИТОВ');
const modEnd = h.indexOf('function validCanonicalOvhNumber(v) {');
assert(modStart >= 0 && modEnd > modStart, 'модуль DimUnit не найден');
const dimUnitSrc = h.slice(modStart, modEnd);

const dimFns = [
  'function currentDimUnit(', 'function dimensionUnitInHeader(', 'function dimensionCellUnit(',
  'function parseDimensionOrVolume(', 'function parseDimensionCm(', 'function parseDimsTriple(',
  'function weightUnitInHeader(', 'function parseWeightKg(',
].map(grab).join('\n');

const dict = [
  { c: 'Датчик давления', l: 6, w: 4, h: 4, wt: 0.05 },
  { c: 'Фильтр масляный', l: 12, w: 10, h: 8, wt: 0.3 },
  { c: 'Амортизатор передний', l: 51, w: 7, h: 7, wt: 3.5 },
  { c: 'Колодка тормозная', l: 20, w: 12, h: 6, wt: 1.2 },
  { c: 'Подшипник ступицы', l: 7, w: 7, h: 3, wt: 0.1 },
  { c: 'Крышка клапанная', l: 15, w: 10, h: 5, wt: 0.2 },
];

/* deepStrictEqual сравнивает прототипы, а объекты из vm их не совпадают с
   объектами теста: для сравнения структур берём JSON-представление. */
const eq = (a, b, msg) => assert.strictEqual(JSON.stringify(a), JSON.stringify(b), msg);

const ctx = {
  S: { settings: { dimUnit: 'cm', weightImportUnit: 'kg' } }, console, Math, Number, String,
  Object, Array, Date, Map, Set, parseFloat, isFinite, nowISO: () => '2026-01-01T00:00:00.000Z',
  StdDims: { match: p => { const d = dict.find(x => x.c === p.name); return d ? { status: 'match', match: 'exact', std: d } : { status: 'none', choices: [] }; } },
};
vm.createContext(ctx);
vm.runInContext(utils + '\n' + dimFns + '\n' + dimUnitSrc + '\nglobalThis.DimUnit=DimUnit;', ctx);
const DimUnit = ctx.DimUnit;

const mk = (uw, ud, order) => (order || dict).map(s => ({
  brand: 'Brand X', name: s.c, category: '', category_type: '',
  dims: { weight: s.wt * (uw === 'g' ? 1000 : 1), length: s.l * (ud === 'mm' ? 10 : 1),
    width: s.w * (ud === 'mm' ? 10 : 1), height: s.h * (ud === 'mm' ? 10 : 1) },
}));

/* 1. Определение по справочнику: все четыре комбинации единиц. */
for (const [uw, ud] of [['kg', 'cm'], ['g', 'cm'], ['kg', 'mm'], ['g', 'mm']]) {
  for (const order of [dict, [...dict].reverse()]) {
    const plan = DimUnit.detect(mk(uw, ud, order), {});
    const grp = plan.brands['brand x'];
    assert(grp, 'нет решения для бренда');
    assert.strictEqual(grp.units.weight, uw, `${uw}/${ud}: вес определён как ${grp.units.weight}`);
    assert.strictEqual(grp.units.length, ud, `${uw}/${ud}: длина определена как ${grp.units.length}`);
    /* Д/Ш/В всегда одной единицей: смесь физически невозможна. */
    assert.strictEqual(grp.units.width, grp.units.length);
    assert.strictEqual(grp.units.height, grp.units.length);
    eq(grp.undefinedFields, [], 'опора есть — неопределённых полей быть не должно');
  }
}
/* Порядок строк внутри бренда не влияет на решение (раньше брали «первую»). */
const a1 = DimUnit.detect(mk('g', 'mm', dict), {}).brands['brand x'];
const a2 = DimUnit.detect(mk('g', 'mm', [...dict].reverse()), {}).brands['brand x'];
eq(a1.units, a2.units);

/* 2. Пересчёт приводит к тем же кг и см, что и эталон бренда в кг/см. */
const asIs = DimUnit.detect(mk('kg', 'cm'), {}).brands['brand x'];
for (const [uw, ud] of [['g', 'cm'], ['kg', 'mm'], ['g', 'mm']]) {
  const res = DimUnit.detect(mk(uw, ud), {}).brands['brand x'];
  mk(uw, ud).forEach((row, i) => {
    const p = Object.assign({}, row, { weight: row.dims.weight, length: row.dims.length, width: row.dims.width, height: row.dims.height });
    for (const f of ['weight', 'length', 'width', 'height']) {
      const conv = DimUnit.convertValue(f, p[f], res);
      if (conv) p[f] = conv.value;
    }
    assert(Math.abs(p.weight - dict[i].wt) < 1e-9, `${uw}/${ud}: вес ${p.weight} ≠ ${dict[i].wt}`);
    assert(Math.abs(p.length - dict[i].l) < 1e-9, `${uw}/${ud}: длина ${p.length} ≠ ${dict[i].l}`);
  });
}
/* Явная единица не переопределяется: convertValue для кг/см возвращает null. */
assert.strictEqual(DimUnit.convertValue('weight', 8.5, asIs), null);
assert.strictEqual(DimUnit.convertValue('length', 410, asIs), null);

/* 3. Нет опоры — решение не принимается (а не «угадывается»). */
const unknown = [{ brand: 'NoDict', name: 'Деталь без описания', dims: { weight: 250, length: 300, width: 200, height: 100 } }];
const uPlan = DimUnit.detect(unknown, {}).brands['nodict'];
eq(uPlan.units, {}, 'при одной строке решение принимать нельзя');
assert(uPlan.undefinedFields.length === 4, 'поля должны быть помечены как неопределённые');
/* Малое число строк (2) тоже не даёт опоры. */
const two = [0, 1].map(i => ({ brand: 'Tiny', name: 'Штука ' + i, dims: { weight: 120 + i, length: 80, width: 60, height: 40 } }));
eq(DimUnit.detect(two, {}).brands['tiny'].units, {}, 'две строки — не опора');

/* 4. Серая зона медианы (20…100) не решается вовсе. */
const grey = [0, 1, 2, 3, 4, 5].map(i => ({ brand: 'Grey', name: 'Штука ' + i, dims: { length: 50 + i, width: 40, height: 30 } }));
const greyPlan = DimUnit.detect(grey, {}).brands['grey'];
assert(!greyPlan.units.length, 'значения 50±5 см не должны трактоваться как мм');

/* 5. Медиана работает там, где справочник молчит: явные граммы. */
const heavy = [0, 1, 2, 3, 4, 5].map(i => ({ brand: 'Heavy', name: 'Штука ' + i, dims: { weight: 2000 + i * 100 } }));
assert.strictEqual(DimUnit.detect(heavy, {}).brands['heavy'].units.weight, 'g');

/* 6. Закреплённый профиль сильнее автоопределения и работает без опоры. */
ctx.S.settings.dimUnitProfiles = { tinybrand: { units: { weight: 'g', length: 'mm', width: 'mm', height: 'mm' }, at: 'x' } };
const sticky = DimUnit.resolveBrand('TinyBrand', { brands: {} });
assert(sticky && sticky.source === 'sticky');
assert.strictEqual(sticky.units.weight, 'g');
const conv = DimUnit.convertValue('weight', 120, sticky);
assert(Math.abs(conv.value - 0.12) < 1e-9, 'закреплённый профиль не применился');
ctx.S.settings.dimUnitProfiles = {};
assert.strictEqual(DimUnit.resolveBrand('TinyBrand', { brands: {} }), null);

/* 7. Сводная ячейка с единицей внутри значения. */
const triple = (v, hdr) => ctx.parseDimsTriple(v, hdr);
eq([triple('410*300*200 мм', 'Габариты').length, triple('410*300*200 мм', 'Габариты').width], [41, 30]);
eq([triple('41 x 30 x 20 см', 'Габариты').length, triple('41 x 30 x 20 см', 'Габариты').height], [41, 20]);
assert.strictEqual(triple('1.5*2*3 м', 'Габариты').length, 150);
assert.strictEqual(triple('41*30*20', 'Габариты, мм').length, 4.1);
assert.strictEqual(triple('2 x 3 x 4', 'Габариты').length, 2, 'буква «x» не должна читаться как метр');
assert.strictEqual(triple('410*300*200 см', 'Габариты, мм'), null, 'противоречие — не угадываем');
assert.strictEqual(triple('410*300*200 мм', 'Габариты')._explicit, true);
assert.strictEqual(triple('410*300*200', 'Габариты')._explicit, false);

/* 8. Физическая проверка результата. */
eq(DimUnit.sanity({ weight: 14, length: 50, width: 22, height: 14 }, { maxW: 400, maxL: 300, maxVol: 1000 }), []);
assert(DimUnit.sanity({ weight: 14, length: 5000, width: 22, height: 14 }, { maxW: 400, maxL: 300, maxVol: 1000 }).includes('dims'));

/* 9. В приложении есть точка применения на импорте и экран по брендам. */
assert(h.includes('dimensionResolve(_brandName || brandInFile, dimPlan, fileDims)'), 'импорт не применяет решение по бренду');
assert(h.includes("el('#btnDimUnits','onclick'"), 'нет кнопки экрана единиц');
assert(h.includes('id="mDimUnits"'), 'нет окна «Единицы по брендам»');
assert(h.includes('exportDimsInvalidate(p)'), 'не сбрасывается кэш габаритов для выгрузки');
assert(h.includes("p._sources[field] = { file: 'приведено '"), 'приведение не записывается в источник');
/* Пределы проверяются по всей строке после всех переводов (иначе бренд с мм
   по всем сторонам уходил в карантин по габаритам, хотя перевод верный). */
assert(h.includes('const bad = DimUnit.sanity(Object.assign({}, p, trial)'), 'пределы проверяются по одному полю, а не по строке');
/* Производный объём пересчитывается, заданный вручную — сохраняется. */
assert(h.includes('const _volFollowsDims ='), 'объём не сверяется с произведением сторон');
assert(h.includes('p._volumeExplicit = true;'), 'ручной объём не помечается — расчёт его перезапишет');
/* Явная единица сильнее решения по бренду. */
assert(h.includes('const _dimExplicit = !!(parsedOvh && parsedOvh.explicit);'));

console.log('OK: единицы по бренду (г/кг, мм/см), закрепление, сводная ячейка и физические пределы');
