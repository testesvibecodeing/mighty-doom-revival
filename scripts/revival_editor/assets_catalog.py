"""Catálogo e transação de assets Unity (fase 9 do plano).

§16.1 — catálogo **somente-leitura primeiro**: lista membro do APK, bundle,
``path_id``, tipo Unity, ``m_Name``, dimensões/duração quando existirem, hash
do objeto e capacidade de escrita. Nada de conteúdo é exportado; o relatório
só carrega metadados sanitizados.

§16.2 — seletores estáveis: uma substituição aponta para
``sha256 do APK + membro do bundle + path_id + tipo + m_Name + hash do
objeto``. Qualquer parte divergente bloqueia em vez de aplicar a um objeto
parecido.

§16.3 — ordem de suporte codificada em `categorize()`: hoje só a textura de
loading é EDITÁVEL_VALIDADA (round-trip provado pelo fluxo de injeção); o
resto é A_VERIFICAR, SOMENTE_LEITURA ou BLOQUEADO. Liberar um conjunto novo
exige fixture e reabertura — mudar a categoria sem isso quebra o gate.

§16.4 — transação de bundle em `apply_replacement()`: cópia temporária no
workspace, confirmação de seletor, escrita UnityPy, reabertura, verificação
do objeto e da contagem, promoção atômica, `zero_catalog_crc()` com
verificação e hashes anterior/posterior no relatório.
"""
from __future__ import annotations

import gc
import hashlib
import json
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from inject_loading_screen import (  # noqa: E402
    MAX_THUMB_DIFF,
    _cover_fit,
    _extract_member,
    _load_unitypy,
    mean_channel_diff,
)
from patch_unity_bundle import zero_catalog_crc  # noqa: E402

__all__ = [
    "AssetsError",
    "SelectorMismatch",
    "TransactionRefused",
    "AssetEntry",
    "ScanResult",
    "EDITAVEL_VALIDADO",
    "SOMENTE_LEITURA",
    "BLOQUEADO",
    "A_VERIFICAR",
    "BLOCKED_TYPES",
    "BLOCKED_APK_MEMBERS",
    "BUNDLE_DIR",
    "categorize",
    "apk_member_category",
    "list_bundle_members",
    "scan_bundle",
    "selector_for",
    "parse_selector",
    "confirm_selector_in_bundle",
    "search_entries",
    "save_report",
    "apply_replacement",
]

#: Categorias do §16.1 — a UI nunca inventa uma quinta.
EDITAVEL_VALIDADO = "EDITÁVEL_VALIDADO"
SOMENTE_LEITURA = "SOMENTE_LEITURA"
BLOQUEADO = "BLOQUEADO"
A_VERIFICAR = "A_VERIFICAR"

#: §16.3: tipos bloqueados no editor genérico, sem exceção.
BLOCKED_TYPES = frozenset({
    "Scene", "GameObject", "MonoScript", "Mesh", "Shader",
})

#: Membros do APK (não-objetos Unity) que o editor nunca toca.
BLOCKED_APK_MEMBERS = frozenset({
    "assets/bin/Data/Managed/Metadata/global-metadata.dat",
})
BLOCKED_APK_SUFFIXES = (".so",)

BUNDLE_DIR = "assets/aa/Android"
CATALOG_MEMBER = "assets/aa/catalog.json"

#: Tipos cujos dados o scanner ousa desserializar (§16.1). `obj.read()` de
#: tipo sem parser nativo no UnityPy desce para o typetree — e um typetree
#: exótico derruba o processo INTEIRO com access violation (comprovado no
#: bundle de conteúdo de 285.669 objetos, UnityPy 1.25.3,
#: `TypeTreeHelper.read_typetree`; não há exceção para capturar). Fora da
#: lista: o objeto entra no catálogo com nome "?" e categoria derivada só
#: do tipo. O fluxo de injeção (fase 7) sempre leu apenas Texture2D —
#: mesma disciplina aqui.
SAFE_READ_TYPES = frozenset({
    "Texture2D",   # provado pela injeção de loading (round-trip CONFIRMADO)
    "Sprite",      # mesmo caminho de parser nativo
    "TextAsset",
    "AudioClip",
})

LogFn = Callable[[str], None]


class AssetsError(Exception):
    """Catálogo/transação recusado — motivo acionável para a UI."""


class SelectorMismatch(AssetsError):
    """O seletor estável divergiu do objeto real — bloqueado por §16.2."""


class TransactionRefused(AssetsError):
    """A categoria do objeto não permite escrita (§16.3 — ordem de suporte)."""


# ---------------------------------------------------------------------------
# §16.3 — categorização (função pura: testável sem UnityPy)
# ---------------------------------------------------------------------------

def categorize(type_name: str, obj_name: str) -> str:
    """Categoria de escrita de um objeto Unity pela ordem de suporte.

    - Textura de loading: EDITÁVEL_VALIDADO — round-trip do fluxo de injeção
      (bundle reaberto, decodificado e comparado) é a prova existente;
    - Texture2D/Sprite/TextAsset/MonoBehaviour fora disso: A_VERIFICAR —
      liberar exige fixture própria e reabertura do bundle, um conjunto
      por vez;
    - AudioClip: SOMENTE_LEITURA até existir writer com round-trip do
      formato real;
    - Scene/GameObject/MonoScript/Mesh/Shader: BLOQUEADO no editor genérico.
    """
    if type_name == "Texture2D" and (
        obj_name == "loading_background" or "LoadingBackground" in obj_name
    ):
        return EDITAVEL_VALIDADO
    if type_name in ("Texture2D", "Sprite", "TextAsset", "MonoBehaviour"):
        return A_VERIFICAR
    if type_name == "AudioClip":
        return SOMENTE_LEITURA
    if type_name in BLOCKED_TYPES:
        return BLOQUEADO
    return SOMENTE_LEITURA


def apk_member_category(member: str) -> str:
    """Categoria de um membro do APK no nível de arquivo (§16.3 final)."""
    if member in BLOCKED_APK_MEMBERS or member.endswith(BLOCKED_APK_SUFFIXES):
        return BLOQUEADO
    if member.startswith(BUNDLE_DIR + "/") and member.endswith(".bundle"):
        return A_VERIFICAR  # o conteúdo do bundle decide objeto a objeto
    return SOMENTE_LEITURA


# ---------------------------------------------------------------------------
# §16.1 — scanner
# ---------------------------------------------------------------------------

@dataclass
class AssetEntry:
    """Um objeto Unity listado — só metadados, nunca conteúdo."""

    member: str                 # membro do APK (o bundle)
    path_id: int
    type: str
    name: str
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    obj_sha256: str | None = None
    category: str = SOMENTE_LEITURA

    def to_dict(self) -> dict[str, Any]:
        return {
            "member": self.member,
            "path_id": self.path_id,
            "type": self.type,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "duration": self.duration,
            "obj_sha256": self.obj_sha256,
            "category": self.category,
        }


@dataclass
class ScanResult:
    """Resultado do scan de um membro bundle do APK."""

    apk: str
    apk_sha256: str
    member: str
    bundle_sha256: str
    object_count: int
    entries: list[AssetEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "apk": self.apk,
            "apk_sha256": self.apk_sha256,
            "member": self.member,
            "bundle_sha256": self.bundle_sha256,
            "object_count": self.object_count,
            "entries": [e.to_dict() for e in self.entries],
        }


def list_bundle_members(apk: zipfile.ZipFile) -> list[dict[str, Any]]:
    """Membros bundle do APK com tamanho — sem abrir nenhum deles."""
    prefix = BUNDLE_DIR + "/"
    return sorted(
        (
            {"member": i.filename, "size": i.file_size}
            for i in apk.infolist()
            if i.filename.startswith(prefix) and i.filename.endswith(".bundle")
        ),
        key=lambda m: -m["size"],
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _measure(data: Any) -> tuple[int | None, int | None, float | None]:
    """(largura, altura, duração) quando o tipo tiver, senão (None, None, None)."""
    width = getattr(data, "m_Width", None)
    height = getattr(data, "m_Height", None)
    duration = getattr(data, "m_Length", None)
    return (
        width if isinstance(width, int) else None,
        height if isinstance(height, int) else None,
        float(duration) if isinstance(duration, (int, float)) else None,
    )


def scan_bundle(
    apk_path: Path | str,
    member: str,
    work_dir: Path | str,
    *,
    hash_objects: bool = True,
    log: LogFn = print,
) -> ScanResult:
    """Escaneia um bundle do APK para o catálogo — leitura, nunca escrita."""
    apk_path = Path(apk_path)
    work_dir = Path(work_dir)
    if apk_member_category(member) == BLOQUEADO:
        raise AssetsError(f"membro bloqueado pelo §16.3: {member}")
    UnityPy = _load_unitypy()

    work_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = work_dir / Path(member).name
    with zipfile.ZipFile(apk_path, "r") as apk:
        if member not in apk.namelist():
            raise AssetsError(f"membro não existe no APK: {member}")
        _extract_member(apk, member, bundle_path)
    apk_sha = _sha256_file(apk_path)
    bundle_sha = _sha256_file(bundle_path)

    log(f"abrindo bundle {Path(member).name} ({bundle_path.stat().st_size:,} bytes)")
    env = UnityPy.load(str(bundle_path))
    entries: list[AssetEntry] = []
    nao_lidos = 0
    for obj in env.objects:
        type_name = getattr(getattr(obj, "type", None), "name", "") or "?"
        if type_name not in SAFE_READ_TYPES:
            # obj.read() de tipo sem parser nativo desce para o typetree —
            # typetree exótico/corrompido derruba o PROCESSO (access
            # violation comprovado no bundle de conteúdo: 285.669 objetos,
            # UnityPy 1.25.3, TypeTreeHelper.read_typetree). Nada de
            # exceção Python: o Studio inteiro morreria. Fora da lista
            # branca, o objeto entra só com metadados de catálogo.
            nao_lidos += 1
            name = "?"
            width = height = duration = None
        else:
            try:
                data = obj.read()
            except Exception:  # noqa: BLE001 - objeto ilegível entra como A_VERIFICAR
                entries.append(AssetEntry(
                    member=member, path_id=obj.path_id, type=type_name, name="?",
                    category=A_VERIFICAR,
                ))
                continue
            name = getattr(data, "m_Name", "") or ""
            width, height, duration = _measure(data)
        obj_sha: str | None = None
        if hash_objects:
            raw = obj.get_raw_data()
            obj_sha = hashlib.sha256(raw).hexdigest()
        entries.append(AssetEntry(
            member=member,
            path_id=obj.path_id,
            type=type_name,
            name=name if name else "?",
            width=width,
            height=height,
            duration=duration,
            obj_sha256=obj_sha,
            category=categorize(type_name, name if name else "?"),
        ))

    result = ScanResult(
        apk=str(apk_path),
        apk_sha256=apk_sha,
        member=member,
        bundle_sha256=bundle_sha,
        object_count=len(entries),
        entries=entries,
    )
    log(
        f"{len(entries)} objeto(s) catalogados em {Path(member).name}"
        + (f" ({nao_lidos} listados sem desserializar — fora de SAFE_READ_TYPES)" if nao_lidos else "")
    )
    return result


def search_entries(
    entries: list[AssetEntry],
    *,
    text: str | None = None,
    type_name: str | None = None,
    member: str | None = None,
) -> list[AssetEntry]:
    """Busca por nome/tipo/bundle (§16.1) — case-insensitive, substring."""
    texto = (text or "").strip().lower()
    tipo = (type_name or "").strip().lower()
    alvo = (member or "").strip()
    saida = []
    for entrada in entries:
        if texto and texto not in entrada.name.lower():
            continue
        if tipo and tipo != entrada.type.lower():
            continue
        if alvo and alvo != entrada.member:
            continue
        saida.append(entrada)
    return saida


def save_report(result: ScanResult, path: Path | str) -> Path:
    """Relatório com metadados sanitizados — nenhum conteúdo de asset."""
    destino = Path(path)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destino


# ---------------------------------------------------------------------------
# §16.2 — seletores estáveis
# ---------------------------------------------------------------------------

SELECTOR_FIELDS = ("apk_sha256", "member", "path_id", "type", "name", "obj_sha256")


def selector_for(apk_sha256: str, entry: AssetEntry) -> dict[str, Any]:
    """Seletor estável: todas as partes têm que bater na hora de escrever."""
    if not entry.obj_sha256:
        raise AssetsError(
            "entrada sem hash de objeto — rode o scan com hash_objects=True "
            "para poder montar seletor estável (§16.2)."
        )
    return {
        "apk_sha256": apk_sha256,
        "member": entry.member,
        "path_id": entry.path_id,
        "type": entry.type,
        "name": entry.name,
        "obj_sha256": entry.obj_sha256,
    }


def selector_str(selector: dict[str, Any]) -> str:
    return "|".join(f"{campo}={selector[campo]}" for campo in SELECTOR_FIELDS)


def parse_selector(texto: str) -> dict[str, Any]:
    partes: dict[str, str] = {}
    for chunk in texto.split("|"):
        campo, sep, valor = chunk.partition("=")
        if not sep:
            raise AssetsError(f"seletor malformado: {chunk!r}")
        partes[campo] = valor
    faltando = [c for c in SELECTOR_FIELDS if c not in partes]
    if faltando:
        raise AssetsError(f"seletor sem os campos {faltando}")
    try:
        partes["path_id"] = int(partes["path_id"])
    except ValueError as exc:
        raise AssetsError("path_id do seletor não é inteiro") from exc
    return partes


def confirm_selector_in_bundle(
    selector: dict[str, Any], bundle_path: Path
) -> tuple[Any, str]:
    """Confere o seletor contra o bundle real; devolve (objeto, hash_atual).

    Qualquer campo divergente levanta `SelectorMismatch` citando o quê —
    aplicar num objeto "parecido" é exatamente o que a §16.2 proíbe.
    """
    UnityPy = _load_unitypy()
    env = UnityPy.load(str(bundle_path))
    objeto = next((o for o in env.objects if o.path_id == selector["path_id"]), None)
    if objeto is None:
        raise SelectorMismatch(
            f"path_id {selector['path_id']} não existe no bundle "
            f"{bundle_path.name} — seletor aponta para outro build"
        )
    type_name = getattr(getattr(objeto, "type", None), "name", "") or "?"
    divergencias = []
    if type_name != selector["type"]:
        divergencias.append(f"tipo: seletor={selector['type']} real={type_name}")
    if type_name in SAFE_READ_TYPES:
        data = objeto.read()
        name = getattr(data, "m_Name", "") or ""
        if name != selector["name"]:
            divergencias.append(f"nome: seletor={selector['name']!r} real={name!r}")
    elif selector["name"] != "?":
        # desserializar tipo fora da lista branca pode derrubar o processo
        # (access violation) — confirmar nome desses não vale o risco.
        divergencias.append(
            f"nome: seletor={selector['name']!r} não confirmável — "
            f"{type_name} está fora de SAFE_READ_TYPES e não é desserializado"
        )
    hash_atual = hashlib.sha256(objeto.get_raw_data()).hexdigest()
    if hash_atual != selector["obj_sha256"]:
        divergencias.append(
            f"hash do objeto: seletor={selector['obj_sha256'][:12]}… real={hash_atual[:12]}…"
        )
    if divergencias:
        raise SelectorMismatch(
            "seletor estável divergiu do objeto real (§16.2 — bloqueado):\n  - "
            + "\n  - ".join(divergencias)
        )
    return objeto, hash_atual


# ---------------------------------------------------------------------------
# §16.4 — transação de bundle
# ---------------------------------------------------------------------------

def apply_replacement(
    apk_path: Path | str,
    selector: dict[str, Any],
    imagem: Any,
    work_dir: Path | str,
    *,
    log: LogFn = print,
    report_path: Path | str | None = None,
) -> dict[str, Any]:
    """Transação completa de substituição de textura EDITÁVEL_VALIDADA.

    Passos (§16.4, na ordem): cópia temporária do bundle no workspace →
    confirmação do seletor → escrita UnityPy → reabertura → verificação do
    objeto alterado e da contagem dos demais → promoção atômica do
    temporário → ``zero_catalog_crc()`` → verificação do catálogo → hashes
    anterior/posterior. Falha em qualquer passo preserva o original.
    """
    apk_path = Path(apk_path)
    work_dir = Path(work_dir)
    member = selector.get("member", "")
    if categorize(selector.get("type", ""), selector.get("name", "")) != EDITAVEL_VALIDADO:
        raise TransactionRefused(
            f"{selector.get('type')}/{selector.get('name')!r} não é "
            f"{EDITAVEL_VALIDADO} (ordem de suporte §16.3) — categoria atual: "
            f"{categorize(selector.get('type', ''), selector.get('name', ''))}. "
            "Liberar exige fixture e reabertura de bundle, um conjunto por vez."
        )

    work_dir.mkdir(parents=True, exist_ok=True)
    # 1. cópia temporária do bundle dentro do workspace
    original = work_dir / (Path(member).stem + ".original.bundle")
    with zipfile.ZipFile(apk_path, "r") as apk:
        if member not in apk.namelist():
            raise AssetsError(f"membro não existe no APK: {member}")
        _extract_member(apk, member, original)
        catalog_path = work_dir / "catalog.json"
        _extract_member(apk, CATALOG_MEMBER, catalog_path)
    hash_bundle_antes = _sha256_file(original)

    # 2. seletor estável contra o bundle temporário
    _objeto, hash_objeto_antes = confirm_selector_in_bundle(selector, original)
    log(f"seletor confirmado: {selector['name']} (path_id {selector['path_id']})")

    # 3. escrita com UnityPy no temporário separado
    resultado = _write_and_verify(original, selector, imagem, work_dir, log)

    # 6. promoção atômica do temporário (o original do workspace é descartável,
    #    o APK de origem nunca foi tocado). gc extra por segurança: qualquer
    #    env remanescente (confirmação do seletor) não pode segurar handle.
    gc.collect()
    promovido = work_dir / (Path(member).stem + ".patched.bundle")
    resultado["patched_path"].replace(promovido)
    hash_depois = _sha256_file(promovido)

    # 7-8. CRC do catálogo zerado e conferido
    crc = zero_catalog_crc(catalog_path, Path(member))
    if not (crc.get("zeroed") or crc.get("already_zero")):
        raise AssetsError(
            f"não foi possível zerar/verificar o m_Crc do bundle no catálogo: {crc.get('error')}"
        )

    relatorio = {
        "member": member,
        "selector": {**selector, "obj_sha256": hash_objeto_antes},
        "hash_bundle_antes": hash_bundle_antes,
        "hash_bundle_depois": hash_depois,
        "hash_objeto_antes": hash_objeto_antes,
        "hash_objeto_depois": resultado["obj_sha_depois"],
        "catalog_crc": crc,
        "object_count_antes": resultado["count_antes"],
        "object_count_depois": resultado["count_depois"],
        "decoded_diff": resultado["decoded_diff"],
        "patched_bundle": str(promovido),
        "original_preservado": True,
        "status": "ok",
    }
    if report_path:
        destino = Path(report_path)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        relatorio["report_path"] = str(destino)
    log(
        f"transação concluída: {selector['name']} "
        f"(diff {resultado['decoded_diff']:.1f}, objetos {resultado['count_antes']}→{resultado['count_depois']})"
    )
    return relatorio


def _write_and_verify(
    original: Path,
    selector: dict[str, Any],
    imagem: Any,
    work_dir: Path,
    log: LogFn,
) -> dict[str, Any]:
    """Passos 3-5: escreve, reabre, verifica objeto alterado e a contagem."""
    UnityPy = _load_unitypy()
    env = UnityPy.load(str(original))
    alvo = next((o for o in env.objects if o.path_id == selector["path_id"]), None)
    if alvo is None:
        raise AssetsError("objeto sumiu do bundle entre a confirmação e a escrita")
    data = alvo.read()
    dims = (data.m_Width, data.m_Height)
    substituta = _cover_fit(imagem, dims) if imagem.size != dims else imagem.copy()
    data.image = substituta
    alvo.patch(data)

    saida = work_dir / (original.stem + ".parcial.bundle")
    saida.write_bytes(env.file.save(packer="original"))
    log(f"bundle re-serializado: {saida.stat().st_size:,} bytes")

    # 4-5. reabre e verifica
    check_env = UnityPy.load(str(saida))
    check_obj = next((o for o in check_env.objects if o.path_id == selector["path_id"]), None)
    if check_obj is None:
        raise AssetsError(f"objeto {selector['name']} sumiu do bundle re-serializado")
    decodificada = check_obj.read().image
    if decodificada.size != dims:
        raise AssetsError(
            f"{selector['name']} mudou de dimensão: {decodificada.size} ≠ {dims}"
        )
    diff = mean_channel_diff(decodificada, substituta)
    if diff > MAX_THUMB_DIFF:
        raise AssetsError(
            f"{selector['name']} decodificada diverge da arte enviada "
            f"(diff {diff:.1f} > {MAX_THUMB_DIFF})"
        )
    count_antes = len(list(env.objects))
    count_depois = len(list(check_env.objects))
    if count_antes != count_depois:
        raise AssetsError(
            f"contagem de objetos mudou: {count_antes} -> {count_depois}"
        )
    obj_sha_depois = hashlib.sha256(check_obj.get_raw_data()).hexdigest()
    log(f"  ok: {selector['name']} decodificada de volta (diff {diff:.1f})")
    # No Windows o UnityPy 1.25.3 retém handle do .parcial reaberto para a
    # verificação — a promoção atômica (os.replace) falharia com WinError 32.
    # Os ambientes vivem em ciclos de referência: só morrem com coleta maior.
    del env, check_env, check_obj, decodificada, substituta, data, alvo
    gc.collect()
    return {
        "patched_path": saida,
        "obj_sha_depois": obj_sha_depois,
        "count_antes": count_antes,
        "count_depois": count_depois,
        "decoded_diff": round(diff, 2),
    }
