#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

from verify_patched_apk import scan_apk


def build_apk(path: Path, payload: bytes) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("AndroidManifest.xml", b"manifest")
        archive.writestr("assets/aa/Android/catalog.bundle", payload)


def main() -> int:
    target = "d.debruinsistemas.com.br"
    official = "slayersclub.bethesda.net"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        good = root / "good.apk"
        build_apk(good, f"https://{target}/game/auth/register".encode("ascii"))
        result = scan_apk(good, target)
        assert result["target_occurrences"] == 1
        assert result["official_occurrences"] == 0

        stale = root / "stale.apk"
        build_apk(
            stale,
            f"https://{target}/data https://{official}/game/auth/register".encode("ascii"),
        )
        result = scan_apk(stale, target)
        assert result["target_occurrences"] == 1
        assert result["official_occurrences"] == 1

        missing = root / "missing.apk"
        build_apk(missing, b"no endpoint here")
        result = scan_apk(missing, target)
        assert result["target_occurrences"] == 0
        assert result["official_occurrences"] == 0

    print("verify_patched_apk regression: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
