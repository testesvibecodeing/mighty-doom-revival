#!/usr/bin/env python3
"""Ponto de partida dos testes — direto do Python, sem wrapper.

Descobre e executa TODA a suíte de regressão do projeto na ordem estável do
gate (`scripts/verify_everything.py`):

    python run_tests.py              # tudo (scripts/ + tests/)
    python run_tests.py tests/revival_editor/test_server.py scripts/test_patch_apk.py
                                     # só os arquivos pedidos

Cada arquivo roda como processo próprio (`python <arquivo>`) porque as suítes
de scripts/ e tests/ resolvem seus imports manipulando sys.path — descoberta
em processo único não é confiável aqui. Saída: uma linha por arquivo com
[OK]/[FALHOU] e o total no fim; exit 0 só quando tudo passa.

O gate completo (npm + registro + coerência) continua sendo
`python scripts/verify_everything.py` — este arquivo é o caminho puro e
direto dos testes Python.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def descobrir() -> list[Path]:
    """Suíte completa: testes do patcher (scripts/) + do editor (tests/)."""
    arquivos: list[Path] = []
    arquivos.extend(sorted((ROOT / "scripts").glob("test_*.py")))
    arquivos.extend(sorted((ROOT / "tests").rglob("test_*.py")))
    return arquivos


def rodar(caminho: Path) -> tuple[int, str]:
    proc = subprocess.run(  # noqa: S603 - sys.executable, arquivo do repositório
        [sys.executable, str(caminho)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    saida = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode, saida


def main(argv: list[str]) -> int:
    if argv:
        alvos = []
        for nome in argv:
            caminho = Path(nome)
            if not caminho.is_file():
                print(f"[FALHOU] {nome}: arquivo de teste ausente")
                return 2
            alvos.append(caminho)
    else:
        alvos = descobrir()

    print(f"== Testes Python direto — {len(alvos)} arquivo(s) ==\n")
    falhas: list[str] = []
    inicio = time.monotonic()
    for caminho in alvos:
        relativo = caminho.relative_to(ROOT)
        codigo, saida = rodar(caminho)
        if codigo == 0:
            # unittest imprime "Ran N tests" na penúltima linha — mostra o N
            resumo = ""
            for linha in saida.splitlines():
                if linha.startswith("Ran "):
                    resumo = f" ({linha.strip()})"
            print(f"  [OK]   {relativo}{resumo}")
        else:
            print(f"  [FALHOU] {relativo} — exit {codigo}")
            for linha in saida.splitlines()[-8:]:
                print("    " + linha)
            falhas.append(str(relativo))

    duracao = time.monotonic() - inicio
    print(f"\n== {len(alvos) - len(falhas)}/{len(alvos)} arquivos OK em {duracao:.1f}s ==")
    if falhas:
        print("Falhas:")
        for nome in falhas:
            print(f"  - {nome}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
