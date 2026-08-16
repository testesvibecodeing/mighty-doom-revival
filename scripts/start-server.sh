#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v node >/dev/null 2>&1; then
  echo '[ERRO] Node.js não encontrado. Execute scripts/setup-server.sh primeiro.' >&2
  exit 2
fi

if ! node -e "const s=require('node:sqlite'); const db=new s.DatabaseSync(':memory:'); db.close()" >/dev/null 2>&1; then
  echo '[ERRO] O Node instalado não possui SQLite nativo. Execute scripts/setup-server.sh.' >&2
  exit 2
fi

if [[ ! -f server/.env ]]; then
  "$ROOT/scripts/setup-server.sh"
fi

if [[ ! -f server/data/game-data.json ]]; then
  echo '[INFO] GameData local ausente. Tentando importar snapshot comunitário...'
  if command -v python3 >/dev/null 2>&1; then
    python3 scripts/fetch-community-gamedata.py || true
  elif command -v python >/dev/null 2>&1; then
    python scripts/fetch-community-gamedata.py || true
  fi
fi

if [[ ! -f server/data/game-data.json ]]; then
  echo '[AVISO] GameData continua ausente; o servidor iniciará em modo de diagnóstico.' >&2
fi

exec node server/src/index.js
