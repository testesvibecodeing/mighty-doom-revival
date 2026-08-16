#!/usr/bin/env bash
# Mighty DOOM Revival - baixar e analisar APK oficial alvo (Linux/Mac)
# O APK fica somente na sua máquina e não entra no Git.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "============================================================"
echo " Mighty DOOM Revival - baixar e analisar APK oficial alvo"
echo " O APK fica somente no seu PC e não entra no Git."
echo "============================================================"
echo

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
else
  echo "[ERRO] Python não encontrado no PATH." >&2
  echo "Instale o Python 3 e garanta que \"python3\" esteja acessível no PATH." >&2
  exit 2
fi

mkdir -p input reports

echo "[1/2] Baixando Mighty DOOM 1.13.1 e validando SHA-256..."
if [[ -n "${1:-}" ]]; then
  DOWNLOAD_OK=1
  "$PYTHON_BIN" scripts/fetch-uptodown-apk.py --output input/mighty-doom.apk --direct-url "$1" || DOWNLOAD_OK=0
else
  DOWNLOAD_OK=1
  "$PYTHON_BIN" scripts/fetch-uptodown-apk.py --output input/mighty-doom.apk || DOWNLOAD_OK=0
fi

if [[ "$DOWNLOAD_OK" != "1" ]]; then
  echo
  echo "[ERRO] Falha ao baixar/validar o APK oficial. Veja a mensagem acima para detalhes." >&2
  echo >&2
  echo "A Uptodown passou a exigir um desafio Cloudflare Turnstile antes de" >&2
  echo "liberar o link de download, então a raspagem automática pode falhar." >&2
  echo "Solução manual:" >&2
  echo "  1. Abra no navegador a página de download da Uptodown e clique em Download." >&2
  echo "  2. Copie a URL final \"https://dw.uptodown.com/dwn/...\" (aba Rede do" >&2
  echo "     DevTools ou o gerenciador de downloads)." >&2
  echo "  3. Rode: scripts/analyze-official-apk.sh \"https://dw.uptodown.com/dwn/...\"" >&2
  exit 1
fi

echo
echo "[2/2] Gerando relatórios sanitizados..."
"$PYTHON_BIN" scripts/analyze_apk.py input/mighty-doom.apk --json-out reports/apk-1.13.1.json --md-out reports/apk-1.13.1.md

echo
echo "CONCLUÍDO."
echo "APK local: input/mighty-doom.apk"
echo "Relatório JSON: reports/apk-1.13.1.json"
echo "Relatório Markdown: reports/apk-1.13.1.md"
echo
echo "O diretório reports e o APK estão ignorados pelo Git."
