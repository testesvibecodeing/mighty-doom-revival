#!/usr/bin/env python3
"""Regressão do zeramento de m_Crc no catalog.json do Addressables.

O cliente 1.13.1 valida o CRC de build gravado no catálogo ao carregar um
bundle. Qualquer bundle reserializado pelo patcher precisa do m_Crc zerado no
formato exato do catálogo (JSON UTF-16LE dentro de m_ExtraDataString base64),
preservando o comprimento em bytes para não deslocar os offsets do stream.

Execução: python tests/test_zero_catalog_crc.py (ou python -m unittest).
"""
from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from patch_unity_bundle import zero_catalog_crc  # noqa: E402

BUNDLE_HASH = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
OTHER_HASH = "0f9e8d7c6b5a4938271605f4e3d2c1b0"


def u16(text: str) -> bytes:
    return text.encode("utf-16-le")


def write_catalog(directory: Path, entries: list[dict]) -> Path:
    stream = "".join(json.dumps(entry, separators=(",", ":")) for entry in entries)
    catalog = {"m_ExtraDataString": base64.b64encode(u16(stream)).decode("ascii")}
    path = directory / "catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    return path


def decoded_stream(catalog_path: Path) -> bytes:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    return base64.b64decode(catalog["m_ExtraDataString"])


class ZeroCatalogCrcTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def bundle(self, name: str) -> Path:
        # A função só lê o nome do arquivo; o bundle em si não é aberto.
        return self.dir / name

    def test_zera_digitos_preservando_comprimento(self) -> None:
        catalog = write_catalog(self.dir, [
            {"m_Hash": OTHER_HASH, "m_Crc": 999, "m_Other": 1},
            {"m_Hash": BUNDLE_HASH, "m_Crc": 1234567890, "m_Extra": "x"},
        ])
        before = decoded_stream(catalog)

        result = zero_catalog_crc(catalog, self.bundle(f"scenes_{BUNDLE_HASH}.bundle"))

        self.assertTrue(result.get("zeroed"), result)
        self.assertEqual(result.get("crc_before"), 1234567890)
        after = decoded_stream(catalog)
        self.assertEqual(len(after), len(before), "stream deve manter o comprimento em bytes")

        marker = u16(f'"m_Hash":"{BUNDLE_HASH}"')
        field = after.find(u16('"m_Crc":'), after.find(marker))
        replaced = after[field + len(u16('"m_Crc":')):field + len(u16('"m_Crc":')) + u16("0" * 10).__len__()]
        self.assertEqual(replaced.decode("utf-16-le"), "0" + " " * 9)
        # O objeto vizinho permanece intacto (offsets preservados).
        self.assertIn(u16(f'"m_Hash":"{OTHER_HASH}"'), after)

    def test_json_do_stream_continua_valido(self) -> None:
        catalog = write_catalog(self.dir, [
            {"m_Hash": BUNDLE_HASH, "m_Crc": 4294967295},
        ])
        result = zero_catalog_crc(catalog, self.bundle(f"ui_{BUNDLE_HASH}.bundle"))
        self.assertTrue(result.get("zeroed"), result)

        text = decoded_stream(catalog).decode("utf-16-le")
        entry = json.loads(text)  # espaços entre tokens são JSON válido
        self.assertEqual(entry["m_Crc"], 0)

    def test_crc_ja_zero_nao_reescreve(self) -> None:
        catalog = write_catalog(self.dir, [
            {"m_Hash": BUNDLE_HASH, "m_Crc": 0},
        ])
        original = catalog.read_bytes()

        result = zero_catalog_crc(catalog, self.bundle(f"scenes_{BUNDLE_HASH}.bundle"))

        self.assertTrue(result.get("already_zero"))
        self.assertFalse(result.get("zeroed"))
        self.assertEqual(catalog.read_bytes(), original)

    def test_hash_ausente_no_catalogo(self) -> None:
        catalog = write_catalog(self.dir, [
            {"m_Hash": OTHER_HASH, "m_Crc": 42},
        ])
        result = zero_catalog_crc(catalog, self.bundle(f"scenes_{BUNDLE_HASH}.bundle"))
        self.assertFalse(result.get("zeroed"))
        self.assertIn("não encontrado", result.get("error", ""))

    def test_nome_de_bundle_sem_hash_32hex(self) -> None:
        catalog = write_catalog(self.dir, [{"m_Hash": BUNDLE_HASH, "m_Crc": 42}])
        result = zero_catalog_crc(catalog, self.bundle("scenes.bundle"))
        self.assertFalse(result.get("zeroed"))
        self.assertIn("hash", result.get("error", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
