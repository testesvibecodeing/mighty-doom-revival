#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

from verify_patched_apk import scan_apk

GEAR_HOST = "international.gear.bethesda.net"
AUX_HOST = "slayersclub.bethesda.net"
TARGET = "doom.debruinsistemas.com.br"


def build_apk(path: Path, bundle_payload: bytes = b"", metadata_payload: bytes = b"") -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("AndroidManifest.xml", b"manifest")
        archive.writestr("assets/aa/Android/catalog.bundle", bundle_payload)
        archive.writestr(
            "assets/bin/Data/Managed/Metadata/global-metadata.dat",
            metadata_payload,
        )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # Realistic happy path: the redirect can live only in IL2CPP metadata,
        # and an unrelated Slayers Club URL may remain elsewhere in the APK.
        good = root / "good.apk"
        build_apk(
            good,
            bundle_payload=f"https://{AUX_HOST}/news".encode("ascii"),
            metadata_payload=f"https://u00@{TARGET}/collections/doom".encode("ascii"),
        )
        result = scan_apk(good, TARGET)
        assert result["target_occurrences"] == 1
        assert result["official_occurrences"] == 0
        assert result["known_host_occurrences"] == 1
        assert result["known_host_hits"][0]["host"] == AUX_HOST

        # A stale Gear API reference must still fail the final gate even when
        # the Revival hostname is present somewhere else.
        stale = root / "stale.apk"
        build_apk(
            stale,
            bundle_payload=f"https://{TARGET}/data".encode("ascii"),
            metadata_payload=f"https://{GEAR_HOST}/collections/doom".encode("ascii"),
        )
        result = scan_apk(stale, TARGET)
        assert result["target_occurrences"] == 1
        assert result["official_occurrences"] == 1
        assert result["forbidden_endpoint_hits"][0]["host"] == GEAR_HOST

        missing = root / "missing.apk"
        build_apk(missing, metadata_payload=b"no endpoint here")
        result = scan_apk(missing, TARGET)
        assert result["target_occurrences"] == 0
        assert result["official_occurrences"] == 0

    print("verify_patched_apk Gear endpoint regression: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
