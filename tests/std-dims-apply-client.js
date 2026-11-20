// Кнопка «Подставить стандартные ОВХ»: запись в каталог, источник, медиана по
// категории, повторный запуск без ложных изменений.
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const h = fs.readFileSync(__dirname + '/../index.html', 'utf8');

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
const lineOf = sig => { const i = lines.findIndex(l => l.startsWith(sig)); assert(i >= 0, 'не найдено: ' + sig); return i; };
const utils = lines.slice(lineOf('const num = v => {'), lineOf('function debounce(')).join('\n');
const eq = (a, b, msg) => assert.strictEqual(JSON.stringify(a), JSON.stringify(b), msg);

const start = h.indexOf('const StdDimsApply = {');
assert(start > 0, 'модуль StdDimsApply не найден');
/* Достаём объект целиком: от объявления до закрывающей пары на нулевом отступе. */
const end = h.indexOf('\n};', start) + 3;
const src = h.slice(start, end);

const dict = [
  { c: 'Колодка тормозная', l: 20, w: 12, h: 6, wt: 1.2, src: 'core' },
  { c: 'Фильтр масляный', l: 12, w: 10, h: 8, wt: 0.3, src: 'core' },
  { c: 'Амортизатор передний', l: 51, w: 7, h: 7, wt: 3.5, src: 'core' },
];

let DB = [];   // каталог
const ctx = {
  console, Math, Number, String, Object, Array, Date, Map, Set, WeakSet, JSON, ArrayLikeError: Error,
  parseFloat, isFinite, fmt: (v, d) => String(Math.round(v * 100) / 100),
  round: (v, d) => { const p = Math.pow(10, d == null ? 2 : d); return Math.round((Number(v) + Number.EPSILON) * p) / p; },
  nowISO: () => '2026-01-01T00:00:00.000Z',
  S: { rows: [], settings: {} },
  Toast: { info: () => {}, ok: () => {}, warn: () => {}, err: () => {} },
  confirm: () => true,
  runPipeline: async () => {},
  exportDimsInvalidate: () => {},
  StdDims: {
    version: 7,
    match: p => {
      const d = dict.find(x => x.c === p.name);
      return d ? { status: 'match', match: 'exact', std: d } : { status: 'none', choices: [] };
    },
  },
  AnomalyDetector: {
    found: [], log: [], save: () => {},
    blockedRows: () => (DB.rows || []).filter(p => p.dimensionAnomalyBlocked),
    quarantineRow: p => { p.dimensionAnomalyBlocked = !(Number(p.weight) > 0 && Number(p.weight) < 100); },
    finishQuarantine: () => {},
    evaluate: p => ({ issues: (Number(p.weight) > 100 ? [{ type: 'weight_high', field: 'weight', val: p.weight, limit: 100 }] : []) }),
  },
};
Object.defineProperty(ctx, 'DB', { get: () => DB });
ctx.S = { get rows() { return DB.rows; }, settings: {} };
vm.createContext(ctx);
vm.runInContext(utils + '\n' + src.replace('const StdDimsApply = {', 'globalThis.StdDimsApply = {') + '\n', ctx);
const StdDimsApply = ctx.StdDimsApply;

const mkRow = (name, category, vals) => ({
  article: 'A-' + name.slice(0, 6), brand: 'B', name, category, custom: {}, _sources: {},
  weight: vals[0], length: vals[1], width: vals[2], height: vals[3],
  volume: vals[1] * vals[2] * vals[3] / 1000, visible: true, dimensionAnomalyBlocked: true,
});

/* 1. Точное совпадение: значения справочника записываются в каталог. */
DB = { rows: [mkRow('Колодка тормозная', 'Тормозная система', [50000, 50000, 50000, 50000])] };
ctx.S.rows = DB.rows;
const plan1 = StdDimsApply.plan(false);
assert.strictEqual(plan1.exact.length, 1, 'точное совпадение не найдено');
eq(plan1.exact[0].values, { length: 20, width: 12, height: 6, weight: 1.2 }, 'взяты не значения справочника');
const changed = StdDimsApply.applyToRow(plan1.exact[0], 'exact');
eq(changed, ['length', 'width', 'height', 'weight'], 'изменены не все поля');
const p1 = DB.rows[0];
eq([p1.weight, p1.length, p1.width, p1.height], [1.2, 20, 12, 6], 'значения не записаны в строку');
assert.strictEqual(p1.volume, 20 * 12 * 6 / 1000, 'объём не пересчитан из сторон');
/* Источник обязателен: без него значение выглядит как измеренное. */
assert(p1._sources.weight && /справочник стандартных ОВХ/.test(p1._sources.weight.file), 'не записан источник веса');
assert(/справочник/.test(p1._sources.length.file), 'не записан источник длины');
assert.strictEqual(p1._sources.weight.stdSubstituted, true, 'источник не помечен как подстановка');
eq({ match: p1._stdDimsApplied.match, estimated: p1._stdDimsApplied.estimated }, { match: 'exact', estimated: false }, 'отметка подстановки неверна');
eq(p1._stdDimsApplied.fields, ['length', 'width', 'height', 'weight'], 'отметка перечисляет не все поля');
assert.strictEqual(p1._stdDimsApplied.dictionary, 7, 'не записана версия справочника');

/* 2. Строка без опоры в справочнике не трогается. */
DB = { rows: [mkRow('Странная деталь', 'Без категории', [5000, 40, 30, 20])] };
ctx.S.rows = DB.rows;
const plan2 = StdDimsApply.plan(false);
assert.strictEqual(plan2.exact.length + plan2.median.length, 0, 'подставлено значение без опоры');
assert.strictEqual(plan2.none.length, 1, 'строка не попала в «без данных»');

/* 3. Медиана по категории — по каталогу, не по справочнику. */
const healthy = [[1.2, 20, 12, 6], [1.5, 24, 14, 7], [0.9, 18, 11, 5]].map((v, i) => Object.assign(
  mkRow('Здоровая ' + i, 'Тормозная система', v), { dimensionAnomalyBlocked: false }));
const broken = mkRow('Странная деталь', 'Тормозная система', [5000, 50, 50, 50]);
DB = { rows: [...healthy, broken] };
ctx.S.rows = DB.rows;
const med = StdDimsApply.categoryMedian('Тормозная система');
eq(med, { l: 20, w: 12, h: 6, wt: 1.2, n: 3 }, 'медиана по категории посчитана неверно');
const plan3 = StdDimsApply.plan(false);
assert.strictEqual(plan3.median.length, 1, 'строка не попала в медиану');
const ch3 = StdDimsApply.applyToRow(plan3.median[0], 'median');
assert(ch3.length === 4, 'медиана записана не во все поля');
assert.strictEqual(broken._stdDimsApplied.estimated, true, 'медиана не помечена как ненастоящая');
assert.strictEqual(broken._stdDimsApplied.match, 'median', 'вид подстановки не записан');
assert(/медиана по категории/.test(broken._sources.weight.file), 'источник не говорит про медиану');
/* Опора не берётся из строк, которые сами в карантине. */
const oneHealthy = [Object.assign(mkRow('Здоровая', 'Фильтры', [0.3, 10, 8, 5]), { dimensionAnomalyBlocked: false })];
DB = { rows: [...oneHealthy, mkRow('Странная деталь', 'Фильтры', [5000, 50, 50, 50])] };
ctx.S.rows = DB.rows;
assert.strictEqual(StdDimsApply.categoryMedian('Фильтры'), null, 'медиана посчитана по одной строке — это догадка');
/* У категории с одной здоровой строкой медианы нет, но строка без категории тем более. */
assert.strictEqual(StdDimsApply.categoryMedian(''), null, 'медиана посчитана без категории');

/* 4. Ручной объём сохраняется, производный — пересчитывается. */
DB = { rows: [Object.assign(mkRow('Колодка тормозная', '', [50000, 50000, 50000, 50000]), { volume: 50, _volumeExplicit: true })] };
ctx.S.rows = DB.rows;
StdDimsApply.applyToRow(StdDimsApply.plan(false).exact[0], 'exact');
assert.strictEqual(DB.rows[0].volume, 50, 'заданный вручную объём перезаписан');
assert.strictEqual(DB.rows[0]._volumeExplicit, true, 'ручной объём не помечен явным');

/* 5. Подтверждение аномалии сбрасывается: значения изменились. */
DB = { rows: [Object.assign(mkRow('Колодка тормозная', '', [50000, 50000, 50000, 50000]), { dimensionAnomalyAck: { signature: 'старое' } })] };
ctx.S.rows = DB.rows;
StdDimsApply.applyToRow(StdDimsApply.plan(false).exact[0], 'exact');
assert.strictEqual(DB.rows[0].dimensionAnomalyAck, undefined, 'старое подтверждение осталось — строка не проверится заново');

/* 6. Область: отмеченные строки, иначе все заблокированные. */
const r1 = mkRow('Колодка тормозная', '', [50000, 50000, 50000, 50000]);
const r2 = mkRow('Фильтр масляный', '', [50000, 50000, 50000, 50000]);
const r3 = mkRow('Амортизатор передний', '', [50000, 50000, 50000, 50000]);
DB = { rows: [r1, r2, r3] };
ctx.S.rows = DB.rows;
ctx.AnomalyDetector.found = [{ p: r2, _sel: true }];
const sc = StdDimsApply.scope(false);
assert.strictEqual(sc.source, 'selected', 'отмеченные строки не в приоритете');
eq(sc.rows.map(p => p.article), [r2.article], 'взяты не отмеченные строки');
assert.strictEqual(StdDimsApply.scope(true).rows.length, 1, 'режим «только отмеченные» не работает');
ctx.AnomalyDetector.found = [];
assert.strictEqual(StdDimsApply.scope(false).source, 'blocked', 'без отметок не берутся заблокированные');

/* 7. Повторный запуск не должен писать «сегодняшнюю» дату в неизменённые
      строки: иначе каталог получает ложную ревизию (как было с _dimUnitNote). */
const once = mkRow('Колодка тормозная', '', [50000, 50000, 50000, 50000]);
DB = { rows: [once] };
ctx.S.rows = DB.rows;
StdDimsApply.applyToRow(StdDimsApply.plan(false).exact[0], 'exact');
const snapshot = JSON.stringify(once);
const planAgain = StdDimsApply.plan(false);
assert.strictEqual(planAgain.exact.length, 0, 'заполненная строка снова попала в план');
const again = StdDimsApply.plan(false);
assert.strictEqual(again.exact.length + again.median.length, 0, 'повторный план что-то нашёл');
assert.strictEqual(JSON.stringify(once), snapshot, 'повторный запуск изменил строку');

/* 8. Предпросмотр: показывает, кто выйдет из карантина, а кто нет. */
const okRow = mkRow('Колодка тормозная', '', [50000, 50000, 50000, 50000]);
DB = { rows: [okRow] };
ctx.S.rows = DB.rows;
const prev = StdDimsApply.preview(false);
assert.strictEqual(prev.sum.released, 1, 'не посчитаны строки, выходящие из карантина');
assert.strictEqual(prev.sum.stillBlocked, 0, 'лишние строки помечены остающимися');
assert(okRow.dimensionAnomalyBlocked, 'предпросмотр изменил карантин — он должен быть только чтением');

/* 9. Явный список строк — для окна «Стандартные ОВХ» со своими галочками. */
const e1 = mkRow('Колодка тормозная', '', [50000, 50000, 50000, 50000]);
const e2 = mkRow('Фильтр масляный', '', [50000, 50000, 50000, 50000]);
DB = { rows: [e1, e2] };
ctx.S.rows = DB.rows;
const pe = StdDimsApply.plan(false, [e2]);
assert.strictEqual(pe.source, 'explicit', 'явный список строк не распознан');
eq(pe.exact.map(x => x.p.article), [e2.article], 'взята чужая строка');
assert.strictEqual(pe.rows, 1, 'в плане больше строк, чем передали');

/* 10. В приложении кнопка, окно и запись на месте. */
assert(h.includes('id="btnStdDimsApply"'), 'нет кнопки «Подставить стандартные ОВХ»');
assert(h.includes("el('#btnStdDimsApply','onclick'"), 'кнопка не подключена');
assert(h.includes('id="mStdApply"'), 'нет окна предпросмотра');
assert(h.includes("el('#stdApplyRun','onclick'"), 'нет запуска из окна');
assert(h.includes('AnomalyDetector.quarantineRow(p);'), 'после записи строки не перепроверяются — карантин останется со старыми флагами');
assert(!/StdDims\.fill\s*=/.test(h), 'кнопка не должна включать отключённый StdDims.fill');
/* Окно «Стандартные ОВХ» больше не упирается в «в каталог не записываем»:
   его кнопки идут через общий механизм записи. */
assert(!h.includes('StdDims.fill(item.p'), 'кнопки окна стандартов всё ещё зовут отключённый fill');
assert(h.includes('StdDimsApply.apply(false, { rows })'), 'кнопки окна стандартов не пишут в каталог');

console.log('OK: стандартные ОВХ — запись в каталог с источником, медиана по категории, сброс подтверждений');
