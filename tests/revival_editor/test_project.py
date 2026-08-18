#!/usr/bin/env python3
"""Regressão do modelo de projeto do Revival Studio (plano §6.3).

Foco: `project.json` fica em work/revival-studio/<id>/ (nunca versionado),
nunca carrega segredo, e mudança de host/CA/APK invalida estados de build.

Execução: python tests/revival_editor/test_project.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from revival_editor.models import (  # noqa: E402
    HostnameError,
    Stage,
)
from revival_editor.project import (  # noqa: E402
    SCHEMA_VERSION,
    Project,
    ProjectError,
    list_projects,
    load_project,
    new_project,
    project_file,
    save_project,
)


class BaseComStudio(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.studio = Path(self._tmp.name) / "revival-studio"

    def tearDown(self) -> None:
        self._tmp.cleanup()


class TestNovoProjeto(BaseComStudio):
    def test_cria_project_json_logs_e_reports(self) -> None:
        projeto, destino = new_project("doom-local", studio_root=self.studio)
        self.assertEqual(destino.name, "project.json")
        self.assertTrue(destino.is_file())
        self.assertTrue((destino.parent / "logs").is_dir())
        self.assertTrue((destino.parent / "reports").is_dir())
        dados = json.loads(destino.read_text(encoding="utf-8"))
        self.assertEqual(dados["schema_version"], SCHEMA_VERSION)
        self.assertEqual(dados["completed_stages"], ["VAZIO"])

    def test_recusa_recriar_projeto_existente(self) -> None:
        new_project("doom-local", studio_root=self.studio)
        with self.assertRaises(ProjectError):
            new_project("doom-local", studio_root=self.studio)

    def test_host_invalido_rejeita_na_criacao(self) -> None:
        with self.assertRaises(HostnameError):
            new_project("x", studio_root=self.studio, server_host="https://host/caminho")


class TestRoundTrip(BaseComStudio):
    def test_salvar_carregar_preserva_estado(self) -> None:
        projeto, _ = new_project("rt", studio_root=self.studio)
        projeto.state.mark(Stage.APK_ANALISADO)
        projeto.state.mark(Stage.SERVIDOR_VALIDADO)
        projeto.reports["analyze"] = str(self.studio / "rt" / "reports" / "analyze.json")
        projeto.customizations = {"loading_screen": {"ativa": True}}
        save_project(projeto, studio_root=self.studio)

        carregado, _ = load_project("rt", studio_root=self.studio)
        self.assertEqual(carregado.state.completed, projeto.state.completed)
        self.assertEqual(carregado.reports, projeto.reports)
        self.assertEqual(carregado.customizations, projeto.customizations)

    def test_schema_do_futuro_e_recusado(self) -> None:
        destino = project_file("futuro", studio_root=self.studio)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            json.dumps({"schema_version": 99, "project_id": "futuro"}), encoding="utf-8"
        )
        with self.assertRaises(ProjectError):
            load_project("futuro", studio_root=self.studio)

    def test_id_divergente_da_pasta_e_recusado(self) -> None:
        destino = project_file("pasta-a", studio_root=self.studio)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            json.dumps({"schema_version": 1, "project_id": "outro-id"}), encoding="utf-8"
        )
        with self.assertRaises(ProjectError):
            load_project("pasta-a", studio_root=self.studio)

    def test_list_projects(self) -> None:
        self.assertEqual(list_projects(studio_root=self.studio), [])
        new_project("beta", studio_root=self.studio)
        new_project("alfa", studio_root=self.studio)
        self.assertEqual(list_projects(studio_root=self.studio), ["alfa", "beta"])


class TestSegredos(BaseComStudio):
    def test_campo_novo_com_segredo_e_gravado_mascarado(self) -> None:
        projeto, destino = new_project("segredo", studio_root=self.studio)
        projeto.customizations["admin_token"] = "valor-muito-secreto"
        save_project(projeto, studio_root=self.studio)
        texto = destino.read_text(encoding="utf-8")
        self.assertNotIn("valor-muito-secreto", texto)
        self.assertIn("***", texto)


class TestInvalidacao(BaseComStudio):
    def setUp(self) -> None:
        super().setUp()
        self.projeto, _ = new_project("inv", studio_root=self.studio, server_host="doom.exemplo.com")
        for stage in (Stage.APK_ANALISADO, Stage.SERVIDOR_VALIDADO, Stage.APK_RECONSTRUIDO,
                      Stage.APK_ASSINADO):
            self.projeto.state.mark(stage)

    def test_trocar_host_invalida_build(self) -> None:
        self.projeto.set_server("outro.exemplo.com")
        self.assertFalse(self.projeto.state.has(Stage.APK_RECONSTRUIDO))
        self.assertFalse(self.projeto.state.has(Stage.APK_ASSINADO))
        self.assertTrue(self.projeto.state.has(Stage.SERVIDOR_VALIDADO))

    def test_mesmo_host_nao_invalida(self) -> None:
        self.projeto.set_server("doom.exemplo.com")
        self.assertTrue(self.projeto.state.has(Stage.APK_RECONSTRUIDO))

    def test_trocar_ca_invalida_build(self) -> None:
        self.projeto.set_ca_path("C:/ca/nova.pem")
        self.assertFalse(self.projeto.state.has(Stage.APK_RECONSTRUIDO))

    def test_trocar_apk_invalida_analise(self) -> None:
        self.projeto.set_input_apk("D:/outro.apk")
        self.assertFalse(self.projeto.state.has(Stage.APK_ANALISADO))
        self.assertFalse(self.projeto.state.has(Stage.SERVIDOR_VALIDADO))

    def test_estrategia_invalida_recusada(self) -> None:
        with self.assertRaises(ProjectError):
            self.projeto.set_patch_strategy("força-bruta")

    def test_from_dict_com_estrategia_desconhecida_recusa(self) -> None:
        dados = self.projeto.to_dict()
        dados["patch_strategy"] = "estranha"
        with self.assertRaises(ProjectError):
            Project.from_dict(dados)


if __name__ == "__main__":
    unittest.main(verbosity=2)
