#!/usr/bin/env python3
"""Regressão dos modelos e da máquina de estados do Revival Studio.

O teste central é `test_mudar_servidor_invalida_o_build`: sem ele, a UI pode
exibir "APK verificado" para um APK que aponta para o host anterior — a causa
nº 2 da triagem de 60 segundos da skill boot-diagnostics.

Execução: python tests/revival_editor/test_models.py
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from revival_editor.models import (  # noqa: E402
    STAGE_ORDER,
    Failure,
    HostnameError,
    ProjectState,
    Stage,
    StageProgress,
    StageResult,
    normalize_hostname,
)


class TestNormalizeHostname(unittest.TestCase):
    def test_aceita_host_puro(self) -> None:
        self.assertEqual(normalize_hostname("doom.exemplo.com.br"), "doom.exemplo.com.br")

    def test_normaliza_esquema_e_caixa_e_espaco(self) -> None:
        self.assertEqual(normalize_hostname("  HTTPS://Doom.Exemplo.COM  "), "doom.exemplo.com")

    def test_remove_ponto_final_do_fqdn(self) -> None:
        self.assertEqual(normalize_hostname("doom.exemplo.com."), "doom.exemplo.com")

    def test_recusa_esquema_nao_https(self) -> None:
        for bad in ("http://doom.exemplo.com", "ftp://doom.exemplo.com"):
            with self.assertRaises(HostnameError):
                normalize_hostname(bad)

    def test_recusa_path_query_fragmento(self) -> None:
        # O usuário tende a colar a URL inteira do cliente; recusar é melhor
        # que descartar em silêncio o /collections/doom.
        for bad in (
            "https://doom.exemplo.com/collections/doom",
            "doom.exemplo.com/collections/doom",
            "doom.exemplo.com?x=1",
            "doom.exemplo.com#frag",
        ):
            with self.assertRaises(HostnameError):
                normalize_hostname(bad)

    def test_recusa_credenciais_e_porta(self) -> None:
        for bad in ("https://u000@doom.exemplo.com", "doom.exemplo.com:8443"):
            with self.assertRaises(HostnameError):
                normalize_hostname(bad)

    def test_recusa_ip_puro(self) -> None:
        with self.assertRaises(HostnameError):
            normalize_hostname("192.168.0.10")

    def test_recusa_nao_fqdn_e_vazio(self) -> None:
        for bad in ("localhost", "", "   ", "."):
            with self.assertRaises(HostnameError):
                normalize_hostname(bad)

    def test_recusa_rotulo_invalido(self) -> None:
        for bad in ("-x.exemplo.com", "x-.exemplo.com", "a_b.exemplo.com", "a" * 64 + ".com"):
            with self.assertRaises(HostnameError):
                normalize_hostname(bad)

    def test_recusa_acima_de_253_bytes(self) -> None:
        gigante = ".".join(["a" * 63] * 5) + ".com"
        with self.assertRaises(HostnameError):
            normalize_hostname(gigante)


class TestStageProgress(unittest.TestCase):
    def test_indeterminado_quando_fraction_e_none(self) -> None:
        p = StageProgress(stage="apktool", message="desmontando")
        self.assertTrue(p.indeterminate)

    def test_determinado(self) -> None:
        p = StageProgress(stage="bundles", message="varrendo", fraction=0.5, current=1, total=2)
        self.assertFalse(p.indeterminate)

    def test_recusa_fraction_fora_do_intervalo(self) -> None:
        for bad in (-0.1, 1.5):
            with self.assertRaises(ValueError):
                StageProgress(stage="x", message="y", fraction=bad)

    def test_serializa(self) -> None:
        p = StageProgress(stage="x", message="y", fraction=0.25)
        self.assertEqual(json.loads(json.dumps(p.to_dict()))["fraction"], 0.25)


class TestFailureEStageResult(unittest.TestCase):
    def test_failure_serializa_com_campos_do_plano(self) -> None:
        f = Failure(
            code="PRECHECK_TOO_LONG",
            stage="precheck",
            message="hostname não cabe no fast path",
            details="exit 4",
            report_path="work/revival-studio/p1/precheck.json",
            exit_code=4,
        )
        d = f.to_dict()
        for chave in ("code", "stage", "message", "details", "report_path", "exit_code"):
            self.assertIn(chave, d)

    def test_stage_result_embute_failure_serializavel(self) -> None:
        r = StageResult(
            stage="precheck",
            ok=False,
            failure=Failure(code="X", stage="precheck", message="falhou"),
        )
        texto = json.dumps(r.to_dict())
        self.assertIn('"code": "X"', texto)

    def test_stage_result_ok_sem_failure(self) -> None:
        r = StageResult(stage="analyze", ok=True, facts={"sha256": "ab"})
        self.assertIsNone(r.to_dict()["failure"])


class TestProjectState(unittest.TestCase):
    def _ate(self, stage: Stage) -> ProjectState:
        state = ProjectState()
        for s in STAGE_ORDER[: stage.order + 1]:
            state.mark(s)
        return state

    def test_projeto_novo_esta_vazio(self) -> None:
        self.assertEqual(ProjectState().current, Stage.VAZIO)

    def test_current_para_no_primeiro_buraco(self) -> None:
        state = ProjectState()
        state.mark(Stage.APK_ANALISADO)
        state.mark(Stage.APK_ASSINADO)  # pulou etapas no meio
        self.assertEqual(state.current, Stage.APK_ANALISADO)

    def test_can_enter_exige_todos_os_anteriores(self) -> None:
        state = self._ate(Stage.PATCH_APLICADO)
        self.assertTrue(state.can_enter(Stage.CUSTOMIZACOES_APLICADAS))
        self.assertFalse(state.can_enter(Stage.APK_ASSINADO))

    def test_assinar_indisponivel_antes_do_rebuild(self) -> None:
        # Regra explícita da §9.1 do plano.
        state = self._ate(Stage.CUSTOMIZACOES_APLICADAS)
        self.assertFalse(state.can_enter(Stage.APK_ASSINADO))
        state.mark(Stage.APK_RECONSTRUIDO)
        self.assertTrue(state.can_enter(Stage.APK_ASSINADO))

    def test_instalar_indisponivel_antes_da_verificacao(self) -> None:
        state = self._ate(Stage.APK_ASSINADO)
        self.assertFalse(state.can_enter(Stage.INSTALADO))
        state.mark(Stage.APK_VERIFICADO)
        self.assertTrue(state.can_enter(Stage.INSTALADO))

    def test_mudar_servidor_invalida_o_build(self) -> None:
        """O teste que impede um selo verde mentiroso."""
        state = self._ate(Stage.CLIENTE_VALIDADO)
        self.assertTrue(state.has(Stage.APK_VERIFICADO))

        invalidadas = state.invalidate_build()

        self.assertEqual(
            invalidadas,
            {
                Stage.APK_RECONSTRUIDO,
                Stage.APK_ASSINADO,
                Stage.APK_VERIFICADO,
                Stage.INSTALADO,
                Stage.CLIENTE_VALIDADO,
            },
        )
        self.assertFalse(state.has(Stage.APK_VERIFICADO))
        self.assertFalse(state.has(Stage.INSTALADO))
        # O que veio antes do build sobrevive: não é preciso reanalisar o APK.
        self.assertTrue(state.has(Stage.PATCH_APLICADO))
        self.assertEqual(state.current, Stage.CUSTOMIZACOES_APLICADAS)

    def test_invalidate_from_e_em_cascata(self) -> None:
        state = self._ate(Stage.APK_VERIFICADO)
        state.invalidate_from(Stage.SERVIDOR_VALIDADO)
        self.assertEqual(state.current, Stage.APK_ANALISADO)
        self.assertFalse(state.has(Stage.PATCH_APLICADO))

    def test_vazio_nunca_some(self) -> None:
        state = self._ate(Stage.APK_VERIFICADO)
        state.invalidate_from(Stage.VAZIO)
        self.assertTrue(state.has(Stage.VAZIO))
        self.assertEqual(state.current, Stage.VAZIO)

    def test_round_trip_de_serializacao(self) -> None:
        state = self._ate(Stage.PATCH_APLICADO)
        restaurado = ProjectState.from_list(state.to_list())
        self.assertEqual(restaurado.completed, state.completed)
        self.assertEqual(restaurado.current, Stage.PATCH_APLICADO)

    def test_to_list_sai_na_ordem_canonica(self) -> None:
        state = ProjectState()
        state.mark(Stage.PATCH_APLICADO)
        state.mark(Stage.APK_ANALISADO)
        valores = state.to_list()
        self.assertEqual(valores, sorted(valores, key=lambda v: Stage(v).order))

    def test_from_list_ignora_etapa_desconhecida(self) -> None:
        state = ProjectState.from_list(["APK_ANALISADO", "ETAPA_DO_FUTURO"])
        self.assertTrue(state.has(Stage.APK_ANALISADO))
        self.assertEqual(state.current, Stage.APK_ANALISADO)

    def test_from_list_none(self) -> None:
        self.assertEqual(ProjectState.from_list(None).current, Stage.VAZIO)


if __name__ == "__main__":
    unittest.main(verbosity=2)
