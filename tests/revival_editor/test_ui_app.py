#!/usr/bin/env python3
"""Regressão da janela mínima do Revival Studio (§30 item 6) e do painel de log.

A janela é construída real (withdraw — nada aparece na tela) e os diálogos são
mockados: teste de GUI não pode travar esperando um humano clicar em "OK".

O caso central é `test_analisar_apk_fluxo_completo`: a UI manda o serviço de
análise para o JobRunner, o worker devolve o resultado pela fila, o estado
avança para APK_ANALISADO e o project.json é gravado — a thread de trabalho
nunca tocou um widget.

Execução: python tests/revival_editor/test_ui_app.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from test_services import apk_sintetico, metadata_sintetico  # noqa: E402

from revival_editor.actions import ACTIONS, MENUS, action_by_id, menu_actions  # noqa: E402
from revival_editor.models import Stage  # noqa: E402
from revival_editor.project import new_project  # noqa: E402
from revival_editor.services import (  # noqa: E402
    EXPECTED_METADATA_VERSION,
    ServerPreflightResult,
)

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - ambiente sem Tcl/Tk
    tk = None


def _bombeiar(root, condicao, timeout=8.0) -> bool:
    """Processa eventos Tk até `condicao` ser verdadeira (ou estourar o tempo).

    TclError = root destruído dentro do ciclo — conta como condição atingida.
    """
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        try:
            root.update()
        except tk.TclError:
            return True
        try:
            atingiu = condicao()
        except tk.TclError:
            return True
        if atingiu:
            return True
        time.sleep(0.02)
    return False


@unittest.skipUnless(tk, "sem Tkinter nesta máquina")
class TestJanelaMinima(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.studio = Path(self._tmp.name) / "studio"
        self.root = tk.Tk()
        self.root.withdraw()
        from revival_editor.ui.app import StudioApp

        self.StudioApp = StudioApp
        with mock.patch("revival_editor.ui.app.messagebox"):
            self.app = StudioApp(self.root, studio_root=self.studio)

    def tearDown(self) -> None:
        try:
            self.app._fechar()
        except tk.TclError:
            pass  # já destruída por teste de fechamento
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        self._tmp.cleanup()

    # -- registro × menus --------------------------------------------------

    def test_registro_e_integro(self) -> None:
        ids = [s.action_id for s in ACTIONS]
        self.assertEqual(len(ids), len(set(ids)), "action_id duplicado")
        for spec in ACTIONS:
            self.assertIn(spec.menu, MENUS)
            self.assertTrue(callable(getattr(self.StudioApp, spec.handler, None)))

    def test_menus_da_janela_minima_existem_e_populados(self) -> None:
        self.assertEqual(tuple(self.app._menus.keys()), MENUS)
        for menu_nome in MENUS:
            menu = self.app._menus[menu_nome]
            self.assertEqual(menu.index("end") + 1, len(menu_actions(menu_nome)))
            for spec in menu_actions(menu_nome):
                rotulos = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)]
                self.assertIn(spec.label, rotulos)

    # -- habilitação por pré-requisito (§9.1) -------------------------------

    def _estado_entrada(self, action_id: str) -> str:
        menu, indice = self.app._entradas[action_id]
        return str(menu.entrycget(indice, "state"))

    def test_sem_projeto_analise_desabilitada_novo_habilitado(self) -> None:
        self.assertEqual(self._estado_entrada("projeto.novo"), "normal")
        self.assertEqual(self._estado_entrada("projeto.abrir"), "normal")
        self.assertEqual(self._estado_entrada("projeto.analisar"), "disabled")

    def test_precheck_exige_analise_previa(self) -> None:
        projeto, _ = new_project("p1", studio_root=self.studio)
        self.app._abrir_projeto_memoria(projeto)
        self.app.refresh()
        self.assertEqual(self._estado_entrada("apk.precheck"), "disabled")
        projeto.state.mark(Stage.APK_ANALISADO)
        self.app.refresh()
        self.assertEqual(self._estado_entrada("apk.precheck"), "normal")
        self.assertEqual(self._estado_entrada("servidor.preflight"), "normal")

    def test_log_continua_usavel_durante_job(self) -> None:
        self.assertTrue(action_by_id("log.limpar").busy_safe)
        self.assertFalse(action_by_id("projeto.analisar").busy_safe)

    # -- painel de log ------------------------------------------------------

    def test_painel_de_log_aplica_teto(self) -> None:
        from revival_editor.ui.log_panel import LogPanel

        for i in range(LogPanel.MAX_LINHAS + 300):
            self.app.log.append(f"linha {i}", "proc")
        self.assertLessEqual(self.app.log.line_count, LogPanel.MAX_LINHAS)
        conteudo = self.app.log.content
        self.assertIn(f"linha {LogPanel.MAX_LINHAS + 299}", conteudo)
        primeira = int(conteudo.splitlines()[0].split()[1])
        self.assertGreaterEqual(primeira, 300, "as linhas mais antigas deveriam ter saído")

        self.app.log.clear()
        self.assertEqual(self.app.log.line_count, 0)

    def test_painel_de_log_salva_em_arquivo(self) -> None:
        self.app.log.append("exit 0", "info")
        destino = self.studio / "logs" / "teste.log"
        linhas = self.app.log.save_to_file(destino)
        self.assertGreaterEqual(linhas, 1)
        self.assertIn("exit 0", destino.read_text(encoding="utf-8"))

    # -- job pelo runner, drenado pelo after() --------------------------------

    def test_job_fluxo_completo_pela_fila(self) -> None:
        self.app._submit("eco", lambda ctx: ctx.log("olá da worker thread"))
        ok = _bombeiar(
            self.root,
            lambda: "eco: concluído" in self.app.var_status.get(),
        )
        self.assertTrue(ok, self.app.var_status.get())
        self.assertIn("olá da worker thread", self.app.log.content)
        self.assertFalse(self.app.runner.is_running)

    def test_segundo_job_concorrente_e_recusado(self) -> None:
        def dorme(ctx):
            for _ in range(200):
                ctx.raise_if_cancelled()
                time.sleep(0.02)
            return 0

        self.app._submit("dorme", dorme)
        self.assertTrue(self.app.runner.is_running)
        with mock.patch("revival_editor.ui.app.messagebox") as caixa:
            self.app.act_analisar_apk()  # exige livre → recusa
            caixa.showwarning.assert_called_once()
        self.app.runner.cancel("fim do teste")
        _bombeiar(self.root, lambda: not self.app.runner.is_running)

    def test_analisar_apk_fluxo_completo(self) -> None:
        apk = apk_sintetico(
            self.studio.parent / "alvo.apk", metadata=metadata_sintetico()
        )
        projeto, _ = new_project(
            "fluxo", studio_root=self.studio, input_apk=apk
        )
        self.app._abrir_projeto_memoria(projeto)
        self.app.refresh()

        with mock.patch("revival_editor.ui.app.messagebox") as caixa:
            self.app.act_analisar_apk()
            # espera o diálogo de modo inspeção: sem aapt, package fica
            # "não medido" e o resultado é aviso, nunca aprovação silenciosa.
            ok = _bombeiar(self.root, lambda: caixa.showwarning.called)
            self.assertTrue(ok, self.app.var_status.get())
            self.assertTrue(self.app.state.has(Stage.APK_ANALISADO))

        salvo = json.loads(
            (self.studio / "fluxo" / "project.json").read_text(encoding="utf-8")
        )
        self.assertIn("APK_ANALISADO", salvo["completed_stages"])
        self.assertIn("analyze", salvo["reports"])
        dados = json.loads(
            (self.studio / "fluxo" / "reports" / "analyze.json").read_text(encoding="utf-8")
        )
        self.assertEqual(dados["metadata_version"], EXPECTED_METADATA_VERSION)
        self.assertFalse(dados["matches_target"], "desconhecido não é aprovação")
        self.assertEqual(self._estado_entrada("apk.precheck"), "normal")

    def test_validar_servidor_falho_nao_marca_etapa(self) -> None:
        projeto, _ = new_project("srv", studio_root=self.studio, server_host="caido.exemplo.com")
        self.app._abrir_projeto_memoria(projeto)
        projeto.state.mark(Stage.APK_ANALISADO)
        self.app.refresh()

        resultado_ruim = ServerPreflightResult(
            host="caido.exemplo.com", ok=False, errors=["health indisponível"]
        )
        with (
            mock.patch("revival_editor.ui.app.server_preflight", return_value=resultado_ruim),
            mock.patch("revival_editor.ui.app.messagebox") as caixa,
        ):
            self.app.act_validar_servidor()
            ok = _bombeiar(self.root, lambda: caixa.showerror.called)
            self.assertTrue(ok, self.app.var_status.get())
            self.assertIn("validar-servidor: FALHOU", self.app.var_status.get())

        self.assertFalse(self.app.state.has(Stage.SERVIDOR_VALIDADO))

    def test_validar_servidor_ok_mostra_checks_e_habilita_pipeline(self) -> None:
        """Fase 5: sucesso marca SERVIDOR_VALIDADO, pinta os checks separados
        e a ação pipeline.completo (fase 6) deixa de ficar cinza."""
        projeto, _ = new_project("srv-ok", studio_root=self.studio, server_host="doom.exemplo.com")
        self.app._abrir_projeto_memoria(projeto)
        projeto.state.mark(Stage.APK_ANALISADO)
        self.app.refresh()
        self.assertEqual(self._estado_entrada("pipeline.completo"), "disabled")

        resultado_bom = ServerPreflightResult(
            host="doom.exemplo.com",
            ok=True,
            checks={
                "dns": {"ok": True, "detail": "hostname resolveu"},
                "tls": {"ok": True, "detail": "handshake HTTPS completo (certificado público)"},
                "health": {"ok": True, "detail": "/revival/health 200 · cliente 1.13.1"},
                "gear_prefix": {"ok": True, "detail": "health 200 · auth probe 400/code 2200"},
            },
            client_version="1.13.1",
            api_version="24.0.0",
            game_data_loaded=True,
        )
        with mock.patch("revival_editor.ui.app.server_preflight", return_value=resultado_bom):
            self.app.act_validar_servidor()
            ok = _bombeiar(self.root, lambda: self.app.state.has(Stage.SERVIDOR_VALIDADO))
            self.assertTrue(ok, self.app.var_status.get())

        self.assertTrue(self.app.state.has(Stage.SERVIDOR_VALIDADO))
        self.assertTrue(self.app._lbl_checks["dns"].cget("text").startswith("✓"))
        self.assertTrue(self.app._lbl_checks["health"].cget("text").startswith("✓"))
        self.assertEqual(self._estado_entrada("pipeline.completo"), "normal")

    def test_painel_de_checks_nao_inventa_verde(self) -> None:
        """Falha de DNS: TLS/health continuam 'não avaliado' — sem verde inventado."""
        resultado = ServerPreflightResult(
            host="sumiu.exemplo.com",
            ok=False,
            checks={"dns": {"ok": False, "detail": "não resolve: Name or service not known"}},
            errors=["dns: não resolve"],
        )
        self.app._mostrar_checks_servidor(resultado)
        self.assertTrue(self.app._lbl_checks["dns"].cget("text").startswith("✗"))
        for chave in ("tls", "health", "gear_prefix"):
            self.assertEqual(
                self.app._lbl_checks[chave].cget("text"),
                "— não avaliado",
                f"{chave} não pode ter verde sem ter sido medido",
            )

    def test_fechar_durante_job_confirma_cancela_e_destroi(self) -> None:
        def dorme(ctx):
            for _ in range(300):
                ctx.raise_if_cancelled()
                time.sleep(0.02)
            return 0

        self.app._submit("dorme", dorme)
        with mock.patch("revival_editor.ui.app.messagebox") as caixa:
            caixa.askyesno.return_value = False
            self.app._ao_fechar()
            caixa.askyesno.assert_called_once()
            self.assertTrue(self.root.winfo_exists(), "recusou sair: janela permanece")
            self.assertTrue(self.app.runner.is_running)

            caixa.askyesno.return_value = True
            self.app._ao_fechar()
            destruiu = _bombeiar(self.root, lambda: not self.root.winfo_exists())
        self.assertTrue(destruiu, "janela deveria ter sido destruída após cancelamento")


if __name__ == "__main__":
    unittest.main(verbosity=2)
