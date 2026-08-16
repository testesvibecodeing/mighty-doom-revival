#!/usr/bin/env python3
"""Sanitized static inventory for a user-supplied Mighty DOOM APK.

The report intentionally contains only metadata useful for interoperability:
hashes, ZIP member paths/sizes and byte offsets of known endpoint strings. It
does not export game assets, decompiled code or proprietary payloads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import BinaryIO

KNOWN_HOSTS = (
    b"slayersclub.bethesda.net",
    b"game.9095be396f3547555fe1039cbc894c88.net",
)
MAX_PATTERN = max(map(len, KNOWN_HOSTS))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def try_aapt(apk: Path) -> dict[str, str]:
    """Use aapt/aapt2 when present; no external Python dependency required."""
    exe = shutil.which("aapt") or shutil.which("aapt2")
    if not exe:
        return {}
    try:
        cp = subprocess.run(
            [exe, "dump", "badging", str(apk)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception:
        return {}

    first = next((line for line in cp.stdout.splitlines() if line.startswith("package:")), "")
    if not first:
        return {}

    result: dict[str, str] = {}
    for key in ("name", "versionCode", "versionName"):
        marker = f"{key}='"
        if marker in first:
            result[key] = first.split(marker, 1)[1].split("'", 1)[0]
    return result


def scan_stream(stream: BinaryIO) -> tuple[str, int, dict[str, list[int]]]:
    """Hash a member and locate known strings without loading it all in RAM."""
    h = hashlib.sha256()
    offsets: dict[str, list[int]] = {x.decode("ascii"): [] for x in KNOWN_HOSTS}
    tail = b""
    processed = 0

    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        h.update(chunk)
        buf = tail + chunk
        base = processed - len(tail)
        for pattern in KNOWN_HOSTS:
            key = pattern.decode("ascii")
            start = 0
            while True:
                idx = buf.find(pattern, start)
                if idx < 0:
                    break
                absolute = base + idx
                if absolute >= 0 and (not offsets[key] or offsets[key][-1] != absolute):
                    offsets[key].append(absolute)
                start = idx + 1
        processed += len(chunk)
        tail = buf[-(MAX_PATTERN - 1):] if MAX_PATTERN > 1 else b""

    offsets = {k: v for k, v in offsets.items() if v}
    return h.hexdigest(), processed, offsets


def write_markdown(report: dict[str, object], out: Path) -> None:
    pkg = report.get("package") if isinstance(report.get("package"), dict) else {}
    indicators = report.get("indicators") if isinstance(report.get("indicators"), dict) else {}
    hits = report.get("host_hits") if isinstance(report.get("host_hits"), list) else []

    lines = [
        "# Relatório sanitizado do APK",
        "",
        "> Este arquivo registra apenas metadados técnicos necessários para interoperabilidade. Nenhum asset ou código proprietário é incluído.",
        "",
        "## Arquivo",
        "",
        f"- SHA-256: `{report.get('sha256', '?')}`",
        f"- Tamanho: `{report.get('size_bytes', '?')}` bytes",
        f"- Package: `{pkg.get('name', '?') if isinstance(pkg, dict) else '?'}`",
        f"- Version name: `{pkg.get('versionName', '?') if isinstance(pkg, dict) else '?'}`",
        f"- Version code: `{pkg.get('versionCode', '?') if isinstance(pkg, dict) else '?'}`",
        "",
        "## Estrutura relevante",
        "",
    ]
    if isinstance(indicators, dict):
        for key, value in indicators.items():
            lines.append(f"- `{key}`: `{value}`")

    lines.extend(["", "## Referências de host encontradas", ""])
    if hits:
        for item in hits:
            if not isinstance(item, dict):
                continue
            lines.append(f"### `{item.get('file', '?')}`")
            lines.append(f"- SHA-256 do membro: `{item.get('sha256', '?')}`")
            lines.append(f"- Tamanho descompactado: `{item.get('uncompressed_size', '?')}` bytes")
            offsets = item.get("offsets", {})
            if isinstance(offsets, dict):
                for host, values in offsets.items():
                    lines.append(f"- `{host}` → offsets `{values}`")
            lines.append("")
    else:
        lines.append("Nenhuma referência conhecida encontrada nas áreas examinadas.")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def analyze(apk: Path) -> dict[str, object]:
    report: dict[str, object] = {
        "file": apk.name,
        "size_bytes": apk.stat().st_size,
        "sha256": sha256_file(apk),
        "package": try_aapt(apk),
        "indicators": {},
        "host_hits": [],
    }

    with zipfile.ZipFile(apk, "r") as zf:
        infos = zf.infolist()
        names = [x.filename for x in infos]
        global_metadata = [n for n in names if n.endswith("global-metadata.dat")]
        bundles = [n for n in names if n.startswith("assets/aa/") and n.endswith(".bundle")]

        report["indicators"] = {
            "zip_entries": len(infos),
            "android_manifest": "AndroidManifest.xml" in names,
            "libil2cpp_arm64": "lib/arm64-v8a/libil2cpp.so" in names,
            "libunity_arm64": "lib/arm64-v8a/libunity.so" in names,
            "global_metadata_count": len(global_metadata),
            "global_metadata_paths": global_metadata,
            "addressables_files": sum(1 for n in names if n.startswith("assets/aa/")),
            "addressable_bundles": len(bundles),
            "network_security_config": any(
                n.endswith("res/xml/network_security_config.xml") for n in names
            ),
        }

        # Endpoint strings are expected in Unity Addressables. XML/JSON/TXT are
        # also cheap and useful to scan. Native .so files are intentionally not
        # scanned here; deeper IL2CPP analysis is a separate phase.
        candidates = [
            x for x in infos
            if x.filename.startswith("assets/aa/")
            or x.filename.endswith(".xml")
            or x.filename.endswith(".json")
            or x.filename.endswith(".txt")
        ]

        hits: list[dict[str, object]] = []
        for info in candidates:
            try:
                with zf.open(info, "r") as stream:
                    digest, size, offsets = scan_stream(stream)
            except Exception:
                continue
            if offsets:
                hits.append(
                    {
                        "file": info.filename,
                        "sha256": digest,
                        "compressed_size": info.compress_size,
                        "uncompressed_size": size,
                        "offsets": offsets,
                    }
                )
        report["host_hits"] = hits

    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("apk", help="Caminho para o APK local")
    ap.add_argument("--json-out", help="Salvar relatório JSON sanitizado")
    ap.add_argument("--md-out", help="Salvar relatório Markdown sanitizado")
    args = ap.parse_args()

    apk = Path(args.apk).expanduser().resolve()
    if not apk.is_file():
        print(f"ERRO: APK não encontrado: {apk}")
        return 2

    try:
        report = analyze(apk)
    except zipfile.BadZipFile:
        print("ERRO: arquivo não é um APK/ZIP válido.")
        return 2

    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    if args.md_out:
        write_markdown(report, Path(args.md_out))

    pkg = report.get("package", {})
    if isinstance(pkg, dict) and pkg:
        print("\nResumo:")
        print(f"  package:     {pkg.get('name', '?')}")
        print(f"  versionName: {pkg.get('versionName', '?')}")
        print(f"  versionCode: {pkg.get('versionCode', '?')}")
    else:
        print("\nDica: aapt/aapt2 no PATH acrescenta package e version ao relatório.")

    if report.get("host_hits"):
        print("Hosts conhecidos encontrados; offsets registrados no relatório sanitizado.")
    else:
        print("Nenhum host conhecido encontrado; será necessária análise IL2CPP/bundle adicional.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
