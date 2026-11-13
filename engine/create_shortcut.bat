@echo off
chcp 6501 >nul 2>&1
rem Один раз: создать ярлык UNIT·CONTROL на рабочем столе
cd /d %~dp0
powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell; $sc=$ws.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\UNIT CONTROL.lnk'); $sc.TargetPath='%~dp0start_app.bat'; $sc.WorkingDirectory='%~dp0'; $sc.Description='UNIT·CONTROL: приложение + локальный Python-движок в одном окне'; $sc.Save()"
echo Ярлык «UNIT CONTROL» создан на рабочем столе.
echo Дальше работайте только через него: двойной клик — одно окно.
pause
