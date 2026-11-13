// Мост страница <-> расширение. Страница шлёт window.postMessage,
// content script пересылает в background и возвращает ответ тем же путём.
// Ключи площадок странице не доступны: background берёт их из своего хранилища.
window.addEventListener('message', (ev) => {
  if (ev.source !== window || !ev.data || typeof ev.data !== 'object') return;
  if (ev.data.type === 'UC_COMPANION_PING') {
    window.postMessage({ type: 'UC_COMPANION_PONG', version: '1.0.0' }, '*');
    return;
  }
  if (ev.data.type === 'UC_SEND' && ev.data.reqId) {
    chrome.runtime.sendMessage(
      { type: 'UC_SEND', marketplace: ev.data.marketplace, kind: ev.data.kind, items: ev.data.items },
      (resp) => {
        const err = chrome.runtime.lastError;
        window.postMessage({
          type: 'UC_SEND_RESULT', reqId: ev.data.reqId,
          ok: !err && !!(resp && resp.ok),
          error: err ? String(err.message) : (resp && resp.error) || '',
          sent: resp && resp.sent, result: resp && resp.result
        }, '*');
      }
    );
  }
});
