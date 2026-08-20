#!/usr/bin/env python3
"""Regressão da toolchain determinística do Revival Studio.

Trava os dois comportamentos que o plano exige na fase 3:

  - "Java 11 é rejeitado com instrução clara; Java 17 local é selecionado";
  - "hash divergente de JAR bloqueia o build".

Os testes não dependem de nenhum Java instalado: a execução de `java -version`
é substituída, então valem igual em Windows, Linux e CI.

Execução: python tests/revival_editor/test_toolchain.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from revival_editor import toolchain as tc  # noqa: E402

JAVA_11 = (
    'java version "11.0.18" 2023-01-17 LTS\n'
    "Java(TM) SE Runtime Environment 18.9 (build 11.0.18+9-LTS-195)\n"
)
JAVA_17 = (
    'openjdk version "17.0.20" 2026-07-21\n'
    "OpenJDK Runtime Environment Temurin-17.0.20+8 (build 17.0.20+8)\n"
)
JAVA_8 = 'java version "1.8.0_382"\n'


class TestParseJavaMajor(unittest.TestCase):
    def test_formato_moderno(self) -> None:
        self.assertEqual(tc.parse_java_major(JAVA_11), 11)
        self.assertEqual(tc.parse_java_major(JAVA_17), 17)

    def test_formato_pre_9(self) -> None:
        self.assertEqual(tc.parse_java_major(JAVA_8), 8)

    def test_saida_irreconhecivel(self) -> None:
        for bad in ("", "comando nao encontrado", 'version "abc"'):
            self.assertIsNone(tc.parse_java_major(bad))


class TestResolveJava(unittest.TestCase):
    """Ordem de resolução: explícito > REVIVAL_JAVA > embarcado > PATH(17+)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        raiz = Path(self._tmp.name)
        self.embarcado = raiz / "jre17" / "java"
        self.embarcado.parent.mkdir(parents=True)
        self.embarcado.write_text("fake", encoding="utf-8")
        self.do_path = raiz / "path" / "java"
        self.do_path.parent.mkdir(parents=True)
        self.do_path.write_text("fake", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _resolver(self, versoes: dict[Path, str], explicit=None, env=None):
        """Executa resolve_java com um mundo de Javas controlado."""

        def fake_run(command, timeout=20.0):
            saida = versoes.get(Path(command[0]))
            return (0, saida) if saida else (1, "não encontrado")

        with mock.patch.object(tc, "BUNDLED_JAVA", self.embarcado), \
             mock.patch.object(tc, "_run", fake_run), \
             mock.patch.object(tc.shutil, "which", lambda _: str(self.do_path)), \
             mock.patch.dict(tc.os.environ, env or {}, clear=False):
            if env is None:
                tc.os.environ.pop(tc.JAVA_ENV_VAR, None)
            return tc.resolve_java(explicit)

    def test_prefere_o_embarcado_quando_o_path_e_java_11(self) -> None:
        """O caso real desta máquina: PATH=11, .tools/jre17=17."""
        status = self._resolver({self.embarcado: JAVA_17, self.do_path: JAVA_11})
        self.assertTrue(status.ok)
        self.assertEqual(status.path, str(self.embarcado))
        self.assertEqual(status.version, "17")
        self.assertIn("embarcado", status.source)

    def test_usa_o_path_quando_ele_e_17_e_nao_ha_embarcado(self) -> None:
        self.embarcado.unlink()
        status = self._resolver({self.do_path: JAVA_17})
        self.assertTrue(status.ok)
        self.assertEqual(status.path, str(self.do_path))
        self.assertEqual(status.source, "PATH")

    def test_rejeita_java_11_com_instrucao_acionavel(self) -> None:
        self.embarcado.unlink()
        status = self._resolver({self.do_path: JAVA_11})
        self.assertFalse(status.ok)
        self.assertIn("Java 11", status.detail)
        self.assertIn("17", status.detail)
        # A instrução tem que dizer o que fazer, não só que falhou — e não
        # pode apontar script aposentado (scripts/setup-patcher-tools.*).
        self.assertIn("REVIVAL_JAVA", status.detail)
        self.assertNotIn("setup-patcher-tools", status.detail)

    def test_explicito_ganha_do_embarcado(self) -> None:
        outro = Path(self._tmp.name) / "meu-jdk"
        outro.write_text("fake", encoding="utf-8")
        status = self._resolver({outro: JAVA_17, self.embarcado: JAVA_17}, explicit=outro)
        self.assertTrue(status.ok)
        self.assertEqual(status.path, str(outro))
        self.assertEqual(status.source, "explícito")

    def test_explicito_invalido_cai_para_o_embarcado(self) -> None:
        status = self._resolver(
            {self.embarcado: JAVA_17},
            explicit=Path(self._tmp.name) / "nao-existe",
        )
        self.assertTrue(status.ok)
        self.assertEqual(status.path, str(self.embarcado))

    def test_variavel_de_ambiente_e_respeitada(self) -> None:
        meu = Path(self._tmp.name) / "env-jdk"
        meu.write_text("fake", encoding="utf-8")
        status = self._resolver(
            {meu: JAVA_17, self.embarcado: JAVA_17},
            env={tc.JAVA_ENV_VAR: str(meu)},
        )
        self.assertTrue(status.ok)
        self.assertEqual(status.path, str(meu))

    def test_nenhum_java_utilizavel(self) -> None:
        self.embarcado.unlink()
        status = self._resolver({})
        self.assertFalse(status.ok)
        self.assertIsNone(status.path)


class TestJarPinning(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _jar(self, conteudo: bytes) -> tuple[Path, str]:
        jar = self.dir / "ferramenta.jar"
        jar.write_bytes(conteudo)
        return jar, tc.sha256_file(jar)

    def test_hash_correto_passa(self) -> None:
        jar, digest = self._jar(b"conteudo autentico")
        status = tc._check_jar("apktool", jar, digest, "3.0.3")
        self.assertTrue(status.ok)
        self.assertEqual(status.version, "3.0.3")

    def test_hash_divergente_bloqueia(self) -> None:
        """Um apktool trocado reserializa diferente (DEAD-ENDS #8)."""
        jar, _ = self._jar(b"binario adulterado")
        status = tc._check_jar("apktool", jar, "0" * 64, "3.0.3")
        self.assertFalse(status.ok)
        self.assertIn("BLOQUEADO", status.detail)
        self.assertIn("0" * 64, status.detail)
        self.assertIn("Não substitua por outra versão", status.detail)

    def test_jar_ausente_orienta_o_setup(self) -> None:
        status = tc._check_jar("uber-apk-signer", self.dir / "sumido.jar", "0" * 64, "1.3.0")
        self.assertFalse(status.ok)
        self.assertIn("Preparar ferramentas", status.detail)

    def test_sha256_file_bate_com_valor_conhecido(self) -> None:
        vazio = self.dir / "vazio.bin"
        vazio.write_bytes(b"")
        self.assertEqual(
            tc.sha256_file(vazio),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

    def test_hashes_pinados_tem_formato_sha256(self) -> None:
        for digest in (tc.APKTOOL_SHA256, tc.SIGNER_SHA256):
            self.assertEqual(len(digest), 64)
            self.assertEqual(digest, digest.lower())
            int(digest, 16)  # levanta se não for hex


class TestChecagensDeAmbiente(unittest.TestCase):
    def test_unitypy_versao_errada_e_recusada(self) -> None:
        falso = mock.MagicMock()
        falso.__version__ = "1.10.0"
        falso.__file__ = "/fake/UnityPy/__init__.py"
        with mock.patch.dict(sys.modules, {"UnityPy": falso}):
            status = tc.check_unitypy()
        self.assertFalse(status.ok)
        self.assertIn("1.25.3", status.detail)
        self.assertIn("DEAD-ENDS", status.detail)

    def test_unitypy_versao_exata_passa(self) -> None:
        falso = mock.MagicMock()
        falso.__version__ = tc.UNITYPY_VERSION
        falso.__file__ = "/fake/UnityPy/__init__.py"
        with mock.patch.dict(sys.modules, {"UnityPy": falso}):
            status = tc.check_unitypy()
        self.assertTrue(status.ok)

    def test_python_atual_atende_ao_minimo(self) -> None:
        # O próprio interpretador que roda os testes precisa servir.
        self.assertTrue(tc.check_python().ok)

    def test_adb_e_opcional(self) -> None:
        with mock.patch.object(tc.shutil, "which", lambda _: None):
            status = tc.check_adb()
        self.assertFalse(status.ok)
        self.assertFalse(status.required, "adb não pode bloquear o patch")

    def test_pillow_e_opcional(self) -> None:
        self.assertFalse(tc.check_pillow().required)

    def test_node_e_opcional_mas_checa_minimo(self) -> None:
        with mock.patch.object(tc.shutil, "which", lambda _: "/usr/bin/node"), \
             mock.patch.object(tc, "_run", lambda cmd, timeout=20.0: (0, "v20.11.0\n")):
            status = tc.check_node()
        self.assertFalse(status.ok)
        self.assertFalse(status.required)
        self.assertIn("22.5.0", status.detail)

    def test_node_nao_lts_nao_bloqueia_mas_recomenda_lts(self) -> None:
        """Node 25 (linha não-LTS) funciona; o gate não pode travar por
        palpite, mas deve recomendar o 24 LTS (npm 12 x 25.3.0 avisa)."""
        with mock.patch.object(tc.shutil, "which", lambda _: "/usr/bin/node"), \
             mock.patch.object(tc, "_run", lambda cmd, timeout=20.0: (0, "v25.3.0\n")):
            status = tc.check_node()
        self.assertTrue(status.ok)
        self.assertFalse(status.required)
        self.assertIn("não-LTS", status.detail)
        self.assertIn("24 LTS", status.detail)

    def test_node_lts_par_fica_limpo(self) -> None:
        with mock.patch.object(tc.shutil, "which", lambda _: "/usr/bin/node"), \
             mock.patch.object(tc, "_run", lambda cmd, timeout=20.0: (0, "v24.15.0\n")):
            status = tc.check_node()
        self.assertTrue(status.ok)
        self.assertIn("mínimo 22.5.0", status.detail)
        self.assertNotIn("não-LTS", status.detail)


class TestRelatorioDaToolchain(unittest.TestCase):
    def test_blocking_ignora_opcionais(self) -> None:
        relatorio = tc.ToolchainReport(
            tools=[
                tc.ToolStatus(name="java", ok=True, required=True),
                tc.ToolStatus(name="adb", ok=False, required=False),
            ]
        )
        self.assertTrue(relatorio.ok)
        self.assertEqual(relatorio.blocking, [])

    def test_obrigatoria_faltando_bloqueia(self) -> None:
        relatorio = tc.ToolchainReport(
            tools=[tc.ToolStatus(name="java", ok=False, required=True)]
        )
        self.assertFalse(relatorio.ok)
        self.assertEqual([t.name for t in relatorio.blocking], ["java"])

    def test_get_e_serializacao(self) -> None:
        relatorio = tc.ToolchainReport(tools=[tc.ToolStatus(name="java", ok=True)])
        self.assertIsNotNone(relatorio.get("java"))
        self.assertIsNone(relatorio.get("inexistente"))
        self.assertIn("tools", relatorio.to_dict())


class TestCliResolveJava(unittest.TestCase):
    """Contrato do `scripts/resolve_java.py` — a sonda de terminal deste
    mesmo resolvedor (os orquestradores shell que a chamavam foram
    aposentados em 2026-08-18; a sonda manual segue documentada em
    docs/APK-PATCH.md).

    stdout = caminho + exit 0; stderr = instrução + exit 3. O caminho impresso
    nunca é um Java < 17: o resolvedor recusa antes de chegar aqui.
    """

    def test_ok_imprime_caminho_e_exit_0(self) -> None:
        from io import StringIO

        import resolve_java  # scripts/ já está no sys.path deste teste

        bom = tc.ToolStatus(name="java", ok=True, path="C:/jre17/bin/java.exe", version="17")
        with (
            mock.patch.object(resolve_java, "resolve_java", return_value=bom) as resolvido,
            mock.patch("sys.stdout", new_callable=StringIO) as saida,
        ):
            codigo = resolve_java.main()
        self.assertEqual(codigo, 0)
        self.assertEqual(saida.getvalue().strip(), "C:/jre17/bin/java.exe")
        resolvido.assert_called_once_with()

    def test_recusa_imprime_instrucao_e_exit_3(self) -> None:
        from io import StringIO

        import resolve_java

        ruim = tc.ToolStatus(
            name="java", ok=False, detail="nenhum Java 17+ utilizável.\nUse o JRE embarcado."
        )
        with (
            mock.patch.object(resolve_java, "resolve_java", return_value=ruim),
            mock.patch("sys.stderr", new_callable=StringIO) as erro,
        ):
            codigo = resolve_java.main()
        self.assertEqual(codigo, 3)
        self.assertIn("Java 17+", erro.getvalue())
        self.assertIn("JRE embarcado", erro.getvalue())


class TestDownloadTool(unittest.TestCase):
    """`download_tool`: pin, atomicidade e recusa em hash divergente."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.logs: list[str] = []

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _jar_fake(self, conteudo: bytes = b"jar-sintetico") -> Path:
        origem = self.dir / "remoto.jar"
        origem.write_bytes(conteudo)
        return origem

    def test_baixa_verifica_e_promove(self) -> None:
        import hashlib

        origem = self._jar_fake()
        destino = self.dir / "outro" / "apktool.jar"
        sha = hashlib.sha256(origem.read_bytes()).hexdigest()
        ok = tc.download_tool(destino, origem.as_uri(), sha, "Jar sintético",
                              log=self.logs.append)
        self.assertTrue(ok)
        self.assertEqual(destino.read_bytes(), origem.read_bytes())
        self.assertFalse((destino.parent / (destino.name + ".part")).exists(),
                         ".part não pode sobrar após promoção")
        self.assertTrue(any("validado" in l for l in self.logs))

    def test_existente_valido_nao_baixa_de_novo(self) -> None:
        import hashlib

        destino = self.dir / "ferramenta.jar"
        destino.write_bytes(b"ja-esta-aqui")
        sha = hashlib.sha256(destino.read_bytes()).hexdigest()
        ok = tc.download_tool(destino, "https://invalido.exemplo/x.jar", sha, "Ferramenta",
                              log=self.logs.append)
        self.assertTrue(ok)
        self.assertTrue(any("já existe" in l for l in self.logs))

    def test_hash_divergente_remove_arquivo(self) -> None:
        origem = self._jar_fake()
        destino = self.dir / "ferramenta.jar"
        ok = tc.download_tool(destino, origem.as_uri(), "0" * 64, "Jar sintético",
                              log=self.logs.append)
        self.assertFalse(ok)
        self.assertFalse(destino.exists(), "JAR com hash errado deve ser removido")
        self.assertTrue(any("não confere" in l for l in self.logs))

    def test_url_morta_limpa_e_devolve_false(self) -> None:
        destino = self.dir / "ferramenta.jar"
        ok = tc.download_tool(destino, (self.dir / "nao-existe.jar").as_uri(), "0" * 64,
                              "Jar sintético", log=self.logs.append)
        self.assertFalse(ok)
        self.assertFalse(destino.exists())
        self.assertFalse((destino.parent / (destino.name + ".part")).exists())


class _CtxFake:
    """JobContext mínimo para prepare_tools (log + run_process + progress)."""

    def __init__(self, rc: int = 0) -> None:
        self.rc = rc
        self.comandos: list[list[str]] = []
        self.logs: list[str] = []

    def log(self, mensagem: str) -> None:
        self.logs.append(mensagem)

    def progress(self, *args) -> None:
        return None

    def run_process(self, command, **kwargs) -> int:
        self.comandos.append([str(c) for c in command])
        return self.rc


class TestPrepareTools(unittest.TestCase):
    def test_java_ausente_levanta_antes_de_baixar(self) -> None:
        ruim = tc.ToolStatus(name="java", ok=False, detail="nenhum Java 17+ utilizável")
        with (
            mock.patch.object(tc, "resolve_java", return_value=ruim),
            mock.patch.object(tc, "download_tool") as baixar,
        ):
            with self.assertRaises(tc.ToolchainError) as cm:
                tc.prepare_tools(_CtxFake())
        self.assertIn("Java", str(cm.exception))
        baixar.assert_not_called()

    def test_baixa_dois_jars_e_valida_com_java(self) -> None:
        bom = tc.ToolStatus(name="java", ok=True, path="C:/jre17/bin/java.exe", version="17",
                            detail="ok")
        ctx = _CtxFake()
        relatorio_falso = tc.ToolchainReport(tools=[])
        with (
            mock.patch.object(tc, "resolve_java", return_value=bom),
            mock.patch.object(tc, "download_tool", return_value=True) as baixar,
            mock.patch.object(tc, "detect_toolchain", return_value=relatorio_falso),
        ):
            relatorio = tc.prepare_tools(ctx)
        self.assertIs(relatorio, relatorio_falso)
        self.assertEqual(baixar.call_count, 2, "apktool + signer")
        urls = [c.args[1] for c in baixar.call_args_list]
        self.assertEqual(urls, [tc.APKTOOL_URL, tc.SIGNER_URL])
        # prova final: java -jar <jar> --version para cada ferramenta
        validacoes = [c for c in ctx.comandos if "--version" in c]
        self.assertEqual(len(validacoes), 2)
        self.assertTrue(all(c[0] == "C:/jre17/bin/java.exe" for c in validacoes))

    def test_download_falho_levanta_erro_claro(self) -> None:
        bom = tc.ToolStatus(name="java", ok=True, path="java", version="17", detail="ok")
        with (
            mock.patch.object(tc, "resolve_java", return_value=bom),
            mock.patch.object(tc, "download_tool", return_value=False),
        ):
            with self.assertRaises(tc.ToolchainError) as cm:
                tc.prepare_tools(_CtxFake())
        self.assertIn("não foi possível obter", str(cm.exception))

    def test_jar_que_nao_executa_levanta_erro(self) -> None:
        bom = tc.ToolStatus(name="java", ok=True, path="java", version="17", detail="ok")
        ctx = _CtxFake(rc=1)
        with (
            mock.patch.object(tc, "resolve_java", return_value=bom),
            mock.patch.object(tc, "download_tool", return_value=True),
        ):
            with self.assertRaises(tc.ToolchainError) as cm:
                tc.prepare_tools(ctx)
        self.assertIn("não executou", str(cm.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
