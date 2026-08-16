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

echo Verificando suporte bundle-aware...
python -c "import UnityPy,sys; sys.exit(0 if getattr(UnityPy,'__version__','') == '1.25.3' else 1)" >nul 2>nul
if errorlevel 1 (
  echo Instalando UnityPy 1.25.3 para reserializacao segura de bundles Unity...
  python -m pip install --disable-pip-version-check "UnityPy==1.25.3"
  if errorlevel 1 (
    echo [ERRO] Nao foi possivel instalar UnityPy 1.25.3.
    echo Execute manualmente: python -m pip install UnityPy==1.25.3
    exit /b 3
  )
)

set "APKTOOL=.tools\apktool.jar"
set "SIGNER=.tools\uber-apk-signer.jar"
set "WORK=work\apk-patch"
set "DECODED=%WORK%\decoded"
set "UNSIGNED=%WORK%\revival-unsigned.apk"
set "REPORT=%WORK%\patch-report.json"
set "VERIFY_REPORT=%WORK%\final-apk-verification.json"
set "OUT=output\mighty-doom-revival.apk"

if exist "%WORK%" rmdir /s /q "%WORK%"
mkdir "%WORK%" >nul 2>nul
if not exist "output" mkdir "output" >nul 2>nul

echo.
echo [1/7] Analisando APK...
python scripts\analyze_apk.py "%APK%"
if errorlevel 1 (
  echo [ERRO] O APK nao passou pela analise inicial.
  exit /b %ERRORLEVEL%
)

echo.
echo [2/7] Desmontando APK...
java -jar "%APKTOOL%" d -f "%APK%" -o "%DECODED%"
if errorlevel 1 (
  echo [ERRO] Apktool falhou ao desmontar o APK.
  exit /b 4
)

echo.
echo [3/7] Aplicando servidor e configuracao TLS...
if "%CA_FILE%"=="" (
  python scripts\patch_apk.py --decoded "%DECODED%" --server "%SERVER_HOST%" --report "%REPORT%"
) else (
  python scripts\patch_apk.py --decoded "%DECODED%" --server "%SERVER_HOST%" --ca "%CA_FILE%" --report "%REPORT%"
)
set "PATCH_RC=%ERRORLEVEL%"

if "%PATCH_RC%"=="4" (
  echo.
  echo Hostname com tamanho diferente detectado. Tentando patch bundle-aware...
  python scripts\patch_bundle_from_report.py --decoded "%DECODED%" --server "%SERVER_HOST%" --report "%REPORT%"
  set "PATCH_RC=!ERRORLEVEL!"
)

if not "%PATCH_RC%"=="0" (
  echo.
  echo [PARADO] O patcher nao conseguiu provar uma alteracao segura do bundle Unity.
  echo Nenhum patch binario de tamanho variavel foi feito no escuro.
  echo Relatorio: %REPORT%
  exit /b %PATCH_RC%
)

echo.
echo [4/7] Reconstruindo APK...
java -jar "%APKTOOL%" b "%DECODED%" -o "%UNSIGNED%"
if errorlevel 1 (
  echo [ERRO] Apktool falhou ao reconstruir o APK.
  exit /b 5
)

echo.
echo [5/7] Validando endpoint dentro do APK reconstruido...
python scripts\verify_patched_apk.py --apk "%UNSIGNED%" --server "%SERVER_HOST%" --report "%VERIFY_REPORT%"
if errorlevel 1 (
  echo [ERRO] APK reconstruido nao passou pelo gate do endpoint Revival.
  echo Relatorio: %VERIFY_REPORT%
  exit /b 6
)

echo.
echo [6/7] Alinhando, assinando e verificando assinatura...
java -jar "%SIGNER%" -a "%UNSIGNED%" --overwrite --verbose
if errorlevel 1 (
  echo [ERRO] Falha ao alinhar/assinar o APK.
  exit /b 7
)

java -jar "%SIGNER%" -a "%UNSIGNED%" --onlyVerify --verbose
if errorlevel 1 (
  echo [ERRO] A verificacao da assinatura falhou.
  exit /b 8
)

rem A assinatura nao deve alterar os payloads de assets. Verifique novamente o
rem endpoint depois do signer para impedir entrega de um artefato inesperado.
python scripts\verify_patched_apk.py --apk "%UNSIGNED%" --server "%SERVER_HOST%" --report "%VERIFY_REPORT%"
if errorlevel 1 (
  echo [ERRO] APK assinado falhou na verificacao final do endpoint.
  exit /b 9
)

if exist "%OUT%" del /q "%OUT%"
copy /Y "%UNSIGNED%" "%OUT%" >nul
if errorlevel 1 (
  echo [ERRO] Nao foi possivel criar %OUT%.
  exit /b 10
)

echo.
echo [7/7] CONCLUIDO
echo APK gerado e verificado: %OUT%
echo Servidor: https://%SERVER_HOST%
echo Relatorio do patch: %REPORT%
echo Relatorio final: %VERIFY_REPORT%
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
