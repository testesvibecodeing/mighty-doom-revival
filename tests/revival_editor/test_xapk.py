#!/usr/bin/env python3
"""Regressão da importação XAPK (fase 4: fluxo separado do APK principal).

XAPK sintético = ZIP com manifest.json + base.apk + splits + obb. O que estes
testes travam:

- base/splits/OBBs vêm do manifest.json, não do nome de arquivo;
- manifest que lista arquivo ausente, XAPK sem manifest, sem base, ou arquivo
  que nem é ZIP → `XapkError` — recusar, nunca adivinhar;
- extração grava só o base APK, sem `.parcial` sobrando.

Execução: python tests/revival_editor/test_xapk.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from revival_editor.xapk import XapkError, extract_base_apk, inspect_xapk  # noqa: E402


def xapk_sintetico(
    destino: Path,
    *,
    splits: tuple[str, ...] = ("split_config.arm64_v8a.apk",),
    com_manifest: bool = True,
    com_base: bool = True,
    manifest_extra: dict | None = None,
    listar_fantasma: bool = False,
) -> Path:
    manifest = {
        "xapk_version": 2,
        "package_name": "com.bethsoft.ubu",
        "name": "Mighty DOOM",
        "version_code": "84862",
        "version_name": "1.13.1",
        "split_apks": [],
        "expansions": [{"file": "main.com.bethsoft.ubu.obb"}],
    }
    with zipfile.ZipFile(destino, "w") as zf:
        if com_base:
            manifest["split_apks"].append({"file": "base.apk", "id": "base"})
            zf.writestr("base.apk", b"APK-BASE-CONTEUDO")
        for split in splits:
            manifest["split_apks"].append({"file": split, "id": split.removeprefix("split_").removesuffix(".apk")})
            zf.writestr(split, b"SPLIT")
        if listar_fantasma:
            manifest["split_apks"].append({"file": "sumiu.apk", "id": "fantasma"})
        if manifest_extra:
            manifest.update(manifest_extra)
        if com_manifest:
            zf.writestr("manifest.json", __import__("json").dumps(manifest))
        zf.writestr("main.com.bethsoft.ubu.obb", b"OBB")
    return destino


class TestInspectXapk(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_manifest_completo(self) -> None:
        info = inspect_xapk(xapk_sintetico(self.dir / "jogo.xapk"))
        self.assertEqual(info.package_name, "com.bethsoft.ubu")
        self.assertEqual(info.version_name, "1.13.1")
        self.assertEqual(info.version_code, "84862")
        self.assertEqual(info.base_apk, "base.apk")
        self.assertEqual(info.splits, ["split_config.arm64_v8a.apk"])
        self.assertEqual(info.obbs, ["main.com.bethsoft.ubu.obb"])
        self.assertTrue(info.has_splits)

    def test_base_identificado_pelo_id_nao_pelo_nome(self) -> None:
        """Se o manifest chamar o base de outro nome, o id manda."""
        destino = self.dir / "renomeado.xapk"
        with zipfile.ZipFile(destino, "w") as zf:
            import json

            zf.writestr("jogo-principal.apk", b"BASE")
            zf.writestr("split_config.en.apk", b"SPLIT")
            zf.writestr(
                "manifest.json",
                json.dumps({
                    "package_name": "x",
                    "split_apks": [
                        {"file": "jogo-principal.apk", "id": "base"},
                        {"file": "split_config.en.apk", "id": "config.en"},
                    ],
                }),
            )
        info = inspect_xapk(destino)
        self.assertEqual(info.base_apk, "jogo-principal.apk")
        self.assertEqual(info.splits, ["split_config.en.apk"])

    def test_sem_splits(self) -> None:
        info = inspect_xapk(xapk_sintetico(self.dir / "mono.xapk", splits=()))
        self.assertFalse(info.has_splits)
        self.assertEqual(info.splits, [])

    def test_entrada_unica_sem_id_base(self) -> None:
        destino = self.dir / "unico.xapk"
        with zipfile.ZipFile(destino, "w") as zf:
            import json

            zf.writestr("app.apk", b"BASE")
            zf.writestr("manifest.json", json.dumps({"package_name": "x", "split_apks": [{"file": "app.apk"}]}))
        info = inspect_xapk(destino)
        self.assertEqual(info.base_apk, "app.apk")

    def test_manifest_lista_arquivo_ausente(self) -> None:
        with self.assertRaises(XapkError) as cm:
            inspect_xapk(xapk_sintetico(self.dir / "fantasma.xapk", listar_fantasma=True))
        self.assertIn("sumiu.apk", str(cm.exception))

    def test_sem_manifest(self) -> None:
        with self.assertRaises(XapkError):
            inspect_xapk(xapk_sintetico(self.dir / "sem-manifest.xapk", com_manifest=False))

    def test_sem_base_e_recusado(self) -> None:
        """Dois splits e nenhum base: recusar em vez de escolher um."""
        destino = self.dir / "so-splits.xapk"
        with zipfile.ZipFile(destino, "w") as zf:
            import json

            zf.writestr("split_config.arm64_v8a.apk", b"S1")
            zf.writestr("split_config.en.apk", b"S2")
            zf.writestr(
                "manifest.json",
                json.dumps({
                    "package_name": "x",
                    "split_apks": [
                        {"file": "split_config.arm64_v8a.apk", "id": "config.arm64_v8a"},
                        {"file": "split_config.en.apk", "id": "config.en"},
                    ],
                }),
            )
        with self.assertRaises(XapkError):
            inspect_xapk(destino)

    def test_nao_e_zip(self) -> None:
        lixo = self.dir / "lixo.xapk"
        lixo.write_bytes(b"definitivamente nao e um zip")
        with self.assertRaises(XapkError):
            inspect_xapk(lixo)

    def test_arquivo_ausente(self) -> None:
        with self.assertRaises(XapkError):
            inspect_xapk(self.dir / "nao-existe.xapk")


class TestExtractBaseApk(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_extrai_somente_o_base(self) -> None:
        info = inspect_xapk(xapk_sintetico(self.dir / "jogo.xapk"))
        destino = self.dir / "proj" / "input"
        base = extract_base_apk(info, destino)
        self.assertEqual(base, destino / "base.apk")
        self.assertEqual(base.read_bytes(), b"APK-BASE-CONTEUDO")
        self.assertFalse((destino / "base.apk.parcial").exists(), "temporário não sobra")
        # splits e obb ficam no XAPK — não são extraídos
        self.assertEqual(sorted(p.name for p in destino.iterdir()), ["base.apk"])

    def test_reextracao_substitui_atomicamente(self) -> None:
        info = inspect_xapk(xapk_sintetico(self.dir / "jogo.xapk"))
        destino = self.dir / "input"
        primeiro = extract_base_apk(info, destino)
        segundo = extract_base_apk(info, destino)
        self.assertEqual(primeiro, segundo)
        self.assertEqual(segundo.read_bytes(), b"APK-BASE-CONTEUDO")


if __name__ == "__main__":
    unittest.main(verbosity=2)
