@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0\.."

echo ============================================================
echo  Mighty DOOM Revival - APK patcher
echo  Uso pessoal / preservacao. O APK original nao e distribuido.
echo ============================================================
echo.

set "APK=input\mighty-doom.apk"
set /p "APK_INPUT=Caminho do APK [%APK%]: "
if not "%APK_INPUT%"=="" set "APK=%APK_INPUT%"

if not exist "%APK%" (
  echo [ERRO] APK nao encontrado: %APK%
  echo Para baixar/validar a copia alvo execute antes:
  echo   scripts\analyze-official-apk.bat
  exit /b 2
)

set "DEFAULT_HOST=d.debruinsistemas.com.br"
set "SERVER_HOST=%DEFAULT_HOST%"
set /p "SERVER_INPUT=Hostname HTTPS do servidor [%DEFAULT_HOST%]: "
if not "%SERVER_INPUT%"=="" set "SERVER_HOST=%SERVER_INPUT%"

set "CA_FILE="
set /p "CA_FILE=CA PEM/CRT local para HTTPS [ENTER = certificado publico]: "
if not "%CA_FILE%"=="" if not exist "%CA_FILE%" (
  echo [ERRO] CA nao encontrada: %CA_FILE%
  exit /b 2
)

echo.
echo Verificando dependencias minimas...
call :require python || exit /b 3
call :require java || exit /b 3

if not exist ".tools\apktool.jar" call "scripts\setup-patcher-tools.bat"
if errorlevel 1 exit /b %ERRORLEVEL%
if not exist ".tools\uber-apk-signer.jar" call "scripts\setup-patcher-tools.bat"
if errorlevel 1 exit /b %ERRORLEVEL%

set "APKTOOL=.tools\apktool.jar"
set "SIGNER=.tools\uber-apk-signer.jar"
set "WORK=work\apk-patch"
set "DECODED=%WORK%\decoded"
set "UNSIGNED=%WORK%\revival-unsigned.apk"
set "REPORT=%WORK%\patch-report.json"
set "OUT=output\mighty-doom-revival.apk"

if exist "%WORK%" rmdir /s /q "%WORK%"
mkdir "%WORK%" >nul 2>nul
if not exist "output" mkdir "output" >nul 2>nul

echo.
echo [1/6] Analisando APK...
python scripts\analyze_apk.py "%APK%"
if errorlevel 1 (
  echo [ERRO] O APK nao passou pela analise inicial.
  exit /b %ERRORLEVEL%
)

echo.
echo [2/6] Desmontando APK...
java -jar "%APKTOOL%" d -f "%APK%" -o "%DECODED%"
if errorlevel 1 (
  echo [ERRO] Apktool falhou ao desmontar o APK.
  exit /b 4
)

echo.
echo [3/6] Aplicando servidor e configuracao TLS...
if "%CA_FILE%"=="" (
  python scripts\patch_apk.py --decoded "%DECODED%" --server "%SERVER_HOST%" --report "%REPORT%"
) else (
  python scripts\patch_apk.py --decoded "%DECODED%" --server "%SERVER_HOST%" --ca "%CA_FILE%" --report "%REPORT%"
)
set "PATCH_RC=%ERRORLEVEL%"
if not "%PATCH_RC%"=="0" (
  echo.
  echo [PARADO] O patcher recusou uma alteracao que poderia corromper o bundle Unity.
  echo Relatorio: %REPORT%
  echo.
  echo Para o APK oficial 1.13.1, o host recomendado para o primeiro teste e:
  echo   d.debruinsistemas.com.br
  echo porque possui o mesmo tamanho do host oficial conhecido.
  exit /b %PATCH_RC%
)

echo.
echo [4/6] Reconstruindo APK...
java -jar "%APKTOOL%" b "%DECODED%" -o "%UNSIGNED%"
if errorlevel 1 (
  echo [ERRO] Apktool falhou ao reconstruir o APK.
  exit /b 5
)

echo.
echo [5/6] Alinhando, assinando e verificando...
java -jar "%SIGNER%" -a "%UNSIGNED%" --overwrite --verbose
if errorlevel 1 (
  echo [ERRO] Falha ao alinhar/assinar o APK.
  exit /b 6
)

java -jar "%SIGNER%" -a "%UNSIGNED%" --onlyVerify --verbose
if errorlevel 1 (
  echo [ERRO] A verificacao da assinatura falhou.
  exit /b 7
)

if exist "%OUT%" del /q "%OUT%"
copy /Y "%UNSIGNED%" "%OUT%" >nul
if errorlevel 1 (
  echo [ERRO] Nao foi possivel criar %OUT%.
  exit /b 8
)

echo.
echo [6/6] CONCLUIDO
echo APK gerado: %OUT%
echo Servidor: https://%SERVER_HOST%
echo Relatorio: %REPORT%
echo.
echo A assinatura e diferente da oficial. Se a versao oficial estiver instalada,
echo desinstale-a antes de instalar este APK de preservacao.
echo.
echo Com ADB instalado, opcionalmente use:
echo   adb uninstall com.bethsoft.ubu
echo   adb install "%OUT%"
echo.
exit /b 0

:require
where %1 >nul 2>nul
if errorlevel 1 (
  echo [FALTA] %1 nao esta no PATH.
  exit /b 1
)
echo [OK] %1
exit /b 0
