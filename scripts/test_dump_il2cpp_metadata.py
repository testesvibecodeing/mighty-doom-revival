#!/usr/bin/env python3
"""Testes do extrator dump_il2cpp_metadata.py com metadata sintético mínimo."""
from __future__ import annotations

import struct
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dump_il2cpp_metadata as dump  # noqa: E402


def build_synthetic_metadata(literals: list[bytes], filler: bytes = b"\x00" * 16) -> bytes:
    """Monta um global-metadata.dat v29 mínimo com a tabela de literals dada."""
    data_blob = b"".join(literals)
    table = b"".join(struct.pack("<II", len(item), offset) for offset, item in
                     ((sum(len(x) for x in literals[:i]), item) for i, item in enumerate(literals)))
    header_size = 8 + 8 * len(dump.HEADER_FIELDS)
    literal_offset = header_size
    literal_data_offset = literal_offset + len(table)
    string_offset = literal_data_offset + len(data_blob)

    out = bytearray()
    out += struct.pack("<Ii", dump.EXPECTED_SANITY, dump.EXPECTED_VERSION)
    out += struct.pack("<Ii", literal_offset, len(table))
    out += struct.pack("<Ii", literal_data_offset, len(data_blob))
    out += struct.pack("<Ii", string_offset, len(filler))
    for _ in dump.HEADER_FIELDS[3:]:
        out += struct.pack("<Ii", 0, 0)
    assert len(out) == header_size
    out += table + data_blob + filler
    return bytes(out)


def test_routes_from_literals(tmp: Path) -> None:
    meta = tmp / "global-metadata.dat"
    meta.write_bytes(build_synthetic_metadata([
        b"game/auth/register",
        b"Ok button label",
        b"game/chapters/start",
        b"gameplay tips",          # com espaço: não é rota
        b"game/store/get",
        b"game/auth/register",     # duplicata no literal stream vira uma rota
    ]))
    result = dump.extract_routes(meta)
    assert result["routes"] == [
        "game/auth/register", "game/chapters/start", "game/store/get"
    ], result["routes"]
    assert result["string_literals"] == 6


def test_routes_from_apk(tmp: Path) -> None:
    apk = tmp / "game.apk"
    with zipfile.ZipFile(apk, "w") as zf:
        zf.writestr(dump.METADATA_ENTRY, build_synthetic_metadata([b"game/talents/buy"]))
    result = dump.extract_routes(apk)
    assert result["routes"] == ["game/talents/buy"]


def test_rejects_wrong_sanity(tmp: Path) -> None:
    meta = tmp / "bad.dat"
    meta.write_bytes(struct.pack("<Ii", 0xDEADBEEF, 29) + b"\x00" * 64)
    try:
        dump.extract_routes(meta)
    except ValueError as exc:
        assert "sanity" in str(exc)
    else:
        raise AssertionError("deveria rejeitar sanity inválido")


def test_rejects_wrong_version(tmp: Path) -> None:
    meta = tmp / "bad.dat"
    meta.write_bytes(struct.pack("<Ii", dump.EXPECTED_SANITY, 31) + b"\x00" * 64)
    try:
        dump.extract_routes(meta)
    except ValueError as exc:
        assert "versão" in str(exc)
    else:
        raise AssertionError("deveria rejeitar versão diferente de 29")


def main() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as name:
        tmp = Path(name)
        for test in (test_routes_from_literals, test_routes_from_apk,
                     test_rejects_wrong_sanity, test_rejects_wrong_version):
            test(tmp)
            print(f"[OK] {test.__name__}")
    print("test_dump_il2cpp_metadata: 4/4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
