chrome.storage.local.get(['ozonClientId', 'ozonApiKey'], (s) => {
  document.getElementById('ozonClientId').value = s.ozonClientId || '';
  document.getElementById('ozonApiKey').value = s.ozonApiKey || '';
});
document.getElementById('save').onclick = () => {
  chrome.storage.local.set({
    ozonClientId: document.getElementById('ozonClientId').value.trim(),
    ozonApiKey: document.getElementById('ozonApiKey').value.trim()
  }, () => { document.getElementById('st').textContent = 'Сохранено'; });
};
