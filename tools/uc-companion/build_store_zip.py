# Сборка zip-пакета для Chrome Web Store: только runtime-файлы расширения.
# Запуск: python build_store_zip.py -> ../uc-companion-store.zip
import zipfile, pathlib
root = pathlib.Path(__file__).parent
include_files = ['manifest.json', 'background.js', 'content.js', 'options.html', 'options.js']
include_dirs = ['icons']
out = root.parent / 'uc-companion-store.zip'
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in include_files: z.write(root / f, f)
    for d in include_dirs:
        for f in sorted((root / d).glob('*')): z.write(f, f'{d}/{f.name}')
print('OK:', out)
