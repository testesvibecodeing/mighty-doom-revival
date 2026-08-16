@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

set "SERVER_DIR=server\community"

echo ============================================================
echo  Mighty DOOM Revival - servidor comunitario (Windows)
echo ============================================================
echo.

where git >nul 2>nul || (echo [ERRO] git nao encontrado no PATH.& exit /b 2)
where node >nul 2>nul || (echo [ERRO] Node.js nao encontrado no PATH. Use Node 24+.& exit /b 2)
where npm >nul 2>nul || (echo [ERRO] npm nao encontrado no PATH. Use npm 11+.& exit /b 2)

if not exist "server" mkdir "server"

if not exist "%SERVER_DIR%\.git" (
  echo Clonando servidor upstream...
  git clone https://gitlab.com/dannyhpy/mightydoom-gameserver.git "%SERVER_DIR%"
  if errorlevel 1 exit /b 3
) else (
  echo Servidor ja existe. Atualizando...
  git -C "%SERVER_DIR%" pull --ff-only
  if errorlevel 1 exit /b 3
)

pushd "%SERVER_DIR%"

echo.
echo Instalando dependencias...
call npm install --omit=dev --omit=optional
if errorlevel 1 (popd & exit /b 4)

call npm install better-sqlite3
if errorlevel 1 (popd & exit /b 4)

echo.
echo Executando migrations...
call npx knex migrate:latest
if errorlevel 1 (popd & exit /b 5)

echo.
echo ============================================================
echo  Servidor preparado.
echo  Para iniciar:
echo    cd %SERVER_DIR%
echo    npm run start -- --addr 127.0.0.1 --port 8080 --proxy --debug
echo ============================================================

popd
exit /b 0
