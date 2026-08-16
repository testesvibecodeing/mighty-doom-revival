#!/usr/bin/env bash
# Mighty DOOM Revival - instalador completo para VPS (Debian/Ubuntu)
#
# Uso:
#   git pull
#   sudo ./scripts/install.sh
#
# O script é idempotente: pode ser executado de novo a cada "git pull" para
# atualizar o servidor em produção. Ele instala Node.js e Caddy se faltarem,
# prepara a configuração do servidor, roda os testes automatizados como
# gate de deploy, sobe o servidor via systemd e configura HTTPS automático
# (Let's Encrypt) via Caddy para o domínio informado.
#
# Toda a execução é registrada em deploy/logs/install-<timestamp>.log.

if [ -z "${BASH_VERSION:-}" ]; then
  echo "[ERRO] Execute este script com bash: sudo bash scripts/install.sh" >&2
  exit 1
fi

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_DIR="$ROOT/server"
DEPLOY_DIR="$ROOT/deploy"
LOG_DIR="$DEPLOY_DIR/logs"
mkdir -p "$LOG_DIR"

TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/install-$TS.log"
: > "$LOG_FILE"

# Espelha tudo (stdout + stderr) no log, mantendo o terminal interativo para
# os prompts (stdin não é redirecionado).
exec > >(tee -a "$LOG_FILE") 2> >(tee -a "$LOG_FILE" >&2)

echo "============================================================"
echo " Mighty DOOM Revival - instalador VPS"
echo " Log desta execução: $LOG_FILE"
echo "============================================================"

STEP="inicialização"
on_error() {
  local exit_code=$?
  echo ""
  echo "============================================================"
  echo "[ERRO] Falha na etapa: $STEP"
  echo "Comando que falhou: ${BASH_COMMAND}"
  echo "Linha: ${BASH_LINENO[0]} em $0"
  echo "Código de saída: $exit_code"
  echo "Log completo desta execução: $LOG_FILE"
  echo "============================================================"
  exit "$exit_code"
}
trap on_error ERR

step() {
  STEP="$1"
  echo ""
  echo "==== $1 ===="
}

fail() {
  echo "[ERRO] $1" >&2
  echo "Log completo desta execução: $LOG_FILE" >&2
  exit "${2:-1}"
}

# ---------------------------------------------------------------------------
step "Verificações iniciais"

if [[ $EUID -ne 0 ]]; then
  fail "Execute como root (sudo ./scripts/install.sh). É necessário para instalar pacotes, abrir as portas 80/443 e criar os serviços systemd."
fi

if ! command -v apt-get >/dev/null 2>&1; then
  fail "Este instalador suporta apenas distros baseadas em Debian/Ubuntu (apt-get não encontrado). Instale manualmente Node.js 22.5+, Caddy e configure o systemd."
fi

RUN_USER="${SUDO_USER:-root}"
echo "Usuário que vai rodar o serviço: $RUN_USER"
echo "Diretório do repositório: $ROOT"

# ---------------------------------------------------------------------------
step "Instalando dependências base do sistema (apt)"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends curl ca-certificates gnupg openssl python3 lsb-release

# ---------------------------------------------------------------------------
step "Verificando/instalando Node.js (precisa de node:sqlite, Node 22.5+)"

NEED_NODE_INSTALL=1
if command -v node >/dev/null 2>&1; then
  if node -e "const s=require('node:sqlite'); const db=new s.DatabaseSync(':memory:'); db.exec('select 1'); db.close()" >/dev/null 2>&1; then
    NEED_NODE_INSTALL=0
  fi
fi

if [[ "$NEED_NODE_INSTALL" == "1" ]]; then
  echo "Instalando Node.js 24 LTS via NodeSource..."
  curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
  apt-get install -y nodejs
fi

node --version
node -e "const s=require('node:sqlite'); const db=new s.DatabaseSync(':memory:'); db.exec('select 1'); db.close(); console.log('node:sqlite OK')" \
  || fail "Node instalado não possui node:sqlite funcional."

# ---------------------------------------------------------------------------
step "Verificando/instalando Caddy (reverse proxy + HTTPS automático)"

if ! command -v caddy >/dev/null 2>&1; then
  apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  apt-get update -y
  apt-get install -y caddy
fi

caddy version

# ---------------------------------------------------------------------------
step "Preparando configuração do servidor"

cp -n "$SERVER_DIR/.env.example" "$SERVER_DIR/.env" 2>/dev/null || true
cp -n "$SERVER_DIR/config/revival.example.json" "$SERVER_DIR/config/revival.json" 2>/dev/null || true
cp -n "$SERVER_DIR/config/packs.example.json" "$SERVER_DIR/config/packs.json" 2>/dev/null || true
cp -n "$SERVER_DIR/config/events.example.json" "$SERVER_DIR/config/events.json" 2>/dev/null || true
mkdir -p "$SERVER_DIR/runtime" "$SERVER_DIR/data" "$DEPLOY_DIR/logs"

ENV_FILE="$SERVER_DIR/.env"

set_env_var() {
  local key="$1" value="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    echo "${key}=${value}" >> "$ENV_FILE"
  fi
}

get_env_var() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -n1 | cut -d= -f2- || true
}

# ---------------------------------------------------------------------------
step "Domínio HTTPS do Revival Server"

DEFAULT_DOMAIN="$(get_env_var PUBLIC_DOMAIN)"
DOMAIN="${DOMAIN:-}"

if [[ -z "$DOMAIN" ]]; then
  if [[ -t 0 ]]; then
    if [[ -n "$DEFAULT_DOMAIN" ]]; then
      read -rp "Domínio HTTPS do Revival (o mesmo que você vai usar no patcher) [$DEFAULT_DOMAIN]: " DOMAIN_INPUT
      DOMAIN="${DOMAIN_INPUT:-$DEFAULT_DOMAIN}"
    else
      read -rp "Domínio HTTPS do Revival (o mesmo que você vai usar no patcher, ex: d.seudominio.com.br): " DOMAIN
    fi
  elif [[ -n "$DEFAULT_DOMAIN" ]]; then
    DOMAIN="$DEFAULT_DOMAIN"
    echo "Sem terminal interativo; reutilizando domínio salvo: $DOMAIN"
  fi
fi

DOMAIN="$(echo "${DOMAIN:-}" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')"

if [[ -z "$DOMAIN" ]]; then
  fail "Nenhum domínio informado. Rode de novo em um terminal interativo, ou passe DOMAIN=seu.dominio.com sudo -E ./scripts/install.sh"
fi

if ! [[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$ ]]; then
  fail "Domínio inválido: '$DOMAIN'. Use um hostname (ex: d.seudominio.com.br), sem http(s):// e sem caminho."
fi

echo "Domínio configurado: $DOMAIN"
set_env_var PUBLIC_DOMAIN "$DOMAIN"

# Checagem opcional de DNS (não bloqueia o deploy: propagação pode demorar).
if command -v python3 >/dev/null 2>&1; then
  RESOLVED_IP="$(python3 -c "import socket,sys
try:
    print(socket.gethostbyname(sys.argv[1]))
except Exception:
    print('')" "$DOMAIN" 2>/dev/null || true)"
  PUBLIC_IP="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)"
  if [[ -n "$RESOLVED_IP" && -n "$PUBLIC_IP" && "$RESOLVED_IP" != "$PUBLIC_IP" ]]; then
    echo "[AVISO] $DOMAIN resolve para $RESOLVED_IP, mas o IP público deste servidor parece ser $PUBLIC_IP."
    echo "[AVISO] Se o DNS ainda não propagou, a emissão do certificado abaixo pode falhar temporariamente."
  fi
fi

# ---------------------------------------------------------------------------
step "Ajustando server/.env para produção atrás do Caddy"

set_env_var HOST 127.0.0.1
set_env_var PORT 8080
set_env_var TRUST_PROXY true

CURRENT_TOKEN="$(get_env_var REVIVAL_ADMIN_TOKEN)"
if [[ -z "$CURRENT_TOKEN" || "$CURRENT_TOKEN" == "change-me" ]]; then
  NEW_TOKEN="$(openssl rand -hex 32)"
  set_env_var REVIVAL_ADMIN_TOKEN "$NEW_TOKEN"
  echo "REVIVAL_ADMIN_TOKEN gerado automaticamente (veja o resumo final)."
fi

# ---------------------------------------------------------------------------
step "GameData local (bootstrap opcional)"

if [[ ! -f "$SERVER_DIR/data/game-data.json" ]]; then
  echo "server/data/game-data.json ausente; tentando importar snapshot comunitário..."
  if ! python3 "$ROOT/scripts/fetch-community-gamedata.py"; then
    echo "[AVISO] Não foi possível baixar o GameData automaticamente."
    echo "[AVISO] O servidor sobe mesmo assim, mas /revival/health reportará game_data_loaded=false"
    echo "[AVISO] até você colocar um server/data/game-data.json válido e reiniciar o serviço."
  fi
else
  echo "server/data/game-data.json já existe; mantendo."
fi

# ---------------------------------------------------------------------------
step "Ajustando permissões"

chown -R "$RUN_USER":"$RUN_USER" "$SERVER_DIR/runtime" "$SERVER_DIR/data" "$SERVER_DIR/config" "$ENV_FILE" "$DEPLOY_DIR" 2>/dev/null || true

# ---------------------------------------------------------------------------
step "Rodando testes automatizados do servidor (gate de deploy)"

if ! (cd "$SERVER_DIR" && npm test); then
  fail "Os testes do servidor falharam. O deploy foi interrompido de propósito para não subir código quebrado. Veja o log acima para o teste que falhou."
fi

# ---------------------------------------------------------------------------
step "Instalando serviço systemd do Revival Server"

NODE_BIN="$(command -v node)"
SERVICE_NAME="mighty-doom-revival"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SERVER_LOG="$LOG_DIR/server.log"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Mighty DOOM Revival Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$SERVER_DIR
ExecStart=$NODE_BIN $SERVER_DIR/src/index.js
Restart=always
RestartSec=3
StandardOutput=append:$SERVER_LOG
StandardError=append:$SERVER_LOG

[Install]
WantedBy=multi-user.target
EOF

touch "$SERVER_LOG"
chown "$RUN_USER":"$RUN_USER" "$SERVER_LOG" 2>/dev/null || true

systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null
systemctl restart "$SERVICE_NAME"

verify_service_active() {
  local svc="$1"
  local tries=0
  while (( tries < 10 )); do
    if systemctl is-active --quiet "$svc"; then
      echo "[OK] $svc ativo."
      return 0
    fi
    sleep 1
    tries=$((tries + 1))
  done
  echo "[ERRO] Serviço $svc não está ativo." >&2
  echo "----- journalctl -u $svc (últimas 80 linhas) -----" >&2
  journalctl -u "$svc" -n 80 --no-pager >&2 || true
  echo "----------------------------------------------------" >&2
  return 1
}

verify_service_active "$SERVICE_NAME" || fail "O serviço $SERVICE_NAME não subiu. Veja o journalctl acima e $SERVER_LOG."

# ---------------------------------------------------------------------------
step "Configurando Caddy (proxy 127.0.0.1:8080 -> HTTPS público em $DOMAIN)"

CADDYFILE="/etc/caddy/Caddyfile"
cat > "$CADDYFILE" <<EOF
$DOMAIN {
	encode gzip
	reverse_proxy 127.0.0.1:8080
}
EOF

if ! caddy validate --config "$CADDYFILE" >>"$LOG_FILE" 2>&1; then
  fail "Caddyfile gerado é inválido. Veja $LOG_FILE para o erro completo do 'caddy validate'."
fi

# Libera 80/443 ANTES de reiniciar o Caddy: se o ufw estiver ativo e as portas
# ainda fechadas nesse momento, o primeiro desafio ACME (HTTP-01) do domínio
# real falha por conexão recusada.
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  echo "ufw ativo: liberando portas 80/tcp e 443/tcp..."
  ufw allow 80/tcp >/dev/null || true
  ufw allow 443/tcp >/dev/null || true
fi

systemctl enable caddy >/dev/null
systemctl restart caddy

verify_service_active "caddy" || fail "O serviço caddy não subiu. Veja o journalctl acima."

# ---------------------------------------------------------------------------
step "Validando saúde do servidor localmente (http://127.0.0.1:8080/revival/health)"

LOCAL_HEALTH="/tmp/mighty-doom-revival-health-local.json"
LOCAL_OK=0
for _ in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:8080/revival/health" -o "$LOCAL_HEALTH" 2>>"$LOG_FILE"; then
    LOCAL_OK=1
    break
  fi
  sleep 1
done

if [[ "$LOCAL_OK" != "1" ]]; then
  echo "----- journalctl -u $SERVICE_NAME (últimas 80 linhas) -----" >&2
  journalctl -u "$SERVICE_NAME" -n 80 --no-pager >&2 || true
  fail "O servidor Node não respondeu em http://127.0.0.1:8080/revival/health."
fi
cat "$LOCAL_HEALTH"
echo ""

# ---------------------------------------------------------------------------
step "Validando HTTPS público em https://$DOMAIN/revival/health (aguardando certificado Let's Encrypt)"

PUBLIC_HEALTH="/tmp/mighty-doom-revival-health-public.json"
PUBLIC_OK=0
for _ in $(seq 1 60); do
  if curl -fsS --max-time 10 "https://$DOMAIN/revival/health" -o "$PUBLIC_HEALTH" 2>>"$LOG_FILE"; then
    PUBLIC_OK=1
    break
  fi
  sleep 5
done

if [[ "$PUBLIC_OK" != "1" ]]; then
  echo "----- journalctl -u caddy (últimas 80 linhas) -----" >&2
  journalctl -u caddy -n 80 --no-pager >&2 || true
  fail "Não foi possível validar https://$DOMAIN/revival/health. Confira se o DNS de $DOMAIN aponta para o IP público deste servidor e se as portas 80/443 estão liberadas no firewall da VPS/provedor de nuvem (ex: AWS Security Group, painel da hospedagem)."
fi
cat "$PUBLIC_HEALTH"
echo ""

python3 - "$PUBLIC_HEALTH" <<'PYEOF' || fail "O health check público não é compatível com o patcher (client_version/api_version incorretos)."
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    payload = json.load(handle)

errors = []
if payload.get("ok") is not True:
    errors.append("campo ok não é true")
if payload.get("client_version") != "1.13.1":
    errors.append(f"client_version={payload.get('client_version')!r}; esperado '1.13.1'")
if payload.get("api_version") != "24.0.0":
    errors.append(f"api_version={payload.get('api_version')!r}; esperado '24.0.0'")

if errors:
    print("[ERRO] health incompatível com o patcher: " + "; ".join(errors))
    sys.exit(1)

if payload.get("game_data_loaded") is not True:
    print("[AVISO] game_data_loaded=false: coloque um server/data/game-data.json real e rode")
    print("[AVISO]   sudo systemctl restart mighty-doom-revival")
    print("[AVISO] antes de gerar o APK final com o patcher.")

print("Revival HTTPS validado: client_version/api_version compatíveis com o patcher.")
PYEOF

# ---------------------------------------------------------------------------
# Mantém só os 20 logs de instalação mais recentes.
ls -1t "$LOG_DIR"/install-*.log 2>/dev/null | tail -n +21 | xargs -r rm -f

echo ""
echo "============================================================"
echo " CONCLUÍDO: Mighty DOOM Revival está 100% no ar"
echo "============================================================"
echo "Domínio:                 https://$DOMAIN"
echo "Health check:             https://$DOMAIN/revival/health"
echo "Health local:              http://127.0.0.1:8080/revival/health"
echo ""
echo "REVIVAL_ADMIN_TOKEN atual: $(get_env_var REVIVAL_ADMIN_TOKEN)"
echo "(guarde este token; ele autoriza POST /revival/reload)"
echo ""
echo "Serviços systemd:"
echo "  systemctl status $SERVICE_NAME"
echo "  systemctl status caddy"
echo "  journalctl -u $SERVICE_NAME -f"
echo ""
echo "Logs:"
echo "  Instalação:  $LOG_FILE"
echo "  Servidor:    $SERVER_LOG"
echo ""
echo "Próximo passo (no Windows): rode scripts\\patch-apk.bat e informe"
echo "'$DOMAIN' quando ele perguntar o servidor."
echo ""
echo "Para atualizar depois de mudanças no código:"
echo "  git pull && sudo ./scripts/install.sh"
echo "============================================================"
