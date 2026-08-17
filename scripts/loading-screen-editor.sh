#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
else
  echo "[ERRO] Python 3 não encontrado no PATH." >&2
  exit 2
fi

if ! "$PYTHON_BIN" -c 'import PIL' >/dev/null 2>&1; then
  echo "[ERRO] Pillow não está instalado." >&2
  echo "Instale com: $PYTHON_BIN -m pip install Pillow" >&2
  exit 3
fi

exec "$PYTHON_BIN" scripts/loading_screen_editor.py "$@"
