@echo off
chcp 6501 >nul 2>&1
rem ============================================================
rem  Сборка ОДНОГО файла UNIT CONTROL.exe (нужна один раз машина
rem  с Python и интернетом для установки PyInstaller).
rem  Пользователю потом нужен только этот exe: двойной клик -
rem  движок стартовал, браузер открылся сам, токен не нужен.
rem  Данные (каталог, токен) exe хранит рядом с собой в engine_data.
rem ============================================================
cd /d %~dp0
python -m pip install --upgrade pyinstaller
if errorlevel 1 goto err
python -m PyInstaller --onefile --name "UNIT CONTROL" --add-data "..\index.html;." --add-data "ozon_template.json;." --add-data "std_dims.json;." uc_engine.py
if errorlevel 1 goto err
echo.
echo Готово: dist\UNIT CONTROL.exe
echo Отдайте пользователю ТОЛЬКО этот файл. Запуск - двойной клик.
pause
exit /b 0
:err
echo.
echo Сборка не удалась - текст ошибки выше. Чаще всего: нет интернета для pip
echo или PyInstaller заблокирован антивирусом.
pause
exit /b 1
