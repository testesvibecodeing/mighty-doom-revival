@echo off
rem Revival Studio - abre a janela do editor (plano, item 6 do cap. 30).
rem Nao e caminho headless: CI/VPS usam os scripts Python diretamente.
setlocal
set "AQUI=%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo ERRO: python nao encontrado no PATH. Instale o Python 3.11+.
    exit /b 1
)

python "%AQUI%revival_studio.py" %*
exit /b %errorlevel%
