#!/usr/bin/env python3
"""Verify that a rebuilt Mighty DOOM APK contains the Revival endpoint.

This verifier intentionally inspects only metadata/byte indicators needed for
interoperability. It does not extract or publish proprietary assets.

For the 1.13.1 target, static analysis identified
``international.gear.bethesda.net`` as the gameplay API base. Other Bethesda
URLs such as Slayers Club may legitimately remain in the client and are not a
proof that gameplay still points at an official service. The final gate
therefore rejects stale *gameplay API* hosts, not every Bethesda-related URL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

from patch_apk import KNOWN_HOSTS, PRIMARY_API_HOST, normalize_host

SEARCH_PREFIXES = ("assets/aa/",)
SEARCH_SUFFIXES = (".json", ".txt", ".xml", "global-metadata.dat")
FORBIDDEN_ENDPOINT_HOSTS = (PRIMARY_API_HOST,)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def should_scan(name: str) -> bool:
    return name.startswith(SEARCH_PREFIXES) or name.endswith(SEARCH_SUFFIXES)


def scan_apk(apk: Path, target_host: str) -> dict[str, object]:
    target = target_host.encode("ascii")
    known = {host: host.encode("ascii") for host in KNOWN_HOSTS}
    forbidden = {host: host.encode("ascii") for host in FORBIDDEN_ENDPOINT_HOSTS}
    target_hits: list[dict[str, object]] = []
    known_host_hits: list[dict[str, object]] = []
    forbidden_endpoint_hits: list[dict[str, object]] = []
    scanned_files = 0

    with zipfile.ZipFile(apk, "r") as archive:
        names = archive.namelist()
        for name in names:
            if not should_scan(name):
                continue
            try:
                data = archive.read(name)
            except Exception:
                continue
            scanned_files += 1

            count = data.count(target)
            if count:
                target_hits.append({"path": name, "count": count})

            for host, raw in known.items():
                count = data.count(raw)
                if count:
                    known_host_hits.append({"path": name, "host": host, "count": count})

            for host, raw in forbidden.items():
                count = data.count(raw)
                if count:
                    forbidden_endpoint_hits.append({"path": name, "host": host, "count": count})

        return {
            "apk": apk.name,
            "sha256": sha256_file(apk),
            "zip_entries": len(names),
            "scanned_files": scanned_files,
            "server_host": target_host,
            "target_hits": target_hits,
            "known_host_hits": known_host_hits,
            # Keep the historical key for downstream report consumers, but it
            # now means stale official *gameplay endpoint* occurrences only.
            "official_host_hits": forbidden_endpoint_hits,
            "forbidden_endpoint_hits": forbidden_endpoint_hits,
            "target_occurrences": sum(int(x["count"]) for x in target_hits),
            "official_occurrences": sum(int(x["count"]) for x in forbidden_endpoint_hits),
            "known_host_occurrences": sum(int(x["count"]) for x in known_host_hits),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk", required=True)
    parser.add_argument("--server", required=True)
    parser.add_argument("--report")
    args = parser.parse_args()

    apk = Path(args.apk).expanduser().resolve()
    if not apk.is_file():
        print(f"ERRO: APK inexistente: {apk}", file=sys.stderr)
        return 2

    try:
        host = normalize_host(args.server)
        result = scan_apk(apk, host)
    except zipfile.BadZipFile:
        print("ERRO: arquivo final não é um APK/ZIP válido.", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERRO ao verificar APK: {exc}", file=sys.stderr)
        return 2

    result["verified"] = bool(result["target_occurrences"]) and not bool(result["official_occurrences"])
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    print(payload)
    if args.report:
        Path(args.report).write_text(payload + "\n", encoding="utf-8")

    if not result["target_occurrences"]:
        print(
            "ERRO: hostname Revival não foi encontrado nas áreas de rede/Addressables/IL2CPP do APK final.",
            file=sys.stderr,
        )
        return 4
    if result["official_occurrences"]:
        print(
            "ERRO: o APK final ainda contém o hostname oficial da API Gear; instalação recusada.",
            file=sys.stderr,
        )
        return 5

    print("APK final validado: endpoint Revival presente e API Gear oficial ausente nas áreas verificadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
