"""Aba Visuais do Revival Studio (fase 7): tela de loading.

Reencarna o editor standalone (`scripts/loading_screen_editor.py`) como aba
do Studio, consumindo o serviço de domínio `revival_editor.visuals` — que por
sua vez usa a **mesma** `compose_loading_image` do fluxo de injeção validado
(fonte única, zero duplicação).

Diferenças de contrato para o editor standalone:

- a injeção roda como job do `JobRunner` (janela responde, cancelável);
- o alvo é o APK do **projeto** (saída do pipeline se existir, senão a
  entrada), nunca um caminho digitado livre;
- depois de injetar, as etapas de assinatura/verificação anteriores são
  invalidadas (plano fase 7) e `CUSTOMIZACOES_APLICADAS` é marcada.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING, Any

from .. import visuals
from ..models import Stage
from ..project import save_project

if TYPE_CHECKING:  # só para anotações; evita ciclo de import em runtime
    from .app import StudioApp

MODE_LABELS = {
    "Imagem": "image",
    "Imagem + Texto": "image+text",
    "Só Texto": "text",
}


class VisualsTab(ttk.Frame):
    """Editor da tela de loading embutido no notebook do Studio."""

    def __init__(self, master: Any, app: "StudioApp") -> None:
        super().__init__(master, padding=10)
        self.app = app
        self.source: Any | None = None          # PIL.Image aberta e validada
        self.source_info: visuals.SourceImageInfo | None = None
        self.preview: Any | None = None          # arte composta em 2048x2048
        self._preview_tk: Any | None = None
        self._crops_tk: list[tuple[str, Any]] = []

        self.var_mode = tk.StringVar(value="Imagem + Texto")
        self.var_title = tk.StringVar(value="REVIVAL")
        self.var_subtitle = tk.StringVar(value="COMMUNITY SERVER")
        self.var_status = tk.StringVar(value="Connecting to Revival Server...")
        self.var_color = tk.StringVar(value="#160b12")
        self.var_safe = tk.BooleanVar(value=True)

        self._construir()
        self.render()

    # ------------------------------------------------------------------
    # construção
    # ------------------------------------------------------------------

    def _construir(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        controles = ttk.LabelFrame(self, text="Loading screen", padding=10)
        controles.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        controles.columnconfigure(0, weight=1)

        ttk.Label(controles, text="Modo").grid(row=0, column=0, sticky="w", pady=(0, 2))
        caixa = ttk.Combobox(
            controles, textvariable=self.var_mode, values=tuple(MODE_LABELS),
            state="readonly",
        )
        caixa.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        caixa.bind("<<ComboboxSelected>>", lambda _e: self._ao_mudar_modo())

        self.campos: list[ttk.Entry] = []
        for desloc, (rotulo, var) in enumerate((
            ("Título", self.var_title),
            ("Subtítulo", self.var_subtitle),
            ("Mensagem", self.var_status),
        )):
            ttk.Label(controles, text=rotulo).grid(
                row=2 + desloc * 2, column=0, sticky="w", pady=(4, 2)
            )
            entrada = ttk.Entry(controles, textvariable=var)
            entrada.grid(row=3 + desloc * 2, column=0, sticky="ew", pady=(0, 8))
            entrada.bind("<KeyRelease>", lambda _e: self.render())
            self.campos.append(entrada)

        ttk.Label(controles, text="Cor de fundo (só texto)").grid(row=8, column=0, sticky="w", pady=(4, 2))
        self.ent_cor = ttk.Entry(controles, textvariable=self.var_color)
        self.ent_cor.grid(row=9, column=0, sticky="ew", pady=(0, 8))
        self.ent_cor.bind("<KeyRelease>", lambda _e: self.render())

        ttk.Button(controles, text="Abrir imagem de fundo…", command=self.abrir_imagem).grid(
            row=10, column=0, sticky="ew", pady=(10, 4)
        )
        ttk.Button(controles, text="Remover imagem", command=self.remover_imagem).grid(
            row=11, column=0, sticky="ew", pady=4
        )
        self.lbl_fonte = ttk.Label(controles, text="— sem imagem de fundo —", wraplength=240)
        self.lbl_fonte.grid(row=12, column=0, sticky="w", pady=(4, 8))

        self.chk_safe = ttk.Checkbutton(
            controles, text="Mostrar safe area (5%)", variable=self.var_safe,
            command=self.render,
        )
        self.chk_safe.grid(row=13, column=0, sticky="w", pady=4)

        ttk.Separator(controles).grid(row=14, column=0, sticky="ew", pady=10)
        ttk.Button(controles, text="Exportar PNG…", command=self.exportar_png).grid(
            row=15, column=0, sticky="ew", pady=4
        )
        self.btn_injetar = ttk.Button(controles, text="Injetar no APK do projeto…", command=self.injetar)
        self.btn_injetar.grid(row=16, column=0, sticky="ew", pady=4)
        ttk.Label(
            controles,
            text=(
                "A arte substitui apenas as texturas de loading do bundle\n"
                "Addressables; o bundle é reaberto e comparado, o CRC do\n"
                "catálogo é zerado e o APK é assinado de novo."
            ),
            wraplength=240,
        ).grid(row=17, column=0, sticky="w", pady=(10, 0))

        area = ttk.Frame(self)
        area.grid(row=0, column=1, sticky="nsew")
        area.columnconfigure(0, weight=1)
        area.rowconfigure(0, weight=1)

        painel = ttk.LabelFrame(area, text="Pré-visualização (2048 × 2048)", padding=6)
        painel.grid(row=0, column=0, sticky="nsew")
        painel.rowconfigure(0, weight=1)
        painel.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(painel, background="#111", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _e: self._mostrar_preview())

        faixa = ttk.LabelFrame(area, text="Corte nas proporções comuns", padding=6)
        faixa.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._frame_crops = ttk.Frame(faixa)
        self._frame_crops.grid(row=0, column=0, sticky="w")

    # ------------------------------------------------------------------
    # estado de modo
    # ------------------------------------------------------------------

    def modo(self) -> str:
        return MODE_LABELS.get(self.var_mode.get(), "image+text")

    def _ao_mudar_modo(self) -> None:
        com_texto = self.modo() in ("image+text", "text")
        for entrada in self.campos:
            entrada.state(["!disabled"] if com_texto else ["disabled"])
        self.ent_cor.state(["!disabled"] if self.modo() == "text" else ["disabled"])
        self.render()

    # ------------------------------------------------------------------
    # imagem de fundo
    # ------------------------------------------------------------------

    def abrir_imagem(self) -> None:
        caminho = filedialog.askopenfilename(
            parent=self,
            filetypes=[("Imagens", "*.png *.jpg *.jpeg *.webp"), ("Todos", "*.*")],
        )
        if not caminho:
            return
        try:
            imagem, info = visuals.open_source_image(caminho)
        except visuals.VisualsError as exc:
            messagebox.showerror("Imagem rejeitada", str(exc), parent=self)
            return
        self.source = imagem
        self.source_info = info
        resumo = f"{info.format} {info.width}×{info.height} ({info.megapixels} MP)"
        if info.icc_profile:
            resumo += " · ICC"
        self.lbl_fonte.configure(text=Path(caminho).name + "\n" + resumo)
        for aviso in info.warnings:
            self.app.log.append(f"[loading] {aviso}", "aviso")
        if self.modo() == "text":
            self.var_mode.set("Imagem")
        self._ao_mudar_modo()

    def remover_imagem(self) -> None:
        self.source = None
        self.source_info = None
        self.lbl_fonte.configure(text="— sem imagem de fundo —")
        if self.modo() != "text":
            self.var_mode.set("Só Texto")
        self._ao_mudar_modo()

    # ------------------------------------------------------------------
    # composição e pré-visualização
    # ------------------------------------------------------------------

    def imagem_composta(self) -> Any:
        """Arte em 2048×2048 (ou `None` se o modo pedir imagem e não houver)."""
        try:
            return visuals.compose(
                self.modo(),
                self.source,
                title=self.var_title.get(),
                subtitle=self.var_subtitle.get(),
                status=self.var_status.get(),
                bg_color=self.var_color.get().strip() or "#160b12",
            )
        except ValueError:
            return None

    def render(self) -> None:
        self.preview = self.imagem_composta()
        self._mostrar_preview()
        self._mostrar_crops()
        com_alvo = self.preview is not None
        self.btn_injetar.state(["!disabled"] if com_alvo else ["disabled"])

    def _mostrar_preview(self) -> None:
        if self.preview is None or not self.canvas.winfo_width():
            return
        from PIL import Image, ImageDraw  # noqa: PLC0415

        imagem = self.preview.copy()
        if self.var_safe.get():
            desenho = ImageDraw.Draw(imagem, "RGBA")
            x0, y0, x1, y1 = visuals.safe_area_rect(imagem.size)
            for coord in ((x0, y0, x1, y0 + 3), (x0, y1 - 3, x1, y1), (x0, y0, x0 + 3, y1), (x1 - 3, y0, x1, y1)):
                desenho.rectangle(coord, fill=(255, 255, 255, 110))
        max_w = max(120, self.canvas.winfo_width() - 16)
        max_h = max(120, self.canvas.winfo_height() - 16)
        imagem.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        self._preview_tk = _photo(imagem)
        self.canvas.delete("all")
        self.canvas.create_image(
            self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2,
            image=self._preview_tk,
        )

    def _mostrar_crops(self) -> None:
        for widget in self._frame_crops.winfo_children():
            widget.destroy()
        self._crops_tk.clear()
        if self.preview is None:
            return
        for rotulo, recorte in visuals.aspect_crops(self.preview, thumb=96):
            self._crops_tk.append((rotulo, _photo(recorte)))
        for coluna, (rotulo, foto) in enumerate(self._crops_tk):
            ttk.Label(self._frame_crops, image=foto).grid(row=0, column=coluna, padx=6)
            ttk.Label(self._frame_crops, text=rotulo).grid(row=1, column=coluna)

    # ------------------------------------------------------------------
    # exportar / injetar
    # ------------------------------------------------------------------

    def exportar_png(self) -> None:
        if self.preview is None:
            messagebox.showwarning(
                "Exportar PNG", "componha uma arte primeiro (abra uma imagem ou use 'Só Texto').",
                parent=self,
            )
            return
        if self.app.project is not None:
            from ..paths import project_dir  # noqa: PLC0415

            inicial = project_dir(self.app.project.project_id, studio_root=self.app.studio_root) / "output"
        else:
            inicial = self.app.studio_root
        destino = filedialog.asksaveasfilename(
            parent=self,
            initialdir=str(inicial),
            initialfile="revival-loading.png",
            defaultextension=".png",
            filetypes=[("PNG", "*.png")],
        )
        if not destino:
            return
        caminho = visuals.export_png(self.preview, destino)
        self.app.log.append(f"[loading] PNG exportado: {caminho}", "info")
        messagebox.showinfo(
            "Exportado", f"Arte salva em:\n{caminho}\n\n2048 × 2048 px — nenhum APK foi tocado.",
            parent=self,
        )

    def injetar(self) -> None:
        projeto = self.app.project
        if projeto is None:
            messagebox.showwarning("Injetar", "abra um projeto primeiro (menu Projeto).", parent=self)
            return
        if self.preview is None:
            return
        alvo = projeto.output_apk or projeto.input_apk
        if not alvo or not Path(alvo).is_file():
            messagebox.showerror(
                "Injetar",
                f"APK alvo não encontrado:\n{alvo or '(nenhum)'}\n\n"
                "Gere o APK com o pipeline (menu APK) ou aponte um APK de entrada no projeto.",
                parent=self,
            )
            return
        if not messagebox.askyesno(
            "Injetar tela de loading",
            f"Injetar a arte nas texturas de loading de:\n{alvo}\n\n"
            "Um backup do APK anterior fica em work/loading-edit/backup.\n"
            "O APK é assinado de novo (assinatura diferente da oficial).",
            parent=self,
        ):
            return

        from ..paths import project_dir  # noqa: PLC0415

        pasta = project_dir(projeto.project_id, studio_root=self.app.studio_root)
        relatorio = pasta / "reports" / "loading-inject.json"
        imagem = self.preview.copy()
        self.app._submit(
            "loading-inject",
            lambda ctx: _trabalho_injetar(Path(alvo), imagem, relatorio, ctx),
            ao_concluir=self._apos_injetar,
        )

    def _apos_injetar(self, evento: Any) -> None:
        projeto = self.app.project
        if projeto is None:
            return
        relatorio = evento.result
        # O APK mudou: assinatura/verificação anteriores não valem mais
        # (plano fase 7). A injeção marca a customização como aplicada.
        invalidadas = projeto.state.invalidate_from(Stage.APK_RECONSTRUIDO)
        projeto.state.mark(Stage.CUSTOMIZACOES_APLICADAS)
        projeto.output_apk = relatorio["apk_out"]
        projeto.reports["loading_inject"] = relatorio.get("report_path") or ""
        save_project(projeto, studio_root=self.app.studio_root)
        if invalidadas:
            nomes = ", ".join(s.value for s in sorted(invalidadas, key=lambda s: s.order))
            self.app.log.append(f"[loading] etapas invalidadas (APK mudou): {nomes}", "aviso")
        self.app.log.append(
            f"[loading] injeção concluída: {relatorio['apk_out']} "
            f"({len(relatorio['bundle_report']['targets'])} textura(s))",
            "info",
        )
        self.app.refresh()


def _photo(imagem: Any) -> Any:
    from PIL import ImageTk  # noqa: PLC0415

    return ImageTk.PhotoImage(imagem)


def _trabalho_injetar(alvo: Path, imagem: Any, relatorio: Path, ctx: Any) -> dict:
    ctx.progress("loading", "injetando texturas de loading…", None)
    resultado = visuals.inject_loading_into_apk(
        alvo,
        imagem,
        alvo,  # in-place com backup automático em work/loading-edit/backup
        log=ctx.log,
        report_path=relatorio,
    )
    ctx.progress("loading", "injeção concluída e assinada", 1.0)
    return {**resultado, "report_path": str(relatorio)}
