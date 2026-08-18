"""Modelos e máquina de estados do Revival Studio.

Nada aqui importa Tkinter nem chama `sys.exit()`. Todo dado é serializável.

A razão de a máquina de estados existir (PLANO §6.2): *"qualquer alteração de
servidor ou customização depois do build deve invalidar os estados
APK_RECONSTRUIDO em diante. A UI não pode continuar exibindo um selo verde
baseado em relatório antigo."* Um APK assinado que aponta para o host antigo é
exatamente o bug que a skill `boot-diagnostics` chama de "APK antigo" — a
triagem de 60 segundos gasta é culpa de um selo verde mentiroso.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

__all__ = [
    "Stage",
    "Severity",
    "StageProgress",
    "Failure",
    "StageResult",
    "ProjectState",
    "PATCH_STRATEGIES",
    "normalize_hostname",
    "HostnameError",
]


class HostnameError(ValueError):
    """Hostname recusado pela normalização."""


class Stage(str, Enum):
    """Estados do projeto, na ordem da §6.2 do plano.

    É `str` Enum para serializar direto em JSON sem conversão manual.
    """

    VAZIO = "VAZIO"
    APK_ANALISADO = "APK_ANALISADO"
    SERVIDOR_VALIDADO = "SERVIDOR_VALIDADO"
    WORKSPACE_PREPARADO = "WORKSPACE_PREPARADO"
    PATCH_APLICADO = "PATCH_APLICADO"
    CUSTOMIZACOES_APLICADAS = "CUSTOMIZACOES_APLICADAS"
    APK_RECONSTRUIDO = "APK_RECONSTRUIDO"
    APK_ASSINADO = "APK_ASSINADO"
    APK_VERIFICADO = "APK_VERIFICADO"
    INSTALADO = "INSTALADO"
    CLIENTE_VALIDADO = "CLIENTE_VALIDADO"

    @property
    def order(self) -> int:
        return STAGE_ORDER.index(self)


#: Ordem canônica. Índice = profundidade do progresso.
STAGE_ORDER: list[Stage] = [
    Stage.VAZIO,
    Stage.APK_ANALISADO,
    Stage.SERVIDOR_VALIDADO,
    Stage.WORKSPACE_PREPARADO,
    Stage.PATCH_APLICADO,
    Stage.CUSTOMIZACOES_APLICADAS,
    Stage.APK_RECONSTRUIDO,
    Stage.APK_ASSINADO,
    Stage.APK_VERIFICADO,
    Stage.INSTALADO,
    Stage.CLIENTE_VALIDADO,
]

#: A partir daqui o artefato é um APK concreto no disco. Qualquer mudança de
#: entrada (host, CA, customização, APK de origem) torna esses selos mentira.
BUILD_STAGES: frozenset[Stage] = frozenset(
    {
        Stage.APK_RECONSTRUIDO,
        Stage.APK_ASSINADO,
        Stage.APK_VERIFICADO,
        Stage.INSTALADO,
        Stage.CLIENTE_VALIDADO,
    }
)

#: Estratégias aceitas pelo pipeline de patch (fase 6).
PATCH_STRATEGIES = ("auto", "fast-path", "bundle-aware")


class Severity(str, Enum):
    INFO = "info"
    AVISO = "aviso"
    ERRO = "erro"


@dataclass(frozen=True)
class StageProgress:
    """Progresso de uma etapa, para a fila do JobRunner.

    `fraction` é `None` quando o progresso é indeterminado — é o caso do
    apktool, que não reporta percentual (plano fase 2).
    """

    stage: str
    message: str
    fraction: float | None = None
    current: int | None = None
    total: int | None = None

    def __post_init__(self) -> None:
        if self.fraction is not None and not (0.0 <= self.fraction <= 1.0):
            raise ValueError(f"fraction fora de [0,1]: {self.fraction}")

    @property
    def indeterminate(self) -> bool:
        return self.fraction is None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Failure:
    """Falha padronizada: código, etapa, mensagem curta, detalhes e relatório.

    Exigido pela fase 1: *"padronizar falhas com código, etapa, mensagem curta,
    detalhes e caminho de relatório"*. A UI mostra `message`; o painel de log
    mostra `details`; o botão "abrir relatório" usa `report_path`.
    """

    code: str
    stage: str
    message: str
    details: str = ""
    report_path: str | None = None
    exit_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StageResult:
    """Resultado serializável de uma etapa do pipeline."""

    stage: str
    ok: bool
    failure: Failure | None = None
    report_path: str | None = None
    facts: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.failure is not None:
            data["failure"] = self.failure.to_dict()
        return data


#: Hostname DNS: rótulos alfanuméricos com hífen interno, 1-63 bytes cada.
_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def normalize_hostname(raw: str) -> str:
    """Normaliza a entrada do usuário para um hostname puro.

    Aceita `https://host` e `host`; rejeita esquema diferente de https, path,
    query, fragmento, credenciais e porta — exigência da fase 5 do plano
    (*"aceitar hostname, não URL com caminho"*).

    O path `/collections/doom` do cliente é preservado pelo patcher; ele **não**
    faz parte do hostname e por isso é recusado aqui em vez de silenciosamente
    descartado.
    """
    if not isinstance(raw, str):
        raise HostnameError("hostname deve ser texto")
    host = raw.strip()
    if not host:
        raise HostnameError("hostname vazio")

    lowered = host.lower()
    if "://" in lowered:
        scheme, _, rest = lowered.partition("://")
        if scheme != "https":
            raise HostnameError(
                f"esquema {scheme!r} não aceito: o cliente 1.13.1 fala HTTPS. Informe só o host."
            )
        host = rest
        lowered = host

    for char, nome in (("/", "caminho"), ("?", "query"), ("#", "fragmento")):
        if char in lowered:
            raise HostnameError(
                f"informe apenas o hostname, sem {nome}. "
                "O path /collections/doom é preservado pelo patcher automaticamente."
            )
    if "@" in lowered:
        raise HostnameError(
            "credenciais na URL não são aceitas. "
            "O padding de userinfo é calculado por build_url_replacement(), não digitado."
        )
    if ":" in lowered:
        raise HostnameError("porta não é aceita: o cliente usa 443 fixo")

    host = lowered.rstrip(".")
    if not host:
        raise HostnameError("hostname vazio")
    if len(host) > 253:
        raise HostnameError(f"hostname com {len(host)} bytes excede o limite DNS de 253")
    if _IPV4.match(host):
        raise HostnameError(
            "IP puro não é suportado pelo patcher de hostname (nem por SNI/HTTPS aqui). Use um nome DNS."
        )
    labels = host.split(".")
    if len(labels) < 2:
        raise HostnameError(f"{host!r} não é um FQDN: informe domínio completo (ex.: doom.exemplo.com)")
    for label in labels:
        if not _LABEL.match(label):
            raise HostnameError(f"rótulo DNS inválido em {host!r}: {label!r}")
    return host


@dataclass
class ProjectState:
    """Estados alcançados por um projeto, com invalidação em cascata.

    Não guarda segredo: sem senha de keystore, sem token admin, sem conteúdo de
    certificado (plano §6.3).
    """

    completed: set[Stage] = field(default_factory=lambda: {Stage.VAZIO})

    def mark(self, stage: Stage) -> None:
        """Marca uma etapa como concluída."""
        self.completed.add(stage)

    def has(self, stage: Stage) -> bool:
        return stage in self.completed

    @property
    def current(self) -> Stage:
        """Etapa mais avançada já concluída sem buraco na sequência."""
        atual = Stage.VAZIO
        for stage in STAGE_ORDER:
            if stage in self.completed:
                atual = stage
            else:
                break
        return atual

    def invalidate_from(self, stage: Stage) -> set[Stage]:
        """Remove `stage` e tudo que vem depois. Devolve o que foi invalidado."""
        removidas = {s for s in self.completed if s.order >= stage.order}
        self.completed -= removidas
        self.completed.add(Stage.VAZIO)
        return removidas

    def invalidate_build(self) -> set[Stage]:
        """Invalida do rebuild em diante.

        Chamada obrigatória quando host, CA, APK de entrada ou qualquer
        customização mudar — o APK no disco deixou de corresponder ao projeto.
        """
        return self.invalidate_from(Stage.APK_RECONSTRUIDO)

    def can_enter(self, stage: Stage) -> bool:
        """True se todos os pré-requisitos de `stage` já foram concluídos.

        É o que desabilita item de menu: "Assinar" não fica disponível antes de
        "Rebuild", "Instalar" não fica antes da verificação pós-assinatura
        (plano §9.1).
        """
        idx = stage.order
        if idx == 0:
            return True
        return all(s in self.completed for s in STAGE_ORDER[:idx])

    def to_list(self) -> list[str]:
        """Serialização estável para `project.json` (`completed_stages`)."""
        return [s.value for s in STAGE_ORDER if s in self.completed]

    @classmethod
    def from_list(cls, values: list[str] | None) -> "ProjectState":
        state = cls()
        for value in values or []:
            try:
                state.completed.add(Stage(value))
            except ValueError:
                # Etapa desconhecida (projeto de versão futura): ignora em vez
                # de explodir, mas nunca a promove a concluída.
                continue
        state.completed.add(Stage.VAZIO)
        return state
