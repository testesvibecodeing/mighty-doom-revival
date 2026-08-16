#!/usr/bin/env python3
"""Local-only APK inventory for the Mighty DOOM preservation project.

This script does not upload or extract proprietary game data into the repository.
It prints hashes, file names and technical indicators useful for interoperability.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

KNOWN_HOSTS = (
    b"slayersclub.bethesda.net",
    b"game.9095be396f3547555fe1039cbc894c88.net",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def try_aapt(apk: Path) -> dict[str, str]:
    """Use aapt/aapt2 if available to read package/version without extra deps."""
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


def main() -> int:
    if len(sys.argv) != 2:
        print("Uso: python scripts/analyze_apk.py caminho\\arquivo.apk")
        return 2

    apk = Path(sys.argv[1]).expanduser().resolve()
    if not apk.is_file():
        print(f"ERRO: APK não encontrado: {apk}")
        return 2

    report: dict[str, object] = {
        "file": apk.name,
        "size_bytes": apk.stat().st_size,
        "sha256": sha256_file(apk),
        "package": try_aapt(apk),
        "indicators": {},
        "host_hits": [],
    }

    try:
        with zipfile.ZipFile(apk, "r") as zf:
            names = zf.namelist()
            indicators = {
                "android_manifest": "AndroidManifest.xml" in names,
                "libil2cpp_arm64": "lib/arm64-v8a/libil2cpp.so" in names,
                "libunity_arm64": "lib/arm64-v8a/libunity.so" in names,
                "global_metadata": any(n.endswith("global-metadata.dat") for n in names),
                "addressables_files": sum(1 for n in names if n.startswith("assets/aa/")),
                "network_security_config": any(
                    n.endswith("res/xml/network_security_config.xml") for n in names
                ),
            }
            report["indicators"] = indicators

            hits: list[dict[str, object]] = []
            # Search the most relevant areas first. Reading a 587 MB APK can take a while.
            candidates = [
                n for n in names
                if n.startswith("assets/aa/")
                or n.endswith(".xml")
                or n.endswith(".json")
                or n.endswith(".txt")
            ]
            for name in candidates:
                try:
                    data = zf.read(name)
                except Exception:
                    continue
                for host in KNOWN_HOSTS:
                    count = data.count(host)
                    if count:
                        hits.append(
                            {
                                "file": name,
                                "host": host.decode("ascii"),
                                "count": count,
                                "uncompressed_size": len(data),
                            }
                        )
            report["host_hits"] = hits
    except zipfile.BadZipFile:
        print("ERRO: arquivo não é um APK/ZIP válido.")
        return 2

    print(json.dumps(report, indent=2, ensure_ascii=False))

    pkg = report.get("package") or {}
    if isinstance(pkg, dict) and pkg:
        print("\nResumo:")
        print(f"  package:     {pkg.get('name', '?')}")
        print(f"  versionName: {pkg.get('versionName', '?')}")
        print(f"  versionCode: {pkg.get('versionCode', '?')}")
    else:
        print("\nDica: adicione 'aapt' ou 'aapt2' ao PATH para exibir package/version.")

    if report["host_hits"]:
        print("\nHosts conhecidos encontrados. O APK é um bom candidato para o patcher.")
    else:
        print("\nNenhum host conhecido apareceu nas áreas pesquisadas; será necessária análise adicional.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
