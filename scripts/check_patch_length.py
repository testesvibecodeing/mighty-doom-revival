#!/usr/bin/env python3
"""Fast pre-decode capability check for the direct hostname patch.

apktool can take minutes to decode a large IL2CPP APK. This check tells the
orchestrator whether the requested hostname fits the zero-offset fast path
before decode starts.

Exit code 4 no longer means the whole patch operation is impossible: it means
only that the direct byte-preserving path cannot prove the replacement. The
Windows/Linux orchestrators may continue to decode and invoke the structured
Unity bundle-aware fallback, which can safely reserialize variable-length
strings inside Addressables bundles. If the remaining occurrence is actually
inside IL2CPP global-metadata.dat, the later patch stage will still stop safely.
"""
from __future__ import annotations

import sys
from pathlib import Path

from analyze_apk import analyze
from patch_apk import normalize_host


def check(apk: Path, host: str) -> tuple[int, list[str]]:
    """Return (exit_code, message_lines) for the direct patch capability."""
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
            "Nao e possivel validar o comprimento agora; o decode + patch bundle-aware decidira depois.",
        ]

    found_lengths = sorted({len(h.encode("ascii")) for h in found_hosts})
    target_len = len(host.encode("ascii"))
    max_len = max(found_lengths)

    if target_len <= max_len:
        if target_len < max_len:
            return 0, [
                f"[OK] '{host}' tem {target_len} bytes (o maior host oficial encontrado tem {max_len}).",
                "O fast path pode preservar o comprimento usando userinfo/FQDN padding quando a ocorrencia",
                "for uma URL https://<host>/; nenhum offset do global-metadata.dat precisa ser deslocado.",
            ]
        return 0, [f"[OK] '{host}' tem {target_len} bytes; compativel com o patch direto e seguro."]

    return 4, [
        f"[FALLBACK] '{host}' tem {target_len} bytes.",
        f"O(s) host(s) oficial(is) encontrado(s) no scan rapido tem/têm {found_lengths} bytes.",
        "O patch direto de tamanho fixo nao cabe. O orquestrador deve continuar para o decode e",
        "tentar o patch bundle-aware, que reserializa strings Unity de tamanho arbitrario com verificacao.",
        "Se a unica referencia relevante estiver em global-metadata.dat e exigir realocacao IL2CPP,",
        "a etapa posterior continuara bloqueando com seguranca em vez de alterar bytes no escuro.",
    ]


def main() -> int:
    if len(sys.argv) != 3:
        print("uso: check_patch_length.py <apk> <hostname>", file=sys.stderr)
        return 2

    apk = Path(sys.argv[1]).expanduser().resolve()
    if not apk.is_file():
        print(f"ERRO: APK nao encontrado: {apk}", file=sys.stderr)
        return 2

    try:
        host = normalize_host(sys.argv[2])
    except ValueError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    code, lines = check(apk, host)
    stream = sys.stderr if code not in (0, 4) else sys.stdout
    for line in lines:
        print(line, file=stream)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
