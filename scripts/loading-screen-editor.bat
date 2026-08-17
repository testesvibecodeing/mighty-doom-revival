@echo off
setlocal
cd /d "%~dp0\.."
python scripts\loading_screen_editor.py %*
if errorlevel 1 pause
