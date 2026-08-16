#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "scripts" / "patch_apk.py"
GEAR_HOST = "international.gear.bethesda.net"
AUX_HOST = "slayersclub.bethesda.net"
TARGET_HOST = "doom.debruinsistemas.com.br"


def make_tree(root: Path) -> tuple[Path, Path]:
    decoded = root / "decoded"
    metadata = decoded / "assets" / "bin" / "Data" / "Managed" / "Metadata" / "global-metadata.dat"
    metadata.parent.mkdir(parents=True)
    metadata.write_bytes(
        b"prefix\x00"
        + f"https://{GEAR_HOST}/collections/doom".encode("ascii")
        + b"\x00club\x00"
        + f"https://{AUX_HOST}/".encode("ascii")
        + b"\x00tail"
    )

    manifest = decoded / "AndroidManifest.xml"
    manifest.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.bethsoft.ubu">\n'
        '  <application android:label="Mighty DOOM"/>\n'
        '</manifest>\n',
        encoding="utf-8",
    )
    return decoded, metadata


def main() -> int:
    # The real deploy hostname is longer than slayersclub.bethesda.net (27 vs
    # 24 bytes) but shorter than the actual Gear API host (31 bytes). Before
    # endpoint selection was introduced, the unrelated Slayers Club URL made
    # this otherwise-safe patch fail with return code 4.
    assert len(TARGET_HOST.encode("ascii")) > len(AUX_HOST.encode("ascii"))
    assert len(TARGET_HOST.encode("ascii")) < len(GEAR_HOST.encode("ascii"))

    with tempfile.TemporaryDirectory(prefix="mighty-doom-primary-api-") as tmp:
        root = Path(tmp)
        decoded, metadata = make_tree(root)
        report = root / "patch-report.json"
        original_size = metadata.stat().st_size

        cp = subprocess.run(
            [
                sys.executable,
                str(PATCHER),
                "--decoded",
                str(decoded),
                "--server",
                TARGET_HOST,
                "--report",
                str(report),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if cp.returncode != 0:
            print(cp.stdout)
            print(cp.stderr, file=sys.stderr)
            raise AssertionError(f"patcher returned {cp.returncode}")

        data = metadata.read_bytes()
        assert metadata.stat().st_size == original_size
        assert GEAR_HOST.encode("ascii") not in data
        assert f"https://u00@{TARGET_HOST}/collections/doom".encode("ascii") in data

        # Ancillary Bethesda URLs are not gameplay API endpoints and must stay
        # byte-for-byte untouched when Gear is present.
        assert f"https://{AUX_HOST}/".encode("ascii") in data

        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["status"] == "ok"
        assert {hit["host"] for hit in payload["patch_target_hits"]} == {GEAR_HOST}
        assert {hit["host"] for hit in payload["ignored_known_host_hits"]} == {AUX_HOST}
        assert payload["unsupported_occurrences"] == []

    print("Mighty DOOM primary Gear API host selection regression: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
