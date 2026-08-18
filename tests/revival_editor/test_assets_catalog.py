#!/usr/bin/env python3
"""Regressão do catálogo e da transação de assets Unity (fase 9 do plano).

Cobre as quatro seções da fase:

- §16.1 categorização e scanner somente-leitura (relatório sem conteúdo);
- §16.2 seletores estáveis — qualquer divergência bloqueia;
- §16.3 ordem de suporte — só textura de loading é EDITÁVEL_VALIDADA;
- §16.4 transação com preservação do original em falha.

Os testes de integração usam o **bundle menor** do APK real (sem extração
para o Git — tudo vive em work/, gitignored) e pulam se o APK não existir.
A transação completa no bundle de conteúdo (494 MB) é o gate manual da fase.

Execução: python tests/revival_editor/test_assets_catalog.py
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from revival_editor import assets_catalog as ac  # noqa: E402

REAL_APK = SCRIPTS_DIR.parent / "input" / "mighty-doom.apk"

HEX64 = re.compile(r"^[0-9a-f]{64}$")


class TestCategorize(unittest.TestCase):
    """§16.3 — a ordem de suporte é código, não promessa."""

    def test_textura_de_loading_e_editavel_validada(self) -> None:
        self.assertEqual(
            ac.categorize("Texture2D", "loading_background"), ac.EDITAVEL_VALIDADO
        )
        self.assertEqual(
            ac.categorize("Texture2D", "halloween_LoadingBackground_2024"),
            ac.EDITAVEL_VALIDADO,
        )

    def test_textura_sprite_textasset_monobehaviour_a_verificar(self) -> None:
        for tipo in ("Texture2D", "Sprite", "TextAsset", "MonoBehaviour"):
            self.assertEqual(ac.categorize(tipo, "qualquer_coisa"), ac.A_VERIFICAR)

    def test_audioclip_somente_leitura(self) -> None:
        self.assertEqual(ac.categorize("AudioClip", "bgm_menu"), ac.SOMENTE_LEITURA)

    def test_tipos_bloqueados(self) -> None:
        for tipo in ("Scene", "GameObject", "MonoScript", "Mesh", "Shader"):
            self.assertEqual(ac.categorize(tipo, "x"), ac.BLOQUEADO, tipo)

    def test_tipo_desconhecido_somente_leitura(self) -> None:
        self.assertEqual(ac.categorize("AnimationClip", "run"), ac.SOMENTE_LEITURA)

    def test_membros_bloqueados_do_apk(self) -> None:
        self.assertEqual(
            ac.apk_member_category("assets/bin/Data/Managed/Metadata/global-metadata.dat"),
            ac.BLOQUEADO,
        )
        self.assertEqual(
            ac.apk_member_category("lib/arm64-v8a/libil2cpp.so"), ac.BLOQUEADO
        )

    def test_membro_bundle_verifica_objeto_a_objeto(self) -> None:
        membro = "assets/aa/Android/stores_x.bundle"
        self.assertEqual(ac.apk_member_category(membro), ac.A_VERIFICAR)
        self.assertEqual(ac.apk_member_category("assets/bin/Data/level0"), ac.SOMENTE_LEITURA)


class TestSelector(unittest.TestCase):
    """§16.2 — seletor estável: forma canônica, parse e recusas."""

    ENTRADA = ac.AssetEntry(
        member="assets/aa/Android/conteudo.bundle",
        path_id=12345,
        type="Texture2D",
        name="loading_background",
        obj_sha256="ab" * 32,
    )

    def test_seletor_str_parse_roundtrip(self) -> None:
        seletor = ac.selector_for("cd" * 32, self.ENTRADA)
        texto = ac.selector_str(seletor)
        self.assertEqual(ac.parse_selector(texto), seletor)

    def test_parse_recusa_malformado(self) -> None:
        with self.assertRaises(ac.AssetsError):
            ac.parse_selector("sem-igual")
        com_falta = ac.selector_str(ac.selector_for("cd" * 32, self.ENTRADA))
        com_falta = com_falta.replace("type=Texture2D|", "")
        with self.assertRaises(ac.AssetsError) as cm:
            ac.parse_selector(com_falta)
        self.assertIn("type", str(cm.exception))

    def test_parse_recusa_path_id_nao_inteiro(self) -> None:
        seletor = ac.selector_for("cd" * 32, self.ENTRADA)
        texto = ac.selector_str(seletor).replace("path_id=12345", "path_id=xyz")
        with self.assertRaises(ac.AssetsError):
            ac.parse_selector(texto)

    def test_seletor_exige_hash_do_objeto(self) -> None:
        sem_hash = ac.AssetEntry(member="m", path_id=1, type="T", name="n")
        with self.assertRaises(ac.AssetsError) as cm:
            ac.selector_for("cd" * 32, sem_hash)
        self.assertIn("hash", str(cm.exception))


class TestSearchEReport(unittest.TestCase):
    def setUp(self) -> None:
        self.entries = [
            ac.AssetEntry("a.bundle", 1, "Texture2D", "loading_background",
                          width=2048, height=2048, obj_sha256="0" * 64,
                          category=ac.EDITAVEL_VALIDADO),
            ac.AssetEntry("a.bundle", 2, "Texture2D", "hero_icon",
                          width=256, height=256, obj_sha256="1" * 64,
                          category=ac.A_VERIFICAR),
            ac.AssetEntry("b.bundle", 3, "AudioClip", "bgm_menu",
                          duration=95.5, obj_sha256="2" * 64,
                          category=ac.SOMENTE_LEITURA),
        ]

    def test_busca_por_texto_tipo_e_bundle(self) -> None:
        self.assertEqual(
            [e.name for e in ac.search_entries(self.entries, text="loading")],
            ["loading_background"],
        )
        self.assertEqual(
            len(ac.search_entries(self.entries, type_name="Texture2D")), 2
        )
        self.assertEqual(
            len(ac.search_entries(self.entries, member="b.bundle")), 1
        )
        self.assertEqual(
            [e.name for e in ac.search_entries(self.entries, text="LOADING")],
            ["loading_background"],
            "busca é case-insensitive",
        )
        self.assertEqual(ac.search_entries(self.entries, text="inexistente"), [])

    def test_relatorio_so_tem_metadados(self) -> None:
        resultado = ac.ScanResult(
            apk="x.apk", apk_sha256="cd" * 32, member="a.bundle",
            bundle_sha256="ef" * 32, object_count=2, entries=self.entries,
        )
        with tempfile.TemporaryDirectory() as tmp:
            destino = ac.save_report(resultado, Path(tmp) / "cat" / "catalogo.json")
            dados = json.loads(destino.read_text(encoding="utf-8"))
        self.assertEqual(dados["object_count"], 2)
        self.assertEqual(len(dados["entries"]), 3)
        for campo in ("image", "image_data", "raw", "samples", "content"):
            self.assertNotIn(campo, json.dumps(dados), "relatório não exporta conteúdo")
        self.assertEqual(dados["entries"][0]["category"], ac.EDITAVEL_VALIDADO)


class TestTransacaoRecusada(unittest.TestCase):
    """§16.3 na prática: fora da ordem de suporte, a transação nem começa."""

    def test_textura_nao_validada_recusada(self) -> None:
        seletor = {
            "apk_sha256": "cd" * 32,
            "member": "assets/aa/Android/qualquer.bundle",
            "path_id": 1,
            "type": "Texture2D",
            "name": "hero_icon",
            "obj_sha256": "0" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ac.TransactionRefused) as cm:
                ac.apply_replacement(REAL_APK, seletor, None, Path(tmp))
        self.assertIn("ordem de suporte", str(cm.exception))
        self.assertIn("A_VERIFICAR", str(cm.exception))

    def test_tipo_bloqueado_recusado(self) -> None:
        seletor = {
            "apk_sha256": "cd" * 32, "member": "m.bundle", "path_id": 9,
            "type": "Shader", "name": "ui.shader", "obj_sha256": "0" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ac.TransactionRefused):
                ac.apply_replacement(REAL_APK, seletor, None, Path(tmp))


class _FakeTipo:
    def __init__(self, nome: str) -> None:
        self.name = nome


class _FakeData:
    def __init__(self, nome: str, width: int = 0, height: int = 0) -> None:
        self.m_Name = nome
        self.m_Width = width
        self.m_Height = height


class _FakeObj:
    """Objeto Unity falso — registra toda desserialização para o teste auditar."""

    def __init__(self, path_id: int, tipo: str, nome: str = "x", ilegivel: bool = False) -> None:
        self.type = _FakeTipo(tipo)
        self.path_id = path_id
        self._data = _FakeData(nome, 64, 64)
        self._ilegivel = ilegivel
        self.lidos: list[str] = []  # compartilhado via env

    def read(self) -> _FakeData:
        self.lidos.append(self.type.name)
        if self._ilegivel:
            raise RuntimeError("objeto ilegível")
        return self._data

    def get_raw_data(self) -> bytes:
        return f"raw-{self.path_id}".encode()


class _FakeEnv:
    def __init__(self, objetos: list[_FakeObj]) -> None:
        self.objects = objetos


class _FakeUnityPy:
    def __init__(self, objetos: list[_FakeObj]) -> None:
        self._objetos = objetos

    def load(self, _caminho: str) -> _FakeEnv:
        return _FakeEnv(self._objetos)


class TestScanHardening(unittest.TestCase):
    """O scanner só desserializa SAFE_READ_TYPES — obj.read() de tipo sem
    parser nativo derruba o processo inteiro (access violation comprovada
    no bundle de conteúdo). Isso é contrato, não otimização."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self._tmp.name)
        self.apk = self.pasta / "fake.apk"
        membro = "assets/aa/Android/fake.bundle"
        with zipfile.ZipFile(self.apk, "w") as z:
            z.writestr(membro, b"bundle-fake")
            z.writestr(ac.CATALOG_MEMBER, b"{}")

        self.objetos = [
            _FakeObj(1, "Texture2D", "loading_background"),
            _FakeObj(2, "Texture2D", "hero_icon"),
            _FakeObj(3, "GameObject", "LevelRoot"),
            _FakeObj(4, "MonoBehaviour", "SaveData"),
            _FakeObj(5, "Texture2D", "quebrada", ilegivel=True),
        ]
        for obj in self.objetos:
            obj.lidos = []
        self.logs: list[str] = []

        patcher_ext = mock.patch.object(ac, "_extract_member")
        patcher_unitypy = mock.patch.object(ac, "_load_unitypy")
        self.mock_ext = patcher_ext.start()
        self.mock_unitypy = patcher_unitypy.start()
        self.addCleanup(patcher_ext.stop)
        self.addCleanup(patcher_unitypy.stop)

        def extrair(_apk, _membro, destino):
            Path(destino).write_bytes(b"bundle-fake")

        self.mock_ext.side_effect = extrair
        self.mock_unitypy.return_value = _FakeUnityPy(self.objetos)

        self.resultado = ac.scan_bundle(
            self.apk, membro, self.pasta / "work", log=self.logs.append
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_so_desserializa_tipos_seguros(self) -> None:
        lidos = {tipo for obj in self.objetos for tipo in obj.lidos}
        self.assertEqual(lidos, {"Texture2D"}, f"read() fora da lista branca: {lidos}")

    def test_fora_da_lista_branca_entrega_interrogacao(self) -> None:
        por_id = {e.path_id: e for e in self.resultado.entries}
        self.assertEqual(por_id[3].name, "?")   # GameObject nunca lido
        self.assertEqual(por_id[4].name, "?")   # MonoBehaviour nunca lido
        self.assertEqual(por_id[3].category, ac.BLOQUEADO)
        self.assertEqual(por_id[4].category, ac.A_VERIFICAR)

    def test_hash_e_categoria_dos_lidos(self) -> None:
        por_id = {e.path_id: e for e in self.resultado.entries}
        self.assertEqual(por_id[1].name, "loading_background")
        self.assertEqual(por_id[1].category, ac.EDITAVEL_VALIDADO)
        self.assertRegex(por_id[1].obj_sha256, HEX64)
        self.assertEqual(por_id[2].category, ac.A_VERIFICAR)

    def test_ilegiviel_da_whitelist_vira_a_verificar(self) -> None:
        por_id = {e.path_id: e for e in self.resultado.entries}
        self.assertEqual(por_id[5].name, "?")
        self.assertEqual(por_id[5].category, ac.A_VERIFICAR)

    def test_log_denuncia_o_que_ficou_fora(self) -> None:
        self.assertTrue(any("sem desserializar" in linha for linha in self.logs))


@unittest.skipUnless(REAL_APK.is_file(), "APK real não presente (input/mighty-doom.apk)")
class TestScanBundleReal(unittest.TestCase):
    """Integração com o bundle MENOR do APK real — o catálogo lê, nunca escreve."""

    @classmethod
    def setUpClass(cls) -> None:
        import zipfile

        # UnityPy retém handle do arquivo aberto no Windows; coleta de lixo
        # antes do cleanup evita PermissionError em rmtree.
        cls._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.work = Path(cls._tmp.name)
        with zipfile.ZipFile(REAL_APK, "r") as apk:
            membros = ac.list_bundle_members(apk)
            cls.membros = membros
            cls.menor = membros[-1]["member"]
        cls.resultado = ac.scan_bundle(REAL_APK, cls.menor, cls.work, log=lambda *_: None)

    @classmethod
    def tearDownClass(cls) -> None:
        import gc

        gc.collect()
        cls._tmp.cleanup()

    def test_lista_membros_sem_abrir(self) -> None:
        self.assertTrue(any(m["member"].endswith(".bundle") for m in self.membros))
        for m in self.membros:
            self.assertGreater(m["size"], 0)

    def test_scan_produz_entradas_sane(self) -> None:
        entradas = self.resultado.entries
        self.assertEqual(len(entradas), self.resultado.object_count)
        self.assertGreater(len(entradas), 0)
        categorias = {e.category for e in entradas}
        self.assertTrue(
            categorias <= {ac.EDITAVEL_VALIDADO, ac.SOMENTE_LEITURA, ac.BLOQUEADO, ac.A_VERIFICAR},
            f"categoria inventada: {categorias}",
        )
        path_ids = [e.path_id for e in entradas]
        self.assertEqual(len(path_ids), len(set(path_ids)), "path_id duplicado no catálogo")
        for entrada in entradas:
            self.assertEqual(entrada.member, self.menor)
            self.assertIsNotNone(entrada.obj_sha256)
            self.assertRegex(entrada.obj_sha256, HEX64)
        self.assertRegex(self.resultado.apk_sha256, HEX64)
        self.assertRegex(self.resultado.bundle_sha256, HEX64)

    def test_busca_no_resultado_real(self) -> None:
        achados = ac.search_entries(self.resultado.entries, member=self.menor)
        self.assertEqual(len(achados), len(self.resultado.entries))
        textos = ac.search_entries(self.resultado.entries, type_name="Texture2D")
        for entrada in textos:
            self.assertIn(entrada.category, (ac.EDITAVEL_VALIDADO, ac.A_VERIFICAR))

    def test_relatorio_salvo_sem_conteudo(self) -> None:
        destino = ac.save_report(self.resultado, self.work / "relatorio.json")
        dados = json.loads(destino.read_text(encoding="utf-8"))
        self.assertEqual(dados["member"], self.menor)
        self.assertNotIn("image", json.dumps(dados))

    def test_seletor_confirma_no_bundle_real(self) -> None:
        entrada = next(e for e in self.resultado.entries if e.obj_sha256)
        seletor = ac.selector_for(self.resultado.apk_sha256, entrada)
        bundle = self.work / Path(self.menor).name
        _obj, hash_atual = ac.confirm_selector_in_bundle(seletor, bundle)
        self.assertEqual(hash_atual, entrada.obj_sha256)

    def test_seletor_divergente_bloqueia(self) -> None:
        entrada = next(e for e in self.resultado.entries if e.obj_sha256)
        bundle = self.work / Path(self.menor).name

        nome_errado = {**ac.selector_for(self.resultado.apk_sha256, entrada), "name": "parecido"}
        with self.assertRaises(ac.SelectorMismatch) as cm:
            ac.confirm_selector_in_bundle(nome_errado, bundle)
        self.assertIn("nome:", str(cm.exception))

        hash_errado = {**ac.selector_for(self.resultado.apk_sha256, entrada),
                       "obj_sha256": "ff" * 32}
        with self.assertRaises(ac.SelectorMismatch) as cm:
            ac.confirm_selector_in_bundle(hash_errado, bundle)
        self.assertIn("hash do objeto", str(cm.exception))

        id_errado = {**ac.selector_for(self.resultado.apk_sha256, entrada),
                     "path_id": entrada.path_id + 10**9}
        with self.assertRaises(ac.SelectorMismatch) as cm:
            ac.confirm_selector_in_bundle(id_errado, bundle)
        self.assertIn("path_id", str(cm.exception))

    def test_falha_de_seletor_preserva_original(self) -> None:
        """§16.4: a divergência aborta ANTES de qualquer promoção — nenhum
        bundle .patched/.parcial aparece no workspace e o APK não é tocado."""
        entrada = next(
            e for e in self.resultado.entries
            if e.obj_sha256 and e.name != "loading_background"
        )
        seletor_falso = {
            **ac.selector_for(self.resultado.apk_sha256, entrada),
            "type": "Texture2D",
            "name": "loading_background",  # disfarçado de validado
        }
        com_categoria = dict(seletor_falso)
        # category check usa type+name: passa; a confirmação tem que derrubar
        import gc

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            with self.assertRaises((ac.SelectorMismatch, ac.AssetsError)):
                ac.apply_replacement(REAL_APK, com_categoria, None, Path(tmp))
            gc.collect()
            sobras = [p.name for p in Path(tmp).rglob("*.bundle")]
            self.assertFalse(
                any(".patched." in n or ".parcial." in n for n in sobras),
                f"transação abortada não pode deixar rastro: {sobras}",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
