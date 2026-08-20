"""Pipeline "Aplicar endpoint" do Revival Studio (fase 6 do plano).

Réplica Python do antigo orquestrador `patch-apk.sh` (wrapper aposentado em
2026-08-18), chamando **os mesmos CLIs** do patcher (patch_apk.py,
patch_bundle_from_report.py, verify_patched_apk.py, apktool,
uber-apk-signer) — a GUI não ganha uma segunda implementação do patch, ganha
a mesma com relatório estruturado e cancelamento.

Diferenças deliberadas em relação ao wrapper (todas exigidas pelo plano):

- Java vem do resolvedor (`toolchain.resolve_java`), nunca do PATH cego —
  era o defeito real medido no baseline (PATH com Java 11 aqui);
- workspace fica em `work/revival-studio/<id>/decoded`, provado dentro do
  projeto via `reset_directory` antes de qualquer limpeza;
- APK de saída só é promovido com `promote_atomic` depois de passar na
  verificação **pós-assinatura** (verify_patched_apk.py exit 0 é regra do
  AGENTS.md, não etapa opcional);
- análise divergente do alvo 1.13.1 bloqueia o patch (fase 4: modo inspeção,
  regras do 1.13.1 não aplicadas por suposição);
- servidor inválido bloqueia o patch por padrão (gate da fase 5).

Contrato de saída: `apply_endpoint` **devolve** `PipelineResult` também quando
uma etapa falha — o resultado carrega `failure` (código/etapa/relatório) e os
steps já executados. `PipelineError` só cobre erro de chamada (APK ausente,
CA recusada). Cancelamento (`JobCancelled`) e timeout propagam intactos para
o JobRunner classificar.

Este módulo não importa Tkinter e não chama `sys.exit()`.
"""
from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from .models import Failure, normalize_hostname
from .paths import REPO_ROOT, ensure_dir, reset_directory
from .runner import promote_atomic
from .services import analyze_apk, check_hostname_budget, server_preflight, validate_ca_file
from .toolchain import APKTOOL_JAR, SIGNER_JAR, detect_toolchain

__all__ = ["PipelineResult", "StepOutcome", "PipelineError", "apply_endpoint", "OUTPUT_APK_NAME"]

#: Saída final dentro do projeto (o path `output/` do repo é decisão de
#: exportação explícita do usuário, não do pipeline).
OUTPUT_APK_NAME = "mighty-doom-revival.apk"

_PYTHON = sys.executable or "python"

_SCRIPTS = REPO_ROOT / "scripts"
_PATCH_CLI = _SCRIPTS / "patch_apk.py"
_PATCH_BUNDLE_CLI = _SCRIPTS / "patch_bundle_from_report.py"
_VERIFY_CLI = _SCRIPTS / "verify_patched_apk.py"


class PipelineError(Exception):
    """Erro de chamada do pipeline — argumento inválido antes de qualquer passo."""


class _AbortPipeline(Exception):
    """Sinal interno: uma etapa falhou; carrega o resultado para devolver."""

    def __init__(self, resultado: "PipelineResult") -> None:
        super().__init__(resultado.failure.message if resultado.failure else "etapa falhou")
        self.resultado = resultado


class RunnerProtocol(Protocol):
    """O que o pipeline precisa do JobContext (log/progresso/subprocesso)."""

    def log(self, line: str, *, stream: str = "info") -> None: ...

    def progress(
        self,
        stage: str,
        message: str,
        fraction: float | None = None,
        *,
        current: int | None = None,
        total: int | None = None,
    ) -> None: ...

    def raise_if_cancelled(self) -> None: ...

    def run_process(
        self,
        command: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        stage: str = "processo",
        timeout: float | None = None,
    ) -> int: ...

    def temp_path(self, destino: Path | str) -> Path: ...


@dataclass
class StepOutcome:
    """Uma etapa executada: nome, exit code do CLI e marca textual."""

    name: str
    ok: bool
    exit_code: int | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "exit_code": self.exit_code, "detail": self.detail}


@dataclass
class PipelineResult:
    """Resultado serializável do pipeline inteiro."""

    host: str
    strategy: str = "auto"
    strategy_used: str | None = None
    steps: list[StepOutcome] = field(default_factory=list)
    patch_report: dict[str, Any] = field(default_factory=dict)
    input_sha256: str | None = None
    output_apk: str | None = None
    verify_report: str | None = None
    precheck_exit: int | None = None
    bundles_alterados: list[str] = field(default_factory=list)
    crcs_zerados: list[str] = field(default_factory=list)
    # Relatório da RevivalAuthActivity quando o passo opcional roda; `None`
    # quando o build é só de endpoint. Nunca carrega URL nem segredo.
    auth_report: dict[str, Any] | None = None
    # A opção PEDIDA, para o relatório provar que o parâmetro chegou — mesmo
    # quando o passo falha ou nem roda.
    revival_auth_requested: bool = False
    server_readiness: dict[str, Any] | None = None
    api_version: str | None = None
    client_version: str | None = None
    failure: Failure | None = None

    @property
    def ok(self) -> bool:
        return self.failure is None and self.output_apk is not None

    def to_dict(self) -> dict[str, Any]:
        dados: dict[str, Any] = {
            "host": self.host,
            "strategy": self.strategy,
            "strategy_used": self.strategy_used,
            "steps": [s.to_dict() for s in self.steps],
            "patch_report": self.patch_report,
            "input_sha256": self.input_sha256,
            "output_apk": self.output_apk,
            "verify_report": self.verify_report,
            "precheck_exit": self.precheck_exit,
            "bundles_alterados": self.bundles_alterados,
            "crcs_zerados": self.crcs_zerados,
            "revival_auth_requested": self.revival_auth_requested,
            "server_readiness": self.server_readiness,
            "auth_report": self.auth_report,
            "ok": self.ok,
        }
        if self.failure:
            dados["failure"] = self.failure.to_dict()
        return dados


# Revisao MINIMA de contrato que um APK gerado hoje exige do servidor. Sobe
# junto com CONTRACT_REVISION do server/src/instance.js sempre que um contrato
# `/game/*` muda de forma que o cliente enxerga.
REQUIRED_CONTRACT_REVISION = 2


def _prontidao_do_servidor(host: str, *, insecure_lab: bool = False) -> dict[str, Any]:
    """Le `/revival/health` e diz se o servidor aguenta o APK que vamos gerar.

    Espelha `productionReadiness` do server/src/instance.js — aqui em Python
    porque o pipeline nao roda dentro do servidor. Recusa, com motivo
    acionavel: identidade ausente (build antigo), revisao de contrato abaixo da
    exigida, `research_mode` ligado e build sujo.

    Servidor inalcancavel NAO e "pronto": e falta de medicao, e o gate reprova.
    """
    import json as _json
    import urllib.request as _url

    saude: dict[str, Any] | None = None
    erro: str | None = None
    for esquema in ("https", "http"):
        try:
            with _url.urlopen(f"{esquema}://{host}/revival/health", timeout=15) as resposta:
                saude = _json.loads(resposta.read().decode("utf-8"))
            break
        except Exception as exc:  # noqa: BLE001 - qualquer falha vira "nao medido"
            erro = f"{esquema}: {exc}"

    motivos: list[str] = []
    if saude is None:
        motivos.append(f"health indisponivel ({erro or 'sem detalhe'})")
    else:
        revisao = saude.get("contract_revision")
        if saude.get("instance_id") is None and saude.get("build_id") is None:
            motivos.append("health sem identidade de instancia/build "
                           "(servidor anterior a server/src/instance.js)")
        if not isinstance(revisao, int):
            motivos.append("health sem contract_revision")
        elif revisao < REQUIRED_CONTRACT_REVISION:
            motivos.append(f"contract_revision {revisao} < {REQUIRED_CONTRACT_REVISION} exigida — "
                           "faltam as correcoes de wire que este APK espera")
        if saude.get("research_mode") is True:
            motivos.append("research_mode ligado: rota desconhecida responde sucesso vazio")
        if saude.get("build_dirty") is True:
            motivos.append("build_id sujo: o commit publicado nao identifica os bytes em execucao")

    return {
        "ready": not motivos,
        "reasons": motivos,
        "required_revision": REQUIRED_CONTRACT_REVISION,
        "observed_revision": (saude or {}).get("contract_revision"),
        "instance_id": (saude or {}).get("instance_id"),
        "build_id": (saude or {}).get("build_id"),
        "research_mode": (saude or {}).get("research_mode"),
        "override_lab": bool(insecure_lab),
    }


def apply_endpoint(
    ctx: RunnerProtocol,
    *,
    apk: Path | str,
    host: str,
    project_dir: Path | str,
    ca_file: Path | str | None = None,
    strategy: str = "auto",
    revival_auth: bool = False,
    allow_incompatible_server: bool = False,
    java_path: Path | str | None = None,
    analyze: Callable[..., Any] = analyze_apk,
    preflight: Callable[..., Any] = server_preflight,
    toolchain_detect: Callable[..., Any] = detect_toolchain,
    readiness: Callable[..., Any] = None,
) -> PipelineResult:
    """Executa o pipeline completo de endpoint contra `host`.

    `analyze`, `preflight` e `toolchain_detect` são injetáveis só para os
    testes de orquestração — em produção são os serviços reais.
    """
    entrada = Path(apk)
    if not entrada.is_file():
        raise PipelineError(f"APK não encontrado: {entrada}")
    host_normalizado = normalize_hostname(host)
    projeto = Path(project_dir)

    resultado = PipelineResult(host=host_normalizado, strategy=strategy)
    try:
        _executar(
            ctx, resultado,
            entrada=entrada, projeto=projeto, host=host_normalizado,
            ca=Path(ca_file) if ca_file else None,
            strategy=strategy, java_path=java_path, revival_auth=revival_auth,
            allow_incompatible_server=allow_incompatible_server,
            analyze=analyze, preflight=preflight, toolchain_detect=toolchain_detect,
            readiness=readiness or _prontidao_do_servidor,
        )
    except _AbortPipeline as abort:
        if resultado.failure:
            ctx.log(f"[falha] {resultado.failure.code}: {resultado.failure.message}", stream="erro")
        return abort.resultado
    return resultado


def _executar(
    ctx: RunnerProtocol,
    resultado: PipelineResult,
    *,
    entrada: Path,
    projeto: Path,
    host: str,
    ca: Path | None,
    strategy: str,
    java_path: Path | str | None,
    revival_auth: bool = False,
    allow_incompatible_server: bool = False,
    analyze: Callable[..., Any],
    preflight: Callable[..., Any],
    toolchain_detect: Callable[..., Any],
    readiness: Callable[..., Any] = _prontidao_do_servidor,
) -> None:
    if ca is not None:
        try:
            info_ca = validate_ca_file(ca)
        except Exception as exc:  # noqa: BLE001 - CaFileError tem mensagem pronta
            raise PipelineError(str(exc)) from exc
        ctx.log(
            f"CA validada: {info_ca.certificates} certificado(s), sha256 {info_ca.sha256[:16]}…"
        )

    reports = ensure_dir(projeto, projeto / "reports", what="reports do projeto")

    # -- análise (fase 4: alvo confirmado ou bloqueia) -----------------------
    _passo(ctx, "análise", "analisando APK de entrada…")
    analise = analyze(entrada, log=ctx.log)
    resultado.input_sha256 = analise.sha256
    ctx.raise_if_cancelled()
    if not analise.matches_target:
        problemas = "; ".join(analise.divergences + analise.unknown)
        _falhar(
            resultado, code="ANALISE_ALVO", stage="análise",
            message="APK não confirmado como alvo 1.13.1 — modo inspeção (fase 4)",
            details=problemas,
        )

    # -- toolchain ----------------------------------------------------------
    _passo(ctx, "toolchain", "conferindo ferramentas (Java 17+, JARs pinados)…")
    ferramentas = toolchain_detect(java_path=java_path)
    bloqueios = ferramentas.blocking
    if bloqueios:
        detalhe = " | ".join(f"{t.name}: {(t.detail or 'indisponível').splitlines()[0]}" for t in bloqueios)
        _falhar(
            resultado, code="TOOLCHAIN", stage="toolchain",
            message="ferramenta obrigatória bloqueando o build", details=detalhe,
        )
    java = ferramentas.get("java")
    if not java or not java.ok or not java.path:
        _falhar(resultado, code="TOOLCHAIN", stage="toolchain",
                message="resolvedor de Java não devolveu caminho utilizável")

    # -- precheck do orçamento ----------------------------------------------
    _passo(ctx, "precheck", f"precheck de orçamento para {host}…")
    pre = check_hostname_budget(entrada, host, log=ctx.log)
    resultado.precheck_exit = pre.exit_code
    if pre.blocks_pipeline:
        _falhar(
            resultado, code="PRECHECK_INVALIDO", stage="precheck",
            message=f"precheck rejeitou hostname ou APK (exit {pre.exit_code})",
            details="\n".join(pre.lines), exit_code=pre.exit_code,
        )
    ctx.raise_if_cancelled()

    # -- preflight do servidor (fase 5: gate) --------------------------------
    _passo(ctx, "preflight", f"preflight HTTPS de {host}…")
    servidor = preflight(host, ca_file=ca, report_path=reports / "server-preflight.json", log=ctx.log)
    if not getattr(servidor, "ok", False):
        erros = "; ".join(getattr(servidor, "errors", None) or ["sem detalhe"])
        _falhar(
            resultado, code="SERVER_PREFLIGHT", stage="preflight",
            message="servidor Revival não passou no preflight (gate da fase 5)",
            details=erros,
        )

    # -- compatibilidade de CONTRATO, antes de publicar qualquer APK ----------
    # O preflight acima só prova que o servidor está vivo e fala o envelope.
    # Em 2026-08-20 um build saiu "verde" contra uma VPS que não tem as
    # correções de wire deste APK (sem identidade, sem contract_revision,
    # research_mode ligado) — o cliente reproduziria os `Malformed response
    # payload` já corrigidos. Este gate roda ANTES do decode: falhar aqui custa
    # segundos, falhar depois custa o build inteiro.
    prontidao = readiness(host, insecure_lab=allow_incompatible_server)
    resultado.server_readiness = prontidao
    if not prontidao["ready"] and not allow_incompatible_server:
        _falhar(
            resultado, code="SERVER_CONTRACT", stage="preflight",
            message=(f"o servidor em {host} não é compatível com este APK "
                     f"(revisão de contrato exigida: {prontidao['required_revision']})"),
            details="; ".join(prontidao["reasons"])
            + ". Publique o servidor atualizado antes de gerar o APK, ou use a "
              "opção explícita de laboratório para ignorar (nunca em produção).",
        )
    if not prontidao["ready"]:
        ctx.log("[LAB] servidor incompatível ACEITO por override explícito: "
                + "; ".join(prontidao["reasons"]), stream="erro")
    ctx.raise_if_cancelled()

    # -- workspace -----------------------------------------------------------
    workspace = projeto / "decoded"
    _passo(ctx, "workspace", f"preparando {workspace} (contenção provada)…")
    reset_directory(projeto, workspace, what="workspace decoded")
    build_dir = ensure_dir(projeto, projeto / "build", what="build do projeto")

    # -- apktool decode -------------------------------------------------------
    _passo(ctx, "decode", "[1/7] apktool d — decodificando (indeterminado)…", None)
    codigo = ctx.run_process(
        [java.path, "-jar", str(APKTOOL_JAR), "d", "-f", str(entrada), "-o", str(workspace)],
        cwd=REPO_ROOT, stage="apktool-decode", timeout=3600,
    )
    _registrar(resultado, "decode", codigo, "apktool d")
    if codigo != 0:
        _falhar(resultado, code="DECODE", stage="decode",
                message=f"apktool d falhou (exit {codigo})", exit_code=codigo)
    ctx.raise_if_cancelled()

    # -- patch (fast path → bundle-aware) --------------------------------------
    relatorio_patch = reports / "patch-report.json"
    _passo(ctx, "patch", "[2/7] patch direto no global-metadata (fast path)…")
    comando = [_PYTHON, str(_PATCH_CLI), "--decoded", str(workspace),
               "--server", host, "--report", str(relatorio_patch)]
    if ca is not None:
        comando += ["--ca", str(ca)]
    codigo = ctx.run_process(comando, cwd=REPO_ROOT, stage="patch-fast", timeout=1800)
    if codigo == 0:
        resultado.strategy_used = "fast-path"

    if codigo == 4:
        if strategy == "fast-path":
            _falhar(
                resultado, code="PATCH_ESTRATEGIA", stage="patch",
                message="fast path não coube (exit 4) e a estratégia escolhida foi fast-path",
                details="mude a estratégia para auto ou bundle-aware", exit_code=4,
            )
        ctx.log("fast path insuficiente (exit 4) — sweep bundle-aware em todos os bundles…")
        _passo(ctx, "patch", "[2/7] patch bundle-aware (--sweep-all-bundles)…")
        codigo = _rodar_patch_bundle(ctx, workspace, host, relatorio_patch)
        if codigo == 0:
            resultado.strategy_used = "bundle-aware"
    elif codigo == 0 and strategy in ("auto", "bundle-aware"):
        # Sucesso do fast path só prova a troca no global-metadata. O host
        # oficial da gameplay (ProdGameServer.baseUrl) vive em bundles
        # Addressables que o scan cru do patch_apk não enxerga — blocos LZ4
        # fragmentam o hostname sem deixar ocorrência contígua em bytes
        # brutos. O sweep é o único estágio que prova a árvore limpa: sem
        # ele, o verify descobre o host remanescente só DEPOIS do apktool b
        # desperdiçado (VERIFY_PRE exit 5 — caso real e2e-vps-fase13:
        # 5 refs oficiais no bundle de cenas com fast path exit 0).
        rotulo = (
            "estratégia bundle-aware: sweep adicional mesmo com fast path completo…"
            if strategy == "bundle-aware"
            else "fast path não prova os bundles — sweep bundle-aware de prova…"
        )
        ctx.log(rotulo)
        codigo = _rodar_patch_bundle(ctx, workspace, host, relatorio_patch)
        if codigo == 0:
            resultado.strategy_used = "bundle-aware"

    _registrar(resultado, "patch", codigo, "patch_apk/patch_bundle")
    if codigo != 0:
        _falhar(resultado, code="PATCH", stage="patch",
                message=f"patch falhou (exit {codigo})", exit_code=codigo)
    ctx.raise_if_cancelled()

    if relatorio_patch.is_file():
        resultado.patch_report = json.loads(relatorio_patch.read_text(encoding="utf-8"))
        _consolidar_bundles(ctx, resultado)

    # -- autenticação Revival (opcional) ---------------------------------------
    # Roda DEPOIS do patch de host e ANTES do rebuild: a Activity precisa do
    # Manifest da árvore já patchada, e o dex entra no APK construído (o Apktool
    # regenera classes*.dex a partir do smali, então dex solto na árvore não
    # entra). Pós-condição conferida pelo próprio patcher: um único launcher,
    # Activity Unity preservada com deep link.
    dex_revival: Path | None = None
    resultado.revival_auth_requested = bool(revival_auth)
    if revival_auth:
        _passo(ctx, "auth", "[2b/7] RevivalAuthActivity — compilando e patchando Manifest…")
        try:
            from patch_revival_auth import apply as aplicar_auth  # noqa: PLC0415
            relatorio_auth = aplicar_auth(
                decoded=workspace,
                base_url=f"https://{host}/collections/doom",
                api_version=resultado.api_version or "24.0.0",
                client_version=resultado.client_version or "1.13.1",
            )
        except Exception as exc:  # noqa: BLE001 - AuthPatchError traz mensagem pronta
            _falhar(resultado, code="REVIVAL_AUTH", stage="auth",
                    message=f"injeção da RevivalAuthActivity falhou: {exc}")
        resultado.auth_report = relatorio_auth
        dex_revival = Path(relatorio_auth["dex_path"])
        ctx.log(f"Activity {relatorio_auth['activity_class']} — launcher único, "
                f"Unity preservada (dex {relatorio_auth['dex_sha256'][:16]}…)")
        _registrar(resultado, "auth", 0, "patch_revival_auth")
        ctx.raise_if_cancelled()

    # -- rebuild ---------------------------------------------------------------
    unsigned = build_dir / "revival-unsigned.apk"
    temporario = ctx.temp_path(unsigned)
    _passo(ctx, "rebuild", "[3/7] apktool b — reconstruindo (indeterminado)…", None)
    codigo = ctx.run_process(
        [java.path, "-jar", str(APKTOOL_JAR), "b", str(workspace), "-o", str(temporario)],
        cwd=REPO_ROOT, stage="apktool-build", timeout=3600,
    )
    if codigo != 0 or not temporario.is_file():
        _falhar(resultado, code="REBUILD", stage="rebuild",
                message=f"apktool b falhou (exit {codigo})", exit_code=codigo or None)
    promote_atomic(temporario, unsigned)
    _registrar(resultado, "rebuild", codigo, "apktool b")

    if dex_revival is not None:
        from patch_revival_auth import inject_dex  # noqa: PLC0415
        com_dex = ctx.temp_path(unsigned)
        info_dex = inject_dex(unsigned, dex_revival, apk_out=com_dex)
        promote_atomic(com_dex, unsigned)
        ctx.log(f"Activity injetada como {info_dex['dex_entry']}")
        resultado.auth_report = {**(resultado.auth_report or {}), **info_dex}
    ctx.raise_if_cancelled()

    # -- verificação pré-assinatura ---------------------------------------------
    relatorio_verify = reports / "final-apk-verification.json"
    _passo(ctx, "verify", "[4/7] verify_patched_apk (pré-assinatura)…")
    codigo = _verificar(ctx, unsigned, host, relatorio_verify)
    _registrar(resultado, "verify-pre", codigo, "verify_patched_apk")
    if codigo != 0:
        _falhar(resultado, code="VERIFY_PRE", stage="verify-pre",
                message="endpoint não verificado no APK reconstruído (pré-assinatura)",
                report_path=str(relatorio_verify), exit_code=codigo)

    # -- assinatura ----------------------------------------------------------------
    _passo(ctx, "sign", "[5/7] uber-apk-signer — assinando…")
    codigo = ctx.run_process(
        [java.path, "-jar", str(SIGNER_JAR), "-a", str(unsigned), "--overwrite", "--verbose"],
        cwd=REPO_ROOT, stage="sign", timeout=1800,
    )
    _registrar(resultado, "sign", codigo, "uber-apk-signer")
    if codigo != 0:
        _falhar(resultado, code="SIGN", stage="sign",
                message=f"assinatura falhou (exit {codigo})", exit_code=codigo)

    ctx.log("[5/7] conferindo a assinatura (--onlyVerify)…")
    codigo = ctx.run_process(
        [java.path, "-jar", str(SIGNER_JAR), "-a", str(unsigned), "--onlyVerify", "--verbose"],
        cwd=REPO_ROOT, stage="sign-verify", timeout=900,
    )
    _registrar(resultado, "sign-verify", codigo, "uber-apk-signer --onlyVerify")
    if codigo != 0:
        _falhar(resultado, code="SIGN_VERIFY", stage="sign-verify",
                message=f"verificação da assinatura falhou (exit {codigo})", exit_code=codigo)
    ctx.raise_if_cancelled()

    # -- verificação pós-assinatura (regra do AGENTS.md) -----------------------------
    _passo(ctx, "verify", "[6/7] verify_patched_apk pós-assinatura…")
    codigo = _verificar(ctx, unsigned, host, relatorio_verify)
    _registrar(resultado, "verify", codigo, "verify_patched_apk")
    resultado.verify_report = str(relatorio_verify)
    if codigo != 0:
        _falhar(resultado, code="VERIFY_POS", stage="verify",
                message="endpoint não verificado após assinatura — APK não promovido",
                report_path=str(relatorio_verify), exit_code=codigo)

    # -- publicação atômica ------------------------------------------------------------
    saida = projeto / "output" / OUTPUT_APK_NAME
    _passo(ctx, "publicar", "[7/7] promovendo APK final…", 0.98)
    temporario_saida = ctx.temp_path(saida)
    ensure_dir(projeto, saida.parent, what="output do projeto")
    shutil.copyfile(unsigned, temporario_saida)
    promote_atomic(temporario_saida, saida)
    resultado.output_apk = str(saida)
    _registrar(resultado, "publicar", 0, f"APK final: {saida}")
    ctx.log(f"[OK] pipeline concluído — estratégia {resultado.strategy_used} · APK: {saida}")


def _rodar_patch_bundle(
    ctx: RunnerProtocol, workspace: Path, host: str, relatorio: Path
) -> int:
    return ctx.run_process(
        [_PYTHON, str(_PATCH_BUNDLE_CLI), "--decoded", str(workspace), "--server", host,
         "--report", str(relatorio), "--sweep-all-bundles"],
        cwd=REPO_ROOT, stage="patch-bundle", timeout=3600,
    )


def _consolidar_bundles(ctx: RunnerProtocol, resultado: PipelineResult) -> None:
    """Consolida bundles alterados/CRCs zerados do schema real do relatório.

    O relatório do patch_bundle_from_report.py carrega os bundles na lista
    `bundle_aware` — uma entrada por arquivo com `changed` e, para os do
    catálogo, `catalog_crc.zeroed`. As chaves de topo `bundles_alterados`/
    `crcs_zerados` que a versão anterior lia nunca existiram em nenhum CLI: o
    e2e real (fase 13) terminou com os agregados vazios e um bundle alterado.

    A relação precisa fechar ou o pipeline falha antes do rebuild desperdiçado:

    - todo bundle `changed=true` sob `assets/aa/**` exige `catalog_crc.zeroed`;
    - nenhum CRC zerado para bundle que o relatório não marca como alterado.

    Caminhos são normalizados para `/` — o CLI escreve com o separador nativo
    e o agregado precisa ser estável entre plataformas.
    """
    relatorio = resultado.patch_report or {}
    entradas = relatorio.get("bundle_aware")
    if not isinstance(entradas, list):
        return  # fast-path puro: relatório do patch_apk não tem dados de bundle
    sem_crc: list[str] = []
    crc_sem_mudanca: list[str] = []
    for entrada in entradas:
        if not isinstance(entrada, dict):
            continue
        caminho = str(entrada.get("path") or "").replace("\\", "/")
        if not caminho:
            continue
        crc = entrada.get("catalog_crc")
        crc_zerado = isinstance(crc, dict) and crc.get("zeroed") is True
        mudou = entrada.get("changed") is True
        if mudou:
            resultado.bundles_alterados.append(caminho)
            if caminho.startswith("assets/aa/") and not crc_zerado:
                sem_crc.append(caminho)
        if crc_zerado:
            resultado.crcs_zerados.append(caminho)
            if not mudou:
                crc_sem_mudanca.append(caminho)
    if resultado.bundles_alterados or resultado.crcs_zerados:
        ctx.log(
            f"bundles alterados: {len(resultado.bundles_alterados)} · "
            f"CRCs zerados: {len(resultado.crcs_zerados)}"
        )
    if sem_crc:
        _falhar(
            resultado, code="BUNDLE_SEM_CRC", stage="patch",
            message="bundle alterado sob assets/aa/** sem CRC zerado no catálogo",
            details="; ".join(sem_crc[:5]),
        )
    if crc_sem_mudanca:
        _falhar(
            resultado, code="CRC_SEM_MUDANCA", stage="patch",
            message="CRC zerado para bundle que o relatório não marca como alterado",
            details="; ".join(crc_sem_mudanca[:5]),
        )


def _verificar(ctx: RunnerProtocol, apk: Path, host: str, relatorio: Path) -> int:
    ctx.log(f"verify_patched_apk em {apk.name} (host {host})…")
    return ctx.run_process(
        [_PYTHON, str(_VERIFY_CLI), "--apk", str(apk), "--server", host,
         "--report", str(relatorio)],
        cwd=REPO_ROOT, stage="verify", timeout=1800,
    )


def _passo(
    ctx: RunnerProtocol,
    nome: str,
    mensagem: str,
    fracao: float | None = 0.0,
) -> None:
    ctx.progress(nome, mensagem, fracao)


def _registrar(resultado: PipelineResult, nome: str, codigo: int, marca: str) -> None:
    resultado.steps.append(
        StepOutcome(name=nome, ok=codigo == 0, exit_code=codigo, detail=marca)
    )


def _falhar(
    resultado: PipelineResult,
    *,
    code: str,
    stage: str,
    message: str,
    details: str = "",
    report_path: str | None = None,
    exit_code: int | None = None,
) -> None:
    resultado.failure = Failure(
        code=code, stage=stage, message=message,
        details=details, report_path=report_path, exit_code=exit_code,
    )
    raise _AbortPipeline(resultado)
