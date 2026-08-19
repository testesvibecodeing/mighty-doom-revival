#!/usr/bin/env bash
# Revival Studio — abre a janela do editor (plano, item 6 do cap. 30).
# Não é caminho headless: CI/VPS usam os scripts Python diretamente.
set -euo pipefail
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "ERRO: python não encontrado no PATH. Instale o Python 3.11+." >&2
  exit 1
fi

exec "$PY" "$AQUI/revival_studio.py" "$@"
