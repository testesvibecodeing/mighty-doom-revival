"""Painel de log do Revival Studio (fase 2: *"log com localizar, copiar, salvar"*).

O texto entra **já mascarado** — quem publica é `JobContext.log`, que aplica
`mask_secrets` na origem. O painel não tenta mascarar de novo (mascarar duas
vezes é inócuo, mas custa CPU em log de subprocesso volumoso).

Teto de linhas: log de apktool/build pode passar de dezenas de milhares de
linhas; um `tk.Text` sem teto come memória e congela o loop de eventos. Ao
passar de `MAX_LINHAS`, as linhas mais antigas saem — o arquivo completo em
`logs/` continua íntegro (gravado pelo runner).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from pathlib import Path

from .theme import CARD, CARD_DARK, GOLD, MUTED, RED, TEXT

__all__ = ["LogPanel"]

#: Cores por fluxo de origem do evento (LogEvent.stream). As de leitura humana
#: (hashes, rotas, exit codes) ficam na cor padrão — diagnóstico depende delas.
#: Paleta: tokens DOOM do tema (muted/ouro/vermelho do slayer.css).
_STREAM_STYLE: dict[str, dict[str, str]] = {
    "info": {},
    "cmd": {"foreground": MUTED},
    "proc": {},
    "aviso": {"foreground": GOLD},
    "erro": {"foreground": RED},
}


class LogPanel(ttk.Frame):
    """Área de log somente-leitura com teto de linhas, cópia e salvamento."""

    MAX_LINHAS = 5000

    def __init__(self, master: tk.Misc, **kwargs) -> None:
        super().__init__(master, **kwargs)

        barra = ttk.Frame(self)
        barra.pack(side="top", fill="x", pady=(0, 2))
        self._botao_salvar = ttk.Button(barra, text="Salvar…", command=self._salvar_dialogo)
        self._botao_salvar.pack(side="left")
        self._botao_limpar = ttk.Button(barra, text="Limpar", command=self.clear)
        self._botao_limpar.pack(side="left", padx=(6, 0))
        self._contador = ttk.Label(barra, text="0 linhas")
        self._contador.pack(side="right")

        corpo = ttk.Frame(self)
        corpo.pack(side="top", fill="both", expand=True)

        self.text = tk.Text(
            corpo,
            wrap="none",
            state="disabled",
            height=12,
            font=("Consolas", 9),
            background=CARD_DARK,
            foreground=TEXT,
            insertbackground=TEXT,
            selectbackground=CARD,
        )
        for stream, estilo in _STREAM_STYLE.items():
            self.text.tag_configure(stream, **estilo)

        rolagem_y = ttk.Scrollbar(corpo, orient="vertical", command=self.text.yview)
        rolagem_x = ttk.Scrollbar(corpo, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=rolagem_y.set, xscrollcommand=rolagem_x.set)

        self.text.grid(row=0, column=0, sticky="nsew")
        rolagem_y.grid(row=0, column=1, sticky="ns")
        rolagem_x.grid(row=1, column=0, sticky="ew")
        corpo.rowconfigure(0, weight=1)
        corpo.columnconfigure(0, weight=1)

    # ------------------------------------------------------------------

    def append(self, line: str, stream: str = "info") -> None:
        """Adiciona uma linha (sem quebrar a thread da UI — chame só nela)."""
        self.text.configure(state="normal")
        self.text.insert("end", line.rstrip("\n") + "\n", stream if stream in _STREAM_STYLE else "info")
        excedente = int(self.text.index("end-1c").split(".")[0]) - self.MAX_LINHAS
        if excedente > 0:
            # remove `excedente` linhas inteiras do começo (1.0 até a linha seguinte
            # à última removida — delete(a, a) seria no-op)
            self.text.delete("1.0", f"{excedente + 1}.0")
        self.text.configure(state="disabled")
        self.text.see("end")
        self._atualizar_contador()

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self._atualizar_contador()

    @property
    def line_count(self) -> int:
        if not self.text.index("end-1c") or self.text.index("end-1c") == "1.0":
            return 0
        return int(self.text.index("end-1c").split(".")[0])

    @property
    def content(self) -> str:
        return self.text.get("1.0", "end-1c")

    def save_to_file(self, path: Path | str) -> int:
        """Grava o conteúdo visível em `path`. Devolve o nº de linhas."""
        destino = Path(path)
        destino.parent.mkdir(parents=True, exist_ok=True)
        conteudo = self.content
        destino.write_text(conteudo, encoding="utf-8")
        return conteudo.count("\n") + (0 if not conteudo else 0)

    # ------------------------------------------------------------------

    def _salvar_dialogo(self) -> None:
        from tkinter import filedialog

        destino = filedialog.asksaveasfilename(
            parent=self,
            title="Salvar log",
            defaultextension=".log",
            filetypes=[("Log", "*.log"), ("Texto", "*.txt"), ("Todos", "*.*")],
        )
        if destino:
            self.save_to_file(destino)

    def _atualizar_contador(self) -> None:
        self._contador.configure(text=f"{self.line_count} linhas")
