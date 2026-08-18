@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0\.."

rem studio-forward: sem argumentos, abre o Revival Studio na aba Visuais,
rem que usa a mesma composicao e o mesmo fluxo de injecao validados. Com
rem argumentos, abre o editor standalone original (caminho headless mantido).
if "%~1"=="" (
  where python >nul 2>nul
  if not errorlevel 1 (
    python "%~dp0revival_studio.py"
    exit /b !errorlevel!
  )
)

python scripts\loading_screen_editor.py %*
if errorlevel 1 pause
