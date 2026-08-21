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

import os
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import patch_lab_http as lab  # noqa: E402
from revival_editor.axml import AxmlError, parse_axml_elements  # noqa: E402
from verify_patched_apk import read_cleartext_policy, scan_insecure_lab_markers  # noqa: E402
from test_patch_lab_http import (  # noqa: E402
    HOST_PUBLICO, URL_METADATA, metadata_sintetico, nsc_sintetico,
)

HOST_LAB = "10.0.2.2"

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


class TestArtefatoDeLaboratorioIsolado(unittest.TestCase):
    """Constrói os DOIS artefatos aqui dentro, e mede os dois.

    Antes esta classe abria `work/audit-opus/rig/mighty-doom-revival-LAB-HTTP.apk`
    e `output/mighty-doom-revival.apk` por caminho fixo. Os dois são artefatos
    compartilhados e não versionados: quando o rig regerava um com outro nome,
    o teste passava a medir uma geração antiga (foi o que aconteceu — o arquivo
    daquele caminho era anterior ao patch de NSC e media `false`), e quando o
    rig estava gravando, o ZIP vinha truncado (`BadZipFile`).

    Agora o teste é dono do que mede: monta o APK HTTPS de entrada, deriva o de
    laboratório pelo `patch_lab_http` real, num diretório temporário só dele, e
    exige os dois desfechos opostos no MESMO par de arquivos. Nada de `output/`,
    nada de nome compartilhado, nenhuma dependência de ordem entre jobs.
    """

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.lab_dir = self.dir / "lab"
        self.lab_dir.mkdir()
        # Entrada = o formato do ENTREGÁVEL: wire HTTPS e NSC com cleartext
        # false para o domínio público.
        self.https = self.dir / "entregavel.apk"
        with zipfile.ZipFile(self.https, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(lab.METADATA_ENTRY, metadata_sintetico([URL_METADATA]))
            z.writestr("AndroidManifest.xml", axml_manifest_minimo())
            z.writestr(lab.NSC_ENTRY, nsc_sintetico("doom.sualoja.app.br"))

    def _derivar_lab(self) -> Path:
        saida = self.lab_dir / "isolado-LAB-HTTP.apk"
        lab.patch_apk(apk_in=self.https, apk_out=saida, host=HOST_LAB,
                      from_host=HOST_PUBLICO, allow_insecure_lab=True,
                      lab_dir=self.lab_dir)
        return saida

    def test_entregavel_https_mede_cleartext_false(self):
        r = read_cleartext_policy(self.https)
        self.assertIs(r["cleartext_permitted"], False)
        self.assertIn("network_security_config", r["cleartext_source"])
        self.assertEqual(r["cleartext_unreadable"], [])
        achados = scan_insecure_lab_markers(self.https, "doom.sualoja.app.br")
        self.assertFalse(achados["insecure"], achados["reason"])

    def test_derivado_de_laboratorio_mede_cleartext_true(self):
        lab_apk = self._derivar_lab()
        r = read_cleartext_policy(lab_apk)
        self.assertIs(r["cleartext_permitted"], True,
                      "o APK de laboratório existe justamente para permitir cleartext")
        self.assertIn("network_security_config", r["cleartext_source"])

    def test_derivado_de_laboratorio_nunca_passa_como_entregavel(self):
        lab_apk = self._derivar_lab()
        achados = scan_insecure_lab_markers(lab_apk, HOST_LAB)
        self.assertTrue(achados["insecure"], "artefato de laboratório tem que reprovar")
        self.assertIs(achados["cleartext_permitted"], True)

    def test_os_dois_artefatos_sao_arquivos_diferentes(self):
        # A prova só vale se as duas medições vierem de bytes distintos.
        lab_apk = self._derivar_lab()
        self.assertNotEqual(self.https.read_bytes(), lab_apk.read_bytes())
        self.assertIn("LAB", lab_apk.name.upper())
        self.assertNotIn((ROOT / "output").resolve(), lab_apk.resolve().parents)


class TestFalhaFechada(unittest.TestCase):
    """AXML que não abre nunca vira `false` nem aprovação silenciosa."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_config_ilegivel_e_listado_como_nao_medido(self):
        apk = apk_com_config(self.dir / "opaco.apk", b"\x03\x00\x08\x00lixo")
        r = read_cleartext_policy(apk)
        self.assertIsNone(r["cleartext_permitted"])
        self.assertIn("res/xml/network_security_config.xml", r["cleartext_unreadable"],
                      "um res/xml ilegível não pode ser pulado em silêncio")

    def test_zip_truncado_levanta_em_vez_de_responder_false(self):
        # Um APK sendo gravado por outro job é ZIP truncado. O verificador tem
        # que quebrar aqui, não devolver uma medição inventada.
        completo = apk_com_config(self.dir / "inteiro.apk", axml_network_config(cleartext=False))
        truncado = self.dir / "truncado.apk"
        truncado.write_bytes(completo.read_bytes()[: len(completo.read_bytes()) // 2])
        with self.assertRaises(zipfile.BadZipFile):
            read_cleartext_policy(truncado)


class TestArtefatosReaisSobDemanda(unittest.TestCase):
    """Só roda contra um arquivo que o CHAMADOR nomeou explicitamente.

    Nenhum caminho fixo, nenhum default compartilhado: quem quiser medir um
    artefato real aponta a variável de ambiente para ele. Sem a variável o
    teste é pulado, e por isso não existe mais o modo de falha em que a suíte
    mede um arquivo que outro job acabou de trocar.
    """

    def test_entregavel_apontado_por_env(self):
        alvo = os.environ.get("REVIVAL_VERIFY_APK")
        if not alvo:
            self.skipTest("defina REVIVAL_VERIFY_APK para medir um entregável real")
        r = read_cleartext_policy(Path(alvo))
        self.assertIs(r["cleartext_permitted"], False)
        self.assertEqual(r["cleartext_unreadable"], [])

    def test_laboratorio_apontado_por_env(self):
        alvo = os.environ.get("REVIVAL_LAB_APK")
        if not alvo:
            self.skipTest("defina REVIVAL_LAB_APK para medir um APK de laboratório real")
        host = os.environ.get("REVIVAL_LAB_HOST", HOST_LAB)
        r = read_cleartext_policy(Path(alvo))
        self.assertIs(r["cleartext_permitted"], True)
        self.assertTrue(scan_insecure_lab_markers(Path(alvo), host)["insecure"],
                        "o artefato de laboratório nunca passa como final")


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
