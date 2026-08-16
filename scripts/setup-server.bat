@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

echo ============================================================
echo  Mighty DOOM Revival - preparar servidor proprio (Windows)
echo ============================================================
echo.

where node >nul 2>nul || (echo [ERRO] Node.js nao encontrado no PATH. Use Node 24+.& exit /b 2)
where npm >nul 2>nul || (echo [ERRO] npm nao encontrado no PATH.& exit /b 2)

for /f "tokens=1 delims=." %%V in ('node -p "process.versions.node"') do set "NODE_MAJOR=%%V"
if %NODE_MAJOR% LSS 24 (
  echo [ERRO] Node.js 24+ necessario. Encontrado: 
  node --version
  exit /b 2
)

if not exist "server\config\revival.json" copy /Y "server\config\revival.example.json" "server\config\revival.json" >nul
if not exist "server\config\packs.json" copy /Y "server\config\packs.example.json" "server\config\packs.json" >nul
if not exist "server\config\events.json" copy /Y "server\config\events.example.json" "server\config\events.json" >nul
if not exist "server\runtime" mkdir "server\runtime"
if not exist "server\data" mkdir "server\data"

pushd server

echo [1/3] Instalando dependencias...
call npm install
if errorlevel 1 (popd & exit /b 3)

echo [2/3] Verificando sintaxe...
call npm run check
if errorlevel 1 (popd & exit /b 4)

echo [3/3] Preparacao concluida.
popd

echo.
echo Para iniciar:
echo   cd server
echo   npm start
echo.
echo Health check:
echo   http://127.0.0.1:8080/revival/health
echo.
echo IMPORTANTE: para compatibilidade completa ainda sera necessario
 echo colocar o game-data validado em server\data\game-data.json.
exit /b 0
