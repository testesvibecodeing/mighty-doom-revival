#!/usr/bin/env bash
# Mighty DOOM Revival - APK patcher (Linux/Mac)
# Uso pessoal / preservação. O APK original não é distribuído.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "============================================================"
echo " Mighty DOOM Revival - APK patcher"
echo " Uso pessoal / preservação. O APK original não é distribuído."
echo "============================================================"
echo

STEP="inicialização"
on_error() {
  local exit_code=$?
  echo "" >&2
  echo "[ERRO] Falha na etapa: $STEP (código de saída $exit_code)" >&2
  exit "$exit_code"
}
trap on_error ERR

step() {
  STEP="$1"
}

DEFAULT_APK="input/mighty-doom.apk"
read -rp "Caminho do APK [$DEFAULT_APK]: " APK_INPUT || true
APK="${APK_INPUT:-$DEFAULT_APK}"

if [[ ! -f "$APK" ]]; then
  echo "[ERRO] APK não encontrado: $APK" >&2
  echo "Para baixar/validar a cópia alvo execute antes:" >&2
  echo "  scripts/analyze-official-apk.sh" >&2
  exit 2
fi

DEFAULT_HOST="d.debruinsistemas.com.br"
read -rp "Hostname HTTPS do servidor [$DEFAULT_HOST]: " SERVER_INPUT || true
SERVER_HOST="${SERVER_INPUT:-$DEFAULT_HOST}"

CA_FILE=""
read -rp "CA PEM/CRT local para HTTPS [ENTER = certificado público]: " CA_FILE || true
if [[ -n "$CA_FILE" && ! -f "$CA_FILE" ]]; then
  echo "[ERRO] CA não encontrada: $CA_FILE" >&2
  exit 2
fi

echo
echo "Verificando dependências mínimas..."
step "verificação de dependências"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
else
  echo "[FALTA] python3 não está no PATH." >&2
  exit 3
fi
echo "[OK] $PYTHON_BIN"

echo
echo "Verificando se \"$SERVER_HOST\" cabe no patch direto e seguro (sem apktool)..."
step "verificação de comprimento do hostname"
if ! "$PYTHON_BIN" scripts/check_patch_length.py "$APK" "$SERVER_HOST"; then
  echo >&2
  echo "Ajuste o hostname acima e rode o patcher de novo." >&2
  exit 4
fi

if ! command -v java >/dev/null 2>&1; then
  echo "[FALTA] java não está no PATH." >&2
  exit 3
fi
echo "[OK] java"

step "preparação das ferramentas do patcher"
if [[ ! -f ".tools/apktool.jar" || ! -f ".tools/uber-apk-signer.jar" ]]; then
  "$ROOT/scripts/setup-patcher-tools.sh"
fi

echo "Verificando suporte bundle-aware..."
step "verificação do UnityPy"
if ! "$PYTHON_BIN" -c "import UnityPy,sys; sys.exit(0 if getattr(UnityPy,'__version__','') == '1.25.3' else 1)" >/dev/null 2>&1; then
  echo "Instalando UnityPy 1.25.3 para reserialização segura de bundles Unity..."
  "$PYTHON_BIN" -m pip install --disable-pip-version-check "UnityPy==1.25.3"
fi

APKTOOL=".tools/apktool.jar"
SIGNER=".tools/uber-apk-signer.jar"
WORK="work/apk-patch"
DECODED="$WORK/decoded"
UNSIGNED="$WORK/revival-unsigned.apk"
REPORT="$WORK/patch-report.json"
PREFLIGHT_REPORT="$WORK/server-preflight.json"
VERIFY_REPORT="$WORK/final-apk-verification.json"
OUT="output/mighty-doom-revival.apk"

rm -rf "$WORK"
mkdir -p "$WORK" output

echo
echo "[1/8] Validando servidor Revival por HTTPS..."
step "[1/8] preflight HTTPS do servidor"
if [[ -z "$CA_FILE" ]]; then
  "$PYTHON_BIN" scripts/check_revival_server.py --server "$SERVER_HOST" --report "$PREFLIGHT_REPORT"
else
  "$PYTHON_BIN" scripts/check_revival_server.py --server "$SERVER_HOST" --ca "$CA_FILE" --report "$PREFLIGHT_REPORT"
fi

echo
echo "[2/8] Analisando APK..."
step "[2/8] análise do APK"
"$PYTHON_BIN" scripts/analyze_apk.py "$APK"

echo
echo "[3/8] Desmontando APK..."
step "[3/8] apktool decode"
java -jar "$APKTOOL" d -f "$APK" -o "$DECODED"

echo
echo "[4/8] Aplicando servidor e configuração TLS..."
step "[4/8] patch de servidor/TLS"
PATCH_RC=0
if [[ -z "$CA_FILE" ]]; then
  "$PYTHON_BIN" scripts/patch_apk.py --decoded "$DECODED" --server "$SERVER_HOST" --report "$REPORT" || PATCH_RC=$?
else
  "$PYTHON_BIN" scripts/patch_apk.py --decoded "$DECODED" --server "$SERVER_HOST" --ca "$CA_FILE" --report "$REPORT" || PATCH_RC=$?
fi

if [[ "$PATCH_RC" == "4" ]]; then
  echo
  echo "Hostname com tamanho diferente detectado. Tentando patch bundle-aware..."
  PATCH_RC=0
  "$PYTHON_BIN" scripts/patch_bundle_from_report.py --decoded "$DECODED" --server "$SERVER_HOST" --report "$REPORT" || PATCH_RC=$?
fi

if [[ "$PATCH_RC" != "0" ]]; then
  echo
  echo "[PARADO] O patcher não conseguiu provar uma alteração segura do bundle Unity." >&2
  echo "Nenhum patch binário de tamanho variável foi feito no escuro." >&2
  echo "Relatório: $REPORT" >&2
  exit "$PATCH_RC"
fi

echo
echo "[5/8] Reconstruindo APK..."
step "[5/8] apktool build"
java -jar "$APKTOOL" b "$DECODED" -o "$UNSIGNED"

echo
echo "[6/8] Validando endpoint dentro do APK reconstruído..."
step "[6/8] verificação do endpoint no APK reconstruído"
"$PYTHON_BIN" scripts/verify_patched_apk.py --apk "$UNSIGNED" --server "$SERVER_HOST" --report "$VERIFY_REPORT"

echo
echo "[7/8] Alinhando, assinando e verificando assinatura..."
step "[7/8] assinatura do APK"
java -jar "$SIGNER" -a "$UNSIGNED" --overwrite --verbose
java -jar "$SIGNER" -a "$UNSIGNED" --onlyVerify --verbose

# A assinatura não deve alterar os payloads de assets. Verifique novamente o
# endpoint depois do signer para impedir entrega de um artefato inesperado.
step "[7/8] verificação final do endpoint pós-assinatura"
"$PYTHON_BIN" scripts/verify_patched_apk.py --apk "$UNSIGNED" --server "$SERVER_HOST" --report "$VERIFY_REPORT"

step "[8/8] publicação do APK final"
rm -f "$OUT"
cp "$UNSIGNED" "$OUT"

echo
echo "[8/8] CONCLUÍDO"
echo "APK gerado e verificado: $OUT"
echo "Servidor: https://$SERVER_HOST"
echo "Preflight HTTPS: $PREFLIGHT_REPORT"
echo "Relatório do patch: $REPORT"
echo "Relatório final: $VERIFY_REPORT"
echo
echo "A assinatura é diferente da oficial. Se a versão oficial estiver instalada,"
echo "desinstale-a antes de instalar este APK de preservação."
echo
echo "Com ADB instalado, opcionalmente use:"
echo "  adb uninstall com.bethsoft.ubu"
echo "  adb install \"$OUT\""
echo
