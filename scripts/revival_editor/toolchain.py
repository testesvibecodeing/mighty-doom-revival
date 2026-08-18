"""Toolchain determinística do Revival Studio (fase 3 do plano).

Por que este módulo existe — defeito real medido nesta base em 2026-08-17:

    grep -nE "java" scripts/patch-apk.sh scripts/patch-apk.bat

Os **dois** orquestradores chamam `java` do PATH. Nesta máquina o PATH tem
Java 11, enquanto `.tools/jre17/jdk-17.0.20+8-jre/bin/java.exe` está instalado e
é o exigido por AGENTS.md e pela skill `apk-patch`. Nenhum wrapper conhece o
JRE local. Este resolvedor é a fonte única — a GUI e os wrappers passam a
consumi-lo em vez de confiar no PATH.

Regras não negociáveis aqui (AGENTS.md + DEAD-ENDS #8):

- versões são **pinadas**, nunca "atualizadas para ver se resolve";
- hash divergente de JAR **bloqueia** o build, não avisa e segue;
- UnityPy tem que ser exatamente 1.25.3 — outra versão reserializa diferente e
  invalida os testes de regressão do patcher.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Iterable

from .paths import REPO_ROOT

__all__ = [
    "ToolStatus",
    "ToolchainReport",
    "APKTOOL_SHA256",
    "SIGNER_SHA256",
    "UNITYPY_VERSION",
    "MIN_JAVA_MAJOR",
    "MIN_PYTHON",
    "resolve_java",
    "check_apktool",
    "check_signer",
    "check_python",
    "check_unitypy",
    "check_pillow",
    "check_node",
    "check_adb",
    "detect_toolchain",
    "sha256_file",
]

#: Pinado em scripts/setup-patcher-tools.{bat,sh}. Fonte única aqui.
APKTOOL_SHA256 = "dbf930b076c6b9be08d57c449cacefc3bdd6b71ebd59b3066fc0e1f5b14f9423"
SIGNER_SHA256 = "e1299fd6fcf4da527dd53735b56127e8ea922a321128123b9c32d619bba1d835"

APKTOOL_VERSION = "3.0.3"
SIGNER_VERSION = "1.3.0"
UNITYPY_VERSION = "1.25.3"

MIN_JAVA_MAJOR = 17
MIN_PYTHON = (3, 11)

TOOLS_DIR = REPO_ROOT / ".tools"
APKTOOL_JAR = TOOLS_DIR / "apktool.jar"
SIGNER_JAR = TOOLS_DIR / "uber-apk-signer.jar"

#: Java 17 embarcado no repositório. Primeira opção no Windows por decisão do
#: plano (fase 3), não por acaso: é o único que sabemos ser a versão certa.
BUNDLED_JAVA = TOOLS_DIR / "jre17" / "jdk-17.0.20+8-jre" / "bin" / (
    "java.exe" if os.name == "nt" else "java"
)

#: Variável de ambiente para o usuário apontar um Java próprio.
JAVA_ENV_VAR = "REVIVAL_JAVA"

_VERSION_LINE = re.compile(r'version "([0-9][0-9._+\-]*)"')


@dataclass
class ToolStatus:
    """Estado de uma ferramenta: caminho, versão e se serve.

    `ok=False` com `required=True` bloqueia a etapa que depende dela.
    A UI mostra `detail` como instrução acionável, não como erro cru.
    """

    name: str
    ok: bool
    path: str | None = None
    version: str | None = None
    detail: str = ""
    required: bool = True
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ToolchainReport:
    tools: list[ToolStatus] = field(default_factory=list)

    def get(self, name: str) -> ToolStatus | None:
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    @property
    def blocking(self) -> list[ToolStatus]:
        """Ferramentas obrigatórias que não estão prontas."""
        return [t for t in self.tools if t.required and not t.ok]

    @property
    def ok(self) -> bool:
        return not self.blocking

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "blocking": [t.name for t in self.blocking],
            "tools": [t.to_dict() for t in self.tools],
        }


def sha256_file(path: Path, *, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for bloco in iter(lambda: handle.read(chunk), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _run(command: list[str], timeout: float = 20.0) -> tuple[int, str]:
    """Executa sem shell e devolve (exit, stdout+stderr).

    `shell=False` com lista de argumentos é regra do plano (fase 1): nunca
    montar comando concatenando caminho ou texto do usuário.
    """
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def parse_java_major(saida: str) -> int | None:
    """Extrai o major da saída de `java -version`.

    Aceita os dois formatos vivos:
      java version "11.0.18" 2023-01-17 LTS      -> 11
      openjdk version "17.0.20" 2026-07-21       -> 17
      java version "1.8.0_382"                   -> 8   (esquema pré-9)
    """
    match = _VERSION_LINE.search(saida or "")
    if not match:
        return None
    bruto = match.group(1)
    partes = bruto.split(".")
    try:
        primeiro = int(partes[0])
    except (ValueError, IndexError):
        return None
    if primeiro == 1 and len(partes) > 1:
        try:
            return int(partes[1])
        except ValueError:
            return None
    return primeiro


def _java_candidates(explicit: str | Path | None) -> Iterable[tuple[Path, str]]:
    """Ordem de resolução exigida pela fase 3 do plano.

    1. escolha explícita do usuário (parâmetro ou env `REVIVAL_JAVA`);
    2. o JRE 17 embarcado em `.tools/`;
    3. o PATH — e **só** se for 17+.

    O explícito vem antes do embarcado para o usuário poder apontar um JDK
    próprio; o PATH vem por último porque é justamente o que está errado nesta
    máquina.
    """
    if explicit:
        yield Path(explicit), "explícito"
    do_ambiente = os.environ.get(JAVA_ENV_VAR)
    if do_ambiente:
        yield Path(do_ambiente), f"variável {JAVA_ENV_VAR}"
    if BUNDLED_JAVA.is_file():
        yield BUNDLED_JAVA, "JRE 17 embarcado (.tools/jre17)"
    do_path = shutil.which("java")
    if do_path:
        yield Path(do_path), "PATH"


def resolve_java(explicit: str | Path | None = None) -> ToolStatus:
    """Resolve o Java a usar para apktool e uber-apk-signer.

    Nunca devolve um Java < 17 como `ok`. Se o único disponível for antigo, o
    `detail` diz exatamente o que fazer — o plano exige que "Java 11 seja
    rejeitado com instrução clara".
    """
    tentativas: list[str] = []
    for caminho, origem in _java_candidates(explicit):
        if not caminho.is_file():
            tentativas.append(f"{origem}: {caminho} (não existe)")
            continue
        code, saida = _run([str(caminho), "-version"])
        major = parse_java_major(saida)
        if code != 0 or major is None:
            tentativas.append(f"{origem}: {caminho} (não respondeu a -version)")
            continue
        if major < MIN_JAVA_MAJOR:
            tentativas.append(f"{origem}: {caminho} (Java {major}, precisa de {MIN_JAVA_MAJOR}+)")
            continue
        linha = (saida.strip().splitlines() or [""])[0]
        return ToolStatus(
            name="java",
            ok=True,
            path=str(caminho),
            version=str(major),
            detail=linha,
            source=origem,
        )

    if BUNDLED_JAVA.is_file():
        instrucao = f"Use o JRE embarcado: {BUNDLED_JAVA}"
    else:
        instrucao = (
            f"Baixe o JRE 17 com scripts/setup-patcher-tools.* ou aponte "
            f"{JAVA_ENV_VAR} para um Java {MIN_JAVA_MAJOR}+."
        )
    return ToolStatus(
        name="java",
        ok=False,
        detail=(
            f"nenhum Java {MIN_JAVA_MAJOR}+ utilizável. {instrucao}\n"
            "Tentado:\n  " + "\n  ".join(tentativas or ["(nenhum candidato)"])
        ),
    )


def _check_jar(nome: str, jar: Path, esperado: str, versao: str) -> ToolStatus:
    """Valida presença e SHA-256 pinado de um JAR.

    Hash divergente **bloqueia**: um apktool trocado reserializa diferente e
    invalida silenciosamente os testes calibrados nesta toolchain
    (DEAD-ENDS #8).
    """
    if not jar.is_file():
        return ToolStatus(
            name=nome,
            ok=False,
            detail=f"{jar} ausente. Rode scripts/setup-patcher-tools.* para baixar {nome} {versao}.",
        )
    real = sha256_file(jar)
    if real != esperado:
        return ToolStatus(
            name=nome,
            ok=False,
            path=str(jar),
            detail=(
                f"SHA-256 não confere — build BLOQUEADO.\n"
                f"  esperado: {esperado}\n"
                f"  no disco: {real}\n"
                f"Apague o arquivo e rode scripts/setup-patcher-tools.* de novo. "
                f"Não substitua por outra versão."
            ),
        )
    return ToolStatus(name=nome, ok=True, path=str(jar), version=versao, detail=f"SHA-256 confere ({versao})")


def check_apktool() -> ToolStatus:
    return _check_jar("apktool", APKTOOL_JAR, APKTOOL_SHA256, APKTOOL_VERSION)


def check_signer() -> ToolStatus:
    return _check_jar("uber-apk-signer", SIGNER_JAR, SIGNER_SHA256, SIGNER_VERSION)


def check_python() -> ToolStatus:
    atual = sys.version_info[:3]
    minimo = ".".join(str(p) for p in MIN_PYTHON)
    if atual[:2] < MIN_PYTHON:
        return ToolStatus(
            name="python",
            ok=False,
            path=sys.executable,
            version=".".join(str(p) for p in atual),
            detail=f"Revival Studio exige Python {minimo}+.",
        )
    return ToolStatus(
        name="python",
        ok=True,
        path=sys.executable,
        version=".".join(str(p) for p in atual),
        detail=f"atende ao mínimo {minimo}",
    )


def check_unitypy() -> ToolStatus:
    try:
        import UnityPy  # noqa: PLC0415
    except ImportError:
        return ToolStatus(
            name="UnityPy",
            ok=False,
            detail=f"não instalado. Use exatamente: pip install UnityPy=={UNITYPY_VERSION}",
        )
    versao = getattr(UnityPy, "__version__", "desconhecida")
    if versao != UNITYPY_VERSION:
        return ToolStatus(
            name="UnityPy",
            ok=False,
            version=versao,
            path=getattr(UnityPy, "__file__", None),
            detail=(
                f"versão {versao} instalada; o projeto exige exatamente {UNITYPY_VERSION}. "
                "Outra versão reserializa bundles de forma diferente e invalida os testes "
                "do patcher (research/DEAD-ENDS.md #8). Não 'atualize para resolver'."
            ),
        )
    return ToolStatus(
        name="UnityPy",
        ok=True,
        version=versao,
        path=getattr(UnityPy, "__file__", None),
        detail="versão exata exigida pelo projeto",
    )


def check_pillow() -> ToolStatus:
    """Pillow é obrigatória só para a loading screen; não bloqueia o patch."""
    try:
        import PIL  # noqa: PLC0415
    except ImportError:
        return ToolStatus(
            name="Pillow",
            ok=False,
            required=False,
            detail="não instalada. Necessária para a aba Loading screen: pip install Pillow",
        )
    return ToolStatus(
        name="Pillow",
        ok=True,
        required=False,
        version=getattr(PIL, "__version__", "desconhecida"),
        detail="disponível para composição da loading screen",
    )


def check_node() -> ToolStatus:
    """Node é obrigatório só para o servidor local e para `npm test`."""
    caminho = shutil.which("node")
    if not caminho:
        return ToolStatus(
            name="node",
            ok=False,
            required=False,
            detail="não encontrado no PATH. Necessário para o servidor Revival (>= 22.5.0, node:sqlite).",
        )
    code, saida = _run([caminho, "--version"])
    versao = (saida or "").strip().lstrip("v")
    if code != 0 or not versao:
        return ToolStatus(name="node", ok=False, required=False, path=caminho,
                          detail="node não respondeu a --version")
    try:
        major, minor = (int(p) for p in versao.split(".")[:2])
    except ValueError:
        return ToolStatus(name="node", ok=True, required=False, path=caminho, version=versao,
                          detail="versão não reconhecida; siga com atenção")
    if (major, minor) < (22, 5):
        return ToolStatus(
            name="node", ok=False, required=False, path=caminho, version=versao,
            detail="o servidor usa node:sqlite, que exige Node >= 22.5.0 (o CI usa 24 LTS).",
        )
    return ToolStatus(name="node", ok=True, required=False, path=caminho, version=versao,
                      detail="atende ao mínimo 22.5.0 do servidor")


def check_adb() -> ToolStatus:
    """adb é opcional até a aba Dispositivo (exigência explícita da fase 3)."""
    caminho = shutil.which("adb")
    if not caminho:
        return ToolStatus(
            name="adb",
            ok=False,
            required=False,
            detail="não encontrado no PATH. Opcional: só a aba Dispositivo/ADB precisa dele.",
        )
    code, saida = _run([caminho, "version"])
    primeira = (saida.strip().splitlines() or [""])[0]
    return ToolStatus(
        name="adb",
        ok=code == 0,
        required=False,
        path=caminho,
        version=primeira,
        detail="disponível para instalação e logcat",
    )


def detect_toolchain(*, java_path: str | Path | None = None) -> ToolchainReport:
    """Levanta o estado de toda a toolchain, sem baixar nem instalar nada.

    Baixar exige confirmação explícita do usuário e acontece pelo botão
    "Preparar ferramentas", nunca como efeito colateral de abrir a tela.
    """
    return ToolchainReport(
        tools=[
            check_python(),
            check_unitypy(),
            resolve_java(java_path),
            check_apktool(),
            check_signer(),
            check_pillow(),
            check_node(),
            check_adb(),
        ]
    )
