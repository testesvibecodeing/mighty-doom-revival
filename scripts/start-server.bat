@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

echo ============================================================
echo  Mighty DOOM Revival - iniciar servidor
echo ============================================================
echo.

where node >nul 2>nul || (
  echo [ERRO] Node.js nao encontrado.
  echo Execute primeiro scripts\setup-server.bat
  pause
  exit /b 2
)

node -e "const s=require('node:sqlite'); const db=new s.DatabaseSync(':memory:'); db.close()" >nul 2>nul
if errorlevel 1 (
  echo [ERRO] O Node instalado nao possui SQLite nativo.
  echo Execute scripts\setup-server.bat para diagnostico.
  pause
  exit /b 2
)

if not exist "server\.env" (
  echo Configuracao inicial ausente. Preparando...
  call "scripts\setup-server.bat"
  if errorlevel 1 (
    pause
    exit /b %ERRORLEVEL%
  )
)

if not exist "server\data\game-data.json" (
  echo [INFO] GameData local ausente. Tentando importar snapshot comunitario...
  where python >nul 2>nul
  if not errorlevel 1 (
    python "scripts\fetch-community-gamedata.py"
  ) else (
    where py >nul 2>nul
    if not errorlevel 1 py -3 "scripts\fetch-community-gamedata.py"
  )
  if not exist "server\data\game-data.json" (
    echo.
    echo [AVISO] Nao foi possivel obter GameData automaticamente.
    echo O servidor pode iniciar para diagnostico, mas o cliente nao tera bootstrap completo.
    echo.
  )
)

echo.
echo Iniciando Mighty DOOM Revival...
echo Para encerrar use CTRL+C.
echo.
node "server\src\index.js"
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
  echo [ERRO] Servidor encerrou com codigo %RC%.
) else (
  echo Servidor encerrado.
)
pause
exit /b %RC%
