#!/usr/bin/env bash
# Mighty DOOM Revival - desinstalador para VPS (Debian/Ubuntu)
#
# Uso:
#   sudo ./scripts/uninstall.sh                   # remove só o que é deste projeto
#   sudo ./scripts/uninstall.sh -y                 # não pede confirmação
#   sudo ./scripts/uninstall.sh --purge-packages   # também remove Node.js/Caddy
#                                                   # via apt, mas SÓ os que
#                                                   # scripts/install.sh registrou
#                                                   # como instalados por ele
#   sudo ./scripts/uninstall.sh --purge-data       # também apaga server/.env,
#                                                   # server/config/*.json,
#                                                   # server/data/ e server/runtime/
#                                                   # (inclui progresso de jogadores)
#
# SEGURO PARA VPS COMPARTILHADA: este é o par de scripts/install.sh e só
# remove o que aquele script registrou como pertencente a este projeto em
# deploy/.install-state. Pacotes de sistema (Node.js, Caddy) e o
# /etc/caddy/Caddyfile compartilhado só são tocados se esse registro
# confirmar que foram criados/instalados por nós; caso contrário ficam
# marcados como "preservados" e o motivo é explicado no log. Blocos de
# outros domínios/projetos no Caddy nunca são removidos ou editados.
#
# Toda a execução é registrada em deploy/logs/uninstall-<timestamp>.log.

if [ -z "${BASH_VERSION:-}" ]; then
  echo "[ERRO] Execute este script com bash: sudo bash scripts/uninstall.sh" >&2
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
LOG_FILE="$LOG_DIR/uninstall-$TS.log"
: > "$LOG_FILE"

# Espelha tudo (stdout + stderr) no log, mantendo o terminal interativo para
# o prompt de confirmação (stdin não é redirecionado).
exec > >(tee -a "$LOG_FILE") 2> >(tee -a "$LOG_FILE" >&2)

echo "============================================================"
echo " Mighty DOOM Revival - desinstalador VPS"
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

ownership_note() {
  case "${!1:-}" in
    1) echo "instalado por este projeto (removido com --purge-packages)" ;;
    0) echo "já existia antes deste projeto / não é nosso (nunca removido)" ;;
    *) echo "desconhecido (sem deploy/.install-state; tratado como não-nosso por segurança)" ;;
  esac
}

# ---------------------------------------------------------------------------
step "Lendo opções"

YES=0
PURGE_PACKAGES=0
PURGE_DATA=0
for arg in "$@"; do
  case "$arg" in
    -y|--yes) YES=1 ;;
    --purge-packages) PURGE_PACKAGES=1 ;;
    --purge-data) PURGE_DATA=1 ;;
    -h|--help)
      cat <<'EOF'
Uso: sudo ./scripts/uninstall.sh [opções]

  -y, --yes           Não pede confirmação antes de remover.
  --purge-packages    Também remove Node.js/Caddy via apt, mas só os que
                       scripts/install.sh registrou como instalados por ele
                       (deploy/.install-state). Se já existiam antes deste
                       projeto (ou pertencem a outro projeto na mesma VPS),
                       são preservados mesmo com esta flag.
  --purge-data        Também apaga server/.env, server/config/*.json
                       gerados, server/data/ e server/runtime/ (inclui o
                       banco SQLite com progresso de jogadores). Sem esta
                       flag, esses arquivos são preservados.
  -h, --help          Mostra esta ajuda.
EOF
      exit 0
      ;;
    *)
      fail "Opção desconhecida: '$arg' (use --help para ver as opções)."
      ;;
  esac
done

# ---------------------------------------------------------------------------
step "Verificações iniciais"

if [[ $EUID -ne 0 ]]; then
  fail "Execute como root (sudo ./scripts/uninstall.sh)."
fi

SERVICE_NAME="mighty-doom-revival"
CADDY_SITE_FILE="/etc/caddy/conf.d/mighty-doom-revival.caddy"

if [[ -f "$STATE_FILE" ]]; then
  echo "Carregando registro de propriedade desta instalação: $STATE_FILE"
  # shellcheck disable=SC1090
  source "$STATE_FILE"
  [[ -n "${CADDY_SITE_FILE:-}" ]] || CADDY_SITE_FILE="/etc/caddy/conf.d/mighty-doom-revival.caddy"
else
  echo "[AVISO] $STATE_FILE não encontrado (instalação feita antes desta versão do"
  echo "[AVISO] install.sh, ou em outra máquina). Prosseguindo no modo mais seguro"
  echo "[AVISO] possível: só removo o que é inequivocamente deste projeto (o serviço"
  echo "[AVISO] systemd e o site próprio do Caddy). Pacotes de sistema (Node.js/Caddy)"
  echo "[AVISO] NÃO serão removidos, mesmo com --purge-packages."
fi

DOMAIN="${DOMAIN:-}"
if [[ -z "$DOMAIN" && -f "$SERVER_DIR/.env" ]]; then
  DOMAIN="$(grep -E '^PUBLIC_DOMAIN=' "$SERVER_DIR/.env" 2>/dev/null | head -n1 | cut -d= -f2- || true)"
fi

echo ""
echo "------------------------------------------------------------"
echo "O que este desinstalador VAI remover (pertence a este projeto):"
echo "  - Serviço systemd: $SERVICE_NAME (/etc/systemd/system/${SERVICE_NAME}.service)"
echo "  - Site do Caddy deste projeto: $CADDY_SITE_FILE"
if [[ -n "$DOMAIN" ]]; then
  echo "    (domínio https://$DOMAIN vai parar de responder depois de remover)"
fi
echo ""
echo "O que este desinstalador NÃO vai tocar, a menos que você use as flags:"
echo "  - Pacote Node.js (apt):        $(ownership_note NODE_INSTALLED_BY_SCRIPT) [--purge-packages]"
echo "  - Pacote 'caddy' (apt):        $(ownership_note CADDY_PACKAGE_INSTALLED_BY_SCRIPT) [--purge-packages]"
echo "  - /etc/caddy/Caddyfile: nunca é apagado nem sobrescrito. Se a linha"
echo "    'import .../conf.d/*.caddy' foi acrescentada por nós, ela permanece"
echo "    (é genérica e inofensiva; outros projetos também podem usá-la)."
echo "  - Qualquer outro bloco/domínio já configurado em /etc/caddy/Caddyfile ou"
echo "    em /etc/caddy/conf.d/*.caddy de outros projetos: sempre intocado."
echo "  - Regras de firewall (portas 80/443): outros serviços podem precisar delas."
echo "  - server/.env, server/config/*.json, server/data/, server/runtime/ e os"
echo "    logs em $LOG_DIR: preservados [--purge-data remove os 4 primeiros]"
echo "------------------------------------------------------------"
echo ""

if [[ "$YES" != "1" ]]; then
  if [[ -t 0 ]]; then
    PROMPT_DOMAIN="${DOMAIN:-o Revival Server configurado nesta VPS}"
    read -rp "Confirma a desinstalação acima? Isso tira $PROMPT_DOMAIN do ar. [y/N] " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
      echo "Cancelado pelo usuário. Nada foi removido."
      exit 1
    fi
  else
    fail "Sem terminal interativo para confirmar. Rode de novo com --yes (ou -y) para prosseguir sem prompt."
  fi
fi

# ---------------------------------------------------------------------------
step "Removendo serviço systemd $SERVICE_NAME"

if systemctl list-unit-files 2>/dev/null | grep -q "^${SERVICE_NAME}\.service"; then
  systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  systemctl disable "$SERVICE_NAME" 2>/dev/null || true
  rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
  systemctl daemon-reload
  echo "[OK] Serviço $SERVICE_NAME parado, desabilitado e removido."
else
  echo "Serviço $SERVICE_NAME não encontrado; nada a fazer."
fi

# ---------------------------------------------------------------------------
step "Removendo o site deste projeto do Caddy"

if [[ -f "$CADDY_SITE_FILE" ]]; then
  rm -f "$CADDY_SITE_FILE"
  echo "[OK] Removido $CADDY_SITE_FILE."

  if command -v caddy >/dev/null 2>&1 && systemctl is-active --quiet caddy 2>/dev/null; then
    if [[ -f /etc/caddy/Caddyfile ]] && caddy validate --config /etc/caddy/Caddyfile >>"$LOG_FILE" 2>&1; then
      systemctl reload caddy
      echo "[OK] Caddy recarregado (reload, sem afetar outros domínios que ele sirva)."
    else
      echo "[AVISO] Não recarreguei o Caddy automaticamente. Confira manualmente:"
      echo "[AVISO]   caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy"
    fi
  fi
else
  echo "$CADDY_SITE_FILE não encontrado; nada a fazer."
fi

echo "[OWNERSHIP] /etc/caddy/Caddyfile e qualquer outro arquivo em /etc/caddy/conf.d/ NÃO foram tocados."

# ---------------------------------------------------------------------------
step "Pacotes de sistema (Node.js / Caddy)"

if [[ "$PURGE_PACKAGES" == "1" ]]; then
  if [[ "${NODE_INSTALLED_BY_SCRIPT:-}" == "1" ]]; then
    echo "Removendo Node.js (registro confirma que foi instalado por este instalador)..."
    apt-get remove -y nodejs || echo "[AVISO] Falha ao remover nodejs; remova manualmente se quiser (apt-get remove nodejs)."
  else
    echo "Node.js preservado: não há registro de que foi instalado por este instalador."
  fi

  if [[ "${CADDY_PACKAGE_INSTALLED_BY_SCRIPT:-}" == "1" ]]; then
    OTHER_CADDY_SITES="$(find /etc/caddy/conf.d -maxdepth 1 -name '*.caddy' -not -name "$(basename "$CADDY_SITE_FILE")" 2>/dev/null || true)"
    if [[ -n "$OTHER_CADDY_SITES" ]]; then
      echo "[AVISO] Existem outros arquivos em /etc/caddy/conf.d/ (provavelmente de outros projetos):"
      echo "$OTHER_CADDY_SITES" | sed 's/^/[AVISO]   /'
      echo "[AVISO] Preservando o pacote 'caddy' mesmo com --purge-packages, para não derrubar esses outros sites."
    else
      echo "Removendo pacote 'caddy' (registro confirma que foi instalado por este instalador; nenhum outro site em /etc/caddy/conf.d/)..."
      apt-get remove -y caddy || echo "[AVISO] Falha ao remover caddy; remova manualmente se quiser (apt-get remove caddy)."
    fi
  else
    echo "Caddy preservado: não há registro de que foi instalado por este instalador."
  fi
else
  echo "Flag --purge-packages não usada: Node.js e Caddy preservados (mesmo os que este instalador possa ter instalado)."
fi

# ---------------------------------------------------------------------------
step "Dados/config locais do repositório"

if [[ "$PURGE_DATA" == "1" ]]; then
  echo "Apagando server/.env, server/config/*.json gerados, server/data/ e server/runtime/..."
  rm -f "$SERVER_DIR/.env" \
        "$SERVER_DIR/config/revival.json" \
        "$SERVER_DIR/config/packs.json" \
        "$SERVER_DIR/config/events.json"
  rm -rf "$SERVER_DIR/data" "$SERVER_DIR/runtime"
  echo "[OK] Dados e configuração locais removidos."
else
  echo "Flag --purge-data não usada: server/.env, server/config/*.json, server/data/ e"
  echo "server/runtime/ preservados (podem conter progresso de jogadores)."
fi

# ---------------------------------------------------------------------------
step "Atualizando registro de propriedade"

if [[ "$PURGE_PACKAGES" == "1" && "$PURGE_DATA" == "1" && -f "$STATE_FILE" ]]; then
  echo "Desinstalação completa (pacotes + dados): removendo $STATE_FILE."
  echo "Uma próxima instalação nesta VPS vai decidir a posse do zero."
  rm -f "$STATE_FILE"
else
  if [[ -f "$STATE_FILE" ]]; then
    echo "Mantendo $STATE_FILE (ainda há itens preservados que uma futura"
    echo "reinstalação/desinstalação deve continuar reconhecendo como já decididos)."
  fi
fi

# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
echo " Desinstalação concluída"
echo "============================================================"
echo "Removido (sempre deste projeto):"
echo "  - Serviço systemd $SERVICE_NAME"
echo "  - Site do Caddy: $CADDY_SITE_FILE"
if [[ "$PURGE_PACKAGES" == "1" ]]; then
  echo "  - Pacotes de sistema: ver detalhes acima (só os que eram nossos)"
fi
if [[ "$PURGE_DATA" == "1" ]]; then
  echo "  - server/.env, server/config/*.json, server/data/, server/runtime/"
fi
echo ""
echo "Preservado:"
echo "  - /etc/caddy/Caddyfile e qualquer outro domínio/projeto configurado nele."
if [[ "$PURGE_PACKAGES" != "1" ]]; then
  echo "  - Node.js e o pacote 'caddy' (use --purge-packages para remover os que são nossos)."
fi
if [[ "$PURGE_DATA" != "1" ]]; then
  echo "  - server/.env, server/config/*.json, server/data/, server/runtime/ (use --purge-data)."
fi
echo "  - Regras de firewall (portas 80/443)."
echo "  - Logs em $LOG_DIR (histórico; apague manualmente se quiser)."
echo ""
echo "Log completo desta execução: $LOG_FILE"
echo "============================================================"
