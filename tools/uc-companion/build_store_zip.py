# Сборка пакетов расширения для магазинов (все — бесплатная публикация):
#   python build_store_zip.py          -> Chromium-совместимый zip (Opera Add-ons, Edge Add-ons, Chrome Web Store)
#   python build_store_zip.py firefox  -> вариант для Firefox (AMO): background scripts вместо service worker
import zipfile, pathlib, json, sys, copy
root = pathlib.Path(__file__).parent
include_files = ['manifest.json', 'background.js', 'content.js', 'options.html', 'options.js']
mode = sys.argv[1] if len(sys.argv) > 1 else 'chromium'
out = root.parent / ('uc-companion-store.zip' if mode == 'chromium' else 'uc-companion-firefox.zip')
manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
if mode == 'firefox':
    manifest = copy.deepcopy(manifest)
    manifest['background'] = {'scripts': ['background.js']}
    manifest['browser_specific_settings'] = {'gecko': {'id': 'unitcontrol-companion@example.com', 'strict_min_version': '109.0'}}
    manifest.pop('minimum_chrome_version', None)
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in include_files:
        if f == 'manifest.json':
            z.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        else:
            z.write(root / f, f)
    for f in sorted((root / 'icons').glob('*')): z.write(f, f'icons/{f.name}')
print('OK:', out)
