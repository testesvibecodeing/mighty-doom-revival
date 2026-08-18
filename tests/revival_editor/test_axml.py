#!/usr/bin/env python3
"""Regressão do parser AXML (fecha a lacuna do aapt — fase 4).

O APK sintético monta um AndroidManifest.xml binário de verdade (string pool
UTF-8/UTF-16 + elemento manifest), byte a byte, para provar que a medição de
package/versionName/versionCode não depende de ferramenta externa.

Caso central: `test_analyze_apk_medido_via_axml_bate_o_alvo` — sem aapt, com
manifest legível, `matches_target` finalmente pode ser True. Desconhecido
continua não sendo aprovação (o teste do lixo de bytes garante).

Execução: python tests/revival_editor/test_axml.py
"""
from __future__ import annotations

import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from test_services import apk_sintetico, metadata_sintetico, METADATA_MEMBER  # noqa: E402

from revival_editor.axml import (  # noqa: E402
    AxmlError,
    parse_axml_manifest,
    read_manifest_facts,
)

TYPE_STRING = 0x03
TYPE_INT_DEC = 0x10
UTF8_FLAG = 0x0100
_NADA = 0xFFFFFFFF


def _len8(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    return bytes([0x80 | (n >> 8), n & 0xFF])


def _pool(strings: list[str], *, utf16: bool = False) -> bytes:
    corpos = []
    for texto in strings:
        if utf16:
            corpo = struct.pack("<H", len(texto)) + texto.encode("utf-16-le") + b"\x00\x00"
        else:
            bruto = texto.encode("utf-8")
            corpo = _len8(len(texto)) + _len8(len(bruto)) + bruto + b"\x00"
        corpos.append(corpo)
    deslocamentos: list[int] = []
    acumulado = 0
    for corpo in corpos:
        deslocamentos.append(acumulado)
        acumulado += len(corpo)
    inicio = 28 + 4 * len(strings)
    flags = 0 if utf16 else UTF8_FLAG
    cabecalho = struct.pack(
        "<HHIIIIII", 0x0001, 28, inicio + acumulado, len(strings), 0, flags, inicio, 0
    )
    return cabecalho + b"".join(struct.pack("<I", d) for d in deslocamentos) + b"".join(corpos)


def _elemento(nome_idx: int, atributos: list[tuple[int, int, int, int]]) -> bytes:
    corpo = struct.pack("<II", _NADA, nome_idx)
    corpo += struct.pack("<HHHHHH", 20, 20, len(atributos), 0, 0, 0)
    for attr_nome, raw, tipo, dado in atributos:
        corpo += struct.pack("<III", _NADA, attr_nome, raw)
        corpo += struct.pack("<HBBI", 8, 0, tipo, dado)
    return (
        struct.pack("<HHI", 0x0102, 16, 16 + len(corpo))
        + struct.pack("<II", 1, _NADA)
        + corpo
    )


def axml_manifest(
    package: str = "com.bethsoft.ubu",
    version_code: int = 84862,
    version_name: str = "1.13.1",
    *,
    utf16: bool = False,
    com_version_name: bool = True,
) -> bytes:
    strings = ["manifest", "package", "versionCode", "versionName", package]
    if com_version_name:
        strings.append(version_name)
    indices = {texto: i for i, texto in enumerate(strings)}

    atributos = [
        (indices["package"], indices[package], TYPE_STRING, indices[package]),
        (indices["versionCode"], _NADA, TYPE_INT_DEC, version_code),
    ]
    if com_version_name:
        atributos.append(
            (indices["versionName"], indices[version_name], TYPE_STRING, indices[version_name])
        )

    pool = _pool(strings, utf16=utf16)
    elemento = _elemento(indices["manifest"], atributos)
    total = 8 + len(pool) + len(elemento)
    return struct.pack("<HHI", 0x0003, 8, total) + pool + elemento


class TestParseAxmlManifest(unittest.TestCase):
    def test_manifest_utf8_completo(self) -> None:
        fatos = parse_axml_manifest(axml_manifest())
        self.assertEqual(
            fatos, {"package": "com.bethsoft.ubu", "versionName": "1.13.1", "versionCode": "84862"}
        )

    def test_manifest_utf16_completo(self) -> None:
        fatos = parse_axml_manifest(axml_manifest(utf16=True))
        self.assertEqual(fatos["package"], "com.bethsoft.ubu")
        self.assertEqual(fatos["versionCode"], "84862")

    def test_version_name_unicode_sobrevive(self) -> None:
        fatos = parse_axml_manifest(axml_manifest(version_name="1.13.1-çã", utf16=False))
        self.assertEqual(fatos["versionName"], "1.13.1-çã")

    def test_sem_version_name_nao_inventa(self) -> None:
        fatos = parse_axml_manifest(axml_manifest(com_version_name=False))
        self.assertNotIn("versionName", fatos)

    def test_version_code_grande_positivo(self) -> None:
        fatos = parse_axml_manifest(axml_manifest(version_code=2100000000))
        self.assertEqual(fatos["versionCode"], "2100000000")

    def test_lixo_de_bytes_e_recusado(self) -> None:
        with self.assertRaises(AxmlError):
            parse_axml_manifest(b"\x03\x00\x08\x00fake-axml")

    def test_truncado_e_recusado(self) -> None:
        inteiro = axml_manifest()
        with self.assertRaises(AxmlError):
            parse_axml_manifest(inteiro[: len(inteiro) // 2])

    def test_arquivo_vazio(self) -> None:
        with self.assertRaises(AxmlError):
            parse_axml_manifest(b"")


class TestReadManifestFacts(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_le_do_zip_do_apk(self) -> None:
        apk = self.dir / "com-axml.apk"
        with zipfile.ZipFile(apk, "w") as zf:
            zf.writestr("AndroidManifest.xml", axml_manifest())
            zf.writestr("lib/arm64-v8a/libil2cpp.so", b"\x7fELF")
        fatos = read_manifest_facts(apk)
        self.assertEqual(fatos["package"], "com.bethsoft.ubu")

    def test_apk_sem_manifest_avisa(self) -> None:
        apk = self.dir / "vazio.apk"
        with zipfile.ZipFile(apk, "w") as zf:
            zf.writestr("qualquer.txt", b"nada")
        with self.assertRaises(AxmlError):
            read_manifest_facts(apk)


class TestIntegracaoAnalyze(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _apk_com_manifest_real(self, destino: Path) -> Path:
        """APK sintético do test_services, mas com manifest AXML legível."""
        apk_sintetico(destino, metadata=metadata_sintetico())
        # reescreve o membro do manifest com conteúdo válido
        temporario = destino.with_suffix(".rezip")
        with zipfile.ZipFile(destino, "r") as origem, zipfile.ZipFile(temporario, "w") as destino_zip:
            for info in origem.infolist():
                dados = origem.read(info.filename)
                if info.filename == "AndroidManifest.xml":
                    dados = axml_manifest()
                destino_zip.writestr(info, dados)
        temporario.replace(destino)
        return destino

    def test_analyze_apk_medido_via_axml_bate_o_alvo(self) -> None:
        """A lacuna do aapt fechou: sem aapt, alvo 1.13.1 é CONFIRMADO."""
        from revival_editor.services import analyze_apk
        import analyze_apk as cli

        apk = self._apk_com_manifest_real(self.dir / "alvo.apk")
        with mock.patch.object(cli, "try_aapt", lambda _: {}):
            resultado = analyze_apk(apk)
        self.assertEqual(resultado.package, "com.bethsoft.ubu")
        self.assertEqual(resultado.version_name, "1.13.1")
        self.assertEqual(resultado.version_code, "84862")
        self.assertNotIn("package (não medido)", " ".join(resultado.unknown))
        self.assertTrue(
            resultado.matches_target,
            f"alvo deveria bater: unknown={resultado.unknown} div={resultado.divergences}",
        )

    def test_manifest_ilegivel_mantem_desconhecido(self) -> None:
        """Garbage no manifest continua sendo 'não medido' — nunca chute."""
        from revival_editor.services import analyze_apk
        import analyze_apk as cli

        apk = apk_sintetico(self.dir / "lixo.apk", metadata=metadata_sintetico())
        with mock.patch.object(cli, "try_aapt", lambda _: {}):
            resultado = analyze_apk(apk)
        self.assertTrue(any("package" in u for u in resultado.unknown))
        self.assertFalse(resultado.matches_target)


if __name__ == "__main__":
    unittest.main(verbosity=2)
