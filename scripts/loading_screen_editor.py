#!/usr/bin/env python3
"""Editor local da tela de loading do Mighty DOOM Revival.

Compõe a arte (imagem, imagem com texto ou só texto), pré-visualiza em
2048x2048 — o tamanho real da textura — e injeta no APK sem desmontá-lo:
apenas as texturas de loading dentro do bundle Addressables são trocadas,
todo o resto do APK é copiado byte a byte e re-assinado.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageTk
except ImportError as exc:  # pragma: no cover - friendly CLI failure
    raise SystemExit("Instale Pillow: python -m pip install Pillow") from exc

from inject_loading_screen import (
    TEXTURE_SIZE,
    compose_loading_image,
    default_apk_in,
    font,
    inject_loading_screen,
)

ROOT = Path(__file__).resolve().parents[1]

MODE_IMAGE = "Imagem"
MODE_IMAGE_TEXT = "Imagem + Texto"
MODE_TEXT = "Só Texto"
MODES = (MODE_IMAGE, MODE_IMAGE_TEXT, MODE_TEXT)


class LoadingEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Revival — Editor de tela de loading")
        self.geometry("1180x820")
        self.minsize(900, 620)
        self.source = None
        self.preview_image = None
        self.preview_tk = None
        self.injecting = False
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.vars = {name: tk.StringVar(value=value) for name, value in {
            "mode": MODE_IMAGE_TEXT,
            "title": "REVIVAL",
            "subtitle": "COMMUNITY SERVER",
            "status": "Connecting to Revival Server...",
            "color": "#160b12",
        }.items()}
        self.build_ui()
        self.render()
        self.after(200, self.drain_log_queue)

    def build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)
        main = ttk.Frame(self, padding=12)
        main.grid(sticky="nsew")
        main.columnconfigure(0, weight=0)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        controls = ttk.LabelFrame(main, text="Configuração", padding=12)
        controls.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        preview = ttk.LabelFrame(main, text="Pré-visualização (2048 × 2048)", padding=8)
        preview.grid(row=0, column=1, sticky="nsew")
        preview.rowconfigure(0, weight=1)
        preview.columnconfigure(0, weight=1)

        ttk.Label(controls, text="Modo").grid(row=0, column=0, sticky="w", pady=(4, 2))
        mode_box = ttk.Combobox(controls, textvariable=self.vars["mode"], values=MODES,
                                state="readonly", width=30)
        mode_box.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        mode_box.bind("<<ComboboxSelected>>", lambda _event: self.on_mode_change())

        self.text_fields = []
        for row, (label, key) in enumerate([
            ("Título", "title"),
            ("Subtítulo", "subtitle"),
            ("Mensagem", "status"),
        ]):
            ttk.Label(controls, text=label).grid(
                row=row * 2 + 2, column=0, sticky="w", pady=(4, 2))
            entry = ttk.Entry(controls, textvariable=self.vars[key], width=32)
            entry.grid(row=row * 2 + 3, column=0, sticky="ew", pady=(0, 8))
            entry.bind("<KeyRelease>", lambda _event: self.render())
            self.text_fields.append(entry)

        self.color_label = ttk.Label(controls, text="Cor de fundo (só texto)")
        self.color_label.grid(row=8, column=0, sticky="w", pady=(4, 2))
        self.color_entry = ttk.Entry(controls, textvariable=self.vars["color"], width=32)
        self.color_entry.grid(row=9, column=0, sticky="ew", pady=(0, 8))
        self.color_entry.bind("<KeyRelease>", lambda _event: self.render())

        ttk.Button(controls, text="Abrir imagem de fundo…", command=self.open_image).grid(
            sticky="ew", pady=(10, 4))
        ttk.Button(controls, text="Remover imagem", command=self.clear_image).grid(
            sticky="ew", pady=4)
        ttk.Separator(controls).grid(sticky="ew", pady=12)
        self.inject_button = ttk.Button(controls, text="Injetar no APK…", command=self.inject)
        self.inject_button.grid(sticky="ew", pady=4)
        ttk.Button(controls, text="Exportar PNG…", command=self.export).grid(sticky="ew", pady=4)
        ttk.Label(controls, text=(
            "A arte é injetada em 2048 × 2048 nas texturas de loading\n"
            "do APK; o resto do APK não é alterado (só re-assinado).\n"
            "Use uma arte própria ou licenciada."
        ), foreground="#666").grid(sticky="w", pady=(14, 0))

        self.canvas = tk.Canvas(preview, background="#111", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _event: self.show_preview())
        self.statusbar = ttk.Label(self, text="Pronto", anchor="w", padding=(12, 5))
        self.statusbar.grid(row=1, column=0, sticky="ew")
        self.on_mode_change()

    def current_mode(self) -> str:
        return self.vars["mode"].get()

    def on_mode_change(self):
        mode = self.current_mode()
        text_state = "normal" if mode in (MODE_IMAGE_TEXT, MODE_TEXT) else "disabled"
        color_state = "normal" if mode == MODE_TEXT else "disabled"
        for entry in self.text_fields:
            entry.config(state=text_state)
        self.color_entry.config(state=color_state)
        self.render()

    def open_image(self):
        path = filedialog.askopenfilename(
            filetypes=[("Imagens", "*.png *.jpg *.jpeg *.webp"), ("Todos", "*.*")])
        if not path:
            return
        try:
            self.source = Image.open(path)
            self.source.load()
            self.statusbar.config(text=f"Imagem aberta: {Path(path).name}")
            if self.current_mode() == MODE_TEXT:
                self.vars["mode"].set(MODE_IMAGE)
            self.on_mode_change()
        except Exception as exc:
            messagebox.showerror("Imagem inválida", str(exc))

    def clear_image(self):
        self.source = None
        self.statusbar.config(text="Imagem removida")
        if self.current_mode() != MODE_TEXT:
            self.vars["mode"].set(MODE_TEXT)
        self.on_mode_change()

    def compose(self) -> Image.Image:
        mode_map = {MODE_IMAGE: "image", MODE_IMAGE_TEXT: "image+text", MODE_TEXT: "text"}
        return compose_loading_image(
            mode=mode_map[self.current_mode()],
            background=self.source,
            title=self.vars["title"].get(),
            subtitle=self.vars["subtitle"].get(),
            status=self.vars["status"].get(),
            bg_color=self.vars["color"].get().strip() or "#160b12",
            size=TEXTURE_SIZE,
        )

    def render(self):
        try:
            self.preview_image = self.compose()
        except ValueError:
            # modo de imagem sem imagem aberta: pré-visualiza um aviso
            # em vez de quebrar; a injeção segue bloqueada no botão.
            from PIL import ImageDraw
            placeholder = Image.new("RGB", TEXTURE_SIZE, "#0d0d10")
            draw = ImageDraw.Draw(placeholder)
            draw.text((TEXTURE_SIZE[0] // 2, TEXTURE_SIZE[1] // 2),
                      "Abra uma imagem de fundo\nou mude para o modo 'Só Texto'",
                      font=font(64, True), anchor="mm", fill="#8a8a96", spacing=40)
            self.preview_image = placeholder
        self.show_preview()

    def show_preview(self):
        if self.preview_image is None or not self.canvas.winfo_width():
            return
        image = self.preview_image.copy()
        max_w = max(120, self.canvas.winfo_width() - 20)
        max_h = max(120, self.canvas.winfo_height() - 20)
        image.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        self.preview_tk = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2,
                                 image=self.preview_tk)

    def export(self):
        if self.preview_image is None:
            return
        path = filedialog.asksaveasfilename(
            initialdir=str(ROOT / "output"), initialfile="revival-loading.png",
            defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not path:
            return
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.preview_image.save(path, "PNG", optimize=True)
        self.statusbar.config(text=f"Exportado: {path}")
        messagebox.showinfo("Exportado", f"Imagem criada em:\n{path}\n\nDimensões: 2048 × 2048 px")

    # ------------------------------------------------------------------
    # Injeção no APK
    # ------------------------------------------------------------------

    def inject(self):
        if self.injecting:
            return
        mode = self.current_mode()
        if mode in (MODE_IMAGE, MODE_IMAGE_TEXT) and self.source is None:
            messagebox.showwarning(
                "Imagem obrigatória",
                f"O modo '{mode}' precisa de uma imagem de fundo.\n"
                "Abra uma imagem ou mude para o modo 'Só Texto'.")
            return

        default_in = default_apk_in()
        apk_in = filedialog.askopenfilename(
            title="APK de entrada (o atual é preservado com backup)",
            initialdir=str(default_in.parent), initialfile=default_in.name,
            filetypes=[("APK", "*.apk"), ("Todos", "*.*")])
        if not apk_in:
            return
        apk_out = filedialog.asksaveasfilename(
            title="APK de saída (padrão: substitui o próprio APK de entrada)",
            initialdir=str(Path(apk_in).parent), initialfile=Path(apk_in).name,
            defaultextension=".apk", filetypes=[("APK", "*.apk")])
        if not apk_out:
            return

        image = self.preview_image.copy()
        self.injecting = True
        self.inject_button.config(state="disabled")
        self.statusbar.config(text="Injetando no APK… (veja a janela de progresso)")

        log_window = tk.Toplevel(self)
        log_window.title("Injeção da tela de loading")
        log_window.geometry("720x420")
        log_box = tk.Text(log_window, wrap="word", height=20)
        log_box.pack(fill="both", expand=True, padx=8, pady=8)
        log_box.config(state="disabled")

        def log(message: str):
            self.log_queue.put(message)

        def worker():
            try:
                report = inject_loading_screen(
                    Path(apk_in), image, Path(apk_out), log=log)
                log(f"__DONE__{report['apk_out']}")
            except Exception as exc:  # noqa: BLE001 - relatado na GUI
                log(f"__FAIL__{exc}")

        threading.Thread(target=worker, daemon=True).start()
        self._log_box = log_box

    def drain_log_queue(self):
        try:
            while True:
                message = self.log_queue.get_nowait()
                if message.startswith("__DONE__"):
                    out = message[len("__DONE__"):]
                    self._finish_inject(ok=True, out=out)
                elif message.startswith("__FAIL__"):
                    self._finish_inject(ok=False, out=message[len("__FAIL__"):])
                else:
                    self._append_log(message)
        except queue.Empty:
            pass
        self.after(200, self.drain_log_queue)

    def _append_log(self, message: str):
        box = getattr(self, "_log_box", None)
        if box is None or not box.winfo_exists():
            print(message)
            return
        box.config(state="normal")
        box.insert("end", message + "\n")
        box.see("end")
        box.config(state="disabled")

    def _finish_inject(self, ok: bool, out: str):
        self.injecting = False
        self.inject_button.config(state="normal")
        self._append_log("Concluído." if ok else "Falhou.")
        if ok:
            self.statusbar.config(text=f"APK atualizado: {out}")
            messagebox.showinfo(
                "Injeção concluída",
                "Tela de loading injetada e APK re-assinado com sucesso:\n"
                f"{out}\n\n"
                "A assinatura é diferente da oficial. Se a versão oficial estiver\n"
                "instalada, desinstale-a antes de instalar este APK.")
        else:
            self.statusbar.config(text="Falha na injeção — o APK de destino não foi alterado")
            messagebox.showerror("Falha na injeção", out)


if __name__ == "__main__":
    LoadingEditor().mainloop()
