#!/usr/bin/env python3
"""Fast pre-decode gate: does this hostname fit the safe same-length patch?

apktool can take minutes to decode a large IL2CPP APK. Nothing about that
step depends on which hostname the user typed, so there is no reason to make
them wait through it before finding out their hostname's byte length does not
match the official host(s) actually found inside the APK. This script does
the same host scan `analyze_apk.py` does (a plain ZIP read, no apktool) and
fails fast, with a clear explanation, before the patcher touches apktool.
"""
from __future__ import annotations

import sys
from pathlib import Path

from analyze_apk import analyze
from patch_apk import normalize_host


def check(apk: Path, host: str) -> tuple[int, list[str]]:
    """Return (exit_code, message_lines)."""
    report = analyze(apk)
    hits = report.get("host_hits") or []

    found_hosts: set[str] = set()
    for hit in hits:
        offsets = hit.get("offsets")
        if isinstance(offsets, dict):
            found_hosts.update(offsets.keys())

    if not found_hosts:
        return 0, [
            "[AVISO] Nenhum host oficial conhecido foi encontrado neste APK ainda.",
            "Não é possível validar o comprimento do hostname agora; a etapa de patch decidirá durante o decode.",
        ]

    found_lengths = sorted({len(h.encode("ascii")) for h in found_hosts})
    target_len = len(host.encode("ascii"))

    if target_len in found_lengths:
        return 0, [f"[OK] '{host}' tem {target_len} bytes; compatível com o patch direto e seguro."]

    return 4, [
        f"[BLOQUEADO] '{host}' tem {target_len} bytes.",
        f"O(s) host(s) oficial(is) encontrado(s) neste APK tem/têm {found_lengths} bytes de comprimento.",
        "Hoje o patcher só troca hostnames com exatamente o mesmo número de bytes do host oficial.",
        "Trocar por um comprimento diferente exigiria reconstruir a tabela de metadata do IL2CPP",
        "(realocar seções inteiras do arquivo), o que ainda não é suportado com segurança.",
        "",
        f"Escolha um hostname com exatamente {found_lengths} bytes e rode de novo.",
    ]


def main() -> int:
    if len(sys.argv) != 3:
        print("uso: check_patch_length.py <apk> <hostname>", file=sys.stderr)
        return 2

    apk = Path(sys.argv[1]).expanduser().resolve()
    if not apk.is_file():
        print(f"ERRO: APK não encontrado: {apk}", file=sys.stderr)
        return 2

    try:
        host = normalize_host(sys.argv[2])
    except ValueError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    code, lines = check(apk, host)
    stream = sys.stderr if code else sys.stdout
    for line in lines:
        print(line, file=stream)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
