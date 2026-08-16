@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

echo ============================================================
echo  Mighty DOOM Revival - baixar e analisar APK oficial alvo
echo  O APK fica somente no seu PC e nao entra no Git.
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERRO] Python nao encontrado no PATH.
  echo Instale o Python 3 e garanta que "python" esteja acessivel no PATH.
  pause
  exit /b 2
)

if not exist "input" mkdir "input"
if not exist "reports" mkdir "reports"

echo [1/2] Baixando Mighty DOOM 1.13.1 e validando SHA-256...
if not "%~1"=="" (
  python scripts\fetch-uptodown-apk.py --output input\mighty-doom.apk --direct-url "%~1"
) else (
  python scripts\fetch-uptodown-apk.py --output input\mighty-doom.apk
)
if errorlevel 1 (
  echo.
  echo [ERRO] Falha ao baixar/validar o APK oficial. Veja a mensagem acima para detalhes.
  echo.
  echo A Uptodown passou a exigir um desafio Cloudflare Turnstile antes de
  echo liberar o link de download, entao a raspagem automatica pode falhar.
  echo Solucao manual:
  echo   1. Abra no navegador a pagina de download da Uptodown e clique em Download.
  echo   2. Copie a URL final "https://dw.uptodown.com/dwn/..." ^(aba Rede do
  echo      DevTools ou o gerenciador de downloads^).
  echo   3. Rode: scripts\analyze-official-apk.bat "https://dw.uptodown.com/dwn/..."
  pause
  exit /b %errorlevel%
)

echo.
echo [2/2] Gerando relatorios sanitizados...
python scripts\analyze_apk.py input\mighty-doom.apk --json-out reports\apk-1.13.1.json --md-out reports\apk-1.13.1.md
if errorlevel 1 (
  echo.
  echo [ERRO] Falha ao gerar os relatorios do APK. Veja a mensagem acima para detalhes.
  pause
  exit /b %errorlevel%
)

echo.
echo CONCLUIDO.
echo APK local: input\mighty-doom.apk
echo Relatorio JSON: reports\apk-1.13.1.json
echo Relatorio Markdown: reports\apk-1.13.1.md
echo.
echo O diretorio reports e o APK estao ignorados pelo Git.
pause
exit /b 0
