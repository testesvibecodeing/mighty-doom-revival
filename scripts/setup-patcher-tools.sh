#!/usr/bin/env bash
# Mighty DOOM Revival - preparar ferramentas do patcher (Linux/Mac)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "============================================================"
echo " Mighty DOOM Revival - preparar ferramentas do patcher"
echo "============================================================"
echo

if ! command -v java >/dev/null 2>&1; then
  echo "[ERRO] Java não encontrado no PATH." >&2
  echo "Instale um JDK/JRE moderno (Java 17+ recomendado) e tente novamente." >&2
  exit 2
fi

if command -v curl >/dev/null 2>&1; then
  DOWNLOADER=curl
elif command -v wget >/dev/null 2>&1; then
  DOWNLOADER=wget
else
  echo "[ERRO] Nem curl nem wget foram encontrados no PATH." >&2
  exit 2
fi

if command -v sha256sum >/dev/null 2>&1; then
  sha256_of() { sha256sum "$1" | awk '{print tolower($1)}'; }
elif command -v shasum >/dev/null 2>&1; then
  sha256_of() { shasum -a 256 "$1" | awk '{print tolower($1)}'; }
else
  echo "[ERRO] Nem sha256sum nem shasum foram encontrados no PATH." >&2
  exit 2
fi

TOOL_DIR=".tools"
APKTOOL="$TOOL_DIR/apktool.jar"
SIGNER="$TOOL_DIR/uber-apk-signer.jar"

APKTOOL_URL="https://github.com/iBotPeaches/Apktool/releases/download/v3.0.3/apktool_3.0.3.jar"
APKTOOL_SHA="dbf930b076c6b9be08d57c449cacefc3bdd6b71ebd59b3066fc0e1f5b14f9423"
SIGNER_URL="https://github.com/patrickfav/uber-apk-signer/releases/download/v1.3.0/uber-apk-signer-1.3.0.jar"
SIGNER_SHA="e1299fd6fcf4da527dd53735b56127e8ea922a321128123b9c32d619bba1d835"

mkdir -p "$TOOL_DIR"

download_and_verify() {
  local url="$1" dest="$2" expected="$3" label="$4"

  if [[ -f "$dest" ]]; then
    if [[ "$(sha256_of "$dest")" == "$expected" ]]; then
      echo "[OK] $label já existe e o SHA-256 confere."
      return 0
    fi
    echo "[AVISO] Hash inválido em $dest. Baixando novamente..."
    rm -f "$dest"
  fi

  echo "Baixando $label..."
  if [[ "$DOWNLOADER" == "curl" ]]; then
    if ! curl -fL --retry 3 -o "$dest" "$url"; then
      echo "[ERRO] Falha ao baixar $label." >&2
      rm -f "$dest"
      exit 3
    fi
  else
    if ! wget -q -O "$dest" "$url"; then
      echo "[ERRO] Falha ao baixar $label." >&2
      rm -f "$dest"
      exit 3
    fi
  fi

  if [[ "$(sha256_of "$dest")" != "$expected" ]]; then
    echo "[ERRO] SHA-256 de $label não confere. Arquivo removido." >&2
    rm -f "$dest"
    exit 4
  fi
  echo "[OK] $label validado."
}

download_and_verify "$APKTOOL_URL" "$APKTOOL" "$APKTOOL_SHA" "Apktool 3.0.3"
download_and_verify "$SIGNER_URL" "$SIGNER" "$SIGNER_SHA" "Uber APK Signer 1.3.0"

echo
echo "Validando executáveis Java..."
if ! java -jar "$APKTOOL" --version; then
  echo "[ERRO] Apktool baixado não executou corretamente." >&2
  exit 5
fi
if ! java -jar "$SIGNER" --version; then
  echo "[ERRO] Uber APK Signer baixado não executou corretamente." >&2
  exit 5
fi

echo
echo "[OK] Ferramentas do patcher preparadas em $TOOL_DIR."
echo "     Essa pasta é ignorada pelo Git."
