@echo off
chcp 6501 >nul
rem ОДНО ОКНО: движок запускается скрытно, приложение открывается в браузере
rem с его же адреса (http://127.0.0.1:8765/). Отдельное окно консоли не нужно.
cd /d %~dp0
curl -s http://127.0.0.1:8765/health >nul 2>nul
if %errorlevel%==0 goto open
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" /min pythonw uc_engine.py serve
) else (
  start "" /min python uc_engine.py serve
)
for /l %%i in (1,1,20) do (
  curl -s http://127.0.0.1:8765/health >nul 2>nul && goto open
  timeout /t 1 /nobreak >nul
)
:open
start "" http://127.0.0.1:8765/
