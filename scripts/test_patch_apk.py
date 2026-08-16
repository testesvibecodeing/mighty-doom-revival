#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "scripts" / "patch_apk.py"
OFFICIAL_HOST = "slayersclub.bethesda.net"
TEST_HOST = "d.debruinsistemas.com.br"
SHORT_HOST = "doom.sualoja.app.br"
LONG_HOST = "doom.debruinsistemas.com.br"
ANDROID_NS = "http://schemas.android.com/apk/res/android"


def make_tree(root: Path) -> Path:
    decoded = root / "decoded"
    bundle = decoded / "assets" / "aa" / "synthetic.bundle"
    bundle.parent.mkdir(parents=True)
    bundle.write_bytes(
        b"UnityFS\x00synthetic\x00https://" + OFFICIAL_HOST.encode("ascii") + b"/game/auth/register\x00tail"
    )

    # Real 1.13.1 APKs carry the hostname as an IL2CPP string-literal inside
    # global-metadata.dat, not inside an Addressables bundle. The literal is
    # the full URL "https://<host>/" (literals are packed back-to-back with no
    # separator), which is exactly what the same-length URL patch relies on.
    metadata_dir = decoded / "assets" / "bin" / "Data" / "Managed" / "Metadata"
    metadata_dir.mkdir(parents=True)
    metadata = metadata_dir / "global-metadata.dat"
    metadata.write_bytes(
        b"\xaf\x1b\xb1\xfa"
        + b"\x00" * 60
        + b"https://"
        + OFFICIAL_HOST.encode("ascii")
        + b"/"
        + b"https://twitter.example\x00"
        + b"\x00" * 60
    )

    manifest = decoded / "AndroidManifest.xml"
    manifest.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.bethsoft.ubu">\n'
        '  <application android:label="Mighty DOOM"/>\n'
        '</manifest>\n',
        encoding="utf-8",
    )
    return decoded


def run_patch(decoded: Path, host: str, report: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(PATCHER),
            "--decoded",
            str(decoded),
            "--server",
            host,
            "--report",
            str(report),
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    if len(OFFICIAL_HOST.encode("ascii")) != len(TEST_HOST.encode("ascii")):
        raise AssertionError("Host de teste precisa manter o tamanho binário do host oficial")

    with tempfile.TemporaryDirectory(prefix="mighty-doom-patch-") as tmp:
        root = Path(tmp)
        decoded = make_tree(root)
        bundle = decoded / "assets" / "aa" / "synthetic.bundle"
        metadata = decoded / "assets" / "bin" / "Data" / "Managed" / "Metadata" / "global-metadata.dat"
        original_bundle_size = bundle.stat().st_size
        original_metadata_size = metadata.stat().st_size
        report = root / "report.json"

        success = run_patch(decoded, TEST_HOST, report)
        if success.returncode != 0:
            print(success.stdout)
            print(success.stderr, file=sys.stderr)
            raise AssertionError(f"Patch seguro falhou com código {success.returncode}")

        data = bundle.read_bytes()
        assert bundle.stat().st_size == original_bundle_size
        assert OFFICIAL_HOST.encode("ascii") not in data
        assert TEST_HOST.encode("ascii") in data

        metadata_data = metadata.read_bytes()
        assert metadata.stat().st_size == original_metadata_size
        assert OFFICIAL_HOST.encode("ascii") not in metadata_data
        assert TEST_HOST.encode("ascii") in metadata_data

        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["status"] == "ok"
        assert payload["binary_patched_files"] == [
            "assets/aa/synthetic.bundle",
            "assets/bin/Data/Managed/Metadata/global-metadata.dat",
        ]

        tree = ET.parse(decoded / "AndroidManifest.xml")
        app = tree.getroot().find("application")
        assert app is not None
        assert app.get(f"{{{ANDROID_NS}}}networkSecurityConfig") == "@xml/network_security_config"
        network_xml = (decoded / "res" / "xml" / "network_security_config.xml").read_text(encoding="utf-8")
        assert TEST_HOST in network_xml
        assert OFFICIAL_HOST not in network_xml

    # Cenário 2: hostname MENOR que o oficial (o caso real de deploy,
    # doom.sualoja.app.br com 19 bytes) deve ser aceito com padding de
    # userinfo na URL, mantendo cada arquivo com o mesmo tamanho em bytes.
    with tempfile.TemporaryDirectory(prefix="mighty-doom-patch-short-") as tmp:
        root = Path(tmp)
        decoded = make_tree(root)
        bundle = decoded / "assets" / "aa" / "synthetic.bundle"
        metadata = decoded / "assets" / "bin" / "Data" / "Managed" / "Metadata" / "global-metadata.dat"
        original_bundle_size = bundle.stat().st_size
        original_metadata_size = metadata.stat().st_size
        report = root / "report.json"

        shorter = run_patch(decoded, SHORT_HOST, report)
        if shorter.returncode != 0:
            print(shorter.stdout)
            print(shorter.stderr, file=sys.stderr)
            raise AssertionError(f"Patch de host menor falhou com código {shorter.returncode}")

        padded_url = f"https://u000@{SHORT_HOST}/".encode("ascii")
        assert len(padded_url) == len(f"https://{OFFICIAL_HOST}/".encode("ascii"))

        data = bundle.read_bytes()
        assert bundle.stat().st_size == original_bundle_size
        assert OFFICIAL_HOST.encode("ascii") not in data
        assert padded_url in data
        assert padded_url + b"game/auth/register" in data

        metadata_data = metadata.read_bytes()
        assert metadata.stat().st_size == original_metadata_size
        assert OFFICIAL_HOST.encode("ascii") not in metadata_data
        assert padded_url in metadata_data
        assert b"https://twitter.example" in metadata_data  # literal vizinho intacto

        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["status"] == "ok"
        assert not payload["unsupported_occurrences"]

    with tempfile.TemporaryDirectory(prefix="mighty-doom-patch-block-") as tmp:
        root = Path(tmp)
        decoded = make_tree(root)
        bundle = decoded / "assets" / "aa" / "synthetic.bundle"
        metadata = decoded / "assets" / "bin" / "Data" / "Managed" / "Metadata" / "global-metadata.dat"
        bundle_before = bundle.read_bytes()
        metadata_before = metadata.read_bytes()
        report = root / "report.json"
        blocked = run_patch(decoded, LONG_HOST, report)
        assert blocked.returncode == 4
        assert bundle.read_bytes() == bundle_before
        assert metadata.read_bytes() == metadata_before
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["status"] == "needs_bundle_aware_patch"
        assert payload["unsupported_occurrences"]

    print("Mighty DOOM Revival APK hostname patch test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
