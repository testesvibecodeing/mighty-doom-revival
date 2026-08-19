#!/usr/bin/env python3
"""Regressão do pipeline "Aplicar endpoint" (fase 6).

O pipeline é orquestração: os CLIs reais (patch_apk.py, apktool,
uber-apk-signer…) já têm suas próprias suítes. Aqui um contexto falso roteiriza
as respostas de `run_process` por comando e prova o que é responsabilidade
deste módulo:

- ordem dos passos e uso do **Java resolvido** (nunca `java` do PATH);
- fallback exit 4 → bundle-aware (e bloqueio quando a estratégia é fast-path);
- falha de qualquer etapa devolve `PipelineResult` com `failure` — nunca um
  APK promovido sem verificação pós-assinatura;
- saída publicada só via `promote_atomic` (sem arquivo parcial sobrando);
- gates: análise divergente, toolchain bloqueada, precheck exit 2, preflight
  do servidor, CA com chave privada.

Execução: python tests/revival_editor/test_pipeline.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

import revival_editor.pipeline as pl  # noqa: E402
from revival_editor.actions import action_by_id  # noqa: E402
from revival_editor.models import Stage  # noqa: E402
from revival_editor.pipeline import (  # noqa: E402
    OUTPUT_APK_NAME,
    PipelineError,
    apply_endpoint,
)
from revival_editor.runner import JobCancelled  # noqa: E402
from revival_editor.services import PrecheckResult  # noqa: E402
from revival_editor.toolchain import APKTOOL_JAR, SIGNER_JAR, ToolStatus, ToolchainReport  # noqa: E402

JAVA_FAKE = "C:/tools-fake/jdk-17/bin/java.exe"
PATCH_CLI = "patch_apk.py"
PATCH_BUNDLE_CLI = "patch_bundle_from_report.py"
VERIFY_CLI = "verify_patched_apk.py"


# ----------------------------------------------------------------------
# dublês
# ----------------------------------------------------------------------


@dataclass
class AnaliseFalsa:
    sha256: str = "ab" * 32
    matches_target: bool = True
    divergences: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)


@dataclass
class PreflightFalso:
    ok: bool = True
    errors: list[str] = field(default_factory=list)


class Resposta:
    """Resposta roteirizada: exit code (fixo ou por ordem de chamada) + efeito.

    Com `exits=[0, 1]`, a primeira chamada devolve 0 e as seguintes 1 — é o
    que distingue a verificação pré-assinatura da pós-assinatura, que passam
    pelo mesmo CLI com resultados diferentes.
    """

    def __init__(
        self,
        exit_code: int = 0,
        efeito: Callable[[list[str]], None] | None = None,
        exits: list[int] | None = None,
    ) -> None:
        self.exit_code = exit_code
        self.efeito = efeito
        self.exits = exits
        self._chamadas = 0

    def proximo_exit(self) -> int:
        self._chamadas += 1
        if self.exits is None:
            return self.exit_code
        return self.exits[min(self._chamadas - 1, len(self.exits) - 1)]


Regra = tuple[Callable[[list[str]], bool], Resposta]


class CtxFalso:
    """JobContext de mentira: casa comando com roteiro, registra tudo."""

    def __init__(self, roteiro: list[Regra]) -> None:
        self.roteiro: list[Regra] = list(roteiro)
        self.logs: list[tuple[str, str]] = []
        self.progressos: list[tuple[str, str, Any]] = []
        self.comandos: list[list[str]] = []
        #: levanta JobCancelled depois de N comandos (None = nunca)
        self.cancelado_apos: int | None = None

    def log(self, linha: str, *, stream: str = "info") -> None:
        self.logs.append((stream, linha))

    def progress(self, stage: str, message: str, fraction: Any = None, **_: Any) -> None:
        self.progressos.append((stage, message, fraction))

    def raise_if_cancelled(self) -> None:
        return None

    def temp_path(self, destino: Path | str) -> Path:
        destino = Path(destino)
        return destino.with_name(destino.name + ".parcial")

    def run_process(self, command: list[str], **_: Any) -> int:
        cmd = [str(c) for c in command]
        self.comandos.append(cmd)
        if self.cancelado_apos is not None and len(self.comandos) > self.cancelado_apos:
            raise JobCancelled("cancelado pelo usuário")
        for casador, resposta in self.roteiro:
            if casador(cmd):
                if resposta.efeito:
                    resposta.efeito(cmd)
                return resposta.proximo_exit()
        raise AssertionError(f"comando fora do roteiro: {cmd}")

    # -- inspetores ----------------------------------------------------------

    def nomeados(self, marcador: str) -> list[list[str]]:
        return [c for c in self.comandos if marcador in " ".join(c)]


def _toolchain_ok() -> ToolchainReport:
    return ToolchainReport(
        tools=[ToolStatus(name="java", ok=True, path=JAVA_FAKE, version="17", source="explícito")]
    )


def _toolchain_sem_java() -> ToolchainReport:
    return ToolchainReport(
        tools=[ToolStatus(name="java", ok=False, detail="nenhum Java 17+ utilizável")]
    )


def _efeito_relatorio_patch(conteudo: dict | None = None) -> Callable[[list[str]], None]:
    payload = conteudo if conteudo is not None else {
        "bundles_alterados": ["assets/bin/Data/resources.bundle"],
        "crcs_zerados": ["resources.bundle"],
    }

    def efeito(cmd: list[str]) -> None:
        rel = Path(cmd[cmd.index("--report") + 1])
        rel.parent.mkdir(parents=True, exist_ok=True)
        rel.write_text(json.dumps(payload), encoding="utf-8")

    return efeito


def _efeito_cria_saida(conteudo: bytes = b"APK-RECONSTRUIDO") -> Callable[[list[str]], None]:
    def efeito(cmd: list[str]) -> None:
        destino = Path(cmd[cmd.index("-o") + 1])
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)

    return efeito


# casadores por CLI — a estrutura do comando, não substring solta
def _eh_decode(cmd: list[str]) -> bool:
    return str(APKTOOL_JAR) in cmd and "d" in cmd


def _eh_build(cmd: list[str]) -> bool:
    return str(APKTOOL_JAR) in cmd and "b" in cmd


def _eh_patch(cmd: list[str]) -> bool:
    return any(c.endswith(PATCH_CLI) for c in cmd)


def _eh_patch_bundle(cmd: list[str]) -> bool:
    return any(c.endswith(PATCH_BUNDLE_CLI) for c in cmd)


def _eh_verify(cmd: list[str]) -> bool:
    return any(c.endswith(VERIFY_CLI) for c in cmd)


def _eh_sign(cmd: list[str]) -> bool:
    return str(SIGNER_JAR) in cmd and "--overwrite" in cmd


def _eh_sign_verify(cmd: list[str]) -> bool:
    return str(SIGNER_JAR) in cmd and "--onlyVerify" in cmd


def _roteiro_sucesso(*, patch_exit: int = 0) -> list[Regra]:
    """Roteiro completo com todos os CLIs passando."""
    return [
        (_eh_decode, Resposta(0)),
        (_eh_patch, Resposta(patch_exit, _efeito_relatorio_patch())),
        (_eh_patch_bundle, Resposta(0, _efeito_relatorio_patch())),
        (_eh_build, Resposta(0, _efeito_cria_saida())),
        (_eh_verify, Resposta(0)),
        (_eh_sign, Resposta(0)),
        (_eh_sign_verify, Resposta(0)),
    ]


def _precheck(exit_code: int = 0) -> PrecheckResult:
    return PrecheckResult(
        host="doom.exemplo.com",
        exit_code=exit_code,
        verdict={0: "fast-path", 4: "bundle-aware"}.get(exit_code, "invalido"),
        lines=[f"precheck exit {exit_code}"],
    )


class BasePipeline(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.apk = self.dir / "entrada.apk"
        self.apk.write_bytes(b"APK-ORIGINAL")
        self.projeto = self.dir / "proj"
        self.projeto.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _rodar(
        self,
        ctx: CtxFalso,
        *,
        precheck_exit: int = 0,
        analise: AnaliseFalsa | None = None,
        preflight: PreflightFalso | None = None,
        toolchain: ToolchainReport | None = None,
        **sobrepos: Any,
    ) -> pl.PipelineResult:
        padrao: dict[str, Any] = dict(
            apk=self.apk,
            host="doom.exemplo.com",
            project_dir=self.projeto,
            analyze=lambda apk, log: analise or AnaliseFalsa(),
            preflight=lambda host, **kw: preflight or PreflightFalso(),
            toolchain_detect=lambda **kw: toolchain or _toolchain_ok(),
        )
        padrao.update(sobrepos)
        with mock.patch.object(
            pl, "check_hostname_budget", lambda *a, **kw: _precheck(precheck_exit)
        ):
            return apply_endpoint(ctx, **padrao)

    @property
    def saida(self) -> Path:
        return self.projeto / "output" / OUTPUT_APK_NAME


# ----------------------------------------------------------------------
# registro da ação (o que liga o pipeline à UI do Studio)
# ----------------------------------------------------------------------


class TestRegistroDaAcao(unittest.TestCase):
    def test_pipeline_completo_exige_servidor_validado(self) -> None:
        """A ação só habilita depois do gate da fase 5 — ordem do §9.1."""
        spec = action_by_id("pipeline.completo")
        self.assertEqual(spec.requires, Stage.SERVIDOR_VALIDADO)
        self.assertEqual(spec.menu, "APK")


# ----------------------------------------------------------------------
# caminho feliz
# ----------------------------------------------------------------------


class TestPipelineSucesso(BasePipeline):
    def test_caminho_feliz_auto_varre_bundles_como_prova(self) -> None:
        """auto com fast path exit 0 AINDA varre os bundles (regressão real).

        O fast path exit 0 só troca o host no global-metadata; o host oficial
        da gameplay vive em bundles Addressables invisíveis ao scan cru (LZ4
        fragmenta). Sem o sweep de prova o pipeline só descobria o resto no
        verify-pre, depois do apktool b desperdiçado (VERIFY_PRE exit 5).
        """
        ctx = CtxFalso(_roteiro_sucesso())
        resultado = self._rodar(ctx)

        self.assertTrue(resultado.ok, f"steps={resultado.steps} failure={resultado.failure}")
        self.assertIsNone(resultado.failure)
        self.assertEqual(resultado.strategy_used, "bundle-aware")
        self.assertEqual(len(ctx.nomeados(PATCH_BUNDLE_CLI)), 1)
        self.assertIn("--sweep-all-bundles", " ".join(ctx.nomeados(PATCH_BUNDLE_CLI)[0]))

        self.assertTrue(self.saida.is_file(), "APK final deveria existir")
        self.assertEqual(self.saida.read_bytes(), b"APK-RECONSTRUIDO")
        self.assertFalse(
            (self.projeto / "output" / (OUTPUT_APK_NAME + ".parcial")).exists(),
            "temporário não pode sobrar depois do promote",
        )
        # o APK de entrada é imutável
        self.assertEqual(self.apk.read_bytes(), b"APK-ORIGINAL")
        self.assertEqual(resultado.bundles_alterados, ["assets/bin/Data/resources.bundle"])
        self.assertEqual(resultado.crcs_zerados, ["resources.bundle"])
        self.assertTrue(self.projeto.joinpath("decoded").is_dir(), "workspace decodado criado")

    def test_java_resolvido_nao_e_o_do_path(self) -> None:
        ctx = CtxFalso(_roteiro_sucesso())
        self._rodar(ctx)
        java_comandos = [c for c in ctx.comandos if c[0] != sys.executable]
        self.assertTrue(java_comandos)
        for comando in java_comandos:
            self.assertEqual(comando[0], JAVA_FAKE,
                             "todo subprocesso Java usa o resolvedor, nunca PATH")

    def test_ordem_dos_passos(self) -> None:
        ctx = CtxFalso(_roteiro_sucesso())
        resultado = self._rodar(ctx)
        self.assertEqual(
            [s.name for s in resultado.steps],
            ["decode", "patch", "rebuild", "verify-pre", "sign", "sign-verify", "verify", "publicar"],
        )
        self.assertTrue(all(s.ok for s in resultado.steps))

    def test_progresso_indeterminado_no_apktool(self) -> None:
        ctx = CtxFalso(_roteiro_sucesso())
        self._rodar(ctx)
        fracoes = {stage: fracao for stage, _, fracao in ctx.progressos}
        self.assertIsNone(fracoes["decode"], "apktool d é indeterminado")
        self.assertIsNone(fracoes["rebuild"], "apktool b é indeterminado")

    def test_relatorio_do_pipeline_e_serializavel(self) -> None:
        ctx = CtxFalso(_roteiro_sucesso())
        resultado = self._rodar(ctx)
        dados = resultado.to_dict()
        self.assertTrue(dados["ok"])
        self.assertEqual(dados["host"], "doom.exemplo.com")
        self.assertEqual(len(dados["steps"]), 8)
        json.dumps(dados)  # não pode levantar


# ----------------------------------------------------------------------
# estratégias de patch
# ----------------------------------------------------------------------


class TestPipelineEstrategias(BasePipeline):
    def test_exit_4_cai_para_bundle_aware(self) -> None:
        ctx = CtxFalso(_roteiro_sucesso(patch_exit=4))
        resultado = self._rodar(ctx)
        self.assertTrue(resultado.ok, str(resultado.failure))
        self.assertEqual(resultado.strategy_used, "bundle-aware")
        self.assertEqual(len(ctx.nomeados(PATCH_CLI)), 1)
        self.assertEqual(len(ctx.nomeados(PATCH_BUNDLE_CLI)), 1)
        self.assertIn("--sweep-all-bundles", " ".join(ctx.nomeados(PATCH_BUNDLE_CLI)[0]))

    def test_fast_path_escolhido_bloqueia_no_exit_4(self) -> None:
        ctx = CtxFalso(_roteiro_sucesso(patch_exit=4))
        resultado = self._rodar(ctx, strategy="fast-path")
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.failure.code, "PATCH_ESTRATEGIA")
        self.assertEqual(resultado.failure.exit_code, 4)
        self.assertEqual(ctx.nomeados(PATCH_BUNDLE_CLI), [], "fast-path não varre bundles")
        self.assertFalse(self.saida.exists())

    def test_bundle_aware_explicito_varre_ate_com_fast_ok(self) -> None:
        ctx = CtxFalso(_roteiro_sucesso(patch_exit=0))
        resultado = self._rodar(ctx, strategy="bundle-aware")
        self.assertTrue(resultado.ok, str(resultado.failure))
        self.assertEqual(resultado.strategy_used, "bundle-aware")
        self.assertEqual(len(ctx.nomeados(PATCH_BUNDLE_CLI)), 1)

    def test_auto_com_fast_ok_mas_sweep_bloqueado_falha_antes_do_rebuild(self) -> None:
        """Regressão e2e-vps-fase13: 5 refs oficiais no bundle de cenas.

        Fast path exit 0 + sweep bloqueado (exit 4) tem que falhar em PATCH,
        antes do apktool b — nunca construir um APK que o verify-pre
        rejeitaria (era o falso "progresso" de 90s de build desperdiçado).
        """
        roteiro = _roteiro_sucesso(patch_exit=0)
        roteiro[2] = (_eh_patch_bundle, Resposta(4, _efeito_relatorio_patch()))
        ctx = CtxFalso(roteiro)
        resultado = self._rodar(ctx)  # auto

        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.failure.code, "PATCH")
        self.assertEqual(resultado.failure.exit_code, 4)
        self.assertEqual([c for c in ctx.comandos if _eh_build(c)], [],
                         "rebuild não pode rodar com host oficial remanescente")
        self.assertFalse(self.saida.exists())

    def test_patch_falhando_bloqueia_antes_do_rebuild(self) -> None:
        roteiro = _roteiro_sucesso()
        roteiro[1] = (_eh_patch, Resposta(3, _efeito_relatorio_patch()))
        roteiro[2] = (_eh_patch_bundle, Resposta(3, _efeito_relatorio_patch()))
        ctx = CtxFalso(roteiro)
        resultado = self._rodar(ctx)
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.failure.code, "PATCH")
        self.assertEqual(resultado.failure.exit_code, 3)
        self.assertEqual([c for c in ctx.comandos if _eh_build(c)], [],
                         "rebuild não pode rodar com patch falhado")
        self.assertFalse(self.saida.exists())


# ----------------------------------------------------------------------
# gates antes do decode
# ----------------------------------------------------------------------


class TestPipelineGates(BasePipeline):
    def test_apk_ausente_levanta_pipeline_error(self) -> None:
        ctx = CtxFalso([])
        with self.assertRaises(PipelineError):
            apply_endpoint(
                ctx, apk=self.dir / "nao-existe.apk", host="doom.exemplo.com",
                project_dir=self.projeto,
            )
        self.assertEqual(ctx.comandos, [])

    def test_analise_divergente_bloqueia_tudo(self) -> None:
        ctx = CtxFalso(_roteiro_sucesso())
        resultado = self._rodar(
            ctx,
            analise=AnaliseFalsa(matches_target=False,
                                 divergences=["versão: 1.12.0 (esperado 1.13.1)"]),
        )
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.failure.code, "ANALISE_ALVO")
        self.assertIn("1.12.0", resultado.failure.details)
        self.assertEqual(ctx.comandos, [], "nenhum CLI pode rodar sem alvo confirmado")

    def test_toolchain_bloqueada_para_antes_do_decode(self) -> None:
        ctx = CtxFalso(_roteiro_sucesso())
        resultado = self._rodar(ctx, toolchain=_toolchain_sem_java())
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.failure.code, "TOOLCHAIN")
        self.assertIn("Java", resultado.failure.details)
        self.assertEqual(ctx.comandos, [])

    def test_precheck_exit_2_bloqueia(self) -> None:
        ctx = CtxFalso(_roteiro_sucesso())
        resultado = self._rodar(ctx, precheck_exit=2)
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.failure.code, "PRECHECK_INVALIDO")
        self.assertEqual(resultado.precheck_exit, 2)
        self.assertEqual(ctx.comandos, [])

    def test_preflight_recusado_bloqueia(self) -> None:
        ctx = CtxFalso(_roteiro_sucesso())
        resultado = self._rodar(
            ctx, preflight=PreflightFalso(ok=False, errors=["certificado vencido"])
        )
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.failure.code, "SERVER_PREFLIGHT")
        self.assertIn("certificado vencido", resultado.failure.details)
        self.assertEqual(ctx.comandos, [], "gate da fase 5: sem decode sem servidor válido")

    def test_ca_com_chave_privada_e_recusada_antes_de_tudo(self) -> None:
        ca_ruim = self.dir / "ca.pem"
        ca_ruim.write_text(
            "-----BEGIN RSA PRIVATE KEY-----\nxxx\n-----END RSA PRIVATE KEY-----\n",
            encoding="utf-8",
        )
        ctx = CtxFalso(_roteiro_sucesso())
        with self.assertRaises(PipelineError) as cm:
            apply_endpoint(
                ctx, apk=self.apk, host="doom.exemplo.com", project_dir=self.projeto,
                ca_file=ca_ruim,
            )
        self.assertIn("chave privada", str(cm.exception))
        self.assertEqual(ctx.comandos, [])

    def test_ca_valida_aparece_no_comando_do_patch(self) -> None:
        ca = self.dir / "ca.pem"
        ca.write_text(
            "-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----\n", encoding="utf-8"
        )
        ctx = CtxFalso(_roteiro_sucesso())
        resultado = self._rodar(ctx, ca_file=ca)
        self.assertTrue(resultado.ok, str(resultado.failure))
        patch_cmd = ctx.nomeados(PATCH_CLI)[0]
        self.assertIn("--ca", patch_cmd)


# ----------------------------------------------------------------------
# falhas tardias: nada inválido vira APK final
# ----------------------------------------------------------------------


class TestPipelineFalhasTardias(BasePipeline):
    def test_verify_pos_assinatura_falhando_nao_promove(self) -> None:
        roteiro = _roteiro_sucesso()
        # verify pré-assinatura passa (1ª chamada), pós-assinatura falha (2ª)
        roteiro[4] = (_eh_verify, Resposta(exits=[0, 1]))
        ctx = CtxFalso(roteiro)
        resultado = self._rodar(ctx)

        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.failure.code, "VERIFY_POS")
        self.assertFalse(self.saida.exists(),
                         "APK que falhou na verificação pós-assinatura não promove")
        self.assertTrue((self.projeto / "build" / "revival-unsigned.apk").exists(),
                        "o assinado fica retido em build/ como evidência")
        self.assertEqual(resultado.verify_report,
                         str(self.projeto / "reports" / "final-apk-verification.json"))

    def test_verify_pre_assinatura_falhando_nao_assina(self) -> None:
        roteiro = _roteiro_sucesso()
        roteiro[4] = (_eh_verify, Resposta(exits=[1, 0]))
        ctx = CtxFalso(roteiro)
        resultado = self._rodar(ctx)
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.failure.code, "VERIFY_PRE")
        self.assertEqual([c for c in ctx.comandos if _eh_sign(c)], [],
                         "não assina APK que já falhou na verificação")
        self.assertFalse(self.saida.exists())

    def test_rebuild_falhando_registra_e_bloqueia(self) -> None:
        roteiro = _roteiro_sucesso()
        roteiro[3] = (_eh_build, Resposta(1))
        ctx = CtxFalso(roteiro)
        resultado = self._rodar(ctx)
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.failure.code, "REBUILD")
        self.assertEqual(resultado.failure.exit_code, 1)

    def test_sign_falhando_nao_promove(self) -> None:
        roteiro = _roteiro_sucesso()
        roteiro[5] = (_eh_sign, Resposta(1))
        ctx = CtxFalso(roteiro)
        resultado = self._rodar(ctx)
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.failure.code, "SIGN")
        self.assertFalse(self.saida.exists())

    def test_cancelamento_propaga_job_cancelled(self) -> None:
        ctx = CtxFalso(_roteiro_sucesso())
        ctx.cancelado_apos = 1  # cancela depois do decode
        with self.assertRaises(JobCancelled):
            self._rodar(ctx)


if __name__ == "__main__":
    unittest.main(verbosity=2)
