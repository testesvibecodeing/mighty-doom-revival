@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0\.."

rem studio-forward: sem argumentos, abre o Revival Studio, que prepara o
rem servidor local como servico (mesmos passos, com relatorio estruturado
rem e cancelamento). O caminho headless de prompts abaixo permanece intacto
rem para terminal/CI/VPS.
if "%~1"=="" (
  where python >nul 2>nul
  if not errorlevel 1 (
    python "%~dp0revival_studio.py"
    exit /b !errorlevel!
  )
)

echo ============================================================
echo  Mighty DOOM Revival - preparar servidor standalone (Windows)
echo ============================================================
echo.

where node >nul 2>nul || (
  echo [ERRO] Node.js nao encontrado no PATH.
  echo Instale Node.js 22.5+ ou 24 LTS e tente novamente.
  pause
  exit /b 2
)

echo [1/4] Validando Node.js e SQLite nativo...
node -e "const s=require('node:sqlite'); const db=new s.DatabaseSync(':memory:'); db.exec('select 1'); db.close()" >nul 2>nul
if errorlevel 1 (
  echo [ERRO] Esta versao do Node nao possui node:sqlite funcional.
  echo Encontrado:
  node --version
  echo Use Node.js 22.5+; Node 24 LTS e o recomendado.
  pause
  exit /b 2
)
node --version

if not exist "server\.env" copy /Y "server\.env.example" "server\.env" >nul
if not exist "server\config\revival.json" copy /Y "server\config\revival.example.json" "server\config\revival.json" >nul
if not exist "server\config\packs.json" copy /Y "server\config\packs.example.json" "server\config\packs.json" >nul
if not exist "server\config\events.json" copy /Y "server\config\events.example.json" "server\config\events.json" >nul
if not exist "server\runtime" mkdir "server\runtime"
if not exist "server\data" mkdir "server\data"

echo [2/4] Verificando sintaxe do servidor...
for %%F in (
  "server\src\index.js"
  "server\src\chapters.js"
  "server\src\config.js"
  "server\src\db.js"
  "server\src\events.js"
  "server\src\game-data-model.js"
  "server\src\store.js"
  "server\test\smoke.mjs"
) do (
  node --check %%F
  if errorlevel 1 (
    pause
    exit /b 3
  )
)

echo [3/4] Executando teste real end-to-end local...
node "server\test\smoke.mjs"
if errorlevel 1 (
  echo [ERRO] O smoke test do servidor falhou.
  pause
  exit /b 4
)

echo [4/4] Preparacao concluida.
echo.
echo Nenhum npm install e necessario: o servidor usa apenas modulos do Node.
echo.
echo IMPORTANTE: edite server\.env e troque REVIVAL_ADMIN_TOKEN=change-me.
echo.
if not exist "server\data\game-data.json" (
  echo [AVISO] server\data\game-data.json ainda nao existe.
  echo Para bootstrap de pesquisa, execute:
  echo   python scripts\fetch-community-gamedata.py
  echo.
)
echo Para iniciar agora:
echo   scripts\start-server.bat
echo.
echo Health check:
echo   http://127.0.0.1:8080/revival/health
echo.
pause
exit /b 0
