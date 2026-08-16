@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0\.."

echo ============================================================
echo  Mighty DOOM Revival - APK patcher experimental

echo  Uso pessoal / preservacao. O APK original nao e distribuido.
echo ============================================================
echo.

set "APK=input\mighty-doom.apk"
set /p "APK_INPUT=Caminho do APK [%APK%]: "
if not "%APK_INPUT%"=="" set "APK=%APK_INPUT%"

if not exist "%APK%" (
  echo [ERRO] APK nao encontrado: %APK%
  exit /b 2
)

set "SERVER_HOST="
set /p "SERVER_HOST=Hostname HTTPS do seu servidor (ex.: doom.seudominio.com): "
if "%SERVER_HOST%"=="" (
  echo [ERRO] Informe o hostname do servidor.
  exit /b 2
)

set "CA_FILE="
set /p "CA_FILE=CA PEM/CRT local para HTTPS [ENTER = somente CAs do sistema]: "
if not "%CA_FILE%"=="" if not exist "%CA_FILE%" (
  echo [ERRO] CA nao encontrada: %CA_FILE%
  exit /b 2
)

echo.
echo Verificando dependencias...
call :require python || exit /b 3
call :require java || exit /b 3
call :require apktool || exit /b 3
call :require keytool || exit /b 3
call :require zipalign || exit /b 3
call :require apksigner || exit /b 3

set "WORK=work\apk-patch"
set "DECODED=%WORK%\decoded"
set "UNSIGNED=%WORK%\unsigned.apk"
set "ALIGNED=%WORK%\aligned.apk"
set "REPORT=%WORK%\patch-report.json"
set "OUT=output\mighty-doom-revival.apk"
set "KEYDIR=work\signing"
set "KEYSTORE=%KEYDIR%\revival.keystore"
set "ALIAS=mightydoom-revival"
set "KSPASS=changeit"

if exist "%WORK%" rmdir /s /q "%WORK%"
mkdir "%WORK%" >nul 2>nul
mkdir "output" >nul 2>nul
mkdir "%KEYDIR%" >nul 2>nul

echo.
echo [1/6] Analisando APK...
python scripts\analyze_apk.py "%APK%"
if errorlevel 1 exit /b %errorlevel%

echo.
echo [2/6] Desmontando com apktool...
apktool d -f "%APK%" -o "%DECODED%"
if errorlevel 1 (
  echo [ERRO] apktool falhou.
  exit /b 4
)

echo.
echo [3/6] Aplicando configuracao de servidor/TLS...
if "%CA_FILE%"=="" (
  python scripts\patch_apk.py --decoded "%DECODED%" --server "%SERVER_HOST%" --report "%REPORT%"
) else (
  python scripts\patch_apk.py --decoded "%DECODED%" --server "%SERVER_HOST%" --ca "%CA_FILE%" --report "%REPORT%"
)
set "PATCH_RC=%ERRORLEVEL%"
if not "%PATCH_RC%"=="0" (
  echo.
  echo [PARADO] O patcher recusou uma alteracao insegura.
  echo Veja: %REPORT%
  echo.
  echo Isto e esperado se o hostname novo tiver tamanho diferente do host
  echo serializado no Unity bundle. Depois de validar o APK real, o projeto
  echo implementara reserializacao bundle-aware em vez de corromper o arquivo.
  exit /b %PATCH_RC%
)

echo.
echo [4/6] Recompilando APK...
apktool b "%DECODED%" -o "%UNSIGNED%"
if errorlevel 1 (
  echo [ERRO] Falha ao recompilar APK.
  exit /b 5
)

echo.
echo [5/6] Alinhando e assinando...
zipalign -f -p 4 "%UNSIGNED%" "%ALIGNED%"
if errorlevel 1 (
  echo [ERRO] zipalign falhou.
  exit /b 6
)

if not exist "%KEYSTORE%" (
  echo Criando chave pessoal de laboratorio em %KEYSTORE% ...
  keytool -genkeypair -v -keystore "%KEYSTORE%" -storepass "%KSPASS%" -keypass "%KSPASS%" -alias "%ALIAS%" -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Mighty DOOM Revival, OU=Personal Preservation, O=Local, C=BR"
  if errorlevel 1 (
    echo [ERRO] Nao foi possivel gerar a chave de assinatura.
    exit /b 7
  )
)

if exist "%OUT%" del /q "%OUT%"
apksigner sign --ks "%KEYSTORE%" --ks-key-alias "%ALIAS%" --ks-pass pass:%KSPASS% --key-pass pass:%KSPASS% --out "%OUT%" "%ALIGNED%"
if errorlevel 1 (
  echo [ERRO] apksigner falhou.
  exit /b 8
)

apksigner verify --verbose "%OUT%"
if errorlevel 1 (
  echo [ERRO] A verificacao da assinatura falhou.
  exit /b 9
)

echo.
echo [6/6] CONCLUIDO
echo APK gerado: %OUT%
echo Relatorio: %REPORT%
echo.
echo ATENCAO: a assinatura e diferente da oficial. Em aparelho de testes,
echo provavelmente sera necessario desinstalar com:
echo   adb uninstall com.bethsoft.ubu
echo e depois instalar com:
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
