// e2e на реальном Chromium: незавершённый импорт => диалог «Прерванный импорт».
// Проверяется: «Закрыть» закрывает диалог и возвращает false; «Восстановить»
// выполняет откат и запуск завершается. Контрольная точка создаётся настоящим
// BrowserApplyCheckpoint.begin(), а не вручную записанным маркером.
const fs = require('fs'), http = require('http');
const { chromium: pw } = require('playwright-core');
const chromium = require('@sparticuz/chromium');

const EXPECT = process.env.E2E_EXPECT || 'fixed';

(async () => {
  const html = fs.readFileSync(__dirname + '/../index.html');
  const server = http.createServer((q, r) => {
    r.setHeader('Content-Type', 'text/html;charset=utf-8'); r.end(html);
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const port = server.address().port;
  const base = 'http://127.0.0.1:' + port + '/';
  let browser;
  const out = {};
  const fails = [];
  try {
    browser = await pw.launch({
      executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || await chromium.executablePath(),
      args: chromium.args, headless: true,
    });
    const page = await browser.newPage();
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.route('**/*', r => new URL(r.request().url()).hostname === '127.0.0.1' ? r.continue() : r.abort());
    const ready = () => page.waitForFunction(() => S._bootReady || S._bootError, null, { timeout: 90000 });
    const dialogShown = () => page.waitForFunction(() => {
      const m = document.getElementById('mGen'); return m && m.classList.contains('on');
    }, null, { timeout: 60000 });
    const isOpen = () => page.evaluate(() => document.getElementById('mGen').classList.contains('on'));

    // 1) Обычный запуск, затем настоящая контрольная точка кодом приложения.
    await page.goto(base); await ready();
    const cp = await page.evaluate(async () => {
      try {
        const owner = await BrowserApplyCheckpoint.begin();
        const m = await db.meta.get(BrowserApplyCheckpoint.KEY);
        return { owner, preparing: !!m.value.preparing, storage: m.value.storage || null };
      } catch (e) { return { error: String(e && e.message || e) }; }
    });
    out.checkpoint = cp;
    if (cp.error) { console.log(JSON.stringify(out, null, 2)); throw new Error('не удалось создать контрольную точку: ' + cp.error); }
    if (cp.preparing) { console.log(JSON.stringify(out, null, 2)); throw new Error('контрольная точка осталась в preparing'); }

    // 2) Перезапуск -> recover() показывает диалог до UI.bind().
    await page.reload(); await dialogShown();
    out.dialogTitle = await page.evaluate(() => document.getElementById('mgTitle').textContent.trim());
    out.closeBtnText = (await page.locator('#mGen .mfoot button[data-close]').textContent()).trim();
    out.onclickBound = await page.locator('#mGen .mfoot button[data-close]').evaluate(b => typeof b.onclick === 'function');

    // 3) Клик по «Закрыть».
    await page.locator('#mGen .mfoot button[data-close]').click();
    await page.waitForTimeout(600);
    out.openAfterClose = await isOpen();
    await page.waitForTimeout(1200);
    out.afterClose = await page.evaluate(() => ({
      bootReady: !!S._bootReady,
      bootError: S._bootError ? String(S._bootError.message || S._bootError) : null,
      checkpointKept: null,
      toasts: [...document.querySelectorAll('[class*=toast]')].map(t => t.textContent.trim()).filter(Boolean).slice(0, 3),
    }));
    out.afterClose.checkpointKept = await page.evaluate(async () => !!(await db.meta.get(BrowserApplyCheckpoint.KEY)));

    // 4) Регресс: обычный диалог после запуска закрывается тем же путём и даёт false.
    // Если диалог остался висеть (дефект), дальнейшие шаги бессмысленны: сразу
    // фиксируем провал, не доводя до таймаута.
    if (await isOpen()) throw new Error('дефект: диалог «Прерванный импорт» не закрылся кликом по «Закрыть»');
    await page.evaluate(() => { window.__ask = askConfirm('Проверка', 'тест', 'ОК'); });
    await page.waitForTimeout(200);
    out.plainOpen = await isOpen();
    await page.locator('#mGen .mfoot button[data-close]').click();
    await page.waitForTimeout(300);
    out.plainClosed = !(await isOpen());
    out.plainResult = await page.evaluate(() => window.__ask);

    // 5) Вторая вкладка-состояние: «Восстановить» откатывает и завершает запуск.
    await page.reload(); await dialogShown();
    await page.locator('#mgApply').click();
    await page.waitForFunction(() => S._bootReady || S._bootError, null, { timeout: 90000 });
    await page.waitForTimeout(800);
    out.afterRestore = await page.evaluate(() => ({
      bootReady: !!S._bootReady,
      bootError: S._bootError ? String(S._bootError.message || S._bootError) : null,
      dialogOpen: document.getElementById('mGen').classList.contains('on'),
      checkpointLeft: null,
    }));
    out.afterRestore.checkpointLeft = await page.evaluate(async () => !!(await db.meta.get(BrowserApplyCheckpoint.KEY)));

    out.pageErrors = errors;
    console.log(JSON.stringify(out, null, 2));

    if (out.dialogTitle !== 'Прерванный импорт') fails.push('неверный заголовок диалога: ' + out.dialogTitle);
    if (out.closeBtnText !== 'Закрыть') fails.push('кнопка «Закрыть» не найдена');
    if (EXPECT === 'fixed') {
      if (!out.onclickBound) fails.push('ДЕФЕКТ: у «Закрыть» нет обработчика — диалог не закроется');
      if (out.openAfterClose) fails.push('ДЕФЕКТ: «Закрыть» не закрывает диалог');
      if (!out.afterClose.checkpointKept) fails.push('отмена не должна удалять контрольную точку');
      if (out.afterClose.bootReady) fails.push('после отмены запуск не должен продолжаться молча без восстановления');
      if (!/восстановление незавершённого импорта/.test(String(out.afterClose.bootError)))
        fails.push('после отмены ожидалось сообщение о необходимости восстановления, получено: ' + out.afterClose.bootError);
      if (!out.plainOpen || !out.plainClosed) fails.push('РЕГРЕСС: обычный диалог не закрывается кнопкой «Закрыть»');
      if (out.plainResult !== false) fails.push('закрытие обычного диалога вернуло не false: ' + out.plainResult);
      if (!out.afterRestore.bootReady) fails.push('«Восстановить» не завершило запуск: ' + out.afterRestore.bootError);
      if (out.afterRestore.dialogOpen) fails.push('диалог остался открыт после восстановления');
      if (out.afterRestore.checkpointLeft) fails.push('после восстановления контрольная точка не удалена');
    } else if (!out.openAfterClose) {
      fails.push('ожидался воспроизведённый дефект, но диалог закрылся');
    }
    if (fails.length) { console.log('FAIL: ' + fails.join('; ')); process.exitCode = 1; }
    else console.log('PASS (' + EXPECT + ')');
  } catch (e) {
    console.log('ERROR: ' + (e && e.stack || e));
    process.exitCode = 1;
  } finally {
    try { if (browser) await browser.close(); } catch (e) { }
    server.close();
  }
})();
