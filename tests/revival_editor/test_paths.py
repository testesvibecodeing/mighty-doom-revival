#!/usr/bin/env python3
"""Regressão do isolamento de caminhos do Revival Studio.

O pipeline apaga e recria o workspace. Se `ensure_within` deixar passar um
caminho de fora, o editor destrói árvore do usuário. Estes testes travam o
comportamento antes de qualquer código de UI existir.

Execução: python tests/revival_editor/test_paths.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from revival_editor.paths import (  # noqa: E402
    InvalidProjectIdError,
    PathEscapeError,
    PathError,
    ensure_dir,
    ensure_within,
    is_within,
    project_dir,
    reset_directory,
    validate_project_id,
)


class TestValidateProjectId(unittest.TestCase):
    def test_aceita_slug_simples(self) -> None:
        for ok in ("a", "projeto", "doom-2026", "p1", "a" * 64):
            self.assertEqual(validate_project_id(ok), ok)

    def test_recusa_travessia_e_separadores(self) -> None:
        for bad in ("..", "../fora", "a/b", "a\\b", "/abs", "C:\\x", "a b", "A", "ção", "", "-x"):
            with self.assertRaises(InvalidProjectIdError, msg=f"deveria recusar {bad!r}"):
                validate_project_id(bad)

    def test_recusa_nome_reservado_do_windows(self) -> None:
        for bad in ("con", "nul", "com1", "lpt9"):
            with self.assertRaises(InvalidProjectIdError):
                validate_project_id(bad)

    def test_recusa_tipo_errado(self) -> None:
        with self.assertRaises(InvalidProjectIdError):
            validate_project_id(None)  # type: ignore[arg-type]


class TestContainment(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve() / "base"
        self.base.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_filho_direto_esta_dentro(self) -> None:
        self.assertTrue(is_within(self.base, self.base / "x" / "y"))

    def test_a_propria_base_esta_dentro(self) -> None:
        self.assertTrue(is_within(self.base, self.base))

    def test_dotdot_escapa_e_e_recusado(self) -> None:
        self.assertFalse(is_within(self.base, self.base / ".." / "fora"))
        with self.assertRaises(PathEscapeError):
            ensure_within(self.base, self.base / ".." / "fora")

    def test_prefixo_parecido_nao_conta_como_dentro(self) -> None:
        # A armadilha que str.startswith() deixaria passar:
        # /tmp/base-malicioso começa com /tmp/base mas está FORA.
        vizinho = self.base.parent / (self.base.name + "-malicioso")
        self.assertFalse(is_within(self.base, vizinho))
        with self.assertRaises(PathEscapeError):
            ensure_within(self.base, vizinho)

    def test_caminho_absoluto_de_fora_e_recusado(self) -> None:
        with self.assertRaises(PathEscapeError):
            ensure_within(self.base, Path(tempfile.gettempdir()).resolve())

    def test_ensure_within_devolve_resolvido(self) -> None:
        alvo = ensure_within(self.base, self.base / "sub" / ".." / "sub" / "f.txt")
        self.assertEqual(alvo, self.base / "sub" / "f.txt")

    def test_mensagem_de_erro_mostra_os_dois_caminhos(self) -> None:
        with self.assertRaises(PathEscapeError) as ctx:
            ensure_within(self.base, self.base / ".." / "fora", what="workspace")
        texto = str(ctx.exception)
        self.assertIn("workspace", texto)
        self.assertIn("permitido:", texto)
        self.assertIn("recebido:", texto)


class TestResetDirectory(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve() / "base"
        self.base.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_recria_vazio_e_apaga_conteudo_antigo(self) -> None:
        alvo = self.base / "decoded"
        (alvo / "profundo").mkdir(parents=True)
        (alvo / "profundo" / "lixo.txt").write_text("velho", encoding="utf-8")

        resultado = reset_directory(self.base, alvo)

        self.assertEqual(resultado, alvo)
        self.assertTrue(alvo.is_dir())
        self.assertEqual(list(alvo.iterdir()), [])

    def test_recusa_apagar_a_propria_base(self) -> None:
        marcador = self.base / "nao-apague.txt"
        marcador.write_text("importante", encoding="utf-8")
        with self.assertRaises(PathEscapeError):
            reset_directory(self.base, self.base)
        self.assertTrue(marcador.is_file(), "a base não pode ser tocada")

    def test_recusa_alvo_de_fora_sem_apagar_nada(self) -> None:
        fora = self.base.parent / "fora"
        fora.mkdir()
        vitima = fora / "arquivo-do-usuario.txt"
        vitima.write_text("nao apague", encoding="utf-8")

        with self.assertRaises(PathEscapeError):
            reset_directory(self.base, fora)

        self.assertTrue(vitima.is_file(), "nada fora da base pode ser removido")

    def test_recusa_quando_alvo_e_arquivo(self) -> None:
        arquivo = self.base / "arquivo"
        arquivo.write_text("x", encoding="utf-8")
        with self.assertRaises(PathError):
            reset_directory(self.base, arquivo)
        self.assertTrue(arquivo.is_file())


class TestProjectDir(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_monta_caminho_do_projeto(self) -> None:
        self.assertEqual(project_dir("doom-01", studio_root=self.root), self.root / "doom-01")

    def test_id_invalido_nao_vira_caminho(self) -> None:
        with self.assertRaises(InvalidProjectIdError):
            project_dir("../fora", studio_root=self.root)

    def test_ensure_dir_cria_dentro_da_base(self) -> None:
        criado = ensure_dir(self.root, self.root / "a" / "b")
        self.assertTrue(criado.is_dir())

    def test_ensure_dir_recusa_fora_da_base(self) -> None:
        with self.assertRaises(PathEscapeError):
            ensure_dir(self.root, self.root.parent / "outro")


if __name__ == "__main__":
    unittest.main(verbosity=2)
