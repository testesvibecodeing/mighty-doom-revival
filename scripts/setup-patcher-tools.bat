@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0\.."

rem studio-forward: sem argumentos, abre o Revival Studio, cujo botao "Preparar
rem ferramentas" executa este mesmo script em modo --headless (mesmo download,
rem mesmos hashes). Com argumentos segue direto para o caminho headless.
if "%~1"=="" (
  where python >nul 2>nul
  if not errorlevel 1 (
    python "%~dp0revival_studio.py"
    exit /b !errorlevel!
  )
)

set "HEADLESS=0"
if /i "%~1"=="--headless" set "HEADLESS=1"

echo ============================================================
echo  Mighty DOOM Revival - preparar ferramentas do patcher
echo ============================================================
echo.

where python >nul 2>nul || (
  echo [ERRO] Python nao encontrado no PATH.
  echo Necessario ao resolvedor de Java do projeto.
  call :pause_if_interactive
  exit /b 2
)
where powershell >nul 2>nul || (
  echo [ERRO] PowerShell nao encontrado.
  call :pause_if_interactive
  exit /b 2
)

rem fase 3: o Java vem do mesmo resolvedor do Studio (explicito/REVIVAL_JAVA
rem > .tools\jre17 > PATH 17+), nao do PATH as cegas.
set "JAVA_BIN="
for /f "usebackq delims=" %%J in (`python scripts\resolve_java.py 2^>nul`) do set "JAVA_BIN=%%J"
if not defined JAVA_BIN (
  python scripts\resolve_java.py
  echo [ERRO] Nenhum Java 17+ utilizavel.
  call :pause_if_interactive
  exit /b 2
)
echo [OK] java: !JAVA_BIN!

set "TOOL_DIR=.tools"
set "APKTOOL=%TOOL_DIR%\apktool.jar"
set "SIGNER=%TOOL_DIR%\uber-apk-signer.jar"

set "APKTOOL_URL=https://github.com/iBotPeaches/Apktool/releases/download/v3.0.3/apktool_3.0.3.jar"
set "APKTOOL_SHA=dbf930b076c6b9be08d57c449cacefc3bdd6b71ebd59b3066fc0e1f5b14f9423"
set "SIGNER_URL=https://github.com/patrickfav/uber-apk-signer/releases/download/v1.3.0/uber-apk-signer-1.3.0.jar"
set "SIGNER_SHA=e1299fd6fcf4da527dd53735b56127e8ea922a321128123b9c32d619bba1d835"

if not exist "%TOOL_DIR%" mkdir "%TOOL_DIR%"

call :download_and_verify "%APKTOOL_URL%" "%APKTOOL%" "%APKTOOL_SHA%" "Apktool 3.0.3"
if errorlevel 1 (
  call :pause_if_interactive
  exit /b %ERRORLEVEL%
)

call :download_and_verify "%SIGNER_URL%" "%SIGNER%" "%SIGNER_SHA%" "Uber APK Signer 1.3.0"
if errorlevel 1 (
  call :pause_if_interactive
  exit /b %ERRORLEVEL%
)

echo.
echo Validando executaveis Java...
"%JAVA_BIN%" -jar "%APKTOOL%" --version
if errorlevel 1 (
  echo [ERRO] Apktool baixado nao executou corretamente.
  call :pause_if_interactive
  exit /b 5
)
"%JAVA_BIN%" -jar "%SIGNER%" --version
if errorlevel 1 (
  echo [ERRO] Uber APK Signer baixado nao executou corretamente.
  call :pause_if_interactive
  exit /b 5
)

echo.
echo [OK] Ferramentas do patcher preparadas em %TOOL_DIR%.
echo      Essa pasta e ignorada pelo Git.
call :pause_if_interactive
exit /b 0

:download_and_verify
set "URL=%~1"
set "DEST=%~2"
set "EXPECTED=%~3"
set "LABEL=%~4"

if exist "%DEST%" (
  call :verify_hash "%DEST%" "%EXPECTED%"
  if not errorlevel 1 (
    echo [OK] %LABEL% ja existe e o SHA-256 confere.
    exit /b 0
  )
  echo [AVISO] Hash invalido em %DEST%. Baixando novamente...
  del /q "%DEST%"
)

echo Baixando %LABEL%...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri '%URL%' -OutFile '%DEST%'"
if errorlevel 1 (
  echo [ERRO] Falha ao baixar %LABEL%.
  if exist "%DEST%" del /q "%DEST%"
  exit /b 3
)

call :verify_hash "%DEST%" "%EXPECTED%"
if errorlevel 1 (
  echo [ERRO] SHA-256 de %LABEL% nao confere. Arquivo removido.
  del /q "%DEST%"
  exit /b 4
)
echo [OK] %LABEL% validado.
exit /b 0

:verify_hash
set "FILE=%~1"
set "EXPECTED_HASH=%~2"
set "ACTUAL_HASH="
for /f "usebackq delims=" %%H in (`powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 -LiteralPath '%FILE%').Hash.ToLowerInvariant()"`) do set "ACTUAL_HASH=%%H"
if /I "%ACTUAL_HASH%"=="%EXPECTED_HASH%" exit /b 0
exit /b 1

:pause_if_interactive
if "%HEADLESS%"=="1" exit /b 0
pause
exit /b 0
