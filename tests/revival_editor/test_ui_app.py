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

import gc
import json
import sys
import tempfile
import time
import unittest
import zipfile
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


def _encerrar_interfase(app, root) -> None:
    """Destrói janela+app e coleta o lixo cíclico de Tk NA thread da UI.

    O JobRunner roda jobs em workers. Se o GC cíclico disparar numa worker
    (pela alocação do próprio DoneEvent, por exemplo) e herdar widgets/
    Variables de um interp já destruído, a chamada Tcl roda na thread errada:
    a worker trava sem entregar o DoneEvent (job fica para sempre "pronto") ou
    o processo aborta com "Tcl_AsyncDelete: async handler deleted by the wrong
    thread". Coletar aqui, na thread que criou o interp, fecha essa corrida.
    """
    try:
        app._fechar()
    except tk.TclError:
        pass  # já destruída por teste de fechamento
    try:
        root.destroy()
    except tk.TclError:
        pass
    gc.collect()


def _bombeiar(root, condicao, timeout=20.0) -> bool:
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
        _encerrar_interfase(self.app, self.root)
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

    def test_preparar_ferramentas_usa_servico_toolchain(self) -> None:
        """O botão chama `toolchain.prepare_tools` — fonte única dos pins."""
        from revival_editor.toolchain import APKTOOL_SHA256, APKTOOL_URL, SIGNER_SHA256, SIGNER_URL

        # pins obrigatórios no módulo (nenhum outro lugar define download)
        self.assertTrue(APKTOOL_URL.startswith("https://"))
        self.assertEqual(len(APKTOOL_SHA256), 64)
        self.assertTrue(SIGNER_URL.startswith("https://"))
        self.assertEqual(len(SIGNER_SHA256), 64)

        from revival_editor.toolchain import ToolStatus, ToolchainReport

        relatorio = ToolchainReport(tools=[ToolStatus(name="java", ok=True, version="17", detail="ok")])
        with (
            mock.patch("revival_editor.ui.app.prepare_tools", return_value=relatorio) as preparar,
            mock.patch("revival_editor.ui.app.messagebox") as caixa,
            mock.patch("revival_editor.ui.app._trabalho_ferramentas_status", return_value=relatorio),
        ):
            caixa.askyesno.return_value = True
            self.app.act_preparar_ferramentas()
            # 1º job: preparo pelo serviço; ao concluir, encadeia a verificação
            ok = _bombeiar(self.root, lambda: caixa.showinfo.called)
            self.assertTrue(ok, self.app.var_status.get())

        preparar.assert_called_once()
        caixa.askyesno.assert_called_once()
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

    # -- Catálogo de assets (fase 9) -------------------------------------------

    def test_aba_assets_existe_e_acao_abre(self) -> None:
        abas = [self.app.notebook.tab(widget, "text") for widget in self.app.notebook.tabs()]
        self.assertIn("Assets", abas)
        self.app.act_assets_catalog()
        self.assertEqual(self.app.notebook.select(), str(self.app.assets_tab))

    def test_assets_sem_projeto_mostra_aviso(self) -> None:
        with mock.patch("revival_editor.ui.assets_tab.messagebox") as caixa:
            self.app.assets_tab.listar_bundles()
        caixa.showwarning.assert_called_once()
        self.assertFalse(self.app.assets_tab.membros)
        self.assertTrue(self.app.assets_tab.btn_scan.instate(["disabled"]))

    def test_assets_scan_popula_arvore_e_salva_relatorio(self) -> None:
        """Fase 9: listar bundles do APK do projeto, escanear (domínio mockado),
        árvore povoada, seletor visível e relatório no projeto."""
        from revival_editor import assets_catalog as ac

        apk = self.studio / "fake-apk.apk"
        apk.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(apk, "w") as z:
            z.writestr("assets/aa/Android/fake.bundle", b"bundle")
            z.writestr("assets/aa/catalog.json", b"{}")
        projeto, _ = new_project("assets1", studio_root=self.studio, input_apk=apk)
        self.app._abrir_projeto_memoria(projeto)
        self.app.refresh()

        aba = self.app.assets_tab
        aba.listar_bundles()
        self.assertEqual(len(aba.membros), 1)
        self.assertEqual(aba.combo_membro.current(), 0)

        resultado = ac.ScanResult(
            apk=str(apk), apk_sha256="ab" * 32,
            member="assets/aa/Android/fake.bundle", bundle_sha256="cd" * 32,
            object_count=2,
            entries=[
                ac.AssetEntry("assets/aa/Android/fake.bundle", 1, "Texture2D",
                              "loading_background", width=2048, height=2048,
                              obj_sha256="0" * 64, category=ac.EDITAVEL_VALIDADO),
                ac.AssetEntry("assets/aa/Android/fake.bundle", 2, "AudioClip",
                              "bgm_menu", duration=12.5,
                              obj_sha256="1" * 64, category=ac.SOMENTE_LEITURA),
            ],
        )
        with mock.patch("revival_editor.ui.assets_tab.messagebox") as caixa, \
                mock.patch("revival_editor.ui.assets_tab.ac.scan_bundle",
                           return_value=resultado):
            caixa.askyesno.return_value = True
            aba.escanear()
            ok = _bombeiar(
                self.root, lambda: len(aba.tree.get_children()) == 2
            )
            self.assertTrue(ok, self.app.var_status.get())
        caixa.askyesno.assert_called_once()

        linhas = [aba.tree.item(i, "values") for i in aba.tree.get_children()]
        self.assertEqual(linhas[0][1], "Texture2D")
        self.assertEqual(linhas[0][2], "loading_background")
        self.assertEqual(linhas[0][4], ac.EDITAVEL_VALIDADO)
        self.assertEqual(linhas[1][3], "12.5s")

        # seleção mostra o seletor estável §16.2
        aba.tree.selection_set(aba.tree.get_children()[0])
        self.root.update()
        self.assertIn("seletor estável", aba.lbl_info.cget("text"))
        self.assertIn("loading_background", aba.lbl_info.cget("text"))

        # relatório no projeto e no disco, sem conteúdo de asset
        relatorio = Path(self.app.project.reports["assets_catalog"])
        self.assertTrue(relatorio.is_file(), relatorio)
        dados = json.loads(relatorio.read_text(encoding="utf-8"))
        self.assertEqual(dados["object_count"], 2)
        self.assertNotIn("image", json.dumps(dados))
        self.assertIn("[assets] scan concluído", self.app.log.content)

        # filtro por texto afunila a árvore
        aba.var_busca.set("bgm")
        aba.filtrar()
        self.assertEqual(len(aba.tree.get_children()), 1)

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


def _registro_fake() -> dict:
    """Registro sintético de 2 rotas (identificadores Synthetic*)."""
    return {
        "_meta": {"route_count": 2},
        "endpoints": {
            "game/synthetic/complete": {
                "module": "synthetic", "implemented": True, "schema_extracted": True,
                "request_observed": True, "response_observed": True,
                "client_validated": True, "persistence_validated": True,
                "regression_test": True, "fixture": None, "fixture_provenance": None,
                "uses_fallback": False, "evidence": "sintético completo",
            },
            "game/synthetic/pendente": {
                "module": "synthetic", "implemented": True, "schema_extracted": False,
                "request_observed": False, "response_observed": False,
                "client_validated": False, "persistence_validated": None,
                "regression_test": False, "fixture": None, "fixture_provenance": None,
                "uses_fallback": False, "evidence": "",
            },
        },
        "server_only_routes": [],
    }


@unittest.skipUnless(tk, "sem Tkinter nesta máquina")
class TestCompatTab(unittest.TestCase):
    """Aba Compatibilidade (fase 16): leitura pura + mutação só via script."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.studio = Path(self._tmp.name) / "studio"
        self.root = tk.Tk()
        self.root.withdraw()
        from revival_editor.ui.app import StudioApp

        with mock.patch("revival_editor.ui.app.messagebox"), \
                mock.patch("revival_editor.ui.compat_tab.load_registry",
                           return_value=_registro_fake()):
            self.app = StudioApp(self.root, studio_root=self.studio)
        self.tab = self.app.compat_tab

    def tearDown(self) -> None:
        _encerrar_interfase(self.app, self.root)
        self._tmp.cleanup()

    def test_aba_existe_e_handler_seleciona(self) -> None:
        abas = [self.app.notebook.tab(w, "text") for w in self.app.notebook.tabs()]
        self.assertIn("Compatibilidade", abas)
        self.app.act_compat_registro()
        self.assertEqual(self.app.notebook.select(), str(self.tab))

    def test_resumo_e_arvore_do_registro(self) -> None:
        resumo = self.tab.var_resumo.get()
        self.assertIn("Rotas: 2", resumo)
        self.assertIn("DoD completo: 1", resumo)
        self.assertIn("fallbacks: 0", resumo)
        self.assertIn("persistência: 1 ok / 0 pendente / 1 n/a", resumo)
        ids = list(self.tab.tree.get_children())
        self.assertEqual(len(ids), 2)
        valores = self.tab.tree.item("game/synthetic/pendente", "values")
        self.assertEqual(valores[2], "schema_extracted")
        self.assertEqual(self.tab.tree.item("game/synthetic/complete", "values")[2],
                         "DoD completo")

    def test_selecao_mostra_detalhe(self) -> None:
        self.tab.tree.selection_set("game/synthetic/pendente")
        self.root.update()
        detalhe = self.tab.txt_detalhe.get("1.0", "end")
        self.assertIn("game/synthetic/pendente", detalhe)
        self.assertIn("schema_extracted", detalhe)

    def test_nenhuma_checkbox_manual(self) -> None:
        for widget in self.tab.winfo_children():
            self.assertNotIsInstance(widget, tk.Checkbutton)

    def test_proxima_tarefa_via_job(self) -> None:
        payload = {
            "status": "task",
            "task": {
                "module": "synthetic", "module_priority": 7,
                "endpoint": "game/synthetic/pendente", "gate": "request_observed",
                "action": "observar com client_harness", "evidence": "sintético",
                "module_pending": [{"endpoint": "game/synthetic/pendente",
                                    "gate": "request_observed"}],
                "module_total": 2,
            },
        }
        with mock.patch("revival_editor.ui.compat_tab.run_next_task",
                        return_value=payload) as run:
            self.tab.atualizar_proxima()
            ok = _bombeiar(self.root, lambda: "game/synthetic/pendente"
                           in self.tab.var_proxima.get())
        self.assertTrue(ok, self.tab.var_proxima.get())
        run.assert_called_once()
        self.assertIn("request_observed", self.tab.var_proxima.get())

    def test_aplicar_evidencia_passa_pelo_script_oficial(self) -> None:
        self.tab.tree.selection_set("game/synthetic/pendente")
        self.root.update()
        self.tab.var_campo.set("persistence_validated")
        self.tab._sync_valores()
        self.tab.var_valor.set("true")
        conteudo_antes = (self.app.repo_root / "compatibility.json").read_text(
            encoding="utf-8"
        ) if (self.app.repo_root / "compatibility.json").is_file() else ""
        with mock.patch("revival_editor.ui.compat_tab.apply_evidence",
                        return_value={"diff": "--- antes\n+++ depois\n+ persistence",
                                      "changed": True}) as aplica, \
                mock.patch("revival_editor.ui.compat_tab.messagebox") as caixa:
            caixa.askyesno.return_value = True
            self.tab.aplicar_evidencia()
            ok = _bombeiar(self.root, lambda: "generate_endpoint_matrix.py"
                           in self.tab.txt_detalhe.get("1.0", "end"))
        self.assertTrue(ok, self.tab.txt_detalhe.get("1.0", "end"))
        aplica.assert_called_once()
        args = aplica.call_args[0]
        self.assertEqual(args[1], "game/synthetic/pendente")
        self.assertEqual(args[2], "persistence_validated")
        self.assertEqual(args[3], "true")
        # a aba em si não escreveu no registro (só o script oficial escreve;
        # aqui ele foi mockado — logo o arquivo real está intocado)
        if conteudo_antes:
            self.assertEqual(
                (self.app.repo_root / "compatibility.json").read_text(encoding="utf-8"),
                conteudo_antes,
            )
        self.assertIn("persistence", self.tab.txt_detalhe.get("1.0", "end"))

    def test_consultar_research_avisa_modo_final(self) -> None:
        self.tab.var_url.set("https://synthetic.local")
        com_research = {
            "research_mode": True, "fallback_total": 2,
            "fallback_endpoints": [{"path": "game/x", "count": 2}],
        }
        with mock.patch("revival_editor.ui.compat_tab.fetch_research",
                        return_value=com_research):
            self.tab.consultar_research()
            ok = _bombeiar(self.root, lambda: "research_mode" in
                           self.tab.lbl_research.cget("text"))
        self.assertTrue(ok, self.tab.lbl_research.cget("text"))
        self.assertIn("RESEARCH_MODE=false", self.app.log.content)
        self.assertIn("zero", self.app.log.content)

    def test_consultar_research_sem_avisos(self) -> None:
        self.tab.var_url.set("https://synthetic.local")
        with mock.patch("revival_editor.ui.compat_tab.fetch_research",
                        return_value={"research_mode": False, "fallback_total": 0,
                                      "fallback_endpoints": []}):
            self.tab.consultar_research()
            ok = _bombeiar(self.root, lambda: "fallback_total=0" in
                           self.tab.lbl_research.cget("text"))
        self.assertTrue(ok, self.tab.lbl_research.cget("text"))
        self.assertIn("sem research e sem fallbacks", self.app.log.content)


class _CtxFake:
    """JobContext de mentira: captura argv e simula o script oficial."""

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self.argv: list[str] | None = None

    def run_process(self, argv, **_kw) -> int:  # noqa: ANN001, ANN003
        self.argv = [str(a) for a in argv]
        item = next(a for a in self.argv if a.startswith("game/"))
        rota, _, resto = item.partition("=")
        campo, _, valor = resto.partition("=")
        caminho = self.repo / "compatibility.json"
        reg = json.loads(caminho.read_text(encoding="utf-8"))
        reg["endpoints"][rota][campo] = None if valor == "null" else valor == "true"
        caminho.write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")
        return 0


class TestCompatLogica(unittest.TestCase):
    """Funções da aba sem Tk: resumo, próxima tarefa e evidência auditável."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        (self.repo / "scripts").mkdir(parents=True)
        (self.repo / "scripts" / "generate_endpoint_matrix.py").write_text(
            "# placeholder — o teste injeta o comportamento via _CtxFake\n",
            encoding="utf-8",
        )
        (self.repo / "compatibility.json").write_text(
            json.dumps(_registro_fake(), indent=2) + "\n", encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_first_open_gate_pula_none(self) -> None:
        from revival_editor.ui.compat_tab import first_open_gate

        ep = _registro_fake()["endpoints"]["game/synthetic/pendente"]
        self.assertEqual(first_open_gate(ep), "schema_extracted")
        ep["schema_extracted"] = True
        ep["implemented"] = True
        ep["request_observed"] = True
        ep["response_observed"] = True
        ep["client_validated"] = True
        ep["regression_test"] = True
        # persistence_validated=None não é gate — DoD completa mesmo assim
        self.assertIsNone(first_open_gate(ep))
        ep["uses_fallback"] = True
        self.assertEqual(first_open_gate(ep), "uses_fallback")

    def test_render_proxima_sem_tarefa(self) -> None:
        from revival_editor.ui.compat_tab import render_proxima

        texto = render_proxima({"status": "done", "task": None})
        self.assertIn("nenhuma tarefa", texto)

    def test_apply_evidence_diff_auditavel(self) -> None:
        from revival_editor.ui.compat_tab import apply_evidence

        ctx = _CtxFake(self.repo)
        resultado = apply_evidence(self.repo, "game/synthetic/pendente",
                                   "persistence_validated", "true", ctx)
        self.assertTrue(resultado["changed"])
        self.assertIn("persistence_validated", resultado["diff"])
        self.assertIn("--set", ctx.argv)
        self.assertTrue(ctx.argv[1].endswith("generate_endpoint_matrix.py"))
        # o registro foi mutado pelo "script oficial" (simulado), não pela aba
        reg = json.loads((self.repo / "compatibility.json").read_text(encoding="utf-8"))
        self.assertIs(reg["endpoints"]["game/synthetic/pendente"]["persistence_validated"], True)

    def test_apply_evidence_rejeita_null_fora_persistence(self) -> None:
        from revival_editor.ui.compat_tab import CompatError, apply_evidence

        ctx = _CtxFake(self.repo)
        with self.assertRaises(CompatError):
            apply_evidence(self.repo, "game/synthetic/pendente",
                           "schema_extracted", "null", ctx)

    def test_apply_evidence_rejeita_campo_livre(self) -> None:
        from revival_editor.ui.compat_tab import CompatError, apply_evidence

        with self.assertRaises(CompatError):
            apply_evidence(self.repo, "game/synthetic/pendente",
                           "implemented", "true", _CtxFake(self.repo))


class TestServidorLocal(unittest.TestCase):
    """Menu Servidor local (§6.1/§9.2): preparar/iniciar/encerrar/status."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.studio = Path(self._tmp.name) / "studio"
        self.root = tk.Tk()
        self.root.withdraw()
        from revival_editor.ui.app import StudioApp

        with mock.patch("revival_editor.ui.app.messagebox"):
            self.app = StudioApp(self.root, studio_root=self.studio)

    def tearDown(self) -> None:
        _encerrar_interfase(self.app, self.root)
        self._tmp.cleanup()

    def _estado_entrada(self, action_id: str) -> str:
        menu, indice = self.app._entradas[action_id]
        return str(menu.entrycget(indice, "state"))

    def test_acoes_registradas_sem_projeto(self) -> None:
        """Servidor local é nível repositório: nenhum item exige projeto."""
        for action_id in ("servidor.preparar", "servidor.iniciar",
                          "servidor.parar", "servidor.status"):
            spec = action_by_id(action_id)
            self.assertFalse(spec.needs_project)
            self.assertEqual(self._estado_entrada(action_id), "normal")

    def test_preparar_servidor_passa_pelo_servico(self) -> None:
        from revival_editor.server import ServerReport

        relatorio = ServerReport(ok=True, node_version="v24.0.0",
                                 copied=[".env", "config/revival.json"])
        with (
            mock.patch("revival_editor.ui.app.prepare_server",
                       return_value=relatorio) as preparar,
            mock.patch("revival_editor.ui.app.messagebox") as caixa,
        ):
            self.app.act_preparar_servidor_local()
            ok = _bombeiar(self.root, lambda: caixa.showinfo.called)
            self.assertTrue(ok, self.app.var_status.get())

        preparar.assert_called_once()
        _args = preparar.call_args.args
        self.assertEqual(len(_args), 2, "assinatura esperada: (repo_root, ctx)")
        self.assertTrue((Path(_args[0]) / "server").is_dir(),
                        f"repo_root inválido: {_args[0]}")
        _titulo, texto = caixa.showinfo.call_args[0]
        self.assertIn("v24.0.0", texto)
        self.assertIn("config/revival.json", texto)
        self.assertIn("REVIVAL_ADMIN_TOKEN", texto, "lembrete de revisar o .env local")

    def test_preparar_falhando_mostra_erro(self) -> None:
        from revival_editor.server import ServerReport

        relatorio = ServerReport(ok=False, erro="Node.js não encontrado no PATH.")
        with (
            mock.patch("revival_editor.ui.app.prepare_server", return_value=relatorio),
            mock.patch("revival_editor.ui.app.messagebox") as caixa,
        ):
            self.app.act_preparar_servidor_local()
            ok = _bombeiar(self.root, lambda: caixa.showerror.called)
            self.assertTrue(ok, self.app.var_status.get())

        _titulo, texto = caixa.showerror.call_args[0]
        self.assertIn("Node.js", texto)
        self.assertIn("FALHOU", self.app.log.content)

    def test_iniciar_mostra_pid_porta_e_game_data(self) -> None:
        from revival_editor.server import ServerReport

        relatorio = ServerReport(
            ok=True, pid=4242, port=8080,
            health={"ok": True, "game_data_loaded": True, "research_mode": True},
            log_path="work/revival-studio/server/local-server.log",
        )
        with (
            mock.patch("revival_editor.ui.app.start_server", return_value=relatorio),
            mock.patch("revival_editor.ui.app.messagebox") as caixa,
        ):
            self.app.act_iniciar_servidor_local()
            ok = _bombeiar(self.root, lambda: caixa.showinfo.called)
            self.assertTrue(ok, self.app.var_status.get())

        _titulo, texto = caixa.showinfo.call_args[0]
        self.assertIn("127.0.0.1:8080", texto)
        self.assertIn("4242", texto)
        self.assertIn("game_data_loaded: True", texto)
        self.assertIn("Encerrar servidor local", texto, "usuário precisa saber como parar")

    def test_iniciar_ja_em_execucao_nao_mata_nada(self) -> None:
        from revival_editor.server import ServerReport

        relatorio = ServerReport(ok=True, ja_em_execucao=True, port=8080,
                                 health={"ok": True})
        with (
            mock.patch("revival_editor.ui.app.start_server", return_value=relatorio),
            mock.patch("revival_editor.ui.app.messagebox") as caixa,
        ):
            self.app.act_iniciar_servidor_local()
            ok = _bombeiar(self.root, lambda: caixa.showinfo.called)
            self.assertTrue(ok, self.app.var_status.get())

        self.assertIn("já estava em execução", self.app.log.content)
        self.assertIn("ativo", self.app.var_status.get())

    def test_encerrar_exige_confirmacao(self) -> None:
        with mock.patch("revival_editor.ui.app.messagebox") as caixa:
            caixa.askyesno.return_value = False
            self.app.act_parar_servidor_local()
        self.assertFalse(self.app.runner.is_running)
        caixa.askyesno.assert_called_once()

    def test_status_servidor_parado_e_ativo(self) -> None:
        parado = {"porta": 8080, "pid": None, "pid_vivo": False,
                  "health": None, "log_path": "…/local-server.log"}
        with (
            mock.patch("revival_editor.ui.app.server_status", return_value=parado),
            mock.patch("revival_editor.ui.app.messagebox") as caixa,
        ):
            self.app.act_status_servidor_local()
            ok = _bombeiar(self.root, lambda: caixa.showinfo.called)
            self.assertTrue(ok, self.app.var_status.get())
        self.assertIn("não está em execução", caixa.showinfo.call_args[0][1])

        ativo = {"porta": 8080, "pid": 4242, "pid_vivo": True,
                 "health": {"ok": True, "game_data_loaded": True,
                            "packs": 8, "events": 0, "players": 2,
                            "research_mode": True},
                 "log_path": "…/local-server.log"}
        with (
            mock.patch("revival_editor.ui.app.server_status", return_value=ativo),
            mock.patch("revival_editor.ui.app.messagebox") as caixa,
        ):
            self.app.act_status_servidor_local()
            ok = _bombeiar(self.root, lambda: caixa.showinfo.called)
            self.assertTrue(ok, self.app.var_status.get())
        _titulo, texto = caixa.showinfo.call_args[0]
        self.assertIn("game_data_loaded: True", texto)
        self.assertIn("vivo", texto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
