#!/usr/bin/env python3
"""Regression guard for the top-level APK patcher orchestration.

The direct same-length check is only a fast-path capability probe. An exit
code 4 from it must not stop the pipeline before the bundle-aware fallback,
because variable-length Addressables endpoints are handled by the structured
bundle-aware pass. The fallback must sweep all bundles to catch LZ4
compressed host strings that are invisible to a raw ZIP byte scan.

This contract originally lived in the retired `patch-apk.{bat,sh}` wrappers
(removed from scripts/ on 2026-08-18) and now lives in the pipeline service
`scripts/revival_editor/pipeline.py`, exercised by the Studio action
"Aplicar endpoint (decode -> patch -> build -> sign -> verify)".

Execução: python scripts/test_patcher_orchestration.py
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "scripts" / "revival_editor" / "pipeline.py"


def main() -> int:
    fonte = PIPELINE.read_text(encoding="utf-8")

    # exit 4 do check de comprimento NÃO aborta: cai no bundle-aware…
    assert "if codigo == 4:" in fonte
    assert "sweep bundle-aware" in fonte
    # …que varre TODOS os bundles (hosts LZ4 são invisíveis ao scan do ZIP).
    assert "--sweep-all-bundles" in fonte
    # sair do fast-path com exit 4 só é fatal quando o usuário PINOU fast-path.
    assert 'strategy == "fast-path"' in fonte
    # bundle-aware explícito varre mesmo após sucesso direto.
    assert 'strategy == "bundle-aware"' in fonte
    # a verificação obrigatória do APK assinado continua no fim do pipeline.
    assert "_VERIFY_CLI" in fonte
    # e a estratégia usada é registrada no relatório.
    assert 'resultado.strategy_used = "fast-path"' in fonte
    assert 'resultado.strategy_used = "bundle-aware"' in fonte

    print("Mighty DOOM patcher bundle-aware orchestration regression: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
