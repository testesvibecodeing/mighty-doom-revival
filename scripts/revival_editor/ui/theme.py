"""Tema escuro DOOM do Revival Studio — espelho do site (`slayer.css`).

Os oito tokens do ``:root`` do servidor são a fonte da verdade; as cores de
widget derivam das MESMAS receitas do css, achatadas para hex sólido porque
Tk não tem canal alfa. O teste de regressão
(``tests/revival_editor/test_theme.py``) compara os tokens hex com o
``:root`` do css e impede que os dois lados divirjam.

Tk puro (``Text``, ``Listbox``, ``Menu``, ``Canvas``) pega cor via
``option_add`` no root — vale para toda a árvore de widgets criada depois de
``aplicar_tema``; widgets criados com cor explícita devem importar os tokens
daqui, nunca de hex espalhado pelo código.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, font as tkfont

__all__ = [
    "BG", "ORANGE", "GOLD", "TEXT", "MUTED", "GREEN", "RED", "LINE",
    "LINE_SOLID", "CARD", "CARD_TOP", "CARD_DARK", "FIELD", "FIELD_TEXT",
    "INPUT_BG", "BORDER_SOFT", "SELECT_BG", "DANGER_TEXT",
    "FONTE_TITULO", "FONTE_CORPO", "aplicar_tema",
]

# -- tokens 1:1 do :root (server/public/assets/css/slayer.css) -------------
BG = "#080403"                  # --bg
ORANGE = "#ff791c"              # --orange
GOLD = "#ffc34e"                # --gold
TEXT = "#f4eadf"                # --text
MUTED = "#a99a8e"               # --muted
GREEN = "#55e878"               # --green
RED = "#ff6658"                 # --red
LINE = "rgba(255,100,30,.24)"   # --line (referência; Tk não tem alpha)

# -- receitas do css achatadas sobre --bg -----------------------------------
LINE_SOLID = "#431b0a"   # --line sobre --bg (borda de card)
CARD = "#160d0a"         # .notice-item / .icon-link
CARD_TOP = "#21120c"     # início do gradiente do .card/.metric-card
CARD_DARK = "#0a0706"    # fim do gradiente / trough
FIELD = "#161312"        # botão secundário (.mini-action)
FIELD_TEXT = "#ffd59a"   # texto do secundário
INPUT_BG = "#060302"     # input: rgba(0,0,0,.28) sobre --bg
BORDER_SOFT = "#282725"  # input: rgba(255,255,255,.13) sobre --bg
SELECT_BG = "#2d1307"    # selected: rgba(255,101,28,.15) sobre --bg
DANGER_TEXT = "#ff8d7d"  # button (ação destrutiva do site)

FONTE_TITULO: tuple[str, int, str] = ("Black Ops One", 15, "bold")
FONTE_CORPO: tuple[str, int] = ("Rajdhani", 10)


def _familia_existe(root: tk.Misc, nome: str) -> bool:
    try:
        return nome in tkfont.families(root)
    except tk.TclError:  # pragma: no cover - interp em fim de vida
        return False


def aplicar_tema(root: tk.Tk) -> None:
    """Pinta a janela com a paleta DOOM do site. Idempotente.

    Chame uma vez, antes de construir os widgets. Famílias do site
    ('Black Ops One'/'Rajdhani') entram só se instaladas na máquina —
    sem elas o Tk usa a substituta do sistema e nada quebra.
    """
    titulo = FONTE_TITULO if _familia_existe(root, FONTE_TITULO[0]) else None
    corpo = FONTE_CORPO if _familia_existe(root, FONTE_CORPO[0]) else None

    root.configure(background=BG)

    # tk puro: cores de Text/Listbox/Menu/Toplevel nascem aqui.
    root.option_add("*Menu.background", CARD)
    root.option_add("*Menu.foreground", TEXT)
    root.option_add("*Menu.activeBackground", SELECT_BG)
    root.option_add("*Menu.activeForeground", TEXT)
    root.option_add("*Menu.selectColor", ORANGE)
    root.option_add("*Text.background", CARD_DARK)
    root.option_add("*Text.foreground", TEXT)
    root.option_add("*Text.insertBackground", TEXT)
    root.option_add("*Text.selectBackground", SELECT_BG)
    root.option_add("*Listbox.background", CARD_DARK)
    root.option_add("*Listbox.foreground", TEXT)
    root.option_add("*Listbox.selectBackground", SELECT_BG)
    root.option_add("*Listbox.selectForeground", TEXT)
    root.option_add("*Toplevel.background", BG)
    root.option_add("*Canvas.background", BG)

    estilo = ttk.Style(root)
    estilo.theme_use("clam")

    base: dict[str, object] = {
        "background": BG,
        "foreground": TEXT,
        "bordercolor": LINE_SOLID,
        "lightcolor": BG,
        "darkcolor": BG,
        "troughcolor": CARD_DARK,
        "selectbackground": SELECT_BG,
        "selectforeground": TEXT,
    }
    if corpo:
        base["font"] = corpo
    estilo.configure(".", **base)

    estilo.configure("TFrame", background=BG)
    estilo.configure("TLabel", background=BG, foreground=TEXT)
    estilo.configure("TSeparator", background=LINE_SOLID)

    estilo.configure(
        "TButton", background=FIELD, foreground=FIELD_TEXT,
        bordercolor=BORDER_SOFT, lightcolor=FIELD, darkcolor=FIELD,
        padding=(10, 5),
    )
    estilo.map(
        "TButton",
        background=[("pressed", CARD), ("active", CARD_TOP),
                    ("disabled", CARD_DARK)],
        lightcolor=[("active", CARD_TOP)],
        darkcolor=[("active", CARD_TOP)],
        foreground=[("disabled", MUTED)],
    )

    estilo.configure(
        "TEntry", fieldbackground=INPUT_BG, foreground=TEXT,
        bordercolor=BORDER_SOFT, insertcolor=TEXT, padding=4,
    )
    estilo.map("TEntry", bordercolor=[("focus", ORANGE)])

    estilo.configure(
        "TCombobox", fieldbackground=INPUT_BG, foreground=TEXT,
        background=FIELD, bordercolor=BORDER_SOFT, arrowcolor=ORANGE,
    )
    estilo.map(
        "TCombobox",
        fieldbackground=[("readonly", INPUT_BG), ("focus", INPUT_BG)],
        foreground=[("readonly", TEXT)],
        bordercolor=[("focus", ORANGE)],
    )
    root.option_add("*TCombobox*Listbox.background", CARD_DARK)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", SELECT_BG)

    estilo.configure("TCheckbutton", background=BG, foreground=TEXT)
    estilo.map(
        "TCheckbutton",
        background=[("active", BG)],
        indicatorcolor=[("selected", ORANGE), ("!selected", INPUT_BG)],
        foreground=[("disabled", MUTED)],
    )

    estilo.configure("TNotebook", background=BG, bordercolor=LINE_SOLID)
    estilo.configure(
        "TNotebook.Tab", background=CARD, foreground=MUTED, padding=(12, 6),
    )
    if titulo:
        estilo.configure("Heading.TLabel", font=titulo)
    estilo.map(
        "TNotebook.Tab",
        background=[("selected", CARD_TOP)],
        foreground=[("selected", ORANGE)],
    )

    estilo.configure("TLabelframe", background=BG, bordercolor=LINE_SOLID)
    estilo.configure(
        "TLabelframe.Label", background=BG, foreground=ORANGE,
        **({"font": titulo} if titulo else {}),
    )

    estilo.configure(
        "TProgressbar", troughcolor=CARD_DARK, background=ORANGE,
        bordercolor=LINE_SOLID, lightcolor=ORANGE, darkcolor=ORANGE,
    )

    estilo.configure(
        "Treeview", background=CARD_DARK, foreground=TEXT,
        fieldbackground=CARD_DARK, bordercolor=BORDER_SOFT, rowheight=22,
    )
    estilo.configure(
        "Treeview.Heading", background=CARD, foreground=GOLD,
        bordercolor=LINE_SOLID, relief="flat",
    )
    estilo.map(
        "Treeview",
        background=[("selected", SELECT_BG)],
        foreground=[("selected", TEXT)],
    )

    estilo.configure(
        "TScrollbar", troughcolor=CARD_DARK, background=FIELD,
        bordercolor=CARD_DARK, lightcolor=FIELD, darkcolor=FIELD,
        arrowcolor=MUTED,
    )
    estilo.map(
        "TScrollbar",
        background=[("active", CARD_TOP), ("pressed", CARD)],
    )
