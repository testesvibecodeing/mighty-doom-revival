#!/usr/bin/env bash
# Mighty DOOM Revival - instalador completo para VPS (Debian/Ubuntu)
#
# Uso:
#   sudo ./scripts/install.sh
#
# O próprio instalador faz o "git pull" no começo (e se reexecuta caso o pull
# tenha trocado este arquivo). Alterações locais em arquivos versionados fazem
# ele PULAR o pull, nunca descartar o trabalho; SKIP_GIT_PULL=1 desliga a
# atualização e instala o código como está no disco.
#
# O script é idempotente: pode ser executado de novo a cada atualização para
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
# Super Admin do painel (/slayer): o instalador consulta o banco do servidor
# e lista o(s) e-mail(is) já cadastrado(s) como admin (senha preservada); se
# ainda não existe nenhum, cadastra o primeiro acesso (e-mail + senha gerados
# e exibidos no resumo final). Sempre gera também um link temporário de 10
# minutos, de uso único, para trocar e-mail e senha do Super Admin caso a
# pessoa esqueça.
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
SERVICE_NAME="mighty-doom-revival"
mkdir -p "$LOG_DIR"

TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/install-$TS.log"
: > "$LOG_FILE"

# ---------------------------------------------------------------------------
# Apresentação (cores, largura do terminal e molduras do resumo final).
#
# Precisa ser decidido AQUI, antes do redirecionamento para o log: depois dele
# o stdout vira um pipe para o tee e '[ -t 1 ]' nunca mais é verdadeiro, ou
# seja, o script nunca saberia que está falando com um terminal de verdade.
STDOUT_IS_TTY=0
if [[ -t 1 ]]; then
  STDOUT_IS_TTY=1
fi

TERM_COLS=0
TERM_COLORS=0
if [[ "$STDOUT_IS_TTY" == "1" ]]; then
  TERM_COLS="$(tput cols 2>/dev/null || echo 0)"
  TERM_COLORS="$(tput colors 2>/dev/null || echo 0)"
fi
[[ "$TERM_COLS"   =~ ^[0-9]+$ ]] || TERM_COLS=0
[[ "$TERM_COLORS" =~ ^[0-9]+$ ]] || TERM_COLORS=0

# Cor só quando há terminal de verdade; NO_COLOR e TERM=dumb desligam tudo.
UI_COLOR=0
if [[ "$STDOUT_IS_TTY" == "1" && -z "${NO_COLOR:-}" && "${TERM:-dumb}" != "dumb" ]]; then
  UI_COLOR=1
fi

if [[ "$UI_COLOR" == "1" ]]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
  if (( TERM_COLORS >= 256 )); then
    C_ACCENT=$'\033[38;5;202m'; C_TITLE=$'\033[1;38;5;208m'
    C_OK=$'\033[38;5;77m';      C_WARN=$'\033[38;5;214m'
    C_ERR=$'\033[1;38;5;196m';  C_LINK=$'\033[1;38;5;45m'
    C_KEY=$'\033[38;5;245m';    C_SECRET=$'\033[1;38;5;220m'
    C_CMD=$'\033[38;5;151m'
  else
    C_ACCENT=$'\033[31m';    C_TITLE=$'\033[1;31m'
    C_OK=$'\033[32m';        C_WARN=$'\033[33m'
    C_ERR=$'\033[1;31m';     C_LINK=$'\033[1;36m'
    C_KEY=$'\033[90m';       C_SECRET=$'\033[1;33m'
    C_CMD=$'\033[36m'
  fi
else
  C_RESET=''; C_BOLD=''; C_DIM=''; C_ACCENT=''; C_TITLE=''
  C_OK='';    C_WARN=''; C_ERR=''; C_LINK=''; C_KEY=''
  C_SECRET=''; C_CMD=''
fi

# Largura das molduras: acompanha o terminal, com piso e teto para o texto não
# ficar espremido em janela estreita nem largo demais para ler em monitor 4K.
UI_WIDTH=72
if (( TERM_COLS > 0 )); then
  UI_WIDTH=$(( TERM_COLS - 2 ))
  if (( UI_WIDTH > 88 )); then UI_WIDTH=88; fi
  if (( UI_WIDTH < 56 )); then UI_WIDTH=56; fi
fi
UI_KEY_W=24

# As cores viram lixo dentro do arquivo de log; este filtro tira os códigos
# ANSI só do que é gravado, mantendo o terminal colorido.
UI_SED_U=''
if printf '' | sed -u '' >/dev/null 2>&1; then
  UI_SED_U='-u'
fi
strip_ansi() {
  sed ${UI_SED_U:+-u} $'s/\033\\[[0-9;]*[a-zA-Z]//g'
}

# Espelha tudo (stdout + stderr) no log, mantendo o terminal interativo para
# os prompts (stdin não é redirecionado).
if [[ "$UI_COLOR" == "1" ]]; then
  exec > >(tee >(strip_ansi >> "$LOG_FILE")) 2> >(tee >(strip_ansi >> "$LOG_FILE") >&2)
else
  exec > >(tee -a "$LOG_FILE") 2> >(tee -a "$LOG_FILE" >&2)
fi

# --- Blocos de saída (molduras, ícones e alinhamento) ----------------------
#
# ÍCONES: só glifos de texto puro (sem propriedade Emoji no Unicode), para o
# terminal nunca trocá-los por um desenho colorido de largura dupla, que
# quebraria o alinhamento. Cada um tem um significado fixo no instalador:
#
#   ✓ feito/no ar      ✗ falhou           ▲ atenção, não impede seguir
#   ● decisão de posse ○ não é nosso      ▸ link para abrir no navegador
#   » prompt/passo     • item de lista    $ comando para copiar e colar
#
# --- Blocos do resumo final ------------------------------------------------
# Contagem de caracteres à prova de locale: em locale C o bash conta BYTES, e
# uma única palavra acentuada ("SERVIÇO") desalinharia a moldura inteira. Aqui
# forçamos byte-mode e contamos só os bytes-líder do UTF-8 (os bytes 0x80-0xBF
# são continuação de caractere, nunca um caractere novo).
ui_len() (
  export LC_ALL=C
  local s="$1" lead
  lead="${s//[$'\x80'-$'\xbf']/}"
  printf '%s' "${#lead}"
)

ui_repeat() {
  local char="$1" count="$2" out=''
  while (( count-- > 0 )); do out+="$char"; done
  printf '%s' "$out"
}

ui_pad() {
  local text="$1" width="$2" fill
  fill=$(( width - $(ui_len "$text") ))
  if (( fill < 0 )); then fill=0; fi
  printf '%s%*s' "$text" "$fill" ''
}

# Linha interna da moldura: mede o texto SEM cor e imprime o texto COM cor.
ui_box_row() {
  local plain="$1" colored="$2" pad
  pad=$(( UI_WIDTH - 2 - $(ui_len "$plain") ))
  if (( pad < 0 )); then pad=0; fi
  printf '%s║%s%s%*s%s║%s\n' "$C_ACCENT" "$C_RESET" "$colored" "$pad" '' "$C_ACCENT" "$C_RESET"
}

# Moldura de abertura/fechamento: ui_banner "<ícone>" "<cor do ícone>" "título" "subtítulo"
ui_banner() {
  local icon="$1" icon_color="$2" title="$3" sub="${4:-}" line
  line="$(ui_repeat '═' $(( UI_WIDTH - 2 )))"
  echo ""
  printf '%s╔%s╗%s\n' "$C_ACCENT" "$line" "$C_RESET"
  ui_box_row "  $icon  $title" "  ${icon_color}${icon}${C_RESET}  ${C_BOLD}${title}${C_RESET}"
  if [[ -n "$sub" ]]; then
    ui_box_row "     $sub" "     ${C_LINK}${sub}${C_RESET}"
  fi
  printf '%s╚%s╝%s\n' "$C_ACCENT" "$line" "$C_RESET"
}

# Cabeçalho de seção: barra + título + régua até a borda, com etiqueta
# opcional encostada à direita (ex: "opcional").
ui_section() {
  local title="$1" badge="${2:-}" right='' n fill
  if [[ -n "$badge" ]]; then right=" ${badge} ──"; fi
  n=$(( UI_WIDTH - 3 - $(ui_len "$title") - $(ui_len "$right") ))
  if (( n < 2 )); then n=2; fi
  fill="$(ui_repeat '─' "$n")"
  echo ""
  printf '%s▌%s %s%s%s %s%s%s%s\n' \
    "$C_ACCENT" "$C_RESET" "$C_TITLE" "$title" "$C_RESET" "$C_DIM" "$fill" "$right" "$C_RESET"
}

ui_row() {
  printf '   %s%s%s%s\n' "$C_KEY" "$(ui_pad "$1" "$UI_KEY_W")" "$C_RESET" "$2"
}

# Igual ao ui_row, mas com o valor destacado (segredos: senha, token).
ui_row_hi() {
  printf '   %s%s%s%s%s%s\n' "$C_KEY" "$(ui_pad "$1" "$UI_KEY_W")" "$C_RESET" "$C_SECRET" "$2" "$C_RESET"
}

# Rótulo + caminho longo em duas linhas (não estoura a largura da moldura).
ui_path() {
  printf '   %s%s%s\n' "$C_KEY" "$1" "$C_RESET"
  printf '     %s%s%s\n' "$C_CMD" "$2" "$C_RESET"
}

ui_text()   { printf '   %s\n' "$1"; }
ui_note()   { printf '   %s%s%s\n' "$C_DIM" "$1" "$C_RESET"; }
ui_sub()    { printf '     %s%s%s\n' "$C_DIM" "$1" "$C_RESET"; }
ui_bullet() { printf '   %s•%s %s\n' "$C_ACCENT" "$C_RESET" "$1"; }
ui_link()   { printf '   %s▸%s %s%s%s\n' "$C_ACCENT" "$C_RESET" "$C_LINK" "$1" "$C_RESET"; }
ui_secret() { printf '   %s%s%s\n' "$C_SECRET" "$1" "$C_RESET"; }

ui_cmd() {
  local cmd="$1" indent="${2:-3}"
  printf '%*s%s$%s %s%s%s\n' "$indent" '' "$C_DIM" "$C_RESET" "$C_CMD" "$cmd" "$C_RESET"
}

# Passo numerado; ui_step_cont continua o mesmo passo alinhado ao texto.
ui_step() {
  printf '   %s%s.%s %s\n' "$C_TITLE" "$1" "$C_RESET" "$2"
}
ui_step_cont() { printf '      %s\n' "$1"; }

# Posse de uma dependência de sistema, lida do .install-state: verde = criado
# por este instalador e removível; âmbar = já existia na VPS e é intocável
# pelo uninstall.sh.
ui_own() {
  local label="$1" value="${!2:-}" mark
  case "$value" in
    1) mark="${C_OK}✓${C_RESET} deste projeto ${C_DIM}· uninstall.sh remove${C_RESET}" ;;
    0) mark="${C_WARN}○${C_RESET} já existia ${C_DIM}· uninstall.sh nunca remove${C_RESET}" ;;
    *) mark="${C_DIM}— não se aplica${C_RESET}" ;;
  esac
  printf '   %s%s%s%s\n' "$C_KEY" "$(ui_pad "$label" 28)" "$C_RESET" "$mark"
}

ui_own_ours() {
  printf '   %s%s%s%s✓%s sempre nosso\n' "$C_KEY" "$(ui_pad "$1" 28)" "$C_RESET" "$C_OK" "$C_RESET"
  if [[ -n "${2:-}" ]]; then
    ui_sub "$2"
  fi
}

# --- Mensagens do passo a passo --------------------------------------------
# Um ícone por significado, sempre na primeira coluna, para o olho achar na
# rolagem o que exige ação. As variantes _cont continuam a mesma mensagem
# alinhadas sob o texto, sem repetir o ícone.
ok()        { printf '%s✓%s %s\n'  "$C_OK"     "$C_RESET" "$1"; }
ok_cont()   { printf '  %s\n' "$1"; }
warn()      { printf '%s▲%s %s\n'  "$C_WARN"   "$C_RESET" "$1"; }
warn_cont() { printf '  %s\n' "$1"; }
err()       { printf '%s✗ %s%s\n'  "$C_ERR"    "$1" "$C_RESET" >&2; }
err_cont()  { printf '%s  %s%s\n'  "$C_ERR"    "$1" "$C_RESET" >&2; }
info()      { printf '%s·%s %s\n'  "$C_ACCENT" "$C_RESET" "$1"; }
info_cont() { printf '  %s%s%s\n'  "$C_DIM"    "$1" "$C_RESET"; }

# Decisão de posse (o que é deste projeto e o que já existia na VPS): fica em
# tom secundário porque é registro, não ação — mas com ícone próprio, já que é
# o que o uninstall.sh vai obedecer depois.
own() {
  printf '%s●%s %s%s%s\n' "$C_LINK" "$C_RESET" "$C_DIM" "$1" "$C_RESET"
}
own_cont() { printf '  %s%s%s\n' "$C_DIM" "$1" "$C_RESET"; }

# Saída crua de outro programa (JSON do health, journalctl, versões): recuada
# e apagada, para não competir com as mensagens do instalador.
raw_header() {
  printf '  %s── %s %s%s\n' "$C_DIM" "$1" "$(ui_repeat '─' 6)" "$C_RESET"
}
raw_block() {
  local line
  # '|| [[ -n "$line" ]]': resposta HTTP não termina em newline, e sem isso o
  # read descartaria justamente a última linha (o JSON inteiro do health).
  while IFS= read -r line || [[ -n "$line" ]]; do
    printf '  %s%s%s\n' "$C_DIM" "$line" "$C_RESET"
  done
}

# Texto do prompt interativo: o "»" marca o que espera resposta.
ask() {
  printf '%s»%s %s' "$C_ACCENT" "$C_RESET" "$1"
}

STEP="inicialização"
on_error() {
  local exit_code=$?
  # Tudo num bloco só, redirecionado de uma vez: stdout e stderr passam por
  # dois 'tee' independentes e sairiam intercalados, picotando a moldura.
  {
    echo ""
    printf '%s%s%s\n' "$C_ERR" "$(ui_repeat '═' "$UI_WIDTH")" "$C_RESET"
    printf '%s✗ FALHOU na etapa: %s%s\n' "$C_ERR" "$STEP" "$C_RESET"
    echo ""
    ui_row "Comando"         "${BASH_COMMAND}"
    ui_row "Linha"           "${BASH_LINENO[0]} em $0"
    ui_row "Código de saída" "$exit_code"
    echo ""
    ui_path "Log completo desta execução" "$LOG_FILE"
    printf '%s%s%s\n' "$C_ERR" "$(ui_repeat '═' "$UI_WIDTH")" "$C_RESET"
  } >&2
  exit "$exit_code"
}
trap on_error ERR

STEP_COUNT=0
step() {
  STEP="$1"
  STEP_COUNT=$((STEP_COUNT + 1))
  echo ""
  printf '%s%s%s\n' "$C_DIM" "$(ui_repeat '─' "$UI_WIDTH")" "$C_RESET"
  printf '%s▌%s %s[%02d]%s %s%s%s\n' \
    "$C_ACCENT" "$C_RESET" "$C_ACCENT" "$STEP_COUNT" "$C_RESET" "$C_TITLE" "$1" "$C_RESET"
}

fail() {
  err "$1"
  err_cont "Log completo desta execução: $LOG_FILE"
  exit "${2:-1}"
}

ui_banner "»" "$C_ACCENT" "MIGHTY DOOM REVIVAL · instalador VPS" ""
ui_path "Log desta execução" "$LOG_FILE"
echo ""
ui_text "Seguro para VPS compartilhada com outros projetos:"
ui_bullet "Detecta o reverse proxy: se já existe um nginx servindo 80/443"
ui_sub    "(de outros projetos), o Revival vira apenas MAIS UM site dele"
ui_sub    "em arquivo próprio + certbot; senão instala/usa o Caddy. Nunca"
ui_sub    "briga pelas portas nem edita sites de outros projetos."
ui_bullet "Pergunta (ou detecta sozinho) o perfil de recursos da VPS:"
ui_sub    "1gb / 4gb / 8gb+ — o serviço systemd nasce otimizado para ele."
ui_bullet "Só assume posse de pacotes (Node.js/Caddy/certbot) se ele mesmo"
ui_sub    "instalar porque estavam ausentes. Se já existiam, ficam marcados"
ui_sub    "como 'não é deste projeto' e scripts/uninstall.sh nunca os remove."
ui_bullet "Cada decisão de posse (●) é registrada permanentemente em:"
ui_sub    "$STATE_FILE"
ui_sub    "e reaproveitada nas próximas execuções."

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

# ---------------------------------------------------------------------------
step "Verificações iniciais"

if [[ $EUID -ne 0 ]]; then
  fail "Execute como root (sudo ./scripts/install.sh). É necessário para instalar pacotes, abrir as portas 80/443 e criar os serviços systemd."
fi

if ! command -v apt-get >/dev/null 2>&1; then
  fail "Este instalador suporta apenas distros baseadas em Debian/Ubuntu (apt-get não encontrado). Instale manualmente Node.js 22.5+, Caddy e configure o systemd."
fi

RUN_USER="${SUDO_USER:-root}"
ui_row "Usuário do serviço" "$RUN_USER"
ui_row "Repositório" "$ROOT"

# ---------------------------------------------------------------------------
step "Atualizando o código do repositório (git pull)"

# Rodar o instalador significa, na prática, "quero a versão nova no ar" — então
# ele mesmo busca o código antes de qualquer outra coisa. Regras:
#   - NUNCA descarta trabalho local: se há alteração em arquivo versionado, o
#     pull é pulado com aviso, não com --force/--reset.
#   - --ff-only: se o histórico divergiu, falha em vez de criar merge commit
#     silencioso numa VPS de produção.
#   - Sem prompt de credencial: um remoto privado falha na hora, em vez de
#     travar o deploy num prompt invisível esperando senha.
#   - Se o pull trocar este próprio arquivo, o script se reexecuta (o bash lê
#     o script em pedaços conforme executa; seguir com o arquivo trocado no
#     disco embaralha a execução).
git_repo() {
  git -c "safe.directory=$ROOT" -C "$ROOT" "$@"
}

GIT_PULL_CHANGED=0
GIT_HEAD_BEFORE=""
GIT_HEAD_AFTER=""

if [[ "${SKIP_GIT_PULL:-0}" == "1" ]]; then
  info "SKIP_GIT_PULL=1: atualização pulada a pedido; usando o código do disco."
elif ! command -v git >/dev/null 2>&1; then
  warn "git não está instalado nesta VPS: seguindo com o código que já está no disco."
elif ! git_repo rev-parse --git-dir >/dev/null 2>&1; then
  warn "$ROOT não é um clone git: seguindo com o código que já está no disco."
elif ! git_repo remote get-url origin >/dev/null 2>&1; then
  warn "O repositório não tem 'origin' configurado: nada para atualizar."
elif [[ -n "$(git_repo status --porcelain --untracked-files=no)" ]]; then
  warn "Há alterações locais em arquivos versionados. O pull foi PULADO para"
  warn_cont "não sobrescrever seu trabalho:"
  git_repo status --short --untracked-files=no | raw_block
  warn_cont "Resolva (git stash / git checkout -- <arquivo>) ou rode de novo"
  warn_cont "com SKIP_GIT_PULL=1 para instalar o código como está."
else
  GIT_BRANCH="$(git_repo rev-parse --abbrev-ref HEAD)"
  GIT_HEAD_BEFORE="$(git_repo rev-parse HEAD)"
  info "Branch '$GIT_BRANCH' em ${GIT_HEAD_BEFORE:0:7}; buscando atualizações no origin..."

  if GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="ssh -o BatchMode=yes" \
     git_repo pull --ff-only >>"$LOG_FILE" 2>&1; then
    GIT_HEAD_AFTER="$(git_repo rev-parse HEAD)"
    if [[ "$GIT_HEAD_BEFORE" == "$GIT_HEAD_AFTER" ]]; then
      ok "Já estava na versão mais recente ($GIT_BRANCH @ ${GIT_HEAD_BEFORE:0:7})."
    else
      GIT_PULL_CHANGED=1
      ok "Atualizado: ${GIT_HEAD_BEFORE:0:7} → ${GIT_HEAD_AFTER:0:7}"
      # -n 8 no próprio git (e não '| head -n 8'): com pipefail, o head fecharia
      # o cano antes da hora e o SIGPIPE no git derrubaria o instalador.
      git_repo log --oneline --no-decorate -n 8 "$GIT_HEAD_BEFORE..$GIT_HEAD_AFTER" | raw_block
    fi
  else
    warn "O 'git pull' falhou (histórico divergente, rede ou credencial)."
    warn_cont "Seguindo com o código que já está no disco. Detalhes no log:"
    warn_cont "$LOG_FILE"
  fi
fi

# O pull trouxe uma versão nova DESTE script? Reexecuta uma única vez, para o
# resto da instalação rodar sob o código novo do começo ao fim.
if [[ "$GIT_PULL_CHANGED" == "1" && "${REVIVAL_INSTALL_RESTARTED:-0}" != "1" ]]; then
  if ! git_repo diff --quiet "$GIT_HEAD_BEFORE" "$GIT_HEAD_AFTER" -- scripts/install.sh; then
    warn "O pull trouxe uma versão nova de scripts/install.sh."
    info "Reiniciando o instalador com o código novo (um log novo será aberto)."
    export REVIVAL_INSTALL_RESTARTED=1
    exec bash "$ROOT/scripts/install.sh" "$@"
  fi
fi

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
    own "Node.js compatível ausente nesta VPS: será instalado agora e passa a"
    own_cont "pertencer a este projeto."
    set_state NODE_INSTALLED_BY_SCRIPT 1
  else
    own "Node.js compatível já estava instalado nesta VPS antes deste projeto:"
    own_cont "NÃO é nosso, uninstall.sh nunca vai removê-lo."
    set_state NODE_INSTALLED_BY_SCRIPT 0
  fi
fi

if [[ "$NEED_NODE_INSTALL" == "1" ]]; then
  info "Instalando Node.js 24 LTS via NodeSource..."
  curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
  apt-get install -y nodejs
fi

ok "Node.js $(node --version) — $(command -v node)"
node -e "const s=require('node:sqlite'); const db=new s.DatabaseSync(':memory:'); db.exec('select 1'); db.close()" \
  || fail "Node instalado não possui node:sqlite funcional."
ok "node:sqlite funcional (o servidor usa o SQLite embutido do Node)"

# ---------------------------------------------------------------------------
step "Detectando o reverse proxy desta VPS (nginx compartilhado ou Caddy)"

# VPS compartilhada: se um nginx já está servindo 80/443 para outros projetos,
# o Revival vira apenas MAIS UM site dele (arquivo próprio + certbot), em vez
# de brigar pelas portas. O Caddy só é usado quando não há nginx na VPS.
PROXY_KIND=""
if systemctl is-active --quiet nginx 2>/dev/null; then
  PROXY_KIND="nginx"
  info "nginx ativo nesta VPS (possivelmente servindo outros projetos):"
  info_cont "o Revival será apenas mais um site dele, em arquivo próprio."
elif systemctl is-active --quiet caddy 2>/dev/null; then
  PROXY_KIND="caddy"
  info "Caddy ativo nesta VPS: o Revival será mais um domínio dele (arquivo próprio)."
elif command -v nginx >/dev/null 2>&1; then
  PROXY_KIND="nginx"
  info "nginx instalado (inativo): será habilitado para servir o Revival."
elif command -v caddy >/dev/null 2>&1; then
  PROXY_KIND="caddy"
  info "Caddy instalado (inativo): será habilitado para servir o Revival."
else
  # Nenhum dos dois instalado: antes de instalar, garantir que 80/443 não
  # pertencem a outro serviço desconhecido desta VPS.
  PORT80_LISTENER="$(ss -ltnp 2>/dev/null | awk '$4 ~ /:80$/  {print; exit}')"
  PORT443_LISTENER="$(ss -ltnp 2>/dev/null | awk '$4 ~ /:443$/ {print; exit}')"
  if [[ -n "$PORT80_LISTENER$PORT443_LISTENER" ]]; then
    raw_header "quem escuta em 80/443 nesta VPS"
    [[ -n "$PORT80_LISTENER" ]] && printf '%s\n' "$PORT80_LISTENER" | raw_block
    [[ -n "$PORT443_LISTENER" ]] && printf '%s\n' "$PORT443_LISTENER" | raw_block
    fail "As portas 80/443 já estão ocupadas por um serviço que não é nginx nem Caddy. Decida qual proxy esta VPS usa (ou desative o serviço acima) antes de rodar o instalador de novo."
  fi
  PROXY_KIND="caddy"
  info "Nenhum proxy instalado: o Caddy será instalado (leve, HTTPS automático)."
fi
ok "Reverse proxy escolhido: $PROXY_KIND"
set_state PROXY_KIND "$PROXY_KIND"

if [[ "$PROXY_KIND" == "caddy" ]]; then
  CADDY_ALREADY_PRESENT=1
  command -v caddy >/dev/null 2>&1 || CADDY_ALREADY_PRESENT=0

  if ! state_decided CADDY_PACKAGE_INSTALLED_BY_SCRIPT; then
    if [[ "$CADDY_ALREADY_PRESENT" == "0" ]]; then
      own "Pacote 'caddy' ausente nesta VPS: será instalado agora e passa a"
      own_cont "pertencer a este projeto."
      set_state CADDY_PACKAGE_INSTALLED_BY_SCRIPT 1
    else
      own "Pacote 'caddy' já estava instalado nesta VPS (pode ser de outro"
      own_cont "projeto): NÃO é nosso, uninstall.sh nunca vai remover o pacote."
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

  ok "Caddy $(caddy version | head -n1)"
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
      read -rp "$(ask "Domínio HTTPS do Revival (o mesmo que você vai usar no patcher) [$DEFAULT_DOMAIN]: ")" DOMAIN_INPUT
      DOMAIN="${DOMAIN_INPUT:-$DEFAULT_DOMAIN}"
    else
      read -rp "$(ask "Domínio HTTPS do Revival (o mesmo que você vai usar no patcher, ex: d.seudominio.com.br): ")" DOMAIN
    fi
  elif [[ -n "$DEFAULT_DOMAIN" ]]; then
    DOMAIN="$DEFAULT_DOMAIN"
    info "Sem terminal interativo; reutilizando domínio salvo: $DOMAIN"
  fi
fi

DOMAIN="$(echo "${DOMAIN:-}" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')"

if [[ -z "$DOMAIN" ]]; then
  fail "Nenhum domínio informado. Rode de novo em um terminal interativo, ou passe DOMAIN=seu.dominio.com sudo -E ./scripts/install.sh"
fi

if ! [[ "$DOMAIN" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$ ]]; then
  fail "Domínio inválido: '$DOMAIN'. Use um hostname (ex: d.seudominio.com.br), sem http(s):// e sem caminho."
fi

ok "Domínio configurado: $DOMAIN"
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
    warn "$DOMAIN resolve para $RESOLVED_IP, mas o IP público deste servidor"
    warn_cont "parece ser $PUBLIC_IP. Se o DNS ainda não propagou, a emissão do"
    warn_cont "certificado abaixo pode falhar temporariamente."
  fi
fi

# ---------------------------------------------------------------------------
step "Ajustando server/.env para produção atrás do reverse proxy"

set_env_var HOST 127.0.0.1
set_env_var PORT 8080
set_env_var TRUST_PROXY true

# Produção NÃO pode nascer em modo pesquisa (medido 2026-08-23: o health
# público rodava research_mode=true porque o .env copiado do exemplo mantém o
# default ligado). Em research, endpoint /game/* desconhecido responde ok()
# vazio — mascara rota faltante e reprova o gate --strict-research. A
# identidade de instância (server/src/instance.js) prova onde o tráfego do
# cliente aterrissou; sem ela o preflight do Studio recusa gerar o APK.
set_env_var RESEARCH_MODE false
set_env_var REVIVAL_INSTANCE_ID "$DOMAIN"
set_env_var REVIVAL_ENVIRONMENT production

CURRENT_TOKEN="$(get_env_var REVIVAL_ADMIN_TOKEN)"
if [[ -z "$CURRENT_TOKEN" || "$CURRENT_TOKEN" == "change-me" ]]; then
  NEW_TOKEN="$(openssl rand -hex 32)"
  set_env_var REVIVAL_ADMIN_TOKEN "$NEW_TOKEN"
  ok "REVIVAL_ADMIN_TOKEN gerado automaticamente (veja o resumo final)."
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

info "Detectado: ${TOTAL_MEM_MB} MB de RAM, ${CPU_COUNT} CPU(s) — perfil '${DETECTED_PROFILE}'"

# Prioridade: variável de ambiente RAM_PROFILE > perfil salvo no .install-state
# > menu interativo (com o detectado como padrão) > detectado.
if [[ -z "${RAM_PROFILE:-}" ]]; then
  RAM_PROFILE="${RAM_PROFILE_STATE:-}"
fi

if [[ -z "$RAM_PROFILE" && -t 0 ]]; then
  echo ""
  ui_text "Perfis disponíveis:"
  ui_row "[1] 1gb" "VPS pequena (~1-2 GB RAM) · heap 256MB, limites rígidos"
  ui_row "[2] 4gb" "VPS média (~4 GB RAM) · heap 768MB, limites folgados"
  ui_row "[3] 8gb+" "VPS grande (8 GB+ RAM) · heap 2GB, limites amplos"
  echo ""
  read -rp "$(ask "Escolha o perfil para esta VPS [${DETECTED_PROFILE}]: ")" PROFILE_INPUT
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

ok "Perfil escolhido: $RAM_PROFILE"
ui_row "heap do V8" "${HEAP_MB}MB (--max-old-space-size)"
ui_row "limites systemd" "MemoryHigh=$MEM_HIGH · MemoryMax=$MEM_MAX · TasksMax=$TASKS_MAX"
ui_row "UV_THREADPOOL" "$UV_TP (I/O concorrente com ${CPU_COUNT} CPU(s))"
set_state RAM_PROFILE_STATE "$RAM_PROFILE"

# Em VPS pequena, swap é o que separa um pico de memória de um OOM-kill.
if [[ "$RAM_PROFILE" == "1gb" ]]; then
  SWAP_MB="$(( $(awk '/^SwapTotal/ {print $2}' /proc/meminfo) / 1024 ))"
  if (( SWAP_MB == 0 )); then
    warn "Esta VPS NÃO tem swap. Em uma VPS de ~1 GB isso costuma causar"
    warn_cont "OOM-kill sob pico. Considere criar 1-2 GB de swap:"
    ui_cmd "fallocate -l 2G /swapfile && chmod 600 /swapfile" 2
    ui_cmd "mkswap /swapfile && swapon /swapfile" 2
    ui_cmd "echo '/swapfile none swap sw 0 0' >> /etc/fstab" 2
  else
    ok "Swap presente: ${SWAP_MB} MB (bom para picos de memória)."
  fi
fi

# ---------------------------------------------------------------------------
step "GameData local (bootstrap opcional)"

if [[ ! -f "$SERVER_DIR/data/game-data.json" ]]; then
  info "server/data/game-data.json ausente; tentando importar snapshot comunitário..."
  if ! python3 "$ROOT/scripts/fetch-community-gamedata.py"; then
    warn "Não foi possível baixar o GameData automaticamente."
    warn_cont "O servidor sobe mesmo assim, mas /revival/health vai reportar"
    warn_cont "game_data_loaded=false até você colocar um server/data/game-data.json"
    warn_cont "válido e reiniciar o serviço."
  fi
else
  ok "server/data/game-data.json já existe; mantendo."
fi

# ---------------------------------------------------------------------------
step "Ajustando permissões"

chown -R "$RUN_USER":"$RUN_USER" "$SERVER_DIR/runtime" "$SERVER_DIR/data" "$SERVER_DIR/config" "$ENV_FILE" "$DEPLOY_DIR" 2>/dev/null || true

# ---------------------------------------------------------------------------
step "Super Admin do painel (/slayer): e-mail cadastrado ou primeiro acesso"

# O painel web precisa de um Super Admin. A regra deste passo:
#   1. Consulta o banco do servidor (SQLite) pelos admins já existentes.
#   2. Se JÁ EXISTE admin: apenas lista o(s) e-mail(is) cadastrado(s) e NADA
#      é sobrescrito — a senha atual, mesmo que trocada pelo painel ou por
#      um link de recuperação anterior, é preservada.
#   3. Se NÃO existe admin: é o primeiro acesso — gera e-mail + senha, grava
#      em runtime/admin-credentials.json e o servidor consome no boot
#      (aplica uma vez e apaga o arquivo).
#   4. Sempre gera também um link temporário de 10 minutos para trocar
#      e-mail e senha do Super Admin (caso a pessoa esqueça), em
#      runtime/admin-recover-token.json — lido a cada requisição, sem
#      precisar reiniciar o serviço. Uso único: ao concluir a troca, o
#      servidor revoga o link na hora.
DB_PATH_REL="$(get_env_var DB_PATH)"
if [[ -n "$DB_PATH_REL" ]]; then
  if [[ "$DB_PATH_REL" == /* ]]; then
    ADMIN_DB="$DB_PATH_REL"
  else
    ADMIN_DB="$SERVER_DIR/${DB_PATH_REL#./}"
  fi
else
  ADMIN_DB="$SERVER_DIR/runtime/revival.sqlite3"
fi

ADMIN_EMAILS=""
ADMIN_DB_READ_OK=1
if [[ -f "$ADMIN_DB" ]]; then
  # Saída: um e-mail por linha (vazio = nenhum admin). Exit 3 = banco
  # ilegível (travado/corrompido): por segurança não mexemos em credenciais.
  ADMIN_EMAILS="$(node - "$ADMIN_DB" <<'NODEEOF' 2>>"$LOG_FILE"
const { DatabaseSync } = require('node:sqlite')
try {
  const db = new DatabaseSync(process.argv[2])
  let emails = []
  try {
    emails = db.prepare('SELECT email FROM users WHERE is_admin = 1 ORDER BY id').all()
      .map(r => (r.email && String(r.email).trim()) || '(sem e-mail)')
  } catch (e) {
    if (!/no such table/i.test(String(e.message))) throw e
  }
  db.close()
  if (emails.length) console.log(emails.join('\n'))
} catch (e) {
  console.error(String((e && e.message) || e))
  process.exit(3)
}
NODEEOF
  )" || ADMIN_DB_READ_OK=0
fi

ADMIN_FIRST_ACCESS=0
if [[ -f "$ADMIN_DB" && "$ADMIN_DB_READ_OK" != "1" ]]; then
  warn "Não foi possível ler o banco ($ADMIN_DB) para conferir os admins"
  warn_cont "existentes. Por segurança NENHUMA senha foi alterada agora; use o"
  warn_cont "link de recuperação abaixo se precisar trocá-la."
  ADMIN_EMAILS="(banco ilegível — nada foi alterado)"
elif [[ -z "$ADMIN_EMAILS" ]]; then
  ADMIN_FIRST_ACCESS=1
fi

if [[ "$ADMIN_FIRST_ACCESS" == "1" ]]; then
  ADMIN_EMAIL="$(get_env_var REVIVAL_ADMIN_EMAIL || true)"
  [[ -z "$ADMIN_EMAIL" ]] && ADMIN_EMAIL="admin@revival.local"
  if [[ -t 0 ]]; then
    read -rp "$(ask "E-mail do Super Admin do painel (primeiro acesso) [$ADMIN_EMAIL]: ")" ADMIN_EMAIL_INPUT
    [[ -n "${ADMIN_EMAIL_INPUT:-}" ]] && ADMIN_EMAIL="$ADMIN_EMAIL_INPUT"
  fi
  ADMIN_EMAIL="$(echo "$ADMIN_EMAIL" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')"
  ADMIN_PASSWORD="$(openssl rand -hex 12)"
  ADMIN_CREDENTIALS_FILE="$SERVER_DIR/runtime/admin-credentials.json"

  mkdir -p "$SERVER_DIR/runtime"
  printf '{\n  "email": "%s",\n  "password": "%s",\n  "created_at": %d\n}\n' \
    "$ADMIN_EMAIL" "$ADMIN_PASSWORD" "$(date +%s)" > "$ADMIN_CREDENTIALS_FILE"
  chown "$RUN_USER":"$RUN_USER" "$ADMIN_CREDENTIALS_FILE" 2>/dev/null || true
  chmod 600 "$ADMIN_CREDENTIALS_FILE"
  ok "Primeiro acesso: Super Admin '$ADMIN_EMAIL' criado (senha no resumo final)."

  # Se o serviço já está rodando (reinstalação com banco novo), reinicia para
  # aplicar as credenciais no boot; se nunca subiu, elas já são consumidas no
  # primeiro boot lá na frente.
  if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    if systemctl restart "$SERVICE_NAME" >>"$LOG_FILE" 2>&1; then
      for _ in $(seq 1 30); do
        curl -fsS --max-time 2 http://127.0.0.1:8080/revival/health -o /dev/null 2>>"$LOG_FILE" && break
        sleep 1
      done
    else
      warn "Não consegui reiniciar $SERVICE_NAME; o Super Admin nasce no próximo boot."
    fi
  fi
else
  info "Super Admin já cadastrado neste servidor (senha preservada):"
  while IFS= read -r admin_line; do
    [[ -n "$admin_line" ]] && ui_bullet "$admin_line"
  done <<< "$ADMIN_EMAILS"
fi

# Link temporário (10 minutos, uso único) para trocar e-mail e senha do
# Super Admin — gerado sempre, caso a pessoa esqueça os dados de acesso.
ADMIN_RECOVER_TOKEN="$(openssl rand -hex 32)"
ADMIN_RECOVER_CREATED_AT="$(date +%s)"
ADMIN_RECOVER_EXPIRES_AT="$(( ADMIN_RECOVER_CREATED_AT + 600 ))"
ADMIN_RECOVER_TOKEN_FILE="$SERVER_DIR/runtime/admin-recover-token.json"

mkdir -p "$SERVER_DIR/runtime"
printf '{\n  "token": "%s",\n  "expires_at": %d,\n  "created_at": %d\n}\n' \
  "$ADMIN_RECOVER_TOKEN" "$ADMIN_RECOVER_EXPIRES_AT" "$ADMIN_RECOVER_CREATED_AT" > "$ADMIN_RECOVER_TOKEN_FILE"
chown "$RUN_USER":"$RUN_USER" "$ADMIN_RECOVER_TOKEN_FILE" 2>/dev/null || true
chmod 600 "$ADMIN_RECOVER_TOKEN_FILE"
ADMIN_RECOVER_EXPIRES_LABEL="$(date -d "@$ADMIN_RECOVER_EXPIRES_AT" '+%H:%M:%S' 2>/dev/null || echo "daqui a 10 minutos")"
ok "Link de recuperação do Super Admin gerado (válido até $ADMIN_RECOVER_EXPIRES_LABEL; veja o resumo final)."

# ---------------------------------------------------------------------------
step "Rodando testes automatizados do servidor (gate de deploy)"

if ! (cd "$SERVER_DIR" && npm test); then
  fail "Os testes do servidor falharam. O deploy foi interrompido de propósito para não subir código quebrado. Veja o log acima para o teste que falhou."
fi

# ---------------------------------------------------------------------------
step "Instalando serviço systemd do Revival Server"

NODE_BIN="$(command -v node)"
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
      ok "$svc ativo."
      return 0
    fi
    sleep 1
    tries=$((tries + 1))
  done
  err "Serviço $svc não está ativo."
  raw_header "journalctl -u $svc (últimas 80 linhas)" >&2
  journalctl -u "$svc" -n 80 --no-pager 2>&1 | raw_block >&2 || true
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
  info "ufw ativo: liberando portas 80/tcp e 443/tcp..."
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
  ok "Site nginx do Revival já existe com HTTPS ativo (gerenciado pelo certbot):"
  ok_cont "mantendo $NGINX_SITE_FILE intacto."
else
  own "Escrevendo somente o site deste projeto em $NGINX_SITE_FILE —"
  own_cont "nenhum outro site/domínio do nginx é tocado."
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
  ok "nginx recarregado (reload; conexões de outros sites não caem)."
else
  systemctl enable nginx >/dev/null
  systemctl restart nginx
fi

verify_service_active "nginx" || fail "O serviço nginx não subiu. Veja o journalctl acima."

# --- certbot: emissor/renovador do certificado Let's Encrypt ---
if ! command -v certbot >/dev/null 2>&1; then
  if ! state_decided CERTBOT_INSTALLED_BY_SCRIPT; then
    own "certbot ausente nesta VPS: será instalado agora e passa a pertencer"
    own_cont "a este projeto."
    set_state CERTBOT_INSTALLED_BY_SCRIPT 1
  fi
  apt-get install -y --no-install-recommends certbot python3-certbot-nginx
else
  if ! state_decided CERTBOT_INSTALLED_BY_SCRIPT; then
    own "certbot já existia nesta VPS (pode ser de outro projeto): NÃO é"
    own_cont "nosso, uninstall.sh nunca vai removê-lo."
    set_state CERTBOT_INSTALLED_BY_SCRIPT 0
  fi
fi
ok "$(certbot --version 2>&1 | head -n1)"

if [[ -f "$CERT_RENEWAL_CONF" ]]; then
  ok "Certificado Let's Encrypt de $DOMAIN já existe; pulando emissão"
  ok_cont "(a renovação é automática; ver etapa abaixo)."
else
  info "Emitindo certificado Let's Encrypt para $DOMAIN (certbot --nginx --redirect)..."
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
  ok "Timer do certbot já existe nesta VPS: renovação já é automática, nada a instalar."
elif [[ -f /etc/cron.d/certbot-renew ]] || crontab -l 2>/dev/null | grep -q 'certbot renew'; then
  ok "Já existe automação de renovação do certbot nesta VPS (cron): nada a instalar."
  if ! state_decided CERTBOT_RENEW_CRON_INSTALLED_BY_SCRIPT; then
    own "Essa automação não foi criada por nós (ou é compartilhada com outros"
    own_cont "certificados da VPS): fica marcada como NÃO nossa e o uninstall.sh"
    own_cont "não vai removê-la."
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
  ok "Cron de renovação instalado: /etc/cron.d/certbot-renew (2x ao dia)."
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
  own "/etc/caddy/Caddyfile não existia: criando um Caddyfile global mínimo"
  own_cont "que só importa $CADDY_CONF_DIR/*.caddy."
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
    own "/etc/caddy/Caddyfile já existia nesta VPS (não foi criado por nós;"
    own_cont "pode ter blocos de outros projetos). Este instalador NUNCA"
    own_cont "sobrescreve esse arquivo."
    set_state CADDYFILE_CREATED_BY_SCRIPT 0
  fi
  if grep -qE "^[[:space:]]*import[[:space:]]+${CADDY_CONF_DIR}/\*\.caddy[[:space:]]*\$" "$CADDYFILE"; then
    own "Caddyfile já importa $CADDY_CONF_DIR/*.caddy; nada a alterar nele."
  else
    own "Acrescentando só a linha 'import $CADDY_CONF_DIR/*.caddy' ao final do"
    own_cont "Caddyfile existente (100% do conteúdo atual é preservado)."
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

own "Escrevendo somente o site deste projeto em $CADDY_SITE_FILE —"
own_cont "nenhum outro arquivo/domínio é tocado."
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
  info "Caddy já estava ativo (pode estar servindo outros domínios): usando"
  info_cont "'reload' em vez de 'restart' para não derrubar as conexões deles."
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
  raw_header "journalctl -u $SERVICE_NAME (últimas 80 linhas)" >&2
  journalctl -u "$SERVICE_NAME" -n 80 --no-pager 2>&1 | raw_block >&2 || true
  fail "O servidor Node não respondeu em http://127.0.0.1:8080/revival/health."
fi
raw_block < "$LOCAL_HEALTH"
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
  raw_header "journalctl -u $PROXY_KIND (últimas 80 linhas)" >&2
  journalctl -u "$PROXY_KIND" -n 80 --no-pager 2>&1 | raw_block >&2 || true
  fail "Não foi possível validar https://$DOMAIN/revival/health. Confira se o DNS de $DOMAIN aponta para o IP público deste servidor e se as portas 80/443 estão liberadas no firewall da VPS/provedor de nuvem (ex: AWS Security Group, painel da hospedagem)."
fi
raw_block < "$PUBLIC_HEALTH"
echo ""

C_ERR="$C_ERR" C_WARN="$C_WARN" C_OK="$C_OK" C_RESET="$C_RESET" \
  python3 - "$PUBLIC_HEALTH" <<'PYEOF' || fail "O health check público não atende o gate de produção (versão, research_mode, contract_revision ou identidade). Veja os erros acima."
import json
import os
import sys

# Mesmos icones/cores do instalador, herdados por ambiente.
ERR = os.environ.get("C_ERR", "")
WARN = os.environ.get("C_WARN", "")
OK = os.environ.get("C_OK", "")
RESET = os.environ.get("C_RESET", "")

# Um gate de deploy nao pode morrer por causa de um icone: se a saida nao
# aceita UTF-8 (locale exotico, PYTHONIOENCODING antigo), cai para ASCII.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def icon(glyph, fallback):
    try:
        glyph.encode(sys.stdout.encoding or "ascii")
        return glyph
    except Exception:
        return fallback


I_OK = icon("✓", "OK")
I_ERR = icon("✗", "X")
I_WARN = icon("▲", "!")

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

# Gate de produção (espelha productionReadiness de server/src/instance.js e o
# preflight do Studio): sem isso o deploy pode subir um servidor que o patcher
# vai recusar — ou pior, aceitar — com rota faltante mascarada por ok() vazio.
if payload.get("research_mode") is not False:
    errors.append("research_mode ligado em produção: endpoint desconhecido responderia sucesso vazio")
if not isinstance(payload.get("contract_revision"), int) or payload.get("contract_revision", 0) < 2:
    errors.append(f"contract_revision={payload.get('contract_revision')!r}; esperado >= 2 (wire do cliente 1.13.1)")
if not payload.get("instance_id"):
    errors.append("health sem instance_id: impossível provar onde o tráfego do cliente aterrissou")
if not payload.get("build_id"):
    errors.append("health sem build_id: os bytes em execução não estão identificados")

if errors:
    print(ERR + I_ERR + " health incompatível com o patcher: " + "; ".join(errors) + RESET)
    sys.exit(1)

if payload.get("game_data_loaded") is not True:
    print(WARN + I_WARN + RESET + " game_data_loaded=false: coloque um server/data/game-data.json")
    print("  real, rode 'sudo systemctl restart mighty-doom-revival' e só então")
    print("  gere o APK final com o patcher.")

print(OK + I_OK + RESET + " Revival HTTPS validado: client_version/api_version batem com o patcher.")
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

# ---------------------------------------------------------------------------
# Resumo final: é o que a pessoa realmente lê depois de 10 minutos de deploy.
# Cada bloco é uma pergunta que ela vai ter ("como entro?", "cadê o link do
# APK?", "o que o uninstall pode apagar?"), com os segredos destacados e os
# links isolados em linha própria para copiar sem cortar caractere.
ui_banner "✓" "$C_OK" "CONCLUÍDO — Mighty DOOM Revival está 100% no ar" "https://$DOMAIN"

ui_section "SERVIÇO"
ui_row "Site"               "https://$DOMAIN/"
ui_row "Health check"       "https://$DOMAIN/revival/health"
ui_row "Health local"       "http://127.0.0.1:8080/revival/health"
ui_row "Perfil de recursos" "$RAM_PROFILE · heap ${HEAP_MB}MB · RAM máx $MEM_MAX · tasks $TASKS_MAX"
ui_row "Reverse proxy"      "$PROXY_KIND"

ui_section "UPLOAD DO APK PELO NAVEGADOR" "opcional"
ui_text "Para publicar o APK patcheado no botão de download do site, abra"
ui_text "este link TEMPORÁRIO e arraste o arquivo .apk:"
echo ""
ui_link "https://$DOMAIN/upload/$UPLOAD_TOKEN"
echo ""
ui_row  "Válido até" "$UPLOAD_EXPIRES_LABEL · 24 horas"
ui_note "Links gerados por instalações anteriores foram invalidados."
echo ""
ui_text "Quer ELIMINAR este link agora, antes das 24h? Abra no navegador:"
echo ""
ui_link "https://$DOMAIN/upload-cancel/$UPLOAD_TOKEN"
echo ""
ui_note "Depois de eliminado, ninguém consegue enviar ou substituir o APK"
ui_note "sem rodar este instalador de novo. O APK já publicado continua no"
ui_note "ar normalmente em:"
ui_link "https://$DOMAIN/download/mighty-doom-revival.apk"

ui_section "PAINEL DO SLAYER" "conta · progresso · administração"
ui_row "Login / criar conta" "https://$DOMAIN/account"
ui_row "Painel (após login)" "https://$DOMAIN/slayer"
echo ""
if [[ "$ADMIN_FIRST_ACCESS" == "1" ]]; then
  ui_text "${C_BOLD}Primeiro acesso criado por ESTA instalação${C_RESET} (guarde bem):"
  ui_row_hi "e-mail do Super Admin" "$ADMIN_EMAIL"
  ui_row_hi "senha do Super Admin"  "$ADMIN_PASSWORD"
else
  ui_text "Super Admin já cadastrado neste servidor (senha inalterada):"
  while IFS= read -r admin_line; do
    if [[ -n "$admin_line" ]]; then
      ui_bullet "$admin_line"
    fi
  done <<< "$ADMIN_EMAILS"
fi
echo ""
ui_text "Esqueceu o e-mail/senha do Super Admin? Abra este link TEMPORÁRIO"
ui_text "para trocar os dois:"
echo ""
ui_link "https://$DOMAIN/admin-recover/$ADMIN_RECOVER_TOKEN"
echo ""
ui_row  "Validade do link" "até $ADMIN_RECOVER_EXPIRES_LABEL · 10 min · uso único"
ui_note "Concluída a troca, o link é revogado na hora e todas as sessões do"
ui_note "painel são encerradas. Se expirar, rode o instalador de novo."

ui_section "TOKEN ADMIN DA API"
ui_secret "$(get_env_var REVIVAL_ADMIN_TOKEN)"
echo ""
ui_note "Guarde este token: é ele que autoriza as operações técnicas do"
ui_note "servidor. Uso na CLI local:"
ui_cmd "export REVIVAL_ADMIN_TOKEN='<token acima>'"
ui_cmd "python3 scripts/revival_admin.py overview"

ui_section "OPERAÇÃO E LOGS"
ui_cmd "systemctl status $SERVICE_NAME"
ui_cmd "systemctl status $PROXY_KIND"
ui_cmd "journalctl -u $SERVICE_NAME -f"
echo ""
ui_path "Log desta instalação" "$LOG_FILE"
ui_path "Log do servidor"      "$SERVER_LOG"

ui_section "PROPRIEDADE" "VPS compartilhada com outros projetos"
ui_own "Node.js" NODE_INSTALLED_BY_SCRIPT
if [[ "$PROXY_KIND" == "nginx" ]]; then
  ui_own_ours "Site nginx deste projeto" "$NGINX_SITE_FILE"
  ui_own_ours "Certificado Let's Encrypt" "domínio $DOMAIN, emitido para este projeto"
  ui_own "Pacote 'certbot'"          CERTBOT_INSTALLED_BY_SCRIPT
  ui_own "Cron de renovação certbot" CERTBOT_RENEW_CRON_INSTALLED_BY_SCRIPT
  ui_sub "/etc/cron.d/certbot-renew"
else
  ui_own "Pacote 'caddy'"              CADDY_PACKAGE_INSTALLED_BY_SCRIPT
  ui_own "/etc/caddy/Caddyfile"        CADDYFILE_CREATED_BY_SCRIPT
  ui_own "Linha 'import' no Caddyfile" CADDY_IMPORT_LINE_ADDED_BY_SCRIPT
  ui_own_ours "Site do Caddy deste projeto" "$CADDY_SITE_FILE"
fi
ui_own_ours "Serviço systemd" "$SERVICE_NAME"
echo ""
ui_path "Registro de posse" "$STATE_FILE"
echo ""
ui_note "Para remover só o que é deste projeto, sem afetar outros projetos"
ui_note "na mesma VPS:"
ui_cmd "sudo ./scripts/uninstall.sh"

ui_section "PRÓXIMOS PASSOS"
ui_step 1 "Gere o APK local no Revival Studio (scripts/revival-studio),"
ui_step_cont "menu 'APK -> Aplicar endpoint', informando '$DOMAIN'"
ui_step_cont "como servidor."
echo ""
ui_step 2 "Para atualizar depois de mudanças no código (o instalador já"
ui_step_cont "faz o git pull sozinho):"
ui_cmd "sudo ./scripts/install.sh" 6

echo ""
printf '%s%s%s\n' "$C_DIM" "$(ui_repeat '─' "$UI_WIDTH")" "$C_RESET"
echo ""
