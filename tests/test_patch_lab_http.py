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
from revival_editor.axml import parse_axml_elements  # noqa: E402

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
        # Diretório PRÓPRIO: LAB_DIR é compartilhada com o rig e com os
        # outros testes, e artefato compartilhado vira ZIP truncado.
        self.lab = self.dir / "lab"
        self.lab.mkdir()
        self.saida = self.lab / "crc-LAB-HTTP.apk"

    def tearDown(self):
        if self.saida.exists():
            self.saida.unlink()

    def test_entrada_comeca_com_crc_nao_zero(self):
        pendentes = lab.verify_catalog_crc_zero(self.apk, [NOME_BUNDLE])
        self.assertEqual(pendentes, [NOME_BUNDLE],
                         "o fixture precisa comecar sujo, senao o teste nao prova nada")

    def test_patch_zera_e_prova_o_crc(self):
        rel = lab.patch_apk(apk_in=self.apk, apk_out=self.saida, host="10.0.2.2",
                            from_host=HOST_PUBLICO, allow_insecure_lab=True,
                            lab_dir=self.lab)
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
        alvo = self.lab / "sem-catalogo-LAB.apk"
        try:
            with self.assertRaises(lab.LabPatchError) as ctx:
                lab.patch_apk(apk_in=sem, apk_out=alvo, host="10.0.2.2",
                              from_host=HOST_PUBLICO, allow_insecure_lab=True,
                              lab_dir=self.lab)
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
        alvo = self.lab / "so-meta-LAB.apk"
        try:
            rel = lab.patch_apk(apk_in=so_meta, apk_out=alvo, host="10.0.2.2",
                                from_host=HOST_PUBLICO, allow_insecure_lab=True,
                                lab_dir=self.lab)
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
        self.lab = self.dir / "lab"
        self.lab.mkdir()
        self.saida = self.lab / "teste-LAB-HTTP.apk"

    def tearDown(self):
        if self.saida.exists():
            self.saida.unlink()

    def _patch(self, **over):
        base = dict(apk_in=self.apk, apk_out=self.saida, host="10.0.2.2",
                    from_host=HOST_PUBLICO, allow_insecure_lab=True,
                    lab_dir=self.lab)
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

    def test_lab_dir_proprio_nao_afrouxa_a_recusa_de_output(self):
        # O diretório é parametrizável para isolar jobs, NÃO para liberar
        # output/: apontar lab_dir para lá continua sendo recusado.
        with self.assertRaises(lab.LabPatchError) as ctx:
            self._patch(apk_out=ROOT / "output" / "x-LAB.apk",
                        lab_dir=ROOT / "output")
        self.assertIn("output/", str(ctx.exception))

    def test_recusa_nome_sem_marca_de_laboratorio(self):
        with self.assertRaises(lab.LabPatchError) as ctx:
            self._patch(apk_out=self.lab / "mighty-doom-revival.apk")
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
        self.lab = self.dir / "lab"
        self.lab.mkdir()
        self.saida = self.lab / "teste-LAB-HTTP.apk"
        self.rel = lab.patch_apk(apk_in=self.apk, apk_out=self.saida, host="10.0.2.2",
                                 from_host=HOST_PUBLICO, allow_insecure_lab=True,
                                 lab_dir=self.lab)

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
        segunda = self.lab / "teste2-LAB-HTTP.apk"
        try:
            with self.assertRaises(lab.LabPatchError):
                lab.patch_apk(apk_in=self.saida, apk_out=segunda, host="10.0.2.2",
                              from_host=HOST_PUBLICO, allow_insecure_lab=True,
                              lab_dir=self.lab)
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
        self.assertNotIn((ROOT / "output").resolve(), self.saida.resolve().parents)
        # O `lab_dir` deste teste e temporario de proposito; o PADRAO de
        # producao continua tendo que morar em work/, fora de output/.
        self.assertIn("work", lab.LAB_DIR.relative_to(ROOT).as_posix())
        self.assertNotIn((ROOT / "output").resolve(), lab.LAB_DIR.resolve().parents)



def nsc_sintetico(dominio: str = HOST_PUBLICO) -> bytes:
    """Monta um `network_security_config.xml` binario igual ao que o aapt gera.

    Reproduz a forma exata medida no APK real: pool UTF-8, resource map vazio e
    `cleartextTrafficPermitted` como booleano tipado (0x12), sem string crua.
    """
    strings = ["certificates", "cleartextTrafficPermitted", "domain", "domain-config",
               dominio, "includeSubdomains", "network-security-config", "src",
               "system", "trust-anchors"]
    corpo = bytearray()
    offsets = []
    for s in strings:
        offsets.append(len(corpo))
        bruto = s.encode("utf-8")
        corpo += bytes([len(bruto), len(bruto)]) + bruto + b"\x00"
    while len(corpo) % 4:
        corpo += b"\x00"
    tabela = b"".join(struct.pack("<I", o) for o in offsets)
    inicio = 28 + len(tabela)
    pool_tam = inicio + len(corpo)
    pool = (struct.pack("<HHIIIIII", 0x0001, 28, pool_tam, len(strings), 0, 0x100, inicio, 0)
            + tabela + bytes(corpo))
    resmap = struct.pack("<HHI", 0x0180, 8, 8)

    def elem(nome_idx: int, attrs: list[tuple[int, int, int]]) -> bytes:
        # 36 bytes de cabecalho (8 do chunk + linha/comentario + ns/nome +
        # attrIni/attrTam/attrCnt/id/class/style) e 20 bytes por atributo.
        cab = struct.pack("<HHIIIIIHHHHHH", 0x0102, 16, 36 + 20 * len(attrs),
                          0, 0xFFFFFFFF, 0xFFFFFFFF, nome_idx,
                          20, 20, len(attrs), 0, 0, 0)
        corpo_attr = b""
        for nome, vtipo, dado in attrs:
            raw = 0xFFFFFFFF if vtipo == 0x12 else dado
            corpo_attr += struct.pack("<IIIHBBI", 0xFFFFFFFF, nome, raw, 8, 0, vtipo, dado)
        return cab + corpo_attr

    def fim(nome_idx: int) -> bytes:
        return struct.pack("<HHIIIII", 0x0103, 16, 24, 0, 0xFFFFFFFF, 0xFFFFFFFF, nome_idx)

    def cdata(idx: int) -> bytes:
        return struct.pack("<HHIIIIHBBI", 0x0104, 16, 28, 0, 0xFFFFFFFF, idx, 8, 0, 0x03, idx)

    doc = (elem(6, []) + elem(3, [(1, 0x12, 0)]) + elem(2, [(5, 0x12, 0xFFFFFFFF)])
           + cdata(4) + fim(2) + elem(9, []) + elem(0, [(7, 0x03, 8)])
           + fim(0) + fim(9) + fim(3) + fim(6))
    total = 8 + len(pool) + len(resmap) + len(doc)
    return struct.pack("<HHI", 0x0003, 8, total) + pool + resmap + doc


class TestCleartextDeLaboratorio(unittest.TestCase):
    """A Activity usa HttpURLConnection; sem liberar cleartext o rig fica mudo."""

    def setUp(self):
        self.dados = nsc_sintetico()

    def test_ida_e_volta_troca_dominio_e_libera_cleartext(self):
        antes = lab.read_network_security_axml(self.dados)
        self.assertEqual(antes[1][1]["cleartextTrafficPermitted"], "false")
        self.assertEqual(antes[2][2], HOST_PUBLICO)
        novo, rel = lab.patch_network_security_axml(self.dados, "10.0.2.2",
                                                    allow_insecure_lab=True,
                                                    revival_host=HOST_PUBLICO)
        depois = lab.read_network_security_axml(novo)
        self.assertEqual(depois[1][1]["cleartextTrafficPermitted"], "true")
        self.assertEqual(depois[2][2], "10.0.2.2")
        self.assertEqual(rel["cleartext_host"], "10.0.2.2")
        self.assertEqual(rel["marker"], lab.MARKER)

    def test_tamanho_preservado_e_offsets_intactos(self):
        novo, _ = lab.patch_network_security_axml(self.dados, "10.0.2.2",
                                                  allow_insecure_lab=True,
                                                    revival_host=HOST_PUBLICO)
        self.assertEqual(len(novo), len(self.dados))
        # As demais strings do pool continuam legiveis no mesmo lugar.
        depois = lab.read_network_security_axml(novo)
        self.assertEqual([e[0] for e in depois],
                         ["network-security-config", "domain-config", "domain",
                          "trust-anchors", "certificates"])
        self.assertEqual(depois[4][1]["src"], "system")

    def test_host_publico_nunca_ganha_cleartext(self):
        with self.assertRaises(lab.LabPatchError):
            lab.patch_network_security_axml(self.dados, HOST_PUBLICO,
                                            allow_insecure_lab=True,
                                                    revival_host=HOST_PUBLICO)
        with self.assertRaises(lab.LabPatchError):
            lab.patch_network_security_axml(self.dados, "8.8.8.8",
                                            allow_insecure_lab=True,
                                                    revival_host=HOST_PUBLICO)

    def test_sem_flag_de_laboratorio_recusa(self):
        with self.assertRaises(lab.LabPatchError):
            lab.patch_network_security_axml(self.dados, "10.0.2.2",
                                            allow_insecure_lab=False,
                                            revival_host=HOST_PUBLICO)

    def test_axml_sem_o_atributo_e_recusado(self):
        quebrado = self.dados.replace(b"cleartextTrafficPermitted", b"cleartextTrafficPermittex")
        with self.assertRaises(lab.LabPatchError):
            lab.patch_network_security_axml(quebrado, "10.0.2.2", allow_insecure_lab=True,
                                                    revival_host=HOST_PUBLICO)

    def test_host_maior_que_o_dominio_e_recusado(self):
        # A troca e feita POR CIMA da string antiga: so encurtar e seguro.
        with self.assertRaises(lab.LabPatchError):
            lab.patch_network_security_axml(self.dados, "10.0.2.2.exemplo.interno.muito.longo",
                                            allow_insecure_lab=True,
                                                    revival_host=HOST_PUBLICO)

    def test_parser_canonico_do_projeto_le_o_resultado(self):
        novo, _ = lab.patch_network_security_axml(self.dados, "10.0.2.2",
                                                  allow_insecure_lab=True,
                                                    revival_host=HOST_PUBLICO)
        elementos = parse_axml_elements(novo)
        self.assertEqual(elementos[1][1]["cleartextTrafficPermitted"], "true")

if __name__ == "__main__":
    unittest.main(verbosity=2)
