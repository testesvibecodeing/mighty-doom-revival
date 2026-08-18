#!/usr/bin/env python3
"""Regressão do JobRunner e do mascaramento de segredos.

Cobre os quatro finais exigidos pela fase 2 do plano — concluído, falho,
cancelado e timeout — mais as duas garantias que evitam estrago:

  - cancelar no meio de uma escrita NÃO substitui a saída válida anterior;
  - a worker thread só se comunica por fila (nenhum widget é tocado).

Execução: python tests/revival_editor/test_runner.py
"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from revival_editor.redaction import MASK, mask_mapping, mask_secrets  # noqa: E402
from revival_editor.runner import (  # noqa: E402
    DoneEvent,
    JobCancelled,
    JobRunner,
    JobState,
    LogEvent,
    ProgressEvent,
    promote_atomic,
)


class TestMascaramento(unittest.TestCase):
    def test_userinfo_de_url(self) -> None:
        # O padding do fast path vira userinfo; não pode vazar no painel.
        saida = mask_secrets("patch aplicado: https://u000@doom.exemplo.com/")
        self.assertNotIn("u000", saida)
        self.assertIn("doom.exemplo.com", saida, "o host precisa continuar legível")

    def test_bearer_e_authorization(self) -> None:
        self.assertNotIn("abc123def456", mask_secrets("Authorization: Bearer abc123def456"))
        self.assertNotIn("abc123def456", mask_secrets("curl -H 'Bearer abc123def456'"))

    def test_chave_valor_sensivel(self) -> None:
        for entrada in (
            "REVIVAL_ADMIN_TOKEN=segredo-do-painel",
            "password: minhasenha",
            "jwt_secret = xyz789",
        ):
            self.assertNotIn("segredo-do-painel", mask_secrets(entrada))
            saida = mask_secrets(entrada)
            self.assertIn(MASK, saida)

    def test_flag_de_linha_de_comando(self) -> None:
        saida = mask_secrets("python scripts/client_harness.py --admin-token TOKEN-REAL --duration 300")
        self.assertNotIn("TOKEN-REAL", saida)
        self.assertIn("--duration 300", saida, "argumentos não sensíveis continuam visíveis")

    def test_header_do_jogo(self) -> None:
        self.assertNotIn("opaco43chars", mask_secrets("x-ubu-token: opaco43chars"))

    def test_jwt(self) -> None:
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.assinaturaAqui"
        self.assertNotIn("assinaturaAqui", mask_secrets(f"session token = {jwt}"))

    def test_chave_privada_pem(self) -> None:
        pem = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADAN\nbase64\n-----END PRIVATE KEY-----"
        saida = mask_secrets(f"CA carregada:\n{pem}")
        self.assertNotIn("MIIEvQIBADAN", saida)

    def test_nao_mascara_o_que_e_diagnostico(self) -> None:
        """Mascarar demais quebra a correlação logcat x [req] da boot-diagnostics."""
        linha = (
            "[req] POST /collections/doom/game/events/get-schedule -> 200 123B 4ms "
            "sha256=519bfbb18c5bbab78f450b549777774e7d0ed78cd8b42cc25c7a2d3167669f35"
        )
        saida = mask_secrets(linha)
        self.assertIn("game/events/get-schedule", saida)
        self.assertIn("519bfbb18c5bbab7", saida, "hash não é segredo")
        self.assertIn("200", saida)

    def test_idempotente(self) -> None:
        original = "Authorization: Bearer abc123def456"
        self.assertEqual(mask_secrets(original), mask_secrets(mask_secrets(original)))

    def test_mask_mapping_por_nome_de_chave(self) -> None:
        limpo = mask_mapping(
            {
                "server_host": "doom.exemplo.com",
                "admin_token": "segredo",
                "aninhado": {"keystore_password": "senha", "sha256": "abc"},
                "lista": ["Bearer tokenzao123", "ok"],
            }
        )
        self.assertEqual(limpo["server_host"], "doom.exemplo.com")
        self.assertEqual(limpo["admin_token"], MASK)
        self.assertEqual(limpo["aninhado"]["keystore_password"], MASK)
        self.assertEqual(limpo["aninhado"]["sha256"], "abc")
        self.assertNotIn("tokenzao123", limpo["lista"][0])

    def test_mask_secrets_aceita_none(self) -> None:
        self.assertEqual(mask_secrets(None), "")


class TestJobRunner(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.runner = JobRunner(log_dir=self.dir / "logs")

    def tearDown(self) -> None:
        self.runner.close()
        self._tmp.cleanup()

    # -- finais exigidos pelo plano ------------------------------------------

    def test_job_concluido(self) -> None:
        def trabalho(ctx):
            ctx.log("começando")
            ctx.progress("etapa", "meio", 0.5)
            return {"resultado": 42}

        self.runner.submit("ok", trabalho)
        eventos, done = self.runner.drain_until_done()

        self.assertIsNotNone(done)
        self.assertEqual(done.state, JobState.CONCLUIDO)
        self.assertEqual(done.result, {"resultado": 42})
        self.assertIsNone(done.failure)
        self.assertTrue(any(isinstance(e, LogEvent) for e in eventos))
        self.assertTrue(any(isinstance(e, ProgressEvent) for e in eventos))

    def test_job_falho_preserva_tipo_e_traceback(self) -> None:
        def trabalho(ctx):
            raise ValueError("hostname não cabe no fast path")

        self.runner.submit("falha", trabalho)
        _, done = self.runner.drain_until_done()

        self.assertEqual(done.state, JobState.FALHOU)
        self.assertEqual(done.failure.code, "ValueError")
        self.assertIn("fast path", done.failure.message)
        self.assertIn("Traceback", done.failure.details)

    def test_job_cancelado(self) -> None:
        liberado = threading.Event()

        def trabalho(ctx):
            liberado.set()
            for _ in range(2000):
                ctx.raise_if_cancelled()
                time.sleep(0.005)
            return "nunca chega aqui"

        self.runner.submit("longo", trabalho)
        self.assertTrue(liberado.wait(5), "worker não iniciou")
        self.assertTrue(self.runner.cancel())

        _, done = self.runner.drain_until_done()
        self.assertEqual(done.state, JobState.CANCELADO)
        self.assertIsNone(done.result)

    def test_job_timeout(self) -> None:
        def trabalho(ctx):
            for _ in range(2000):
                ctx.raise_if_cancelled()
                time.sleep(0.01)
            return "nunca"

        self.runner.submit("lento", trabalho, timeout=0.3)
        _, done = self.runner.drain_until_done()

        self.assertEqual(done.state, JobState.TIMEOUT)
        self.assertIn("timeout", done.failure.message.lower())

    def test_timeout_nao_dispara_em_job_rapido(self) -> None:
        self.runner.submit("rapido", lambda ctx: "pronto", timeout=10)
        _, done = self.runner.drain_until_done()
        self.assertEqual(done.state, JobState.CONCLUIDO)
        self.assertEqual(done.result, "pronto")

    # -- um job por vez -------------------------------------------------------

    def test_recusa_segundo_job_concorrente(self) -> None:
        rodando = threading.Event()
        pode_sair = threading.Event()

        def trabalho(ctx):
            rodando.set()
            pode_sair.wait(5)
            return "fim"

        self.runner.submit("primeiro", trabalho)
        self.assertTrue(rodando.wait(5))

        with self.assertRaises(RuntimeError) as ctx:
            self.runner.submit("segundo", lambda c: None)
        self.assertIn("primeiro", str(ctx.exception))

        pode_sair.set()
        self.runner.drain_until_done()

    def test_aceita_novo_job_apos_o_anterior_terminar(self) -> None:
        self.runner.submit("a", lambda ctx: 1)
        self.runner.drain_until_done()
        self.runner.submit("b", lambda ctx: 2)
        _, done = self.runner.drain_until_done()
        self.assertEqual(done.result, 2)

    def test_is_running_reflete_o_ciclo(self) -> None:
        self.assertFalse(self.runner.is_running)
        pode_sair = threading.Event()
        rodando = threading.Event()

        def trabalho(ctx):
            rodando.set()
            pode_sair.wait(5)

        self.runner.submit("x", trabalho)
        self.assertTrue(rodando.wait(5))
        self.assertTrue(self.runner.is_running)
        pode_sair.set()
        self.runner.drain_until_done()
        self.assertFalse(self.runner.is_running)

    def test_cancel_sem_job_retorna_false(self) -> None:
        self.assertFalse(self.runner.cancel())

    # -- escrita segura -------------------------------------------------------

    def test_cancelar_durante_escrita_preserva_a_saida_anterior(self) -> None:
        """A garantia do plano: cancelamento não corrompe a saída válida."""
        destino = self.dir / "mighty-doom-revival.apk"
        destino.write_text("APK VALIDO ANTERIOR", encoding="utf-8")
        escrevendo = threading.Event()

        def trabalho(ctx):
            parcial = ctx.temp_path(destino)
            parcial.write_text("METADE DE UM APK NOVO", encoding="utf-8")
            escrevendo.set()
            ctx.cancel_token.wait(5)
            ctx.raise_if_cancelled()
            promote_atomic(parcial, destino)  # nunca alcançado

        self.runner.submit("build", trabalho)
        self.assertTrue(escrevendo.wait(5))
        self.runner.cancel()
        _, done = self.runner.drain_until_done()

        self.assertEqual(done.state, JobState.CANCELADO)
        self.assertEqual(
            destino.read_text(encoding="utf-8"),
            "APK VALIDO ANTERIOR",
            "a saída aprovada anterior não pode ser tocada",
        )
        parciais = list(self.dir.glob("*.parcial"))
        self.assertTrue(parciais, "o parcial deve ser preservado como evidência")

    def test_promote_atomic_substitui_destino(self) -> None:
        origem = self.dir / "novo.tmp"
        destino = self.dir / "final.apk"
        origem.write_text("novo", encoding="utf-8")
        destino.write_text("velho", encoding="utf-8")
        promote_atomic(origem, destino)
        self.assertEqual(destino.read_text(encoding="utf-8"), "novo")
        self.assertFalse(origem.exists())

    def test_promote_atomic_sem_temporario(self) -> None:
        with self.assertRaises(FileNotFoundError):
            promote_atomic(self.dir / "nao-existe", self.dir / "destino")

    # -- log e mascaramento no caminho quente ---------------------------------

    def test_log_do_job_e_mascarado_na_fila(self) -> None:
        def trabalho(ctx):
            ctx.log("conectando com Authorization: Bearer TOKEN-SECRETO-123")
            return None

        self.runner.submit("log", trabalho)
        eventos, _ = self.runner.drain_until_done()
        linhas = [e.line for e in eventos if isinstance(e, LogEvent)]
        self.assertTrue(linhas)
        self.assertFalse(any("TOKEN-SECRETO-123" in l for l in linhas))

    def test_log_e_gravado_em_arquivo(self) -> None:
        self.runner.submit("arquivo", lambda ctx: ctx.log("linha de teste"))
        self.runner.drain_until_done()
        arquivos = list((self.dir / "logs").glob("*.log"))
        self.assertEqual(len(arquivos), 1)
        conteudo = arquivos[0].read_text(encoding="utf-8")
        self.assertIn("linha de teste", conteudo)
        self.assertIn("concluido", conteudo)

    def test_poll_nao_bloqueia_quando_vazio(self) -> None:
        self.assertEqual(self.runner.poll(), [])

    # -- subprocesso ----------------------------------------------------------

    def test_run_process_captura_saida_e_exit_code(self) -> None:
        def trabalho(ctx):
            return ctx.run_process([sys.executable, "-c", "print('ola do subprocesso')"])

        self.runner.submit("proc", trabalho)
        eventos, done = self.runner.drain_until_done()
        self.assertEqual(done.state, JobState.CONCLUIDO)
        self.assertEqual(done.result, 0)
        linhas = [e.line for e in eventos if isinstance(e, LogEvent)]
        self.assertTrue(any("ola do subprocesso" in l for l in linhas))

    def test_run_process_propaga_exit_code_nao_zero(self) -> None:
        def trabalho(ctx):
            return ctx.run_process([sys.executable, "-c", "import sys; sys.exit(4)"])

        self.runner.submit("proc4", trabalho)
        _, done = self.runner.drain_until_done()
        self.assertEqual(done.result, 4, "exit 4 do precheck precisa chegar intacto")

    def test_run_process_recusa_comando_invalido(self) -> None:
        def trabalho(ctx):
            return ctx.run_process("nao pode ser string")  # type: ignore[arg-type]

        self.runner.submit("mau", trabalho)
        _, done = self.runner.drain_until_done()
        self.assertEqual(done.state, JobState.FALHOU)
        self.assertEqual(done.failure.code, "ValueError")

    def test_run_process_e_encerrado_no_cancelamento(self) -> None:
        rodando = threading.Event()

        def trabalho(ctx):
            programa = (
                "import sys,time\n"
                "print('vivo', flush=True)\n"
                "[ (print('tick', flush=True), time.sleep(0.05)) for _ in range(400) ]\n"
            )
            rodando.set()
            return ctx.run_process([sys.executable, "-c", programa])

        self.runner.submit("infinito", trabalho)
        self.assertTrue(rodando.wait(5))
        time.sleep(0.3)
        self.runner.cancel()
        _, done = self.runner.drain_until_done(timeout=20)

        self.assertIsNotNone(done, "o job precisa terminar após o cancelamento")
        self.assertEqual(done.state, JobState.CANCELADO)


class TestJobStateEnum(unittest.TestCase):
    def test_terminalidade(self) -> None:
        self.assertFalse(JobState.PENDENTE.terminal)
        self.assertFalse(JobState.RODANDO.terminal)
        for estado in (JobState.CONCLUIDO, JobState.FALHOU, JobState.CANCELADO, JobState.TIMEOUT):
            self.assertTrue(estado.terminal)


if __name__ == "__main__":
    unittest.main(verbosity=2)
