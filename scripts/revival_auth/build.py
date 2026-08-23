"""Compila a RevivalAuthActivity e a transforma em um `classesN.dex`.

Escolha de toolchain (feita por disponibilidade real, não por preferência):

- **Java + d8** quando existir um `javac` e o `d8.jar` das build-tools. É o
  caminho escolhido nesta máquina: `javac` 11 (Oracle JDK em `D:\\DevPrograms`)
  e `d8.jar` das build-tools 34.0.0, executado pelo JRE 17 já pinado do projeto.
- **smali via Apktool** só entraria se não houvesse compilador Java utilizável.

O `.dex` gerado contém APENAS a Activity do Revival — nada do APK original é
recompilado. Ele entra no APK como `classes3.dex` (o cliente já traz
`classes.dex` e `classes2.dex`), que o Android carrega junto com os demais.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ANDROID_DIR = Path(__file__).resolve().parent / "android"
ACTIVITY_SOURCE = ANDROID_DIR / "RevivalAuthActivity.java"
ACTIVITY_CLASS = "br.com.revival.auth.RevivalAuthActivity"

# JRE pinado do projeto (AGENTS.md): apktool/uber-apk-signer/d8 exigem 17+.
PINNED_JRE = ROOT / ".tools" / "jre17" / "jdk-17.0.20+8-jre" / "bin" / "java.exe"


class BuildError(Exception):
    """Toolchain ausente ou compilação falhou. Nunca degrada em silêncio."""


@dataclass
class Toolchain:
    javac: Path
    android_jar: Path
    d8_jar: Path
    java: Path
    versions: dict = field(default_factory=dict)

    def describe(self) -> dict:
        return {
            "javac": str(self.javac),
            "android_jar": self.android_jar.name,
            "android_jar_sha256": _sha256(self.android_jar)[:16],
            "d8_jar": str(self.d8_jar),
            "d8_jar_sha256": _sha256(self.d8_jar)[:16],
            "java_runtime": str(self.java),
            **self.versions,
        }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _android_sdk() -> Path:
    for candidato in (os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
                      Path.home() / "AppData/Local/Android/Sdk", Path.home() / "Android/Sdk"):
        if not candidato:
            continue
        caminho = Path(candidato)
        if caminho.is_dir():
            return caminho
    raise BuildError("Android SDK não encontrado (defina ANDROID_HOME)")


def _find_javac() -> Path:
    """`javac` do PATH ou de um JDK conhecido. Nunca baixa nada."""
    achado = shutil.which("javac")
    if achado:
        return Path(achado)
    for raiz in (os.environ.get("JAVA_HOME"), "D:/DevPrograms", "C:/Program Files/Java"):
        if not raiz:
            continue
        base = Path(raiz)
        for candidato in (base / "bin" / "javac.exe", *base.glob("*/bin/javac.exe")):
            if candidato.is_file():
                return candidato
    raise BuildError(
        "nenhum javac encontrado. Instale um JDK ou aponte JAVA_HOME; "
        "o fallback documentado é gerar a Activity em smali pelo Apktool.")


def detect_toolchain() -> Toolchain:
    sdk = _android_sdk()
    javac = _find_javac()

    plataformas = sorted((sdk / "platforms").glob("android-*/android.jar"),
                         key=lambda p: int(p.parent.name.split("-")[1]), reverse=True)
    if not plataformas:
        raise BuildError("nenhum android.jar em platforms/ do SDK")
    # API 34 = targetSdk do cliente 1.13.1; usa a mais alta disponível <= 35.
    android_jar = next((p for p in plataformas if p.parent.name == "android-34"), plataformas[0])

    d8_candidatos = sorted((sdk / "build-tools").glob("*/lib/d8.jar"), reverse=True)
    if not d8_candidatos:
        raise BuildError("d8.jar não encontrado nas build-tools do SDK")

    java = PINNED_JRE if PINNED_JRE.is_file() else Path(shutil.which("java") or "java")

    versoes = {}
    try:
        saida = subprocess.run([str(javac), "-version"], capture_output=True, text=True, timeout=60)
        versoes["javac_version"] = (saida.stdout + saida.stderr).strip()
    except Exception:
        versoes["javac_version"] = "desconhecida"
    return Toolchain(javac=javac, android_jar=android_jar, d8_jar=d8_candidatos[0],
                     java=java, versions=versoes)


BG_PLACEHOLDER = "@@REVIVAL_BG_B64_ENTRIES@@"
BG_CHUNK_SIZE = 4000  # << limite de 65535 bytes UTF-8 por literal String do classfile
BG_MAX_BYTES = 2 * 1024 * 1024  # orçamento de dex; fundo é cosmético, não vale inflar o APK
_BASE64_CHUNK_RE = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")


def _encode_background(background_png: Path | None) -> str:
    """PNG local -> literal de array Java (string vazia = sem fundo, cai no
    fallback solido). O arquivo NUNCA é lido de um caminho versionado no git —
    quem chama decide a origem; aqui só valida e fatia."""
    if background_png is None:
        return ""
    background_png = Path(background_png)
    if not background_png.is_file():
        raise BuildError(f"background_png não existe: {background_png}")
    dados = background_png.read_bytes()
    if len(dados) > BG_MAX_BYTES:
        raise BuildError(
            f"background_png tem {len(dados)} bytes, acima do orçamento de {BG_MAX_BYTES}")
    b64 = base64.b64encode(dados).decode("ascii")
    partes = [b64[i:i + BG_CHUNK_SIZE] for i in range(0, len(b64), BG_CHUNK_SIZE)]
    for parte in partes:
        if not _BASE64_CHUNK_RE.match(parte):
            # Nunca deveria acontecer (saída do próprio base64.b64encode), mas
            # isto vai para dentro de um literal Java: falha alto e cedo.
            raise BuildError("chunk de base64 com caractere fora do alfabeto esperado")
    return ", ".join(f'"{parte}"' for parte in partes)


def render_source(*, base_url: str, api_version: str, client_version: str,
                  unity_activity: str, background_png: Path | None = None) -> str:
    """Injeta a configuração do pipeline. Nada de URL de produção no .java.

    `background_png` é OPCIONAL e nunca deve apontar para um caminho
    versionado: a imagem em si não entra no git (regra 1 do AGENTS.md — o
    `.gitignore` já bloqueia `*.png`). Sem ela, a tela usa o fundo sólido.
    """
    if not base_url.startswith(("http://", "https://")):
        raise BuildError(f"base_url inválida: {base_url!r}")
    fonte = ACTIVITY_SOURCE.read_text(encoding="utf-8")
    substituicoes = {
        "@@REVIVAL_BASE_URL@@": base_url.rstrip("/"),
        "@@REVIVAL_API_VERSION@@": api_version,
        "@@REVIVAL_CLIENT_VERSION@@": client_version,
        "@@REVIVAL_UNITY_ACTIVITY@@": unity_activity,
    }
    for marcador, valor in substituicoes.items():
        if marcador not in fonte:
            raise BuildError(f"marcador ausente na fonte: {marcador}")
        if '"' in valor or "\\" in valor:
            raise BuildError(f"valor com caractere proibido para literal Java: {marcador}")
        fonte = fonte.replace(marcador, valor)
    if BG_PLACEHOLDER not in fonte:
        raise BuildError(f"marcador ausente na fonte: {BG_PLACEHOLDER}")
    fonte = fonte.replace(BG_PLACEHOLDER, _encode_background(background_png))
    return fonte


def build_dex(*, base_url: str, api_version: str, client_version: str,
              unity_activity: str, out_dex: Path,
              toolchain: Toolchain | None = None,
              background_png: Path | None = None) -> dict:
    """Compila + dexa. Devolve relatório sanitizado (sem segredo algum)."""
    tc = toolchain or detect_toolchain()
    fonte = render_source(base_url=base_url, api_version=api_version,
                          client_version=client_version, unity_activity=unity_activity,
                          background_png=background_png)

    with tempfile.TemporaryDirectory(prefix="revival-auth-") as tmp:
        trabalho = Path(tmp)
        pacote = trabalho / "src" / "br" / "com" / "revival" / "auth"
        pacote.mkdir(parents=True)
        java_file = pacote / "RevivalAuthActivity.java"
        java_file.write_text(fonte, encoding="utf-8")

        classes = trabalho / "classes"
        classes.mkdir()
        # `--release 8`: bytecode que o d8 aceita sem depender do JDK usado.
        compilar = subprocess.run(
            # `-encoding UTF-8`: sem isso o javac usa o encoding da plataforma
            # (cp1252 no Windows) e os acentos da UI viram mojibake na tela.
            [str(tc.javac), "--release", "8", "-nowarn", "-encoding", "UTF-8",
             "-classpath", str(tc.android_jar), "-d", str(classes), str(java_file)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        if compilar.returncode != 0:
            raise BuildError(f"javac falhou:\n{compilar.stdout}\n{compilar.stderr}")

        class_files = sorted(classes.rglob("*.class"))
        if not class_files:
            raise BuildError("javac não produziu .class")

        saida_dex = trabalho / "dex"
        saida_dex.mkdir()
        dexar = subprocess.run(
            [str(tc.java), "-cp", str(tc.d8_jar), "com.android.tools.r8.D8",
             "--min-api", "29", "--lib", str(tc.android_jar),
             "--output", str(saida_dex), *[str(c) for c in class_files]],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        if dexar.returncode != 0:
            raise BuildError(f"d8 falhou:\n{dexar.stdout}\n{dexar.stderr}")

        gerado = saida_dex / "classes.dex"
        if not gerado.is_file():
            raise BuildError("d8 não produziu classes.dex")
        out_dex.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(gerado, out_dex)

    return {
        "activity_class": ACTIVITY_CLASS,
        "dex": out_dex.name,
        "dex_sha256": _sha256(out_dex),
        "dex_bytes": out_dex.stat().st_size,
        "class_count": len(class_files),
        "toolchain": tc.describe(),
        "base_url_scheme": base_url.split("://", 1)[0],
        "unity_activity": unity_activity,
        # Nunca o caminho nem os bytes: só se o fundo entrou e o hash do PNG de
        # entrada, para correlacionar com a origem sem versionar a imagem.
        "background_embedded": background_png is not None,
        "background_sha256": _sha256(Path(background_png)) if background_png else None,
    }
