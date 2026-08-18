"""Validação e isolamento de caminhos do Revival Studio.

Motivo de existir: o pipeline apaga e recria o workspace de trabalho
(`work/revival-studio/<id>/decoded`). Um `rmtree` com caminho errado destrói a
árvore do usuário. O plano (fase 6) exige: *"antes de limpar/recriar workspace,
resolver o caminho absoluto e provar que está dentro de
`work/revival-studio/<id>`"*.

Este módulo é a prova. Nenhum código do editor pode chamar `rmtree` direto.

Nota de Windows: `Path.resolve()` normaliza maiúsculas/minúsculas, `..`,
symlinks e junctions, que é exatamente o que precisamos antes de comparar. A
comparação usa `os.path.commonpath` sobre caminhos já resolvidos — `str.startswith`
aceitaria `/work/revival-studio-malicioso` como se estivesse dentro de
`/work/revival-studio`.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

__all__ = [
    "PathError",
    "PathEscapeError",
    "InvalidProjectIdError",
    "PROJECT_ID_PATTERN",
    "REPO_ROOT",
    "STUDIO_ROOT",
    "validate_project_id",
    "is_within",
    "ensure_within",
    "project_dir",
    "reset_directory",
    "ensure_dir",
]


class PathError(ValueError):
    """Base das falhas de caminho deste módulo."""


class PathEscapeError(PathError):
    """O caminho candidato caiu fora da base permitida."""


class InvalidProjectIdError(PathError):
    """O identificador de projeto não é um slug seguro."""


#: Slug de projeto: minúsculas, dígitos e hífen. Sem ponto, sem barra, sem
#: espaço — para nunca virar `..` nem caminho absoluto ao ser concatenado.
PROJECT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

#: Raiz do repositório (…/scripts/revival_editor/paths.py -> …/).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: Todo artefato do editor vive aqui. `work/` está no .gitignore.
STUDIO_ROOT = REPO_ROOT / "work" / "revival-studio"

#: Nomes reservados do Windows: viram dispositivo, não arquivo.
_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def validate_project_id(project_id: str) -> str:
    """Devolve o id se for um slug seguro; senão levanta InvalidProjectIdError."""
    if not isinstance(project_id, str):
        raise InvalidProjectIdError(f"id de projeto deve ser str, veio {type(project_id).__name__}")
    if not PROJECT_ID_PATTERN.match(project_id):
        raise InvalidProjectIdError(
            f"id de projeto inválido: {project_id!r}. "
            "Use minúsculas, dígitos e hífen (1-64 caracteres, começando por letra ou dígito)."
        )
    if project_id in _WINDOWS_RESERVED:
        raise InvalidProjectIdError(f"id de projeto reservado pelo Windows: {project_id!r}")
    return project_id


def _resolved(path: Path | str) -> Path:
    """Absolutiza e normaliza sem exigir que o caminho exista."""
    return Path(path).expanduser().resolve()


def is_within(base: Path | str, candidate: Path | str) -> bool:
    """True se `candidate` estiver dentro de `base` (ou for a própria base).

    Ambos são resolvidos antes da comparação, então `..`, symlink, junction e
    diferença de caixa no Windows são tratados.
    """
    base_r = _resolved(base)
    cand_r = _resolved(candidate)
    try:
        # commonpath levanta ValueError quando os caminhos estão em drives
        # diferentes (C: vs D:) — que é justamente "fora da base".
        return os.path.commonpath([str(base_r), str(cand_r)]) == str(base_r)
    except ValueError:
        return False


def ensure_within(base: Path | str, candidate: Path | str, *, what: str = "caminho") -> Path:
    """Devolve `candidate` resolvido, provando que está dentro de `base`.

    Levanta PathEscapeError caso contrário. Use esta função antes de qualquer
    escrita, remoção ou recriação de diretório.
    """
    base_r = _resolved(base)
    cand_r = _resolved(candidate)
    if not is_within(base_r, cand_r):
        raise PathEscapeError(
            f"{what} fora da área permitida.\n"
            f"  permitido: {base_r}\n"
            f"  recebido:  {cand_r}"
        )
    return cand_r


def project_dir(project_id: str, *, studio_root: Path | None = None) -> Path:
    """Diretório do projeto: `work/revival-studio/<id>` (resolvido e provado)."""
    validate_project_id(project_id)
    root = _resolved(studio_root or STUDIO_ROOT)
    return ensure_within(root, root / project_id, what="diretório do projeto")


def ensure_dir(base: Path | str, target: Path | str, *, what: str = "diretório") -> Path:
    """Cria `target` (e pais) depois de provar que está dentro de `base`."""
    resolved = ensure_within(base, target, what=what)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def reset_directory(base: Path | str, target: Path | str, *, what: str = "workspace") -> Path:
    """Apaga e recria `target`, **somente** se estiver dentro de `base`.

    Esta é a única porta autorizada para remoção recursiva no editor.
    Recusa explicitamente apagar a própria base — `reset_directory(x, x)` é
    quase sempre um bug de composição de caminho, não uma intenção.
    """
    base_r = _resolved(base)
    resolved = ensure_within(base_r, target, what=what)
    if resolved == base_r:
        raise PathEscapeError(
            f"recusado: {what} coincide com a base ({base_r}). "
            "Apagar a base inteira nunca é intencional aqui."
        )
    if resolved.exists() and not resolved.is_dir():
        raise PathError(f"{what} existe e não é diretório: {resolved}")
    if resolved.is_dir():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved
