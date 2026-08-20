#!/usr/bin/env python3
"""Testes do modo LAB_ONLY_INSECURE_HTTP (scripts/patch_lab_http.py).

Este modo existe por autorização explícita do usuário para vencer o bloqueio TLS
do rig. Ele rebaixa o wire para HTTP, então os testes que mais importam são os de
RECUSA: sem a flag, fora do laboratório, ou apontando para `output/`.

Nenhum APK proprietário é usado: os fixtures são um metadata v29 sintético e um
ZIP montado no teste.
"""
from __future__ import annotations

import base64
import json
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import patch_lab_http as lab  # noqa: E402

HOST_PUBLICO = "doom.exemplo.br"
URL_METADATA = b"https://u0000000000@doom.exemplo.br/collections/doom"
URL_BUNDLE = b"https://doom.exemplo.br"


def metadata_sintetico(literais: list[bytes]) -> bytes:
    """global-metadata.dat v29 mínimo, só com a tabela de literais válida."""
    cabecalho = bytearray(struct.pack("<32I", *([0] * 32)))
    struct.pack_into("<I", cabecalho, 0, 0xFAB11BAF)
    struct.pack_into("<I", cabecalho, 4, 29)
    tabela = bytearray()
    dados = bytearray()
    for literal in literais:
        tabela += struct.pack("<Ii", len(literal), len(dados))
        dados += literal
    lit_off = 128
    data_off = lit_off + len(tabela)
    struct.pack_into("<I", cabecalho, 8, lit_off)          # h[2] stringLiteral off
    struct.pack_into("<I", cabecalho, 12, len(tabela))     # h[3] size
    struct.pack_into("<I", cabecalho, 16, data_off)        # h[4] stringLiteralData
    struct.pack_into("<I", cabecalho, 20, len(dados))      # h[5] size
    return bytes(cabecalho) + bytes(tabela) + bytes(dados)


def bundle_sintetico(*strings: bytes) -> bytes:
    """Strings Unity serializadas: int32 LE de comprimento + UTF-8."""
    saida = bytearray(b"UnityFS\x00pref\x00")
    for s in strings:
        saida += struct.pack("<i", len(s)) + s + b"\x00\x00"
    return bytes(saida)


HASH_BUNDLE = "00112233445566778899aabbccddeeff"
NOME_BUNDLE = f"assets/aa/Android/grupo_all_{HASH_BUNDLE}.bundle"


def catalogo_sintetico(crc: int) -> bytes:
    """`catalog.json` do Addressables com um AssetBundleRequestOptions real.

    O JSON dos options vive em UTF-16LE dentro do base64 de
    `m_ExtraDataString` — e assim que o catalogo do jogo guarda o `m_Crc`.
    """
    options = ('{"m_Hash":"' + HASH_BUNDLE + '","m_Crc":' + str(crc)
               + ',"m_BundleName":"grupo_all_' + HASH_BUNDLE + '.bundle"}')
    extra = base64.b64encode(options.encode("utf-16-le")).decode("ascii")
    return json.dumps({"m_ExtraDataString": extra, "m_InternalIds": [NOME_BUNDLE]}).encode("utf-8")


def apk_sintetico(destino: Path, *, metadata: bytes, bundle: bytes) -> Path:
    """APK minimo COM catalogo: bundle alterado sem catalogo e recusado."""
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(lab.METADATA_ENTRY, metadata)
        z.writestr(NOME_BUNDLE, bundle)
        z.writestr("assets/aa/catalog.json", catalogo_sintetico(4023233417))
        z.writestr("AndroidManifest.xml", b"\x03\x00\x08\x00fake")
    return destino


class TestDestinoDeLaboratorio(unittest.TestCase):
    def test_aceita_apenas_local_e_privado(self):
        for host in ("127.0.0.1", "localhost", "10.0.2.2", "192.168.0.10",
                     "172.16.5.4", "10.1.2.3", "169.254.1.1", "rig.local"):
            self.assertTrue(lab.is_lab_target(host), host)

    def test_recusa_publico(self):
        for host in ("doom.sualoja.app.br", "international.gear.bethesda.net",
                     "8.8.8.8", "example.com", "", "1.1.1.1"):
            self.assertFalse(lab.is_lab_target(host), host)


class TestTrocaByteAByte(unittest.TestCase):
    def test_comprimento_preservado_em_todos_os_casos(self):
        for url in (URL_METADATA, URL_BUNDLE,
                    b"https://a.exemplo.br/x", b"https://u00@a.exemplo.br/"):
            for novo in (None, "10.0.2.2", "127.0.0.1"):
                with self.subTest(url=url, novo=novo):
                    try:
                        saida = lab.downgrade_url(url, novo)
                    except lab.LabPatchError:
                        continue  # não coube: recusa é resultado válido
                    self.assertEqual(len(saida), len(url), "comprimento tem que ser idêntico")
                    self.assertTrue(saida.startswith(b"http://"))
                    self.assertNotIn(b"https://", saida)

    def test_postimage_esperada(self):
        # A postimage é determinística: http:// + userinfo de padding + host.
        # O padding é calculado, não chutado — por isso o esperado é montado
        # aqui do mesmo jeito, e o que se afirma é a FORMA e o comprimento.
        for url in (URL_METADATA, URL_BUNDLE):
            with self.subTest(url=url):
                saida = lab.downgrade_url(url, "10.0.2.2")
                alvo = lab.describe_target(url)
                folga = len(url) - len(b"http://10.0.2.2") - len(alvo["path"].encode())
                if alvo["path"] == "/":   # URL sem path explícito
                    folga = len(url) - len(b"http://10.0.2.2")
                esperado = b"http://u" + b"0" * (folga - 2) + b"@10.0.2.2" + \
                    (alvo["path"].encode() if alvo["path"] != "/" else b"")
                self.assertEqual(saida, esperado)
                self.assertEqual(len(saida), len(url))
        # E o caso concreto do APK real (host de 19 bytes -> 10.0.2.2):
        self.assertEqual(
            lab.downgrade_url(b"https://u0000000000@doom.sualoja.app.br/collections/doom",
                              "10.0.2.2"),
            b"http://u0000000000000000000000@10.0.2.2/collections/doom")

    def test_host_e_path_efetivos_nao_mudam_sem_novo_host(self):
        saida = lab.downgrade_url(URL_METADATA)
        antes, depois = lab.describe_target(URL_METADATA), lab.describe_target(saida)
        self.assertEqual(antes["host"], depois["host"])
        self.assertEqual(antes["path"], depois["path"])
        self.assertEqual(depois["scheme"], "http")

    def test_padding_de_userinfo_e_ignorado_pelo_destino(self):
        saida = lab.downgrade_url(URL_METADATA, "10.0.2.2")
        self.assertEqual(lab.describe_target(saida)["host"], "10.0.2.2",
                         "userinfo não faz parte do host efetivo")
        self.assertEqual(lab.describe_target(saida)["path"], "/collections/doom")

    def test_recusa_quando_o_host_novo_nao_cabe(self):
        with self.assertRaises(lab.LabPatchError):
            lab.downgrade_url(b"https://a.br/", "um.host.bem.mais.comprido.exemplo.br")

    def test_recusa_preimage_que_nao_e_https(self):
        with self.assertRaises(lab.LabPatchError):
            lab.downgrade_url(b"http://a.exemplo.br/")


class TestFronteiraExata(unittest.TestCase):
    def test_literal_colado_nao_e_engolido(self):
        # O bug que isto previne: scan guloso levando a próxima literal junto.
        meta = metadata_sintetico([URL_METADATA, b"https://oauth2.googleapis.com/token"])
        achados = lab.find_https_urls(meta, HOST_PUBLICO)
        self.assertEqual(achados, [URL_METADATA],
                         "só a URL do host alvo, com o comprimento da tabela")

    def test_bundle_usa_prefixo_de_comprimento(self):
        bundle = bundle_sintetico(URL_BUNDLE, b"https://outro.exemplo.com/x")
        self.assertEqual(lab.find_https_urls(bundle, HOST_PUBLICO), [URL_BUNDLE])

    def test_ocorrencia_sem_fronteira_provavel_e_ignorada(self):
        # Sem tabela e sem prefixo válido: nada é recortado no palpite.
        cru = b"lixo" + URL_BUNDLE + b"maislixo"
        self.assertEqual(lab.find_https_urls(cru, HOST_PUBLICO), [])

    def test_blob_nao_muda_de_tamanho(self):
        meta = metadata_sintetico([URL_METADATA])
        saida, rel, _ = lab.patch_blob(meta, HOST_PUBLICO, "10.0.2.2")
        self.assertEqual(len(saida), len(meta))
        self.assertEqual(rel.total, 1)
        self.assertNotIn(b"https://", saida)


class TestCrcDoCatalogo(unittest.TestCase):
    """Bundle alterado sem CRC zerado = menu abre e a cena morre (DEAD-ENDS #7).

    O teste anterior so passava por HERDAR um catalogo ja zerado do APK de
    entrada. Aqui o catalogo comeca com CRC NAO-ZERO de proposito.
    """

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.apk = self.dir / "entrada.apk"
        with zipfile.ZipFile(self.apk, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(lab.METADATA_ENTRY, metadata_sintetico([URL_METADATA]))
            z.writestr(NOME_BUNDLE, bundle_sintetico(URL_BUNDLE))
            z.writestr("assets/aa/catalog.json", catalogo_sintetico(4023233417))
            z.writestr("AndroidManifest.xml", b"\x03\x00\x08\x00fake")
        self.saida = lab.LAB_DIR / "crc-LAB-HTTP.apk"

    def tearDown(self):
        if self.saida.exists():
            self.saida.unlink()

    def test_entrada_comeca_com_crc_nao_zero(self):
        pendentes = lab.verify_catalog_crc_zero(self.apk, [NOME_BUNDLE])
        self.assertEqual(pendentes, [NOME_BUNDLE],
                         "o fixture precisa comecar sujo, senao o teste nao prova nada")

    def test_patch_zera_e_prova_o_crc(self):
        rel = lab.patch_apk(apk_in=self.apk, apk_out=self.saida, host="10.0.2.2",
                            from_host=HOST_PUBLICO, allow_insecure_lab=True)
        self.assertEqual(rel["bundles_alterados"], [NOME_BUNDLE])
        self.assertTrue(rel["catalog_crc_verified"], "a pos-condicao tem que ter rodado")
        self.assertTrue(all(c["zeroed"] for c in rel["catalog_crc"]),
                        f"zero_catalog_crc nao zerou: {rel['catalog_crc']}")
        self.assertEqual(lab.verify_catalog_crc_zero(self.saida, [NOME_BUNDLE]), [],
                         "no APK de saida o CRC daquele bundle tem que ser 0")

    def test_apk_sem_catalogo_e_recusado(self):
        sem = self.dir / "sem-catalogo.apk"
        with zipfile.ZipFile(sem, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(lab.METADATA_ENTRY, metadata_sintetico([URL_METADATA]))
            z.writestr(NOME_BUNDLE, bundle_sintetico(URL_BUNDLE))
        alvo = lab.LAB_DIR / "sem-catalogo-LAB.apk"
        try:
            with self.assertRaises(lab.LabPatchError) as ctx:
                lab.patch_apk(apk_in=sem, apk_out=alvo, host="10.0.2.2",
                              from_host=HOST_PUBLICO, allow_insecure_lab=True)
            self.assertIn("catalog", str(ctx.exception).lower())
            self.assertFalse(alvo.exists(), "nada e escrito numa recusa")
        finally:
            if alvo.exists():
                alvo.unlink()

    def test_apk_so_com_metadata_nao_exige_catalogo(self):
        # Sem bundle alterado nao ha CRC a zerar — e nao pode inventar exigencia.
        so_meta = self.dir / "so-metadata.apk"
        with zipfile.ZipFile(so_meta, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(lab.METADATA_ENTRY, metadata_sintetico([URL_METADATA]))
        alvo = lab.LAB_DIR / "so-meta-LAB.apk"
        try:
            rel = lab.patch_apk(apk_in=so_meta, apk_out=alvo, host="10.0.2.2",
                                from_host=HOST_PUBLICO, allow_insecure_lab=True)
            self.assertEqual(rel.get("bundles_alterados", []), [])
            self.assertNotIn("catalog_crc_verified", rel)
        finally:
            if alvo.exists():
                alvo.unlink()


class TestGatesDeSeguranca(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.apk = apk_sintetico(self.dir / "entrada.apk",
                                 metadata=metadata_sintetico([URL_METADATA]),
                                 bundle=bundle_sintetico(URL_BUNDLE))
        self.saida = lab.LAB_DIR / "teste-LAB-HTTP.apk"

    def tearDown(self):
        if self.saida.exists():
            self.saida.unlink()

    def _patch(self, **over):
        base = dict(apk_in=self.apk, apk_out=self.saida, host="10.0.2.2",
                    from_host=HOST_PUBLICO, allow_insecure_lab=True)
        return lab.patch_apk(**{**base, **over})

    def test_recusa_sem_a_flag(self):
        with self.assertRaises(lab.LabPatchError) as ctx:
            self._patch(allow_insecure_lab=False)
        self.assertIn("--allow-insecure-lab", str(ctx.exception))

    def test_recusa_destino_publico(self):
        with self.assertRaises(lab.LabPatchError) as ctx:
            self._patch(host="doom.sualoja.app.br", from_host=None)
        self.assertIn("laboratório", str(ctx.exception))

    def test_recusa_saida_em_output(self):
        with self.assertRaises(lab.LabPatchError) as ctx:
            self._patch(apk_out=ROOT / "output" / "mighty-doom-revival.apk")
        self.assertIn("output/", str(ctx.exception))

    def test_recusa_saida_fora_do_diretorio_de_laboratorio(self):
        with self.assertRaises(lab.LabPatchError):
            self._patch(apk_out=self.dir / "qualquer-LAB.apk")

    def test_recusa_nome_sem_marca_de_laboratorio(self):
        with self.assertRaises(lab.LabPatchError) as ctx:
            self._patch(apk_out=lab.LAB_DIR / "mighty-doom-revival.apk")
        self.assertIn("laboratório", str(ctx.exception))

    def test_analyze_nao_escreve_nada(self):
        antes = self.apk.read_bytes()
        rel = self._patch(analyze=True)
        self.assertFalse(rel["written"])
        self.assertFalse(self.saida.exists())
        self.assertEqual(self.apk.read_bytes(), antes, "entrada intacta")


class TestArtefatoDeLaboratorio(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.apk = apk_sintetico(self.dir / "entrada.apk",
                                 metadata=metadata_sintetico([URL_METADATA]),
                                 bundle=bundle_sintetico(URL_BUNDLE))
        self.saida = lab.LAB_DIR / "teste-LAB-HTTP.apk"
        self.rel = lab.patch_apk(apk_in=self.apk, apk_out=self.saida, host="10.0.2.2",
                                 from_host=HOST_PUBLICO, allow_insecure_lab=True)

    def tearDown(self):
        if self.saida.exists():
            self.saida.unlink()

    def test_relatorio_marca_o_risco(self):
        self.assertEqual(self.rel["marker"], lab.MARKER)
        self.assertTrue(self.rel["insecure_http"])
        self.assertTrue(self.rel["lab_only"])
        self.assertIn("input_sha256", self.rel)
        self.assertIn("output_sha256", self.rel)
        self.assertEqual(self.rel["total_replacements"], 2)

    def test_relatorio_traz_preimage_postimage_e_bytes(self):
        for entrada in self.rel["entries"]:
            for r in entrada["replacements"]:
                self.assertTrue(r["preimage"].startswith("https://"))
                self.assertTrue(r["postimage"].startswith("http://"))
                self.assertEqual(len(r["preimage"]), len(r["postimage"]))
                self.assertEqual(r["bytes"], len(r["preimage"]))
                self.assertEqual(r["target_after"]["host"], "10.0.2.2")
                self.assertEqual(r["target_before"]["path"], r["target_after"]["path"])

    def test_apk_de_laboratorio_verificado(self):
        v = lab.verify_lab_apk(self.saida, "10.0.2.2")
        self.assertGreater(v["http_occurrences"], 0)
        self.assertEqual(v["https_occurrences"], 0)
        self.assertEqual(v["official_occurrences"], 0, "host oficial nunca pode sobrar")
        self.assertTrue(v["verified"])

    def test_segunda_execucao_falha_com_seguranca(self):
        # Idempotência: reprocessar o artefato já rebaixado não corrompe nada.
        segunda = lab.LAB_DIR / "teste2-LAB-HTTP.apk"
        try:
            with self.assertRaises(lab.LabPatchError):
                lab.patch_apk(apk_in=self.saida, apk_out=segunda, host="10.0.2.2",
                              from_host=HOST_PUBLICO, allow_insecure_lab=True)
            self.assertFalse(segunda.exists(), "nada é escrito numa recusa")
        finally:
            if segunda.exists():
                segunda.unlink()

    def test_entrada_permanece_intacta(self):
        with zipfile.ZipFile(self.apk) as z:
            self.assertIn(b"https://", z.read(lab.METADATA_ENTRY))

    def test_separacao_absoluta_do_artefato_final(self):
        final = ROOT / "output" / "mighty-doom-revival.apk"
        self.assertNotEqual(self.saida.resolve(), final.resolve())
        self.assertIn("LAB", self.saida.name.upper())
        self.assertIn("work", self.saida.as_posix())


if __name__ == "__main__":
    unittest.main(verbosity=2)
