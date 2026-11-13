@echo off
chcp 6501 >nul 2>&1
title UC PyEngine
cd /d %~dp0
where python >nul 2>nul
if %errorlevel%==0 (
  python uc_engine.py serve
) else (
  echo Python не найден. Установите Python 3.10+ с python.org или используйте собранный UNIT CONTROL.exe
  pause
)
