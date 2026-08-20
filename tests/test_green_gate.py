#!/usr/bin/env python3
"""Regressões do gate falso-verde — as três formas de ficar verde sem prova.

1. arquivo de teste que engole a própria falha (`unittest.main(exit=False)`);
2. teste que existe mas o gate nunca roda (lista manual paralela à
   autodescoberta do run_tests.py);
3. fixture versionada com valor sensível que a camada de fixtures deixa passar.

Historicamente tests/test_generate_endpoint_matrix.py terminava com
`unittest.main(verbosity=2, exit=False)` seguido de `return 0` incondicional
(padrão copiado também para o recém-criado tests/test_client_harness.py) — o
processo sempre saía 0, mesmo com testes falhando, e run_tests.py /
verify_everything.py, que confiam no exit code, reportavam verde. A regra do
repositório é: arquivo de teste termina com `unittest.main(verbosity=2)` e
deixa o unittest controlar o exit code.

Este teste falhava antes da correção (flagrava os dois arquivos) e passa
depois; qualquer regressão do padrão volta a quebrar o gate.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import run_tests  # noqa: E402
import verify_everything as gate  # noqa: E402

EXIT_FALSE_RE = re.compile(r"unittest\.main\([^)]*exit\s*=\s*False")


def discovered_test_files() -> list[Path]:
    # A descoberta é a do run_tests.py, importada — reimplementá-la aqui seria
    # a mesma duplicação que este arquivo existe para proibir.
    return run_tests.descobrir()


class TestGreenGate(unittest.TestCase):
    def test_nenhum_arquivo_de_teste_engole_falha(self):
        self_path = Path(__file__).resolve()
        offenders = [
            str(path.relative_to(ROOT))
            for path in discovered_test_files()
            if path.resolve() != self_path  # este arquivo carrega o padrão como dado de teste
            and EXIT_FALSE_RE.search(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(
            offenders, [],
            "unittest.main(exit=False) sem propagação de resultado engole falha "
            "(run_tests.py/verify_everything.py confiam no exit code): use "
            "unittest.main(verbosity=2) — encontrado em: "
            + ", ".join(offenders),
        )

    def test_regex_flagra_o_padrao_historico_e_poupa_o_correto(self):
        self.assertIsNotNone(EXIT_FALSE_RE.search(
            "unittest.main(verbosity=2, exit=False)\n    return 0"))
        self.assertIsNotNone(EXIT_FALSE_RE.search(
            "unittest.main(\n    verbosity=2,\n    exit=False,\n)"))
        self.assertIsNone(EXIT_FALSE_RE.search("unittest.main(verbosity=2)"))


TESTE_SINTETICO = '''#!/usr/bin/env python3
"""Arquivo temporario da regressao do gate - apagado no tearDown."""
import sys
sys.exit(1)
'''


class TestGateRodaSuiteAutodescoberta(unittest.TestCase):
    """O gate e o run_tests.py compartilham UMA descoberta.

    Historicamente verify_everything.py tinha uma lista PYTHON_TESTS escrita à
    mão; tests/test_client_harness.py e tests/test_green_gate.py nasceram fora
    dela e o gate ficou verde sem executá-los. Estes testes falham se a lista
    manual voltar ou se um test_*.py novo e falho não derrubar a camada.
    """

    def setUp(self):
        self.dir_temp = ROOT / "tests" / "_regressao_gate_tmp"
        self.arquivo = self.dir_temp / "test_falha_sintetica.py"
        self.dir_temp.mkdir(parents=True, exist_ok=True)
        self.arquivo.write_text(TESTE_SINTETICO, encoding="utf-8")

    def tearDown(self):
        if self.arquivo.exists():
            self.arquivo.unlink()
        if self.dir_temp.exists():
            for resto in self.dir_temp.rglob("*"):
                if resto.is_file():
                    resto.unlink()
            self.dir_temp.rmdir()

    def test_o_gate_nao_tem_lista_manual_de_testes(self):
        fonte = (ROOT / "scripts" / "verify_everything.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "PYTHON_TESTS", fonte,
            "lista manual de testes de volta no gate: use a descoberta do run_tests.py")
        self.assertIs(
            gate.descobrir_testes_python, run_tests.descobrir,
            "o gate tem que reusar a MESMA função de descoberta do run_tests.py")

    def test_arquivo_novo_entra_na_descoberta(self):
        descobertos = {p.resolve() for p in run_tests.descobrir()}
        self.assertIn(
            self.arquivo.resolve(), descobertos,
            "test_*.py novo sob tests/ tem que ser autodescoberto — sem isso o "
            "gate volta a ficar verde por omissão")

    def test_teste_falho_deixa_a_camada_do_gate_vermelha(self):
        relatorio = gate.Report()
        gate.check_python_tests(relatorio, arquivos=[self.arquivo])
        self.assertEqual(relatorio.passed, 0)
        self.assertTrue(relatorio.failures, "exit != 0 tem que virar falha do gate")
        self.assertIn("test_falha_sintetica.py", relatorio.failures[0])

    def test_descoberta_vazia_reprova_em_vez_de_passar(self):
        relatorio = gate.Report()
        gate.check_python_tests(relatorio, arquivos=[])
        self.assertTrue(relatorio.failures, "suíte vazia é falha, não sucesso silencioso")


class TestGateReprovaFixtureNaoSanitizada(unittest.TestCase):
    """A camada de fixtures precisa de dentes para o placeholder de puuid.

    Vale para os dois produtores de fixture (client_harness.py e
    capture_protocol_fixtures.mjs): o que o gate cobra é o arquivo versionado.
    """

    def setUp(self):
        self.dir_temp = ROOT / "tests" / "fixtures" / "protocol" / "_regressao_gate_tmp"
        self.arquivo = self.dir_temp / "game__auth__register.json"
        self.dir_temp.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.arquivo.exists():
            self.arquivo.unlink()
        if self.dir_temp.exists():
            self.dir_temp.rmdir()

    def _escrever(self, puuid):
        self.arquivo.write_text(json.dumps({
            "endpoint": "game/auth/register",
            "provenance": "client",
            "sanitized": True,
            "request": {"method": "POST", "path": "/game/auth/register", "body": {}},
            "response": {"status": 200, "code": 1000, "body": {"user_id": 8, "puuid": puuid}},
        }, indent=2), encoding="utf-8")

    def test_puuid_cru_reprova(self):
        self._escrever("3f2504e0-4f89-11d3-9a0c-0305e82c3301")
        relatorio = gate.Report()
        gate.check_fixtures(relatorio)
        self.assertTrue(relatorio.failures, "puuid em texto claro tem que reprovar")
        self.assertIn("game__auth__register.json", relatorio.failures[0])

    def test_placeholder_passa_e_preserva_a_chave(self):
        self._escrever("<puuid>")
        relatorio = gate.Report()
        gate.check_fixtures(relatorio)
        self.assertFalse(relatorio.failures, "placeholder é a forma correta")
        corpo = json.loads(self.arquivo.read_text(encoding="utf-8"))["response"]["body"]
        self.assertIn("puuid", corpo, "a chave continua no wire; só o valor muda")


if __name__ == "__main__":
    unittest.main(verbosity=2)
