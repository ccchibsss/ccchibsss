// Переоткрытие базы не должно менять состояние каталога.
// NODE_PATH=.arena/idb-tests/node_modules node tests/persist-reopen-parity-indexeddb.js
//
// Что здесь было сломано (v12.9.171, воспроизведено этим файлом):
//   slimOf намеренно не пишет oe_list (дубль oe_numbers) и oe_norm (дубль после
//   нормализации). article_norm пересчитывает конвейер, а эти два поля при
//   загрузке не восстанавливались — сразу после переоткрытия их не было, и
//   состояние в памяти расходилось с диском до первого пересчёта. В браузере это
//   и ловил tests/browser-enrichment-parity-e2e.js («Persist/reopen differs from
//   memory»), который падал и на main начиная с PR #108.
//
// Тест держит инвариант, а не конкретную реализацию: записали каталог, закрыли и
// открыли базу, загрузили — снимок полей обязан совпасть с тем, что было в памяти.
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const fidb = require('fake-indexeddb');
const h = fs.readFileSync(__dirname + '/../index.html', 'utf8');

// --- минимальное окружение: DOM-заглушки, IndexedDB, встроенные библиотеки ---
const el = () => new Proxy({
  innerHTML: '', textContent: '', value: '', checked: false, disabled: false, style: {}, dataset: {}, options: [],
  selectedIndex: -1, scrollTop: 0, scrollHeight: 0, offsetHeight: 0, clientHeight: 0, children: [], childNodes: [],
  classList: { add() {}, remove() {}, toggle() {}, contains() { return false } },
  appendChild() {}, removeChild() {}, insertBefore() {}, setAttribute() {}, removeAttribute() {}, getAttribute() { return null },
  addEventListener() {}, removeEventListener() {}, querySelector() { return el() }, querySelectorAll() { return [] },
  closest() { return null }, focus() {}, blur() {}, click() {}, remove() {}, cloneNode() { return el() },
  getContext() { return null }, getBoundingClientRect() { return { top: 0, left: 0, width: 0, height: 0, bottom: 0, right: 0 } },
  getElementsByTagName() { return [] }, contains() { return false }
}, { get(t, k) { return k in t ? t[k] : undefined }, set(t, k, v) { t[k] = v; return true } });
const CACHE = new Map(); const stable = k => { if (!CACHE.has(k)) CACHE.set(k, el()); return CACHE.get(k) };
const doc = { getElementById: id => stable('#' + id), querySelector: s => stable(String(s)), querySelectorAll: () => [], createElement: () => el(), createTextNode: () => el(), createDocumentFragment: () => el(), addEventListener() {}, removeEventListener() {}, body: el(), head: el(), documentElement: el(), scripts: [] };

const c = { ...fidb, console, setTimeout, clearTimeout, setInterval, clearInterval, queueMicrotask, AbortController, structuredClone, TextDecoder, TextEncoder, Blob, File, performance, document: doc, navigator: {}, location: { protocol: 'http:', href: 'http://127.0.0.1/', hostname: '127.0.0.1', search: '', hash: '' }, fetch: async () => { throw new Error('нет сети') } };
c.window = c; c.self = c; c.globalThis = c;
c.addEventListener = () => {}; c.window.addEventListener = () => {};
c.localStorage = { _d: new Map(), getItem(k) { return this._d.get(k) ?? null }, setItem(k, v) { this._d.set(k, String(v)) }, removeItem(k) { this._d.delete(k) }, clear() { this._d.clear() } };
c.sessionStorage = c.localStorage;
c.requestAnimationFrame = fn => setTimeout(fn, 0); c.cancelAnimationFrame = clearTimeout;
c.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
c.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
c.MutationObserver = class { observe() {} disconnect() {} };
c.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
c.getComputedStyle = () => ({ getPropertyValue: () => '' });
c.alert = () => {}; c.confirm = () => false; c.prompt = () => null;
c.URL = Object.assign(function(u){return String(u)},{createObjectURL:()=>'blob:test',revokeObjectURL:()=>{},prototype:{}});
c.ProgressEvent = class { constructor(t) { this.type = t } };
c.CustomEvent = class { constructor(t) { this.type = t } };
vm.createContext(c);

const scripts = [...h.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m => m[1]);
for (const lib of scripts.filter(x => x.includes('встроен офлайн') && !x.includes('APP_VERSION'))) vm.runInContext(lib, c);
const app = scripts.filter(x => x.includes('APP_VERSION')).pop();
assert(app && app.length > 100000, 'скрипт приложения не найден');
// const-состояние живёт в лексическом скоупе скрипта: забираем его тем же прогоном.
const PROLOG = '\n;globalThis.__S=S;globalThis.__db=db;globalThis.__loadAll=loadAll;globalThis.__UI=UI;globalThis.__persistNow=persistNow;globalThis.__HVC=HVC;globalThis.__OE_DELIMITERS=OE_DELIMITERS;globalThis.__oeMode=oeMode;globalThis.__codeList=codeList;globalThis.__normArticle=normArticle;';
vm.runInContext(app + PROLOG, c, { filename: 'index.html' });

const S = c.__S, db = c.__db;
const FIELDS = ['article', 'brand', 'name', 'cost', 'oe_numbers', 'oe_list', 'oe_norm', 'applicability',
  'weight', 'length', 'width', 'height', 'category', 'tnved', 'barcode', 'originalArticle'];
// Снимок ровно того, что видит UI/экспорт: undefined и пустая строка различаются.
const snapshot = () => S.rows.map(p => Object.fromEntries(FIELDS.map(k => [k, p[k] === undefined ? '__нет__' : p[k]])))
  .sort((a, b) => String(a.article + '|' + a.brand).localeCompare(String(b.article + '|' + b.brand)));

(async () => {
  await db.delete().catch(() => {});
  await db.open();
  await c.__UI.boot();
  assert(S._bootReady === true, 'приложение не загрузилось: ' + JSON.stringify(S._bootError));

  // Каталог с OE в разных видах: несколько кодов, один код, пусто, только у части строк.
  S.rows = [
    { article: '0001', brand: 'B1', name: 'Name1', cost: 77, oe_numbers: 'A11 / A12', oe_list: 'A11 / A12', oe_norm: 'A11 / A12', applicability: 'Car1', weight: 0.5, length: 20, width: 10, height: 5, category: 'Запчасти', tnved: '8708999709', barcode: '00000000123' },
    { article: '0002', brand: 'B1', name: '', cost: 20, oe_numbers: 'OE2', oe_list: 'OE2', oe_norm: 'OE2' },
    { article: '0003', brand: 'B1', name: 'Без OE', cost: 30 },
    { article: '0004', brand: 'B1', name: 'Good', cost: 44, oe_numbers: 'OE4', oe_list: 'OE4', oe_norm: 'OE4' },
    { article: 'DONOR', brand: 'B1', name: 'Donor', oe_numbers: 'SHARED1', oe_list: 'SHARED1', oe_norm: 'SHARED1', weight: 0.8, length: 4, width: 5, height: 6 },
    { article: 'TARGET', brand: 'B1', name: 'Keep', oe_numbers: 'SHARED1', oe_list: 'SHARED1', oe_norm: 'SHARED1' }
  ];
  for (const p of S.rows) { p.article_norm = c.__normArticle(p.article); c.__HVC.ensureNorm(p); }
  const memory = snapshot();

  assert(await c.__persistNow(), 'запись каталога не удалась: ' + String(S._cacheWriteError || ''));

  db.close(); await db.open(); await c.__loadAll();

  const after = snapshot();
  const diffs = [];
  for (let i = 0; i < Math.max(memory.length, after.length); i++) {
    for (const k of FIELDS) {
      const a = memory[i] && memory[i][k], b = after[i] && after[i][k];
      if (JSON.stringify(a) !== JSON.stringify(b))
        diffs.push((memory[i] ? memory[i].article : '?') + ' / ' + k + ': в памяти ' + JSON.stringify(a) + ', после переоткрытия ' + JSON.stringify(b));
    }
  }
  if (memory.length !== after.length) diffs.push('строк: в памяти ' + memory.length + ', после переоткрытия ' + after.length);
  assert.equal(diffs.length, 0, 'переоткрытие изменило каталог:\n  ' + diffs.slice(0, 12).join('\n  '));

  // Отдельно: поля, которые намеренно не пишутся, обязаны восстанавливаться.
  const one = after.find(r => r.article === '0001');
  assert.equal(one.oe_list, 'A11 / A12', 'oe_list восстановлен из oe_numbers');
  assert.equal(one.oe_norm, 'A11 / A12', 'oe_norm восстановлен нормализацией');
  const noOe = after.find(r => r.article === '0003');
  assert.equal(noOe.oe_list, '__нет__', 'у строки без OE поле не появляется само');
  /* У этой строки пустое oe_norm — это состояние «в памяти» (так его видит
     приложение), важно лишь, что переоткрытие его не изменило: это уже
     проверено сверкой снимков выше. Здесь фиксируем, что пустой список OE не
     порождает непустых полей. */
  assert(noOe.oe_norm === '__нет__' || noOe.oe_norm === '', 'у строки без OE не появляется непустой oe_norm');

  console.log('OK: каталог после переоткрытия совпадает с памятью (' + after.length + ' строк × ' + FIELDS.length + ' полей);');
  console.log('    oe_list/oe_norm восстанавливаются из oe_numbers, у строк без OE полей не появляется');
  process.exit(0);
})().catch(e => { console.error(e && e.message || e); process.exit(1); });
