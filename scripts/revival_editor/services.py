"""Adaptadores dos CLIs do patcher para o Revival Studio (fase 1 do plano).

Princípio: **a GUI chama a mesma implementação dos CLIs**. Os três scripts desta
primeira leva já separavam lógica de `argparse` — `analyze()`, `check()` e
`check_server()` são funções puras — então este módulo é um adaptador fino, não
um refactor. Os CLIs continuam intactos: nenhum argumento e nenhum exit code
mudou.

O que este módulo acrescenta por cima do que já existia:

- tipos de resultado serializáveis (`AnalyzeResult`, `PrecheckResult`,
  `ServerPreflightResult`), em vez de dicionário solto e parse de texto;
- `log: Callable[[str], None]` opcional, sem acoplar Tkinter ao domínio;
- os fatos que a fase 4 exige para travar a entrada e que `analyze_apk.py`
  ainda não produzia: **versão do global-metadata.dat** e **ABIs**.

Nenhuma função aqui chama `sys.exit()`.
"""
from __future__ import annotations

import struct
import zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

from .models import Failure, normalize_hostname

__all__ = [
    "EXPECTED_PACKAGE",
    "EXPECTED_VERSION_NAME",
    "EXPECTED_VERSION_CODE",
    "EXPECTED_UNITY",
    "EXPECTED_ABI",
    "EXPECTED_METADATA_VERSION",
    "METADATA_SANITY",
    "OFFICIAL_GAMEPLAY_HOST",
    "AnalyzeResult",
    "PrecheckResult",
    "PrecheckVerdict",
    "ServerPreflightResult",
    "analyze_apk",
    "read_metadata_version",
    "check_hostname_budget",
    "server_preflight",
]

Logger = Callable[[str], None]

#: Alvo do projeto. Divergência não bloqueia, mas abre só em modo inspeção
#: (fase 4: *"se algum campo divergir, abrir somente em modo inspeção e marcar
#: A VERIFICAR; não aplicar regras do 1.13.1 automaticamente"*).
EXPECTED_PACKAGE = "com.bethsoft.ubu"
EXPECTED_VERSION_NAME = "1.13.1"
EXPECTED_VERSION_CODE = "84862"
EXPECTED_UNITY = "2021.3.25f1"
EXPECTED_ABI = "arm64-v8a"
EXPECTED_METADATA_VERSION = 29

#: Sanity do global-metadata.dat do IL2CPP (skill il2cpp-recon).
METADATA_SANITY = 0xFAB11BAF

#: Host da API de gameplay. 31 bytes — define o orçamento do fast path.
OFFICIAL_GAMEPLAY_HOST = "international.gear.bethesda.net"


def _noop(_: str) -> None:
    return None


# --------------------------------------------------------------------------
# Análise do APK
# --------------------------------------------------------------------------


@dataclass
class AnalyzeResult:
    """Fatos do APK de entrada, sanitizados (nenhum byte proprietário)."""

    path: str
    sha256: str
    size_bytes: int
    package: str | None = None
    version_name: str | None = None
    version_code: str | None = None
    unity_version: str | None = None
    abis: list[str] = field(default_factory=list)
    metadata_version: int | None = None
    metadata_path: str | None = None
    indicators: dict[str, Any] = field(default_factory=dict)
    host_hits: list[dict[str, Any]] = field(default_factory=list)
    report_path: str | None = None
    #: Campos que divergiram do alvo 1.13.1, com a leitura obtida.
    divergences: list[str] = field(default_factory=list)
    #: Campos que não pôde medir (ex.: package sem aapt no PATH).
    unknown: list[str] = field(default_factory=list)

    @property
    def matches_target(self) -> bool:
        """True só quando nada divergiu **e** nada ficou desconhecido.

        Desconhecido não é aprovação: sem `aapt` não dá para provar que o APK é
        o 1.13.1, e o plano proíbe aplicar as regras do 1.13.1 por suposição.
        """
        return not self.divergences and not self.unknown

    @property
    def official_host_present(self) -> bool:
        return any(
            OFFICIAL_GAMEPLAY_HOST in (hit.get("offsets") or {}) for hit in self.host_hits
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["matches_target"] = self.matches_target
        data["official_host_present"] = self.official_host_present
        return data


def read_metadata_version(apk: Path, member: str) -> tuple[int | None, str | None]:
    """Lê sanity e versão do `global-metadata.dat` direto do ZIP.

    Só os 8 primeiros bytes — não extrai o APK de 615 MB nem roda apktool,
    conforme a skill `il2cpp-recon`.

    Devolve `(versao, erro)`. `versao` é None quando o sanity não bate.
    """
    try:
        with zipfile.ZipFile(apk, "r") as zf, zf.open(member, "r") as stream:
            cabecalho = stream.read(8)
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        return None, f"não foi possível ler {member}: {exc}"
    if len(cabecalho) < 8:
        return None, f"{member} truncado ({len(cabecalho)} bytes)"
    sanity, versao = struct.unpack("<II", cabecalho)
    if sanity != METADATA_SANITY:
        return None, f"sanity inesperado: 0x{sanity:08X} (esperado 0x{METADATA_SANITY:08X})"
    return versao, None


def _detect_abis(nomes: list[str]) -> list[str]:
    abis: set[str] = set()
    for nome in nomes:
        partes = nome.split("/")
        if len(partes) >= 3 and partes[0] == "lib" and partes[2].endswith(".so"):
            abis.add(partes[1])
    return sorted(abis)


def _detect_unity_version(zf: zipfile.ZipFile) -> str | None:
    """Versão da engine, lida do `globalgamemanagers` ou do bundle de dados.

    O número aparece como string ASCII curta no começo do arquivo de
    serialização da Unity. Lê só um bloco inicial; não decodifica o asset.
    """
    import re

    for membro in ("assets/bin/Data/globalgamemanagers", "assets/bin/Data/data.unity3d"):
        try:
            with zf.open(membro, "r") as stream:
                cabeca = stream.read(4096)
        except (KeyError, OSError):
            continue
        achado = re.search(rb"\d{4}\.\d+\.\d+[a-z]\d+", cabeca)
        if achado:
            return achado.group(0).decode("ascii", "replace")
    return None


def analyze_apk(
    apk: Path | str,
    *,
    report_path: Path | str | None = None,
    log: Logger = _noop,
) -> AnalyzeResult:
    """Analisa o APK reutilizando `scripts/analyze_apk.py` e completa a fase 4.

    Não copia, não move e não altera o APK de entrada — ele é imutável
    (AGENTS.md / §5 do plano).
    """
    import json
    import sys

    scripts_dir = str(Path(__file__).resolve().parent.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from analyze_apk import analyze as _analyze  # noqa: PLC0415

    caminho = Path(apk)
    if not caminho.is_file():
        raise FileNotFoundError(f"APK não encontrado: {caminho}")

    log(f"analisando {caminho.name} ({caminho.stat().st_size:,} bytes)…")
    bruto = _analyze(caminho)
    log(f"SHA-256 {bruto['sha256']}")

    indicadores = dict(bruto.get("indicators") or {})
    pacote = dict(bruto.get("package") or {})

    resultado = AnalyzeResult(
        path=str(caminho),
        sha256=str(bruto["sha256"]),
        size_bytes=int(bruto["size_bytes"]),
        package=pacote.get("package") or None,
        version_name=pacote.get("versionName") or None,
        version_code=pacote.get("versionCode") or None,
        indicators=indicadores,
        host_hits=list(bruto.get("host_hits") or []),
        report_path=str(report_path) if report_path else None,
    )

    with zipfile.ZipFile(caminho, "r") as zf:
        nomes = zf.namelist()
        resultado.abis = _detect_abis(nomes)
        resultado.unity_version = _detect_unity_version(zf)

    caminhos_metadata = list(indicadores.get("global_metadata_paths") or [])
    if caminhos_metadata:
        resultado.metadata_path = caminhos_metadata[0]
        versao, erro = read_metadata_version(caminho, caminhos_metadata[0])
        resultado.metadata_version = versao
        if erro:
            log(f"[aviso] metadata: {erro}")

    _classificar(resultado, log)

    if report_path:
        destino = Path(report_path)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            json.dumps(resultado.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        log(f"relatório: {destino}")

    return resultado


def _classificar(resultado: AnalyzeResult, log: Logger) -> None:
    """Preenche `divergences` e `unknown` contra o alvo 1.13.1."""

    def confere(rotulo: str, obtido: Any, esperado: Any) -> None:
        if obtido in (None, "", []):
            resultado.unknown.append(f"{rotulo} (não medido)")
        elif str(obtido) != str(esperado):
            resultado.divergences.append(f"{rotulo}: {obtido} (esperado {esperado})")

    confere("package", resultado.package, EXPECTED_PACKAGE)
    confere("versão", resultado.version_name, EXPECTED_VERSION_NAME)
    confere("build", resultado.version_code, EXPECTED_VERSION_CODE)
    confere("Unity", resultado.unity_version, EXPECTED_UNITY)
    confere("metadata", resultado.metadata_version, EXPECTED_METADATA_VERSION)

    if not resultado.abis:
        resultado.unknown.append("ABI (não medido)")
    elif EXPECTED_ABI not in resultado.abis:
        resultado.divergences.append(f"ABI: {resultado.abis} (esperado conter {EXPECTED_ABI})")

    if not resultado.indicators.get("libil2cpp_arm64"):
        resultado.divergences.append("lib/arm64-v8a/libil2cpp.so ausente")

    if resultado.unknown:
        log(f"[A VERIFICAR] não medido: {', '.join(resultado.unknown)}")
    if resultado.divergences:
        log(f"[divergência] {'; '.join(resultado.divergences)}")


# --------------------------------------------------------------------------
# Precheck do orçamento de hostname
# --------------------------------------------------------------------------


class PrecheckVerdict(str):
    """Veredito do precheck, espelhando os exit codes de check_patch_length.py."""

    FAST_PATH = "fast-path"      # exit 0
    BUNDLE_AWARE = "bundle-aware"  # exit 4
    INVALIDO = "invalido"        # exit 2


@dataclass
class PrecheckResult:
    """Resultado de `check_patch_length.py`, com o exit code preservado."""

    host: str
    exit_code: int
    verdict: str
    lines: list[str] = field(default_factory=list)
    failure: Failure | None = None

    @property
    def can_fast_path(self) -> bool:
        return self.exit_code == 0

    @property
    def blocks_pipeline(self) -> bool:
        """Só o exit 2 bloqueia. **Exit 4 não é fatal** — cai para bundle-aware."""
        return self.exit_code == 2

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["can_fast_path"] = self.can_fast_path
        data["blocks_pipeline"] = self.blocks_pipeline
        if self.failure:
            data["failure"] = self.failure.to_dict()
        return data


def check_hostname_budget(apk: Path | str, host: str, *, log: Logger = _noop) -> PrecheckResult:
    """Executa o precheck de orçamento de bytes reutilizando o CLI.

    Semântica dos exit codes (skill apk-patch), preservada literalmente:

    - 0 → cabe no fast path (patch byte-preserving no `global-metadata.dat`);
    - 4 → **não é fatal**: seguir para `patch_bundle_from_report.py`;
    - 2 → hostname ou APK inválido; aí sim bloqueia.
    """
    import sys

    scripts_dir = str(Path(__file__).resolve().parent.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from check_patch_length import check as _check  # noqa: PLC0415

    caminho = Path(apk)
    if not caminho.is_file():
        raise FileNotFoundError(f"APK não encontrado: {caminho}")

    normalizado = normalize_hostname(host)
    code, linhas = _check(caminho, normalizado)
    for linha in linhas:
        log(linha)

    veredito = {
        0: PrecheckVerdict.FAST_PATH,
        4: PrecheckVerdict.BUNDLE_AWARE,
    }.get(code, PrecheckVerdict.INVALIDO)

    falha = None
    if code == 2:
        falha = Failure(
            code="PRECHECK_INVALIDO",
            stage="precheck",
            message="hostname ou APK inválido para o precheck",
            details="\n".join(linhas),
            exit_code=code,
        )

    return PrecheckResult(
        host=normalizado, exit_code=code, verdict=veredito, lines=list(linhas), failure=falha
    )


# --------------------------------------------------------------------------
# Preflight do servidor
# --------------------------------------------------------------------------


@dataclass
class ServerPreflightResult:
    """Resultado de `check_revival_server.py`, sem segredo no relatório."""

    host: str
    ok: bool
    checks: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    client_version: str | None = None
    api_version: str | None = None
    game_data_loaded: bool | None = None
    report_path: str | None = None
    failure: Failure | None = None

    def to_dict(self) -> dict[str, Any]:
        from .redaction import mask_mapping

        data = asdict(self)
        if self.failure:
            data["failure"] = self.failure.to_dict()
        return mask_mapping(data)


def server_preflight(
    host: str,
    *,
    ca_file: Path | str | None = None,
    timeout: float = 15.0,
    require_game_data: bool = True,
    report_path: Path | str | None = None,
    log: Logger = _noop,
) -> ServerPreflightResult:
    """Valida HTTPS, `/revival/health` e o formato do `uts` do servidor.

    Exigências da fase 5: cliente 1.13.1, API 24.0.0, `uts` no formato estrito
    e game data carregado. **Não existe opção de ignorar TLS** — nem aqui nem
    na UI.
    """
    import json
    import sys

    scripts_dir = str(Path(__file__).resolve().parent.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from check_revival_server import check_server as _check_server  # noqa: PLC0415

    normalizado = normalize_hostname(host)
    ca = Path(ca_file) if ca_file else None
    if ca is not None and not ca.is_file():
        raise FileNotFoundError(f"CA não encontrada: {ca}")

    log(f"preflight HTTPS de {normalizado}…")
    bruto = _check_server(normalizado, ca, timeout, require_game_data)

    erros = [str(e) for e in (bruto.get("errors") or [])]
    checks = dict(bruto.get("checks") or {})
    saude = checks.get("health") if isinstance(checks.get("health"), dict) else {}
    payload = saude.get("payload") if isinstance(saude, dict) else {}
    payload = payload if isinstance(payload, dict) else {}

    resultado = ServerPreflightResult(
        host=normalizado,
        ok=bool(bruto.get("ok")) and not erros,
        checks=checks,
        errors=erros,
        client_version=payload.get("client_version"),
        api_version=payload.get("api_version"),
        game_data_loaded=payload.get("game_data_loaded"),
        report_path=str(report_path) if report_path else None,
    )

    if not resultado.ok:
        resultado.failure = Failure(
            code="SERVER_PREFLIGHT",
            stage="preflight",
            message="servidor Revival não passou no preflight",
            details="\n".join(erros) or "sem detalhe",
            report_path=resultado.report_path,
        )
        for erro in erros:
            log(f"[erro] {erro}")
    else:
        log(
            f"[OK] cliente {resultado.client_version} · API {resultado.api_version} · "
            f"game_data_loaded={resultado.game_data_loaded}"
        )

    if report_path:
        destino = Path(report_path)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            json.dumps(resultado.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        log(f"relatório: {destino}")

    return resultado
