@echo off
chcp 6501 >nul
rem Сборка одного exe без консоли: нужна один раз машина с Python и PyInstaller
cd /d %~dp0
pip install pyinstaller openpyxl
pyinstaller --onefile --windowed --name UC-движок uc_engine.py
echo Готово: dist\UC-движок.exe — запускается двойным кликом, установка Python не нужна.
pause
