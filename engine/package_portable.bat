@echo off
chcp 6501 >nul
rem ============================================================
rem  Сборка ПОРТАТИВНОЙ папки UNIT·CONTROL (один раз, на машине
rem  сборщика). Итог: папка UC-portable, которую пользователь
rem  просто распаковывает и запускает — Python УСТАНАВЛИВАТЬ
rem  НЕ НУЖНО: интерпретатор лежит внутри папки (embeddable).
rem ============================================================
cd /d %~dp0
set PYVER=3.12.7
set OUT=%~dp0..\UC-portable
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%\engine" "%OUT%\python"
echo Скачиваю портативный Python %PYVER% ...
curl -L -o "%TEMP%\pyembed.zip" "https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-embed-amd64.zip"
if %errorlevel% neq 0 ( echo Не удалось скачать Python. Проверьте интернет. & pause & exit /b 1 )
powershell -NoProfile -Command "Expand-Archive -Force '%TEMP%\pyembed.zip' '%OUT%\python'"
rem Разрешить импорт модулей из папки движка в embeddable-сборке
powershell -NoProfile -Command "(Get-Content '%OUT%\python\python312._pth') -replace '#import site','import site' | Set-Content '%OUT%\python\python312._pth'"
copy /y "%~dp0uc_engine.py" "%OUT%\engine\" >nul
copy /y "%~dp0..\index.html" "%OUT%\" >nul
(
echo @echo off
echo chcp 6501 ^>nul
echo cd /d %%~dp0
echo curl -s http://127.0.0.1:8765/health ^>nul 2^>nul
echo if %%errorlevel%%==0 goto open
echo start "" /min "%%~dp0python\pythonw.exe" "%%~dp0engine\uc_engine.py" serve
echo :wait
echo for /l %%%%i in ^(1,1,20^) do ^( curl -s http://127.0.0.1:8765/health ^>nul 2^>nul ^&^& goto open ^& timeout /t 1 /nobreak ^>nul ^)
echo :open
echo start "" http://127.0.0.1:8765/
) > "%OUT%\UNIT CONTROL.bat"
echo.
echo Готово: %OUT%
echo Пользователю: распаковать папку и запускать "UNIT CONTROL.bat".
echo Python устанавливать НЕ требуется.
pause
