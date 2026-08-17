#!/usr/bin/env python3
"""Small local editor for an original Revival loading screen.

This tool edits only user-supplied/local images and exports a PNG. It does not
open, download, or publish APKs and does not replace Unity bundle textures yet.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
except ImportError as exc:  # pragma: no cover - friendly CLI failure
    raise SystemExit("Instale Pillow: python -m pip install Pillow") from exc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SIZE = (1080, 1920)


def font(size: int, bold: bool = False):
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


class LoadingEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Revival — Editor de tela de loading")
        self.geometry("1180x820")
        self.minsize(900, 620)
        self.source = None
        self.preview_image = None
        self.preview_tk = None
        self.vars = {name: tk.StringVar(value=value) for name, value in {
            "title": "REVIVAL",
            "subtitle": "COMMUNITY SERVER",
            "status": "Connecting to Revival Server...",
            "progress": "93",
            "color": "#160b12",
        }.items()}
        self.build_ui()
        self.render()

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
        preview = ttk.LabelFrame(main, text="Pré-visualização", padding=8)
        preview.grid(row=0, column=1, sticky="nsew")
        preview.rowconfigure(0, weight=1)
        preview.columnconfigure(0, weight=1)

        fields = [
            ("Título", "title"),
            ("Subtítulo", "subtitle"),
            ("Mensagem", "status"),
            ("Progresso (0-100)", "progress"),
            ("Cor de fundo", "color"),
        ]
        for row, (label, key) in enumerate(fields):
            ttk.Label(controls, text=label).grid(row=row * 2, column=0, sticky="w", pady=(4, 2))
            entry = ttk.Entry(controls, textvariable=self.vars[key], width=32)
            entry.grid(row=row * 2 + 1, column=0, sticky="ew", pady=(0, 8))
            entry.bind("<KeyRelease>", lambda _event: self.render())

        ttk.Button(controls, text="Abrir imagem de fundo…", command=self.open_image).grid(sticky="ew", pady=(10, 4))
        ttk.Button(controls, text="Usar fundo abstrato", command=self.clear_image).grid(sticky="ew", pady=4)
        ttk.Separator(controls).grid(sticky="ew", pady=12)
        ttk.Button(controls, text="Exportar PNG…", command=self.export).grid(sticky="ew", pady=4)
        ttk.Label(controls, text="Saída recomendada: 1080 × 1920 px\nUse uma arte própria ou licenciada.", foreground="#666").grid(sticky="w", pady=(18, 0))

        self.canvas = tk.Canvas(preview, background="#111", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _event: self.show_preview())
        self.statusbar = ttk.Label(self, text="Pronto", anchor="w", padding=(12, 5))
        self.statusbar.grid(row=1, column=0, sticky="ew")

    def open_image(self):
        path = filedialog.askopenfilename(filetypes=[("Imagens", "*.png *.jpg *.jpeg *.webp"), ("Todos", "*.*")])
        if not path:
            return
        try:
            self.source = Image.open(path).convert("RGB")
            self.statusbar.config(text=f"Imagem aberta: {Path(path).name}")
            self.render()
        except Exception as exc:
            messagebox.showerror("Imagem inválida", str(exc))

    def clear_image(self):
        self.source = None
        self.statusbar.config(text="Fundo abstrato selecionado")
        self.render()

    def render(self):
        width, height = DEFAULT_SIZE
        try:
            base_color = self.vars["color"].get().strip() or "#160b12"
            image = Image.new("RGB", DEFAULT_SIZE, base_color)
        except ValueError:
            image = Image.new("RGB", DEFAULT_SIZE, "#160b12")
        draw = ImageDraw.Draw(image, "RGBA")

        if self.source is not None:
            background = self.source.copy()
            background.thumbnail(DEFAULT_SIZE, Image.Resampling.LANCZOS)
            x = (width - background.width) // 2
            y = (height - background.height) // 2
            image.paste(background, (x, y))

        # Original atmospheric treatment: gradients, glow, and geometric lines.
        for y in range(height):
            alpha = int(120 * y / height)
            draw.line((0, y, width, y), fill=(3, 2, 8, alpha))
        for x in range(-height, width, 120):
            draw.line((width // 2, height // 2, x, height), fill=(255, 74, 21, 28), width=5)
        draw.ellipse((width // 2 - 360, height // 2 - 420, width // 2 + 360, height // 2 + 300), fill=(255, 93, 24, 30))

        title_font = font(150, True)
        subtitle_font = font(38, True)
        status_font = font(30)
        title = self.vars["title"].get().upper()[:24]
        subtitle = self.vars["subtitle"].get().upper()[:40]
        status = self.vars["status"].get()[:70]
        draw.text((width // 2, 560), title, font=title_font, anchor="mm", fill="#ffd34e", stroke_width=3, stroke_fill="#a92818")
        draw.text((width // 2, 715), subtitle, font=subtitle_font, anchor="mm", fill="#ff7540")
        draw.text((width // 2, 1640), status, font=status_font, anchor="mm", fill="#f6e8d1")

        try:
            progress = max(0, min(100, int(self.vars["progress"].get())))
        except ValueError:
            progress = 0
        bar = (170, 1710, 910, 1780)
        draw.rounded_rectangle(bar, radius=18, fill="#09090d", outline="#7e6b56", width=5)
        inner = (bar[0] + 14, bar[1] + 14, bar[0] + 14 + int((bar[2] - bar[0] - 28) * progress / 100), bar[3] - 14)
        draw.rounded_rectangle(inner, radius=10, fill="#ff7a18")
        draw.text((width // 2, 1825), f"{progress}%", font=font(28, True), anchor="mm", fill="#ffe8bd")
        self.preview_image = image
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
        self.canvas.create_image(self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2, image=self.preview_tk)

    def export(self):
        if self.preview_image is None:
            return
        path = filedialog.asksaveasfilename(initialdir=str(ROOT / "output"), initialfile="revival-loading.png", defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not path:
            return
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.preview_image.save(path, "PNG", optimize=True)
        self.statusbar.config(text=f"Exportado: {path}")
        messagebox.showinfo("Exportado", f"Imagem criada em:\n{path}\n\nDimensões: 1080 × 1920 px")


if __name__ == "__main__":
    LoadingEditor().mainloop()
