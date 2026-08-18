"""Aba Compatibilidade do Revival Studio (fase 16): registro 116 rotas.

Regras do plano (§23) que este módulo obedece:

- lê `compatibility.json` **sem modificá-lo diretamente** — a aba é
  somente-leitura sobre o arquivo;
- mutação de evidência acontece SOMENTE chamando o script oficial
  `scripts/generate_endpoint_matrix.py --set ROTA=campo=valor`, com o diff
  antes/depois exibido ao usuário (toda mudança é auditável);
- não existe checkbox manual "done" — nenhuma widget desta aba escreve no
  registro fora do script oficial;
- a próxima tarefa vem de `scripts/next_task.py --json` (fila determinística);
- o estado do servidor vivo vem de `GET /revival/research`; em modo final
  exigimos `research_mode=false` e zero fallbacks — a aba avisa, não decide.
"""
from __future__ import annotations

import difflib
import json
import subprocess
import sys
import tkinter as tk
import urllib.error
import urllib.request
from pathlib import Path
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # só para anotações; evita ciclo de import em runtime
    from .app import StudioApp

# Gates DoD na ordem do registro (igual ao next_task.py; None = não aplicável)
DOD_GATES = (
    "schema_extracted", "implemented", "request_observed", "response_observed",
    "client_validated", "persistence_validated", "regression_test",
)

CAMPOS_EDITAVEIS = (
    "schema_extracted", "client_validated", "persistence_validated", "uses_fallback",
)

COLUNAS = ("rota", "modulo", "gate", "impl", "fallback")


class CompatError(RuntimeError):
    """Falha de leitura/consulta na aba Compatibilidade (sem mutar nada)."""


# ----------------------------------------------------------------------
# funções de módulo — rodam na worker thread ou direto, nunca tocam widget
# ----------------------------------------------------------------------

def load_registry(repo_root: Path) -> dict:
    caminho = Path(repo_root) / "compatibility.json"
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CompatError(f"não foi possível ler {caminho}: {exc}") from exc


def first_open_gate(endpoint: dict) -> str | None:
    """Primeiro gate DoD falso (None = não aplicável); depois usa uses_fallback."""
    for gate in DOD_GATES:
        valor = endpoint.get(gate)
        if valor is None:
            continue
        if valor is False:
            return gate
    if endpoint.get("uses_fallback"):
        return "uses_fallback"
    return None


def summarize_registry(reg: dict) -> dict:
    endpoints = reg.get("endpoints", {})
    resumo = {
        "total": len(endpoints),
        "implemented": 0,
        "dod_completo": 0,
        "schemas": 0,
        "requests": 0,
        "responses": 0,
        "client_validated": 0,
        "persist_ok": 0,
        "persist_false": 0,
        "persist_null": 0,
        "regression": 0,
        "fallbacks": 0,
        "server_only": len(reg.get("server_only_routes", [])),
    }
    for ep in endpoints.values():
        if ep.get("implemented"):
            resumo["implemented"] += 1
        if first_open_gate(ep) is None:
            resumo["dod_completo"] += 1
        if ep.get("schema_extracted"):
            resumo["schemas"] += 1
        if ep.get("request_observed"):
            resumo["requests"] += 1
        if ep.get("response_observed"):
            resumo["responses"] += 1
        if ep.get("client_validated"):
            resumo["client_validated"] += 1
        persistencia = ep.get("persistence_validated")
        if persistencia is True:
            resumo["persist_ok"] += 1
        elif persistencia is False:
            resumo["persist_false"] += 1
        else:
            resumo["persist_null"] += 1
        if ep.get("regression_test"):
            resumo["regression"] += 1
        if ep.get("uses_fallback"):
            resumo["fallbacks"] += 1
    return resumo


def render_resumo(resumo: dict) -> str:
    return (
        f"Rotas: {resumo['total']}  ·  implementadas: {resumo['implemented']}\n"
        f"DoD completo: {resumo['dod_completo']}  ·  schemas extraídos: {resumo['schemas']}\n"
        f"req observados: {resumo['requests']}  ·  resp observados: {resumo['responses']}\n"
        f"validado no cliente: {resumo['client_validated']}  ·  "
        f"testes de regressão: {resumo['regression']}\n"
        f"persistência: {resumo['persist_ok']} ok / {resumo['persist_false']} pendente / "
        f"{resumo['persist_null']} n/a\n"
        f"fallbacks: {resumo['fallbacks']} (modo final exige 0)\n"
        f"rotas só no servidor: {resumo['server_only']}"
    )


def run_next_task(repo_root: Path) -> dict:
    """Roda `python scripts/next_task.py --json` e devolve o payload."""
    script = Path(repo_root) / "scripts" / "next_task.py"
    try:
        proc = subprocess.run(  # noqa: S603 - lista de args, shell=False
            [sys.executable, str(script), "--json"],
            cwd=str(repo_root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CompatError(f"next_task.py falhou: {exc}") from exc
    if proc.returncode not in (0, 3):
        raise CompatError(f"next_task.py exit {proc.returncode}: {proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout)
    except ValueError as exc:
        raise CompatError(f"next_task.py devolveu JSON inválido: {exc}") from exc


def render_proxima(payload: dict) -> str:
    task = payload.get("task")
    if payload.get("status") != "task" or task is None:
        return "— nenhuma tarefa restante na fila (next_task.py) —"
    pendentes = ", ".join(
        f"{p['endpoint']} ({p['gate']})" for p in task.get("module_pending", [])[:5]
    )
    return (
        f"[{task.get('module_priority', '?')} {task.get('module')}] "
        f"{task.get('endpoint')}\n"
        f"gate aberto: {task.get('gate')}\n"
        f"ação: {task.get('action')}\n"
        f"evidência: {task.get('evidence') or '—'}\n"
        f"fila do módulo ({task.get('module_total')}): {pendentes}"
    )


def fetch_research(base_url: str, timeout: float = 10.0) -> dict:
    """GET /revival/research (json puro, sem envelope e sem token)."""
    url = base_url.rstrip("/") + "/revival/research"
    requisicao = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:  # noqa: S310
            return json.loads(resposta.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise CompatError(f"consulta a {url} falhou: {exc}") from exc


def apply_evidence(repo_root: Path, route: str, field: str, value: str, ctx: Any) -> dict:
    """Muta evidência chamando o script oficial; devolve o diff do registro.

    Esta aba NUNCA escreve em compatibility.json — só o
    generate_endpoint_matrix.py toca o arquivo. O diff prova o que mudou.
    """
    if field not in CAMPOS_EDITAVEIS:
        raise CompatError(f"campo {field!r} não é editável via script oficial")
    if value not in ("true", "false", "null"):
        raise CompatError(f"valor {value!r} inválido (true/false/null)")
    if value == "null" and field != "persistence_validated":
        raise CompatError("null só é aceito para persistence_validated")

    compat_path = Path(repo_root) / "compatibility.json"
    antes = compat_path.read_text(encoding="utf-8").splitlines()
    argv = [
        sys.executable, str(Path(repo_root) / "scripts" / "generate_endpoint_matrix.py"),
        "--set", f"{route}={field}={value}",
    ]
    codigo = ctx.run_process(argv, cwd=Path(repo_root), stage="compat", timeout=300)
    if codigo != 0:
        raise RuntimeError(f"generate_endpoint_matrix.py falhou com exit {codigo}")
    depois = compat_path.read_text(encoding="utf-8").splitlines()
    diff = "\n".join(difflib.unified_diff(
        antes, depois, fromfile="compatibility.json (antes)", tofile="compatibility.json (depois)",
        lineterm="",
    ))
    return {"diff": diff, "changed": bool(diff)}


# ----------------------------------------------------------------------
# aba
# ----------------------------------------------------------------------

class CompatTab(ttk.Frame):
    """Painel somente-leitura do registro + mutação via script oficial."""

    def __init__(self, master: Any, app: "StudioApp") -> None:
        super().__init__(master, padding=10)
        self.app = app
        self.registro: dict | None = None

        self.var_resumo = tk.StringVar(value="— registro não lido —")
        self.var_proxima = tk.StringVar(value="— next_task.py ainda não rodou —")
        self.var_url = tk.StringVar()
        self.var_campo = tk.StringVar(value=CAMPOS_EDITAVEIS[0])
        self.var_valor = tk.StringVar(value="true")

        self._construir()
        self.recarregar(silencioso=True)

    # ------------------------------------------------------------------
    # construção
    # ------------------------------------------------------------------

    def _construir(self) -> None:
        self.columnconfigure(0, weight=0, minsize=340)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        lateral = ttk.Frame(self)
        lateral.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 10))
        lateral.columnconfigure(0, weight=1)

        # ---- resumo do registro
        painel_resumo = ttk.LabelFrame(lateral, text="Registro (compatibility.json)", padding=8)
        painel_resumo.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        painel_resumo.columnconfigure(0, weight=1)
        self.lbl_resumo = ttk.Label(
            painel_resumo, textvariable=self.var_resumo, wraplength=320, justify="left",
        )
        self.lbl_resumo.grid(row=0, column=0, sticky="w")
        ttk.Button(painel_resumo, text="Recarregar registro", command=self.recarregar).grid(
            row=1, column=0, sticky="ew", pady=(6, 0),
        )
        ttk.Label(
            painel_resumo,
            text="Somente leitura — nada aqui edita o JSON.",
            wraplength=320, foreground="#666",
        ).grid(row=2, column=0, sticky="w", pady=(2, 0))

        # ---- próxima tarefa
        painel_proxima = ttk.LabelFrame(lateral, text="Próxima tarefa (next_task.py)", padding=8)
        painel_proxima.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        painel_proxima.columnconfigure(0, weight=1)
        self.lbl_proxima = ttk.Label(
            painel_proxima, textvariable=self.var_proxima, wraplength=320, justify="left",
        )
        self.lbl_proxima.grid(row=0, column=0, sticky="w")
        ttk.Button(painel_proxima, text="Atualizar próxima tarefa", command=self.atualizar_proxima).grid(
            row=1, column=0, sticky="ew", pady=(6, 0),
        )

        # ---- evidência via script oficial
        painel_set = ttk.LabelFrame(lateral, text="Evidência via script oficial", padding=8)
        painel_set.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        painel_set.columnconfigure(1, weight=1)
        ttk.Label(painel_set, text="Rota selecionada:").grid(row=0, column=0, sticky="w")
        self.lbl_rota_set = ttk.Label(painel_set, text="—", wraplength=200)
        self.lbl_rota_set.grid(row=0, column=1, sticky="w")
        ttk.Label(painel_set, text="Campo").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.cmb_campo = ttk.Combobox(
            painel_set, textvariable=self.var_campo, values=list(CAMPOS_EDITAVEIS),
            state="readonly", width=24,
        )
        self.cmb_campo.grid(row=1, column=1, sticky="ew", pady=(4, 0))
        self.cmb_campo.bind("<<ComboboxSelected>>", lambda _e: self._sync_valores())
        ttk.Label(painel_set, text="Valor").grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.cmb_valor = ttk.Combobox(
            painel_set, textvariable=self.var_valor, values=["true", "false"],
            state="readonly", width=24,
        )
        self.cmb_valor.grid(row=2, column=1, sticky="ew", pady=(4, 0))
        self.btn_set = ttk.Button(
            painel_set, text="Aplicar (roda generate_endpoint_matrix.py)", command=self.aplicar_evidencia,
        )
        self.btn_set.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(
            painel_set,
            text=("O diff antes/depois aparece no painel de detalhe.\n"
                  "Nenhuma mudança acontece sem o script oficial."),
            wraplength=320, foreground="#666",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # ---- servidor vivo
        painel_srv = ttk.LabelFrame(lateral, text="Servidor vivo (/revival/research)", padding=8)
        painel_srv.grid(row=3, column=0, sticky="ew")
        painel_srv.columnconfigure(0, weight=1)
        self.ent_url = ttk.Entry(painel_srv, textvariable=self.var_url)
        self.ent_url.grid(row=0, column=0, sticky="ew")
        self.ent_url.insert(0, "https://")
        ttk.Button(painel_srv, text="Consultar research", command=self.consultar_research).grid(
            row=1, column=0, sticky="ew", pady=(6, 0),
        )
        self.lbl_research = ttk.Label(
            painel_srv, text="— não consultado —", wraplength=320, justify="left",
        )
        self.lbl_research.grid(row=2, column=0, sticky="w", pady=(4, 0))

        # ---- árvore de endpoints
        area = ttk.LabelFrame(self, text="Endpoints — DoD por rota", padding=6)
        area.grid(row=0, column=1, sticky="nsew")
        area.columnconfigure(0, weight=1)
        area.rowconfigure(0, weight=3)
        area.rowconfigure(1, weight=2)

        self.tree = ttk.Treeview(area, columns=COLUNAS, show="headings", selectmode="browse")
        for col, texto, largura in (
            ("rota", "rota", 240), ("modulo", "módulo", 90),
            ("gate", "próximo gate", 140), ("impl", "impl", 50), ("fallback", "fallback", 60),
        ):
            self.tree.heading(col, text=texto)
            self.tree.column(col, width=largura, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._mostrar_selecao())
        barra = ttk.Scrollbar(area, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=barra.set)
        barra.grid(row=0, column=1, sticky="ns")

        self.txt_detalhe = tk.Text(area, wrap="none", state="disabled", height=10)
        self.txt_detalhe.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(6, 0))

    def _sync_valores(self) -> None:
        valores = ["true", "false", "null"] if self.var_campo.get() == "persistence_validated" \
            else ["true", "false"]
        self.cmb_valor.configure(values=valores)
        if self.var_valor.get() not in valores:
            self.var_valor.set(valores[0])

    # ------------------------------------------------------------------
    # leitura (sem mutação)
    # ------------------------------------------------------------------

    def recarregar(self, silencioso: bool = False) -> None:
        try:
            registro = load_registry(self.app.repo_root)
        except CompatError as exc:
            self.registro = None
            self.var_resumo.set(f"— registro não lido —\n{exc}")
            if not silencioso:
                messagebox.showerror("Compatibilidade", str(exc), parent=self)
            return
        self.registro = registro
        resumo = summarize_registry(registro)
        self.var_resumo.set(render_resumo(resumo))
        self._povoar_tree(registro)
        if not silencioso:
            self.app.log.append(
                f"[compat] registro relido: {resumo['total']} rotas, "
                f"{resumo['dod_completo']} DoD completo, {resumo['fallbacks']} fallback(s)",
                "info",
            )

    def _povoar_tree(self, registro: dict) -> None:
        self.tree.delete(*self.tree.get_children())
        for rota in sorted(registro.get("endpoints", {})):
            ep = registro["endpoints"][rota]
            self.tree.insert("", "end", iid=rota, values=(
                rota, ep.get("module", "?"), first_open_gate(ep) or "DoD completo",
                "sim" if ep.get("implemented") else "não",
                "sim" if ep.get("uses_fallback") else "não",
            ))

    def _mostrar_selecao(self) -> None:
        selecao = self.tree.selection()
        if not selecao or self.registro is None:
            return
        rota = selecao[0]
        ep = self.registro["endpoints"].get(rota, {})
        self.lbl_rota_set.configure(text=rota)
        self._escrever_detalhe(
            f"== {rota} ==\n\n" + json.dumps(ep, indent=2, ensure_ascii=False)
        )

    def _escrever_detalhe(self, texto: str) -> None:
        self.txt_detalhe.config(state="normal")
        self.txt_detalhe.delete("1.0", "end")
        self.txt_detalhe.insert("1.0", texto)
        self.txt_detalhe.config(state="disabled")

    # ------------------------------------------------------------------
    # próxima tarefa
    # ------------------------------------------------------------------

    def atualizar_proxima(self) -> None:
        repo = self.app.repo_root
        self.app._submit(
            "compat-next-task",
            lambda ctx: run_next_task(repo),
            ao_concluir=self._apos_proxima,
        )

    def _apos_proxima(self, evento: Any) -> None:
        self.var_proxima.set(render_proxima(evento.result))
        self.app.log.append("[compat] próxima tarefa atualizada", "info")

    # ------------------------------------------------------------------
    # mutação auditável — somente via script oficial
    # ------------------------------------------------------------------

    def aplicar_evidencia(self) -> None:
        selecao = self.tree.selection()
        if not selecao:
            messagebox.showwarning(
                "Evidência", "selecione uma rota na tabela primeiro.", parent=self,
            )
            return
        rota = selecao[0]
        campo = self.var_campo.get()
        valor = self.var_valor.get()
        if campo not in CAMPOS_EDITAVEIS or valor not in ("true", "false", "null"):
            return
        if not messagebox.askyesno(
            "Aplicar evidência",
            f"Rodar o script oficial?\n\n"
            f"python scripts/generate_endpoint_matrix.py \\\n"
            f"    --set {rota}={campo}={valor}\n\n"
            f"O diff de compatibility.json será exibido antes de você confirmar\n"
            f"qualquer coisa nova. O registro nunca é editado à mão.",
            parent=self,
        ):
            return
        repo = self.app.repo_root
        self.app._submit(
            "compat-apply-evidence",
            lambda ctx: apply_evidence(repo, rota, campo, valor, ctx),
            ao_concluir=lambda evento: self._apos_aplicar(rota, campo, valor, evento),
        )

    def _apos_aplicar(self, rota: str, campo: str, valor: str, evento: Any) -> None:
        resultado = evento.result
        self._escrever_detalhe(
            f"$ python scripts/generate_endpoint_matrix.py --set {rota}={campo}={valor}\n\n"
            + (resultado["diff"] or "(nenhuma mudança de conteúdo)")
        )
        self.app.log.append(
            f"[compat] evidência aplicada via script oficial: {rota} {campo}={valor} "
            f"({'diff gerado' if resultado['changed'] else 'sem mudança de conteúdo'})",
            "info",
        )
        self.recarregar(silencioso=True)

    # ------------------------------------------------------------------
    # servidor vivo
    # ------------------------------------------------------------------

    def consultar_research(self) -> None:
        url = self.var_url.get().strip()
        if not url.startswith(("http://", "https://")) or url in ("http://", "https://"):
            messagebox.showwarning(
                "Research", "informe a URL base do servidor (ex.: https://host).", parent=self,
            )
            return
        self.app._submit(
            "compat-research",
            lambda ctx: fetch_research(url),
            ao_concluir=self._apos_research,
        )

    def _apos_research(self, evento: Any) -> None:
        research = evento.result
        avisos: list[str] = []
        if research.get("research_mode"):
            avisos.append("research_mode ATIVO — modo final exige RESEARCH_MODE=false")
        total = int(research.get("fallback_total", 0))
        if total:
            avisos.append(f"{total} fallback(s) observados — modo final exige zero")
        top = "\n".join(
            f"  {item.get('path')}: {item.get('count')}x" for item in research.get("fallback_endpoints", [])[:5]
        )
        estado = "AVISO" if avisos else "OK"
        texto = (
            f"[{estado}] research_mode={research.get('research_mode')} · "
            f"fallback_total={total}\n{top if top else '  (sem fallbacks registrados)'}"
        )
        self.lbl_research.configure(text=texto)
        for aviso in avisos:
            self.app.log.append(f"[compat] {aviso}", "aviso")
        if not avisos:
            self.app.log.append("[compat] /revival/research: sem research e sem fallbacks", "info")
