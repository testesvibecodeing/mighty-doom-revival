#!/usr/bin/env python3
"""Resolvedor de Java para os orquestradores headless (fase 3 do plano).

O plano manda *"corrigir os orquestradores antigos para consumirem o mesmo
resolvedor de Java, sem depender cegamente do PATH"*. Este CLI é a ponte:
`patch-apk.*` e `setup-patcher-tools.*` chamam aqui e recebem o mesmo Java que
o Revival Studio usaria — ordem idêntica à de `revival_editor.toolchain`:

1. escolha explícita (parâmetro do Studio ou variável `REVIVAL_JAVA`);
2. o JRE 17 embarcado em `.tools/jre17/`;
3. `PATH` — e **só** se for 17+.

Contrato:
- stdout: caminho absoluto do java (uma linha) — exit 0;
- stderr: instrução acionável (o `detail` do resolvedor) — exit 3.

O caminho impresso nunca é versão < 17: o resolvedor recusa antes.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from revival_editor.toolchain import resolve_java  # noqa: E402


def main() -> int:
    status = resolve_java()
    if status.ok and status.path:
        print(status.path)
        return 0
    print(status.detail, file=sys.stderr)
    return 3


if __name__ == "__main__":
    sys.exit(main())
