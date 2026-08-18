#!/usr/bin/env python3
"""Launcher do Revival Studio (janela Tkinter).

Regras herdadas do plano (§6 e §9.2):

- o launcher **nunca** chama um wrapper `.bat`/`.sh` — os wrappers é que
  encaminham para cá; chamar de volta seria recursão (§9.2);
- sem argumentos: abre a janela. Este launcher não é caminho headless — CI e
  VPS continuam usando os scripts Python diretamente.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def main(argv: list[str] | None = None) -> int:
    try:
        import tkinter  # noqa: F401 - falha clara quando falta o Tcl/Tk
    except ImportError:
        print(
            "ERRO: Tkinter/Tcl não está disponível nesta instalação do Python.\n"
            "  Windows: reinstale o Python marcando 'tcl/tk and IDLE'.\n"
            "  Linux: instale python3-tk (Debian/Ubuntu) ou tkinter (Fedora).",
            file=sys.stderr,
        )
        return 1

    from revival_editor.ui.app import main as ui_main

    return ui_main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
