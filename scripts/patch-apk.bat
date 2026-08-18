@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0\.."

rem studio-forward: sem argumentos, abre o Revival Studio, que roda este mesmo
rem pipeline como servico (mesmos CLIs, com relatorio estruturado e cancelamento).
rem O caminho headless de prompts abaixo permanece intacto para CI/VPS.
if "%~1"=="" (
  where python >nul 2>nul
  if not errorlevel 1 (
    python "%~dp0revival_studio.py"
    exit /b !errorlevel!
  )
)

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
  pause
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
  pause
  exit /b 2
)

echo.
echo Verificando dependencias minimas...
call :require python || (pause & exit /b 3)

echo.
echo Verificando capacidade do patch direto (sem apktool)...
python scripts\check_patch_length.py "%APK%" "%SERVER_HOST%"
set "LENGTH_RC=!ERRORLEVEL!"
if "!LENGTH_RC!"=="2" (
  echo [ERRO] Hostname/APK invalido para o precheck.
  pause
  exit /b 2
)
if not "!LENGTH_RC!"=="0" if not "!LENGTH_RC!"=="4" (
  echo [ERRO] Precheck falhou com codigo !LENGTH_RC!.
  pause
  exit /b !LENGTH_RC!
)
if "!LENGTH_RC!"=="4" (
  echo.
  echo [INFO] O hostname nao cabe no fast path. Continuando para o patch bundle-aware.
  echo [INFO] Se a referencia exigir realocacao de metadata IL2CPP, a etapa posterior bloqueara com seguranca.
)

call :require java || (pause & exit /b 3)

if not exist ".tools\apktool.jar" call "scripts\setup-patcher-tools.bat"
if errorlevel 1 (
  pause
  exit /b %ERRORLEVEL%
)
if not exist ".tools\uber-apk-signer.jar" call "scripts\setup-patcher-tools.bat"
if errorlevel 1 (
  pause
  exit /b %ERRORLEVEL%
)

echo Verificando suporte bundle-aware...
python -c "import UnityPy,sys; sys.exit(0 if getattr(UnityPy,'__version__','') == '1.25.3' else 1)" >nul 2>nul
if errorlevel 1 (
  echo Instalando UnityPy 1.25.3 para reserializacao segura de bundles Unity...
  python -m pip install --disable-pip-version-check "UnityPy==1.25.3"
  if errorlevel 1 (
    echo [ERRO] Nao foi possivel instalar UnityPy 1.25.3.
    echo Execute manualmente: python -m pip install UnityPy==1.25.3
    pause
    exit /b 3
  )
)

set "APKTOOL=.tools\apktool.jar"
set "SIGNER=.tools\uber-apk-signer.jar"
set "WORK=work\apk-patch"
set "DECODED=%WORK%\decoded"
set "UNSIGNED=%WORK%\revival-unsigned.apk"
set "REPORT=%WORK%\patch-report.json"
set "PREFLIGHT_REPORT=%WORK%\server-preflight.json"
set "VERIFY_REPORT=%WORK%\final-apk-verification.json"
set "OUT=output\mighty-doom-revival.apk"

if exist "%WORK%" rmdir /s /q "%WORK%"
mkdir "%WORK%" >nul 2>nul
if not exist "output" mkdir "output" >nul 2>nul

echo.
echo [1/8] Validando servidor Revival por HTTPS...
if "%CA_FILE%"=="" (
  python scripts\check_revival_server.py --server "%SERVER_HOST%" --report "%PREFLIGHT_REPORT%"
) else (
  python scripts\check_revival_server.py --server "%SERVER_HOST%" --ca "%CA_FILE%" --report "%PREFLIGHT_REPORT%"
)
if errorlevel 1 (
  echo.
  echo [PARADO] O servidor HTTPS ainda nao esta pronto para receber o cliente.
  echo O patcher exige /revival/health com client 1.13.1, API 24.0.0 e GameData carregado.
  echo Corrija DNS/TLS/servidor antes de gerar um APK apontando para um destino quebrado.
  pause
  exit /b 11
)

echo.
echo [2/8] Analisando APK...
python scripts\analyze_apk.py "%APK%"
if errorlevel 1 (
  echo [ERRO] O APK nao passou pela analise inicial.
  pause
  exit /b %ERRORLEVEL%
)

echo.
echo [3/8] Desmontando APK...
java -jar "%APKTOOL%" d -f "%APK%" -o "%DECODED%"
if errorlevel 1 (
  echo [ERRO] Apktool falhou ao desmontar o APK.
  pause
  exit /b 4
)

echo.
echo [4/8] Aplicando servidor e configuracao TLS...
if "%CA_FILE%"=="" (
  python scripts\patch_apk.py --decoded "%DECODED%" --server "%SERVER_HOST%" --report "%REPORT%"
) else (
  python scripts\patch_apk.py --decoded "%DECODED%" --server "%SERVER_HOST%" --ca "%CA_FILE%" --report "%REPORT%"
)
set "PATCH_RC=%ERRORLEVEL%"

if "%PATCH_RC%"=="4" (
  echo.
  echo Patch direto incompleto. Tentando patch bundle-aware em TODOS os bundles Addressables...
  python scripts\patch_bundle_from_report.py --decoded "%DECODED%" --server "%SERVER_HOST%" --report "%REPORT%" --sweep-all-bundles
  set "PATCH_RC=!ERRORLEVEL!"
)

if not "%PATCH_RC%"=="0" (
  echo.
  echo [PARADO] O patcher nao conseguiu provar uma alteracao segura do bundle Unity.
  echo Nenhum patch binario de tamanho variavel foi feito no escuro.
  echo Relatorio: %REPORT%
  pause
  exit /b %PATCH_RC%
)

echo.
echo [5/8] Reconstruindo APK...
java -jar "%APKTOOL%" b "%DECODED%" -o "%UNSIGNED%"
if errorlevel 1 (
  echo [ERRO] Apktool falhou ao reconstruir o APK.
  pause
  exit /b 5
)

echo.
echo [6/8] Validando endpoint dentro do APK reconstruido...
python scripts\verify_patched_apk.py --apk "%UNSIGNED%" --server "%SERVER_HOST%" --report "%VERIFY_REPORT%"
if errorlevel 1 (
  echo [ERRO] APK reconstruido nao passou pelo gate do endpoint Revival.
  echo Relatorio: %VERIFY_REPORT%
  pause
  exit /b 6
)

echo.
echo [7/8] Alinhando, assinando e verificando assinatura...
java -jar "%SIGNER%" -a "%UNSIGNED%" --overwrite --verbose
if errorlevel 1 (
  echo [ERRO] Falha ao alinhar/assinar o APK.
  pause
  exit /b 7
)

java -jar "%SIGNER%" -a "%UNSIGNED%" --onlyVerify --verbose
if errorlevel 1 (
  echo [ERRO] A verificacao da assinatura falhou.
  pause
  exit /b 8
)

python scripts\verify_patched_apk.py --apk "%UNSIGNED%" --server "%SERVER_HOST%" --report "%VERIFY_REPORT%"
if errorlevel 1 (
  echo [ERRO] APK assinado falhou na verificacao final do endpoint.
  pause
  exit /b 9
)

if exist "%OUT%" del /q "%OUT%"
copy /Y "%UNSIGNED%" "%OUT%" >nul
if errorlevel 1 (
  echo [ERRO] Nao foi possivel criar %OUT%.
  pause
  exit /b 10
)

echo.
echo [8/8] CONCLUIDO
echo APK gerado e verificado: %OUT%
echo Servidor: https://%SERVER_HOST%
echo Preflight HTTPS: %PREFLIGHT_REPORT%
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
pause
exit /b 0

:require
where %1 >nul 2>nul
if errorlevel 1 (
  echo [FALTA] %1 nao esta no PATH.
  exit /b 1
)
echo [OK] %1
exit /b 0
