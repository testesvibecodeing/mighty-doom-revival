#!/usr/bin/env python3
"""A RevivalAuthActivity precisa sair do botão NORMAL do Studio.

O defeito que isto previne foi medido em 2026-08-20: `revival_auth` tinha
default `False` no pipeline e o job da UI não passava o parâmetro, então
**Aplicar endpoint** gerava um APK sem a Activity — só um script auxiliar em
`work/audit-opus/rig/` produzia o build de verdade. Um teste chamando
`apply_endpoint(..., revival_auth=True)` diretamente NÃO pegaria isso.

Por isso estes testes entram pelo mesmo `_trabalho_pipeline` que o botão usa, com
`apply_endpoint` espionado: o que se afirma é que o parâmetro atravessa
projeto -> job -> pipeline, e que o `pipeline.json` registra a opção pedida.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from revival_editor.pipeline import PipelineResult  # noqa: E402
from revival_editor.project import Project  # noqa: E402


class CtxFalso:
    def __init__(self) -> None:
        self.linhas: list[str] = []

    def log(self, linha: str, **_kw) -> None:
        self.linhas.append(linha)

    def progress(self, *_a, **_kw) -> None:
        pass

    def raise_if_cancelled(self) -> None:
        pass


def resultado_ok(host: str, *, auth: bool) -> PipelineResult:
    r = PipelineResult(host=host, strategy="auto")
    r.output_apk = "output/mighty-doom-revival.apk"
    r.revival_auth_requested = auth
    if auth:
        r.auth_report = {
            "activity_class": "br.com.revival.auth.RevivalAuthActivity",
            "dex_entry": "classes3.dex",
            "launcher_count": 1,
            "revival_is_launcher": True,
            "unity_activity_preserved": True,
            "deep_link_preserved": True,
            "base_url_scheme": "https",
            "verified": True,
        }
    return r


class TestParametroChegaPeloJobDaUI(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.projeto = Project(project_id="teste")
        self.projeto.input_apk = "input/mighty-doom.apk"
        self.projeto.server_host = "doom.exemplo.br"

    def _rodar(self):
        from revival_editor.ui import app as ui_app
        with mock.patch("revival_editor.pipeline.apply_endpoint") as espiao:
            espiao.side_effect = lambda ctx, **kw: resultado_ok(
                kw["host"], auth=kw.get("revival_auth", False))
            ui_app._trabalho_pipeline(self.projeto, self.dir, CtxFalso())
            return espiao.call_args.kwargs

    def test_ligado_por_padrao_no_projeto(self):
        self.assertTrue(Project(project_id="novo").revival_auth,
                        "o build Revival sem a Activity não autentica: o padrão é LIGADO")

    def test_job_da_ui_repassa_revival_auth(self):
        kwargs = self._rodar()
        self.assertIn("revival_auth", kwargs,
                      "o job da UI tem que repassar a opção — sem isso o botão normal "
                      "gera APK sem Activity")
        self.assertTrue(kwargs["revival_auth"])

    def test_opcao_desligada_tambem_atravessa(self):
        self.projeto.revival_auth = False
        kwargs = self._rodar()
        self.assertIs(kwargs["revival_auth"], False, "quem desliga tem que ser obedecido")

    def test_relatorio_normal_registra_a_opcao_e_o_passo_auth(self):
        self._rodar()
        relatorio = json.loads((self.dir / "reports" / "pipeline.json").read_text(encoding="utf-8"))
        self.assertTrue(relatorio["revival_auth_requested"],
                        "pipeline.json tem que provar que a opção foi pedida")
        auth = relatorio["auth_report"]
        self.assertEqual(auth["activity_class"], "br.com.revival.auth.RevivalAuthActivity")
        self.assertEqual(auth["dex_entry"], "classes3.dex")
        self.assertEqual(auth["launcher_count"], 1)
        self.assertTrue(auth["unity_activity_preserved"])
        self.assertTrue(auth["deep_link_preserved"])
        self.assertEqual(auth["base_url_scheme"], "https")
        self.assertTrue(auth["verified"])

    def test_relatorio_sem_auth_nao_finge_que_teve(self):
        self.projeto.revival_auth = False
        self._rodar()
        relatorio = json.loads((self.dir / "reports" / "pipeline.json").read_text(encoding="utf-8"))
        self.assertFalse(relatorio["revival_auth_requested"])
        self.assertIsNone(relatorio["auth_report"])


class TestInvalidacaoDoBuild(unittest.TestCase):
    def test_trocar_a_opcao_invalida_o_apk_pronto(self):
        from revival_editor.models import Stage
        projeto = Project(project_id="x")
        projeto.state.mark(Stage.APK_ANALISADO)
        projeto.state.mark(Stage.APK_VERIFICADO)
        self.assertTrue(projeto.state.has(Stage.APK_VERIFICADO))
        projeto.set_revival_auth(False)
        self.assertFalse(projeto.state.has(Stage.APK_VERIFICADO),
                         "o Manifest e o dex estão DENTRO do APK: marcar a opção "
                         "depois não transforma um build antigo em build com Activity")

    def test_repetir_a_mesma_opcao_nao_invalida(self):
        from revival_editor.models import Stage
        projeto = Project(project_id="y")
        projeto.state.mark(Stage.APK_ANALISADO)
        projeto.state.mark(Stage.APK_VERIFICADO)
        projeto.set_revival_auth(True)      # já era True
        self.assertTrue(projeto.state.has(Stage.APK_VERIFICADO))


class TestPersistencia(unittest.TestCase):
    def test_ida_e_volta_no_project_json(self):
        projeto = Project(project_id="p")
        projeto.set_revival_auth(False)
        volta = Project.from_dict(projeto.to_dict())
        self.assertIs(volta.revival_auth, False)

    def test_projeto_antigo_sem_o_campo_assume_ligado(self):
        dados = Project(project_id="p").to_dict()
        del dados["revival_auth"]
        self.assertTrue(Project.from_dict(dados).revival_auth,
                        "projeto salvo antes da opção não pode virar build sem Activity")




class TestPreflightDeContrato(unittest.TestCase):
    """Build "verde" contra servidor incompativel e o defeito que isto fecha.

    Em 2026-08-20 um APK foi publicado contra uma VPS sem identidade, sem
    `contract_revision` e com `research_mode: true` — o cliente reproduziria os
    `Malformed response payload` ja corrigidos. O gate roda ANTES do decode.
    """

    def _prontidao(self, saude):
        from revival_editor import pipeline
        with mock.patch("urllib.request.urlopen") as abrir:
            if saude is None:
                abrir.side_effect = OSError("conexao recusada")
            else:
                ctx = mock.MagicMock()
                ctx.__enter__.return_value.read.return_value = json.dumps(saude).encode()
                abrir.return_value = ctx
            return pipeline._prontidao_do_servidor("doom.exemplo.br")

    def _saude_boa(self, **over):
        from revival_editor.pipeline import REQUIRED_CONTRACT_REVISION
        return {"ok": True, "instance_id": "vps", "build_id": "abc123",
                "contract_revision": REQUIRED_CONTRACT_REVISION,
                "research_mode": False, "build_dirty": False, **over}

    def test_servidor_compativel_passa(self):
        r = self._prontidao(self._saude_boa())
        self.assertTrue(r["ready"], r["reasons"])
        self.assertEqual(r["reasons"], [])

    def test_health_antigo_sem_identidade_reprova(self):
        r = self._prontidao({"ok": True, "client_version": "1.13.1", "api_version": "24.0.0"})
        self.assertFalse(r["ready"])
        self.assertTrue(any("identidade" in m for m in r["reasons"]))

    def test_revisao_insuficiente_reprova(self):
        from revival_editor.pipeline import REQUIRED_CONTRACT_REVISION
        r = self._prontidao(self._saude_boa(contract_revision=REQUIRED_CONTRACT_REVISION - 1))
        self.assertFalse(r["ready"])
        self.assertTrue(any("contract_revision" in m for m in r["reasons"]))

    def test_research_mode_ligado_reprova(self):
        r = self._prontidao(self._saude_boa(research_mode=True))
        self.assertFalse(r["ready"])
        self.assertTrue(any("research_mode" in m for m in r["reasons"]))

    def test_build_sujo_reprova(self):
        r = self._prontidao(self._saude_boa(build_dirty=True))
        self.assertFalse(r["ready"])
        self.assertTrue(any("sujo" in m for m in r["reasons"]))

    def test_servidor_inalcancavel_nao_e_pronto(self):
        r = self._prontidao(None)
        self.assertFalse(r["ready"], "falta de medicao nao e aprovacao")
        self.assertTrue(any("indisponivel" in m for m in r["reasons"]))

    def test_motivos_sao_acionaveis(self):
        for saude in (None, {"ok": True}, self._saude_boa(research_mode=True)):
            r = self._prontidao(saude)
            for motivo in r["reasons"]:
                self.assertGreater(len(motivo), 25, f"motivo curto demais: {motivo!r}")

    def test_override_de_laboratorio_e_explicito_e_nunca_default(self):
        import inspect
        from revival_editor.pipeline import apply_endpoint
        parametro = inspect.signature(apply_endpoint).parameters["allow_incompatible_server"]
        self.assertIs(parametro.default, False,
                      "ignorar servidor incompativel nunca pode ser o padrao")


if __name__ == "__main__":
    unittest.main(verbosity=2)
