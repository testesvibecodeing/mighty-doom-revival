#!/usr/bin/env python3
"""Regressão do tema DOOM do Revival Studio (espelho do site).

O tema (`revival_editor.ui.theme`) é uma tradução de Tk para o `:root` do
`server/public/assets/css/slayer.css`. Se um dos dois lados mudar sozinho, o
site e o Studio deixam de ser a mesma identidade visual — este teste impede
a divergência comparando token a token.

Execução: python tests/revival_editor/test_theme.py
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - ambiente sem Tcl/Tk
    tk = None

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from revival_editor.ui import theme  # noqa: E402

CSS = Path(__file__).resolve().parent.parent.parent / "server" / "public" / "assets" / "css" / "slayer.css"

# token do :root -> constante do tema
HEX_TOKENS = {
    "--bg": "BG",
    "--orange": "ORANGE",
    "--gold": "GOLD",
    "--text": "TEXT",
    "--muted": "MUTED",
    "--green": "GREEN",
    "--red": "RED",
}


def _root_do_css() -> dict[str, str]:
    texto = CSS.read_text(encoding="utf-8")
    bloco = re.search(r":root\{([^}]*)\}", texto)
    assert bloco, ":root não encontrado no slayer.css"
    variaveis: dict[str, str] = {}
    for par in bloco.group(1).split(";"):
        if ":" in par:
            nome, valor = par.split(":", 1)
            variaveis[nome.strip()] = valor.strip()
    return variaveis


class TestTokensIguaisAoSite(unittest.TestCase):
    """Cada token hex do :root existe no tema com o MESMO valor."""

    def setUp(self) -> None:
        self.css = _root_do_css()

    def test_todos_os_tokens_hex_estao_no_tema(self) -> None:
        for token, constante in HEX_TOKENS.items():
            with self.subTest(token=token):
                self.assertEqual(self.css.get(token), getattr(theme, constante))

    def test_variavel_line_e_referenciada(self) -> None:
        """--line é rgba (sem alpha em Tk), mas o tema carrega o valor bruto."""
        self.assertEqual(self.css.get("--line"), theme.LINE)

    def test_derivadas_sao_hex_validos(self) -> None:
        for nome in ("LINE_SOLID", "CARD", "CARD_TOP", "CARD_DARK", "FIELD",
                     "FIELD_TEXT", "INPUT_BG", "BORDER_SOFT", "SELECT_BG",
                     "DANGER_TEXT"):
            with self.subTest(constante=nome):
                self.assertRegex(getattr(theme, nome), r"^#[0-9a-f]{6}$")


@unittest.skipUnless(tk, "sem Tkinter nesta máquina")
class TestAplicarTema(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self) -> None:
        self.root.destroy()

    def test_pinta_a_janela_com_o_bg_do_site(self) -> None:
        theme.aplicar_tema(self.root)
        self.assertEqual(str(self.root.cget("background")).lower(), theme.BG)

    def test_widgets_ttk_nascem_escuros(self) -> None:
        from tkinter import ttk

        theme.aplicar_tema(self.root)
        estilo = ttk.Style(self.root)
        self.assertEqual(estilo.lookup("TFrame", "background").lower(), theme.BG)
        self.assertEqual(estilo.lookup("TLabel", "background").lower(), theme.BG)
        # botão secundário do site: fundo #161312, texto #ffd59a
        self.assertEqual(estilo.lookup("TButton", "background").lower(), theme.FIELD)
        self.assertEqual(estilo.lookup("TButton", "foreground").lower(), theme.FIELD_TEXT)

    def test_option_add_alcancam_o_menu(self) -> None:
        theme.aplicar_tema(self.root)
        menu = tk.Menu(self.root)
        try:
            self.assertEqual(str(menu.cget("background")).lower(), theme.CARD)
            self.assertEqual(str(menu.cget("activebackground")).lower(), theme.SELECT_BG)
        finally:
            menu.destroy()

    def test_e_idempotente(self) -> None:
        theme.aplicar_tema(self.root)
        theme.aplicar_tema(self.root)  # não pode levantar nem reverter nada
        self.assertEqual(str(self.root.cget("background")).lower(), theme.BG)


if __name__ == "__main__":
    unittest.main(verbosity=2)
