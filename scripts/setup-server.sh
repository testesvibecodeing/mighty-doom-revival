#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_DIR="$ROOT/server"

for cmd in node npm; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[ERRO] $cmd não encontrado. Use Node.js 24+." >&2
    exit 2
  fi
done

NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])')"
if (( NODE_MAJOR < 24 )); then
  echo "[ERRO] Node.js 24+ necessário. Encontrado: $(node --version)" >&2
  exit 2
fi

cp -n "$SERVER_DIR/config/revival.example.json" "$SERVER_DIR/config/revival.json" || true
cp -n "$SERVER_DIR/config/packs.example.json" "$SERVER_DIR/config/packs.json" || true
cp -n "$SERVER_DIR/config/events.example.json" "$SERVER_DIR/config/events.json" || true
mkdir -p "$SERVER_DIR/runtime" "$SERVER_DIR/data"

cd "$SERVER_DIR"
echo '[1/3] Instalando dependências...'
npm install

echo '[2/3] Verificando sintaxe...'
npm run check

echo '[3/3] Preparação concluída.'
cat <<'EOF'

Para iniciar:
  cd server
  npm start

Health check:
  http://127.0.0.1:8080/revival/health

Para compatibilidade completa, coloque o game-data validado em:
  server/data/game-data.json
EOF
