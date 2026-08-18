#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_DIR="$ROOT/server"

# studio-forward: sem argumentos e em sessão gráfica interativa, abre o Revival
# Studio — que prepara o servidor local como serviço (mesmos passos, com
# relatório estruturado e cancelamento). O caminho headless abaixo permanece
# intacto para terminal/CI/VPS: com argumentos, ou sem display, segue direto.
if [[ $# -eq 0 ]] && [[ -t 0 ]] && { [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]] || [[ "$(uname -s)" == "Darwin" ]]; }; then
  if command -v python3 >/dev/null 2>&1; then
    exec python3 "$(dirname "${BASH_SOURCE[0]}")/revival_studio.py"
  elif command -v python >/dev/null 2>&1; then
    exec python "$(dirname "${BASH_SOURCE[0]}")/revival_studio.py"
  fi
fi

if ! command -v node >/dev/null 2>&1; then
  echo '[ERRO] Node.js não encontrado. Instale Node.js 22.5+; Node 24 LTS é recomendado.' >&2
  exit 2
fi

echo '[1/4] Validando Node.js e SQLite nativo...'
if ! node -e "const s=require('node:sqlite'); const db=new s.DatabaseSync(':memory:'); db.exec('select 1'); db.close()" >/dev/null 2>&1; then
  echo "[ERRO] node:sqlite não está disponível em $(node --version). Use Node.js 22.5+; Node 24 LTS é recomendado." >&2
  exit 2
fi
node --version

cp -n "$SERVER_DIR/.env.example" "$SERVER_DIR/.env" 2>/dev/null || true
cp -n "$SERVER_DIR/config/revival.example.json" "$SERVER_DIR/config/revival.json" 2>/dev/null || true
cp -n "$SERVER_DIR/config/packs.example.json" "$SERVER_DIR/config/packs.json" 2>/dev/null || true
cp -n "$SERVER_DIR/config/events.example.json" "$SERVER_DIR/config/events.json" 2>/dev/null || true
mkdir -p "$SERVER_DIR/runtime" "$SERVER_DIR/data"

echo '[2/4] Verificando sintaxe do servidor...'
for file in \
  "$SERVER_DIR/src/index.js" \
  "$SERVER_DIR/src/chapters.js" \
  "$SERVER_DIR/src/config.js" \
  "$SERVER_DIR/src/db.js" \
  "$SERVER_DIR/src/events.js" \
  "$SERVER_DIR/src/game-data-model.js" \
  "$SERVER_DIR/src/store.js" \
  "$SERVER_DIR/test/smoke.mjs"; do
  node --check "$file"
done

echo '[3/4] Executando teste real end-to-end local...'
node "$SERVER_DIR/test/smoke.mjs"

echo '[4/4] Preparação concluída.'
cat <<'EOF'

Nenhum npm install é necessário: o servidor usa apenas módulos nativos do Node.

IMPORTANTE: edite server/.env e troque REVIVAL_ADMIN_TOKEN=change-me.

Para iniciar:
  ./scripts/start-server.sh

Health check:
  http://127.0.0.1:8080/revival/health
EOF

if [[ ! -f "$SERVER_DIR/data/game-data.json" ]]; then
  cat <<'EOF'

[AVISO] server/data/game-data.json ainda não existe.
Para bootstrap de pesquisa:
  python3 scripts/fetch-community-gamedata.py
EOF
fi
