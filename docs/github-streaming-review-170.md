# GitHub: проверенные подходы и внедрение в Python Ozon export

> Измерения ниже относятся к первому этапу 170. Затем CSV дополнительно ускорен в 171: [профилирование, точные сравнения и регрессия](csv-speed-171.md). Старые цифры сохранены как история, не как текущая скорость CSV.

## Область поиска

Просмотрены шесть целевых репозиториев, а не «весь GitHub». Поиск выполнялся через GitHub CLI/API по XLSX streaming и смежным задачам; прочитаны README, ограничения/лицензионные метаданные и соответствующие участки writer-кода. Эти проекты не объявляются прошедшими полный security audit. Новые зависимости не добавлены, сторонний исходный код не скопирован: внедрён общий алгоритмический подход в существующий stdlib engine.

## Источники и решение

| Репозиторий / проверенный commit | Что найдено | Решение |
|---|---|---|
| [XlsxWriter](https://github.com/jmcnamara/XlsxWriter/tree/af5927c110cf01571046a3138600f63b256ea89a), BSD-2-Clause | [working_with_memory.rst](https://github.com/jmcnamara/XlsxWriter/blob/af5927c110cf01571046a3138600f63b256ea89a/dev/docs/source/working_with_memory.rst): constant_memory сбрасывает предыдущую строку; требуется порядок row-major; inline strings вместо глобального sharedStrings. В [worksheet.py](https://github.com/jmcnamara/XlsxWriter/blob/af5927c110cf01571046a3138600f63b256ea89a/xlsxwriter/worksheet.py) просмотрен `_write_single_row`. | Применён принцип последовательной записи строки и освобождения её памяти. Библиотека не установлена: сохраняем stdlib-only Python и собственный exact serializer. |
| [ExcelJS](https://github.com/exceljs/exceljs/tree/5bed18b45e824f409b08456b59b87430ded023ab), MIT | [README Streaming XLSX Writer](https://github.com/exceljs/exceljs/blob/5bed18b45e824f409b08456b59b87430ded023ab/README.md#streaming-xlsx-writer) предупреждает: без stream/filename результат хранится в StreamBuf; `row.commit` освобождает строки. В [worksheet-writer.js](https://github.com/exceljs/exceljs/blob/5bed18b45e824f409b08456b59b87430ded023ab/lib/stream/xlsx/worksheet-writer.js) просмотрен `_commitRow`. Browser build не включает streaming reader/writer. | Подтверждён файловый sink на **всём** пути, а не только название «stream». ExcelJS не добавлен в браузер или Python. |
| [xlsx-stream-reader](https://github.com/DaSpawn/xlsx-stream-reader/tree/3dfcc6647e8b817e40cccd84e095c24979510978), MIT | [README](https://github.com/DaSpawn/xlsx-stream-reader/blob/3dfcc6647e8b817e40cccd84e095c24979510978/README.md): событийные строки; shared strings кешируются; `saxTrim` по умолчанию true; форматирование настраивается. | Не заменяет SheetJS без проверки точного typing/date/sharedStrings/whitespace поведения; не внедрён. Нельзя обещать постоянную память лишь из названия streaming. |
| [stream-json](https://github.com/uhop/stream-json/tree/f608dff6533b76a2f8c5a6e2c94422144cadfb0b), BSD-3-Clause | [README](https://github.com/uhop/stream-json/blob/f608dff6533b76a2f8c5a6e2c94422144cadfb0b/README.md): токенизация/выбор поддеревьев вместо JSON.parse целого документа; оговорка trusted inputs. | Перспективно для нового порционного протокола, но замена parser не уберёт создание `export_cells` во вкладке. Сессионные revision/atomicity guards нужно проектировать отдельно. Не внедрён. |
| [fflate](https://github.com/101arrowz/fflate/tree/dcb3714a6c25db3a2748641019c5277413d09714), MIT | [README](https://github.com/101arrowz/fflate/blob/dcb3714a6c25db3a2748641019c5277413d09714/README.md): streaming ZIP/Unzip, можно запускать распаковку только нужных entries. | Уже используется в приложении. Потоковый unzip сам по себе не решает sharedStrings и exact XLSX typing. В этой работе версия/reader не менялись. |
| [Dexie.js](https://github.com/dexie/Dexie.js/tree/95666bf5370a222a21d7f53130d87b42e9b7bac7), Apache-2.0 | [README](https://github.com/dexie/Dexie.js/blob/95666bf5370a222a21d7f53130d87b42e9b7bac7/README.md): IndexedDB wrapper и bulk/transaction модель. | Dexie уже используется; готового проверенного drop-in алгоритма, устраняющего нашу random-page cache thrashing с exact conflict policy, в просмотренных материалах не найдено. Перестройка этих индексов не выдается за выполненную. |

## Внедрение — engine 12.9.170-pyengine-41

В `engine/uc_engine.py`:

1. `_xlsx_from_rows_file` пишет малые служебные ZIP entries, затем XML первого листа непосредственно в `ZipFile.open(..., 'w')`. XML строк, типы ячеек, формулы, кешированные значения и жёлтые стили остаются прежними. Буфер — примерно 64 KiB плюс одна текущая строка; нет списка всех rows_xml и полного XML-листа.
2. `_iter_ozon_rows_meta` читает товары курсором SQLite. Видимость, excluded, ключи отбора, порядок, нумерация, `ozon_row_meta`, скидка/НДС/ЧЗ не заменены новыми эвристиками.
3. `export_ozon_xlsx_file` потребляет курсор последовательно. Yellow marks удерживаются только для текущей строки, а не для всего файла.
4. `export_ozon_csv_file` пишет непосредственно во временный файл; BOM, quoting, CSV injection policy и строгий CP1251 сохранены. Ошибка кодировки не публикует частичный файл.
5. Все четыре GET/POST маршрута `/export/ozon.csv` и `/export/ozon.xlsx` используют файловый `_send_file`; временный файл закрывается после ответа/отключения клиента. Книга полностью сформирована перед HTTP headers, поэтому поздняя ошибка генерации не публикует неполный XLSX.
6. Byte-returning APIs и `_ozon_rows_data` сохранены для совместимости. Они по определению могут материализовать результат; Ozon HTTP больше через них не проходит.

Функции не удалены; основной Python остаётся одним runtime-файлом. Браузерный HTML не менялся. Дополнительная запись на диск и отсутствие whole-body gzip для CSV файлового ответа — сознательные компромиссы. XLSX получает ZIP64-capable local entry, поэтому ZIP-байты немного отличаются, но распакованные XML — нет.

## Проверка результата

### Точность

- Golden SHA-256 всех распакованных entries для исходного single-sheet serializer из baseline `5e5a6660841e72761dbca8fede6d84c0c49c8224` — совпали. Fixture включает числовые/текстовые значения, boolean прежнего serializer, пустые поля, спецсимволы, Unicode, формулы и стили.
- Ozon: видимость/excluded, пустой/частичный scope, нумерация, currency/CP1251, жёлтые стили и шаблон проверены.
- На большом случайном наборе — CSV SHA-256 совпадает побайтно; XLSX SHA-256 по именам и содержимому **всех распакованных entries** совпадает до/после.
- Late generator failure и CP1251 failure закрывают временные файлы; legacy materialization helpers намеренно запрещены mock-ом при вызове production file API.
- Реальные четыре HTTP GET/POST запроса проходят даже при запрещённых `export_ozon_*_bytes`. Content-Length и структура ответа проверены.

### Память и время

Ручной `engine/tests/benchmark_streaming_export.py`, 20000 товаров, 32 случайных 64-битных слова в описании каждого товара, отдельный процесс на sample, два повтора с чередованием порядка. SQLite fixture создавался до дочерних процессов. Для одинаковой подготовки baseline-функции компилируются из AST в обеих версиях. Время — только генерация; обратный hash/readback исключён. Память — Linux process `ru_maxrss`, включая startup/setup (то есть не только функцию); файл и SQLite fixture на диске.

| Python Ozon export | Время до → после, медиана | Пик RSS до → после | Изменение пика |
|---|---:|---:|---:|
| XLSX | 2.838 → 2.807 с | 307.4 → 57.2 MiB | **−81%** |
| CSV | 3.189 → 3.419 с | 157.1 → 57.2 MiB | **−64%** |

Не заявляется ускорение XLSX на 1%: это практически одинаковое время при двух прогонах. CSV в этом тесте **примерно на 7% медленнее**, а не быстрее. Главный выигрыш — устранение полного списка/полного XML/готового bytes HTTP-ответа в памяти.

`ru_maxrss` — high-water mark **всей жизни** процесса, а не точное увеличение от начала операции. В «после» peak может быть задан подготовкой/AST, а не самим writer; поэтому 57.2 MiB не является универсальным пределом его памяти. Pairs/reference map, OS allocator, SQLite cache, множество запрошенных keys и очень широкая отдельная строка всё ещё занимают память. Нет замера полного UI→HTTP→download пути на файле пользователя.

Сырые результаты восьми процессов: `docs/benchmarks/python-ozon-stream-170.json`.

### Регрессия

- Python discovery: **271 tests PASS**.
- Основной Node suite и **31 client suite PASS**.
- Новые тесты автоматически входят в существующий Python discovery CI.
- `git diff --check` PASS.

## Что не объявляется исправленным

- Browser XLSX reader/SheetJS worksheet, resident `S.rows` и HVC.
- Generic formatted multi-sheet Python XLSX: `_xlsx_workbook` всё ещё распаковывает XML/строит ElementTree и собирает финальные bytes. Он получает улучшенный row serializer, но не стал полностью потоковым.
- SQL presentation JSON request, сценарии и атомарные staged results.
- Большие случайные lookup сверх bounded IndexedDB cache.
- Полная нейтрализация OOM или ускорение всех видов импорта.

Следующий безопасный шаг — отдельные revision-pinned сессии и SAX/sharedStrings parity fixtures; не безусловная установка ещё одной библиотеки.
