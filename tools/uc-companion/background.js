// UNIT CONTROL companion: запросы к API площадок из контекста расширения.
// host_permissions снимают CORS: страница так не может, расширение — может.
// Ключи площадок хранятся только в chrome.storage.local расширения и
// никогда не попадают в страницу приложения.

async function ozonCreds() {
  const s = await chrome.storage.local.get(['ozonClientId', 'ozonApiKey']);
  if (!s.ozonClientId || !s.ozonApiKey) throw new Error('В настройках расширения не заданы Client-Id и Api-Key Ozon');
  return { 'Client-Id': s.ozonClientId, 'Api-Key': s.ozonApiKey, 'Content-Type': 'application/json' };
}

async function sendOzon(kind, items) {
  const headers = await ozonCreds();
  if (kind === 'prices') {
    const prices = items.map(it => ({
      offer_id: String(it.article),
      price: String(it.price),
      old_price: String(it.old_price != null ? it.old_price : it.price),
      min_price: String(it.min_price != null ? it.min_price : it.price)
    }));
    const r = await fetch('https://api-seller.ozon.ru/v1/product/import/prices', {
      method: 'POST', headers, body: JSON.stringify({ prices })
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error('Ozon prices HTTP ' + r.status + ': ' + JSON.stringify(j).slice(0, 200));
    return { sent: prices.length, result: j.result || j };
  }
  if (kind === 'stocks') {
    const stocks = items.filter(it => it.warehouse_id).map(it => ({
      offer_id: String(it.article), stock: parseInt(it.stock, 10) || 0, warehouse_id: Number(it.warehouse_id)
    }));
    if (!stocks.length) throw new Error('Для остатков нужен warehouse_id в каждой строке');
    const r = await fetch('https://api-seller.ozon.ru/v2/products/stocks', {
      method: 'POST', headers, body: JSON.stringify({ stocks })
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error('Ozon stocks HTTP ' + r.status + ': ' + JSON.stringify(j).slice(0, 200));
    return { sent: stocks.length, result: j.result || j };
  }
  throw new Error('Неизвестный kind: ' + kind);
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.type !== 'UC_SEND') return;
  (async () => {
    try {
      if (msg.marketplace !== 'OZON') throw new Error('Компаньон v1 умеет только OZON; WB/ЯМ — следующими версиями');
      sendResponse({ ok: true, ...(await sendOzon(msg.kind, msg.items || [])) });
    } catch (e) {
      sendResponse({ ok: false, error: String(e && e.message || e) });
    }
  })();
  return true; // async sendResponse
});
