"""Janela principal do Revival Studio (§30 item 6: janela mínima com menus).

Único lugar do editor que importa Tkinter junto de lógica de aplicação. As
regras que este módulo obedece (fase 2 do plano):

- a worker thread nunca toca widget — todo resultado chega pela fila do
  `JobRunner` e é aplicado no bombeamento `after()`;
- um job mutável por vez; novo `submit` durante job vivo é recusado;
- fechar a janela com job vivo pede confirmação, cancela e **só então**
  destrói — saída válida anterior nunca é substituída (`promote_atomic`);
- item de menu desabilitado quando o pré-requisito de estado não existe
  (§9.1: "Assinar" não aparece antes de "Rebuild");
- mudança de host/CA/APK invalida os estados de build (§6.2).

Os menus são construídos a partir do registro em `revival_editor.actions` —
nada de handler solto que o registro não conheça (é o que o teste de wrappers
da §9.2 valida).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Callable

from .. import __version__
from ..actions import ACTIONS, ActionSpec, MENUS
from ..models import (
    STAGE_ORDER,
    Failure,
    ProjectState,
    Stage,
    StageProgress,
)
from ..paths import REPO_ROOT, STUDIO_ROOT, project_dir
from ..toolchain import ToolchainReport, prepare_tools
from ..project import (
    Project,
    ProjectError,
    list_projects,
    load_project,
    new_project,
    save_project,
)
from ..runner import (
    DoneEvent,
    JobRunner,
    JobState,
    LogEvent,
    ProgressEvent,
)
from ..server import prepare_server, server_status, start_server, stop_server
from ..services import analyze_apk, check_hostname_budget, server_preflight
from .theme import aplicar_tema

__all__ = ["StudioApp", "main"]

POLL_MS = 100


class StudioApp:
    """Controla a janela; toda ação de peso roda no `JobRunner`."""

    def __init__(
        self,
        root: tk.Tk,
        *,
        studio_root: Path | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self.root = root
        self.repo_root = Path(repo_root) if repo_root else REPO_ROOT
        self.studio_root = Path(studio_root) if studio_root else STUDIO_ROOT

        self.project: Project | None = None
        self.runner = JobRunner(log_dir=self.studio_root / "logs")
        self._pendentes: dict[int, Callable[[DoneEvent], None]] = {}
        self._fechando = False

        # Um handler digitado errado no registro derruba o app aqui, no boot —
        # não no meio da sessão do usuário.
        for spec in ACTIONS:
            if not callable(getattr(self, spec.handler, None)):
                raise AttributeError(
                    f"ação {spec.action_id} aponta para handler inexistente "
                    f"StudioApp.{spec.handler}"
                )

        root.title(f"Revival Studio {__version__} — mighty-doom-revival")
        root.protocol("WM_DELETE_WINDOW", self._ao_fechar)

        # Paleta DOOM do site (slayer.css) antes de qualquer widget nascer.
        aplicar_tema(root)

        self._construir_menus()
        self._construir_corpo()
        self.refresh()
        self.root.after(POLL_MS, self._bombear)

    # ==================================================================
    # construção da janela
    # ==================================================================

    def _construir_menus(self) -> None:
        menubar = tk.Menu(self.root)
        self._menus: dict[str, tk.Menu] = {}
        self._entradas: dict[str, tuple[tk.Menu, int]] = {}
        for nome in MENUS:
            menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label=nome, menu=menu)
            self._menus[nome] = menu
        for spec in ACTIONS:
            menu = self._menus[spec.menu]
            menu.add_command(label=spec.label, command=self._despachar(spec))
            self._entradas[spec.action_id] = (menu, menu.index("end"))
        self.root.config(menu=menubar)

    def _construir_corpo(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        # ---- notebook: aba Projeto (formulário/checks/etapas) + aba Visuais ----
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 0))
        pagina_projeto = ttk.Frame(self.notebook, padding=0)
        self.notebook.add(pagina_projeto, text="Projeto")
        pagina_projeto.columnconfigure(0, weight=1)

        from .assets_tab import AssetsTab
        from .branding_tab import BrandingTab
        from .compat_tab import CompatTab
        from .visuals_tab import VisualsTab

        self.visuals_tab = VisualsTab(self.notebook, self)
        self.notebook.add(self.visuals_tab, text="Visuais")
        self.branding_tab = BrandingTab(self.notebook, self)
        self.notebook.add(self.branding_tab, text="Branding")
        self.assets_tab = AssetsTab(self.notebook, self)
        self.notebook.add(self.assets_tab, text="Assets")
        self.compat_tab = CompatTab(self.notebook, self)
        self.notebook.add(self.compat_tab, text="Compatibilidade")

        # ---- formulário do projeto ----
        form = ttk.LabelFrame(pagina_projeto, text="Projeto")
        form.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        self.lbl_projeto = ttk.Label(form, text="—")
        self.lbl_projeto.grid(row=0, column=0, columnspan=4, sticky="w", padx=6, pady=(4, 2))

        ttk.Label(form, text="APK de entrada:").grid(row=1, column=0, sticky="w", padx=6, pady=2)
        self.var_apk = tk.StringVar()
        self.ent_apk = ttk.Entry(form, textvariable=self.var_apk)
        self.ent_apk.grid(row=1, column=1, columnspan=2, sticky="ew", padx=4)
        self.btn_apk = ttk.Button(form, text="Procurar…", command=self._escolher_apk)
        self.btn_apk.grid(row=1, column=3, sticky="e", padx=(0, 6))

        ttk.Label(form, text="Hostname do servidor:").grid(row=2, column=0, sticky="w", padx=6, pady=2)
        self.var_host = tk.StringVar()
        self.ent_host = ttk.Entry(form, textvariable=self.var_host)
        self.ent_host.grid(row=2, column=1, sticky="ew", padx=4)
        self.ent_host.bind("<FocusOut>", lambda _e: self._aplicar_host())
        self.ent_host.bind("<Return>", lambda _e: self._aplicar_host())

        ttk.Label(form, text="CA (opcional):").grid(row=3, column=0, sticky="w", padx=6, pady=2)
        self.var_ca = tk.StringVar()
        self.ent_ca = ttk.Entry(form, textvariable=self.var_ca)
        self.ent_ca.grid(row=3, column=1, columnspan=2, sticky="ew", padx=4)
        self.btn_ca = ttk.Button(form, text="Procurar…", command=self._escolher_ca)
        self.btn_ca.grid(row=3, column=3, sticky="e", padx=(0, 6))

        ttk.Label(form, text="Estratégia de patch:").grid(row=4, column=0, sticky="w", padx=6, pady=(2, 6))
        self.var_estrategia = tk.StringVar(value="auto")
        self.cmb_estrategia = ttk.Combobox(
            form, textvariable=self.var_estrategia, state="readonly",
            values=("auto", "fast-path", "bundle-aware"), width=16,
        )
        self.cmb_estrategia.grid(row=4, column=1, sticky="w", padx=4, pady=(2, 6))
        self.cmb_estrategia.bind("<<ComboboxSelected>>", lambda _e: self._aplicar_estrategia())

        # ---- checks do servidor (fase 5: DNS/TLS/health separados) ----
        servidor = ttk.LabelFrame(pagina_projeto, text="Servidor — checks do último preflight")
        servidor.grid(row=1, column=0, sticky="ew", pady=4)
        servidor.columnconfigure(1, weight=1)
        self._lbl_checks: dict[str, ttk.Label] = {}
        for linha, (chave, rotulo) in enumerate(
            (("dns", "DNS"), ("tls", "TLS"), ("health", "Health"), ("gear_prefix", "Prefixo Gear"))
        ):
            ttk.Label(servidor, text=rotulo, padding=(8, 1)).grid(row=linha, column=0, sticky="w")
            valor = ttk.Label(servidor, text="— não avaliado", padding=(0, 1))
            valor.grid(row=linha, column=1, sticky="w")
            self._lbl_checks[chave] = valor

        # ---- etapas ----
        etapas = ttk.LabelFrame(pagina_projeto, text="Etapas")
        etapas.grid(row=2, column=0, sticky="ew", pady=4)
        self._lbl_etapas: dict[Stage, ttk.Label] = {}
        for coluna, stage in enumerate(STAGE_ORDER):
            rotulo = ttk.Label(etapas, text=f"○ {stage.value}", padding=(8, 2))
            rotulo.grid(row=0, column=coluna, sticky="w")
            self._lbl_etapas[stage] = rotulo

        # ---- log ----
        from .log_panel import LogPanel

        self.log = LogPanel(self.root)
        self.log.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

        # ---- barra de job ----
        barra = ttk.Frame(self.root)
        barra.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        barra.columnconfigure(0, weight=1)
        self.var_status = tk.StringVar(value="pronto")
        self.lbl_status = ttk.Label(barra, textvariable=self.var_status, anchor="w")
        self.lbl_status.grid(row=0, column=0, sticky="ew")
        self.btn_cancelar = ttk.Button(
            barra, text="Cancelar job", command=self._cancelar_job, state="disabled"
        )
        self.btn_cancelar.grid(row=0, column=1, padx=(6, 0))
        self.progresso = ttk.Progressbar(barra, mode="determinate", maximum=100)
        self.progresso.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))

    # ==================================================================
    # estado / refresh
    # ==================================================================

    @property
    def state(self) -> ProjectState:
        """Estado do projeto aberto (VAZIO quando nenhum)."""
        return self.project.state if self.project else ProjectState()

    def refresh(self) -> None:
        """Reavalia menus, formulário e etapas. Chamar só na thread da UI."""
        tem_projeto = self.project is not None
        ocupado = self.runner.is_running

        self.lbl_projeto.configure(
            text=(
                f"Projeto: {self.project.project_id} — {self._caminho_projeto()}"
                if tem_projeto
                else "Nenhum projeto aberto — use o menu Projeto."
            )
        )
        if tem_projeto and self.project:
            if str(self.var_apk.get()) != (self.project.input_apk or ""):
                self.var_apk.set(self.project.input_apk or "")
            if str(self.var_host.get()) != (self.project.server_host or ""):
                self.var_host.set(self.project.server_host or "")
            if str(self.var_ca.get()) != (self.project.ca_path or ""):
                self.var_ca.set(self.project.ca_path or "")
            if str(self.var_estrategia.get()) != self.project.patch_strategy:
                self.var_estrategia.set(self.project.patch_strategy)

        for spec in ACTIONS:
            habilitado = tem_projeto or not spec.needs_project
            if ocupado and not spec.busy_safe:
                habilitado = False
            if habilitado and spec.requires is not None:
                habilitado = self.state.has(spec.requires)
            menu, indice = self._entradas[spec.action_id]
            menu.entryconfig(indice, state="normal" if habilitado else "disabled")

        for campo in (self.ent_apk, self.btn_apk, self.ent_host, self.ent_ca, self.btn_ca):
            campo.configure(state="normal" if tem_projeto and not ocupado else "disabled")
        self.cmb_estrategia.configure(
            state="readonly" if tem_projeto and not ocupado else "disabled"
        )

        concluidas = self.state.completed
        for stage, rotulo in self._lbl_etapas.items():
            rotulo.configure(text=("✓" if stage in concluidas else "○") + f" {stage.value}")

    def _caminho_projeto(self) -> str:
        if not self.project:
            return ""
        try:
            return str(project_dir(self.project.project_id, studio_root=self.studio_root))
        except Exception:  # noqa: BLE001 - exibição, não gate
            return self.project.project_id

    # ==================================================================
    # bombeamento da fila (único lugar que mexe em widget pós-boot)
    # ==================================================================

    def _bombear(self) -> None:
        if self._fechando:
            return
        # Reagendar ANTES de processar: se aplicar um evento levantar qualquer
        # exceção (TclError de janela morrendo incluída), a cadeia de drenagem
        # já está garantida para o próximo tick — sem isso, um único erro
        # mata o ciclo e a UI para de receber eventos do runner para sempre
        # (visto em prática: job conclui, status não muda, diálogo não abre).
        proximo = self.root.after(POLL_MS, self._bombear)
        try:
            for evento in self.runner.poll():
                self._aplicar(evento)
        except tk.TclError:
            try:
                self.root.after_cancel(proximo)  # janela já destruída
            except tk.TclError:
                pass  # interp já foi: o after morre com ele
            return

    def _aplicar(self, evento: Any) -> None:
        if isinstance(evento, LogEvent):
            self.log.append(evento.line, evento.stream)
        elif isinstance(evento, ProgressEvent):
            self._aplicar_progresso(evento.progress)
        elif isinstance(evento, DoneEvent):
            self._aplicar_conclusao(evento)

    def _aplicar_progresso(self, progresso: StageProgress) -> None:
        self.var_status.set(f"[{progresso.stage}] {progresso.message}")
        if progresso.fraction is None:
            if str(self.progresso.cget("mode")) != "indeterminate":
                self.progresso.configure(mode="indeterminate")
                self.progresso.start(20)
        else:
            if str(self.progresso.cget("mode")) != "determinate":
                self.progresso.stop()
                self.progresso.configure(mode="determinate")
            self.progresso.configure(value=progresso.fraction * 100)

    def _aplicar_conclusao(self, evento: DoneEvent) -> None:
        self.progresso.stop()
        self.progresso.configure(mode="determinate", value=100 if evento.state is JobState.CONCLUIDO else 0)
        rotulo = {
            JobState.CONCLUIDO: "concluído",
            JobState.FALHOU: "FALHOU",
            JobState.CANCELADO: "cancelado",
            JobState.TIMEOUT: "timeout",
        }[evento.state]
        self.var_status.set(f"{evento.name}: {rotulo} em {evento.duration_seconds:.1f}s")
        if evento.failure is not None:
            self._reportar_falha(evento.name, evento.failure)
        callback = self._pendentes.pop(evento.job_id, None)
        self.refresh()
        if callback is not None and evento.state is JobState.CONCLUIDO:
            callback(evento)

    def _reportar_falha(self, nome: str, falha: Failure) -> None:
        detalhe = falha.message
        if falha.exit_code is not None:
            detalhe += f" (exit {falha.exit_code})"
        if falha.report_path:
            detalhe += f"\nrelatório: {falha.report_path}"
        self.log.append(f"[FALHOU] {nome}: {falha.message}", "erro")
        messagebox.showerror(f"{nome} falhou", detalhe)

    # ==================================================================
    # submissão de jobs
    # ==================================================================

    def _submit(
        self,
        nome: str,
        trabalho: Callable[[Any], Any],
        *,
        ao_concluir: Callable[[DoneEvent], None] | None = None,
    ) -> None:
        handle = self.runner.submit(nome, trabalho)
        if ao_concluir is not None:
            self._pendentes[handle.job_id] = ao_concluir
        self.log.append(f"== {nome} iniciado (job {handle.job_id}) ==", "info")
        self.refresh()

    def _cancelar_job(self) -> None:
        if self.runner.cancel():
            self.var_status.set("cancelando…")

    def _exige_projeto(self) -> bool:
        if self.project is None:
            messagebox.showwarning("Sem projeto", "Abra ou crie um projeto primeiro (menu Projeto).")
            return False
        return True

    def _exige_livre(self) -> bool:
        if self.runner.is_running:
            atual = self.runner.current
            messagebox.showwarning(
                "Job em execução",
                f"aguarde/cancele o job {atual.name!r} antes de iniciar outro.",
            )
            return False
        return True

    def _reports_dir(self) -> Path:
        assert self.project is not None
        diretorio = project_dir(self.project.project_id, studio_root=self.studio_root)
        destino = diretorio / "reports"
        destino.mkdir(parents=True, exist_ok=True)
        return destino

    # ==================================================================
    # menus — Projeto
    # ==================================================================

    def ui_novo_projeto(self) -> None:
        if not self._exige_livre():
            return
        while True:
            identificador = simpledialog.askstring(
                "Novo projeto",
                "id do projeto (minúsculas, dígitos e hífen; ex.: doom-local):",
                parent=self.root,
            )
            if identificador is None:
                return
            identificador = identificador.strip().lower()
            try:
                projeto, destino = new_project(
                    identificador,
                    studio_root=self.studio_root,
                    input_apk=self.var_apk.get().strip() or None,
                )
                break
            except ProjectError as exc:
                messagebox.showerror("Novo projeto", str(exc))
                continue
        self._abrir_projeto_memoria(projeto)
        self.log.append(f"projeto criado: {destino}", "info")
        self.refresh()

    def ui_abrir_projeto(self) -> None:
        if not self._exige_livre():
            return
        ids = list_projects(studio_root=self.studio_root)
        if not ids:
            messagebox.showinfo(
                "Abrir projeto",
                f"nenhum projeto em {self.studio_root}.\nCrie um com Projeto → Novo projeto…",
            )
            return
        escolhido = self._dialogo_escolher(
            "Abrir projeto", "Projetos encontrados:", ids
        )
        if escolhido is None:
            return
        try:
            projeto, _ = load_project(escolhido, studio_root=self.studio_root)
        except ProjectError as exc:
            messagebox.showerror("Abrir projeto", str(exc))
            return
        self._abrir_projeto_memoria(projeto)
        self.log.append(
            f"projeto aberto: {projeto.project_id} — etapa atual {projeto.state.current.value}",
            "info",
        )
        self.refresh()

    def _abrir_projeto_memoria(self, projeto: Project) -> None:
        self.project = projeto
        logs = project_dir(projeto.project_id, studio_root=self.studio_root) / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        self.runner = JobRunner(log_dir=logs)
        self._limpar_checks_servidor()

    def _dialogo_escolher(self, titulo: str, texto: str, opcoes: list[str]) -> str | None:
        escolha: dict[str, str | None] = {"valor": None}

        dialogo = tk.Toplevel(self.root)
        dialogo.title(titulo)
        dialogo.transient(self.root)
        dialogo.grab_set()
        ttk.Label(dialogo, text=texto).pack(padx=12, pady=(10, 4))
        lista = tk.Listbox(dialogo, height=min(10, max(3, len(opcoes))), width=48)
        lista.pack(padx=12, fill="both", expand=True)
        for opcao in opcoes:
            lista.insert("end", opcao)

        def confirmar() -> None:
            selecao = lista.curselection()
            if selecao:
                escolha["valor"] = opcoes[selecao[0]]
            dialogo.destroy()

        botoes = ttk.Frame(dialogo)
        botoes.pack(pady=8)
        ttk.Button(botoes, text="Abrir", command=confirmar).pack(side="left", padx=4)
        ttk.Button(botoes, text="Cancelar", command=dialogo.destroy).pack(side="left", padx=4)
        dialogo.protocol("WM_DELETE_WINDOW", dialogo.destroy)
        self.root.wait_window(dialogo)
        return escolha["valor"]

    def ui_salvar_projeto(self) -> None:
        if not self._exige_projeto():
            return
        assert self.project is not None
        destino = save_project(self.project, studio_root=self.studio_root)
        self.log.append(f"projeto salvo: {destino}", "info")

    # -- formulário ------------------------------------------------------

    def _escolher_apk(self) -> None:
        if not self._exige_projeto():
            return
        from tkinter import filedialog

        caminho = filedialog.askopenfilename(
            parent=self.root,
            title="APK de entrada",
            filetypes=[("APK", "*.apk")],
        )
        if not caminho or self.project is None:
            return
        self.project.set_input_apk(caminho)
        save_project(self.project, studio_root=self.studio_root)
        self.log.append(f"APK de entrada: {caminho}", "info")
        self.refresh()

    def _escolher_ca(self) -> None:
        if not self._exige_projeto():
            return
        from tkinter import filedialog

        caminho = filedialog.askopenfilename(
            parent=self.root,
            title="Certificado da CA (PEM)",
            filetypes=[("PEM", "*.pem *.crt *.cer"), ("Todos", "*.*")],
        )
        if not caminho or self.project is None:
            return
        self.project.set_ca_path(caminho)
        save_project(self.project, studio_root=self.studio_root)
        self.log.append(f"CA: {caminho} (build invalidado — reforce rebuild quando chegar à fase 6)", "aviso")
        self.refresh()

    def _aplicar_host(self) -> None:
        if self.project is None or self.runner.is_running:
            return
        bruto = self.var_host.get().strip()
        if not bruto:
            return
        if bruto == (self.project.server_host or ""):
            return
        try:
            host = self.project.set_server(bruto)
        except Exception as exc:  # noqa: BLE001 - HostnameError tem texto acionável
            messagebox.showerror("Hostname inválido", str(exc))
            self.var_host.set(self.project.server_host or "")
            return
        save_project(self.project, studio_root=self.studio_root)
        self.log.append(
            f"servidor: {host} (estados de build invalidados — selo verde antigo não vale mais)",
            "aviso",
        )
        self._limpar_checks_servidor()
        self.refresh()

    # -- checks do servidor (fase 5) ----------------------------------------

    def _limpar_checks_servidor(self) -> None:
        """Zera o painel: os checks pertencem ao host que os mediu."""
        for rotulo in self._lbl_checks.values():
            rotulo.configure(text="— não avaliado")

    def _mostrar_checks_servidor(self, resultado: Any) -> None:
        """Desenha DNS/TLS/health/Gear como linhas separadas.

        Verde só onde mediu: check ausente continua "não avaliado" — a falha
        de DNS não deixa o painel inventar um TLS verde (fase 5).
        """
        for chave, rotulo in self._lbl_checks.items():
            check = (resultado.checks or {}).get(chave)
            if not isinstance(check, dict):
                continue
            marca = "✓" if check.get("ok") else "✗"
            rotulo.configure(text=f"{marca} {check.get('detail', '')}")

    def _aplicar_estrategia(self) -> None:
        if self.project is None:
            return
        try:
            self.project.set_patch_strategy(self.var_estrategia.get())
        except ProjectError as exc:
            messagebox.showerror("Estratégia", str(exc))
            return
        save_project(self.project, studio_root=self.studio_root)
        self.log.append(f"estratégia de patch: {self.project.patch_strategy}", "info")

    # ==================================================================
    # menus — Projeto/Analisar, APK, Servidor
    # ==================================================================

    def act_analisar_apk(self) -> None:
        if not (self._exige_projeto() and self._exige_livre()):
            return
        assert self.project is not None
        apk = self.project.input_apk
        if not apk:
            messagebox.showwarning("Analisar APK", "escolha o APK de entrada no formulário primeiro.")
            return
        destino = self._reports_dir() / "analyze.json"
        self._submit(
            "analisar-apk",
            lambda ctx: _trabalho_analisar(apk, destino, ctx),
            ao_concluir=self._apos_analisar,
        )

    def _apos_analisar(self, evento: DoneEvent) -> None:
        if self.project is None:
            return
        resultado = evento.result
        self.project.input_sha256 = resultado.sha256
        self.project.reports["analyze"] = str(self._reports_dir() / "analyze.json")
        self.project.state.mark(Stage.APK_ANALISADO)
        save_project(self.project, studio_root=self.studio_root)

        if resultado.divergences or resultado.unknown:
            linhas = ["APK analisado — MODO INSPEÇÃO (plano fase 4):"]
            if resultado.divergences:
                linhas.append("Divergências do alvo 1.13.1:\n  - " + "\n  - ".join(resultado.divergences))
            if resultado.unknown:
                linhas.append("A VERIFICAR (não medido):\n  - " + "\n  - ".join(resultado.unknown))
            linhas.append("Regras do 1.13.1 não são aplicadas por suposição.")
            messagebox.showwarning("Análise concluída", "\n".join(linhas))
        else:
            self.log.append(
                f"[OK] alvo confirmado: {resultado.package} {resultado.version_name} "
                f"build {resultado.version_code} · Unity {resultado.unity_version} · "
                f"metadata v{resultado.metadata_version}",
                "info",
            )
        self.refresh()

    def act_precheck_hostname(self) -> None:
        if not (self._exige_projeto() and self._exige_livre()):
            return
        assert self.project is not None
        if not self.project.server_host:
            messagebox.showwarning("Precheck", "informe o hostname do servidor no formulário primeiro.")
            return
        apk = self.project.input_apk or ""
        host = self.project.server_host
        destino = self._reports_dir() / "precheck-hostname.json"
        self._submit(
            "precheck-hostname",
            lambda ctx: _trabalho_precheck(apk, host, destino, ctx),
        )

    def act_resumo_hashes(self) -> None:
        if not self._exige_projeto():
            return
        assert self.project is not None
        caminho = Path(self.project.reports.get("analyze") or "")
        if not caminho.is_file():
            messagebox.showinfo("Resumo de hashes", "rode Projeto → Analisar APK primeiro.")
            return
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        linhas = [
            f"APK: {dados.get('path')}",
            f"SHA-256: {dados.get('sha256')}",
            f"tamanho: {dados.get('size_bytes'):,} bytes".replace(",", "."),
            f"package: {dados.get('package')}",
            f"versão: {dados.get('version_name')} (build {dados.get('version_code')})",
            f"Unity: {dados.get('unity_version')} · metadata v{dados.get('metadata_version')}",
            f"ABIs: {', '.join(dados.get('abis') or [])}",
            f"host oficial presente: {'sim' if dados.get('official_host_present') else 'não'}",
            f"relatório: {caminho}",
        ]
        messagebox.showinfo("Resumo de hashes", "\n".join(linhas))

    def act_importar_xapk(self) -> None:
        """Fase 4: `.xapk` é importação separada — nunca entra no fluxo principal."""
        if not (self._exige_projeto() and self._exige_livre()):
            return
        from tkinter import filedialog

        caminho = filedialog.askopenfilename(
            parent=self.root,
            title="XAPK (importação separada — extrai só o base APK)",
            filetypes=[("XAPK", "*.xapk")],
        )
        if not caminho or self.project is None:
            return
        diretorio = project_dir(self.project.project_id, studio_root=self.studio_root)
        self._submit(
            "importar-xapk",
            lambda ctx: _trabalho_xapk(caminho, diretorio / "input", ctx),
            ao_concluir=self._apos_importar_xapk,
        )

    def _apos_importar_xapk(self, evento: DoneEvent) -> None:
        if self.project is None:
            return
        resultado = evento.result  # (XapkInfo, Path do base extraído)
        info, base = resultado
        self.project.set_input_apk(str(base))
        save_project(self.project, studio_root=self.studio_root)
        self.log.append(
            f"[OK] base APK importado: {base} "
            f"(pacote {info.package_name} {info.version_name or '?'})",
            "info",
        )
        if info.has_splits:
            messagebox.showwarning(
                "XAPK com splits",
                "A VERIFICAR: este XAPK tem splits além do base APK:\n  - "
                + "\n  - ".join(info.splits)
                + "\n\nOs splits NÃO foram mesclados — o pipeline trabalha com o base "
                  "APK. Se a instalação exigir os splits, use adb install-multiple.",
            )
        self.refresh()

    def act_validar_servidor(self) -> None:
        if not (self._exige_projeto() and self._exige_livre()):
            return
        assert self.project is not None
        if not self.project.server_host:
            messagebox.showwarning("Validar servidor", "informe o hostname do servidor primeiro.")
            return
        host = self.project.server_host
        ca = self.project.ca_path
        destino = self._reports_dir() / "server-preflight.json"
        self._submit(
            "validar-servidor",
            lambda ctx: _trabalho_servidor(host, ca, destino, ctx),
            ao_concluir=self._apos_validar_servidor,
        )

    def _apos_validar_servidor(self, evento: DoneEvent) -> None:
        """Mostra os checks separados sempre; marca SERVIDOR_VALIDADO só no verde."""
        if self.project is None:
            return
        resultado = evento.result
        self._mostrar_checks_servidor(resultado)
        self.project.reports["server_preflight"] = str(self._reports_dir() / "server-preflight.json")
        if resultado.ok:
            self.project.state.mark(Stage.SERVIDOR_VALIDADO)
            save_project(self.project, studio_root=self.studio_root)
            self.log.append(
                f"[OK] servidor validado: cliente {resultado.client_version} · "
                f"API {resultado.api_version} · game_data_loaded={resultado.game_data_loaded}",
                "info",
            )
        else:
            falha = getattr(resultado, "failure", None)
            mensagem = falha.message if falha else "; ".join(resultado.errors) or "sem detalhe"
            detalhe = mensagem
            if falha and falha.details:
                detalhe += f"\n{falha.details}"
            self.log.append(f"[FALHOU] validar-servidor: {mensagem}", "erro")
            self.var_status.set("validar-servidor: FALHOU")
            messagebox.showerror("Validar servidor", detalhe)
        self.refresh()

    # -- Servidor local (§6.1: setup/start do servidor como serviço) -------

    def act_preparar_servidor_local(self) -> None:
        """Preparo do servidor local — nível repositório, sem projeto aberto."""
        if not self._exige_livre():
            return
        self._submit(
            "preparar-servidor",
            _trabalho_preparar_servidor,
            ao_concluir=self._apos_preparar_servidor,
        )

    def _apos_preparar_servidor(self, evento: DoneEvent) -> None:
        resultado = evento.result
        if resultado.ok:
            self.log.append(
                f"[OK] preparar-servidor: node {resultado.node_version} · "
                f"{len(resultado.copied)} config(s) criado(s)",
                "info",
            )
            self.var_status.set("servidor local preparado")
            if resultado.copied:
                extras = "Configs criados (de *.example):\n  - " + "\n  - ".join(resultado.copied)
            else:
                extras = "Nenhum config novo: todos já existiam — nada foi sobrescrito."
            messagebox.showinfo(
                "Preparar servidor local",
                "Preparo concluído com sucesso.\n\n"
                f"Node: {resultado.node_version}\n\n"
                + extras
                + "\n\nRevise server/.env (troque REVIVAL_ADMIN_TOKEN=change-me).",
            )
        else:
            self.log.append(f"[FALHOU] preparar-servidor: {resultado.erro}", "erro")
            self.var_status.set("preparar-servidor: FALHOU")
            messagebox.showerror("Preparar servidor local", resultado.erro or "falha sem detalhe")
        self.refresh()

    def act_iniciar_servidor_local(self) -> None:
        if not self._exige_livre():
            return
        self._submit(
            "iniciar-servidor",
            _trabalho_iniciar_servidor,
            ao_concluir=self._apos_iniciar_servidor,
        )

    def _apos_iniciar_servidor(self, evento: DoneEvent) -> None:
        resultado = evento.result
        if not resultado.ok:
            self.log.append(f"[FALHOU] iniciar-servidor: {resultado.erro}", "erro")
            self.var_status.set("iniciar-servidor: FALHOU")
            messagebox.showerror("Iniciar servidor local", resultado.erro or "falha sem detalhe")
            self.refresh()
            return
        saude = resultado.health or {}
        if resultado.ja_em_execucao:
            self.log.append(
                f"[OK] iniciar-servidor: já estava em execução na porta {resultado.port}",
                "info",
            )
        else:
            self.log.append(
                f"[OK] iniciar-servidor: pid {resultado.pid} na porta {resultado.port} · "
                f"game_data_loaded={saude.get('game_data_loaded')}",
                "info",
            )
        self.var_status.set(f"servidor local ativo (porta {resultado.port})")
        messagebox.showinfo(
            "Iniciar servidor local",
            f"Servidor Revival ativo em http://127.0.0.1:{resultado.port}\n\n"
            f"PID: {resultado.pid if resultado.pid is not None else 'desconhecido (iniciado fora do Studio)'}\n"
            f"game_data_loaded: {saude.get('game_data_loaded')}\n"
            f"research_mode: {saude.get('research_mode')}\n\n"
            f"Log: {resultado.log_path}\n"
            "Encerre pelo menu Servidor → Encerrar servidor local.",
        )
        self.refresh()

    def act_parar_servidor_local(self) -> None:
        if not self._exige_livre():
            return
        if not messagebox.askyesno(
            "Encerrar servidor local",
            "Encerrar o servidor Revival local?\n\n"
            "O processo registrado em work/revival-studio/server/server.pid será "
            "terminado agora. Testes de dispositivo em andamento perderão o servidor.",
        ):
            return
        self._submit(
            "encerrar-servidor",
            _trabalho_parar_servidor,
            ao_concluir=self._apos_parar_servidor,
        )

    def _apos_parar_servidor(self, evento: DoneEvent) -> None:
        resultado = evento.result
        if resultado.ok:
            for passo in resultado.steps:
                self.log.append(f"[OK] encerrar-servidor: {passo}", "info")
            self.var_status.set("servidor local encerrado")
        else:
            self.log.append(f"[FALHOU] encerrar-servidor: {resultado.erro}", "erro")
            self.var_status.set("encerrar-servidor: FALHOU")
            messagebox.showerror("Encerrar servidor local", resultado.erro or "falha sem detalhe")
        self.refresh()

    def act_status_servidor_local(self) -> None:
        if not self._exige_livre():
            return
        self._submit(
            "status-servidor",
            _trabalho_status_servidor,
            ao_concluir=self._apos_status_servidor,
        )

    def _apos_status_servidor(self, evento: DoneEvent) -> None:
        estado = evento.result
        saude = estado["health"]
        if saude is None:
            mensagem = (
                f"Sem resposta em http://127.0.0.1:{estado['porta']}/revival/health\n\n"
                "O servidor local não está em execução."
            )
            self.var_status.set("servidor local: parado")
        else:
            mensagem = (
                f"Servidor ativo em http://127.0.0.1:{estado['porta']}\n\n"
                f"ok: {saude.get('ok')}\n"
                f"game_data_loaded: {saude.get('game_data_loaded')}\n"
                f"packs: {saude.get('packs')} · events: {saude.get('events')} · "
                f"players: {saude.get('players')}\n"
                f"research_mode: {saude.get('research_mode')}\n\n"
                f"PID registrado: {estado['pid']} "
                f"({'vivo' if estado['pid_vivo'] else 'não encontrado'})"
            )
            self.var_status.set(f"servidor local: ativo (porta {estado['porta']})")
        self.log.append(f"[info] status-servidor: {mensagem.splitlines()[0]}", "info")
        messagebox.showinfo("Status do servidor local", mensagem)
        self.refresh()

    def act_pipeline_completo(self) -> None:
        """Fase 6: o pipeline inteiro como serviço (revival_editor.pipeline)."""
        if not (self._exige_projeto() and self._exige_livre()):
            return
        assert self.project is not None
        if not self.project.input_apk:
            messagebox.showwarning("Aplicar endpoint", "escolha o APK de entrada no formulário primeiro.")
            return
        if not self.project.server_host:
            messagebox.showwarning(
                "Aplicar endpoint",
                "informe o hostname do servidor e valide-o (menu Servidor) primeiro.",
            )
            return
        projeto = self.project
        diretorio = project_dir(projeto.project_id, studio_root=self.studio_root)
        self._submit(
            "aplicar-endpoint",
            lambda ctx: _trabalho_pipeline(projeto, diretorio, ctx),
            ao_concluir=self._apos_pipeline,
        )

    def _apos_pipeline(self, evento: DoneEvent) -> None:
        """Marca WORKSPACE_PREPARADO…APK_VERIFICADO — só depois de tudo verde."""
        if self.project is None:
            return
        resultado = evento.result
        for etapa in (
            Stage.WORKSPACE_PREPARADO,
            Stage.PATCH_APLICADO,
            Stage.APK_RECONSTRUIDO,
            Stage.APK_ASSINADO,
            Stage.APK_VERIFICADO,
        ):
            self.project.state.mark(etapa)
        self.project.output_apk = resultado.output_apk
        reports = self._reports_dir()
        self.project.reports["patch"] = str(reports / "patch-report.json")
        self.project.reports["verify"] = str(reports / "final-apk-verification.json")
        self.project.reports["pipeline"] = str(reports / "pipeline.json")
        save_project(self.project, studio_root=self.studio_root)
        self.log.append(
            f"[OK] APK final: {resultado.output_apk} "
            f"(estratégia {resultado.strategy_used} · precheck exit {resultado.precheck_exit})",
            "info",
        )
        if resultado.bundles_alterados:
            self.log.append(
                f"bundles alterados: {len(resultado.bundles_alterados)} · "
                f"CRCs zerados: {len(resultado.crcs_zerados)}",
                "info",
            )
        self.refresh()

    # ==================================================================
    # menus — Visuais
    # ==================================================================

    def act_visuals_loading(self) -> None:
        """Abre a aba Visuais (fase 7) — editor de tela de loading."""
        self.notebook.select(self.visuals_tab)

    def act_branding_android(self) -> None:
        """Abre a aba Branding (fase 8): nome/ícone/cor com diff e bloqueios."""
        self.notebook.select(self.branding_tab)

    def act_assets_catalog(self) -> None:
        """Abre a aba Assets (fase 9): catálogo somente-leitura dos bundles."""
        self.notebook.select(self.assets_tab)

    def act_compat_registro(self) -> None:
        """Abre a aba Compatibilidade (fase 16): registro 116 rotas, somente
        leitura — mutação de evidência apenas via generate_endpoint_matrix.py."""
        self.notebook.select(self.compat_tab)

    # ==================================================================
    # menus — Ferramentas
    # ==================================================================

    def act_verificar_ferramentas(self) -> None:
        """Fase 3, gate: a tela informa caminho e versão de cada ferramenta."""
        if not self._exige_livre():
            return
        destino = self.studio_root / "logs" / "toolchain.json"
        self._submit(
            "ferramentas-status",
            lambda ctx: _trabalho_ferramentas_status(destino, ctx),
            ao_concluir=self._apos_ferramentas_status,
        )

    def _apos_ferramentas_status(self, evento: DoneEvent) -> None:
        relatorio = evento.result
        if relatorio.ok:
            titulo = "Ferramentas: nenhuma pendência obrigatória"
        else:
            titulo = "Ferramentas bloqueando: " + ", ".join(t.name for t in relatorio.blocking)
        linhas = [titulo, ""]
        for ferramenta in relatorio.tools:
            marca = "✓" if ferramenta.ok else "✗"
            obrigatorio = "" if ferramenta.required else " (opcional)"
            versao = f" {ferramenta.version}" if ferramenta.version else ""
            linhas.append(f"{marca} {ferramenta.name}{versao}{obrigatorio}")
            if ferramenta.path:
                linhas.append(f"    caminho: {ferramenta.path}")
            if not ferramenta.ok and ferramenta.detail:
                linhas.append("    " + ferramenta.detail.replace("\n", "\n    "))
        messagebox.showinfo("Verificar ferramentas", "\n".join(linhas))

    def act_preparar_ferramentas(self) -> None:
        """Fase 3: serviço `toolchain.prepare_tools` (fonte única dos pins)
        — pede confirmação antes de baixar qualquer coisa."""
        if not self._exige_livre():
            return
        confirmado = messagebox.askyesno(
            "Preparar ferramentas",
            "Baixar/validar em .tools/ (SHA-256 pinado, sem trocar de versão):\n"
            "  • Apktool 3.0.3 → apktool.jar\n"
            "  • uber-apk-signer 1.3.0 → uber-apk-signer.jar\n"
            "\n"
            "O Java é resolvido antes (explícito > REVIVAL_JAVA > .tools/jre17\n"
            "> PATH apenas se 17+); Java antigo é rejeitado com instrução.\n"
            "\nConfirmar o download?",
        )
        if not confirmado:
            return
        self.log.append("== preparar ferramentas: download com hashes pinados", "info")
        self._submit(
            "preparar-ferramentas",
            _trabalho_preparar_ferramentas,
            ao_concluir=self._reverificar_pos_preparo,
        )

    def _reverificar_pos_preparo(self, _evento: DoneEvent) -> None:
        """Encadeia a verificação depois do preparo — o gate da fase 3 pede
        caminho e versão de cada ferramenta na tela."""
        self.act_verificar_ferramentas()

    # ==================================================================
    # menus — Cliente / Testes / Log
    # ==================================================================

    def act_detectar_dispositivos(self) -> None:
        if not self._exige_livre():
            return
        self._submit("adb-devices", _trabalho_adb)

    def act_testes_editor(self) -> None:
        if not self._exige_livre():
            return
        pasta = self.repo_root / "tests" / "revival_editor"
        self._submit(
            "testes-editor",
            lambda ctx: _trabalho_testes(
                [sys.executable, "-m", "unittest", "discover",
                 "-s", str(pasta), "-p", "test_*.py", "-v"],
                ctx,
            ),
        )

    def act_verify_everything(self) -> None:
        if not self._exige_livre():
            return
        self._submit(
            "verify-everything",
            lambda ctx: _trabalho_testes(
                [sys.executable, str(self.repo_root / "scripts" / "verify_everything.py")],
                ctx,
            ),
        )

    def ui_salvar_log(self) -> None:
        destino = self.studio_root / "logs" / "log-salvo-painel.log"
        if self.project is not None:
            destino = project_dir(self.project.project_id, studio_root=self.studio_root) / "logs" / "log-salvo-painel.log"
        destino.parent.mkdir(parents=True, exist_ok=True)
        linhas = self.log.save_to_file(destino)
        self.log.append(f"log salvo ({linhas} linhas): {destino}", "info")

    def ui_limpar_log(self) -> None:
        self.log.clear()

    def ui_abrir_pasta_logs(self) -> None:
        if not self._exige_projeto():
            return
        assert self.project is not None
        pasta = project_dir(self.project.project_id, studio_root=self.studio_root) / "logs"
        pasta.mkdir(parents=True, exist_ok=True)
        _abrir_no_sistema(pasta)

    # ==================================================================
    # Ajuda — sobre, preservação de jogos e base legal
    # ==================================================================

    def act_sobre(self) -> None:
        from .about import mostrar_sobre

        mostrar_sobre(self.root)

    def act_preservacao(self) -> None:
        from .about import mostrar_preservacao

        mostrar_preservacao(self.root)

    def act_lei(self) -> None:
        from .about import mostrar_lei

        mostrar_lei(self.root)

    # ==================================================================
    # fechamento
    # ==================================================================

    def _ao_fechar(self) -> None:
        if self._fechando:
            return
        if self.runner.is_running:
            if not messagebox.askyesno(
                "Job em execução",
                "há um job rodando. Cancelar e sair?\n(a saída válida anterior não é substituída; "
                "o temporário .parcial fica preservado)",
            ):
                return
            self.runner.cancel("janela fechada pelo usuário")
            self._aguardar_e_fechar(3.0)
            return
        self._fechar()

    def _aguardar_e_fechar(self, restante: float) -> None:
        atual = self.runner.current
        if restante <= 0 or atual is None or atual.state.terminal:
            self._fechar()
        else:
            self.root.after(100, lambda: self._aguardar_e_fechar(restante - 0.1))

    def _fechar(self) -> None:
        self._fechando = True
        self.runner.close()
        self.root.destroy()

    def _despachar(self, spec: ActionSpec) -> Callable[[], None]:
        def executar() -> None:
            getattr(self, spec.handler)()

        return executar


# ==========================================================================
# trabalhos executados na worker thread — nada aqui toca widget
# ==========================================================================


def _trabalho_analisar(apk: str, destino: Path, ctx: Any) -> Any:
    ctx.progress("analisar", f"analisando {Path(apk).name}…", None)
    resultado = analyze_apk(apk, report_path=destino, log=ctx.log)
    ctx.progress("analisar", "análise concluída", 1.0)
    ctx.log(f"relatório: {destino}")
    return resultado


def _trabalho_precheck(apk: str, host: str, destino: Path, ctx: Any) -> Any:
    ctx.progress("precheck", f"medindo orçamento de bytes para {host}…", None)
    resultado = check_hostname_budget(apk, host, log=ctx.log)
    destino.write_text(
        json.dumps(resultado.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    ctx.log(f"relatório: {destino}")
    if resultado.blocks_pipeline:
        raise RuntimeError(
            f"precheck inválido (exit {resultado.exit_code}) — hostname ou APK rejeitado"
        )
    ctx.progress("precheck", resultado.verdict, 1.0)
    return resultado


def _trabalho_servidor(host: str, ca: str | None, destino: Path, ctx: Any) -> Any:
    """Preflight do servidor — devolve o resultado mesmo em falha.

    A falha já vem estruturada (checks separados + Failure); é o callback da
    UI que decide marcar etapa ou mostrar erro. Levantar aqui esconderia os
    checks parciais (DNS ✓ TLS ✗) que a fase 5 exige exibir.
    """
    ctx.progress("servidor", f"preflight HTTPS de {host}…", None)
    return server_preflight(host, ca_file=ca, report_path=destino, log=ctx.log)


def _trabalho_preparar_servidor(ctx: Any) -> Any:
    """Servidor → Preparar: espelho estruturado do wrapper de setup (§6.1)."""
    ctx.progress("servidor", "preparando servidor local…", None)
    return prepare_server(REPO_ROOT, ctx)


def _trabalho_iniciar_servidor(ctx: Any) -> Any:
    """Servidor → Iniciar: servidor local em segundo plano com health check."""
    ctx.progress("servidor", "iniciando servidor local…", None)
    return start_server(REPO_ROOT, ctx)


def _trabalho_parar_servidor(ctx: Any) -> Any:
    ctx.progress("servidor", "encerrando servidor local…", None)
    return stop_server(REPO_ROOT, ctx)


def _trabalho_status_servidor(ctx: Any) -> Any:
    ctx.progress("servidor", "consultando estado do servidor local…", None)
    return server_status(REPO_ROOT)


def _trabalho_pipeline(projeto: Project, diretorio: Path, ctx: Any) -> Any:
    """Roda `pipeline.apply_endpoint` na worker thread.

    O pipeline devolve resultado estruturado mesmo quando uma etapa falha; aqui
    a falha vira exceção para o JobRunner classificar o job como FALHOU — mas
    o `pipeline.json` com steps/failure já foi gravado como evidência antes.
    """
    from ..pipeline import apply_endpoint

    resultado = apply_endpoint(
        ctx,
        apk=projeto.input_apk or "",
        host=projeto.server_host or "",
        project_dir=diretorio,
        ca_file=projeto.ca_path,
        strategy=projeto.patch_strategy,
        # Sem isto o botão normal "Aplicar endpoint" gerava um APK SEM a
        # RevivalAuthActivity, e só um script auxiliar produzia o build de
        # verdade. A opção vem do projeto e é persistida com ele.
        revival_auth=projeto.revival_auth,
        # Override de laboratório: só quando o projeto o declara, e o
        # `pipeline.json` registra que foi usado.
        allow_incompatible_server=projeto.allow_incompatible_server,
    )
    relatorio = diretorio / "reports" / "pipeline.json"
    relatorio.parent.mkdir(parents=True, exist_ok=True)
    relatorio.write_text(
        json.dumps(resultado.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    ctx.log(f"relatório do pipeline: {relatorio}")
    if not resultado.ok:
        falha = resultado.failure
        assert falha is not None
        partes = [f"[{falha.code}] {falha.message}"]
        if falha.exit_code is not None:
            partes[0] += f" (exit {falha.exit_code})"
        if falha.details:
            partes.append(falha.details)
        if falha.report_path:
            partes.append(f"relatório: {falha.report_path}")
        raise RuntimeError("\n".join(partes))
    return resultado


def _trabalho_xapk(caminho: str, destino_dir: Path, ctx: Any) -> Any:
    """Inspeciona o XAPK e extrai o base APK — worker thread, sem widget."""
    from ..xapk import extract_base_apk, inspect_xapk

    ctx.progress("xapk", f"inspecionando {Path(caminho).name}…", None)
    info = inspect_xapk(caminho)
    ctx.log(
        f"xapk: pacote {info.package_name} {info.version_name or '?'} · "
        f"base {info.base_apk} · {len(info.splits)} split(s) · {len(info.obbs)} obb(s)"
    )
    if info.has_splits:
        ctx.log(
            f"[A VERIFICAR] splits não mesclados: {', '.join(info.splits)}",
            stream="aviso",
        )
    ctx.progress("xapk", "extraindo o base APK…", 0.5)
    base = extract_base_apk(info, destino_dir)
    ctx.progress("xapk", "base APK extraído", 1.0)
    return info, base


def _trabalho_adb(ctx: Any) -> None:
    from ..toolchain import check_adb

    status = check_adb()
    if not status.ok or not status.path:
        ctx.log("[info] adb não encontrado — é opcional até a fase 11 (aba Dispositivo)")
        ctx.progress("adb", "adb ausente (opcional)", 1.0)
        return
    ctx.progress("adb", "consultando dispositivos…", None)
    codigo = ctx.run_process([status.path, "devices", "-l"], stage="adb")
    if codigo != 0:
        raise RuntimeError(f"adb devices falhou com exit {codigo}")


def _trabalho_testes(comando: list[str], ctx: Any) -> int:
    ctx.progress("testes", "executando…", None)
    codigo = ctx.run_process(comando, cwd=REPO_ROOT, stage="testes", timeout=1800)
    ctx.log(f"exit {codigo}")
    if codigo != 0:
        raise RuntimeError(f"comando falhou com exit {codigo} (veja o log acima)")
    ctx.progress("testes", "tudo verde", 1.0)
    return codigo


def _trabalho_preparar_ferramentas(ctx: Any) -> ToolchainReport:
    """Preparo das ferramentas pelo serviço — download pinado em toolchain."""
    ctx.progress("ferramentas", "baixando/validando JARs (hashes pinados)…", None)
    relatorio = prepare_tools(ctx)
    ctx.progress("ferramentas", "JARs prontos", 1.0)
    return relatorio


def _trabalho_ferramentas_status(destino: Path, ctx: Any):
    from ..toolchain import detect_toolchain

    ctx.progress("ferramentas", "inspecionando toolchain…", None)
    relatorio = detect_toolchain()
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(relatorio.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    for ferramenta in relatorio.tools:
        marca = "✓" if ferramenta.ok else "✗"
        onde = f" — {ferramenta.path}" if ferramenta.path else ""
        primeira = ferramenta.detail.splitlines()[0] if ferramenta.detail else ""
        ctx.log(f"{marca} {ferramenta.name}: {primeira}{onde}")
    ctx.progress("ferramentas", "toolchain inspecionada", 1.0)
    return relatorio


def _abrir_no_sistema(caminho: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(caminho))  # noqa: S606 - explorer, confiança do usuário
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(caminho)])
        else:
            subprocess.Popen(["xdg-open", str(caminho)])
    except OSError as exc:
        messagebox.showerror("Abrir pasta", f"não consegui abrir {caminho}: {exc}")


# ==========================================================================


def main(argv: list[str] | None = None) -> int:
    """Entry point do launcher `scripts/revival_studio.py`."""
    root = tk.Tk()
    StudioApp(root)
    root.mainloop()
    return 0
