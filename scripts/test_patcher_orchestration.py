#!/usr/bin/env python3
"""Regression guard for the top-level APK patcher orchestration.

The direct same-length check is only a fast-path capability probe. A return
code 4 must not stop the Windows/Linux patchers before apktool decode, because
variable-length Addressables endpoints are handled by the structured
bundle-aware fallback. The fallback must sweep all bundles to catch LZ4
compressed host strings that are invisible to a raw ZIP byte scan.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    bat = (ROOT / "scripts" / "patch-apk.bat").read_text(encoding="utf-8")
    sh = (ROOT / "scripts" / "patch-apk.sh").read_text(encoding="utf-8")

    assert "LENGTH_RC" in bat
    assert '"!LENGTH_RC!"=="4"' in bat
    assert "Continuando para o patch bundle-aware" in bat
    assert "--sweep-all-bundles" in bat

    assert "LENGTH_RC=0" in sh
    assert "4)" in sh
    assert "Continuando para o patch bundle-aware" in sh
    assert "--sweep-all-bundles" in sh

    print("Mighty DOOM patcher bundle-aware orchestration regression: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
