#!/usr/bin/env python3
"""Continue a blocked APK patch using Unity object reserialization."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from patch_apk import normalize_host
from patch_unity_bundle import UnityPyUnavailable, patch_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decoded", required=True)
    parser.add_argument("--server", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    decoded = Path(args.decoded).resolve()
    report_path = Path(args.report).resolve()
    if not decoded.is_dir() or not report_path.is_file():
        print("ERRO: diretório decoded ou relatório inexistente.", file=sys.stderr)
        return 2

    try:
        host = normalize_host(args.server)
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"ERRO ao ler parâmetros do bundle-aware patch: {exc}", file=sys.stderr)
        return 2

    paths = sorted({str(hit.get("path", "")) for hit in report.get("known_host_hits", []) if hit.get("path")})
    results = []
    try:
        for rel in paths:
            candidate = (decoded / rel).resolve()
            try:
                candidate.relative_to(decoded)
            except ValueError:
                print(f"ERRO: caminho fora do decoded recusado: {rel}", file=sys.stderr)
                return 2
            if not candidate.is_file():
                continue
            result = patch_bundle(candidate, host)
            result["path"] = rel
            results.append(result)
    except UnityPyUnavailable as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 5
    except Exception as exc:
        print(f"ERRO no patch bundle-aware: {exc}", file=sys.stderr)
        return 4

    changed = [x for x in results if x.get("changed")]
    if not changed:
        print(
            "BLOQUEADO COM SEGURANÇA: o hostname foi localizado no bundle bruto, "
            "mas não apareceu em TextAsset/MonoBehaviour serializável. Nenhum byte foi alterado.",
            file=sys.stderr,
        )
        report["bundle_aware"] = results
        report["status"] = "needs_object_mapping"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return 4

    report["bundle_aware"] = results
    report["status"] = "ok_bundle_aware"
    report["bundle_aware_patched_files"] = [x["path"] for x in changed]
    report["bundle_aware_replacements"] = sum(int(x.get("replacements", 0)) for x in changed)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": report["status"],
        "server_host": host,
        "patched_files": report["bundle_aware_patched_files"],
        "replacements": report["bundle_aware_replacements"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
