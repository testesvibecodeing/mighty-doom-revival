"""Ciclo de vida do servidor Revival local (planos §6.1 e §9.2).

Espelha como serviço os passos dos wrappers de setup/start do servidor: o
wrapper continua sendo o caminho headless canônico (terminal, CI, VPS) e
este módulo é o mesmo fluxo invocado pelo Revival Studio, com relatório
estruturado e cancelamento pelo runner.

Regras fixas:

- configs locais (`server/.env`, `server/config/*.json`) **nunca** são
  editadas nem sobrescritas: o `*.example` é copiado somente quando o
  arquivo local não existe (mesma semântica do wrapper de setup);
- o servidor roda em segundo plano com PID e log registrados em
  `work/revival-studio/server/` (ignorado pelo Git);
- encerrar é sempre explícito: fechar o Studio **não** derruba o servidor,
  para não interromper um teste de dispositivo em andamento;
- nada aqui publica, faz deploy ou substitui `install.sh`/`uninstall.sh`
  (regra 1.8: deploy de VPS continua sendo o par shell canônico).
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .paths import REPO_ROOT

__all__ = [
    "DEFAULT_PORT",
    "HEALTH_PATH",
    "ServerError",
    "ServerReport",
    "check_node",
    "health_probe",
    "pid_alive",
    "prepare_server",
    "read_port",
    "resolve_node",
    "server_status",
    "start_server",
    "state_dir",
    "stop_server",
]

DEFAULT_PORT = 8080
HEALTH_PATH = "/revival/health"
HEALTH_TIMEOUT = 3.0
START_TIMEOUT = 30.0
STOP_TIMEOUT = 8.0

WINDOWS = os.name == "nt"

#: Cópia example -> local feita pelo preparo quando o local falta (etapa 1/4
#: do wrapper). Ordem deliberadamente igual à do wrapper.
CONFIG_COPIES: tuple[tuple[str, str], ...] = (
    (".env", ".env.example"),
    ("config/revival.json", "config/revival.example.json"),
    ("config/packs.json", "config/packs.example.json"),
    ("config/events.json", "config/events.example.json"),
)

#: Arquivos validados com `node --check` no preparo (etapa 2/4 do wrapper).
CHECK_FILES: tuple[str, ...] = (
    "src/index.js",
    "src/chapters.js",
    "src/config.js",
    "src/db.js",
    "src/events.js",
    "src/game-data-model.js",
    "src/store.js",
    "test/smoke.mjs",
)

#: Sonda equivalente à do wrapper: valida `node:sqlite` nativo de verdade.
SQLITE_PROBE = (
    "const s=require('node:sqlite'); const db=new s.DatabaseSync(':memory:');"
    " db.exec('select 1'); db.close()"
)


class ServerError(RuntimeError):
    """Falha de preparo/início/parada do servidor local (mensagem amigável)."""


@dataclass
class ServerReport:
    """Resultado estruturado de prepare/start/stop para o callback da UI."""

    ok: bool
    steps: list[str] = field(default_factory=list)
    node_version: str | None = None
    copied: list[str] = field(default_factory=list)
    pid: int | None = None
    port: int | None = None
    health: dict | None = None
    ja_em_execucao: bool = False
    log_path: str | None = None
    erro: str | None = None


# ----------------------------------------------------------------------
# utilitários (sem Tk; testáveis com fakes)
# ----------------------------------------------------------------------


def state_dir(repo_root: Path | str | None = None) -> Path:
    """Diretório de estado do servidor local (PID + log), fora do Git."""
    root = Path(repo_root) if repo_root else REPO_ROOT
    return root / "work" / "revival-studio" / "server"


def _server_dir(repo_root: Path | str | None) -> Path:
    return (Path(repo_root) if repo_root else REPO_ROOT) / "server"


def _pid_path(repo_root: Path | str | None = None) -> Path:
    return state_dir(repo_root) / "server.pid"


def _log_path(repo_root: Path | str | None = None) -> Path:
    return state_dir(repo_root) / "local-server.log"


def resolve_node() -> str | None:
    """Caminho do executável `node`, ou None quando ausente do PATH."""
    return shutil.which("node")


def _probe(command: list[str], *, timeout: float = 20.0) -> tuple[int, str]:
    """Roda um comando curto capturando saída (sem log — sondas internas)."""
    try:
        proc = subprocess.run(  # noqa: S603 - lista de args, shell=False
            [str(c) for c in command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)
    saida = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode, saida


def check_node() -> tuple[str | None, str | None]:
    """Valida Node.js presente e com `node:sqlite` funcional.

    Devolve `(versão, None)` ou `(None, mensagem_de_erro)` — espelha os dois
    primeiros bloqueios do wrapper de setup (Node 22.5+; 24 LTS recomendado).
    """
    node = resolve_node()
    if not node:
        return None, "Node.js não encontrado no PATH. Instale Node 22.5+ (24 LTS recomendado) e tente novamente."
    rc, saida = _probe([node, "--version"])
    if rc != 0:
        return None, f"node --version falhou (código {rc}): {saida or 'sem saída'}"
    versao = saida.splitlines()[-1].strip() if saida else "?"
    rc, saida = _probe([node, "-e", SQLITE_PROBE])
    if rc != 0:
        return (
            None,
            f"Node {versao} não possui node:sqlite funcional — o servidor exige "
            "Node 22.5+ (24 LTS recomendado).",
        )
    return versao, None


def read_port(repo_root: Path | str | None = None) -> int:
    """Porta do servidor local: `PORT=` do `server/.env`, senão 8080."""
    env_file = _server_dir(repo_root) / ".env"
    if env_file.is_file():
        try:
            for linha in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
                linha = linha.strip()
                if linha.startswith("PORT="):
                    bruto = linha.split("=", 1)[1].strip().strip('"').strip("'")
                    try:
                        porta = int(bruto)
                    except ValueError:
                        continue
                    if 1 <= porta <= 65535:
                        return porta
        except OSError:
            pass
    return DEFAULT_PORT


def health_probe(port: int, *, timeout: float = HEALTH_TIMEOUT) -> dict | None:
    """GET /revival/health em 127.0.0.1:porta — payload ou None (sem servidor)."""
    url = f"http://127.0.0.1:{int(port)}{HEALTH_PATH}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resposta:  # noqa: S310 - localhost fixo
            if resposta.status != 200:
                return None
            import json

            dados = json.loads(resposta.read().decode("utf-8", errors="replace"))
            return dados if isinstance(dados, dict) else None
    except Exception:  # URLError, timeout, JSON inválido, conexão recusada
        return None


def pid_alive(pid: int | None) -> bool:
    """Checagem de processo vivo sem dependências externas (Win32/POSIX)."""
    if not pid or pid <= 0:
        return False
    if WINDOWS:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _tail(path: Path, linhas: int = 25) -> str:
    try:
        conteudo = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(conteudo[-linhas:])


def _spawn_node(node: str, cwd: Path, log_file: Any) -> "subprocess.Popen[bytes]":
    """Inicia o servidor desanexado do console do Studio (PID registrado)."""
    kwargs: dict[str, Any] = {}
    if WINDOWS:
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(  # noqa: S603 - lista de args, shell=False
        [node, "src/index.js"],
        cwd=str(cwd),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        shell=False,
        **kwargs,
    )


def _terminate(proc: "subprocess.Popen[bytes]") -> None:
    for metodo in (proc.terminate, proc.kill):
        try:
            metodo()
            proc.wait(timeout=5)
            return
        except Exception:
            continue


# ----------------------------------------------------------------------
# preparo (espelha o wrapper de setup, etapas 1-4)
# ----------------------------------------------------------------------


def prepare_server(repo_root: Path | str | None, ctx: Any) -> ServerReport:
    """Prepara o servidor local: Node, configs, `node --check` e smoke test.

   Configs locais existentes nunca são sobrescritos — o example só é copiado
    quando o arquivo local falta. Falha devolve relatório com `erro` (a UI
    decide como mostrar); não levanta exceção por defeito esperado.
    """
    raiz = Path(repo_root) if repo_root else REPO_ROOT
    server = _server_dir(raiz)
    relatorio = ServerReport(ok=False)

    # 1/4 — Node.js + node:sqlite
    ctx.progress("servidor", "validando Node.js e node:sqlite…", None)
    versao, erro = check_node()
    relatorio.node_version = versao
    if erro:
        relatorio.erro = erro
        return relatorio
    node = resolve_node()
    assert node is not None  # check_node garantiu
    relatorio.steps.append(f"node {versao} com node:sqlite OK")

    # configs example -> local (somente quando faltam)
    ctx.progress("servidor", "garantindo configs locais a partir dos examples…", None)
    for destino_rel, origem_rel in CONFIG_COPIES:
        destino = server / destino_rel
        if destino.exists():
            continue
        origem = server / origem_rel
        if not origem.is_file():
            relatorio.erro = (
                f"example ausente: server/{origem_rel} — o repositório está "
                "incompleto; restaure o arquivo antes de preparar."
            )
            return relatorio
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origem, destino)
        relatorio.copied.append(destino_rel)
    copiados = len(relatorio.copied)
    relatorio.steps.append(f"configs: {copiados} criado(s), existentes preservados")

    for sub in ("runtime", "data"):
        (server / sub).mkdir(parents=True, exist_ok=True)

    # 2/4 — sintaxe
    ctx.progress("servidor", "validando sintaxe dos módulos do servidor…", None)
    for arquivo in CHECK_FILES:
        rc = ctx.run_process(
            [node, "--check", arquivo],
            cwd=server,
            stage="servidor",
            timeout=60,
        )
        if rc != 0:
            relatorio.erro = f"node --check falhou em server/{arquivo} (código {rc})."
            return relatorio
    relatorio.steps.append(f"node --check OK em {len(CHECK_FILES)} arquivo(s)")

    # 3/4 — smoke end-to-end local
    ctx.progress("servidor", "executando smoke test do servidor…", None)
    rc = ctx.run_process(
        [node, "test/smoke.mjs"],
        cwd=server,
        stage="servidor",
        timeout=300,
    )
    if rc != 0:
        relatorio.erro = f"smoke test do servidor falhou (código {rc}) — veja o log acima."
        return relatorio
    relatorio.steps.append("smoke test end-to-end OK")

    relatorio.ok = True
    return relatorio


# ----------------------------------------------------------------------
# início / parada / status
# ----------------------------------------------------------------------


def start_server(repo_root: Path | str | None, ctx: Any) -> ServerReport:
    """Inicia o servidor local em segundo plano e espera o health ficar verde.

    Idempotente: se o health já responde, devolve `ja_em_execucao` sem criar
    outro processo. Exige `.env` presente (ou seja: preparo já executado).
    """
    raiz = Path(repo_root) if repo_root else REPO_ROOT
    server = _server_dir(raiz)
    porta = read_port(raiz)
    relatorio = ServerReport(ok=False, port=porta, log_path=str(_log_path(raiz)))

    if not (server / ".env").is_file():
        relatorio.erro = (
            "server/.env não existe — execute Servidor → Preparar servidor local "
            "antes de iniciar."
        )
        return relatorio

    ctx.progress("servidor", "checando se o servidor já está em execução…", None)
    saude = health_probe(porta)
    if saude is not None:
        relatorio.ok = True
        relatorio.ja_em_execucao = True
        relatorio.health = saude
        relatorio.pid = _ler_pid(raiz)
        relatorio.steps.append(f"health já responde na porta {porta} — nada a fazer")
        return relatorio

    versao, erro = check_node()
    relatorio.node_version = versao
    if erro:
        relatorio.erro = erro
        return relatorio
    node = resolve_node()
    assert node is not None

    state = state_dir(raiz)
    state.mkdir(parents=True, exist_ok=True)
    log_path = _log_path(raiz)

    ctx.progress("servidor", f"iniciando node src/index.js (porta {porta})…", None)
    with log_path.open("ab") as log_file:
        proc = _spawn_node(node, server, log_file)
    relatorio.pid = proc.pid
    _pid_path(raiz).write_text(str(proc.pid), encoding="ascii")

    limite = time.monotonic() + START_TIMEOUT
    while time.monotonic() < limite:
        ctx.raise_if_cancelled()
        saude = health_probe(porta)
        if saude is not None:
            relatorio.ok = True
            relatorio.health = saude
            relatorio.steps.append(
                f"health OK na porta {porta} (pid {proc.pid}, log {log_path.name})"
            )
            return relatorio
        if proc.poll() is not None:
            break  # processo morreu antes de responder
        time.sleep(0.5)

    # não subiu: encerramos o que nós mesmos iniciamos e reportamos o log.
    # O estado é capturado ANTES do _terminate — depois dele o poll() é sempre
    # não-None e o timeout seria confundido com morte espontânea.
    morreu_sooinho = proc.poll() is not None
    codigo = proc.returncode
    _terminate(proc)
    try:
        _pid_path(raiz).unlink()
    except OSError:
        pass
    rastro = _tail(log_path)
    if morreu_sooinho:
        relatorio.erro = (
            f"o servidor encerrou sozinho (código {codigo}) antes de "
            f"responder na porta {porta}."
        )
    else:
        relatorio.erro = (
            f"o servidor não respondeu em /revival/health na porta {porta} dentro "
            f"de {START_TIMEOUT:.0f}s e foi encerrado."
        )
    if rastro:
        relatorio.erro += f"\n\nÚltimas linhas do log ({log_path}):\n{rastro}"
    return relatorio


def _ler_pid(repo_root: Path | str | None) -> int | None:
    try:
        texto = _pid_path(repo_root).read_text(encoding="ascii").strip()
    except OSError:
        return None
    try:
        return int(texto)
    except ValueError:
        return None


def stop_server(repo_root: Path | str | None, ctx: Any) -> ServerReport:
    """Encerra o servidor local iniciado pelo Studio (PID registrado).

    Recusa-se a matar processo desconhecido: sem PID do Studio e com health
    respondendo, devolve erro instruindo o encerramento manual.
    """
    raiz = Path(repo_root) if repo_root else REPO_ROOT
    porta = read_port(raiz)
    relatorio = ServerReport(ok=False, port=porta)

    pid = _ler_pid(raiz)
    saude = health_probe(porta)
    relatorio.health = saude

    if pid is None:
        if saude is not None:
            relatorio.erro = (
                f"há um servidor respondendo na porta {porta}, mas sem PID "
                "registrado pelo Studio (iniciado fora dele). Encerre-o "
                "manualmente no terminal/processo que o iniciou."
            )
            return relatorio
        relatorio.ok = True
        relatorio.steps.append("nenhum servidor local em execução — nada a fazer")
        return relatorio

    ctx.progress("servidor", f"encerrando servidor local (pid {pid})…", None)
    if WINDOWS:
        rc, saida = _probe(["taskkill", "/PID", str(pid), "/T", "/F"])
        if rc != 0:
            relatorio.erro = f"taskkill falhou (código {rc}): {saida or 'sem saída'}"
            return relatorio
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        limite = time.monotonic() + STOP_TIMEOUT
        while time.monotonic() < limite and pid_alive(pid):
            time.sleep(0.25)
        if pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    # confere o efeito: health precisa parar de responder
    limite = time.monotonic() + STOP_TIMEOUT
    while time.monotonic() < limite:
        if health_probe(porta) is None:
            break
        time.sleep(0.25)

    try:
        _pid_path(raiz).unlink()
    except OSError:
        pass

    if health_probe(porta) is not None:
        relatorio.pid = pid
        relatorio.erro = (
            f"PID {pid} foi encerrado, mas a porta {porta} ainda responde — "
            "outro processo pode estar atendendo; confira manualmente."
        )
        return relatorio

    relatorio.ok = True
    relatorio.pid = pid
    relatorio.steps.append(f"servidor encerrado (pid {pid}, porta {porta} livre)")
    return relatorio


def server_status(repo_root: Path | str | None = None) -> dict:
    """Estado instantâneo do servidor local para exibição na UI."""
    raiz = Path(repo_root) if repo_root else REPO_ROOT
    porta = read_port(raiz)
    pid = _ler_pid(raiz)
    return {
        "porta": porta,
        "pid": pid,
        "pid_vivo": pid_alive(pid),
        "health": health_probe(porta),
        "log_path": str(_log_path(raiz)),
    }
