#!/usr/bin/env python3
"""O verificador do entregável precisa LER o cleartext, não presumi-lo.

Antes, `scan_insecure_lab_markers` inicializava `cleartext_permitted: false` e
nunca decodificava o AXML — o relatório afirmava `false` sem ter verificado o
atributo. Aqui os três desfechos são exigidos com APKs sintéticos mínimos:

    cleartextTrafficPermitted="true"  -> reprova o entregável (exit 6)
    cleartextTrafficPermitted="false" -> passa
    AXML ilegível                     -> inconclusivo (None), nunca `false`

Nenhum APK proprietário: o AXML é montado byte a byte, com o mesmo construtor
usado em tests/revival_editor/test_axml.py.
"""
from __future__ import annotations

import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from revival_editor.axml import AxmlError, parse_axml_elements  # noqa: E402
from verify_patched_apk import read_cleartext_policy, scan_insecure_lab_markers  # noqa: E402

TYPE_STRING = 0x03
TYPE_BOOL = 0x12
UTF8_FLAG = 0x0100
_NADA = 0xFFFFFFFF


def _len8(n: int) -> bytes:
    return bytes([n]) if n < 0x80 else bytes([0x80 | (n >> 8), n & 0xFF])


def _pool(strings: list[str]) -> bytes:
    corpos = []
    for texto in strings:
        bruto = texto.encode("utf-8")
        corpos.append(_len8(len(texto)) + _len8(len(bruto)) + bruto + b"\x00")
    deslocamentos, acumulado = [], 0
    for corpo in corpos:
        deslocamentos.append(acumulado)
        acumulado += len(corpo)
    inicio = 28 + 4 * len(strings)
    cabecalho = struct.pack("<HHIIIIII", 0x0001, 28, inicio + acumulado,
                            len(strings), 0, UTF8_FLAG, inicio, 0)
    return cabecalho + b"".join(struct.pack("<I", d) for d in deslocamentos) + b"".join(corpos)


def _elemento(nome_idx: int, atributos: list[tuple[int, int, int, int]]) -> bytes:
    corpo = struct.pack("<II", _NADA, nome_idx)
    corpo += struct.pack("<HHHHHH", 20, 20, len(atributos), 0, 0, 0)
    for attr_nome, raw, tipo, dado in atributos:
        corpo += struct.pack("<III", _NADA, attr_nome, raw)
        corpo += struct.pack("<HBBI", 8, 0, tipo, dado)
    return (struct.pack("<HHI", 0x0102, 16, 16 + len(corpo))
            + struct.pack("<II", 1, _NADA) + corpo)


def axml_network_config(*, cleartext: bool) -> bytes:
    """`network_security_config.xml` com o atributo booleano de verdade."""
    strings = ["network-security-config", "domain-config", "cleartextTrafficPermitted",
               "domain", "includeSubdomains"]
    idx = {t: i for i, t in enumerate(strings)}
    pool = _pool(strings)
    corpo = (
        _elemento(idx["network-security-config"], [])
        + _elemento(idx["domain-config"],
                    [(idx["cleartextTrafficPermitted"], _NADA, TYPE_BOOL, 1 if cleartext else 0)])
        + _elemento(idx["domain"], [(idx["includeSubdomains"], _NADA, TYPE_BOOL, 1)])
    )
    return struct.pack("<HHI", 0x0003, 8, 8 + len(pool) + len(corpo)) + pool + corpo


def axml_manifest_minimo() -> bytes:
    strings = ["manifest", "package", "com.bethsoft.ubu"]
    idx = {t: i for i, t in enumerate(strings)}
    pool = _pool(strings)
    corpo = _elemento(idx["manifest"],
                      [(idx["package"], idx["com.bethsoft.ubu"], TYPE_STRING,
                        idx["com.bethsoft.ubu"])])
    return struct.pack("<HHI", 0x0003, 8, 8 + len(pool) + len(corpo)) + pool + corpo


def apk_com_config(destino: Path, config: bytes | None) -> Path:
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("AndroidManifest.xml", axml_manifest_minimo())
        if config is not None:
            z.writestr("res/xml/network_security_config.xml", config)
        z.writestr("assets/bin/Data/Managed/Metadata/global-metadata.dat",
                   b"https://doom.exemplo.br/collections/doom")
    return destino


class TestLeituraDoCleartext(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_true_e_lido_como_true(self):
        apk = apk_com_config(self.dir / "cleartext-true.apk", axml_network_config(cleartext=True))
        r = read_cleartext_policy(apk)
        self.assertIs(r["cleartext_permitted"], True)
        self.assertIn("network_security_config", r["cleartext_source"])

    def test_false_e_lido_como_false(self):
        apk = apk_com_config(self.dir / "cleartext-false.apk", axml_network_config(cleartext=False))
        r = read_cleartext_policy(apk)
        self.assertIs(r["cleartext_permitted"], False)
        self.assertIn("network_security_config", r["cleartext_source"],
                      "o campo só pode ser false depois de ter LIDO o atributo")

    def test_axml_ilegivel_e_inconclusivo_nunca_false(self):
        apk = apk_com_config(self.dir / "quebrado.apk", b"\x03\x00\x08\x00lixo-que-nao-e-axml")
        r = read_cleartext_policy(apk)
        self.assertIsNone(r["cleartext_permitted"],
                          "erro de parse é inconclusivo — false inventado seria mentira")

    def test_sem_config_e_inconclusivo(self):
        apk = apk_com_config(self.dir / "sem-config.apk", None)
        r = read_cleartext_policy(apk)
        self.assertIsNone(r["cleartext_permitted"])
        self.assertIn("nenhum atributo", r["cleartext_source"])


class TestGateDoEntregavel(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_cleartext_true_reprova_o_entregavel(self):
        apk = apk_com_config(self.dir / "lab.apk", axml_network_config(cleartext=True))
        achados = scan_insecure_lab_markers(apk, "doom.exemplo.br")
        self.assertTrue(achados["insecure"], "entregável com cleartext tem que reprovar")
        self.assertIn("cleartextTrafficPermitted=true", achados["reason"])

    def test_cleartext_false_passa(self):
        apk = apk_com_config(self.dir / "final.apk", axml_network_config(cleartext=False))
        achados = scan_insecure_lab_markers(apk, "doom.exemplo.br")
        self.assertFalse(achados["insecure"])
        self.assertIs(achados["cleartext_permitted"], False)

    def test_inconclusivo_nao_reprova_mas_tambem_nao_afirma_false(self):
        apk = apk_com_config(self.dir / "opaco.apk", b"\x03\x00\x08\x00lixo")
        achados = scan_insecure_lab_markers(apk, "doom.exemplo.br")
        self.assertIsNone(achados["cleartext_permitted"])
        self.assertFalse(achados["insecure"], "sem medição não se acusa")


class TestArtefatosReais(unittest.TestCase):
    """Quando os APKs reais existem em work//output (ignorados pelo Git)."""

    ENTREGAVEL = ROOT / "output" / "mighty-doom-revival.apk"
    LAB = ROOT / "work" / "audit-opus" / "rig" / "mighty-doom-revival-LAB-HTTP.apk"

    def test_entregavel_tem_cleartext_false_medido(self):
        if not self.ENTREGAVEL.is_file():
            self.skipTest("APK entregável ausente (output/ não é versionado)")
        self.assertIs(read_cleartext_policy(self.ENTREGAVEL)["cleartext_permitted"], False)

    def test_laboratorio_tem_cleartext_true_medido(self):
        if not self.LAB.is_file():
            self.skipTest("APK de laboratório ausente (work/ não é versionado)")
        r = read_cleartext_policy(self.LAB)
        self.assertIs(r["cleartext_permitted"], True)
        achados = scan_insecure_lab_markers(self.LAB, "doom.sualoja.app.br")
        self.assertTrue(achados["insecure"], "o artefato de laboratório nunca passa como final")


class TestParserGenerico(unittest.TestCase):
    def test_le_todos_os_elementos_nao_so_a_raiz(self):
        elementos = parse_axml_elements(axml_network_config(cleartext=True))
        nomes = [nome for nome, _ in elementos]
        self.assertEqual(nomes, ["network-security-config", "domain-config", "domain"])

    def test_axml_invalido_levanta(self):
        with self.assertRaises(AxmlError):
            parse_axml_elements(b"\x99\x99\x08\x00nada")
        with self.assertRaises(AxmlError):
            parse_axml_elements(b"")


if __name__ == "__main__":
    unittest.main(verbosity=2)
