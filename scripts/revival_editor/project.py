"""Modelo de projeto do Revival Studio (plano §6.3).

`project.json` vive em `work/revival-studio/<id>/` — nunca na raiz versionada.
O arquivo **não carrega segredo**: nem senha de keystore, nem token admin, nem
segredo JWT, nem conteúdo de certificado. Senhas ficam só em memória; tokens
vêm de variável de ambiente ou prompt temporário.

`save()` aplica `mask_mapping` como trava de última linha: se amanhã algum
campo novo carregar segredo, ele é gravado mascarado, nunca em claro.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import PATCH_STRATEGIES, ProjectState, Stage, normalize_hostname
from .paths import STUDIO_ROOT, ensure_dir, project_dir
from .redaction import mask_mapping

__all__ = [
    "SCHEMA_VERSION",
    "ProjectError",
    "Project",
    "project_file",
    "new_project",
    "save_project",
    "load_project",
    "list_projects",
]

SCHEMA_VERSION = 1

PROJECT_FILENAME = "project.json"


class ProjectError(Exception):
    """Projeto inválido ou incompatível — mensagem já acionável para a UI."""


@dataclass
class Project:
    """Estado persistente de um projeto (§6.3), sem segredo.

    `reports` mapeia nome de etapa -> caminho do relatório JSON sanitizado.
    """

    project_id: str
    input_apk: str | None = None
    input_sha256: str | None = None
    server_host: str | None = None
    ca_path: str | None = None
    patch_strategy: str = "auto"
    # Injeta a RevivalAuthActivity (tela Criar conta | Entrar) como único
    # MAIN/LAUNCHER. LIGADO por padrão: é o que define o build Revival — sem
    # ela o jogo cai no gate do Google Play Games e não autentica.
    revival_auth: bool = True
    # Override de LABORATÓRIO: publica o APK mesmo contra servidor com contrato
    # incompatível. Sempre `False` por padrão e sempre registrado no
    # `pipeline.json` — existe para gerar artefato estático enquanto o servidor
    # compatível não está no ar, nunca para produção silenciosa.
    allow_incompatible_server: bool = False
    customizations: dict[str, Any] = field(default_factory=dict)
    output_apk: str | None = None
    state: ProjectState = field(default_factory=ProjectState)
    reports: dict[str, str] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    # ------------------------------------------------------------------
    # mutação com invalidação em cascata (§6.2)
    # ------------------------------------------------------------------

    def set_server(self, raw_host: str) -> str:
        """Troca o host do servidor, invalidando o build se mudou.

        Devolve o hostname normalizado. Levanta `HostnameError` (de models)
        com instrução se a entrada for URL com path, IP, porta etc.
        """
        host = normalize_hostname(raw_host)
        if self.server_host and host != self.server_host:
            self.state.invalidate_build()
        self.server_host = host
        return host

    def set_input_apk(self, path: Path | str) -> str:
        """Troca o APK de entrada — análise anterior perde validade.

        Invalidation também quando o anterior era vazio: definir o APK
        inicial após já ter marcado etapas é mudança de entrada do mesmo jeito.
        """
        caminho = str(Path(path))
        if caminho != (self.input_apk or ""):
            self.state.invalidate_from(Stage.APK_ANALISADO)
        self.input_apk = caminho
        return caminho

    def set_patch_strategy(self, strategy: str) -> None:
        if strategy not in PATCH_STRATEGIES:
            raise ProjectError(
                f"estratégia {strategy!r} desconhecida. Use: {', '.join(PATCH_STRATEGIES)}"
            )
        self.patch_strategy = strategy

    def set_revival_auth(self, enabled: bool) -> None:
        """Liga/desliga a RevivalAuthActivity — o APK pronto perde validade.

        Um build feito sem a Activity não vira build com Activity só por marcar
        a opção depois: o Manifest e o dex estão dentro do APK.
        """
        novo = bool(enabled)
        if novo != self.revival_auth:
            self.state.invalidate_build()
        self.revival_auth = novo

    def set_ca_path(self, path: Path | str | None) -> None:
        """Troca a CA — o APK construído com a CA antiga (ou sem CA) fica obsoleto."""
        novo = str(Path(path)) if path else None
        if novo != self.ca_path:
            self.state.invalidate_build()
        self.ca_path = novo

    # ------------------------------------------------------------------
    # serialização
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "project_id": self.project_id,
            "input_apk": self.input_apk,
            "input_sha256": self.input_sha256,
            "server_host": self.server_host,
            "ca_path": self.ca_path,
            "patch_strategy": self.patch_strategy,
            "revival_auth": self.revival_auth,
            "allow_incompatible_server": self.allow_incompatible_server,
            "customizations": self.customizations,
            "output_apk": self.output_apk,
            "completed_stages": self.state.to_list(),
            "reports": dict(self.reports),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Project":
        versao = data.get("schema_version")
        if versao != SCHEMA_VERSION:
            raise ProjectError(
                f"project.json com schema_version={versao!r}; este editor entende "
                f"{SCHEMA_VERSION}. Abra com a versão que criou o projeto ou crie um projeto novo."
            )
        project = cls(project_id=str(data["project_id"]))
        project.input_apk = data.get("input_apk")
        project.input_sha256 = data.get("input_sha256")
        project.server_host = data.get("server_host")
        project.ca_path = data.get("ca_path")
        project.patch_strategy = str(data.get("patch_strategy") or "auto")
        # Projeto salvo antes desta opcao existir: assume LIGADO, que e o
        # padrao do build Revival — nao silenciosamente desligado.
        project.revival_auth = bool(data.get("revival_auth", True))
        project.allow_incompatible_server = bool(data.get("allow_incompatible_server", False))
        project.customizations = dict(data.get("customizations") or {})
        project.output_apk = data.get("output_apk")
        project.state = ProjectState.from_list(data.get("completed_stages"))
        project.reports = {str(k): str(v) for k, v in (data.get("reports") or {}).items()}
        project.created_at = data.get("created_at")
        project.updated_at = data.get("updated_at")
        if project.patch_strategy not in PATCH_STRATEGIES:
            raise ProjectError(
                f"estratégia {project.patch_strategy!r} no project.json é desconhecida "
                "neste editor; recuse adivinhar (regra do plano: sem suposição)."
            )
        return project


# ----------------------------------------------------------------------
# persistência
# ----------------------------------------------------------------------


def project_file(project_id: str, *, studio_root: Path | None = None) -> Path:
    return project_dir(project_id, studio_root=studio_root) / PROJECT_FILENAME


def new_project(
    project_id: str,
    *,
    studio_root: Path | None = None,
    input_apk: Path | str | None = None,
    server_host: str | None = None,
) -> tuple[Project, Path]:
    """Cria um projeto em memória e grava o `project.json` inicial.

    Recusa recriar por cima de um projeto existente — abrir é outra ação.
    """
    diretorio = project_dir(project_id, studio_root=studio_root)
    destino = diretorio / PROJECT_FILENAME
    if destino.is_file():
        raise ProjectError(
            f"projeto {project_id!r} já existe em {destino}. Abra-o em vez de recriar."
        )
    ensure_dir(diretorio, diretorio / "logs", what="logs do projeto")
    ensure_dir(diretorio, diretorio / "reports", what="reports do projeto")

    project = Project(project_id=project_id, created_at=_carimbo())
    if input_apk:
        project.input_apk = str(Path(input_apk))
    if server_host:
        project.set_server(server_host)
    destino = _gravar(project, destino)
    return project, destino


def save_project(project: Project, *, studio_root: Path | None = None) -> Path:
    """Grava `project.json` (idempotente, sem segredo)."""
    destino = project_file(project.project_id, studio_root=studio_root)
    return _gravar(project, destino)


def load_project(
    project_id: str, *, studio_root: Path | None = None
) -> tuple[Project, Path]:
    destino = project_file(project_id, studio_root=studio_root)
    if not destino.is_file():
        raise ProjectError(f"não há project.json para {project_id!r} em {destino}")
    try:
        dados = json.loads(destino.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectError(f"project.json ilegível ({destino}): {exc}") from exc
    project = Project.from_dict(dados)
    if project.project_id != project_id:
        raise ProjectError(
            f"project.json declara id {project.project_id!r} mas está na pasta de "
            f"{project_id!r} — recuse mesclar projetos diferentes."
        )
    return project, destino


def list_projects(*, studio_root: Path | None = None) -> list[str]:
    """Ids com `project.json`, em ordem alfabética (para o diálogo Abrir)."""
    base = Path(studio_root) if studio_root else STUDIO_ROOT
    if not base.is_dir():
        return []
    return sorted(
        p.parent.name for p in base.glob(f"*/{PROJECT_FILENAME}") if p.is_file()
    )


def _gravar(project: Project, destino: Path) -> Path:
    project.updated_at = _carimbo()
    destino.parent.mkdir(parents=True, exist_ok=True)
    dados = mask_mapping(project.to_dict())
    destino.write_text(
        json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return destino


def _carimbo() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
