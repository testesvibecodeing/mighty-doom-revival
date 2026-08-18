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

    # -- Ferramentas (fase 3) ------------------------------------------------

    def test_ferramentas_disponiveis_sem_projeto(self) -> None:
        """Preparar/verificar ferramentas não depende de projeto aberto."""
        self.assertEqual(self._estado_entrada("ferramentas.status"), "normal")
        self.assertEqual(self._estado_entrada("ferramentas.preparar"), "normal")

    def test_verificar_ferramentas_mostra_caminho_e_versao(self) -> None:
        """Gate da fase 3: a tela informa caminho e versão de cada ferramenta."""
        from revival_editor.toolchain import ToolStatus, ToolchainReport

        relatorio = ToolchainReport(
            tools=[
                ToolStatus(name="java", ok=True, path="C:/jre17/bin/java.exe", version="17",
                           detail="ok", source="JRE 17 embarcado (.tools/jre17)"),
                ToolStatus(name="apktool", ok=False, detail=".tools/apktool.jar ausente."),
            ]
        )
        with (
            mock.patch("revival_editor.ui.app._trabalho_ferramentas_status", return_value=relatorio),
            mock.patch("revival_editor.ui.app.messagebox") as caixa,
        ):
            self.app.act_verificar_ferramentas()
            ok = _bombeiar(self.root, lambda: caixa.showinfo.called)
            self.assertTrue(ok, self.app.var_status.get())

        _titulo, texto = caixa.showinfo.call_args[0]
        self.assertIn("bloqueando: apktool", texto, "pendência obrigatória precisa aparecer")
        self.assertIn("java 17", texto)
        self.assertIn("C:/jre17/bin/java.exe", texto, "caminho do Java na tela")
        self.assertIn("apktool", texto)

    def test_preparar_ferramentas_exige_confirmacao(self) -> None:
        """O plano manda confirmar antes de download — recusa não submete job."""
        with mock.patch("revival_editor.ui.app.messagebox") as caixa:
            caixa.askyesno.return_value = False
            self.app.act_preparar_ferramentas()
        self.assertFalse(self.app.runner.is_running)
        caixa.askyesno.assert_called_once()

    def test_comando_preparar_ferramentas_e_headless(self) -> None:
        """O botão usa o script oficial e SEMPRE em modo --headless (§9.2)."""
        from revival_editor.ui.app import _comando_preparar_ferramentas

        comando = _comando_preparar_ferramentas(self.app.repo_root)
        self.assertEqual(comando[-1], "--headless", "sem a flag o wrapper reabriria o Studio")
        self.assertTrue(Path(comando[-2]).is_file(), f"script ausente: {comando[-2]}")
        esperado = ".bat" if sys.platform.startswith("win") else ".sh"
        self.assertTrue(comando[-2].endswith(esperado))

    def test_preparar_ferramentas_confirma_e_encadeia_verificacao(self) -> None:
        from revival_editor.toolchain import ToolStatus, ToolchainReport

        relatorio = ToolchainReport(tools=[ToolStatus(name="java", ok=True, version="17", detail="ok")])
        comando_inofensivo = [sys.executable, "-c", "print('preparado-dry')"]
        with (
            mock.patch("revival_editor.ui.app.messagebox") as caixa,
            mock.patch(
                "revival_editor.ui.app._comando_preparar_ferramentas",
                return_value=comando_inofensivo,
            ),
            mock.patch("revival_editor.ui.app._trabalho_ferramentas_status", return_value=relatorio),
        ):
            caixa.askyesno.return_value = True
            self.app.act_preparar_ferramentas()
            # 1º job: preparo; ao concluir, encadeia a verificação da toolchain
            ok = _bombeiar(self.root, lambda: caixa.showinfo.called)
            self.assertTrue(ok, self.app.var_status.get())

        caixa.askyesno.assert_called_once()
        self.assertIn("preparado-dry", self.app.log.content)
        # a verificação encadeada mostrou o relatório mockado na tela
        _titulo, texto = caixa.showinfo.call_args[0]
        self.assertIn("java 17", texto)

    # -- Visuais / loading screen (fase 7) -----------------------------------

    def test_aba_visuais_existe_e_acao_abre(self) -> None:
        abas = [self.app.notebook.tab(widget, "text") for widget in self.app.notebook.tabs()]
        self.assertIn("Visuais", abas)
        self.app.act_visuals_loading()
        self.assertEqual(self.app.notebook.select(), str(self.app.visuals_tab))

    def test_loading_modo_texto_compoe_e_modo_imagem_sem_fundo_bloqueia(self) -> None:
        aba = self.app.visuals_tab
        aba.var_mode.set("Só Texto")
        aba.render()
        self.assertIsNotNone(aba.preview)
        self.assertEqual(aba.preview.size, (2048, 2048), "tamanho real da textura")

        aba.var_mode.set("Imagem")
        aba.render()
        self.assertIsNone(aba.preview, "modo imagem sem fundo não compõe")
        self.assertEqual(str(aba.btn_injetar.instate(["disabled"])), "True",
                         "injetar sem arte fica desabilitado")

    def test_injetar_invalida_assinatura_e_verificacao_anteriores(self) -> None:
        """Fase 7: o APK mudou — APK_ASSINADO/APK_VERIFICADO caem e a
        customização fica marcada."""
        apk = apk_sintetico(self.studio.parent / "alvo-loading.apk",
                            metadata=metadata_sintetico())
        projeto, _ = new_project("visuais", studio_root=self.studio, input_apk=apk)
        for etapa in Stage:
            projeto.state.mark(etapa)
        self.app._abrir_projeto_memoria(projeto)
        self.app.refresh()

        relatorio = {
            "apk_out": str(self.studio / "visuais" / "output" / "revival.apk"),
            "bundle_report": {"targets": [{"name": "loading_background"}]},
            "report_path": str(self.studio / "visuais" / "reports" / "loading-inject.json"),
        }
        with (
            mock.patch("revival_editor.ui.visuals_tab.messagebox") as caixa,
            mock.patch(
                "revival_editor.ui.visuals_tab._trabalho_injetar", return_value=relatorio
            ) as trabalho,
        ):
            caixa.askyesno.return_value = True
            aba = self.app.visuals_tab
            aba.var_mode.set("Só Texto")
            aba.render()
            self.assertIsNotNone(aba.preview)
            aba.injetar()
            ok = _bombeiar(
                self.root,
                lambda: self.app.project is not None
                and self.app.project.state.has(Stage.CUSTOMIZACOES_APLICADAS)
                and not self.app.project.state.has(Stage.APK_VERIFICADO),
            )
            self.assertTrue(ok, self.app.var_status.get())

        trabalho.assert_called_once()
        self.assertFalse(self.app.project.state.has(Stage.APK_ASSINADO))
        self.assertFalse(self.app.project.state.has(Stage.APK_RECONSTRUIDO))
        self.assertEqual(self.app.project.output_apk, relatorio["apk_out"])
        self.assertIn("loading_inject", self.app.project.reports)
        self.assertIn("etapas invalidadas", self.app.log.content)

    # -- Branding Android (fase 8) --------------------------------------------

    def test_aba_branding_existe_e_acao_abre(self) -> None:
        abas = [self.app.notebook.tab(widget, "text") for widget in self.app.notebook.tabs()]
        self.assertIn("Branding", abas)
        self.app.act_branding_android()
        self.assertEqual(self.app.notebook.select(), str(self.app.branding_tab))

    def test_branding_sem_arvore_decoded_mostra_erro(self) -> None:
        projeto, _ = new_project("sem-decode", studio_root=self.studio)
        self.app._abrir_projeto_memoria(projeto)
        with mock.patch("revival_editor.ui.branding_tab.messagebox") as caixa:
            self.app.branding_tab.ler_arvore()
        caixa.showerror.assert_called_once()
        self.assertIsNone(self.app.branding_tab.decoded)

    def test_branding_aplica_diff_e_invalida_build(self) -> None:
        """Fase 8: planejar mostra diff, aplicar muda o recurso (não o manifest),
        invalida build/assinatura e grava relatório no projeto."""
        from test_branding import arvore_decodificada

        from revival_editor.paths import project_dir

        projeto, _ = new_project("branding1", studio_root=self.studio)
        for etapa in Stage:
            projeto.state.mark(etapa)
        self.app._abrir_projeto_memoria(projeto)
        self.app.refresh()

        decoded = arvore_decodificada(project_dir("branding1", studio_root=self.studio) / "decoded")
        bytes_manifesto = (decoded / "AndroidManifest.xml").read_bytes()
        aba = self.app.branding_tab
        aba.ler_arvore()
        self.assertIsNotNone(aba.manifest_antes)
        self.assertIn("com.bethsoft.ubu", aba.lbl_info.cget("text"))

        aba.var_label.set("DOOM Revival")
        aba.planejar_label()
        self.assertIsNotNone(aba.plano)
        self.assertIn("+<string name=\"app_name\">DOOM Revival</string>", aba.txt_diff.get("1.0", "end"))
        self.assertEqual(str(aba.btn_aplicar.instate(["disabled"])), "False")

        with mock.patch("revival_editor.ui.branding_tab.messagebox") as caixa:
            caixa.askyesno.return_value = True
            aba.aplicar()
            ok = _bombeiar(
                self.root,
                lambda: self.app.project is not None
                and self.app.project.state.has(Stage.CUSTOMIZACOES_APLICADAS)
                and not self.app.project.state.has(Stage.APK_RECONSTRUIDO),
            )
            self.assertTrue(ok, self.app.var_status.get())
        caixa.askyesno.assert_called_once()

        # recurso mudou de verdade; manifest intocado
        self.assertIn(
            "DOOM Revival",
            (decoded / "res" / "values" / "strings.xml").read_text(encoding="utf-8"),
        )
        self.assertEqual((decoded / "AndroidManifest.xml").read_bytes(), bytes_manifesto)
        # etapas invalidadas + relatório no projeto
        self.assertIn("etapas invalidadas", self.app.log.content)
        relatorio = Path(self.app.project.reports["branding"])
        self.assertTrue(relatorio.is_file(), relatorio)
        dados = json.loads(relatorio.read_text(encoding="utf-8"))
        self.assertTrue(dados["verified_untouched"])
        self.assertEqual(len(dados["result"]["labels_alterados"]), 2)
        # o plano consumido sai da tela
        self.assertIsNone(aba.plano)

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
