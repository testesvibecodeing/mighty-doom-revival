#!/usr/bin/env python3
"""Regressão dos scripts shell canônicos (planos §6.1 e regra 1.8).

Histórico: os wrappers de compatibilidade (.bat/.sh encaminhadores para o
Studio) foram **aposentados em 2026-08-18** por decisão do mantenedor — o
Studio e os serviços Python são a arquitetura; as cópias antigas foram
estacionadas em `tmp/` local e seguem recuperáveis no histórico do Git.
No mesmo dia o mantenedor pediu de volta **o par de launcher** do Studio
(`revival-studio.{bat,sh}`), que voltou como launcher puro.

O que permanece em scripts/ é exatamente:

- `install.sh` — instalação/deploy do servidor no VPS (regra 1.8: nunca
  convertido nem removido);
- `uninstall.sh` — remoção destrutiva de deploy (regra 1.8);
- `revival-studio.bat` / `revival-studio.sh` — launcher do Studio para
  Windows e Linux/Mac (pedido explícito do mantenedor).

O que este arquivo garante:

1. esses três grupos existem e **nenhum outro** .bat/.sh pode voltar para
   scripts/ sem passar por aqui (senão a porta de entrada vira ambígua);
2. deploy NUNCA encaminha para o launcher do Studio (regra 1.8 + §9.2);
3. o launcher abre exatamente `revival_studio.py` e nada mais;
4. o launcher Python (e todo o revival_editor/) não referencia script
   shell de scripts/ em código — nada da GUI pode virar chamada a .sh/.bat.

Execução: python tests/revival_editor/test_wrappers.py
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

#: Par de deploy permanente (regra 1.8) + launcher do Studio (pedido do
#: mantenedor em 2026-08-18). Tudo que voltar a aparecer em scripts/ além
#: disso quebra o teste — wrapper aposentado é wrapper morto.
DEPLOY_PAIR = ("install", "uninstall")
LAUNCHER_STEM = "revival-studio"
STEMS_CANONICOS = {*DEPLOY_PAIR, LAUNCHER_STEM}

LAUNCHER_REF = "revival_studio.py"


def _shells_em_scripts() -> list[Path]:
    return [
        p
        for p in SCRIPTS_DIR.iterdir()
        if p.suffix in {".bat", ".sh"}
    ]


class TestParDeDeploy(unittest.TestCase):
    def test_somente_deploy_e_launcher_existem(self) -> None:
        """scripts/ não pode acumular .bat/.sh de novo."""
        bases = {p.stem for p in _shells_em_scripts()}
        self.assertEqual(
            bases, STEMS_CANONICOS,
            f"scripts/ deve conter só {sorted(STEMS_CANONICOS)}; "
            f"extras: {bases - STEMS_CANONICOS}",
        )

    def test_deploy_e_executavel_no_conteudo(self) -> None:
        """Sanidade mínima: os dois são scripts shell de verdade."""
        for base in DEPLOY_PAIR:
            caminho = SCRIPTS_DIR / f"{base}.sh"
            self.assertTrue(caminho.is_file(), f"{base}.sh ausente")
            texto = caminho.read_text(encoding="utf-8", errors="replace")
            self.assertTrue(texto.startswith("#!"), f"{base}.sh sem shebang")

    def test_deploy_nunca_encaminha_para_o_studio(self) -> None:
        """install/uninstall são deploy puro: nunca abrem a GUI."""
        for base in DEPLOY_PAIR:
            caminho = SCRIPTS_DIR / f"{base}.sh"
            texto = caminho.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn(
                LAUNCHER_REF, texto,
                f"{caminho.name} é deploy: não encaminha para o Studio",
            )


class TestLauncherDoStudio(unittest.TestCase):
    """O par revival-studio.{bat,sh}: existe, é launcher puro e abre o .py."""

    def test_par_existe_com_shebang_no_sh(self) -> None:
        bat = SCRIPTS_DIR / "revival-studio.bat"
        sh = SCRIPTS_DIR / "revival-studio.sh"
        self.assertTrue(bat.is_file(), "revival-studio.bat ausente")
        self.assertTrue(sh.is_file(), "revival-studio.sh ausente")
        self.assertTrue(
            sh.read_text(encoding="utf-8", errors="replace").startswith("#!"),
            "revival-studio.sh sem shebang",
        )

    def test_launcher_abre_so_o_revival_studio_py(self) -> None:
        """Launcher puro: invoca o .py e não orquestra mais nada."""
        for caminho in (SCRIPTS_DIR / "revival-studio.bat",
                        SCRIPTS_DIR / "revival-studio.sh"):
            texto = caminho.read_text(encoding="utf-8", errors="replace")
            self.assertIn(LAUNCHER_REF, texto,
                          f"{caminho.name} não abre {LAUNCHER_REF}")
            for proibido in ("setup-server", "start-server", "patch-apk",
                             "install.sh", "uninstall.sh"):
                self.assertNotIn(
                    proibido, texto,
                    f"{caminho.name} referencia {proibido} — launcher não orquestra",
                )


class TestLauncherNaoReferenciaShell(unittest.TestCase):
    """O launcher (e todo o revival_editor/) não invoca script shell de
    scripts/ — a GUI só existe em Python; chamar .sh/.bat de volta seria o
    tipo de recursão que a §9.2 proibia.

    Docstring pode *citar* um script como documentação; o que não pode
    existir é o nome aparecendo em string de **código**, que é como um
    subprocesso seria montado. Por isso a análise é por AST.
    """

    def test_nenhum_nome_de_shell_em_codigo(self) -> None:
        alvo = SCRIPTS_DIR / "revival_studio.py"
        self.assertTrue(alvo.is_file(), "launcher ausente")
        fontes = [alvo, *sorted((SCRIPTS_DIR / "revival_editor").rglob("*.py"))]
        nomes = [f"{base}{ext}" for base in DEPLOY_PAIR for ext in (".sh", ".bat")]
        for fonte in fontes:
            arvore = ast.parse(fonte.read_text(encoding="utf-8", errors="replace"))
            docstrings: set[int] = set()
            for no in ast.walk(arvore):
                if isinstance(no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    primeiro = no.body[0] if no.body else None
                    if (
                        isinstance(primeiro, ast.Expr)
                        and isinstance(primeiro.value, ast.Constant)
                        and isinstance(primeiro.value.value, str)
                    ):
                        docstrings.add(id(primeiro.value))
            for no in ast.walk(arvore):
                if (
                    isinstance(no, ast.Constant)
                    and isinstance(no.value, str)
                    and id(no) not in docstrings
                ):
                    for nome in nomes:
                        self.assertNotIn(
                            nome,
                            no.value,
                            f"{fonte.relative_to(SCRIPTS_DIR)} usa {nome} em código — "
                            "a GUI não invoca script shell de scripts/",
                        )


class TestContratoDeProducaoDoInstalador(unittest.TestCase):
    """O install.sh não pode mais nascer um servidor de produção doente.

    Medido em 2026-08-23: o health público rodava `research_mode=true` e sem
    identidade porque o instalador copiava o `.env` do exemplo (RESEARCH_MODE
    ligado, default de pesquisa) e nunca sobrescrevia para produção. O gate de
    health do próprio instalador só conferia client/api_version — deixava
    passar um servidor que o preflight do Studio (`productionReadiness` de
    server/src/instance.js) recusaria.

    Bash não roda na suíte Windows do projeto; a regressão é por invariantes
    de texto no script, como o restante deste arquivo.
    """

    def setUp(self) -> None:
        self.install = (SCRIPTS_DIR / "install.sh").read_text(
            encoding="utf-8", errors="replace"
        )

    def test_producao_desliga_research_mode(self) -> None:
        self.assertIn(
            "set_env_var RESEARCH_MODE false", self.install,
            "instalador deve fixar RESEARCH_MODE=false para produção",
        )

    def test_producao_define_identidade_de_instancia(self) -> None:
        for chave in ("REVIVAL_INSTANCE_ID", "REVIVAL_ENVIRONMENT"):
            self.assertIn(
                f"set_env_var { chave }", self.install,
                f"instalador deve definir {chave} no .env de produção",
            )

    def test_gate_de_health_reprova_research_e_revisao_velha(self) -> None:
        for marcador in ('payload.get("research_mode") is not False',
                         'payload.get("contract_revision")',
                         'payload.get("instance_id")',
                         'payload.get("build_id")'):
            self.assertIn(
                marcador, self.install,
                f"gate de health do instalador deve recusar: faltou {marcador}",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
