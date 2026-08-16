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
ANDROID_NS = "http://schemas.android.com/apk/res/android"


def make_tree(root: Path) -> Path:
    decoded = root / "decoded"
    bundle = decoded / "assets" / "aa" / "synthetic.bundle"
    bundle.parent.mkdir(parents=True)
    bundle.write_bytes(
        b"UnityFS\x00synthetic\x00https://" + OFFICIAL_HOST.encode("ascii") + b"/game/auth/register\x00tail"
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
        original_size = bundle.stat().st_size
        report = root / "report.json"

        success = run_patch(decoded, TEST_HOST, report)
        if success.returncode != 0:
            print(success.stdout)
            print(success.stderr, file=sys.stderr)
            raise AssertionError(f"Patch seguro falhou com código {success.returncode}")

        data = bundle.read_bytes()
        assert bundle.stat().st_size == original_size
        assert OFFICIAL_HOST.encode("ascii") not in data
        assert TEST_HOST.encode("ascii") in data

        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["status"] == "ok"
        assert payload["binary_patched_files"] == ["assets/aa/synthetic.bundle"]

        tree = ET.parse(decoded / "AndroidManifest.xml")
        app = tree.getroot().find("application")
        assert app is not None
        assert app.get(f"{{{ANDROID_NS}}}networkSecurityConfig") == "@xml/network_security_config"
        network_xml = (decoded / "res" / "xml" / "network_security_config.xml").read_text(encoding="utf-8")
        assert TEST_HOST in network_xml
        assert OFFICIAL_HOST not in network_xml

    with tempfile.TemporaryDirectory(prefix="mighty-doom-patch-block-") as tmp:
        root = Path(tmp)
        decoded = make_tree(root)
        bundle = decoded / "assets" / "aa" / "synthetic.bundle"
        before = bundle.read_bytes()
        report = root / "report.json"
        blocked = run_patch(decoded, "doom.example.com", report)
        assert blocked.returncode == 4
        assert bundle.read_bytes() == before
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["status"] == "needs_bundle_aware_patch"

    print("Mighty DOOM Revival APK hostname patch test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
