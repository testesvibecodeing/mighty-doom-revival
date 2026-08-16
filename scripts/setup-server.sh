#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_DIR="$ROOT/server/community"

for cmd in git node npm; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[ERRO] $cmd não encontrado. O upstream atual requer Node.js 24+ e npm 11+." >&2
    exit 2
  fi
done

mkdir -p "$ROOT/server"

if [[ ! -d "$SERVER_DIR/.git" ]]; then
  echo "Clonando servidor upstream..."
  git clone https://gitlab.com/dannyhpy/mightydoom-gameserver.git "$SERVER_DIR"
else
  echo "Servidor já existe. Atualizando..."
  git -C "$SERVER_DIR" pull --ff-only
fi

cd "$SERVER_DIR"

npm install --omit=dev --omit=optional
npm install better-sqlite3
npx knex migrate:latest

cat <<'EOF'

Servidor preparado.

Para iniciar atrás de Nginx/Caddy:
  cd server/community
  npm run start -- --addr 127.0.0.1 --port 8080 --proxy --debug
EOF
