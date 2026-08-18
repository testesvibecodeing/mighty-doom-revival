"""JobRunner assíncrono do Revival Studio (fase 2 do plano).

Padrão reaproveitado de `scripts/loading_screen_editor.py`, que já acerta o
essencial: worker thread + `queue.Queue` + `after()` no lado Tk.

Contrato inegociável:

- **a worker thread nunca toca widget**. Ela só publica evento na fila;
- quem drena a fila é a thread da UI, via `poll()` dentro de um `after()`;
- **um único job mutável por projeto** — `submit()` recusa concorrente;
- cancelamento é **cooperativo** para Python (`ctx.raise_if_cancelled()`) e
  encerramento controlado para subprocesso (terminate, depois kill);
- cancelamento durante escrita **não** substitui a saída válida anterior: quem
  escreve usa `ctx.temp_path()` e só promove no fim (`promote_atomic`).

Este módulo não importa Tkinter.
"""
from __future__ import annotations

import os
import queue
import subprocess
import threading
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .models import Failure, StageProgress
from .redaction import mask_secrets

__all__ = [
    "JobState",
    "JobCancelled",
    "JobTimeout",
    "CancelToken",
    "JobContext",
    "LogEvent",
    "ProgressEvent",
    "DoneEvent",
    "JobHandle",
    "JobRunner",
    "promote_atomic",
]


class JobState(str, Enum):
    PENDENTE = "pendente"
    RODANDO = "rodando"
    CONCLUIDO = "concluido"
    FALHOU = "falhou"
    CANCELADO = "cancelado"
    TIMEOUT = "timeout"

    @property
    def terminal(self) -> bool:
        return self in _TERMINAIS


_TERMINAIS = frozenset(
    {JobState.CONCLUIDO, JobState.FALHOU, JobState.CANCELADO, JobState.TIMEOUT}
)


class JobCancelled(Exception):
    """Levantada dentro do worker quando o usuário cancela."""


class JobTimeout(Exception):
    """Levantada quando o job estoura o tempo limite."""


class CancelToken:
    """Sinal de cancelamento compartilhado entre UI e worker."""

    def __init__(self) -> None:
        self._evento = threading.Event()
        self._motivo = "cancelado pelo usuário"

    def cancel(self, motivo: str = "cancelado pelo usuário") -> None:
        self._motivo = motivo
        self._evento.set()

    @property
    def cancelled(self) -> bool:
        return self._evento.is_set()

    @property
    def reason(self) -> str:
        return self._motivo

    def raise_if_cancelled(self) -> None:
        if self._evento.is_set():
            raise JobCancelled(self._motivo)

    def wait(self, timeout: float | None = None) -> bool:
        return self._evento.wait(timeout)


@dataclass(frozen=True)
class LogEvent:
    job_id: int
    line: str
    stream: str = "info"


@dataclass(frozen=True)
class ProgressEvent:
    job_id: int
    progress: StageProgress


@dataclass(frozen=True)
class DoneEvent:
    job_id: int
    name: str
    state: JobState
    result: Any = None
    failure: Failure | None = None
    duration_seconds: float = 0.0


def promote_atomic(temporario: Path, destino: Path) -> Path:
    """Promove `temporario` para `destino` sem deixar destino parcial.

    `os.replace` é atômico dentro do mesmo volume. Se o job for cancelado antes
    desta chamada, o `destino` anterior — que era válido — continua intacto.
    """
    temporario = Path(temporario)
    destino = Path(destino)
    if not temporario.is_file():
        raise FileNotFoundError(f"temporário ausente, nada a promover: {temporario}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temporario, destino)
    return destino


class JobContext:
    """O que a função de trabalho recebe. Só fala com a fila.

    Nunca exponha widget, `root` ou variável Tk aqui.
    """

    def __init__(
        self,
        job_id: int,
        fila: "queue.Queue[Any]",
        token: CancelToken,
        *,
        workspace: Path | None = None,
    ) -> None:
        self.job_id = job_id
        self._fila = fila
        self.cancel_token = token
        self.workspace = workspace
        self._temporarios: list[Path] = []

    # -- comunicação com a UI -------------------------------------------------

    def log(self, linha: str, *, stream: str = "info") -> None:
        """Publica uma linha de log já mascarada."""
        self._fila.put(LogEvent(self.job_id, mask_secrets(linha).rstrip("\n"), stream))

    def progress(
        self,
        stage: str,
        message: str,
        fraction: float | None = None,
        *,
        current: int | None = None,
        total: int | None = None,
    ) -> None:
        self._fila.put(
            ProgressEvent(
                self.job_id,
                StageProgress(
                    stage=stage,
                    message=mask_secrets(message),
                    fraction=fraction,
                    current=current,
                    total=total,
                ),
            )
        )

    # -- cancelamento ---------------------------------------------------------

    @property
    def cancelled(self) -> bool:
        return self.cancel_token.cancelled

    def raise_if_cancelled(self) -> None:
        """Ponto de cancelamento cooperativo. Chame entre unidades de trabalho."""
        self.cancel_token.raise_if_cancelled()

    # -- escrita segura -------------------------------------------------------

    def temp_path(self, destino: Path | str) -> Path:
        """Caminho temporário irmão de `destino`, registrado para inspeção.

        O plano exige que o temporário **permaneça** se houver cancelamento no
        meio de uma escrita — ele é evidência, não lixo.
        """
        destino = Path(destino)
        temporario = destino.with_name(f"{destino.name}.job{self.job_id}.parcial")
        self._temporarios.append(temporario)
        return temporario

    @property
    def temp_files(self) -> list[Path]:
        return list(self._temporarios)

    # -- subprocesso ----------------------------------------------------------

    def run_process(
        self,
        command: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        stage: str = "processo",
        timeout: float | None = None,
    ) -> int:
        """Roda subprocesso com `shell=False`, transmitindo stdout para o log.

        Encerra o processo de forma controlada quando o usuário cancela:
        `terminate()` e, se resistir, `kill()`. Devolve o exit code.
        """
        if not isinstance(command, (list, tuple)) or not command:
            raise ValueError("command deve ser uma lista de argumentos não vazia")

        self.raise_if_cancelled()
        self.log(f"$ {' '.join(str(c) for c in command)}", stream="cmd")

        ambiente = {**os.environ, **(env or {})} if env else None
        proc = subprocess.Popen(  # noqa: S603 - lista de args, shell=False
            [str(c) for c in command],
            cwd=str(cwd) if cwd else None,
            env=ambiente,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            shell=False,
        )

        limite = (time.monotonic() + timeout) if timeout else None
        try:
            assert proc.stdout is not None
            for linha in proc.stdout:
                self.log(linha.rstrip("\n"), stream="proc")
                if self.cancel_token.cancelled:
                    self._encerrar(proc, "cancelado pelo usuário")
                    raise JobCancelled(self.cancel_token.reason)
                if limite and time.monotonic() > limite:
                    self._encerrar(proc, f"timeout de {timeout}s")
                    raise JobTimeout(f"{stage}: excedeu {timeout}s")
            proc.wait()
        finally:
            if proc.poll() is None:
                self._encerrar(proc, "encerramento de segurança")
            if proc.stdout is not None and not proc.stdout.closed:
                proc.stdout.close()
        return proc.returncode

    def _encerrar(self, proc: subprocess.Popen, motivo: str) -> None:
        self.log(f"[runner] encerrando subprocesso: {motivo}", stream="aviso")
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.log("[runner] processo resistiu ao terminate; matando", stream="aviso")
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.log("[runner] processo não morreu após kill", stream="erro")
        except OSError:
            pass


@dataclass
class JobHandle:
    """Referência ao job em execução, do lado da UI."""

    job_id: int
    name: str
    token: CancelToken
    thread: threading.Thread
    state: JobState = JobState.PENDENTE
    started_at: float = field(default_factory=time.monotonic)
    context: JobContext | None = None

    def cancel(self, motivo: str = "cancelado pelo usuário") -> None:
        self.token.cancel(motivo)


class JobRunner:
    """Executa um job por vez e entrega eventos por fila.

    Uso no lado Tk:

        runner = JobRunner(log_dir=...)
        runner.submit("analisar", funcao)
        def bombear():
            for evento in runner.poll():
                ...   # aqui, e só aqui, mexe em widget
            root.after(100, bombear)
    """

    def __init__(self, *, log_dir: Path | None = None) -> None:
        self._fila: "queue.Queue[Any]" = queue.Queue()
        self._atual: JobHandle | None = None
        self._lock = threading.Lock()
        self._proximo_id = 1
        self._log_dir = Path(log_dir) if log_dir else None
        self._log_handle = None

    # -- estado ---------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._atual is not None and not self._atual.state.terminal

    @property
    def current(self) -> JobHandle | None:
        with self._lock:
            return self._atual

    # -- submissão ------------------------------------------------------------

    def submit(
        self,
        name: str,
        func: Callable[[JobContext], Any],
        *,
        timeout: float | None = None,
        workspace: Path | None = None,
    ) -> JobHandle:
        """Agenda `func(ctx)` numa worker thread.

        Levanta RuntimeError se já houver job vivo — a regra "um único job
        mutável por projeto" impede duas escritas concorrentes no mesmo
        workspace.
        """
        with self._lock:
            if self._atual is not None and not self._atual.state.terminal:
                raise RuntimeError(
                    f"já existe um job em execução: {self._atual.name!r}. "
                    "Cancele-o ou aguarde antes de iniciar outro."
                )
            job_id = self._proximo_id
            self._proximo_id += 1
            token = CancelToken()
            ctx = JobContext(job_id, self._fila, token, workspace=workspace)
            thread = threading.Thread(
                target=self._executar,
                args=(job_id, name, func, ctx, token, timeout),
                name=f"revival-job-{job_id}",
                daemon=True,
            )
            handle = JobHandle(job_id=job_id, name=name, token=token, thread=thread, context=ctx)
            handle.state = JobState.RODANDO
            self._atual = handle
            self._abrir_log(job_id, name)

        thread.start()
        return handle

    # -- worker ---------------------------------------------------------------

    def _executar(
        self,
        job_id: int,
        name: str,
        func: Callable[[JobContext], Any],
        ctx: JobContext,
        token: CancelToken,
        timeout: float | None,
    ) -> None:
        """Corpo da worker thread. Nada aqui pode tocar widget."""
        inicio = time.monotonic()
        estado = JobState.CONCLUIDO
        resultado: Any = None
        falha: Failure | None = None

        cronometro: threading.Timer | None = None
        if timeout:
            cronometro = threading.Timer(
                timeout, lambda: token.cancel(f"timeout de {timeout}s")
            )
            cronometro.daemon = True
            cronometro.start()

        try:
            resultado = func(ctx)
        except JobCancelled as exc:
            estado = JobState.TIMEOUT if "timeout" in str(exc).lower() else JobState.CANCELADO
            falha = Failure(code=estado.value.upper(), stage=name, message=str(exc))
        except JobTimeout as exc:
            estado = JobState.TIMEOUT
            falha = Failure(code="TIMEOUT", stage=name, message=str(exc))
        except Exception as exc:  # noqa: BLE001 - a UI precisa ver qualquer falha
            estado = JobState.FALHOU
            falha = Failure(
                code=type(exc).__name__,
                stage=name,
                message=mask_secrets(str(exc)) or type(exc).__name__,
                details=mask_secrets(traceback.format_exc()),
            )
        finally:
            if cronometro:
                cronometro.cancel()

        # O timer pode ter disparado enquanto a função retornava normalmente.
        if estado is JobState.CONCLUIDO and token.cancelled:
            estado = JobState.TIMEOUT if "timeout" in token.reason.lower() else JobState.CANCELADO
            falha = Failure(code=estado.value.upper(), stage=name, message=token.reason)

        duracao = time.monotonic() - inicio
        with self._lock:
            if self._atual and self._atual.job_id == job_id:
                self._atual.state = estado

        if estado is not JobState.CONCLUIDO and ctx.temp_files:
            for parcial in ctx.temp_files:
                if parcial.exists():
                    ctx.log(f"[runner] parcial preservado para inspeção: {parcial}", stream="aviso")

        self._fila.put(
            DoneEvent(
                job_id=job_id,
                name=name,
                state=estado,
                result=resultado if estado is JobState.CONCLUIDO else None,
                failure=falha,
                duration_seconds=duracao,
            )
        )

    # -- drenagem (thread da UI) ---------------------------------------------

    def poll(self, *, max_events: int = 500) -> list[Any]:
        """Retira eventos da fila. Chame **somente** da thread da UI."""
        eventos: list[Any] = []
        for _ in range(max_events):
            try:
                evento = self._fila.get_nowait()
            except queue.Empty:
                break
            eventos.append(evento)
            self._gravar_log(evento)
        return eventos

    def drain_until_done(self, timeout: float = 30.0) -> tuple[list[Any], DoneEvent | None]:
        """Bloqueia até o job terminar. Para testes e modo headless — não use na GUI."""
        eventos: list[Any] = []
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            try:
                evento = self._fila.get(timeout=0.05)
            except queue.Empty:
                continue
            eventos.append(evento)
            self._gravar_log(evento)
            if isinstance(evento, DoneEvent):
                return eventos, evento
        return eventos, None

    def cancel(self, motivo: str = "cancelado pelo usuário") -> bool:
        with self._lock:
            atual = self._atual
        if atual is None or atual.state.terminal:
            return False
        atual.cancel(motivo)
        return True

    # -- log em arquivo -------------------------------------------------------

    def _abrir_log(self, job_id: int, name: str) -> None:
        if self._log_dir is None:
            return
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            carimbo = time.strftime("%Y%m%d-%H%M%S")
            seguro = "".join(c if c.isalnum() or c in "-_" else "-" for c in name)[:48]
            destino = self._log_dir / f"{carimbo}-job{job_id}-{seguro}.log"
            self._fechar_log()
            self._log_handle = open(destino, "a", encoding="utf-8")
        except OSError:
            self._log_handle = None

    def _gravar_log(self, evento: Any) -> None:
        if self._log_handle is None:
            return
        try:
            if isinstance(evento, LogEvent):
                self._log_handle.write(f"{evento.stream}: {evento.line}\n")
            elif isinstance(evento, ProgressEvent):
                p = evento.progress
                self._log_handle.write(f"progress: [{p.stage}] {p.message}\n")
            elif isinstance(evento, DoneEvent):
                self._log_handle.write(
                    f"done: {evento.name} -> {evento.state.value} em {evento.duration_seconds:.2f}s\n"
                )
                if evento.failure:
                    self._log_handle.write(f"falha: {evento.failure.code} {evento.failure.message}\n")
                self._fechar_log()
                return
            self._log_handle.flush()
        except (OSError, ValueError):
            self._log_handle = None

    def _fechar_log(self) -> None:
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except OSError:
                pass
            self._log_handle = None

    def close(self) -> None:
        self.cancel("runner encerrado")
        self._fechar_log()
