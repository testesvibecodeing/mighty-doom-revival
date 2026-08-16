#!/usr/bin/env python3
from __future__ import annotations

import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from check_patch_length import check

OFFICIAL_HOST = "slayersclub.bethesda.net"  # 24 bytes


def make_apk(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "assets/aa/synthetic.bundle",
            b"UnityFS\x00https://" + OFFICIAL_HOST.encode("ascii") + b"/game/auth/register\x00",
        )


def main() -> int:
    with TemporaryDirectory(prefix="mighty-doom-check-length-") as tmp:
        apk = Path(tmp) / "synthetic.apk"
        make_apk(apk)

        code, lines = check(apk, "d.debruinsistemas.com.br")  # 24 bytes, same length
        assert code == 0, lines
        assert any("[OK]" in line for line in lines), lines

        code, lines = check(apk, "doom.debruinsistemas.com.br")  # 27 bytes, mismatched
        assert code == 4, lines
        assert any("[BLOQUEADO]" in line for line in lines), lines
        assert any("24" in line for line in lines), lines

        empty_apk = Path(tmp) / "empty.apk"
        with zipfile.ZipFile(empty_apk, "w") as zf:
            zf.writestr("assets/aa/placeholder.txt", b"nothing official here")
        code, lines = check(empty_apk, "doom.debruinsistemas.com.br")
        assert code == 0, lines
        assert any("AVISO" in line for line in lines), lines

    print("Mighty DOOM Revival pre-decode patch-length check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
