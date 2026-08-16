@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

echo ============================================================
echo  Mighty DOOM Revival - baixar e analisar APK oficial alvo
 echo  O APK fica somente no seu PC e nao entra no Git.
echo ============================================================
echo.

where python >nul 2>nul || (echo [ERRO] Python nao encontrado no PATH.& exit /b 2)

if not exist "input" mkdir "input"
if not exist "reports" mkdir "reports"

echo [1/2] Baixando Mighty DOOM 1.13.1 e validando SHA-256...
python scripts\fetch-uptodown-apk.py --output input\mighty-doom.apk
if errorlevel 1 exit /b %errorlevel%

echo.
echo [2/2] Gerando relatorios sanitizados...
python scripts\analyze_apk.py input\mighty-doom.apk --json-out reports\apk-1.13.1.json --md-out reports\apk-1.13.1.md
if errorlevel 1 exit /b %errorlevel%

echo.
echo CONCLUIDO.
echo APK local: input\mighty-doom.apk
echo Relatorio JSON: reports\apk-1.13.1.json
echo Relatorio Markdown: reports\apk-1.13.1.md
echo.
echo O diretorio reports e o APK estao ignorados pelo Git.
exit /b 0
