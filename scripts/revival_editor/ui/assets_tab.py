"""Aba Assets do Revival Studio (fase 9): catálogo somente-leitura.

§16.1 do plano — *"catálogo somente-leitura primeiro"*. Esta aba lista,
busca e gera relatório de metadados dos objetos Unity nos bundles do APK do
projeto. Ela NÃO edita nada: a escrita existe apenas como transação de
domínio (`assets_catalog.apply_replacement`) para objetos
EDITÁVEL_VALIDADOS, e a ordem de suporte (§16.3) é o que decide — hoje,
só textura de loading.

O scan é um job do JobRunner (cancelável — o bundle de conteúdo tem 494 MB
e o hash por objeto é pesado de propósito: seletor estável exige hash).
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any

from .. import assets_catalog as ac
from ..project import save_project

if TYPE_CHECKING:  # só para anotações; evita ciclo de import em runtime
    from .app import StudioApp

#: Colunas da árvore: path_id, tipo, nome, dimensões/duração, categoria.
COLUNAS = ("path_id", "tipo", "nome", "dims", "categoria")

CATEGORY_BADGE = {
    ac.EDITAVEL_VALIDADO: "EDITÁVEL_VALIDADO",
    ac.A_VERIFICAR: "A_VERIFICAR",
    ac.SOMENTE_LEITURA: "SOMENTE_LEITURA",
    ac.BLOQUEADO: "BLOQUEADO",
}


class AssetsTab(ttk.Frame):
    """Catálogo somente-leitura dos objetos Unity dos bundles do APK."""

    def __init__(self, master: Any, app: "StudioApp") -> None:
        super().__init__(master, padding=10)
        self.app = app
        self.membros: list[dict[str, Any]] = []
        self.resultado: ac.ScanResult | None = None

        self.var_busca = tk.StringVar()
        self.var_tipo = tk.StringVar()
        self.var_membro = tk.StringVar()

        self._construir()

    # ------------------------------------------------------------------
    # construção
    # ------------------------------------------------------------------

    def _construir(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        topo = ttk.LabelFrame(self, text="Catálogo de assets (somente leitura)", padding=8)
        topo.grid(row=0, column=0, sticky="ew")
        topo.columnconfigure(1, weight=1)

        ttk.Button(topo, text="Listar bundles do APK…", command=self.listar_bundles).grid(
            row=0, column=0, padx=(0, 6)
        )
        self.combo_membro = ttk.Combobox(topo, textvariable=self.var_membro, state="readonly")
        self.combo_membro.grid(row=0, column=1, sticky="ew")
        self.btn_scan = ttk.Button(topo, text="Escanear bundle…", command=self.escanear)
        self.btn_scan.grid(row=0, column=2, padx=6)
        self.btn_scan.state(["disabled"])

        ttk.Label(topo, text="Buscar:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        entrada = ttk.Entry(topo, textvariable=self.var_busca)
        entrada.grid(row=1, column=1, sticky="ew", pady=(8, 0), padx=(6, 0))
        entrada.bind("<KeyRelease>", lambda _e: self.filtrar())
        self.combo_tipo = ttk.Combobox(
            topo, textvariable=self.var_tipo, state="readonly", width=16,
            values=("", "Texture2D", "Sprite", "TextAsset", "MonoBehaviour",
                    "AudioClip", "GameObject", "Shader", "Mesh"),
        )
        self.combo_tipo.grid(row=1, column=2, sticky="w", pady=(8, 0), padx=6)
        self.combo_tipo.bind("<<ComboboxSelected>>", lambda _e: self.filtrar())

        lista = ttk.LabelFrame(self, text="Objetos (metadados — nenhum conteúdo é extraído)", padding=4)
        lista.grid(row=1, column=0, sticky="nsew")
        lista.columnconfigure(0, weight=1)
        lista.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(lista, columns=COLUNAS, show="headings", selectmode="browse")
        for col, largura, ancora in (
            ("path_id", 90, "e"), ("tipo", 110, "w"), ("nome", 320, "w"),
            ("dims", 130, "w"), ("categoria", 150, "w"),
        ):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=largura, anchor=ancora)
        barra = ttk.Scrollbar(lista, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=barra.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._mostrar_seletor())

        self.lbl_info = ttk.Label(
            self, text=(
                "— sem scan —\n"
                "Editável hoje: apenas textura de loading (ordem de suporte §16.3).\n"
                "O relatório carrega só metadados; nenhum asset entra no Git."
            ),
            wraplength=640, justify="left",
        )
        self.lbl_info.grid(row=2, column=0, sticky="w", pady=(6, 0))

    # ------------------------------------------------------------------
    # listagem e scan
    # ------------------------------------------------------------------

    def _apk_do_projeto(self) -> Path | None:
        projeto = self.app.project
        if projeto is None:
            messagebox.showwarning(
                "Catálogo de assets", "abra um projeto primeiro (menu Projeto).", parent=self
            )
            return None
        alvo = projeto.output_apk or projeto.input_apk
        if not alvo or not Path(alvo).is_file():
            messagebox.showerror(
                "Catálogo de assets",
                f"APK não encontrado:\n{alvo or '(nenhum)'}",
                parent=self,
            )
            return None
        return Path(alvo)

    def listar_bundles(self) -> None:
        apk = self._apk_do_projeto()
        if apk is None:
            return
        import zipfile

        try:
            with zipfile.ZipFile(apk, "r") as z:
                self.membros = ac.list_bundle_members(z)
        except (OSError, zipfile.BadZipFile) as exc:
            messagebox.showerror("Catálogo de assets", f"falha abrindo o APK: {exc}", parent=self)
            return
        self.combo_membro["values"] = [
            f"{Path(m['member']).name} ({m['size'] / 1_048_576:.1f} MB)" for m in self.membros
        ]
        if self.membros:
            self.combo_membro.current(0)
        self.btn_scan.state(["!disabled"] if self.membros else ["disabled"])
        self.app.log.append(
            f"[assets] {len(self.membros)} bundle(s) listados em {apk.name}", "info"
        )

    def _membro_selecionado(self) -> str | None:
        if not self.membros:
            return None
        indice = self.combo_membro.current()
        if indice < 0 or indice >= len(self.membros):
            return None
        return self.membros[indice]["member"]

    def escanear(self) -> None:
        apk = self._apk_do_projeto()
        if apk is None:
            return
        membro = self._membro_selecionado()
        if membro is None:
            messagebox.showwarning(
                "Catálogo de assets", "liste os bundles e escolha um primeiro.", parent=self
            )
            return
        if not messagebox.askyesno(
            "Escanear bundle",
            f"Escanear {Path(membro).name}?\n\n"
            "O bundle é extraído para work/ (gitignored) e cada objeto é\n"
            "listado com hash — bundles grandes demoram minutos e o job\n"
            "é cancelável. Nada é gravado no APK.",
            parent=self,
        ):
            return
        from ..paths import project_dir

        pasta = project_dir(self.app.project.project_id, studio_root=self.app.studio_root)
        relatorio = pasta / "reports" / f"assets-catalog-{Path(membro).stem}.json"
        self.app._submit(
            "assets-scan",
            lambda ctx: _trabalho_scan(apk, membro, relatorio, ctx),
            ao_concluir=self._apos_scan,
        )

    def _apos_scan(self, evento: Any) -> None:
        self.resultado = evento.result
        projeto = self.app.project
        if projeto is not None:
            projeto.reports["assets_catalog"] = self.resultado.get("report_path", "")
            save_project(projeto, studio_root=self.app.studio_root)
        self.app.log.append(
            f"[assets] scan concluído: {self.resultado['object_count']} objeto(s) "
            f"— relatório {self.resultado.get('report_path', '(não salvo)')}",
            "info",
        )
        self._povoar(self.resultado["entries"])

    # ------------------------------------------------------------------
    # busca e exibição
    # ------------------------------------------------------------------

    def _povoar(self, entradas: list[ac.AssetEntry]) -> None:
        self.tree.delete(*self.tree.get_children())
        for entrada in entradas:
            dims = (
                f"{entrada.width}×{entrada.height}" if entrada.width
                else f"{entrada.duration:.1f}s" if entrada.duration is not None
                else "—"
            )
            self.tree.insert("", "end", values=(
                entrada.path_id, entrada.type, entrada.name, dims, entrada.category,
            ))
        self.lbl_info.configure(text=f"{len(entradas)} objeto(s) listado(s) — metadados somente")

    def filtrar(self) -> None:
        if self.resultado is None:
            return
        achados = ac.search_entries(
            self.resultado["entries"],
            text=self.var_busca.get(),
            type_name=self.var_tipo.get(),
        )
        self._povoar(achados)

    def _mostrar_seletor(self) -> None:
        selecao = self.tree.selection()
        if not selecao or self.resultado is None:
            return
        valores = self.tree.item(selecao[0], "values")
        try:
            path_id = int(valores[0])
        except ValueError:
            return
        entrada = next(
            (e for e in self.resultado["entries"] if e.path_id == path_id), None
        )
        if entrada is None:
            return
        try:
            seletor = ac.selector_for(self.resultado["apk_sha256"], entrada)
        except ac.AssetsError as exc:
            self.lbl_info.configure(text=str(exc))
            return
        texto = (
            f"seletor estável (§16.2):\n{ac.selector_str(seletor)}\n"
            f"categoria: {entrada.category} — edição exige {ac.EDITAVEL_VALIDADO}"
        )
        self.lbl_info.configure(text=texto)


def _trabalho_scan(apk: Path, membro: str, relatorio: Path, ctx: Any) -> dict:
    ctx.progress("assets", f"escaneando {Path(membro).name}…", None)
    resultado = ac.scan_bundle(apk, membro, ctx.workspace, log=ctx.log)
    salvo = ac.save_report(resultado, relatorio)
    ctx.progress("assets", "scan concluído", 1.0)
    return {**resultado.to_dict(), "entries": resultado.entries, "report_path": str(salvo)}
