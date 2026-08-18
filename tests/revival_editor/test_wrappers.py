#!/usr/bin/env python3
"""Regressão do encaminhamento dos wrappers (planos §6.1 e §9.2).

O inventário abaixo é a tabela da §6.1 em forma executável: cada wrapper
declara a ação-alvo do Revival Studio e um estado:

- PRONTO — a ação já existe no registro (`actions.ACTIONS`) e o wrapper
  **precisa** encaminhar para o launcher quando chamado sem argumentos em
  sessão interativa;
- PENDENTE — a ação ainda não existe; quando a fase correspondente a
  implementar, este teste **falha sozinho** até o encaminhamento ser
  adicionado. É o mecanismo que impede "pipeline pronto, wrapper esquecido";
- NUNCA — deploy destrutivo/produção: nunca encaminha, nunca executa por
  padrão (install.sh / uninstall.sh).

Também guarda as duas regras de recursão da §9.2: nenhum wrapper chama outro
wrapper, e o launcher Python não referencia wrapper nenhum.

Execução: python tests/revival_editor/test_wrappers.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from revival_editor.actions import ACTIONS  # noqa: E402

PRONTO = "pronto"
PENDENTE = "pendente"
NUNCA = "nunca"

#: base do nome (sem extensão) -> (ação-alvo, estado, [marcas headless preservadas])
WRAPPER_INVENTORY: dict[str, tuple[str | None, str, tuple[str, ...]]] = {
    "patch-apk": (
        "pipeline.completo",
        PRONTO,  # fase 6: pipeline.py + ação pipeline.completo no registro
        ("apktool",),
    ),
    "loading-screen-editor": (
        "visuals.loading_screen",
        PRONTO,  # fase 7: aba Visuais no Studio
        ("loading_screen_editor.py",),
    ),
    "analyze-official-apk": (
        "projeto.analisar",
        PRONTO,
        ("analyze_apk.py",),
    ),
    "setup-patcher-tools": (
        "ferramentas.preparar",
        PRONTO,  # fase 3: botão Preparar ferramentas no menu Ferramentas
        ("apktool",),
    ),
    "setup-server": (
        "servidor.preparar",
        PRONTO,  # §6.1/§9.2 fechadas: serviço server.py + menu Servidor
        ("server",),
    ),
    "start-server": (
        "servidor.iniciar",
        PRONTO,  # §6.1/§9.2 fechadas: start_server com PID + health check
        ("server",),
    ),
    "install": (None, NUNCA, ()),  # deploy: nunca encaminhar
    "uninstall": (None, NUNCA, ()),
}

#: Wrappers do próprio launcher — não são encaminhadores, são a porta de entrada.
LAUNCHER_WRAPPERS = ("revival-studio",)

FORWARD_MARKER = "studio-forward"
LAUNCHER_REF = "revival_studio.py"


def _ids_registrados() -> set[str]:
    return {spec.action_id for spec in ACTIONS}


def _arquivos_da_base(base: str) -> list[Path]:
    return [p for p in SCRIPTS_DIR.glob(f"{base}.*") if p.suffix in {".bat", ".sh"}]


def _todos_wrappers() -> list[Path]:
    return [
        p
        for p in SCRIPTS_DIR.iterdir()
        if p.suffix in {".bat", ".sh"}
        and p.stem not in LAUNCHER_WRAPPERS
    ]


class TestInventario(unittest.TestCase):
    def test_inventario_cobre_todos_os_wrappers(self) -> None:
        """§6.1: a tabela precisa listar tudo que existe em scripts/."""
        no_inventario = {base for base in WRAPPER_INVENTORY}
        encontrados = {p.stem for p in _todos_wrappers()}
        faltando = encontrados - no_inventario
        self.assertEqual(faltando, set(), f"wrapper sem inventário: {faltando}")
        fantasmas = no_inventario - encontrados
        self.assertEqual(fantasmas, set(), f"inventário aponta wrapper inexistente: {fantasmas}")

    def test_toda_entrada_pronto_tem_acao_real(self) -> None:
        registradas = _ids_registrados()
        for base, (acao, estado, _) in WRAPPER_INVENTORY.items():
            if estado == PRONTO:
                self.assertIn(acao, registradas, f"{base}: PRONTO sem ação no registro")


class TestEncaminhamento(unittest.TestCase):
    def test_pronto_encaminha_para_o_launcher(self) -> None:
        for base, (acao, estado, _) in WRAPPER_INVENTORY.items():
            if estado != PRONTO:
                continue
            for caminho in _arquivos_da_base(base):
                texto = caminho.read_text(encoding="utf-8", errors="replace")
                self.assertIn(FORWARD_MARKER, texto, f"{caminho.name} sem marca studio-forward")
                self.assertIn(LAUNCHER_REF, texto, f"{caminho.name} não referencia o launcher")

    def test_pendente_ainda_nao_encaminha(self) -> None:
        """Meio-encaminhamento é pior que nenhum: PENDENTE não deve ter o branch."""
        for base, (_, estado, _) in WRAPPER_INVENTORY.items():
            if estado != PENDENTE:
                continue
            for caminho in _arquivos_da_base(base):
                texto = caminho.read_text(encoding="utf-8", errors="replace")
                self.assertNotIn(
                    FORWARD_MARKER,
                    texto,
                    f"{caminho.name} marcado PENDENTE mas já encaminha — atualize o inventário",
                )

    def test_acao_registrada_exige_encaminhamento(self) -> None:
        """A regra invertida: se a ação-alvo existe, o wrapper NÃO pode ficar PENDENTE.

        É o que fecha a §9.2 mecânicamente: a fase que criar a ação quebra este
        teste até o wrapper aprender a encaminhar.
        """
        registradas = _ids_registrados()
        for base, (acao, estado, _) in WRAPPER_INVENTORY.items():
            if estado == PENDENTE and acao in registradas:
                self.fail(
                    f"{base}: ação {acao} já existe no registro — mude o inventário "
                    "para PRONTO e adicione o encaminhamento ao wrapper"
                )

    def test_caminho_headless_preservado(self) -> None:
        """§9.2: encaminhar não pode apagar o caminho headless (CI/VPS)."""
        for base, (_, estado, marcas) in WRAPPER_INVENTORY.items():
            if not marcas:
                continue
            for caminho in _arquivos_da_base(base):
                texto = caminho.read_text(encoding="utf-8", errors="replace")
                for marca in marcas:
                    self.assertIn(marca, texto, f"{caminho.name} perdeu o núcleo headless: {marca!r}")

    def test_deploy_nunca_encaminha(self) -> None:
        for base, (_, estado, _) in WRAPPER_INVENTORY.items():
            if estado != NUNCA:
                continue
            for caminho in _arquivos_da_base(base):
                texto = caminho.read_text(encoding="utf-8", errors="replace")
                self.assertNotIn(LAUNCHER_REF, texto, f"{caminho.name} é deploy: não encaminha")


class TestRecursao(unittest.TestCase):
    """§9.2: *"impedir recursão: o Python launcher nunca deve chamar um wrapper
    que chama o Python launcher de volta"*.

    Wrappers que se chamam entre si por razões legítimas de pipeline headless
    (patch-apk chama setup-patcher-tools quando falta ferramenta) podem
    continuar **desde que passem `--headless` explícito** — o branch de
    encaminhamento só dispara sem argumentos, então a chamada argumentada não
    pode abrir GUI nem gerar loop. O que este teste proíbe é invocar um
    encaminhador (PRONTO) sem essa proteção.
    """

    @staticmethod
    def _linhas_executaveis(texto: str) -> list[str]:
        import re

        saida = []
        heredoc_ate: str | None = None  # delimitador do <<'EOF' aberto
        for linha in texto.splitlines():
            l = linha.strip()
            if heredoc_ate is not None:
                # corpo de heredoc é texto impresso (documentação), não comando
                if l == heredoc_ate:
                    heredoc_ate = None
                continue
            if not l or l.startswith("#") or l.startswith("rem ") or l == "rem":
                continue
            if l.startswith("echo ") or l.startswith("echo.") or l.startswith('echo"'):
                continue
            saida.append(l)
            abertura = re.search(r"<<-?\s*['\"]?(\w+)", l)
            if abertura:
                heredoc_ate = abertura.group(1)
        return saida

    def test_nenhum_wrapper_invoca_wrapper_encaminhador(self) -> None:
        prontos = [base for base, (_, estado, _) in WRAPPER_INVENTORY.items() if estado == PRONTO]
        for caminho in _todos_wrappers():
            texto = caminho.read_text(encoding="utf-8", errors="replace")
            for linha in self._linhas_executaveis(texto):
                if "--headless" in linha:
                    continue  # chamada argumentada: o branch forward exige zero args
                for base in prontos:
                    if base == caminho.stem:
                        continue
                    self.assertNotIn(
                        f"{base}.sh",
                        linha,
                        f"{caminho.name} invoca {base}.sh (encaminhador) sem --headless — "
                        "abrira a GUI no meio de um fluxo headless",
                    )
                    self.assertNotIn(
                        f"{base}.bat",
                        linha,
                        f"{caminho.name} invoca {base}.bat (encaminhador) sem --headless — "
                        "abrira a GUI no meio de um fluxo headless",
                    )

    def test_launcher_nao_referencia_wrapper(self) -> None:
        """O launcher (e todo o revival_editor/) não invoca wrapper nenhum.

        Docstring e comentário podem *citar* um wrapper como documentação
        (toolchain.py narra o defeito do java do PATH citando patch-apk.sh) —
        o que não pode existir é o nome aparecendo em string de **código**,
        que é como um subprocesso seria montado. Por isso a análise é por AST,
        não por texto bruto.

        Exceção deliberada (fase 3): a ação "Preparar ferramentas" executa o
        script oficial de setup em modo `--headless` — o branch de
        encaminhamento exige zero argumentos, então essa chamada não pode
        voltar ao launcher. A exceção vale apenas para chamadas cujo argumento
        literal `--headless` está na mesma invocação.
        """
        import ast

        alvo = SCRIPTS_DIR / "revival_studio.py"
        self.assertTrue(alvo.is_file(), "launcher ausente")
        fontes = [alvo, *sorted((SCRIPTS_DIR / "revival_editor").rglob("*.py"))]
        # nome exato de arquivo executável — menção em prosa ("setup-patcher-tools.*")
        # é instrução ao usuário, não chamada de subprocesso.
        nomes = [f"{base}{ext}" for base in WRAPPER_INVENTORY for ext in (".sh", ".bat")]
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
            # strings dentro de uma invocação (lista de comando ou chamada)
            # que contém --headless: protegidas por construção — o branch de
            # encaminhamento exige zero argumentos, logo não há recursão.
            permitidas: set[int] = set()
            for no in ast.walk(arvore):
                if not isinstance(no, (ast.List, ast.Call)):
                    continue
                subliterais = [
                    s for s in ast.walk(no)
                    if isinstance(s, ast.Constant) and isinstance(s.value, str)
                ]
                if any(s.value.strip() == "--headless" for s in subliterais):
                    permitidas.update(id(s) for s in subliterais)
            for no in ast.walk(arvore):
                if (
                    isinstance(no, ast.Constant)
                    and isinstance(no.value, str)
                    and id(no) not in docstrings
                    and id(no) not in permitidas
                ):
                    for nome in nomes:
                        self.assertNotIn(
                            nome,
                            no.value,
                            f"{fonte.relative_to(SCRIPTS_DIR)} usa {nome}* em código — "
                            "recursão launcher→wrapper proibida (exceto com --headless)",
                        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
