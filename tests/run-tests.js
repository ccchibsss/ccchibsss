/* UNIT·CONTROL — воспроизводимые тесты аудита v12.9.67–12.9.68.
   Запуск: node tests/run-tests.js   (Node 18+, зависимостей нет) */
'use strict';
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const html = fs.readFileSync(__dirname + '/../index.html', 'utf8').replace(/\r\n/g, '\n');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const app = scripts[scripts.length - 1];
new vm.Script(app); // синтаксис клиентского скрипта
const gas = html.match(/<script type="text\/plain" id="gas-backend">([\s\S]*?)<\/script>/)[1];
new vm.Script(gas); // синтаксис GAS-бэкенда

const grab = re => { const m = app.match(re); assert(m, 'не найден фрагмент: ' + re); return m[0]; };
const ctx = {};
vm.createContext(ctx);
vm.runInContext(
  grab(/const num = v => \{[\s\S]*?\n\};\n/) +
  grab(/const _POW10[\s\S]*?const round = \(n, d = 2\) => \{[\s\S]*?\n\};\n/) +
  grab(/function solveEcoInteger\(initial, metric\) \{[\s\S]*?\n\}\n/) +
  '\nthis.num=num; this.round=round; this.solveEcoInteger=solveEcoInteger;', ctx);
const { num, round, solveEcoInteger } = ctx;

// num(): форматы чисел
assert.strictEqual(num('11 200,00'), 11200);
assert.strictEqual(num('1.200,50'), 1200.5, 'точка тысяч + запятая');
assert.strictEqual(num('1,200.50'), 1200.5, 'запятая тысяч + точка');
assert.strictEqual(num('12%'), 12);
assert.strictEqual(num(''), 0); assert.strictEqual(num(null), 0); assert.strictEqual(num('abc'), 0);

// round(): Excel-семантика (половина от нуля)
assert.strictEqual(round(2.5, 0), 3); assert.strictEqual(round(-2.5, 0), -3);
assert.strictEqual(round(1.005, 2), 1.01); assert.strictEqual(round(313.635, 2), 313.64);
assert.strictEqual(round(-313.635, 2), -313.64);

// solver: линейная, ступенчатая и интервальная (немонотонная) прибыль
assert.strictEqual(solveEcoInteger(15306, p => p * 0.785 - 11285.17), 14377);
assert.strictEqual(solveEcoInteger(900, p => p * 0.8 - 700 - (p >= 1000 ? 500 : 0)), 875);
const band = solveEcoInteger(100, p => (p >= 500 && p <= 600) ? 10 : -Math.abs(p - 550));
// v12.9.74: «+ − +» ступенчатого тарифа — первое пересечение, не второе (регрессия аудита расчётов)
assert.strictEqual(solveEcoInteger(1000, p => p * 0.5468438030438701 - 2294.911242553457 - (p >= 4612 ? 463.87214682245263 : 0)), 4197, 'первое пересечение при провале ступени');
assert.strictEqual(solveEcoInteger(1000, p => p * 0.3085886478464066 - 1034.5393632233793 - (p >= 3972 ? 543.2384493496448 : 0)), 3353, 'полоса целиком внутри сегмента сетки');
{ // решатель против полного перебора на случайных линейных/ступенчатых функциях
  let seed = 42; const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  const brute = (f, cap) => { for (let p = 1; p <= cap; p++) if (f(p) >= 0) return p; return 10000000; };
  for (let i = 0; i < 100; i++) {
    const r = 0.3 + rnd() * 0.6, F = 100 + rnd() * 20000, at = 500 + Math.floor(rnd() * 5000), st = rnd() * 800;
    const f = p => p * r - F - (p >= at ? st : 0);
    assert.strictEqual(solveEcoInteger(1000, f), brute(f, 100000), 'solver != brute, случай ' + i);
  }
}
assert(band >= 500 && band <= 600, 'интервальная прибыль должна находиться, получено ' + band);
assert.strictEqual(solveEcoInteger(100, () => -5), 10000000, 'нет прибыли — CAP');

// статические гарантии аудита
assert(app.includes('autoStdDims: false'), 'стандартные ОВХ по умолчанию выключены');
assert(app.includes('stdDimsDefaultOffV2'), 'миграция выключения стандартных ОВХ');
assert(app.includes('запись стандартных ОВХ в каталог запрещена'), 'StdDims.fill не пишет в каталог');
assert(app.includes('function exportDimsFor'), 'стандартные ОВХ применяются при выгрузке');
// v12.9.68: стандартные ОВХ и автоподстановка — жёлтая заливка, не красный шрифт
assert(!app.includes('FFFF0000'), 'красной пометки ОВХ не осталось');
assert(app.includes("fgColor: { rgb: 'FFFFFF00' }"), 'Ozon XLSX: жёлтая заливка стандартных ОВХ');
assert(app.includes("dxf('FFFFFF00', true, 'FF000000')"), 'юнит-экономика XLSX: жёлтая заливка');
assert(app.includes('function autoFillFields'), 'маркеры автоподстановки категорий/ТН ВЭД');
assert(app.includes('function autoFillNote'), 'служебная колонка автозаполнения в экспорте');
assert(app.includes("$AY"), 'Ozon XLSX: маркер автоподстановки ТН ВЭД (колонка AY)');
assert(app.includes('rgba(250,204,21,.30)'), 'таблица каталога: жёлтая заливка автоподстановки');
// автоподстановка — только в пустые поля; файл — главный источник
assert(app.includes('const explicit=this.findCode(p,false); if (explicit) return {status:\'preserved\''), 'ТН ВЭД: явный код из файла не затирается');
assert(app.includes('HVC.enCol(\'tnved\') && !String(p.tnved || \'\').trim() && t.tnved'), 'Каталог V: ТН ВЭД только в пустое поле');
assert(app.includes('const canCategory=NameCategory.blank(p.category)&&!explicitBlank;'), 'файл категорий: только пустые поля');
assert(app.includes('12.9.70-client+export-guard') || app.includes('12.9.74-client+solver-first-crossing'), 'версия клиента обновлена');
// v12.9.70: ошибка выгрузки не теряет данные
assert(app.includes('async function exportGuard'), 'страж выгрузки');
assert(app.includes('ensureCatalogSafeBeforeExport'), 'запись каталога на диск перед выгрузкой');
assert(app.includes('данные НЕ потеряны'), 'честное сообщение об ошибке выгрузки');
assert(app.includes("return exportGuard('Экспорт', () => this._runImpl(forceRows))"), 'общий экспорт под стражем');
assert(app.includes("return exportGuard('Экспорт в OZON', () => this._runImpl())"), 'Ozon экспорт под стражем');
assert(app.includes('_persistDirty = true'), 'флаг несохранённых изменений');
assert((app.match(/exportGuard\('/g) || []).length >= 5, 'все кнопки выгрузки под стражем');
assert(!app.includes('OFFICIAL_ALL_MP_TARIFFS_2026 = ['), 'мёртвый справочник тарифов удалён');
assert(app.includes('p.profitEstimate = p.priceInputsIncomplete'), 'прибыль помечается оценкой');
assert(app.includes('ОЦЕНКА по '), 'KPI показывает долю оценочной прибыли');
assert(gas.includes('toPrecision(15)'), 'GAS round_ унифицирован с клиентом');

// CSV: независимый пересчёт безубытка в recalculated
const csvText = fs.readFileSync(__dirname + '/../UC_unit_economics_OZON_2026-11-06_recalculated.csv', 'utf8').replace(/^﻿/, '');
const rows = csvText.trim().split(/\r?\n/).slice(1).map(l => l.split(';'));
const n = s => parseFloat(String(s).replace(/[\s ]/g, '').replace(',', '.')) || 0;
for (const r of rows) {
  const price = n(r[13]), tot = n(r[32]);
  const pct = (n(r[15]) + n(r[17]) + n(r[31])) / price;
  const fixed = tot - price * pct;
  const be = fixed / (1 - pct), t20 = fixed / (1 - pct - 0.20);
  assert(Math.abs(n(r[41]) - be) < 0.02, r[0] + ': BE ' + r[41] + ' != ' + be.toFixed(2));
  assert(Math.abs(n(r[42]) - t20) < 0.02, r[0] + ': target20 ' + r[42] + ' != ' + t20.toFixed(2));
  // суммы статей
  let sum = 0; for (let i = 14; i <= 31; i++) sum += n(r[i]);
  assert(Math.abs(sum - tot) < 0.02, r[0] + ': сумма статей != итогу');
}
// v12.9.69: раздельный режим категории/ТН ВЭД + единогласие OE-доноров (функционально, на HVC)
assert(app.includes('function autoFillFields'), 'маркеры автоподстановки категорий/ТН ВЭД');
assert(app.includes('enrichCatMode()'), 'отдельный способ обогащения категории/ТН ВЭД');
assert(app.includes("grp === 'cat'"), 'раздельные проходы обогащения main/cat');
assert(app.includes('catConflict'), 'флаг конфликта категорий OE-доноров');
assert(app.includes('12.9.69-client+enrich-catmode') || app.includes('12.9.74-client+solver-first-crossing'), 'версия клиента обновлена');
{
  const hvcSrc = app.match(/const HVC = \{[\s\S]*?\n\};\n/)[0];
  const c2 = {
    console, Set, Map, WeakMap, WeakSet, JSON, Math, Number, String, Array, Object, Date, RegExp, Error, Promise, performance,
    S: { settings: { enrichMode: 'oe' }, rows: [], catalogVersion: 0 },
    normArticle: s => String(s == null ? '' : s).toUpperCase().replace(/[^A-Z0-9А-ЯЁ]/g, ''),
    num: v => { const n = parseFloat(String(v).replace(',', '.')); return isFinite(n) ? n : 0; },
    codeList: v => String(v || '').split(/[\/;,|]+/).map(x => x.trim()).filter(Boolean),
    OE_DELIMITERS: { auto: { join: ' / ' } }, oeMode: () => 'auto',
    CONST: { OE_SET_CACHE_MAX: 1000 },
    DimPolicy: { validTuple: () => false, compareTuples: () => 0 },
    nowISO: () => '2026-01-01'
  };
  c2.globalThis = c2;
  vm.createContext(c2);
  vm.runInContext(hvcSrc + '\nthis.HVC=HVC;', c2);
  const H = c2.HVC;
  assert.strictEqual(H.enrichCatMode(), 'artbrand', 'по умолчанию категория — только Артикул+Бренд');
  const k1 = 'ART1|BRAND', k2 = 'ART2|BRAND';
  H.parts.set(k1, { artikul: 'ART1', brand: 'BRAND', category: 'Фильтры', name: 'Фильтр масляный', tnved: '8421230000' });
  H.parts.set(k2, { artikul: 'ART2', brand: 'BRAND', category: 'Двигатель', name: 'Поршень' });
  H.byOe.set('OE1', new Set([k1, k2]));
  H.byArt.set(k1, new Set(['OE1'])); H.byArt.set(k2, new Set(['OE1']));
  const probe = { article: 'ART1', brand: 'BRAND', oe_norm: 'OE1', category: '', name: '', applicability: '' };
  assert.strictEqual(H.textFor(probe, 'oe').category, '', 'доноры OE расходятся — категория по OE не берётся');
  assert.strictEqual(H._oeSetOf(probe).catConflict, true, 'конфликт категорий зафиксирован');
  H.parts.get(k2).category = 'Фильтры'; H._oeAggCache = null; H._oeSetCache = null;
  assert.strictEqual(H.textFor(probe, 'oe').category, 'Фильтры', 'единогласные доноры OE — категория берётся');
  const p2 = { article: 'ART1', brand: 'BRAND', oe_norm: 'OE1', category: '', tnved: '', name: '', applicability: '', weight: 0, length: 0, width: 0, height: 0 };
  H.enrichOne(p2, null);
  assert.strictEqual(p2.category, 'Фильтры', 'категория заполнена');
  assert(/Артикул \+ Бренд/.test(p2._sources.category.file), 'по умолчанию категория — от пары Артикул+Бренд, не от OE: ' + p2._sources.category.file);
  assert.strictEqual(p2.tnved, '8421230000', 'ТН ВЭД заполнен из пары Артикул+Бренд');
}

// v12.9.71: сноска «чего не хватает для юнит-экономики» в разделе «Данные»
assert(html.includes('id="econMissingNote"'), 'сноска недостающих данных в разделе «Данные»');
assert(app.includes('function renderEconMissingNote()'), 'рендер сноски недостающих данных');
assert(app.includes('renderEconMissingNote(); } catch'), 'сноска обновляется в filterUI');
assert(app.includes('12.9.74-client+solver-first-crossing'), 'версия клиента обновлена');
{
  const specSrc = app.slice(app.indexOf('const ECON_INPUT_SPEC = ['), app.indexOf('function econSpecOf'));
  const src = specSrc
    + grab(/function econSpecOf\(key\)[^\n]*\n/)
    + grab(/function econReadiness\(rows\) \{[\s\S]*?\n\}\n/)
    + grab(/function renderEconMissingNote\(\) \{[\s\S]*?\n\}\n/);
  const mkCtx = rows => {
    const el = { style: {}, innerHTML: '' };
    const c = {
      S: { rows, settings: { activeMarketplace: 'WB' }, tariffs: {} },
      document: { getElementById: () => el },
      num: v => { const n = parseFloat(String(v == null ? '' : v).replace(',', '.')); return isFinite(n) ? n : 0; },
      fmt: v => String(v),
      esc: s => String(s == null ? '' : s),
      ozonActiveScheme: () => 'FBS', ozonRoutePresent: () => true
    };
    c.globalThis = c; vm.createContext(c);
    vm.runInContext(src + '\nthis.renderEconMissingNote=renderEconMissingNote;', c);
    return { c, el };
  };
  const bad = mkCtx([
    { price: 100, cost: 50, weight: 1, length: 10, width: 10, height: 10, sales: 5, category: 'Фильтры', fixed: 10, noBuyRateSource: 'SKU · импорт/проверено' },
    { price: 0, cost: 0, weight: 0, length: 0, width: 0, height: 0, sales: 0, tariffMissing: true, category: '', fixed: 0,
      priceInputsIncomplete: true, priceInputsReason: 'ставка Ozon не подтверждена', noBuyRateSource: 'Общая настройка · проверьте по площадке' }
  ]);
  bad.c.renderEconMissingNote();
  assert(bad.el.style.display === 'block', 'сноска видна при неполных данных');
  assert(bad.el.innerHTML.includes('Для полной юнит-экономики не хватает данных'), 'сноска перечисляет недостающее');
  assert(bad.el.innerHTML.includes('нет себестоимости') && bad.el.innerHTML.includes('1 SKU (50%)'), 'счётчики недостающих данных верны: ' + bad.el.innerHTML);
  assert(bad.el.innerHTML.includes('Себестоимость'), 'указаны столбцы для догрузки');
  assert(bad.el.innerHTML.includes('нет категории для ставки комиссии'), 'расширенная сноска: категория для ставки');
  assert(bad.el.innerHTML.includes('ставка комиссии не подтверждена'), 'расширенная сноска: неподтверждённая ставка');
  assert(bad.el.innerHTML.includes('% невыкупа не задан'), 'расширенная сноска: % невыкупа');
  assert(bad.el.innerHTML.includes('постоянные расходы не заданы'), 'расширенная сноска: постоянные расходы');
  assert(!bad.el.innerHTML.includes('нет продаж за месяц'), 'продажи за месяц не числятся недостающими: экономика на единицу');
  const good = mkCtx([{ price: 100, cost: 50, weight: 1, length: 10, width: 10, height: 10, sales: 0, category: 'Фильтры', fixed: 10, noBuyRateSource: 'SKU · импорт/проверено' }]);
  good.c.renderEconMissingNote();
  assert(good.el.innerHTML.includes('данные полны'), 'без продаж за месяц данные всё равно полны: расчёт на единицу');
  const empty = mkCtx([]);
  empty.c.renderEconMissingNote();
  assert(empty.el.style.display === 'none', 'при пустом каталоге сноска скрыта');
}

console.log('OK: все тесты пройдены (' + rows.length + ' строк CSV пересчитано)');
