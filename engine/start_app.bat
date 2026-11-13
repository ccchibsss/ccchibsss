@echo off
chcp 6501 >nul 2>&1
rem ============================================================
rem  UNIT·CONTROL — запуск в одно окно.
rem  Сам находит движок: сначала готовый exe, потом Python.
rem  Токен вставлять не нужно: приложение получает его само.
rem ============================================================
cd /d %~dp0
echo Запуск UNIT CONTROL...
curl -s --max-time 2 http://127.0.0.1:8765/health >nul 2>nul
if %errorlevel%==0 goto open
echo Движок не запущен - запускаю...

if exist "UNIT CONTROL.exe" (
  start "" /min "UNIT CONTROL.exe" serve
  goto wait
)
if exist "UC-движок.exe" (
  start "" /min "UC-движок.exe" serve
  goto wait
)
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" /min pythonw uc_engine.py serve
  goto wait
)
where python >nul 2>nul
if %errorlevel%==0 (
  start "" /min python uc_engine.py serve
  goto wait
)

echo.
echo  Не найден ни UC-движок.exe, ни Python.
echo  Установите Python 3.10+ с python.org (галочка "Add to PATH")
echo  или попросите собранный UC-движок.exe и положите рядом с этим файлом.
echo.
start "" https://www.python.org/downloads/
pause
exit /b 1

:wait
for /l %%i in (1,1,20) do (
  curl -s --max-time 2 http://127.0.0.1:8765/health >nul 2>nul && goto open
  echo Жду движок... %%i
  timeout /t 1 /nobreak >nul
)
echo Движок не поднялся за 20 секунд. Запустите run_engine.bat и посмотрите ошибку.
pause
exit /b 1

:open
echo Движок работает - открываю браузер...
start "" http://127.0.0.1:8765/
