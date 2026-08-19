"""Aba Branding do Revival Studio (fase 8): invólucro Android seguro.

Consome `revival_editor.branding` — todo o poder de recusa mora lá (label só
no recurso referenciado, ícone só com todos os recursos mapeados, cor só em
recurso existente). O que esta aba acrescenta é o fluxo da UI:

- lê a árvore decoded **do projeto** (`work/revival-studio/<id>/decoded`,
  criada pela etapa decode do pipeline), nunca um caminho digitado;
- mostra o diff **antes** de aplicar e exige confirmação;
- aplica como job do JobRunner; depois prova com `verify_untouched` que o
  manifest não mudou;
- invalida APK_RECONSTRUIDO e seguintes (o APK construído ficou velho) e
  marca CUSTOMIZACOES_APLICADAS;
- modo avançado é **somente-leitura** — inspecionar sem botão de editar.
"""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING, Any

from .. import branding
from .theme import CARD_DARK, TEXT
from ..models import Stage
from ..project import save_project

if TYPE_CHECKING:  # só para anotações; evita ciclo de import em runtime
    from .app import StudioApp


class BrandingTab(ttk.Frame):
    """Editor de branding (nome exibido, ícone, cor de tema/splash)."""

    def __init__(self, master: Any, app: "StudioApp") -> None:
        super().__init__(master, padding=10)
        self.app = app
        self.decoded: Path | None = None
        self.manifest_antes: branding.ManifestInfo | None = None
        self.plano: branding.BrandingPlan | None = None
        self.icon_source: Path | None = None

        self.var_label = tk.StringVar()
        self.var_color_name = tk.StringVar()
        self.var_color = tk.StringVar(value="#7B1FA2")

        self._construir()
        self._atualizar_estado()

    # ------------------------------------------------------------------
    # construção
    # ------------------------------------------------------------------

    def _construir(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        controles = ttk.LabelFrame(self, text="Branding Android", padding=10)
        controles.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        controles.columnconfigure(0, weight=1)

        ttk.Button(
            controles, text="Ler árvore decoded do projeto…", command=self.ler_arvore
        ).grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.lbl_info = ttk.Label(
            controles,
            text="— árvore não lida —\n rode o pipeline (menu APK) até o decode",
            wraplength=260, justify="left",
        )
        self.lbl_info.grid(row=1, column=0, sticky="w", pady=(0, 10))

        ttk.Separator(controles).grid(row=2, column=0, sticky="ew", pady=4)

        ttk.Label(controles, text="Novo nome exibido").grid(row=3, column=0, sticky="w", pady=(4, 2))
        self.ent_label = ttk.Entry(controles, textvariable=self.var_label)
        self.ent_label.grid(row=4, column=0, sticky="ew", pady=(0, 4))
        self.btn_label = ttk.Button(controles, text="Planejar mudança de nome", command=self.planejar_label)
        self.btn_label.grid(row=5, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(controles, text="Ícone (todas as densidades + adaptive)").grid(
            row=6, column=0, sticky="w", pady=(4, 2)
        )
        ttk.Button(controles, text="Abrir imagem de ícone…", command=self.abrir_icone).grid(
            row=7, column=0, sticky="ew", pady=(0, 4)
        )
        self.lbl_icone = ttk.Label(controles, text="— sem imagem —", wraplength=260)
        self.lbl_icone.grid(row=8, column=0, sticky="w", pady=(0, 4))
        self.btn_icone = ttk.Button(controles, text="Planejar mudança de ícone", command=self.planejar_icone)
        self.btn_icone.grid(row=9, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(controles, text="Cor de tema/splash (recurso existente)").grid(
            row=10, column=0, sticky="w", pady=(4, 2)
        )
        self.ent_color_name = ttk.Entry(controles, textvariable=self.var_color_name)
        self.ent_color_name.grid(row=11, column=0, sticky="ew", pady=(0, 4))
        self.ent_color = ttk.Entry(controles, textvariable=self.var_color)
        self.ent_color.grid(row=12, column=0, sticky="ew", pady=(0, 4))
        self.btn_cor = ttk.Button(controles, text="Planejar mudança de cor", command=self.planejar_cor)
        self.btn_cor.grid(row=13, column=0, sticky="ew", pady=(0, 10))

        ttk.Separator(controles).grid(row=14, column=0, sticky="ew", pady=4)
        ttk.Button(
            controles, text="Modo avançado (somente leitura)…", command=self.modo_avancado
        ).grid(row=15, column=0, sticky="ew", pady=4)
        ttk.Label(
            controles,
            text=(
                "Bloqueado no modo normal: package, minSdk, targetSdk,\n"
                "componentes, permissões e exported — verificado após aplicar."
            ),
            wraplength=260,
        ).grid(row=16, column=0, sticky="w", pady=(10, 0))

        area = ttk.LabelFrame(self, text="Diff — antes de aplicar", padding=6)
        area.grid(row=0, column=1, sticky="nsew")
        area.columnconfigure(0, weight=1)
        area.rowconfigure(0, weight=1)
        self.txt_diff = tk.Text(area, wrap="none", state="disabled", height=18,
                                 background=CARD_DARK, foreground=TEXT,
                                 insertbackground=TEXT)
        self.txt_diff.grid(row=0, column=0, sticky="nsew")

        barra = ttk.Frame(area)
        barra.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.btn_aplicar = ttk.Button(barra, text="Aplicar plano…", command=self.aplicar)
        self.btn_aplicar.grid(row=0, column=0, padx=(0, 6))
        self.btn_descartar = ttk.Button(barra, text="Descartar plano", command=self.descartar)
        self.btn_descartar.grid(row=0, column=1)

    def _atualizar_estado(self) -> None:
        com_plano = self.plano is not None
        self.btn_aplicar.state(["!disabled"] if com_plano else ["disabled"])
        self.btn_descartar.state(["!disabled"] if com_plano else ["disabled"])

    def _mostrar_diff(self, texto: str) -> None:
        self.txt_diff.config(state="normal")
        self.txt_diff.delete("1.0", "end")
        self.txt_diff.insert("1.0", texto)
        self.txt_diff.config(state="disabled")

    # ------------------------------------------------------------------
    # leitura da árvore decoded
    # ------------------------------------------------------------------

    def _decoded_do_projeto(self) -> Path | None:
        projeto = self.app.project
        if projeto is None:
            messagebox.showwarning("Branding", "abra um projeto primeiro (menu Projeto).", parent=self)
            return None
        from ..paths import project_dir  # noqa: PLC0415

        return project_dir(projeto.project_id, studio_root=self.app.studio_root) / "decoded"

    def ler_arvore(self) -> None:
        decoded = self._decoded_do_projeto()
        if decoded is None:
            return
        try:
            info = branding.read_manifest(decoded)
        except branding.BrandingError as exc:
            self.decoded = None
            self.manifest_antes = None
            self.lbl_info.configure(text="— árvore não lida —")
            messagebox.showerror("Branding", str(exc), parent=self)
            return
        self.decoded = decoded
        self.manifest_antes = info
        icones = ", ".join(info.icon_refs) or "nenhum"
        self.lbl_info.configure(text=(
            f"package: {info.package}\n"
            f"label: {info.label_raw}\n"
            f"ícones: {icones}\n"
            f"minSdk {info.min_sdk or '?'} · targetSdk {info.target_sdk or '?'}"
        ))
        self.app.log.append(f"[branding] árvore decoded lida: {info.package}", "info")

    # ------------------------------------------------------------------
    # planejamento (diff antes de aplicar — fase 8)
    # ------------------------------------------------------------------

    def _exigir_arvore(self) -> bool:
        if self.decoded is None or self.manifest_antes is None:
            self.ler_arvore()
        return self.decoded is not None

    def _publicar_plano(self, plano: branding.BrandingPlan) -> None:
        self.plano = plano
        self._mostrar_diff(branding.render_diff(plano))
        self._atualizar_estado()
        self.app.log.append("[branding] plano pronto — revise o diff antes de aplicar", "info")

    def planejar_label(self) -> None:
        if not self._exigir_arvore():
            return
        try:
            plano = branding.plan_label_change(self.decoded, self.var_label.get())
        except branding.BrandingError as exc:
            messagebox.showerror("Mudança de nome", str(exc), parent=self)
            return
        self._publicar_plano(plano)

    def abrir_icone(self) -> None:
        caminho = filedialog.askopenfilename(
            parent=self,
            filetypes=[("Imagens", "*.png *.jpg *.jpeg *.webp"), ("Todos", "*.*")],
        )
        if not caminho:
            return
        self.icon_source = Path(caminho)
        self.lbl_icone.configure(text=Path(caminho).name)

    def planejar_icone(self) -> None:
        if not self._exigir_arvore():
            return
        if self.icon_source is None:
            messagebox.showwarning("Mudança de ícone", "abra uma imagem primeiro.", parent=self)
            return
        try:
            plano = branding.plan_icon_change(self.decoded, self.icon_source)
        except branding.BrandingError as exc:
            messagebox.showerror("Mudança de ícone", str(exc), parent=self)
            return
        self._publicar_plano(plano)

    def planejar_cor(self) -> None:
        if not self._exigir_arvore():
            return
        try:
            plano = branding.plan_theme_change(
                self.decoded, self.var_color_name.get(), self.var_color.get()
            )
        except branding.BrandingError as exc:
            messagebox.showerror("Mudança de cor", str(exc), parent=self)
            return
        self._publicar_plano(plano)

    def descartar(self) -> None:
        self.plano = None
        self._mostrar_diff("(plano descartado)")
        self._atualizar_estado()

    # ------------------------------------------------------------------
    # modo avançado somente-leitura
    # ------------------------------------------------------------------

    def modo_avancado(self) -> None:
        decoded = self._decoded_do_projeto()
        if decoded is None:
            return
        try:
            snap = branding.advanced_snapshot(decoded)
        except branding.BrandingError as exc:
            messagebox.showerror("Modo avançado", str(exc), parent=self)
            return
        janela = tk.Toplevel(self)
        janela.title("Modo avançado — somente leitura")
        janela.transient(self.winfo_toplevel())
        texto = tk.Text(janela, wrap="none", state="disabled", width=100, height=32,
                    background=CARD_DARK, foreground=TEXT,
                    insertbackground=TEXT)
        texto.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        conteudo = (
            f"== recursos: {snap['resource_total']} arquivo(s) "
            f"(listados {len(snap['resources'])}, truncado={snap['truncated']}) ==\n\n"
            + snap["manifest"]
            + "\n\n== inventário ==\n"
            + "\n".join(f"{r['path']}  ({r['size']} bytes)" for r in snap["resources"])
        )
        texto.config(state="normal")
        texto.insert("1.0", conteudo)
        texto.config(state="disabled")  # somente leitura: nada aqui é editável

    # ------------------------------------------------------------------
    # aplicação
    # ------------------------------------------------------------------

    def aplicar(self) -> None:
        if self.plano is None or self.decoded is None or self.manifest_antes is None:
            return
        if self.app.project is None:
            messagebox.showwarning("Aplicar branding", "abra um projeto primeiro (menu Projeto).", parent=self)
            return
        if not messagebox.askyesno(
            "Aplicar branding",
            "Aplicar o plano mostrado no diff?\n\n"
            "A árvore decoded muda — o APK construído/assinado anterior fica\n"
            "velho (etapas de build/assinatura/verificação serão invalidadas)\n"
            "e o pipeline precisa reconstruir depois.\n"
            "O AndroidManifest.xml NÃO é editado.",
            parent=self,
        ):
            return
        plano = self.plano
        decoded = self.decoded
        antes = self.manifest_antes
        from ..paths import project_dir  # noqa: PLC0415

        pasta = project_dir(self.app.project.project_id, studio_root=self.app.studio_root)
        relatorio = pasta / "reports" / "branding.json"
        self.app._submit(
            "branding-apply",
            lambda ctx: _trabalho_aplicar(decoded, plano, antes, relatorio, ctx),
            ao_concluir=self._apos_aplicar,
        )

    def _apos_aplicar(self, evento: Any) -> None:
        projeto = self.app.project
        if projeto is None:
            return
        resultado = evento.result
        # a árvore mudou: build/assinatura/verificação anteriores caducaram
        invalidadas = projeto.state.invalidate_from(Stage.APK_RECONSTRUIDO)
        projeto.state.mark(Stage.CUSTOMIZACOES_APLICADAS)
        projeto.reports["branding"] = str(resultado["report_path"])
        save_project(projeto, studio_root=self.app.studio_root)
        if invalidadas:
            nomes = ", ".join(s.value for s in sorted(invalidadas, key=lambda s: s.order))
            self.app.log.append(f"[branding] etapas invalidadas (APK velho): {nomes}", "aviso")
        self.app.log.append(
            f"[branding] aplicado: {len(resultado['labels_alterados'])} recurso(s) de texto/cor, "
            f"{len(resultado['icones_gerados'])} ícone(s) — manifest intocado",
            "info",
        )
        self.plano = None
        self._mostrar_diff("(aplicado — construa o APK de novo no pipeline)")
        self._atualizar_estado()
        self.app.refresh()


def _trabalho_aplicar(
    decoded: Path,
    plano: branding.BrandingPlan,
    manifest_antes: branding.ManifestInfo,
    relatorio: Path,
    ctx: Any,
) -> dict:
    ctx.progress("branding", "aplicando plano na árvore decoded…", None)
    resultado = branding.apply_plan(plano)
    if not branding.verify_untouched(manifest_antes, decoded):
        raise RuntimeError(
            "verify_untouched falhou: campo protegido do manifest mudou — "
            "a mudança foi aplicada mas o resultado NÃO é seguro; investigue."
        )
    relatorio.parent.mkdir(parents=True, exist_ok=True)
    relatorio.write_text(
        json.dumps(
            {"plan": plano.to_dict(), "result": resultado, "verified_untouched": True},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    ctx.progress("branding", "branding aplicado e verificado", 1.0)
    return {**resultado, "report_path": str(relatorio)}
