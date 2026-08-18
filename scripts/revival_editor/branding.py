"""Branding Android seguro (fase 8 do plano).

Tudo aqui opera sobre a **árvore decoded do apktool** (criada pela etapa decode
do pipeline) e nunca sobre o APK binário. As regras da fase 8 que este módulo
impõe mecanicamente:

- o nome exibido muda **no recurso referenciado por `android:label`** — nunca
  editando o manifest (modo normal não escreve AndroidManifest.xml, ponto);
- ícone legado + adaptive só depois de **mapear todos os recursos
  referenciados** pelo manifest (icon/roundIcon → densidades → foreground/
  background do adaptive). Recurso referenciado e ausente = recusa, não chute;
- densidades são geradas por cover-fit exato por pasta — sem distorção;
- o plano de mudança é um objeto auditável: a UI mostra o diff **antes** de
  aplicar (`render_diff`);
- depois de aplicar, `verify_untouched` prova que package, uses-sdk,
  permissões, componentes e exported flags continuam idênticos;
- a imagem do usuário só é lida de onde ela estiver e vira PNG dentro da
  árvore decoded (gitignored) — nunca copiada para pasta versionada.
"""
from __future__ import annotations

import difflib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "BrandingError",
    "ManifestInfo",
    "StringResource",
    "IconMapping",
    "BrandingPlan",
    "read_manifest",
    "resolve_string_resources",
    "plan_label_change",
    "plan_icon_change",
    "plan_theme_change",
    "render_diff",
    "apply_plan",
    "verify_untouched",
    "advanced_snapshot",
    "LAUNCHER_DENSITIES",
]

ANDROID_NS = "http://schemas.android.com/apk/res/android"
#: Tamanhos oficiais de ícone launcher por densidade.
LAUNCHER_DENSITIES: dict[str, int] = {
    "mdpi": 48,
    "hdpi": 72,
    "xhdpi": 96,
    "xxhdpi": 144,
    "xxxhdpi": 192,
}

#: Campos do manifest que o modo normal jamais deixa mudar (fase 8).
CAMPOS_PROTEGIDOS = (
    "package",
    "minSdkVersion",
    "targetSdkVersion",
    "permissions",
    "components",
    "exported",
)


class BrandingError(Exception):
    """Branding recusado — motivo acionável, pronto para a UI."""


def _attr(nome: str) -> str:
    return f"{{{ANDROID_NS}}}{nome}"


def _get_attr(elemento: ET.Element, nome: str) -> str | None:
    """Atributo android: lendo namespaced (apktool) ou plano (fallback)."""
    return elemento.get(_attr(nome)) or elemento.get(nome)


@dataclass
class ManifestInfo:
    """Fatos do AndroidManifest.xml decodificado — medição, não opinião."""

    package: str
    label_raw: str
    icon_raw: str | None
    round_icon_raw: str | None
    permissions: list[str] = field(default_factory=list)
    activities: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    receivers: list[str] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    exported: list[str] = field(default_factory=list)
    min_sdk: str | None = None
    target_sdk: str | None = None

    @property
    def label_is_resource(self) -> bool:
        return self.label_raw.startswith("@")

    @property
    def label_resource_name(self) -> str | None:
        if not self.label_is_resource:
            return None
        _tipo, _, nome = self.label_raw.lstrip("@").partition("/")
        return nome or None

    @property
    def icon_refs(self) -> list[str]:
        return [ref for ref in (self.icon_raw, self.round_icon_raw) if ref]

    def to_dict(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "label": self.label_raw,
            "icon": self.icon_raw,
            "round_icon": self.round_icon_raw,
            "permissions": list(self.permissions),
            "activities": list(self.activities),
            "services": list(self.services),
            "receivers": list(self.receivers),
            "providers": list(self.providers),
            "exported": list(self.exported),
            "min_sdk": self.min_sdk,
            "target_sdk": self.target_sdk,
        }


def read_manifest(decoded_dir: Path | str) -> ManifestInfo:
    """Lê o AndroidManifest.xml decodificado (XML texto do apktool)."""
    caminho = Path(decoded_dir) / "AndroidManifest.xml"
    if not caminho.is_file():
        raise BrandingError(
            f"AndroidManifest.xml não encontrado em {caminho}.\n"
            "Rode o pipeline (menu APK) até a etapa de decode primeiro."
        )
    try:
        raiz = ET.parse(caminho).getroot()
    except ET.ParseError as exc:
        raise BrandingError(f"AndroidManifest.xml não é XML válido: {exc}") from exc

    app = raiz.find("application")
    if app is None:
        raise BrandingError("manifest sem <application> — árvore decoded inesperada")

    uses_sdk = raiz.find("uses-sdk")
    info = ManifestInfo(
        package=raiz.get("package") or "",
        label_raw=_get_attr(app, "label") or "",
        icon_raw=_get_attr(app, "icon"),
        round_icon_raw=_get_attr(app, "roundIcon"),
        min_sdk=_get_attr(uses_sdk, "minSdkVersion") if uses_sdk is not None else None,
        target_sdk=_get_attr(uses_sdk, "targetSdkVersion") if uses_sdk is not None else None,
    )
    info.permissions = sorted(
        _get_attr(permissao, "name") or ""
        for permissao in raiz.findall("uses-permission")
    )
    for tag, destino in (
        ("activity", info.activities),
        ("activity-alias", info.activities),
        ("service", info.services),
        ("receiver", info.receivers),
        ("provider", info.providers),
    ):
        for elemento in raiz.iter(tag):
            nome = _get_attr(elemento, "name") or ""
            destino.append(nome)
            if _get_attr(elemento, "exported") == "true":
                info.exported.append(nome)
    return info


@dataclass
class StringResource:
    """Uma definição de <string> num arquivo de recursos decodificado."""

    file: Path
    name: str
    value: str

    def to_dict(self) -> dict[str, Any]:
        return {"file": str(self.file), "name": self.name, "value": self.value}


def resolve_string_resources(
    decoded_dir: Path | str, nome: str
) -> list[StringResource]:
    """Todas as definições de `@string/<nome>` nos values* (inclui locales).

    O nome exibido costuma existir em values/ e em values-*/ (traduções):
    mudar só uma deixaria o app inconsistente entre idiomas — a mudança
    planejada cobre todas.
    """
    res = Path(decoded_dir) / "res"
    if not nome or not res.is_dir():
        return []
    achados: list[StringResource] = []
    for arquivo in sorted(res.glob("values*/strings.xml")):
        try:
            raiz = ET.parse(arquivo).getroot()
        except ET.ParseError:
            continue  # arquivo degradado: não é onde o label se resolve
        for elemento in raiz.findall("string"):
            if elemento.get("name") == nome:
                achados.append(StringResource(arquivo, nome, elemento.text or ""))
    return achados


# ---------------------------------------------------------------------------
# plano de mudança
# ---------------------------------------------------------------------------

@dataclass
class EditStep:
    """Uma edição atômica: valor novo para o texto de um elemento de recurso."""

    file: Path
    name: str
    old_value: str
    new_value: str
    tag: str = "string"   # <string> para label, <color> para cor de tema

    @property
    def kind(self) -> str:
        return "label" if self.tag == "string" else self.tag


@dataclass
class IconMapping:
    """Recurso de ícone mapeado em todas as densidades referenciadas."""

    ref: str                       # ex.: @mipmap/ic_launcher
    bitmaps: dict[str, Path] = field(default_factory=dict)   # densidade -> arquivo
    adaptive_xml: Path | None = None
    adaptive_layers: list[str] = field(default_factory=list)  # refs de foreground/background

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "bitmaps": {d: str(p) for d, p in self.bitmaps.items()},
            "adaptive_xml": str(self.adaptive_xml) if self.adaptive_xml else None,
            "adaptive_layers": list(self.adaptive_layers),
        }


@dataclass
class BrandingPlan:
    """Mudança auditável: passos + mapa de ícones + o que NÃO pode mudar."""

    label_edits: list[EditStep] = field(default_factory=list)
    icon_mappings: list[IconMapping] = field(default_factory=list)
    icon_source: Path | None = None
    guarded: tuple[str, ...] = CAMPOS_PROTEGIDOS

    @property
    def vazio(self) -> bool:
        return not self.label_edits and not self.icon_mappings

    def to_dict(self) -> dict[str, Any]:
        return {
            "label_edits": [
                {"file": str(e.file), "name": e.name, "tag": e.tag,
                 "old": e.old_value, "new": e.new_value}
                for e in self.label_edits
            ],
            "icons": [m.to_dict() for m in self.icon_mappings],
            "icon_source": str(self.icon_source) if self.icon_source else None,
            "guarded": list(self.guarded),
        }


#: Cor Android válida: #RGB, #RRGGBB ou #AARRGGBB.
_COR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def plan_theme_change(
    decoded_dir: Path | str, color_name: str, nova_cor: str
) -> BrandingPlan:
    """Plano para trocar uma cor de tema/splash **em recurso existente**.

    Regras da fase 8: (1) só edita `<color name=…>` que já exista — o modo
    normal nunca cria recurso novo nem inventa nome; (2) a cor precisa estar
    referenciada por algum XML de res/ (style/splash/drawable) — cor órfã não
    tem efeito e é recusada; (3) o plano cobre **cada variante de Android**
    (values/, values-v21/, values-night/…) onde a cor existe — trocar só a
    base deixaria versões novas com a cor velha.
    """
    cor = nova_cor.strip()
    if not _COR_RE.match(cor):
        raise BrandingError(
            f"cor inválida: {nova_cor!r} — use #RGB, #RRGGBB ou #AARRGGBB (ex.: #7B1FA2)."
        )
    nome = color_name.strip()
    if not nome or "/" in nome:
        raise BrandingError("nome do recurso de cor vazio ou malformado.")
    decoded = Path(decoded_dir)
    res = decoded / "res"
    if not res.is_dir():
        raise BrandingError(f"pasta res/ não encontrada em {decoded} — rode o decode primeiro.")

    definicoes: list[StringResource] = []
    for arquivo in sorted(res.glob("values*/colors.xml")):
        try:
            raiz_xml = ET.parse(arquivo).getroot()
        except ET.ParseError:
            continue
        for elemento in raiz_xml.findall("color"):
            if elemento.get("name") == nome:
                definicoes.append(StringResource(arquivo, nome, elemento.text or ""))
    if not definicoes:
        raise BrandingError(
            f"@color/{nome} não existe em nenhum res/values*/colors.xml — "
            "o modo normal não cria recursos (fase 8). Use o modo avançado "
            "somente-leitura para inspecionar os nomes reais."
        )

    referencia = f"@color/{nome}"
    usado = False
    for arquivo in res.rglob("*.xml"):
        if arquivo.name == "colors.xml":
            continue
        try:
            if referencia in arquivo.read_text(encoding="utf-8", errors="replace"):
                usado = True
                break
        except OSError:
            continue
    if not usado:
        raise BrandingError(
            f"{referencia} não é referenciada por nenhum style/splash/drawable — "
            "trocar essa cor não teria efeito nenhum no app. Recusando."
        )

    plano = BrandingPlan()
    for definicao in definicoes:
        if definicao.value.strip() == cor:
            continue
        plano.label_edits.append(
            EditStep(
                file=definicao.file, name=nome,
                old_value=definicao.value, new_value=cor, tag="color",
            )
        )
    if not plano.label_edits:
        raise BrandingError("a cor já é essa em todas as variantes — nada a fazer.")
    return plano


def plan_label_change(decoded_dir: Path | str, novo_valor: str) -> BrandingPlan:
    """Plano para trocar o nome exibido no recurso que `android:label` aponta.

    Recusas explícitas (não chutes): label literal no manifest (exigiria editar
    o manifest — bloqueado no modo normal), recurso inexistente, valor vazio
    ou fora de sanidade.
    """
    info = read_manifest(decoded_dir)
    valor = novo_valor.strip()
    if not valor:
        raise BrandingError("novo nome exibido vazio.")
    if len(valor) > 50:
        raise BrandingError(f"nome exibido com {len(valor)} caracteres (máximo 50) — launcher trunca.")
    if not info.label_is_resource:
        raise BrandingError(
            f"android:label é literal ({info.label_raw!r}), não um @string/…: "
            "mudar o nome exigiria editar o AndroidManifest.xml, o que o modo "
            "normal não faz (fase 8)."
        )
    nome = info.label_resource_name or ""
    definicoes = resolve_string_resources(decoded_dir, nome)
    if not definicoes:
        raise BrandingError(
            f"o manifest referencia @{info.label_raw.lstrip('@')} mas nenhum "
            "res/values*/strings.xml define esse nome — árvore inesperada, recusando."
        )
    plano = BrandingPlan()
    for definicao in definicoes:
        if definicao.value == valor:
            continue
        plano.label_edits.append(
            EditStep(file=definicao.file, name=nome, old_value=definicao.value, new_value=valor)
        )
    if not plano.label_edits:
        raise BrandingError("o nome exibido já é esse em todos os locales — nada a fazer.")
    return plano


def _mapear_icon_ref(decoded_dir: Path, ref: str) -> IconMapping:
    """Mapeia uma referência (@mipmap/x) para arquivos reais na árvore.

    Regra da fase 8: ícone só troca com **todos** os recursos referenciados
    mapeados — adaptive incluído (foreground/background). Falta um = recusa.
    """
    if not ref.startswith("@"):
        raise BrandingError(f"referência de ícone não é recurso: {ref!r}")
    _tipo, _, nome = ref.lstrip("@").partition("/")
    if not nome:
        raise BrandingError(f"referência de ícone sem nome: {ref!r}")
    res = decoded_dir / "res"

    mapa = IconMapping(ref=ref)
    pastas = sorted(p for p in res.glob(f"{_tipo}-*") if p.is_dir())
    densidades = {
        p.name.split("-", 1)[1]: p for p in pastas
        if p.name.split("-", 1)[1] in LAUNCHER_DENSITIES
    }
    for densidade, pasta in densidades.items():
        arquivo = pasta / f"{nome}.png"
        if arquivo.is_file():
            mapa.bitmaps[densidade] = arquivo
    adaptive = res / f"{_tipo}-anydpi-v26" / f"{nome}.xml"
    if adaptive.is_file():
        mapa.adaptive_xml = adaptive
        try:
            raiz = ET.parse(adaptive).getroot()
        except ET.ParseError as exc:
            raise BrandingError(f"adaptive icon ilegível ({adaptive}): {exc}") from exc
        for camada in raiz.iter():
            drawable = camada.get(_attr("drawable"))
            if drawable:
                mapa.adaptive_layers.append(drawable)

    if not mapa.bitmaps and mapa.adaptive_xml is None:
        raise BrandingError(
            f"nenhum arquivo para {ref} em res/{_tipo}-* — recurso referenciado "
            "e ausente; recusando em vez de criar do nada."
        )
    return mapa


def plan_icon_change(decoded_dir: Path | str, imagem_fonte: Path | str) -> BrandingPlan:
    """Plano para regenerar o ícone (legado + adaptive) em todas as densidades."""
    fonte = Path(imagem_fonte)
    if not fonte.is_file():
        raise BrandingError(f"imagem de origem não encontrada: {fonte}")
    info = read_manifest(decoded_dir)
    if not info.icon_refs:
        raise BrandingError("manifest não referencia android:icon — nada a mapear.")
    plano = BrandingPlan(icon_source=fonte)
    for ref in info.icon_refs:
        plano.icon_mappings.append(_mapear_icon_ref(Path(decoded_dir), ref))
    return plano


# ---------------------------------------------------------------------------
# diff, aplicação e verificação
# ---------------------------------------------------------------------------

def _trocar_valor_string(arquivo: Path, tag: str, nome: str, novo: str) -> bool:
    """Reescreve o texto do elemento <tag name=nome> preservando o resto do arquivo."""
    texto = arquivo.read_text(encoding="utf-8")
    padrao = re.compile(
        r'(<' + re.escape(tag) + r'[^>]*name="' + re.escape(nome) + r'"[^>]*>)(.*?)(</' + re.escape(tag) + r'>)',
        re.DOTALL,
    )
    novo_texto, total = padrao.subn(lambda m: m.group(1) + novo + m.group(3), texto, count=1)
    if total != 1:
        return False
    arquivo.write_text(novo_texto, encoding="utf-8")
    return True


def render_diff(plano: BrandingPlan) -> str:
    """Diff unificado do que `apply_plan` faria — mostrado ANTES de aplicar."""
    if plano.vazio:
        return "(plano vazio)"
    pedacos: list[str] = []
    for edicao in plano.label_edits:
        antes = f"<{edicao.tag} name=\"{edicao.name}\">{edicao.old_value}</{edicao.tag}>"
        depois = f"<{edicao.tag} name=\"{edicao.name}\">{edicao.new_value}</{edicao.tag}>"
        diff = difflib.unified_diff(
            [antes + "\n"], [depois + "\n"],
            fromfile=f"a/{edicao.file.name}", tofile=f"b/{edicao.file.name}", lineterm="\n",
        )
        pedacos.append("".join(diff).rstrip("\n"))
    for mapa in plano.icon_mappings:
        linhas = [f"ic: {mapa.ref}"]
        for densidade, arquivo in sorted(mapa.bitmaps.items()):
            alvo = LAUNCHER_DENSITIES[densidade]
            linhas.append(f"ic:   {densidade}: {arquivo.name} -> PNG {alvo}x{alvo} (cover-fit)")
        if mapa.adaptive_xml is not None:
            linhas.append(f"ic:   adaptive: {mapa.adaptive_xml.name} mantido (camadas preservadas)")
        pedacos.append("\n".join(linhas))
    return "\n\n".join(pedacos)


def apply_plan(plano: BrandingPlan) -> dict[str, Any]:
    """Aplica o plano: troca labels nos recursos e regenera ícones por densidade.

    Nunca escreve em AndroidManifest.xml. A imagem do usuário só é lida; os
    PNGs gerados ficam na árvore decoded (gitignored).
    """
    if plano.vazio:
        raise BrandingError("plano vazio — nada a aplicar.")
    aplicados: list[str] = []
    for edicao in plano.label_edits:
        if edicao.file.name == "AndroidManifest.xml":
            raise BrandingError("plano tentaria editar o manifest — bloqueado.")
        if not _trocar_valor_string(edicao.file, edicao.tag, edicao.name, edicao.new_value):
            raise BrandingError(
                f"não achei <{edicao.tag} name=\"{edicao.name}\"> em {edicao.file} na hora de aplicar."
            )
        aplicados.append(str(edicao.file))

    icones_gerados: list[str] = []
    if plano.icon_mappings:
        from PIL import Image  # noqa: PLC0415 - Pillow é opcional na toolchain

        with Image.open(plano.icon_source) as bruta:
            bruta.load()
            fonte = bruta.convert("RGBA")
        for mapa in plano.icon_mappings:
            for densidade, arquivo in mapa.bitmaps.items():
                alvo = LAUNCHER_DENSITIES[densidade]
                redimensionada = _cover_fit_exato(fonte, alvo)
                temporario = arquivo.with_suffix(".png.parcial")
                redimensionada.save(temporario, "PNG", optimize=True)
                temporario.replace(arquivo)
                icones_gerados.append(f"{mapa.ref}@{densidade}={alvo}x{alvo}")

    return {
        "labels_alterados": aplicados,
        "icones_gerados": icones_gerados,
        "manifest_tocado": False,
    }


def _cover_fit_exato(imagem: Any, lado: int) -> Any:
    """Cover-fit quadrado sem distorção (a fonte nunca é esticada)."""
    from PIL import Image, ImageOps  # noqa: PLC0415

    # Pillow ≥9.1: Image.Resampling.LANCZOS; mais antigo: constante no módulo.
    resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
    return ImageOps.fit(imagem, (lado, lado), method=resampling)


def verify_untouched(manifest_antes: ManifestInfo, decoded_dir: Path | str) -> bool:
    """Prova que o manifest continua com a mesma forma protegida.

    Retorna True quando nada protegido mudou; False caso contrário (a UI
    bloqueia a continuação e mostra o campo divergente).
    """
    depois = read_manifest(decoded_dir)
    campos = {
        "package": (manifest_antes.package, depois.package),
        "minSdkVersion": (manifest_antes.min_sdk, depois.min_sdk),
        "targetSdkVersion": (manifest_antes.target_sdk, depois.target_sdk),
        "permissions": (manifest_antes.permissions, depois.permissions),
        "components": (
            (manifest_antes.activities, manifest_antes.services,
             manifest_antes.receivers, manifest_antes.providers),
            (depois.activities, depois.services, depois.receivers, depois.providers),
        ),
        "exported": (manifest_antes.exported, depois.exported),
    }
    return all(anterior == posterior for anterior, posterior in campos.values())


#: Teto de arquivos listados no snapshot avançado — o APK real tem milhares
#: de recursos; a UI mostra a contagem completa e a lista cabe no widget.
SNAPSHOT_MAX_FILES = 500


def advanced_snapshot(decoded_dir: Path | str) -> dict[str, Any]:
    """Modo avançado **somente-leitura**: o que existe, sem botão de editar.

    A fase 8 quer inspeção sem risco: o snapshot devolve o texto do manifest e
    o inventário de recursos (contagem completa, lista limitada por página).
    Nenhum caminho aqui é gravável pela UI avançada — as mudanças passam pelos
    planos (`plan_*`), que são auditados, ou não acontecem.
    """
    decoded = Path(decoded_dir)
    info = read_manifest(decoded)
    manifest_texto = (decoded / "AndroidManifest.xml").read_text(encoding="utf-8")

    res = decoded / "res"
    recursos: list[dict[str, Any]] = []
    total = 0
    if res.is_dir():
        for arquivo in sorted(res.rglob("*")):
            if not arquivo.is_file():
                continue
            total += 1
            if len(recursos) < SNAPSHOT_MAX_FILES:
                recursos.append({
                    "path": str(arquivo.relative_to(decoded)).replace("\\", "/"),
                    "size": arquivo.stat().st_size,
                })
    return {
        "manifest": manifest_texto,
        "manifest_info": info.to_dict(),
        "resource_total": total,
        "resources": recursos,
        "truncated": total > len(recursos),
        "writable": False,
    }
