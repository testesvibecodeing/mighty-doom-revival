"""Registro de ações do Revival Studio (planos §9.1 e §9.2).

Este módulo **não importa Tkinter**: é a fonte única da qual a UI constrói os
menus e pela qual os wrappers de compatibilidade (§6.1/§9.2) são validados —
*"adicionar teste que verifica que cada wrapper encaminha para uma ação
existente"*. Se um wrapper aponta para uma ação fora daqui, o teste falha.

A janela mínima (§30 item 6) usa os menus `MENUS`; as fases seguintes acrescentam
ações novas aqui, nunca handlers soltos na UI.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import Stage

__all__ = ["MENUS", "ActionSpec", "ACTIONS", "action_by_id", "menu_actions"]


#: Menus da janela mínima (§30 item 6). A barra completa da §9.1 cresce a partir
#: daqui — "Arquivo" e "Ajuda" entram quando ganharem ações de verdade.
MENUS: tuple[str, ...] = ("Projeto", "APK", "Servidor", "Cliente", "Testes", "Log")


@dataclass(frozen=True)
class ActionSpec:
    """Um item de menu: pré-requisito declarável e handler nomeado.

    - `requires`: etapa que precisa estar concluída para o item habilitar
      (§9.1: *"Cada item deve ficar desabilitado quando seus pré-requisitos
      não estiverem cumpridos"*). `None` = sempre habilitado.
    - `needs_project`: a ação exige um projeto aberto (Novo/Abrir não exigem).
    - `handler`: nome do método em `revival_editor.ui.app.StudioApp` — testado,
      então um typo aqui derruba o gate, não o usuário no meio da sessão.
    """

    action_id: str
    menu: str
    label: str
    handler: str
    requires: Stage | None = None
    needs_project: bool = True
    #: True = permanece utilizável com job em execução (ações de leitura do log).
    busy_safe: bool = False


ACTIONS: tuple[ActionSpec, ...] = (
    # -- Projeto ---------------------------------------------------------
    ActionSpec(
        action_id="projeto.novo",
        menu="Projeto",
        label="Novo projeto…",
        handler="ui_novo_projeto",
        needs_project=False,
    ),
    ActionSpec(
        action_id="projeto.abrir",
        menu="Projeto",
        label="Abrir projeto…",
        handler="ui_abrir_projeto",
        needs_project=False,
    ),
    ActionSpec(
        action_id="projeto.salvar",
        menu="Projeto",
        label="Salvar projeto",
        handler="ui_salvar_projeto",
    ),
    ActionSpec(
        action_id="projeto.analisar",
        menu="Projeto",
        label="Analisar APK",
        handler="act_analisar_apk",
    ),
    # -- APK ---------------------------------------------------------------
    ActionSpec(
        action_id="apk.precheck",
        menu="APK",
        label="Precheck de hostname",
        handler="act_precheck_hostname",
        requires=Stage.APK_ANALISADO,
    ),
    ActionSpec(
        action_id="apk.resumo_hashes",
        menu="APK",
        label="Ver resumo de hashes",
        handler="act_resumo_hashes",
        requires=Stage.APK_ANALISADO,
    ),
    ActionSpec(
        action_id="pipeline.completo",
        menu="APK",
        label="Aplicar endpoint (decode → patch → build → sign → verify)",
        handler="act_pipeline_completo",
        requires=Stage.SERVIDOR_VALIDADO,
    ),
    # -- Servidor ----------------------------------------------------------
    ActionSpec(
        action_id="servidor.preflight",
        menu="Servidor",
        label="Validar servidor (HTTPS + health + game data)",
        handler="act_validar_servidor",
        requires=Stage.APK_ANALISADO,
    ),
    # -- Cliente -----------------------------------------------------------
    ActionSpec(
        action_id="cliente.detectar_dispositivos",
        menu="Cliente",
        label="Detectar dispositivos ADB",
        handler="act_detectar_dispositivos",
        needs_project=False,
    ),
    # -- Testes ------------------------------------------------------------
    ActionSpec(
        action_id="testes.editor",
        menu="Testes",
        label="Testes Python do editor",
        handler="act_testes_editor",
        needs_project=False,
    ),
    ActionSpec(
        action_id="testes.gate",
        menu="Testes",
        label="verify_everything.py (gate completo)",
        handler="act_verify_everything",
        needs_project=False,
    ),
    # -- Log ---------------------------------------------------------------
    ActionSpec(
        action_id="log.salvar",
        menu="Log",
        label="Salvar log em arquivo…",
        handler="ui_salvar_log",
        needs_project=False,
        busy_safe=True,
    ),
    ActionSpec(
        action_id="log.limpar",
        menu="Log",
        label="Limpar painel",
        handler="ui_limpar_log",
        needs_project=False,
        busy_safe=True,
    ),
    ActionSpec(
        action_id="log.pasta",
        menu="Log",
        label="Abrir pasta de logs do projeto",
        handler="ui_abrir_pasta_logs",
    ),
)

_BY_ID: dict[str, ActionSpec] = {spec.action_id: spec for spec in ACTIONS}


def action_by_id(action_id: str) -> ActionSpec:
    try:
        return _BY_ID[action_id]
    except KeyError:
        raise ValueError(
            f"ação {action_id!r} não existe no registro. Ações válidas: "
            + ", ".join(sorted(_BY_ID))
        ) from None


def menu_actions(menu: str) -> list[ActionSpec]:
    return [spec for spec in ACTIONS if spec.menu == menu]
