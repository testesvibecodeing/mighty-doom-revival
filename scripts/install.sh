#!/usr/bin/env bash
# Mighty DOOM Revival - instalador completo para VPS (Debian/Ubuntu)
#
# Uso:
#   git pull
#   sudo ./scripts/install.sh
#
# O script é idempotente: pode ser executado de novo a cada "git pull" para
# atualizar o servidor em produção. Ele instala o Node.js se faltar, escolhe
# um perfil de recursos conforme a RAM da VPS (1 GB / 4 GB / 8 GB ou mais),
# roda os testes automatizados como gate de deploy, sobe o servidor via
# systemd já otimizado para o perfil escolhido e ativa HTTPS automático
# (Let's Encrypt) para o domínio informado. O proxy é escolhido sozinho:
# reaproveita um nginx que já exista na VPS (seguro para VPS compartilhada)
# ou instala/usa o Caddy quando não há nginx.
#
# SEGURO PARA VPS COMPARTILHADA: se Node.js e/ou Caddy já estiverem
# instalados (por exemplo, por outro projeto na mesma VPS), este instalador
# NUNCA os reinstala nem os marca como "nossos". Ele também nunca sobrescreve
# /etc/caddy/Caddyfile - só acrescenta uma linha "import" (se ainda não
# houver) e escreve o domínio deste projeto em um arquivo próprio dentro de
# /etc/caddy/conf.d/, sem tocar em blocos de outros domínios/projetos. Cada
# decisão de posse (o que é "nosso" e pode ser removido depois) é tomada uma
# única vez, na primeira execução, e fica registrada permanentemente em
# deploy/.install-state para o par deste script, scripts/uninstall.sh, usar.
#
# Para desfazer só o que pertence a este projeto (sem afetar outros projetos
# na mesma VPS), veja scripts/uninstall.sh.
#
# Toda a execução é registrada em deploy/logs/install-<timestamp>.log, com
# uma seção "OWNERSHIP" para cada decisão sobre o que pertence a este
# projeto e o que foi preservado por já pertencer a outra coisa.

if [ -z "${BASH_VERSION:-}" ]; then
  echo "[ERRO] Execute este script com bash: sudo bash scripts/install.sh" >&2
  exit 1
fi

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_DIR="$ROOT/server"
DEPLOY_DIR="$ROOT/deploy"
LOG_DIR="$DEPLOY_DIR/logs"
STATE_FILE="$DEPLOY_DIR/.install-state"
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
echo ""
echo "Este instalador é seguro para VPS compartilhada com outros projetos:"
echo "  - Detecta o reverse proxy: se já existe um nginx servindo 80/443"
echo "    (de outros projetos), o Revival vira apenas MAIS UM site dele em"
echo "    arquivo próprio + certbot; senão instala/usa o Caddy. Nunca briga"
echo "    pelas portas nem edita sites de outros projetos."
echo "  - Pergunta (ou detecta sozinho) o perfil de recursos da VPS:"
echo "    1gb / 4gb / 8gb+ - o serviço systemd nasce otimizado para ele."
echo "  - Só assume posse de pacotes (Node.js/Caddy/certbot) se ele mesmo"
echo "    instalar porque estavam ausentes. Se já existiam, ficam marcados"
echo "    como 'não é deste projeto' e scripts/uninstall.sh nunca os remove."
echo "  - Cada decisão de posse é registrada permanentemente em:"
echo "      $STATE_FILE"
echo "    e reaproveitada nas próximas execuções (git pull && install.sh)."
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

# Registro persistente de posse (deploy/.install-state): guarda, para sempre,
# se cada dependência de sistema (Node.js, pacote Caddy, ...) foi instalada
# por ESTE instalador ou já existia na VPS antes dele (ex: outro projeto).
# Uma vez decidido, o valor nunca é reavaliado em execuções futuras - assim
# scripts/uninstall.sh sabe com segurança o que pode remover.
[[ -f "$STATE_FILE" ]] || : > "$STATE_FILE"
# shellcheck disable=SC1090
source "$STATE_FILE"

set_state() {
  local key="$1" value="$2"
  if grep -q "^${key}=" "$STATE_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$STATE_FILE"
  else
    echo "${key}=${value}" >> "$STATE_FILE"
  fi
  export "${key}=${value}"
}

state_decided() {
  grep -q "^${1}=" "$STATE_FILE" 2>/dev/null
}

ownership_label() {
  case "${!1:-}" in
    1) echo "SIM - pertence a este projeto (uninstall.sh pode remover)" ;;
    0) echo "NÃO - já existia antes/pertence a outra coisa (uninstall.sh nunca remove)" ;;
    *) echo "não se aplica" ;;
  esac
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

if ! state_decided NODE_INSTALLED_BY_SCRIPT; then
  if [[ "$NEED_NODE_INSTALL" == "1" ]]; then
    echo "[OWNERSHIP] Node.js compatível ausente nesta VPS: será instalado agora e passa a pertencer a este projeto."
    set_state NODE_INSTALLED_BY_SCRIPT 1
  else
    echo "[OWNERSHIP] Node.js compatível já estava instalado nesta VPS antes deste projeto: NÃO é nosso, uninstall.sh nunca vai removê-lo."
    set_state NODE_INSTALLED_BY_SCRIPT 0
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
step "Detectando o reverse proxy desta VPS (nginx compartilhado ou Caddy)"

# VPS compartilhada: se um nginx já está servindo 80/443 para outros projetos,
# o Revival vira apenas MAIS UM site dele (arquivo próprio + certbot), em vez
# de brigar pelas portas. O Caddy só é usado quando não há nginx na VPS.
PROXY_KIND=""
if systemctl is-active --quiet nginx 2>/dev/null; then
  PROXY_KIND="nginx"
  echo "nginx ativo nesta VPS (possivelmente servindo outros projetos):"
  echo "  o Revival será apenas mais um site dele, em arquivo próprio."
elif systemctl is-active --quiet caddy 2>/dev/null; then
  PROXY_KIND="caddy"
  echo "Caddy ativo nesta VPS: o Revival será mais um domínio dele (arquivo próprio)."
elif command -v nginx >/dev/null 2>&1; then
  PROXY_KIND="nginx"
  echo "nginx instalado (inativo): será habilitado para servir o Revival."
elif command -v caddy >/dev/null 2>&1; then
  PROXY_KIND="caddy"
  echo "Caddy instalado (inativo): será habilitado para servir o Revival."
else
  # Nenhum dos dois instalado: antes de instalar, garantir que 80/443 não
  # pertencem a outro serviço desconhecido desta VPS.
  PORT80_LISTENER="$(ss -ltnp 2>/dev/null | awk '$4 ~ /:80$/  {print; exit}')"
  PORT443_LISTENER="$(ss -ltnp 2>/dev/null | awk '$4 ~ /:443$/ {print; exit}')"
  if [[ -n "$PORT80_LISTENER$PORT443_LISTENER" ]]; then
    echo "----- quem escuta em 80/443 nesta VPS -----"
    [[ -n "$PORT80_LISTENER" ]] && echo "$PORT80_LISTENER"
    [[ -n "$PORT443_LISTENER" ]] && echo "$PORT443_LISTENER"
    fail "As portas 80/443 já estão ocupadas por um serviço que não é nginx nem Caddy. Decida qual proxy esta VPS usa (ou desative o serviço acima) antes de rodar o instalador de novo."
  fi
  PROXY_KIND="caddy"
  echo "Nenhum proxy instalado: o Caddy será instalado (leve, HTTPS automático)."
fi
echo "Reverse proxy escolhido: $PROXY_KIND"
set_state PROXY_KIND "$PROXY_KIND"

if [[ "$PROXY_KIND" == "caddy" ]]; then
  CADDY_ALREADY_PRESENT=1
  command -v caddy >/dev/null 2>&1 || CADDY_ALREADY_PRESENT=0

  if ! state_decided CADDY_PACKAGE_INSTALLED_BY_SCRIPT; then
    if [[ "$CADDY_ALREADY_PRESENT" == "0" ]]; then
      echo "[OWNERSHIP] Pacote 'caddy' ausente nesta VPS: será instalado agora e passa a pertencer a este projeto."
      set_state CADDY_PACKAGE_INSTALLED_BY_SCRIPT 1
    else
      echo "[OWNERSHIP] Pacote 'caddy' já estava instalado nesta VPS (pode ser de outro projeto): NÃO é nosso, uninstall.sh nunca vai remover o pacote."
      set_state CADDY_PACKAGE_INSTALLED_BY_SCRIPT 0
    fi
  fi

  if [[ "$CADDY_ALREADY_PRESENT" == "0" ]]; then
    apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
      | gpg --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
      | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
    apt-get update -y
    apt-get install -y caddy
  fi

  caddy version
fi

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
step "Ajustando server/.env para produção atrás do reverse proxy"

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
step "Perfil de recursos da VPS (otimização para a RAM disponível)"

# Três perfis: 1gb (VPS pequena, até ~3 GB de RAM total), 4gb (média) e
# 8gb+ (grande). O perfil define o heap do Node e os limites do systemd, de
# modo que o Revival dê o melhor desempenho possível SEM estrangular o resto
# da VPS (nginx, outros projetos, cache do sistema).
TOTAL_MEM_MB="$(( $(awk '/^MemTotal/ {print $2}' /proc/meminfo) / 1024 ))"
CPU_COUNT="$(nproc 2>/dev/null || echo 1)"

if (( TOTAL_MEM_MB < 3000 )); then
  DETECTED_PROFILE="1gb"
elif (( TOTAL_MEM_MB < 7000 )); then
  DETECTED_PROFILE="4gb"
else
  DETECTED_PROFILE="8gb"
fi

echo "Detectado: ${TOTAL_MEM_MB} MB de RAM, ${CPU_COUNT} CPU(s) -> perfil '${DETECTED_PROFILE}'"

# Prioridade: variável de ambiente RAM_PROFILE > perfil salvo no .install-state
# > menu interativo (com o detectado como padrão) > detectado.
if [[ -z "${RAM_PROFILE:-}" ]]; then
  RAM_PROFILE="${RAM_PROFILE_STATE:-}"
fi

if [[ -z "$RAM_PROFILE" && -t 0 ]]; then
  echo ""
  echo "Perfis disponíveis:"
  echo "  [1] 1gb  - VPS pequena (~1-2 GB RAM): heap 256MB, limites rígidos de RAM"
  echo "  [2] 4gb  - VPS média   (~4 GB RAM):    heap 768MB, limites folgados"
  echo "  [3] 8gb+ - VPS grande  (8 GB+ RAM):    heap 2GB, limites amplos"
  read -rp "Escolha o perfil para esta VPS [${DETECTED_PROFILE}]: " PROFILE_INPUT
  RAM_PROFILE="${PROFILE_INPUT:-$DETECTED_PROFILE}"
fi

if [[ -z "$RAM_PROFILE" ]]; then
  RAM_PROFILE="$DETECTED_PROFILE"
fi

case "$RAM_PROFILE" in
  1|1gb|low)  RAM_PROFILE="1gb" ;;
  2|4gb|mid)  RAM_PROFILE="4gb" ;;
  3|8gb|8gb+|high) RAM_PROFILE="8gb" ;;
  *) fail "Perfil inválido: '$RAM_PROFILE'. Use 1gb, 4gb ou 8gb." ;;
esac

case "$RAM_PROFILE" in
  1gb)
    HEAP_MB=256;  MEM_HIGH="384M";  MEM_MAX="512M";  TASKS_MAX=256;  UV_TP=2
    ;;
  4gb)
    HEAP_MB=768;  MEM_HIGH="1G";    MEM_MAX="1536M"; TASKS_MAX=512;  UV_TP=4
    ;;
  8gb)
    HEAP_MB=2048; MEM_HIGH="2G";    MEM_MAX="3G";    TASKS_MAX=1024; UV_TP=4
    ;;
esac

echo "Perfil escolhido: $RAM_PROFILE"
echo "  Node --max-old-space-size=${HEAP_MB}MB (heap do V8)"
echo "  systemd MemoryHigh=$MEM_HIGH / MemoryMax=$MEM_MAX / TasksMax=$TASKS_MAX"
echo "  UV_THREADPOOL=$UV_TP (pools de I/O concorrentes com ${CPU_COUNT} CPU(s))"
set_state RAM_PROFILE_STATE "$RAM_PROFILE"

# Em VPS pequena, swap é o que separa um pico de memória de um OOM-kill.
if [[ "$RAM_PROFILE" == "1gb" ]]; then
  SWAP_MB="$(( $(awk '/^SwapTotal/ {print $2}' /proc/meminfo) / 1024 ))"
  if (( SWAP_MB == 0 )); then
    echo "[AVISO] Esta VPS NÃO tem swap. Em uma VPS de ~1 GB isso costuma causar"
    echo "[AVISO] OOM-kill sob pico. Considere criar 1-2 GB de swap, ex.:"
    echo "[AVISO]   fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile"
    echo "[AVISO]   (echo '/swapfile none swap sw 0 0' >> /etc/fstab)"
  else
    echo "Swap presente: ${SWAP_MB} MB (bom para picos de memória)."
  fi
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
# Otimização por perfil de recursos (RAM_PROFILE=$RAM_PROFILE, ver install.sh):
# heap do Node calibrado para a RAM da VPS e limites do cgroup que protegem o
# resto da máquina sem estrangular o servidor do jogo.
Environment=UV_THREADPOOL=$UV_TP
ExecStart=$NODE_BIN --max-old-space-size=$HEAP_MB $SERVER_DIR/src/index.js
MemoryHigh=$MEM_HIGH
MemoryMax=$MEM_MAX
TasksMax=$TASKS_MAX
LimitNOFILE=16384
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
# Libera 80/443 ANTES de (re)configurar o proxy: se o ufw estiver ativo e as
# portas ainda fechadas nesse momento, o primeiro desafio ACME (HTTP-01) do
# domínio real falha por conexão recusada. Isso é global (não some no
# uninstall): outros serviços/domínios da VPS também costumam precisar de
# 80/443.
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  echo "ufw ativo: liberando portas 80/tcp e 443/tcp..."
  ufw allow 80/tcp >/dev/null || true
  ufw allow 443/tcp >/dev/null || true
fi

if [[ "$PROXY_KIND" == "nginx" ]]; then
# ---------------------------------------------------------------------------
step "Configurando nginx (proxy 127.0.0.1:8080 -> HTTPS público em $DOMAIN)"

# IMPORTANTE (VPS compartilhada): este bloco NUNCA edita o nginx.conf global
# nem sites de outros projetos. O Revival ganha UM arquivo próprio, e o
# certbot --nginx edita SOMENTE esse arquivo ao ativar o HTTPS.
if [[ -f /etc/nginx/sites-available/mighty-doom-revival ]]; then
  NGINX_SITE_FILE="/etc/nginx/sites-available/mighty-doom-revival"
  NGINX_ENABLED_LINK="/etc/nginx/sites-enabled/mighty-doom-revival"
elif [[ -d /etc/nginx/sites-enabled ]]; then
  NGINX_SITE_FILE="/etc/nginx/sites-available/mighty-doom-revival"
  NGINX_ENABLED_LINK="/etc/nginx/sites-enabled/mighty-doom-revival"
else
  NGINX_SITE_FILE="/etc/nginx/conf.d/mighty-doom-revival.conf"
  NGINX_ENABLED_LINK=""
fi

CERT_RENEWAL_CONF="/etc/letsencrypt/renewal/$DOMAIN.conf"

if [[ -f "$NGINX_SITE_FILE" ]] && grep -q "ssl_certificate" "$NGINX_SITE_FILE" && [[ -f "$CERT_RENEWAL_CONF" ]]; then
  echo "Site nginx do Revival já existe com HTTPS ativo (gerenciado pelo certbot): mantendo $NGINX_SITE_FILE intacto."
else
  echo "[OWNERSHIP] Escrevendo somente o site deste projeto em $NGINX_SITE_FILE - nenhum outro site/domínio do nginx é tocado."
  cat > "$NGINX_SITE_FILE" <<EOF
# Site do Mighty DOOM Revival (criado por scripts/install.sh).
# O HTTPS é ativado abaixo pelo certbot --nginx, que edita APENAS este arquivo.
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
fi

if [[ -n "$NGINX_ENABLED_LINK" && ! -e "$NGINX_ENABLED_LINK" ]]; then
  ln -s "$NGINX_SITE_FILE" "$NGINX_ENABLED_LINK"
fi
set_state NGINX_SITE_FILE "$NGINX_SITE_FILE"
set_state DOMAIN "$DOMAIN"

if ! nginx -t >>"$LOG_FILE" 2>&1; then
  fail "Configuração do nginx ficou inválida depois de escrever $NGINX_SITE_FILE. Veja $LOG_FILE para o erro completo do 'nginx -t'."
fi

if systemctl is-active --quiet nginx; then
  systemctl reload nginx
  echo "[OK] nginx recarregado (reload; conexões de outros sites não caem)."
else
  systemctl enable nginx >/dev/null
  systemctl restart nginx
fi

verify_service_active "nginx" || fail "O serviço nginx não subiu. Veja o journalctl acima."

# --- certbot: emissor/renovador do certificado Let's Encrypt ---
if ! command -v certbot >/dev/null 2>&1; then
  if ! state_decided CERTBOT_INSTALLED_BY_SCRIPT; then
    echo "[OWNERSHIP] certbot ausente nesta VPS: será instalado agora e passa a pertencer a este projeto."
    set_state CERTBOT_INSTALLED_BY_SCRIPT 1
  fi
  apt-get install -y --no-install-recommends certbot python3-certbot-nginx
else
  if ! state_decided CERTBOT_INSTALLED_BY_SCRIPT; then
    echo "[OWNERSHIP] certbot já existia nesta VPS (pode ser de outro projeto): NÃO é nosso, uninstall.sh nunca vai removê-lo."
    set_state CERTBOT_INSTALLED_BY_SCRIPT 0
  fi
fi
certbot --version

if [[ -f "$CERT_RENEWAL_CONF" ]]; then
  echo "Certificado Let's Encrypt de $DOMAIN já existe; pulando emissão (a renovação é automática; ver etapa abaixo)."
else
  echo "Emitindo certificado Let's Encrypt para $DOMAIN (certbot --nginx --redirect)..."
  if ! certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --redirect --register-unsafely-without-email >>"$LOG_FILE" 2>&1; then
    tail -n 30 "$LOG_FILE" >&2 || true
    fail "O certbot não conseguiu emitir o certificado de $DOMAIN. Confira se o DNS do domínio aponta para o IP público desta VPS e se as portas 80/443 estão liberadas no firewall da VPS/provedor."
  fi
  nginx -t >>"$LOG_FILE" 2>&1 && systemctl reload nginx
fi

# --- renovação automática ---
# O certificado só se renova sozinho quando existe um timer/cron dele na VPS.
# Se não houver NENHUM, instalamos um cron dedicado (nosso; o uninstall.sh
# pode remover). Se já houver qualquer mecanismo (nosso ou de outro projeto),
# não tocamos nele.
if systemctl list-timers --all --no-legend 2>/dev/null | grep -q 'certbot'; then
  echo "Timer do certbot já existe nesta VPS: renovação já é automática, nada a instalar."
elif [[ -f /etc/cron.d/certbot-renew ]] || crontab -l 2>/dev/null | grep -q 'certbot renew'; then
  echo "Já existe automação de renovação do certbot nesta VPS (cron): nada a instalar."
  if ! state_decided CERTBOT_RENEW_CRON_INSTALLED_BY_SCRIPT; then
    echo "[OWNERSHIP] Essa automação não foi criada por nós (ou é compartilhada com outros certificados da VPS): fica marcada como NÃO nossa e o uninstall.sh não vai removê-la."
    set_state CERTBOT_RENEW_CRON_INSTALLED_BY_SCRIPT 0
  fi
else
  CERTBOT_BIN="$(command -v certbot)"
  cat > /etc/cron.d/certbot-renew <<EOF
# Renovação Let's Encrypt (criado por mighty-doom-revival scripts/install.sh).
# Roda 2x ao dia; o certbot só troca o certificado quando perto de expirar.
0 3,15 * * * root $CERTBOT_BIN renew --quiet --deploy-hook "systemctl reload nginx"
EOF
  chmod 644 /etc/cron.d/certbot-renew
  echo "[OK] Cron de renovação instalado: /etc/cron.d/certbot-renew (2x ao dia)."
  set_state CERTBOT_RENEW_CRON_INSTALLED_BY_SCRIPT 1
fi

else
# ---------------------------------------------------------------------------
step "Configurando Caddy (proxy 127.0.0.1:8080 -> HTTPS público em $DOMAIN)"

# IMPORTANTE (VPS compartilhada): este bloco NUNCA sobrescreve o Caddyfile
# existente. Cada projeto/domínio ganha seu próprio arquivo em
# /etc/caddy/conf.d/*.caddy, importado uma única vez a partir do Caddyfile
# principal. Assim vários projetos podem dividir o mesmo Caddy na mesma VPS
# sem um apagar a configuração do outro.
CADDYFILE="/etc/caddy/Caddyfile"
CADDY_CONF_DIR="/etc/caddy/conf.d"
CADDY_SITE_FILE="$CADDY_CONF_DIR/mighty-doom-revival.caddy"
mkdir -p "$CADDY_CONF_DIR"

if [[ ! -f "$CADDYFILE" ]]; then
  echo "[OWNERSHIP] /etc/caddy/Caddyfile não existia: criando um Caddyfile global mínimo que só importa $CADDY_CONF_DIR/*.caddy."
  cat > "$CADDYFILE" <<EOF
# Caddyfile global desta VPS. Cada site/domínio deve ficar em seu próprio
# arquivo dentro de $CADDY_CONF_DIR/ (importado abaixo), nunca editado
# direto aqui, para vários projetos compartilharem o mesmo Caddy sem
# conflito entre si.
import $CADDY_CONF_DIR/*.caddy
EOF
  if ! state_decided CADDYFILE_CREATED_BY_SCRIPT; then
    set_state CADDYFILE_CREATED_BY_SCRIPT 1
  fi
else
  if ! state_decided CADDYFILE_CREATED_BY_SCRIPT; then
    echo "[OWNERSHIP] /etc/caddy/Caddyfile já existia nesta VPS (não foi criado por nós; pode ter blocos de outros projetos). Este instalador NUNCA sobrescreve esse arquivo."
    set_state CADDYFILE_CREATED_BY_SCRIPT 0
  fi
  if grep -qE "^[[:space:]]*import[[:space:]]+${CADDY_CONF_DIR}/\*\.caddy[[:space:]]*\$" "$CADDYFILE"; then
    echo "[OWNERSHIP] Caddyfile já importa $CADDY_CONF_DIR/*.caddy; nada a alterar nele."
  else
    echo "[OWNERSHIP] Acrescentando só a linha 'import $CADDY_CONF_DIR/*.caddy' ao final do Caddyfile existente (100% do conteúdo atual é preservado)."
    {
      echo ""
      echo "# Acrescentado por mighty-doom-revival scripts/install.sh (idempotente):"
      echo "# permite sites em arquivos separados sem editar este Caddyfile."
      echo "import $CADDY_CONF_DIR/*.caddy"
    } >> "$CADDYFILE"
    if ! state_decided CADDY_IMPORT_LINE_ADDED_BY_SCRIPT; then
      set_state CADDY_IMPORT_LINE_ADDED_BY_SCRIPT 1
    fi
  fi
fi

echo "[OWNERSHIP] Escrevendo somente o site deste projeto em $CADDY_SITE_FILE - nenhum outro arquivo/domínio é tocado."
cat > "$CADDY_SITE_FILE" <<EOF
$DOMAIN {
	encode gzip
	reverse_proxy 127.0.0.1:8080
}
EOF
set_state CADDY_SITE_FILE "$CADDY_SITE_FILE"
set_state DOMAIN "$DOMAIN"

if ! caddy validate --config "$CADDYFILE" >>"$LOG_FILE" 2>&1; then
  fail "Configuração do Caddy ficou inválida depois de escrever $CADDY_SITE_FILE. Veja $LOG_FILE para o erro completo do 'caddy validate'."
fi

systemctl enable caddy >/dev/null
if systemctl is-active --quiet caddy; then
  echo "Caddy já estava ativo (pode estar servindo outros domínios): usando 'reload' em vez de 'restart' para não derrubar as conexões deles."
  systemctl reload caddy
else
  systemctl restart caddy
fi

verify_service_active "caddy" || fail "O serviço caddy não subiu. Veja o journalctl acima."

fi  # fim do branch do proxy (nginx | caddy)

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
  echo "----- journalctl -u $PROXY_KIND (últimas 80 linhas) -----" >&2
  journalctl -u "$PROXY_KIND" -n 80 --no-pager >&2 || true
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
step "Gerando link temporário de upload do APK (válido por 24 horas)"

# O token abaixo habilita o envio do APK pelo navegador em
# https://$DOMAIN/upload/<token>. O servidor valida o arquivo
# (runtime/upload-token.json) a cada requisição e aplica a expiração de 24h
# sozinho, sem cron. Executar o instalador de novo gera um token novo e
# invalida automaticamente qualquer link anterior.
UPLOAD_TOKEN="$(openssl rand -hex 32)"
UPLOAD_CREATED_AT="$(date +%s)"
UPLOAD_EXPIRES_AT="$(( UPLOAD_CREATED_AT + 24 * 3600 ))"
UPLOAD_TOKEN_FILE="$SERVER_DIR/runtime/upload-token.json"

mkdir -p "$SERVER_DIR/runtime"
printf '{\n  "token": "%s",\n  "expires_at": %d,\n  "created_at": %d\n}\n' \
  "$UPLOAD_TOKEN" "$UPLOAD_EXPIRES_AT" "$UPLOAD_CREATED_AT" > "$UPLOAD_TOKEN_FILE"
chown "$RUN_USER":"$RUN_USER" "$UPLOAD_TOKEN_FILE" 2>/dev/null || true
chmod 600 "$UPLOAD_TOKEN_FILE"

UPLOAD_EXPIRES_LABEL="$(date -d "@$UPLOAD_EXPIRES_AT" '+%d/%m/%Y %H:%M %Z' 2>/dev/null || true)"
if [[ -z "$UPLOAD_EXPIRES_LABEL" ]]; then
  UPLOAD_EXPIRES_LABEL="$(date -r "$UPLOAD_EXPIRES_AT" '+%d/%m/%Y %H:%M' 2>/dev/null || echo "daqui a 24 horas")"
fi

# ---------------------------------------------------------------------------
# Mantém só os 20 logs de instalação mais recentes.
ls -1t "$LOG_DIR"/install-*.log 2>/dev/null | tail -n +21 | xargs -r rm -f

echo ""
echo "============================================================"
echo " CONCLUÍDO: Mighty DOOM Revival está 100% no ar"
echo "============================================================"
echo "Domínio:                 https://$DOMAIN"
echo "Site (abre no domínio):   https://$DOMAIN/"
echo "Health check:             https://$DOMAIN/revival/health"
echo "Health local:              http://127.0.0.1:8080/revival/health"
echo "Perfil de recursos:       $RAM_PROFILE (heap ${HEAP_MB}MB, MemoryMax $MEM_MAX, TasksMax $TASKS_MAX)"
echo "Reverse proxy:            $PROXY_KIND"
echo ""
echo "------------------------------------------------------------"
echo " UPLOAD DO APK PELO NAVEGADOR (opcional)"
echo "------------------------------------------------------------"
echo "Para publicar o APK patcheado no botão de download do site,"
echo "abra este link TEMPORÁRIO e arraste o arquivo .apk:"
echo ""
echo "  https://$DOMAIN/upload/$UPLOAD_TOKEN"
echo ""
echo "  Válido até: $UPLOAD_EXPIRES_LABEL (24 horas)"
echo "  (links gerados por instalações anteriores foram invalidados)"
echo ""
echo "Quer ELIMINAR este link de upload imediatamente, antes das 24h"
echo "(uso opcional)? Basta abrir o link abaixo no navegador:"
echo ""
echo "  https://$DOMAIN/upload-cancel/$UPLOAD_TOKEN"
echo ""
echo "  Depois de eliminado, ninguém consegue enviar ou substituir o"
echo "  APK sem rodar este instalador de novo. O APK já publicado"
echo "  continua no ar normalmente em:"
echo "  https://$DOMAIN/download/mighty-doom-revival.apk"
echo ""
echo "REVIVAL_ADMIN_TOKEN atual: $(get_env_var REVIVAL_ADMIN_TOKEN)"
echo "(guarde este token; ele autoriza POST /revival/reload)"
echo ""
echo "Serviços systemd:"
echo "  systemctl status $SERVICE_NAME"
echo "  systemctl status $PROXY_KIND"
echo "  journalctl -u $SERVICE_NAME -f"
echo ""
echo "Logs:"
echo "  Instalação:  $LOG_FILE"
echo "  Servidor:    $SERVER_LOG"
echo ""
echo "------------------------------------------------------------"
echo "Resumo de propriedade (VPS compartilhada com outros projetos):"
echo "  Node.js instalado por este instalador:        $(ownership_label NODE_INSTALLED_BY_SCRIPT)"
if [[ "$PROXY_KIND" == "nginx" ]]; then
echo "  Site nginx deste projeto ($NGINX_SITE_FILE): sempre nosso"
echo "  Certificado Let's Encrypt de $DOMAIN:         sempre nosso (domínio do projeto)"
echo "  Pacote 'certbot' instalado por este instalador: $(ownership_label CERTBOT_INSTALLED_BY_SCRIPT)"
echo "  Cron de renovação /etc/cron.d/certbot-renew:  $(ownership_label CERTBOT_RENEW_CRON_INSTALLED_BY_SCRIPT)"
else
echo "  Pacote 'caddy' instalado por este instalador:  $(ownership_label CADDY_PACKAGE_INSTALLED_BY_SCRIPT)"
echo "  /etc/caddy/Caddyfile criado por este instalador: $(ownership_label CADDYFILE_CREATED_BY_SCRIPT)"
echo "  Linha 'import' acrescentada por este instalador: $(ownership_label CADDY_IMPORT_LINE_ADDED_BY_SCRIPT)"
echo "  Site do Caddy deste projeto ($CADDY_SITE_FILE): sempre nosso"
fi
echo "  Serviço systemd $SERVICE_NAME:              sempre nosso"
echo ""
echo "  Registro completo salvo em: $STATE_FILE"
echo "  Para remover só o que é deste projeto (sem afetar outros projetos"
echo "  na mesma VPS): sudo ./scripts/uninstall.sh"
echo "------------------------------------------------------------"
echo ""
echo "Próximo passo (no Windows): rode scripts\\patch-apk.bat e informe"
echo "'$DOMAIN' quando ele perguntar o servidor."
echo ""
echo "Para atualizar depois de mudanças no código:"
echo "  git pull && sudo ./scripts/install.sh"
echo "============================================================"
