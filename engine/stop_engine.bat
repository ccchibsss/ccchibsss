@echo off
chcp 6501 >nul
rem Остановить локальный движок UNIT·CONTROL (процесс на порту 8765)
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
echo Движок остановлен. Приложение продолжит работу на встроенном расчёте.
timeout /t 2 /nobreak >nul
