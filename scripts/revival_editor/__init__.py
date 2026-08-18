"""Revival Studio — camada de domínio do editor desktop.

Este pacote existe para que a GUI (Tkinter) chame **a mesma implementação** que
os CLIs do patcher já usam, em vez de duplicar lógica crítica dentro de widgets.

Regras do pacote (PLANO-REVIVAL-STUDIO-100-POR-CENTO, fases 1 e 2):

- nada aqui importa `tkinter`; a thread de trabalho nunca toca widget;
- nada aqui chama `sys.exit()` — quem traduz exceção em exit code é o CLI;
- todo resultado é serializável (dataclass -> dict -> JSON sanitizado).

O launcher é `scripts/revival_studio.py`. Este pacote deliberadamente **não** se
chama `revival_studio` para não colidir com o módulo do launcher no import.
"""
from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
