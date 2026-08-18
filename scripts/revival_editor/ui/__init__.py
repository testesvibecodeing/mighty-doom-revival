"""Camada Tkinter do Revival Studio.

Só este subpacote importa `tkinter`. A thread de trabalho (runner) publica
eventos na fila; quem mexe em widget é exclusivamente a thread da UI, no
bombeamento `after()` de `app.py` (padrão herdado de loading_screen_editor.py).
"""
