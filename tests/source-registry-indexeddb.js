// Происхождение полей в записи каталога (v12.9.170): _sources → _src + meta.catalog
// и точный обратный разворот. Проверяется на настоящем Dexie, поэтому тест ловит
// и потерю набора, и ошибку StructuralClone, и «тихую» подмену даты.
const fs = require('fs'), vm = require('vm'), assert = require('assert'), fidb = require('fake-indexeddb');
const h = fs.readFileSync(__dirname + '/../index.html', 'utf8');
const c = { ...fidb, console, setTimeout, clearTimeout, queueMicrotask, AbortController, structuredClone, performance, TextDecoder, TextEncoder, CustomEvent: class { }, location: { protocol: 'http:' }, navigator: {}, S: { settings: {}, rows: [] } };
vm.createContext(c);
vm.runInContext([...h.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1], c);

const nm = (...n) => { const a = h.indexOf('const ' + n[0] + ' = '); assert(a > 0, 'не найден ' + n[0]); return h.slice(a, h.indexOf('\n};', a) + 3); };
vm.runInContext(nm('SourceRegistry') + ';this.SR = SourceRegistry;', c);
/* slimOf берём из настоящей функции записи, а не из копии. */
const s0 = h.indexOf('    const slimOf = src => {'), s1 = h.indexOf('    /* v12.9.7-mem', s0);
assert(s0 > 0 && s1 > s0, 'slimOf: границы функции не найдены');
vm.runInContext('this.slimOf = ' + h.slice(s0, s1).match(/const slimOf = (src => \{[\s\S]*?\n    \});/)[1] + ';', c);
const SR = c.SR, slimOf = c.slimOf;

const price = { file: 'Прайс_поставщик_2026-11.csv', date: '2026-11-18T09:00:00.000Z' };
const dims = { file: 'Весогабариты_2026-11.xlsx', date: '2026-11-18T10:30:12.345Z' };
const rows = [];
for (let i = 0; i < 400; i++) rows.push({ article: 'A' + i, brand: 'B', price: 10, name: 'n' + i,
  _sources: { 'Артикул': price, 'Наименование': price, 'Цена': price } });
for (let i = 0; i < 40; i++) rows.push({ article: 'C' + i, brand: 'B', weight: 1,
  _sources: { 'Артикул': price, 'Вес, кг': dims } });
/* Ручная правка: своя дата у одного поля. */
rows.push({ article: 'M1', brand: 'B', _sources: { 'Цена': { file: 'вручную:карточка', date: '2026-11-18T11:11:11.111Z' } } });
/* Непакуемые формы: обязаны остаться в прежнем формате, а не потеряться. */
rows.push({ article: 'BAD1', brand: 'B', _sources: { '': price } });
rows.push({ article: 'BAD2', brand: 'B', _sources: { 'Цена': { file: 'x', date: 'не дата' } } });
rows.push({ article: 'BAD3', brand: 'B', _sources: { 'Цена': { file: 'x', date: price.date, extra: 1 } } });
/* Дата без миллисекунд пакуется намеренно: точная строка сохраняется рядом с
   номером, поэтому разворот даёт ровно то же значение. Проверяем и это. */
rows.push({ article: 'OK5', brand: 'B', _sources: { 'Цена': { file: 'x', date: '2026-11-18T09:00:00Z' } } });

const ms = d => { const t = Date.parse(d); return Number.isFinite(t) ? t : d; };
const view = s => JSON.stringify(Object.keys(s || {}).sort().map(k => [k, s[k].file, ms(s[k].date)]));

(async () => {
  SR.reset(null);
  const stored = rows.map(r => slimOf(r));
  const packed = stored.filter(r => r._src !== undefined);
  const kept = stored.filter(r => r._sources !== undefined);
  assert(packed.length >= 440, 'одинаковые наборы должны сжиматься: ' + packed.length);
  assert.equal(packed.length + kept.length, rows.length, 'каждая строка записана ровно одним из способов');
  assert.equal(kept.length, 3, 'непакуемые наборы остаются в прежнем формате (пустое имя, непарсимая дата, лишнее поле)');
assert.equal(rows.length - kept.length, packed.length);
  assert(!packed.some(r => r._sources !== undefined), 'сжатая строка не несёт полный _sources');
  assert(packed.every(r => Number.isSafeInteger(r._src) && r._src > 0), '_src — номер набора');

  /* Запись реально весит меньше: это и есть цель правки. */
  const bytes = list => list.reduce((n, r) => n + Buffer.byteLength(JSON.stringify(r)), 0);
  assert(bytes(stored) * 4 < bytes(rows) * 3, 'запись должна уменьшиться минимум на четверть: ' + bytes(stored) + ' из ' + bytes(rows));

  const db = new c.Dexie('source-registry-test');
  c.db = db;
  db.version(1).stores({ products: '++id', meta: 'key' });
  await db.open();
  await db.products.bulkAdd(JSON.parse(JSON.stringify(stored)));
  await db.meta.put({ key: 'catalog', value: { count: rows.length, sources: JSON.parse(JSON.stringify(SR.snapshot())) } });
  db.close(); await db.open();

  /* --- «загрузка каталога», как в init(): наборы из meta, затем разворот --- */
  const loaded = await db.products.toArray();
  const rec = await db.meta.get('catalog');
  SR.reset(rec.value.sources);
  let orphan = 0;
  for (const p of loaded) {
    if (p._src === undefined) continue;
    const full = SR.expand(p._src);
    if (full) { p._sources = full; delete p._src; }
    else if (p._sources === undefined) { p._sources = {}; orphan++; }
  }
  assert.equal(orphan, 0, 'ни одна строка не должна остаться без набора');
  assert(loaded.every(p => p._src === undefined), '_src разворачивается при загрузке');
  let bad = 0;
  for (let i = 0; i < rows.length; i++) if (view(rows[i]._sources) !== view(loaded[i]._sources)) bad++;
  assert.equal(bad, 0, 'происхождение полей совпадает до и после записи');

  /* Служебная запись маленькая: наборов единицы, а не по одному на строку. */
  assert(SR.snapshot().length <= 6, 'наборов в meta.catalog: ' + SR.snapshot().length);
  const metaBytes = Buffer.byteLength(JSON.stringify(rec.value));
  assert(metaBytes < 4096, 'служебная запись не должна расти: ' + metaBytes);

  /* --- резервная копия (JSONL) должна нести полный _sources, а не номер --- */
  const backup = JSON.parse(JSON.stringify(stored)).map(r => {
    const copy = Object.assign({}, r);
    SR.expandOrFlag(copy);
    return copy;
  });
  assert(backup.every(r => r._src === undefined), 'в резервной копии нет номеров вместо происхождения');
  const restored = backup.filter(r => Object.keys(r._sources || {}).length);
  assert.equal(restored.length, rows.filter(r => Object.keys(r._sources).length).length, 'все наборы из копии развернулись');
  let copyBad = 0;
  for (let i = 0; i < rows.length; i++) if (view(rows[i]._sources) !== view(backup[i]._sources)) copyBad++;
  assert.equal(copyBad, 0, 'копия совпадает с исходным происхождением');
  assert.equal(SR.flagText(), '', 'при живой meta.catalog предупреждений нет');

  /* --- дельта: adopt переносит номера на строки старого формата --- */
  const legacy = rows.map(r => Object.assign({}, r));            /* строки без _src */
  SR.reset(rec.value.sources);
  SR.adopt(legacy);
  /* Пакуемая строка — та, для которой slimOf действительно дал _src. */
  const packable = legacy.filter(r => slimOf(r)._src !== undefined && !Object.keys(r._sources).includes(''));
  if (!packable.every(r => Number.isSafeInteger(r._src) && r._src > 0)) {
    const bad = packable.filter(r => !Number.isSafeInteger(r._src) || r._src <= 0).slice(0, 3);
    console.error('diagnostics: packable', packable.length, 'bad', JSON.stringify(bad.map(r => ({ s: Object.keys(r._sources), n: r._src }))));
  }
  assert(packable.every(r => Number.isSafeInteger(r._src) && r._src > 0), 'adopt проставляет _src каждой пакуемой строке');
  assert(packable.length >= rows.length - 4, 'adopt покрывает весь каталог: ' + packable.length);
  assert.equal(SR.idOf(packable[0]._sources), packable[0]._src, 'номер набора стабилен по содержимому');

  /* --- потеря служебной записи не должна стирать происхождение --- */
  await db.meta.delete('catalog');
  const rec2 = await db.meta.get('catalog');
  assert.equal(rec2, undefined);
  const reloaded = await db.products.toArray();
  SR.reset(rec2 && rec2.value && rec2.value.sources);
  let lost = 0, empty = 0;
  for (const p of reloaded) {
    const full = SR.expand(p._src);
    if (full) { p._sources = full; delete p._src; }
    else if (p._sources === undefined) { p._sources = {}; lost++; } else empty++;
  }
  assert.equal(lost, packed.length, 'без meta.catalog развернуть нечего — это видно, а не скрыто');
  assert(reloaded.filter(p => Object.keys(p._sources || {}).length).length === kept.length, 'строки прежнего формата читаются без потерь');

  await db.delete();
  console.log('OK: происхождение полей сжимается на записи и разворачивается при загрузке без потерь; непакуемые наборы и потеря meta.catalog обрабатываются явно');
})().catch(e => { console.error(e); process.exitCode = 1; });
