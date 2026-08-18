#!/usr/bin/env bash
# Analyze an APK supplied locally by the user. No download is performed.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON_BIN="$(command -v python3 || command -v python)"
# studio-forward: sem argumentos e com sessão gráfica, abre o Revival Studio
# (ação projeto.analisar). Com qualquer argumento segue o caminho headless de
# sempre — CI/VPS não mudam (plano §9.2).
if [[ $# -eq 0 ]] && [[ -t 1 ]] && { [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]] || [[ "$(uname -s)" == "Darwin" ]]; }; then
  exec "$PYTHON_BIN" "$(dirname "${BASH_SOURCE[0]}")/revival_studio.py"
fi
APK_PATH="${1:-input/mighty-doom.apk}"
if [[ ! -f "$APK_PATH" ]]; then
  echo "[ERROR] Local APK not found: $APK_PATH" >&2
  echo "Usage: scripts/analyze-official-apk.sh path/to/your-copy.apk" >&2
  exit 1
fi
mkdir -p reports
"$PYTHON_BIN" scripts/analyze_apk.py "$APK_PATH" --json-out reports/apk-1.13.1.json --md-out reports/apk-1.13.1.md
echo "Sanitized reports written to reports/. The APK was not downloaded or published."
