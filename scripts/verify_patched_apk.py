#!/usr/bin/env python3
"""Verify that a rebuilt Mighty DOOM APK contains the Revival endpoint.

This verifier intentionally inspects only metadata/byte indicators needed for
interoperability. It does not extract or publish proprietary assets.

For the 1.13.1 target, static analysis identified
``international.gear.bethesda.net`` as the gameplay API base. Other Bethesda
URLs such as Slayers Club may legitimately remain in the client and are not a
proof that gameplay still points at an official service.

Addressables bundles can use internal LZ4 compression, so a hostname may be
completely absent from the raw ZIP-entry bytes even though Unity can read it
from a serialized object. The final gate therefore combines a fast raw scan
with an optional UnityPy object scan of every ``assets/aa/**/*.bundle`` entry.
This closes the verifier gap for the bundle-aware arbitrary-hostname patcher.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

from patch_apk import KNOWN_HOSTS, PRIMARY_API_HOST, normalize_host
from patch_unity_bundle import UnityPyUnavailable, _load_unitypy

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


def _serialized_texts(env: Any):
    """Yield text representations of Unity objects without exporting payloads."""
    for obj in getattr(env, "objects", []):
        type_name = getattr(getattr(obj, "type", None), "name", "")
        if type_name == "TextAsset":
            try:
                text = obj.parse_as_object().m_Script
            except Exception:
                continue
            if isinstance(text, str):
                yield text
            continue

        try:
            tree = obj.parse_as_dict()
        except Exception:
            continue
        try:
            yield json.dumps(tree, ensure_ascii=False, default=str)
        except Exception:
            continue


def scan_unity_bundle_payload(payload: bytes, target_host: str, unitypy: Any | None = None) -> dict[str, int]:
    """Count target/known/forbidden hosts after Unity decodes a bundle payload.

    The function accepts an injected loader for regression tests; production
    callers lazily load the pinned UnityPy version used by the patcher.
    """
    if unitypy is None:
        unitypy = _load_unitypy()
    env = unitypy.load(payload)
    counts = {"target": 0, "known": 0, "forbidden": 0}
    for text in _serialized_texts(env):
        counts["target"] += text.count(target_host)
        counts["known"] += sum(text.count(host) for host in KNOWN_HOSTS)
        counts["forbidden"] += sum(text.count(host) for host in FORBIDDEN_ENDPOINT_HOSTS)
    return counts


def scan_apk(apk: Path, target_host: str) -> dict[str, object]:
    target = target_host.encode("ascii")
    known = {host: host.encode("ascii") for host in KNOWN_HOSTS}
    forbidden = {host: host.encode("ascii") for host in FORBIDDEN_ENDPOINT_HOSTS}
    target_hits: list[dict[str, object]] = []
    known_host_hits: list[dict[str, object]] = []
    forbidden_endpoint_hits: list[dict[str, object]] = []
    structured_bundle_hits: list[dict[str, object]] = []
    bundle_scan_errors: list[dict[str, str]] = []
    scanned_files = 0
    unitypy: Any | None = None
    unitypy_error: str | None = None

    with zipfile.ZipFile(apk, "r") as archive:
        names = archive.namelist()
        bundle_names = [
            name for name in names
            if name.startswith("assets/aa/") and name.endswith(".bundle")
        ]

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
                target_hits.append({"path": name, "count": count, "source": "raw"})

            for host, raw in known.items():
                count = data.count(raw)
                if count:
                    known_host_hits.append({"path": name, "host": host, "count": count, "source": "raw"})

            for host, raw in forbidden.items():
                count = data.count(raw)
                if count:
                    forbidden_endpoint_hits.append({"path": name, "host": host, "count": count, "source": "raw"})

        # Always inspect Addressables bundles structurally when UnityPy is
        # available. A stale Gear endpoint hidden in LZ4 is just as important
        # as a target hostname hidden there. Do not unpack/export objects.
        if bundle_names:
            try:
                unitypy = _load_unitypy()
            except UnityPyUnavailable as exc:
                unitypy_error = str(exc)

        if unitypy is not None:
            for name in bundle_names:
                try:
                    payload = archive.read(name)
                    counts = scan_unity_bundle_payload(payload, target_host, unitypy=unitypy)
                except Exception as exc:
                    bundle_scan_errors.append({"path": name, "error": str(exc)})
                    continue
                if any(counts.values()):
                    structured_bundle_hits.append({"path": name, **counts, "source": "unity"})

        raw_target = sum(int(x["count"]) for x in target_hits)
        raw_official = sum(int(x["count"]) for x in forbidden_endpoint_hits)
        raw_known = sum(int(x["count"]) for x in known_host_hits)
        unity_target = sum(int(x["target"]) for x in structured_bundle_hits)
        unity_official = sum(int(x["forbidden"]) for x in structured_bundle_hits)
        unity_known = sum(int(x["known"]) for x in structured_bundle_hits)

        return {
            "apk": apk.name,
            "sha256": sha256_file(apk),
            "zip_entries": len(names),
            "scanned_files": scanned_files,
            "server_host": target_host,
            "target_hits": target_hits,
            "known_host_hits": known_host_hits,
            "forbidden_endpoint_hits": forbidden_endpoint_hits,
            "structured_bundle_hits": structured_bundle_hits,
            "bundle_scan_errors": bundle_scan_errors,
            "bundle_scan_available": unitypy is not None,
            "bundle_scan_error": unitypy_error,
            "raw_target_occurrences": raw_target,
            "raw_official_occurrences": raw_official,
            "raw_known_host_occurrences": raw_known,
            "unity_target_occurrences": unity_target,
            "unity_official_occurrences": unity_official,
            "unity_known_host_occurrences": unity_known,
            # Keep historical keys for downstream report consumers. Structured
            # hits are additive because LZ4 can hide strings from raw scanning.
            "official_host_hits": forbidden_endpoint_hits,
            "target_occurrences": raw_target + unity_target,
            "official_occurrences": raw_official + unity_official,
            "known_host_occurrences": raw_known + unity_known,
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
        detail = ""
        if not result.get("bundle_scan_available"):
            detail = " UnityPy indisponível; endpoints comprimidos em bundles não puderam ser confirmados."
        print(
            "ERRO: hostname Revival não foi encontrado nas áreas de rede/Addressables/IL2CPP do APK final." + detail,
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
