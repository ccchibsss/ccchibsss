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
assert(app.includes('12.9.70-client+export-guard') || app.includes('12.9.137-client+secrets-engine'), 'версия клиента обновлена');
// v12.9.79: светлый экспорт + компактный поштучный калькулятор без месячных расчётов
assert(app.includes('12.9.137-client+secrets-engine'), 'версия 12.9.79');
assert(!app.includes('FF1B2140'), 'чёрной заливки шапки экспорта не осталось');
assert(app.includes("['markupPct','Заработок на закупку, % — формула'"), 'калькулятор: заработок на закупку');
assert(app.includes("['logisticsRub','Логистика и доставка, ₽/ед — ввод'"), 'калькулятор 24: объединённая логистика');
assert(app.includes("['otherPct','Остальные %, от цены — ввод'"), 'калькулятор 24: объединённые % расходы');
assert(app.includes("'Вводы и ставки'"), 'калькулятор: лист вводов и ставок');
assert(app.includes('colGroups:[{ from:1, to:4, hidden:true }]'), 'калькулятор: свёрнутая группа габаритов');
assert(app.includes('outlineLevel="1"'), 'патч XLSX: группировка колонок');
assert(app.includes("INPUT_SHEET_KEYS"), 'общий экспорт: лист вводов и ставок по всем МП');
assert(app.includes("'Вводы и ставки'!${c.Lin}"), 'общий экспорт: межлистовые ссылки формул');
assert(app.includes('const enrichOnlyRef = enrichOnlyOn && S.rows.length > 0;'), 'импорт: обогащение только по текущему прайсу');
assert(html.includes('id="impLightMode"'), 'лёгкий импорт: переключатель в панели импорта');
assert(html.includes('id="expReimportKit"'), 'повторная загрузка: кнопка комплекта в экспорте');
assert(app.includes('async downloadReimportKit()'), 'повторная загрузка: метод формирования двух файлов');
assert(app.includes("'article', 'article_norm', 'brand', 'name', 'price', 'cost', 'stock', 'sales'"), 'повторная загрузка: прайс с нормализованным артикулом');
assert(app.includes("'oe_numbers', 'oe_norm', 'group_articles', 'analog_list'"), 'повторная загрузка: обогащение с нормализованными OE');
assert(app.includes("catList.filter(c => c.g === 'custom')"), 'повторная загрузка: пользовательские колонки включены');
assert(app.includes('UC_повторная_загрузка_1_прайс_'), 'повторная загрузка: имя первого файла');
assert(app.includes("'аналоги':'analog_list'"), 'повторная загрузка: импорт узнаёт колонку «Аналоги»');
assert(app.includes('function stdDimsSubstituteForCalc(p)'), 'стандартные ОВХ: временная подстановка для расчёта');
assert(app.includes("S.settings.calcStdDims !== true) return null;"), 'стандартные ОВХ: подстановка только при включённой настройке');
assert(app.includes("f.match !== 'exact'"), 'стандартные ОВХ: только точное совпадение');
assert(app.includes('function computeEconomicsInner(p, ov)'), 'стандартные ОВХ: расчёт обёрнут подстановкой');
assert(app.includes('габариты для расчёта — СТАНДАРТНЫЕ (не измерены): '), 'стандартные ОВХ: пометка в качестве данных');
assert(html.includes('id="recalcStdDimsBtn"'), 'стандартные ОВХ: кнопка пересчёта');
assert(html.includes('id="enCalcStdDims"'), 'стандартные ОВХ: переключатель в настройках');
assert(app.includes("k: 'stdDimsCalc', n: 'ОВХ из стандартных при расчёте'"), 'стандартные ОВХ: колонка-маркер в выгрузке');
assert(app.includes('СТАНДАРТ-РАСЧЁТ: '), 'стандартные ОВХ: текст маркера');
assert(app.includes("dxf('FFFFA07A', false, 'FF000000')"), 'стандартные ОВХ: подсветка #FFA07A в XLSX');
assert(app.includes("ct('stdDimsCalc', 'СТАНДАРТ-РАСЧЁТ', dStdCalc);"), 'стандартные ОВХ: правило подсветки маркера');
assert(app.includes("c.k === 'multiplicity' ? 'Кратность, шт' : c.n"), 'повторная загрузка: кратность под стандартным именем');
assert(app.includes('skipEconomics: lightModeOn'), 'лёгкий импорт: пайплайн получает skipEconomics');
assert(app.includes('const skipEcon = options.skipEconomics === true;'), 'лёгкий импорт: флаг пропуска экономики в пайплайне');
assert(app.includes('if (skipEcon) { internRowStrings(old); continue; }'), 'лёгкий импорт: расчётные массивы строк не выделяются');
assert(app.includes('async function ensureEconomics()'), 'лёгкий импорт: ленивый досчёт экономики');
assert(app.includes('if (S._econPending) { await ensureEconomicsFor(rows); rows = refreshRowRefs(rows); }'), 'лёгкий импорт: экспорт досчитывает экономику своих строк');
assert(app.includes("if (!skipEcon && !changedRows) { S._econPending = false; persistEconPending(); }"), 'лёгкий импорт: флаг ожидания снимает только полный расчёт');
assert(app.includes('async function ensureEconomicsFor(rows)'), 'лёгкий экспорт: досчёт только строк выгрузки');
assert(app.includes('changedRows: new WeakSet(rows), changedList: rows'), 'лёгкий экспорт: дельта-проход по строкам выгрузки');
assert(app.includes('function refreshRowRefs(rows)'), 'лёгкий экспорт: обновление ссылок после упаковки строк');
assert(app.includes('async function releaseEconomics()'), 'лёгкий экспорт: сброс расчётных данных после выгрузки');
assert(app.includes('_releaseAfterExport()'), 'лёгкий экспорт: точка сброса в экспорте');
assert(app.includes('usedEstMB()'), 'MemGuard: эвристика памяти без performance.memory');
assert(app.includes('function persistEconPending()'), 'лёгкий старт: флаг ожидания сохраняется');
assert(app.includes("lsGet('uc.econPending') === '1'"), 'лёгкий старт: флаг восстанавливается при загрузке');
assert(app.includes('skipEconomics: S._econPending === true'), 'лёгкий старт: стартовый пайплайн пропускает экономику');
assert(app.includes('if (estimated) { soft = 700; hard = 950; }'), 'MemGuard: для эвристики пороги выше');
assert(app.includes('smallDelta: true, persist: false, suppressSummaryToast: true, preserveView: true'), 'лёгкий экспорт: срез таблицы не перестраивается');
assert(app.includes('used = this.usedEstMB();'), 'MemGuard: check использует эвристику в Firefox/Safari');
assert(app.includes('const findByOe = r => {'), 'импорт: поиск SKU прайса только по OE');
assert(!app.includes('analogMap'), 'импорт: поиска по аналогам нет');
assert(app.includes('matchedByKey && (cm.target === \'article\' || cm.target === \'brand\')'), 'импорт: OE-сопоставление не затирает артикул/бренд прайса');
assert(html.includes('Только обогащение по текущему прайсу, новых SKU не создавать'), 'импорт: подпись переключателя прайс-первым');
assert(!app.includes("['returnsRub','Возвраты/невыкуп, ₽/ед — ввод'"), 'калькулятор 24: без отдельных статей возвратов');
assert(!app.includes('Прогноз ЧП / мес, ₽'), 'общий экспорт: без прогноза ЧП/мес');
assert(app.includes("selectedSheets.delete('PnL'); selectedSheets.delete('Поставщики');"), 'без листов PnL/Поставщики');
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
assert(app.includes('12.9.69-client+enrich-catmode') || app.includes('12.9.137-client+secrets-engine'), 'версия клиента обновлена');
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
assert(app.includes('12.9.137-client+secrets-engine'), 'версия клиента обновлена');
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

// v12.9.75: таргетная группировка OE (onlyKeys) эквивалентна полной для затронутых связок
{
  const c2 = {};
  vm.createContext(c2);
  const src =
    'const _normArticleCache = new Map();\n' +
    'const S = { settings: { oeDelimiter: "auto" }, rows: [] };\n' +
    grab(/const normArticle = s => \{[\s\S]*?\n\};\n/) +
    grab(/const OE_DELIMITERS = \{[\s\S]*?\n\}\nfunction mergeCodeLists\(\) \{[\s\S]*?\n\}\n/) +
    'const HVC = {\n' +
    '  normalizeKey(s) { return normArticle(s); },\n' +
    '  identityUnsafe() { return false; },\n' +
    '  ensureNorm(p) { if (!p.oe_norm) p.oe_norm = codeList(p.oe_numbers).map(t => normArticle(t)).filter(Boolean).join(OE_DELIMITERS[oeMode()].join); return p; },\n' +
    '  keyOf(p) { return HVC.normalizeKey(p.article) + "|" + HVC.normalizeKey(p.brand || ""); },\n' +
    '  ' + grab(/groupOeByKeyFromRows\(list,scope,onlyKeys\) \{[\s\S]*?\n    return changed;\n  \},/) + '\n};\n' +
    'this.HVC = HVC; this.normArticle = normArticle;';
  vm.runInContext(src, c2);
  const mk = () => ([
    { article: 'A1', brand: 'B', oe_numbers: '111 / 222', oe_list: '' },
    { article: 'a1', brand: 'b', oe_numbers: '333', oe_list: '' },
    { article: 'C9', brand: 'D', oe_numbers: '999', oe_list: '' },
    { article: 'C9', brand: 'D', oe_numbers: '888', oe_list: '' }
  ]);
  const full = mk(); c2.HVC.groupOeByKeyFromRows(full, {});
  // изменилась только связка A1|B — добавляем OE в одну её строку
  const delta = mk(); delta[0].oe_numbers = '111 / 222 / 777';
  c2.HVC.groupOeByKeyFromRows(delta, {}, new Set(['A1|B']));
  assert.strictEqual(delta[0].oe_numbers, '111 / 222 / 777 / 333', 'таргет: OE связки слиты в одну строку');
  assert.strictEqual(delta[1].oe_numbers, '111 / 222 / 777 / 333', 'таргет: OE разошлись по связке как при полном проходе');
  assert.ok(delta[1].oe_norm.includes('777'), 'oe_norm обновлён');
  assert.strictEqual(delta[2].oe_numbers, '999', 'чужая связка не тронута таргетным проходом');
  assert.strictEqual(delta[3].oe_numbers, '888', 'чужая связка не слита таргетным проходом');
  const fullDelta = mk(); fullDelta[0].oe_numbers = '111 / 222 / 777';
  c2.HVC.groupOeByKeyFromRows(fullDelta, {});
  assert.strictEqual(delta[0].oe_numbers, fullDelta[0].oe_numbers, 'эквивалентность полной группировке (строка 1)');
  assert.strictEqual(delta[1].oe_numbers, fullDelta[1].oe_numbers, 'эквивалентность полной группировке (строка 2)');
  assert.strictEqual(delta[1].oe_norm, fullDelta[1].oe_norm, 'эквивалентность oe_norm');
}
// v12.9.75: импорт — точечный syncOeByKey и таргетная группировка в пайплайне
assert(app.includes('HVC.syncOeByKey(changedList)'), 'импорт: syncOeByKey только по изменённым строкам');
assert(app.includes('groupOeByKeyFromRows(undefined, undefined, _grpOnlyKeys)'), 'пайплайн: таргетная группировка OE при малой дельте');
assert(app.includes('12.9.137-client+secrets-engine'), 'версия клиента обновлена');

// v12.9.76: пайплайн пропускает неизменённые строки при любом известном changedRows
assert(app.includes('if (changedRows && !changedRows.has(old)) continue;'), 'упаковка: пропуск неизменённых строк');
assert(app.includes('if (changedRows && !isChangedRow(p)) { if (typeof AnomalyDetector'), 'расчёт: ранний пропуск неизменённых, карантин сохранён');
assert(app.includes('const _grpOnlyKeys = (changedRows && Array.isArray(options.changedList)'), 'таргетная группировка OE при любой дельте');
assert(app.includes('12.9.137-client+secrets-engine'), 'версия клиента обновлена');

assert(app.includes("classList.contains('active')) UE.render()"), 'импорт: UE.render только для активного раздела');
assert(app.includes("classList.contains('active')) Dash.render()"), 'импорт: Dash.render только для активного раздела');

// v12.9.77: таргетный rebuildIndex эквивалентен полному на OE-графе
{
  const c3 = {};
  vm.createContext(c3);
  const hvcMethods =
    'const HVC = {\n' +
    '  parts: new Map(), oe: new Map(), byArt: new Map(), byOe: new Map(), bySku: new Map(), cross: new Map(), _agg: new Map(), _graph: new Map(),\n' +
    '  normalizeKey(s) { return normArticle(s); },\n' +
    '  identityScope() { return {}; }, identityUnsafe() { return false; }, identityUnsafeKey() { return false; },\n' +
    '  enCol() { return true; }, _clearEnrichCaches() {},\n' +
    '  ensureNorm(p) { if (!p.oe_norm) p.oe_norm = codeList(p.oe_numbers).map(t => normArticle(t)).filter(Boolean).join(OE_DELIMITERS[oeMode()].join); return p; },\n' +
    '  keyOf(p) { return HVC.normalizeKey(p.article) + "|" + HVC.normalizeKey(p.brand || ""); },\n' +
    '  ' + grab(/groupOeByKeyFromRows\(list,scope,onlyKeys\) \{[\s\S]*?\n    return changed;\n  \},/) + '\n' +
    '  ' + grab(/syncOeByKey\(list,scope\) \{[\s\S]*?\n    return changed;\n  \},/) + '\n' +
    '  ' + grab(/_groupOnly\(key\) \{[\s\S]*?\n    return out;\n  \},/) + '\n' +
    '  ' + grab(/rebuildIndex\(list, onlyKeys\) \{[\s\S]*?\n  \},\n/) + '\n};\nthis.HVC = HVC;';
  vm.runInContext(
    'const _normArticleCache = new Map();\nconst S = { settings: { oeDelimiter: "auto" }, rows: [] };\n' +
    grab(/const normArticle = s => \{[\s\S]*?\n\};\n/) +
    grab(/const OE_DELIMITERS = \{[\s\S]*?\n\}\nfunction mergeCodeLists\(\) \{[\s\S]*?\n\}\n/) +
    hvcMethods, c3);
  const mkRows = () => ([
    { article: 'A1', brand: 'B', oe_numbers: '111', oe_list: '' },
    { article: 'A1', brand: 'B', oe_numbers: '222', oe_list: '' },
    { article: 'C1', brand: 'D', oe_numbers: '222', oe_list: '' },
    { article: 'E1', brand: 'F', oe_numbers: '999', oe_list: '' },
    { article: 'G1', brand: 'H', oe_numbers: '555', oe_list: '' }
  ]);
  const prep = rows => { // реестр parts + первичная ПОЛНАЯ перестройка (как при загрузке)
    for (const p of rows) { const k = c3.HVC.keyOf(p); if (!c3.HVC.parts.has(k)) c3.HVC.parts.set(k, { artikul: p.article, brand: p.brand }); }
    c3.HVC.rebuildIndex(rows);
  };
  const rowsFull = mkRows(); prep(rowsFull);
  const HVC2parts = new Map(c3.HVC.parts);
  // сброс реестра ко второму экземпляру: пересобираем состояние вручную через JSON-снимок карт нельзя —
  // поэтому второй набор строк обрабатываем тем же HVC после очистки индексов:
  const snap = r => r.map(p => [p.oe_numbers, p.oe_list, p.oe_norm, p.group_articles, p.groupSize].join('~')).join('\n');
  rowsFull[0].oe_numbers = '111 / 999'; // импорт: связка A получила OE 999 (мост к E)
  c3.HVC.rebuildIndex(rowsFull);        // полный проход
  const rowsTg = mkRows();
  // реестр возвращаем к исходному: полная перестройка на исходных строках, затем таргетная после той же мутации
  c3.HVC.byArt.clear(); c3.HVC.byOe.clear(); c3.HVC.bySku.clear(); c3.HVC.cross.clear(); c3.HVC.oe.clear();
  prep(rowsTg);
  rowsTg[0].oe_numbers = '111 / 999';
  c3.HVC.rebuildIndex(rowsTg, new Set(['A1|B'])); // таргетный проход
  assert.strictEqual(snap(rowsTg), snap(rowsFull), 'таргетный rebuildIndex == полный (OE, группы, размеры)');
  assert.ok(rowsTg[2].group_articles.includes('A1'), 'группа связанной связки C обновилась через byOe');
  assert.ok(rowsTg[3].group_articles.includes('A1'), 'группа связки E обновилась через новый OE');
}
// v12.9.77: таргетный dedupe сливает только заданные связки, полный — все
{
  const c4 = {};
  vm.createContext(c4);
  vm.runInContext(
    'const _normArticleCache = new Map();\n' +
    'const S = { settings: { oeDelimiter: "auto" }, rows: [] };\n' +
    'const CODE_FIELDS = ["article","originalArticle","barcode","markCode"];\n' +
    'function articleText(v) { return String(v); }\n' +
    grab(/const normArticle = s => \{[\s\S]*?\n\};\n/) +
    grab(/const OE_DELIMITERS = \{[\s\S]*?\n\}\nfunction mergeCodeLists\(\) \{[\s\S]*?\n\}\n/) +
    grab(/function codeFieldsToStr\(p\) \{[\s\S]*?\n\}\n/) +
    'function sourceSkuKey(v) { return String(v || ""); }\nfunction sourceBrandKey(v) { return String(v || ""); }\n' +
    'function ozonSourceMap() { return {}; }\nfunction isRemovedDbsName() { return false; }\n' +
    'const CategoryTnved = { typeInfo() { return { value: "", conflict: false }; }, findCode() { return ""; } };\n' +
    grab(/function dedupeCatalog\(onlyFull\) \{[\s\S]*?\n  return merged;\n\}\n/) +
    'this.S = S; this.dedupeCatalog = dedupeCatalog;', c4);
  const mk = () => ([
    { article: 'X1', brand: 'B', price: 100, name: 'первый' },
    { article: 'X1', brand: 'B', price: 100, name: 'первый', stock: 5 },
    { article: 'Y1', brand: 'B', price: 200, name: 'второй' },
    { article: 'Y1', brand: 'B', price: 200, name: 'второй', stock: 7 }
  ]);
  c4.S.rows = mk();
  const mT = c4.dedupeCatalog(new Set(['X1|B']));
  assert.strictEqual(mT, 1, 'таргетный dedupe: слита одна пара');
  assert.strictEqual(c4.S.rows.length, 3, 'чужая дублирующая пара не тронута');
  assert.strictEqual(c4.S.rows[0].stock, 5, 'поля слиты в первую строку');
  c4.S.rows = mk();
  const mF = c4.dedupeCatalog(null);
  assert.strictEqual(mF, 2, 'полный dedupe: слиты обе пары');
  assert.strictEqual(c4.S.rows.length, 2);
}
// v12.9.77: импорт — таргетные rebuildIndex/dedupe и запись дельты при любой доле
assert(app.includes('HVC.rebuildIndex(S.rows, _rbKeys.size ? _rbKeys : undefined)'), 'импорт: таргетный rebuildIndex');
assert(app.includes('dedupeCatalog(_dedupeKeys)'), 'импорт: таргетный dedupe после первого полного');
assert(app.includes('persistChangedOnly: changedTouched > 0 && !dedup'), 'импорт: запись только дельты, если не было слияний');
assert(app.includes('12.9.137-client+secrets-engine'), 'версия клиента обновлена');

// v12.9.78: автосверка аномалий находит донора через реестр byOe (функционально, настоящий AnomalyOE+DimPolicy)
;(async () => {
  const c5 = { console, Set, Map, WeakMap, WeakSet, JSON, Math, Number, String, Array, Object, Date, RegExp, Error, Promise, performance, setTimeout,
    normArticle: s => String(s == null ? '' : s).toUpperCase().replace(/[^A-Z0-9А-ЯЁ]/g, ''),
    num: v => { const n = parseFloat(String(v == null ? '' : v).replace(',', '.')); return isFinite(n) ? n : 0; },
    fmt: v => String(v), round: (v, d = 2) => { const p = 10 ** d; return Math.round(v * p) / p; },
    nowISO: () => '2026-01-01', productVolumeIsExplicit: () => false,
    Toast: { info() {}, warn() {}, err() {}, ok() {} },
    STD: [{ k: 'weight', n: 'Вес, кг' }, { k: 'length', n: 'Длина, см' }, { k: 'width', n: 'Ширина, см' }, { k: 'height', n: 'Высота, см' }],
    S: { rows: [], catalogVersion: 0, settings: {} },
    HVC: { oe: new Map(), byOe: new Map(), byArt: new Map(), parts: new Map(), cross: new Map(), ozonRevision: 0 },
    AnomalyDetector: { found: [], log: [], renderLog() {}, save() {}, evaluate: () => ({ issues: [] }), getLimit: () => ({ category: '', maxW: 0, maxL: 0, maxVol: 0 }), signature: () => 'sig' },
    runPipeline: async () => 0,
    withProgress: async (t, s2, fn) => fn(() => {}) };
  c5.globalThis = c5;
  c5.codeList = v => { const out = [], seen = new Set(); for (const part of (Array.isArray(v) ? v : [v])) for (const x of String(part == null ? '' : part).split(/[\/;,|]+/)) { const t = x.trim(); if (t && !seen.has(t)) { seen.add(t); out.push(t); } } return out; };
  vm.createContext(c5);
  vm.runInContext(grab(/const DimPolicy = \{[\s\S]*?\n\};\n/) + grab(/const AnomalyOE = \{[\s\S]*?\n\};\n/) + '\nthis.AnomalyOE=AnomalyOE;', c5);
  const A = c5.AnomalyOE; A.render = () => {};
  const T = { article: 'T1', brand: 'B', oe_numbers: 'OE1', oe_list: '', weight: 0, length: 0, width: 0, height: 0, dimensionAnomalyBlocked: true, category: 'Фильтры' };
  const D = { article: 'D1', brand: 'B', oe_numbers: 'OE1', oe_list: '', weight: 1, length: 10, width: 5, height: 5, category: 'Фильтры',
    _dimensionAutoEvidence: { file: 'dims.csv', row: 7, identity: 'D1|B', weight: 1, length: 10, width: 5, height: 5, entries: [{ code: 'OE1' }] } };
  const U = { article: 'U1', brand: 'Z', oe_numbers: 'OE9', oe_list: '', weight: 2, length: 20, width: 6, height: 6, category: 'Фильтры' };
  c5.S.rows = [T, D, U];
  c5.HVC.byOe.set('OE1', new Set(['D1|B'])); c5.HVC.byArt.set('D1|B', new Set(['OE1'])); c5.HVC.byArt.set('T1|B', new Set(['OE1']));
  c5.AnomalyDetector.found = [{ p: T }];
  const res = await A.find({ automatic: true });
  assert.strictEqual(res.checked, 1, 'автосверка: проверена одна цель');
  assert.ok(A.preview[0].choice, 'автосверка: донор найден через реестр byOe, без прохода по каталогу');
  assert.strictEqual(T.length, 10, 'автосверка: габариты донора применены');
  assert.ok(T._dimensionOeReview, 'автосверка: строка помечена к проверке упаковки');
})().catch(e => { console.error(e); process.exit(1); });
// v12.9.78: триггер полного пересчёта по отпечатку глобальных параметров
{
  const store = new Map();
  const c6 = { S: { settings: { ozonCommissionPct: 14, ozonLogisticsManual: 0, gasUrl: 'x' }, tariffs: { fixed: 1000, list: [1, 2] }, cats: [{}], rules: [], excs: [] },
    num: v => { const n = parseFloat(v); return isFinite(n) ? n : 0; },
    lsGet: k => store.get(k) || null, lsSet: (k, v) => store.set(k, v) };
  vm.createContext(c6);
  vm.runInContext(grab(/function globalParamsFp\(\) \{[\s\S]*?\n\}\nfunction fullRecalcStale\(\) \{[\s\S]*?\n\}\n/) + '\nthis.globalParamsFp=globalParamsFp; this.fullRecalcStale=fullRecalcStale;', c6);
  assert.strictEqual(c6.fullRecalcStale(), false, 'нет сохранённого отпечатка — не устарело');
  c6.lsSetRef = null; store.set('uc.fullCalcFp', c6.globalParamsFp());
  assert.strictEqual(c6.fullRecalcStale(), false, 'отпечаток актуален — не устарело');
  c6.S.settings.ozonCommissionPct = 20;
  assert.strictEqual(c6.fullRecalcStale(), true, 'ставка изменилась после полного пересчёта — устарело');
  c6.S.settings.ozonCommissionPct = 14; c6.S.settings.gasUrl = 'другой';
  assert.strictEqual(c6.fullRecalcStale(), false, 'неэкономическая настройка триггер не дёргает');
}
assert(app.includes('const donorRows=[];'), 'автосверка: отбор доноров по реестру');
assert(app.includes("lsSet('uc.fullCalcFp', globalParamsFp())"), 'полный пересчёт фиксирует отпечаток параметров');
assert(app.includes('профиль дельты: изменено строк'), 'журнал импорта: профиль дельты');
assert(app.includes('12.9.137-client+secrets-engine'), 'версия клиента обновлена');

// v12.9.93: потоковый CSV-парсер — разрезы чанков в любом месте не меняют результат
{
  const c7 = {};
  vm.createContext(c7);
  vm.runInContext(grab(/const CsvStream = \{[\s\S]*?\n\};\n/) + '\nthis.CsvStream=CsvStream;', c7);
  const csv = 'Артикул;Бренд;Цена;Описание\r\nA1;BOSCH;149,81;"Фильтр; масляный ""новый"""\nA2;MANN;4,5;"много\nстрочный"\r\nA3;;0;\n';
  const parseAll = chunks => {
    const out = [];
    const p = c7.CsvStream.createParser(';', r => out.push(r));
    for (const ch of chunks) p.feed(ch);
    p.end();
    return out;
  };
  const whole = parseAll([csv]);
  assert.strictEqual(whole.length, 4, 'CsvStream: заголовок + 3 строки');
  assert.strictEqual(whole[1][3], 'Фильтр; масляный "новый"', 'CsvStream: кавычки и разделитель внутри ячейки');
  assert.strictEqual(whole[2][3], 'много\nстрочный', 'CsvStream: перевод строки внутри кавычек');
  assert.strictEqual(whole[1][2], '149,81', 'CsvStream: десятичная запятая текстом');
  assert.deepStrictEqual(parseAll([...csv]), whole, 'CsvStream: подача по одному символу');
  for (let cut = 1; cut < csv.length; cut += 17)
    assert.deepStrictEqual(parseAll([csv.slice(0, cut), csv.slice(cut)]), whole, 'CsvStream: разрез на ' + cut);
  assert.strictEqual(c7.CsvStream.detectSep('a;b;c'), ';', 'CsvStream: разделитель ;');
  assert.strictEqual(c7.CsvStream.detectSep('a,b,c'), ',', 'CsvStream: разделитель ,');
}
// v12.9.93: дисковый импорт — поток в IndexedDB, не в память
assert(app.includes('const DiskImport = {'), 'дисковый импорт присутствует');
assert(app.includes("db.products_stage.bulkPut(part)"), 'дисковый импорт: пакеты пишутся в IndexedDB');
assert(app.includes('crossByPair'), 'дисковый импорт: кроссы — только OE-индекс');
assert(html.includes('id="btnDiskImport"'), 'кнопка дискового импорта в интерфейсе');
assert(app.includes('skipEconomics: true, persist: false, onProgress: prog, stepRange: [82, 97]'), 'дисковый импорт: экономика лениво, запись одной порцией');

// v12.9.94: пакет оптимизаций
assert(app.includes('12.9.137-client+secrets-engine'), 'версия 12.9.94');
assert(app.includes('econSkipFresh'), 'пропуск пересчёта актуальной экономики');
assert(app.includes("S._econFreshKey = _econFreshKey"), 'отметка актуальности экономики фиксируется');
assert(app.includes('расчётные поля экономики (досчёт при экспорте)'), 'MemGuard: автосброс экономики при давлении памяти');
assert(app.includes('_catFpMemo'), 'catFp: мемоизация отпечатка');
assert(app.includes('дедупликация при загрузке пропущена'), 'старт: пропуск дедупликации при совпадении отпечатка');
assert(app.includes('_diskAbort'), 'дисковый импорт: отмена пользователем');
assert(app.includes('HVC.ingest(part)'), 'дисковый импорт: реестры Каталога V пополняются пакетами');
assert(app.includes('запись каталога одной порцией'), 'дисковый импорт: без второй полной записи пайплайна');

// v12.9.95: золотые фикстуры экономики (эталонные выгрузки владельца, 12 SKU)
{
  const readGolden = name => {
    const txt = fs.readFileSync(__dirname + '/../' + name, 'utf8').replace(/^\uFEFF/, '');
    const lines = txt.split(/\r?\n/).filter(l => l.trim());
    const head = lines[0].split(';');
    return lines.slice(1).map(l => { const c = l.split(';'); const o = {}; head.forEach((h, i) => o[h] = c[i]); return o; });
  };
  const rec = readGolden('UC_unit_economics_OZON_2026-11-06_recalculated.csv');
  const fil = readGolden('UC_unit_economics_OZON_2026-11-06_filtered.csv');
  assert.strictEqual(rec.length, 12, 'golden: 12 SKU в пересчитанной выгрузке');
  assert.strictEqual(fil.length, 12, 'golden: 12 SKU в отфильтрованной выгрузке');
  const byArt = rows => new Map(rows.map(r => [r['Артикул'], r]));
  const rm = byArt(rec), fm = byArt(fil);
  assert.deepStrictEqual([...rm.keys()].sort(), [...fm.keys()].sort(), 'golden: состав SKU совпадает');
  for (const [art, r] of rm) {
    assert.strictEqual(r['Цена, ₽/ед.'], fm.get(art)['Цена, ₽/ед.'], 'golden: цена SKU ' + art + ' стабильна между выгрузками');
  }
}
// v12.9.95: воркер XLSX дискового импорта на настоящем SheetJS
{
  const c8 = { console, Uint8Array, Array, Object, String, Math, JSON, Promise, setTimeout };
  c8.self = { msgs: [], postMessage(m) { this.msgs.push(m); } };
  vm.createContext(c8);
  vm.runInContext(scripts[1], c8);
  assert(c8.XLSX, 'SheetJS поднялся в контексте воркера');
  vm.runInContext(grab(/function DiskXlsxWorkerMain\(\) \{[\s\S]*?\n\}\n/) + '\nDiskXlsxWorkerMain();', c8);
  const wb8 = c8.XLSX.utils.book_new();
  c8.XLSX.utils.book_append_sheet(wb8, c8.XLSX.utils.aoa_to_sheet(
    [['Бренд', 'Каталожный номер', 'Цена'], ['BOSCH', 'A100', '149,81'], ['MANN', 'B200', 200]]), 'Прайс');
  const buf8 = c8.XLSX.write(wb8, { type: 'array', bookType: 'xlsx' });
  c8.self.onmessage({ data: { type: 'load', buf: buf8 } });
  const h8 = c8.self.msgs.find(m => m.type === 'headers');
  assert(h8 && h8.rows[1] === 'Каталожный номер', 'воркер XLSX: заголовки получены');
  c8.self.onmessage({ data: { type: 'go' } });
  const rows8 = c8.self.msgs.filter(m => m.type === 'batch').flatMap(b => b.rows);
  assert.strictEqual(rows8.length, 2, 'воркер XLSX: строки без заголовка');
  assert.strictEqual(rows8[0][2], '149,81', 'воркер XLSX: значение ячейки текстом');
}
// v12.9.95: остальные разделы пакета
assert(app.includes('12.9.137-client+secrets-engine'), 'версия 12.9.95');
assert(app.includes('warnQuarantinedBeforeExport'), 'карантин: предупреждение перед выгрузкой');
assert(app.includes("await CsvStream.rows(file, r => { table.push(r); }"), 'обычный импорт: потоковый разбор CSV');
assert(app.includes('let first = true;'), 'дисковый импорт: заголовок файла не попадает в данные');
assert(app.includes('покрытие OE: '), 'дисковый импорт: отчёт о покрытии кроссами');
assert(app.includes('oePairSets'), 'дисковый импорт: неоднозначные OE считаются');
assert(app.includes('_xlsxBegin'), 'дисковый импорт: XLSX через воркер');
assert(app.includes('const SettingsSnapshot = {'), 'снимок настроек присутствует');
assert(html.includes('id="btnSettingsSnapshot"'), 'кнопка снимка настроек в интерфейсе');

// v12.9.96: отмена загрузки во всех разделах импорта
assert(html.includes('id="prCancel"'), 'кнопка отмены в общем индикаторе прогресса');
assert(app.includes('const UCCancel = {'), 'токен отмены присутствует');
assert(app.includes("e._ucCancelled = true"), 'отмена помечается для мягкой обработки');
assert(app.includes("if (typeof UCCancel !== 'undefined') UCCancel.check();"), 'проверки отмены в длинных циклах');
assert(app.includes("Toast.warn('Отменено пользователем'"), 'отмена — предупреждение, а не ошибка');
assert(app.includes('12.9.137-client+secrets-engine'), 'версия 12.9.96');
// токен отмены работает как чистая логика
{
  const c9 = {};
  vm.createContext(c9);
  vm.runInContext(grab(/const UCCancel = \{[\s\S]*?\n\};\n/) + '\nthis.UCCancel=UCCancel;', c9);
  c9.document = { getElementById: () => null };
  c9.UCCancel.check();
  c9.UCCancel.requested = true;
  assert.throws(() => c9.UCCancel.check(), /отменена пользователем/, 'UCCancel.check бросает при запрошенной отмене');
}

// v12.9.97: очередь ручной проверки — кандидаты, память решений, Левенштейн
{
  const c10 = { S: { rows: [] }, lsGet: () => null, lsSet: () => true, console };
  vm.createContext(c10);
  vm.runInContext(
    grab(/const num = v => \{[\s\S]*?\n\};\n/) +
    'const _normArticleCache = new Map();\n' +
    grab(/const normArticle = s => \{[\s\S]*?\n\};\n/) +
    grab(/const OE_DELIMITERS = \{[\s\S]*?function mergeCodeLists\(\) \{[\s\S]*?\n\}\n/) +
    grab(/const ReviewQueue = \{[\s\S]*?\n\};\n/) +
    '\nthis.ReviewQueue=ReviewQueue; this.normArticle=normArticle;', c10);
  const R = c10.ReviewQueue;
  assert.strictEqual(R._lev('A100', 'A101', 2), 1, 'Левенштейн: замена = 1');
  assert.strictEqual(R._lev('A100', 'XYZ99', 2) > 2, true, 'Левенштейн: далёкие строки отсекаются');
  c10.S.rows = [
    { article: 'F100', brand: 'BOSCH', name: 'Фильтр масляный', oe_numbers: 'OE1', oe_list: '', length: 10, width: 6, height: 6, weight: 0.3, analog_list: '' },
    { article: 'F200', brand: 'MANN', name: 'Фильтр масляный аналог', oe_numbers: 'OE1', oe_list: '', length: 20, width: 6, height: 6, weight: 0.5, analog_list: '' },
    { article: 'X900', brand: 'BOSCH', name: 'Свеча зажигания', oe_numbers: '', oe_list: '', analog_list: 'GHOST1' },
    { article: 'ABC12345', brand: 'FEBI', name: 'Рычаг подвески левый', oe_numbers: '', oe_list: '', analog_list: '' },
    { article: 'ABC12346', brand: 'FEBI', name: 'Рычаг подвески правый', oe_numbers: '', oe_list: '', analog_list: '' }
  ];
  const q = R.generate();
  const kinds = new Set(q.map(c => c.kind));
  assert(kinds.has('oe-dims-conflict'), 'очередь: конфликт габаритов по OE найден');
  assert(kinds.has('cross-dangling'), 'очередь: висячий кросс найден');
  assert(kinds.has('fuzzy'), 'очередь: fuzzy-пара найдена');
  const fuzzy = q.find(c => c.kind === 'fuzzy');
  assert(fuzzy && fuzzy.confidence !== 'high', 'fuzzy не бывает высокой уверенности');
  // решённая пара повторно не предлагается
  const saved = {};
  c10.lsGet = () => JSON.stringify(saved);
  saved[fuzzy.id] = { d: 'reject', at: 'x' };
  assert(!R.generate().some(c => c.id === fuzzy.id), 'очередь: отклонённая пара скрыта');
}
// v12.9.97: статические гарантии
assert(app.includes('const ReviewQueue = {'), 'модуль очереди проверки');
assert(app.includes('uc.reviewDecisions'), 'память решений оператора');
assert(app.includes('Артикулы пришли числами (XLSX)'), 'QA: артикулы-числа в XLSX');
assert(html.includes('id="btnReviewExport"') && html.includes('id="btnReviewImport"'), 'кнопки очереди проверки');
assert(app.includes('12.9.137-client+secrets-engine'), 'версия 12.9.97');

// v12.9.98 (аудит): round() в формулах = Excel-стиль, как round() приложения
{
  const c11 = { console };
  vm.createContext(c11);
  vm.runInContext(grab(/const ExprLang = \(function \(\) \{[\s\S]*?\n\}\)\(\);\n/) + '\nthis.ExprLang=ExprLang;', c11);
  const E = c11.ExprLang;
  assert.strictEqual(E.eval('round(2.5, 0)', {}), 3, 'формулы: 2.5 -> 3');
  assert.strictEqual(E.eval('round(-2.5, 0)', {}), -3, 'формулы: -2.5 -> -3 (от нуля, как Excel)');
  assert.strictEqual(E.eval('round(2.675, 2)', {}), 2.68, 'формулы: 2.675 -> 2.68 (не 2.67)');
  assert.strictEqual(E.eval('round(31363.499999999996, 0)', {}), 31364, 'формулы: грязная половина -> вверх');
  assert.strictEqual(E.eval('1 + 2 * 3', {}), 7, 'формулы: приоритет операций');
  assert.strictEqual(E.eval('10 / 4', {}), 2.5, 'формулы: деление');
}
assert(app.includes('12.9.137-client+secrets-engine'), 'версия 12.9.98');
assert(app.includes('aAnalogs.includes(B.art)'), 'очередь: аналоги сравниваются токенами, не подстрокой');

// v12.9.99 (аудит-2): cloneRowForCalc не теряет компактные поля (объём!)
{
  const c12 = { console };
  vm.createContext(c12);
  vm.runInContext(
    grab(/const CALC_NUM_FIELDS = \[[\s\S]*?\];\n/) +
    grab(/const CALC_IDX = Object\.create\(null\);[\s\S]*?function compactRowNumeric\(p\) \{[\s\S]*?\n\}\n/) +
    grab(/function cloneRowForCalc\(p\) \{[\s\S]*?\n\}\n/) +
    '\nthis.compactRowNumeric=compactRowNumeric; this.cloneRowForCalc=cloneRowForCalc;', c12);
  const src = c12.compactRowNumeric({ article: 'V1', price: 500, volume: 3.5, margin: 12.5, cheapFbsReason: 'причина' });
  const lost = Object.assign({}, src);
  assert.strictEqual(lost.volume, undefined, 'контроль: голый Object.assign теряет volume компактной строки');
  const c = c12.cloneRowForCalc(src);
  assert.strictEqual(c.volume, 3.5, 'клон для расчёта: volume сохранён');
  assert.strictEqual(c.margin, 12.5, 'клон для расчёта: margin сохранён');
  assert.strictEqual(c.cheapFbsReason, 'причина', 'клон для расчёта: строковое поле сохранено');
  assert.strictEqual(c.article, 'V1', 'клон для расчёта: обычные поля сохранены');
  c.volume = 9; assert.strictEqual(src.volume, 3.5, 'клон независим от оригинала');
}
assert(app.includes('12.9.137-client+secrets-engine'), 'версия 12.9.99');
assert(app.includes('computeEconomics(cloneRowForCalc(p))'), 'WhatIf считает на полном клоне');
assert(app.includes('const c = cloneRowForCalc(p);'), 'сценарий «что если» на полном клоне');

// v12.9.100 (аудит — закрытие находок): ступенчатое хранение WB, ноль продаж, if()
{
  const c13 = { console };
  vm.createContext(c13);
  vm.runInContext(grab(/const ExprLang = \(function \(\) \{[\s\S]*?\n\}\)\(\);\n/) + '\nthis.ExprLang=ExprLang;', c13);
  const E = c13.ExprLang;
  // невыбранная ветка if() не вычисляется: дата там не должна ломать формулу
  assert.strictEqual(E.eval('if(1, 10, num(d))', { d: new Date() }), 10, 'if(): ленивая ветка');
  assert.throws(() => E.eval('1.2.3 + 1', {}), /Некорректное число/, 'литерал 1.2.3 запрещён');
}
assert(app.includes('wbStorageDayRate'), 'хранение WB ступенчатое (первый литр + 7/15)');
assert(html.includes('value="0.15" title="Ставка за ПЕРВЫЙ литр'), 'ставка хранения WB по умолчанию 0.15 ₽/л/день');
assert(app.includes('if (!(num(baseEco.sales) > 0)) { baseEco.breakEvenPrice = 0; baseEco.tgtPrice = 0; return baseEco; }'), 'без прогноза продаж безубыток не выдумывается');
assert(app.includes('eco.solverNetUnit = sales > 0 ? eco.netProfit / sales : eco.contribution;'), 'юнит при нулевых продажах = вклад единицы');
assert(!app.includes('function fbsLogistics('), 'мёртвая fbsLogistics удалена');
assert(html.includes('ttlSec <= 21600 + SKEW'), 'GAS: одноразовость только для токенов ≤ 6 ч');
assert(html.includes('освобождение — до 20 млн ₽/год, 5% — до 272,5 млн ₽, 7% — до 490,5 млн ₽'), 'подсказка о порогах НДС УСН');
assert(app.includes('12.9.137-client+secrets-engine'), 'версия 12.9.100');

// v12.9.101: интеграция локального Python-движка
assert(app.includes('const PyEngine = {'), 'модуль PyEngine в приложении');
assert(app.includes('/calc/batch'), 'сверка экономики вторым контуром');
assert(app.includes('uc.pyToken'), 'токен движка в localStorage');
assert(html.includes('id="btnPyCheck"') && html.includes('id="pyEngineStatus"'), 'кнопка и статус Python-движка');
assert(app.includes('12.9.137-client+secrets-engine'), 'версия 12.9.101');
assert(app.includes('window.__UC_PY_TOKEN__ || lsGet'), 'авто-токен движка без ручной вставки');

assert(app.includes('async recalcCatalog()'), 'полный пересчёт каталога на движке');
assert(app.includes('/catalog/recalc') && app.includes('/catalog/results'), 'протокол пересчёта движка');
assert(html.includes('id="btnPyRecalc"'), 'кнопка пересчёта каталога на Python');
assert(app.includes('importFile() {') && app.includes("'/import/file'"), 'импорт файла на движке');
assert(app.includes('async enrichOe()') && app.includes("'/catalog/enrich'"), 'обогащение OE на движке');
assert(html.includes('id="btnPyImport"') && html.includes('id="btnPyEnrich"'), 'кнопки импорта и обогащения Python');

// v12.9.107: сводка каталога на движке (SQL-агрегаты)
assert(app.includes("'/report/dashboard'") && app.includes('async dashboard()'), 'сводка каталога на движке');
assert(app.includes('btnPyDashboard'), 'кнопка сводки каталога');

// v12.9.108: экспорт каталога на движке
assert(app.includes("'/export/catalog.xlsx'") && app.includes('async exportCatalog()'), 'экспорт каталога на движке');
assert(app.includes('btnPyExport') && app.includes('_syncCatalog'), 'кнопка экспорта и общий синк каталога');

// v12.9.109: параллельный пересчёт на движке
assert(app.includes('rec.parallel'), 'приложение показывает параллельный пересчёт');

// v12.9.110: полное обогащение на движке
assert(app.includes("'/catalog/enrich-full'") && app.includes('async enrichFull()'), 'полное обогащение на движке');
assert(app.includes("'/donors/import'") && app.includes('btnPyEnrichFull'), 'доноры Каталога V и кнопка полного обогащения');
assert(app.includes("'category', 'tnved', 'applicability'"), 'слияние расширенных полей только в пустые');

// v12.9.111: обобщённый разбор файлов на движке для прочих импортов
assert(app.includes("'/parse/file'") && app.includes('async parseFile(f)'), 'разбор файла на движке');
assert(app.includes("'/parse/rows?parse_id='"), 'постраничная выдача разбора');
assert(app.includes('rows = await PyEngine.parseFile(f)'), 'импорт конкурентов через движок с откатом');

// v12.9.112: история цен и снапшоты на движке
assert(app.includes("'/report/price-changes?days=30'") && app.includes('async priceHistory()'), 'история цен на движке');
assert(app.includes('btnPyHistory') && app.includes('btnPySnapshot'), 'кнопки истории цен и снапшота');

// v12.9.113: fuzzy-подсказки аналогов — только оператору
assert(app.includes("'/analogs/suggestions?limit=100'") && app.includes('async analogHints()'), 'подсказки аналогов на движке');
assert(app.includes('Автоматически аналоги НЕ проставлены'), 'авто-поиск аналогов по-прежнему запрещён');

// v12.9.114: UI сравнения снапшотов
assert(app.includes("'/snapshots/diff?from='") && app.includes('async snapshotDiff()'), 'сравнение снапшотов в UI');
assert(app.includes('btnPySnapshotDiff'), 'кнопка сравнения снапшотов');

// v12.9.115: выгрузка OZON на движке (этап 1)
assert(app.includes("'/export/ozon.' + ext") && app.includes('async exportOzon(format, articlesOverride)'), 'выгрузка OZON на движке');
assert(app.includes('btnPyOzon') && app.includes("ozon_type: p.ozon_type || ''"), 'кнопка OZON и синк полей карточки');

// v12.9.116: OZON этап 2 — скоуп выделенных
assert(app.includes('selArticles') && app.includes('articles: selArticles, discount_pct: discount'), 'выгрузка OZON по выделенным через движок');

// v12.9.117: OZON этап 3 — пары справочника в движок
assert(app.includes("'/ozon/pairs/import'") && app.includes('OzonReference.entries()'), 'пары категория-тип уходят в движок перед выгрузкой');

// v12.9.119: инкрементальный пересчёт на движке
assert(app.includes('инкрементальный пересчёт'), 'приложение показывает пропущенные без изменений SKU');

// v12.9.121: движок встроен в существующие кнопки, отдельной Python-строки нет
assert(!app.includes('Python: пересчитать каталог') && !app.includes('>Python: '), 'отдельных Python-кнопок в интерфейсе нет');
assert(app.includes("if (await PyEngine.health()) PyEngine.importFile(); else Import.pick();"), 'импорт: движок первым, мастер — откат');
assert(app.includes("if (await PyEngine.health()) PyEngine.exportOzon(); else OzonExport.open();"), 'экспорт OZON: движок первым, обычная выгрузка — откат');
assert(html.includes('Локальный движок (SQLite) · операции с каталогом'), 'действия движка живут в окне Каталог V');

// v12.9.122: токен проверяется автоматически после сохранения
assert(app.includes('async verifyAuth()') && app.includes("'bad-token'"), 'авторизованная проверка токена (200/401)');
assert(app.includes('Токен верный — движок подключён') && !app.includes('Проверьте статус движка кнопкой'), 'тост о токене не ссылается на несуществующие кнопки');

// v12.9.123: библиотеки встроенные, текст ошибки не про CDN
assert(app.includes('Не загрузились встроенные библиотеки') && !app.includes('Не загрузились CDN-библиотеки'), 'честный текст проверки библиотек');

// v12.9.125: самовосстановление встроенных библиотек
assert(app.includes('function recoverEmbeddedLibs()'), 'самовосстановление библиотек на месте');
{
  const libText = html.match(/<script>(\/\*! xlsx встроен офлайн[\s\S]*?)<\/script>/)[1];
  const rctx = { console, setTimeout: () => 0, clearTimeout: () => {} };
  rctx.window = rctx; rctx.self = rctx;
  const fakeEl = { textContent: libText, style: {} };
  rctx.document = { scripts: [fakeEl] };
  vm.createContext(rctx);
  vm.runInContext(grab(/function recoverEmbeddedLibs\(\) \{[\s\S]*?\n\}\n/), rctx);
  vm.runInContext('recoverEmbeddedLibs()', rctx);
  assert(vm.runInContext('window.XLSX && XLSX.version', rctx) === '0.18.5', 'XLSX восстановлен вручную');
  assert(fakeEl.style.display === 'none', 'восстановленный блок скрыт');
}

// v12.9.126: диагностика библиотек в баннере
assert(app.includes('__libRecovery') && app.includes('/diag'), 'баннер показывает диагностику восстановления и ссылку на /diag');

// v12.9.127: восстановление вставкой скрипта + битый фрагмент в диагностике
assert(app.includes('восстановлена вставкой скрипта') && app.includes('фрагмент'), 'диагностика места ошибки библиотеки');

// v12.9.129: запуск движка из HTML одной ссылкой + автопереход
assert(app.includes('unitcontrol://start') && app.includes('_fileModeWatch'), 'ссылка запуска движка и автопереход на его адрес');

// v12.9.130: предпроверка места перед сохранением и экспортом
assert(app.includes('async function warnIfLowStorage') && app.includes('storageFreeInfo'), 'проверка свободного места браузера');
assert(app.includes("warnIfLowStorage('сохранения каталога')") && app.includes("warnIfLowStorage('экспорта')"), 'проверка подключена к сохранению и экспорту');

// v12.9.131: все экспорты при живом движке идут через SQL
assert(app.includes('async exportCatalogFormat') && app.includes('_download('), 'движок: общий экспорт каталога по формату');
assert(app.includes("PyEngine.exportOzon(opts0.fmt === 'xlsx' ? 'xlsx' : 'csv'"), 'OzonExport.run ходит в движок');
assert(app.includes('await PyEngine.exportCatalogFormat(fmtChoice'), 'Exp.run ходит в движок для общих форматов');
assert(app.includes("return PyEngine.exportOzon('xlsx'"), 'прямая кнопка XLSX ходит в движок');

// v12.9.132: массовый пересчёт каталога — на движке (SQL), браузер — запасной путь
assert(app.includes('async recalcAndApply(prog)') && app.includes('await PyEngine.recalcAndApply(null)'), 'ensureEconomics сначала идёт в движок');
assert(app.includes("p.pyEngineCalc = '12.9.136'"), 'строки помечены расчётом движка');

// v12.9.134 (аудит): единая синхронизация у пересчёта
assert(app.includes("await this._syncCatalog('app-recalc')"), 'A6: recalcAndApply использует полную синхронизацию');

// v12.9.136 (аудит №2): честная маркировка цифр движка
assert(app.includes('Экономика посчитана движком (SQL)') && app.includes('по плоским ставкам движка'), 'B2: предупреждение о плоских ставках');
assert(app.includes("p.pyEngineCalc = '12.9.136'"), 'строки помечены версией расчёта движка');

// v12.9.137 (B6): секреты площадок — в движке, не в localStorage
assert(app.includes('SECRET_SETTING_KEYS') && app.includes("lsGet('uc.secretsInEngine')"), 'секретные поля вырезаются из сохраняемых настроек');
assert(app.includes('async migrateSecrets') && app.includes('async loadSecrets'), 'миграция и подгрузка секретов из движка');
