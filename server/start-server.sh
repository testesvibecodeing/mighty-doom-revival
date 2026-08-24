#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# studio-forward: sem argumentos e em sessão gráfica interativa, abre o Revival
# Studio — que inicia o servidor local como serviço de segundo plano (com
# health check e PID registrado). O caminho headless abaixo (foreground,
# CTRL+C para encerrar) permanece intacto para terminal/CI/VPS.
if [[ $# -eq 0 ]] && [[ -t 0 ]] && { [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]] || [[ "$(uname -s)" == "Darwin" ]]; }; then
  if command -v python3 >/dev/null 2>&1; then
    exec python3 "$(dirname "${BASH_SOURCE[0]}")/revival_studio.py"
  elif command -v python >/dev/null 2>&1; then
    exec python "$(dirname "${BASH_SOURCE[0]}")/revival_studio.py"
  fi
fi

if ! command -v node >/dev/null 2>&1; then
  echo '[ERRO] Node.js não encontrado. Execute scripts/setup-server.sh primeiro.' >&2
  exit 2
fi

if ! node -e "const s=require('node:sqlite'); const db=new s.DatabaseSync(':memory:'); db.close()" >/dev/null 2>&1; then
  echo '[ERRO] O Node instalado não possui SQLite nativo. Execute scripts/setup-server.sh.' >&2
  exit 2
fi

if [[ ! -f server/.env ]]; then
  # --headless: chamada argumentada, o branch studio-forward do setup exige
  # zero argumentos — sem isso abriria a GUI no meio de um fluxo headless.
  "$ROOT/scripts/setup-server.sh" --headless
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
