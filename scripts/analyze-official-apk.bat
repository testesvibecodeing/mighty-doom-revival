@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."
where python >nul 2>nul || (echo [ERROR] Python not found.& exit /b 2)
rem studio-forward: sem argumentos abre o Revival Studio (acao projeto.analisar).
rem Com qualquer argumento segue o caminho headless de sempre (plano, par. 9.2).
if "%~1"=="" (
    python "%~dp0revival_studio.py" %*
    exit /b %errorlevel%
)
set "APK_PATH=%~1"
if "%APK_PATH%"=="" set "APK_PATH=input\mighty-doom.apk"
if not exist "%APK_PATH%" (
  echo [ERROR] Local APK not found: %APK_PATH%
  echo Usage: scripts\analyze-official-apk.bat path\to\your-copy.apk
  exit /b 1
)
if not exist reports mkdir reports
python scripts\analyze_apk.py "%APK_PATH%" --json-out reports\apk-1.13.1.json --md-out reports\apk-1.13.1.md
echo Sanitized reports written to reports\. The APK was not downloaded or published.
