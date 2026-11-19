// Ячейка Excel с числовым значением и «датным» форматом (вес 8.5, габарит 41014,
// характеристика 3.5) должна читаться как ЧИСЛО, а не как дата:
//   до исправления: 41014 → Date 15.04.2012 → вес/габариты терялись (0/undefined),
//                    характеристика становилась «Sun Apr 15 2012 00:00:00 GMT+0000…»;
//   после:          значения возвращаются из «сырого» чтения файла (NumericCellGuard).
// Проверяется полный путь: Import.read → Import.apply → реальная выгрузка XLSX
// (Exp.open → #expRun) и разбор полученного ZIP штатным SheetJS приложения.
const fs = require('fs'), http = require('http'), assert = require('assert');
const { chromium: pw } = require('playwright-core'), ch = require('@sparticuz/chromium');
const toBytes = b64 => Array.from(Buffer.from(b64, 'base64'));

(async () => {
  const html = fs.readFileSync(__dirname + '/../index.html');
  const server = http.createServer((q, r) => { r.setHeader('Content-Type', 'text/html; charset=utf-8'); r.end(html); });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  let browser;
  try {
    browser = await pw.launch({ executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || await ch.executablePath(), args: ch.args, headless: true });
    const page = await browser.newPage({ acceptDownloads: true });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/*', r => new URL(r.request().url()).hostname === '127.0.0.1' ? r.continue() : r.abort());
    await page.goto('http://127.0.0.1:' + server.address().port);
    await page.waitForFunction(() => S._bootReady || S._bootError);
    if (await page.evaluate(() => S._bootError)) throw Error(await page.evaluate(() => S._bootError));

    /* Книга собирается штатным SheetJS: ячейки с числом и форматом даты. */
    const b64 = await page.evaluate(() => {
      const aoa = [
        ['Артикул', 'Вес в упаковке, кг', 'Длина, см', 'Ширина, см', 'Высота, см', 'Высота профиля', 'Диаметр, мм'],
        ['A-DATE', { t: 'n', v: 41014, z: 'dd.mm.yyyy' }, { t: 'n', v: 8.5, z: 'dd.mm.yyyy' },
          { t: 'n', v: 1.25, z: 'dd.mm.yyyy' }, { t: 'n', v: 23.5, z: 'dd.mm.yyyy' },
          { t: 'n', v: 41014, z: 'dd.mm.yyyy' }, { t: 'n', v: 3.5, z: 'dd.mm.yyyy' }],
        ['A-PLAIN', 1.25, 10, 20, 30, 8.5, 7]
      ];
      const ws = XLSX.utils.aoa_to_sheet(aoa);
      const wb = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wb, ws, 'Прайс');
      const bytes = XLSX.write(wb, { type: 'array', bookType: 'xlsx' });
      return btoa(Array.from(new Uint8Array(bytes), b => String.fromCharCode(b)).join(''));
    });

    const expect = {
      'A-DATE': { weight: 41014, length: 8.5, width: 1.25, height: 23.5, custom: { 'Высота профиля': 41014, 'Диаметр, мм': 3.5 } },
      'A-PLAIN': { weight: 1.25, length: 10, width: 20, height: 30, custom: { 'Высота профиля': 8.5, 'Диаметр, мм': 7 } }
    };

    const rows = await page.evaluate(async b64 => {
      const u8 = new Uint8Array(atob(b64).split('').map(c => c.charCodeAt(0)));
      await Import.read(new File([u8], 'date-cells.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }));
      Import.normalize(); Import.render();
      document.querySelector('#impKey').value = 'article+brand';
      await Import.apply();
      return S.rows.map(p => ({ article: p.article, weight: p.weight, length: p.length, width: p.width, height: p.height, custom: p.custom || {} }));
    }, b64);

    assert.equal(rows.length, 2, 'обе строки импортированы');
    for (const p of rows) {
      const e = expect[p.article];
      assert(e, 'неожиданный артикул ' + p.article);
      for (const k of ['weight', 'length', 'width', 'height']) {
        assert.strictEqual(typeof p[k], 'number', `${p.article}.${k} должно быть числом, получено ` + String(p[k]));
        assert.ok(Math.abs(p[k] - e[k]) < 1e-9, `${p.article}.${k}: ожидалось ${e[k]}, получено ${p[k]}`);
      }
      for (const [key, value] of Object.entries(e.custom)) {
        const got = p.custom[key];
        assert(!(got instanceof Date), `${p.article}: характеристика «${key}» осталась датой`);
        assert(!/GMT|Apr|2012|1900/.test(String(got)), `${p.article}: характеристика «${key}» = ` + String(got));
        assert.ok(Math.abs(Number(got) - value) < 1e-9, `${p.article}: «${key}» ожидалось ${value}, получено ${got}`);
      }
    }

    /* Реальная выгрузка: числа должны остаться числами в каталоге и в «Вводах и ставках». */
    const download = page.waitForEvent('download', { timeout: 180000 });
    await page.evaluate(() => Exp.open());
    await page.waitForTimeout(400);
    await page.locator('#expRun').click();
    const file = await download.catch(async e => {
      console.log(await page.locator('#toasts').innerText().catch(() => ''));
      throw e;
    });
    assert.equal(await file.failure(), null);
    const bytes = fs.readFileSync(await file.path());
    assert.equal(bytes.readUInt16LE(0), 0x4b50, 'выгружен настоящий XLSX (ZIP)');

    const sheets = await page.evaluate(data => {
      const wb = XLSX.read(new Uint8Array(data), { type: 'array' });
      return wb.SheetNames.map(name => {
        const all = XLSX.utils.sheet_to_json(wb.Sheets[name], { header: 1, raw: true, defval: '' });
        return { name, rows: all };
      });
    }, Array.from(bytes));

    /* Ни в одной ячейке выгрузки не должно быть «дат» вместо чисел. */
    for (const sh of sheets) {
      for (const row of sh.rows) {
        for (const v of row) {
          assert(!(v instanceof Date), `лист «${sh.name}»: в выгрузке дата ` + String(v));
          assert(!/GMT\+|Coordinated Universal/.test(String(v)), `лист «${sh.name}»: текст даты в выгрузке — ` + String(v));
        }
      }
    }
    const values = sheets.map(s => s.rows).flat().flat();
    assert(!values.some(v => /Apr 15 2012|Sun Jan 07 1900/.test(String(v))), 'в выгрузке остались строки дат');

    /* Каталог: вес и характеристика A-DATE — числа. */
    const findCell = (sheet, header) => {
      const col = sheet.rows[0].indexOf(header);
      assert(col >= 0, `колонка «${header}» не найдена на листе «${sheet.name}»`);
      const row = sheet.rows.find(r => r[0] === 'A-DATE');
      assert(row, `строка A-DATE не найдена на листе «${sheet.name}»`);
      return row[col];
    };
    const hasAll = (sheet, headers) => sheet.rows[0] && headers.every(h => sheet.rows[0].includes(h)) && sheet.rows.some(r => r[0] === 'A-DATE');
    const catalog = sheets.find(s => hasAll(s, ['Артикул', 'Высота профиля', 'Диаметр, мм']));
    assert(catalog, 'лист каталога с характеристиками не найден');
    /* Пользовательская колонка по умолчанию текстовая, поэтому число может быть
       и числом, и его текстовым представлением — но НЕ датой и не «GMT»-строкой. */
    for (const [header, want] of [['Высота профиля', 41014], ['Диаметр, мм', 3.5]]) {
      const cell = findCell(catalog, header);
      assert(!(cell instanceof Date), `характеристика «${header}» осталась датой`);
      assert.strictEqual(Number(cell), want, `характеристика «${header}» в выгрузке: ` + String(cell));
    }

    /* «Вводы и ставки»: вес/габариты A-DATE — исходные числа, а не дата и не 0. */
    const DIMS = ['Вес, кг', 'Длина, см', 'Ширина, см', 'Высота, см'];
    const inputs = sheets.find(s => hasAll(s, DIMS));
    assert(inputs, 'лист «Вводы и ставки» с габаритами не найден');
    for (const [header, want] of [['Вес, кг', 41014], ['Длина, см', 8.5], ['Ширина, см', 1.25], ['Высота, см', 23.5]]) {
      assert.strictEqual(findCell(inputs, header), want, `${header} A-DATE в выгрузке`);
    }
    /* Контрольная строка с обычными числами не должна измениться. */
    const plainRow = inputs.rows.find(r => r[0] === 'A-PLAIN');
    assert(plainRow, 'строка A-PLAIN на листе «Вводы и ставки»');
    for (const [header, want] of [['Вес, кг', 1.25], ['Длина, см', 10], ['Ширина, см', 20], ['Высота, см', 30]]) {
      assert.strictEqual(plainRow[inputs.rows[0].indexOf(header)], want, `контрольный ${header} A-PLAIN`);
    }

    assert.equal(errors.length, 0, errors.join('\n'));
    console.log(JSON.stringify({ imported: rows.length, sheets: sheets.map(s => s.name), xlsxBytes: bytes.length, dateCellsAsNumbers: true, catalogCharacteristic: 41014, inputDims: [41014, 8.5, 1.25, 23.5] }));
  } finally {
    if (browser) await browser.close();
    await new Promise(r => server.close(r));
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
