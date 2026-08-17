#!/usr/bin/env python3
"""Injeta uma tela de loading personalizada no APK do Mighty DOOM.

Troca apenas as texturas de fundo da tela de loading dentro do bundle
Addressables local (``defaultlocalgroup_assets_all_*.bundle``):
``loading_background`` (genérica) e as sazonais ``*_LoadingBackground_*``.
Os Sprites que as exibem referenciam a Texture2D por path_id, então a troca
dos pixels da textura atualiza a tela sem mexer em mais nada.

Composição em três modos:
* ``image``: só a arte fornecida (cover-fit para o tamanho da textura);
* ``image+text``: arte + blocos de texto por cima;
* ``text``: fundo em cor sólida com tratamento abstrato + texto.

O APK nunca passa por apktool: todos os outros membros do ZIP são copiados
byte a byte (CRC32 conferido um a um), o bundle reserializado é recarregado
e decodificado com UnityPy antes de ser aceito, o m_Crc do bundle é zerado
no catalog.json (a Unity só valida CRC quando o valor é não-zero) e o APK
final é alinhado e assinado com uber-apk-signer. O arquivo de saída só
substitui o destino depois de passar por todos os gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_MEMBER_DIR = "assets/aa/Android"
BUNDLE_MEMBER_GLOB = "defaultlocalgroup_assets_all_*.bundle"
CATALOG_MEMBER = "assets/aa/catalog.json"
TARGET_EXACT_NAME = "loading_background"
TARGET_NAME_CONTAINS = "LoadingBackground"
TEXTURE_SIZE = (2048, 2048)
UNITYPY_VERSION = "1.25.3"

# Diff médio por canal aceito entre a arte enviada e a textura ASTC 5x5
# decodificada de volta (ASTC é com perdas; planos ficam ~8, bordas ficam
# acima — 64x64 downsample mantém a média bem abaixo disso).
MAX_THUMB_DIFF = 45.0

LogFn = Callable[[str], None]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_unity_bundle import zero_catalog_crc  # noqa: E402


class UnityPyUnavailable(RuntimeError):
    pass


def _load_unitypy():
    try:
        import UnityPy  # type: ignore
    except ImportError as exc:
        raise UnityPyUnavailable(
            f"UnityPy {UNITYPY_VERSION} não está instalado. Execute scripts\\setup-patcher-tools.bat."
        ) from exc
    version = getattr(UnityPy, "__version__", None)
    if version and version != UNITYPY_VERSION:
        raise UnityPyUnavailable(
            f"Versão UnityPy incompatível: {version}; esperado {UNITYPY_VERSION}."
        )
    return UnityPy


# ---------------------------------------------------------------------------
# Composição da imagem
# ---------------------------------------------------------------------------

def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _cover_fit(source: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(source, size, Image.Resampling.LANCZOS)


def draw_abstract_background(size: tuple[int, int], base_color: str) -> Image.Image:
    """Fundo abstrato do modo 'só texto': gradiente escuro + raios + brilho."""
    width, height = size
    try:
        image = Image.new("RGB", size, base_color)
    except ValueError:
        image = Image.new("RGB", size, "#160b12")
    draw = ImageDraw.Draw(image, "RGBA")
    for y in range(height):
        alpha = int(120 * y / height)
        draw.line((0, y, width, y), fill=(3, 2, 8, alpha))
    for x in range(-height, width, max(1, height // 16)):
        draw.line((width // 2, height // 2, x, height), fill=(255, 74, 21, 28), width=max(1, height // 384))
    cx, cy = width // 2, height // 2
    draw.ellipse((cx - width * 7 // 20, cy - height * 11 // 50, cx + width * 7 // 20, cy + height * 31 // 100),
                 fill=(255, 93, 24, 30))
    return image


def _draw_text_block(image: Image.Image, title: str, subtitle: str, status: str) -> None:
    """Pinta título/subtítulo/mensagem nas mesmas posições relativas da tela
    oficial (o jogo desenha a barra de progresso real por cima, então nenhuma
    barra falsa é incluída na arte)."""
    width, height = image.size
    draw = ImageDraw.Draw(image, "RGBA")
    title = title.upper()[:24]
    subtitle = subtitle.upper()[:40]
    status = status[:70]
    if title:
        draw.text((width // 2, int(height * 0.29)), title,
                  font=font(int(height * 0.078), True), anchor="mm",
                  fill="#ffd34e", stroke_width=max(2, height // 640), stroke_fill="#a92818")
    if subtitle:
        draw.text((width // 2, int(height * 0.372)), subtitle,
                  font=font(int(height * 0.0198), True), anchor="mm", fill="#ff7540")
    if status:
        draw.text((width // 2, int(height * 0.854)), status,
                  font=font(int(height * 0.0156)), anchor="mm", fill="#f6e8d1")


def compose_loading_image(
    mode: str = "auto",
    background: Image.Image | None = None,
    title: str = "",
    subtitle: str = "",
    status: str = "",
    bg_color: str = "#160b12",
    size: tuple[int, int] = TEXTURE_SIZE,
) -> Image.Image:
    """Compõe a arte final da tela de loading nos modos image/text/image+text.

    ``auto`` resolve para ``image+text`` quando existe imagem e algum texto,
    ``image`` quando só existe imagem e ``text`` quando não há imagem.
    """
    has_text = bool(title.strip() or subtitle.strip() or status.strip())
    if mode == "auto":
        mode = "image" if background is not None and not has_text else (
            "image+text" if background is not None else "text"
        )
    if mode not in {"image", "text", "image+text"}:
        raise ValueError(f"modo de composição desconhecido: {mode}")
    if mode in {"image", "image+text"} and background is None:
        raise ValueError("este modo exige uma imagem de fundo")

    if mode == "text":
        image = draw_abstract_background(size, bg_color)
    else:
        assert background is not None
        source = background
        if getattr(source, "n_frames", 1) > 1:
            source = source.convert("RGBA")
        source = ImageOps.exif_transpose(source).convert("RGB")
        image = _cover_fit(source, size)

    if mode in {"text", "image+text"}:
        _draw_text_block(image, title, subtitle, status)
    return image


# ---------------------------------------------------------------------------
# Localização do bundle e das texturas
# ---------------------------------------------------------------------------

def find_bundle_member(apk: zipfile.ZipFile) -> str:
    """Retorna o membro do bundle de conteúdo local dentro do APK."""
    prefix = BUNDLE_MEMBER_DIR + "/"
    candidates = [
        name for name in apk.namelist()
        if name.startswith(prefix) and Path(name).match(BUNDLE_MEMBER_GLOB)
    ]
    if not candidates:
        raise RuntimeError(
            f"nenhum bundle {BUNDLE_MEMBER_GLOB} encontrado em {BUNDLE_MEMBER_DIR}"
        )
    # Em tese existe um só; se houver mais de um, o de conteúdo é o maior.
    return max(candidates, key=lambda name: apk.getinfo(name).file_size)


def _is_loading_texture(name: str) -> bool:
    return name == TARGET_EXACT_NAME or TARGET_NAME_CONTAINS in name


def find_loading_textures(env: Any) -> list[Any]:
    return [
        obj for obj in env.objects
        if getattr(getattr(obj, "type", None), "name", "") == "Texture2D"
        and _is_loading_texture(getattr(obj.read(), "m_Name", ""))
    ]


# ---------------------------------------------------------------------------
# Patch e reverificação do bundle
# ---------------------------------------------------------------------------

def mean_channel_diff(a: Image.Image, b: Image.Image, thumb: int = 64) -> float:
    """Diferença média por canal entre duas imagens (downsampled)."""
    pa = a.convert("RGB").resize((thumb, thumb), Image.Resampling.BILINEAR).tobytes()
    pb = b.convert("RGB").resize((thumb, thumb), Image.Resampling.BILINEAR).tobytes()
    total = sum(abs(x - y) for x, y in zip(pa, pb))
    return total / max(1, len(pa))


def _extract_member(apk: zipfile.ZipFile, member: str, target: Path) -> None:
    with apk.open(member, "r") as src, target.open("wb") as dst:
        shutil.copyfileobj(src, dst, 8 * 1024 * 1024)


def patch_bundle(
    bundle_path: Path,
    image: Image.Image,
    work_dir: Path,
    log: LogFn = print,
) -> dict[str, Any]:
    """Substitui as texturas de loading, reserializa e reverifica o bundle.

    Levanta ``RuntimeError`` se qualquer gate falhar; nesse caso o arquivo
    original nunca é tocado (o resultado fica em ``work_dir`` e só é aceito
    depois de recarregado e decodificado com sucesso).
    """
    UnityPy = _load_unitypy()
    work_dir.mkdir(parents=True, exist_ok=True)
    patched_path = work_dir / "loading-patched.bundle"

    log(f"Carregando bundle: {bundle_path.name}")
    env = UnityPy.load(str(bundle_path))
    targets = find_loading_textures(env)
    if not targets:
        raise RuntimeError(
            "nenhuma textura de loading encontrada no bundle "
            f"(esperado '{TARGET_EXACT_NAME}' ou '*{TARGET_NAME_CONTAINS}*')"
        )

    resized: dict[int, Image.Image] = {}
    entries: list[dict[str, Any]] = []
    for obj in targets:
        data = obj.read()
        dims = (data.m_Width, data.m_Height)
        if dims not in resized:
            resized[dims] = _cover_fit(image, dims) if image.size != dims else image.copy()
        data.image = resized[dims]
        obj.patch(data)
        entries.append({"name": data.m_Name, "path_id": obj.path_id, "width": dims[0], "height": dims[1]})
    for entry in entries:
        log(f"  textura substituída: {entry['name']} ({entry['width']}x{entry['height']})")

    log("Re-serializando bundle (pode demorar um pouco)...")
    started = time.time()
    patched_path.write_bytes(env.file.save(packer="original"))
    log(f"Bundle salvo: {patched_path.stat().st_size:,} bytes ({time.time() - started:.0f}s)")

    # Gate 1: o bundle reserializado precisa recarregar, decodificar de volta
    # para a arte enviada e manter a mesma população de objetos.
    log("Reverificando bundle re-serializado...")
    check_env = UnityPy.load(str(patched_path))
    check_targets = {obj.path_id: obj for obj in find_loading_textures(check_env)}
    for entry in entries:
        obj = check_targets.get(entry["path_id"])
        if obj is None:
            raise RuntimeError(f"textura {entry['name']} sumiu do bundle re-serializado")
        decoded = obj.read().image
        if decoded.size != (entry["width"], entry["height"]):
            raise RuntimeError(f"textura {entry['name']} mudou de dimensão após re-serializar")
        diff = mean_channel_diff(decoded, resized[(entry["width"], entry["height"])])
        if diff > MAX_THUMB_DIFF:
            raise RuntimeError(
                f"textura {entry['name']} decodificada diverge da arte enviada (diff {diff:.1f} > {MAX_THUMB_DIFF})"
            )
        entry["decoded_diff"] = round(diff, 2)
        log(f"  ok: {entry['name']} decodificada de volta (diff {diff:.1f})")

    count_before = len(list(env.objects))
    count_after = len(list(check_env.objects))
    if count_before != count_after:
        raise RuntimeError(
            f"contagem de objetos mudou após re-serializar: {count_before} -> {count_after}"
        )

    return {
        "patched_bundle": patched_path,
        "targets": entries,
        "object_count": count_after,
        "bundle_size": patched_path.stat().st_size,
        "verified": True,
    }


# ---------------------------------------------------------------------------
# Reconstrução cirúrgica do ZIP
# ---------------------------------------------------------------------------

def _copy_zip_info(info: zipfile.ZipInfo) -> ZipInfo:
    clone = zipfile.ZipInfo(info.filename, date_time=info.date_time)
    clone.compress_type = info.compress_type
    clone.external_attr = info.external_attr
    clone.internal_attr = info.internal_attr
    clone.create_system = info.create_system
    return clone


def rebuild_apk(
    apk_in: Path,
    apk_out: Path,
    replacements: dict[str, Path],
    log: LogFn = print,
) -> dict[str, Any]:
    """Recria o ZIP do APK trocando apenas os membros em ``replacements``.

    Todos os outros membros são copiados com o mesmo tipo de compressão e
    conferidos por CRC32 contra o APK de origem depois da escrita.
    """
    log(f"Reconstruindo APK: {apk_in.name} -> {apk_out.name}")
    started = time.time()
    with zipfile.ZipFile(apk_in, "r") as zin, zipfile.ZipFile(apk_out, "w", allowZip64=True) as zout:
        for info in zin.infolist():
            clone = _copy_zip_info(info)
            if info.filename in replacements:
                with replacements[info.filename].open("rb") as src, zout.open(clone, "w") as dst:
                    shutil.copyfileobj(src, dst, 8 * 1024 * 1024)
            else:
                with zin.open(info, "r") as src, zout.open(clone, "w") as dst:
                    shutil.copyfileobj(src, dst, 8 * 1024 * 1024)
    log(f"APK reconstruído em {time.time() - started:.0f}s")

    # Gate 2: cada membro não-trocado precisa ter exatamente o mesmo CRC32.
    with zipfile.ZipFile(apk_in, "r") as zin, zipfile.ZipFile(apk_out, "r") as zout:
        before = {i.filename: (i.CRC, i.file_size) for i in zin.infolist()}
        after = {i.filename: (i.CRC, i.file_size) for i in zout.infolist()}
        if set(before) != set(after):
            raise RuntimeError("a lista de membros do APK mudou durante a reconstrução")
        changed: list[str] = []
        for name, (crc, size) in before.items():
            if after[name] == (crc, size):
                continue
            if name in replacements:
                changed.append(name)
                continue
            raise RuntimeError(f"membro não-trocado foi alterado: {name}")
        for name in replacements:
            if name not in changed:
                raise RuntimeError(f"membro a substituir não mudou: {name}")
    return {
        "replaced_members": sorted(replacements),
        "members": len(before),
        "verified": True,
    }


# ---------------------------------------------------------------------------
# Assinatura
# ---------------------------------------------------------------------------

def find_java() -> str:
    found = shutil.which("java")
    if found:
        return found
    for exe in (ROOT / ".tools" / "jre17").glob("*/bin/java.exe"):
        return str(exe)
    for exe in (ROOT / ".tools" / "jre17").glob("*/bin/java"):
        if exe.exists():
            return str(exe)
    raise RuntimeError(
        "java não encontrado no PATH nem em .tools/jre17 (execute scripts\\setup-patcher-tools.bat)"
    )


def run_signer(apk: Path, only_verify: bool = False, log: LogFn = print) -> None:
    java = find_java()
    signer = ROOT / ".tools" / "uber-apk-signer.jar"
    if not signer.is_file():
        raise RuntimeError(
            f"assinador não encontrado: {signer} (execute scripts\\setup-patcher-tools.bat)"
        )
    cmd = [java, "-jar", str(signer), "-a", str(apk)]
    if only_verify:
        cmd.append("--onlyVerify")
    else:
        cmd.append("--overwrite")
    result = subprocess.run(cmd, capture_output=True, text=True)
    for line in (result.stdout or "").splitlines():
        log(f"  [signer] {line}")
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "")[-800:]
        raise RuntimeError(f"uber-apk-signer falhou (rc={result.returncode}):\n{tail}")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------

def default_apk_in() -> Path:
    patched = ROOT / "output" / "mighty-doom-revival.apk"
    if patched.is_file():
        return patched
    return ROOT / "input" / "mighty-doom.apk"


def inject_loading_screen(
    apk_in: Path,
    image: Image.Image,
    apk_out: Path | None = None,
    log: LogFn = print,
    report_path: Path | None = None,
) -> dict[str, Any]:
    """Fluxo completo: patch do bundle -> CRC do catálogo -> ZIP -> assinatura.

    Só substitui ``apk_out`` (in-place por padrão, com backup) depois que
    todos os gates passam. Retorna o relatório final.
    """
    apk_in = Path(apk_in).expanduser().resolve()
    if not apk_in.is_file():
        raise RuntimeError(f"APK de entrada não encontrado: {apk_in}")
    apk_out = Path(apk_out).expanduser().resolve() if apk_out else apk_in
    apk_out.parent.mkdir(parents=True, exist_ok=True)

    work_dir = ROOT / "work" / "loading-edit"
    work_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_path or (work_dir / "inject-report.json")

    started = time.time()
    with zipfile.ZipFile(apk_in, "r") as apk:
        bundle_member = find_bundle_member(apk)
        bundle_path = work_dir / "loading-current.bundle"
        log(f"Extraindo {bundle_member} ({apk.getinfo(bundle_member).file_size:,} bytes)")
        _extract_member(apk, bundle_member, bundle_path)
        catalog_path = work_dir / "catalog.json"
        _extract_member(apk, CATALOG_MEMBER, catalog_path)

    # Gate 0: UnityPy disponível antes de qualquer trabalho pesado.
    _load_unitypy()

    bundle_report = patch_bundle(bundle_path, image, work_dir, log=log)

    # Gate 3: o CRC do bundle no catálogo precisa ser zerado, senão a Unity
    # recusa carregar o bundle em runtime ("CRC Mismatch ... Will not load").
    crc_report = zero_catalog_crc(catalog_path, Path(bundle_member))
    log(f"catalog.json m_Crc: {crc_report}")
    if not (crc_report.get("zeroed") or crc_report.get("already_zero")):
        raise RuntimeError(f"não foi possível zerar o m_Crc do bundle no catálogo: {crc_report.get('error')}")

    unsigned = work_dir / "revival-loading-unsigned.apk"
    rebuild_report = rebuild_apk(
        apk_in, unsigned,
        {bundle_member: bundle_report["patched_bundle"], CATALOG_MEMBER: catalog_path},
        log=log,
    )

    # Gate 4: alinhar, assinar e conferir a assinatura.
    log("Alinhando e assinando APK (uber-apk-signer)...")
    run_signer(unsigned, log=log)
    log("Verificando assinatura...")
    run_signer(unsigned, only_verify=True, log=log)

    # Gate 5: o bundle dentro do APK assinado é byte a byte o verificado.
    bundle_sha = file_sha256(bundle_report["patched_bundle"])
    catalog_sha = file_sha256(catalog_path)
    with zipfile.ZipFile(unsigned, "r") as signed:
        with signed.open(bundle_member) as fh:
            got = hashlib.sha256()
            for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
                got.update(chunk)
            if got.hexdigest() != bundle_sha:
                raise RuntimeError("o bundle dentro do APK assinado difere do bundle verificado")
        if hashlib.sha256(signed.read(CATALOG_MEMBER)).hexdigest() != catalog_sha:
            raise RuntimeError("o catalog.json dentro do APK assinado difere do catálogo verificado")

    # Backup do destino atual e troca atômica.
    backup = None
    if apk_out.exists():
        backup_dir = work_dir / "backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / apk_out.name
        if backup.exists() and backup.stat().st_size != apk_out.stat().st_size:
            backup = backup_dir / f"{apk_out.name}.{time.strftime('%Y%m%d-%H%M%S')}"
        if not backup.exists():
            shutil.copy2(apk_out, backup)
            log(f"Backup do APK anterior: {backup}")
    shutil.copyfile(unsigned, apk_out)

    report = {
        "apk_in": str(apk_in),
        "apk_out": str(apk_out),
        "backup": str(backup) if backup else None,
        "bundle_member": bundle_member,
        "bundle_report": {**bundle_report, "patched_bundle": str(bundle_report["patched_bundle"])},
        "catalog_crc": crc_report,
        "rebuild_report": rebuild_report,
        "signature_verified": True,
        "bundle_sha256": bundle_sha,
        "elapsed_seconds": round(time.time() - started, 1),
        "status": "ok",
    }
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    print(payload)
    report_path.write_text(payload + "\n", encoding="utf-8")
    log(f"Concluído em {report['elapsed_seconds']}s: {apk_out}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Injeta uma tela de loading personalizada no APK (imagem, imagem+texto ou só texto)."
    )
    parser.add_argument("--image", help="Imagem de fundo (PNG/JPG/WebP)")
    parser.add_argument("--mode", choices=["auto", "image", "text", "image+text"], default="auto")
    parser.add_argument("--title", default="", help="Título opcional")
    parser.add_argument("--subtitle", default="", help="Subtítulo opcional")
    parser.add_argument("--status", default="", help="Mensagem opcional exibida no rodapé")
    parser.add_argument("--bg-color", default="#160b12", help="Cor de fundo no modo só texto")
    parser.add_argument("--apk-in", help="APK de entrada (padrão: output/mighty-doom-revival.apk se existir, senão input/mighty-doom.apk)")
    parser.add_argument("--apk-out", help="APK de saída (padrão: mesmo caminho da entrada)")
    parser.add_argument("--report", help="Caminho do relatório JSON")
    parser.add_argument("--export-png", help="Salva a arte composta em PNG e sai (sem injetar)")
    args = parser.parse_args()

    # Saída UTF-8 mesmo em consoles Windows com codepage regional.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):  # pragma: no cover - streams exóticos
            pass

    background: Image.Image | None = None
    if args.image:
        background = Image.open(args.image)
    try:
        image = compose_loading_image(
            mode=args.mode,
            background=background,
            title=args.title,
            subtitle=args.subtitle,
            status=args.status,
            bg_color=args.bg_color,
        )
    except ValueError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    if args.export_png:
        path = Path(args.export_png)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, "PNG", optimize=True)
        print(f"Arte exportada: {path} ({image.size[0]}x{image.size[1]})")
        return 0

    apk_in = Path(args.apk_in).expanduser() if args.apk_in else default_apk_in()
    apk_out = Path(args.apk_out).expanduser() if args.apk_out else None
    try:
        inject_loading_screen(apk_in, image, apk_out, report_path=Path(args.report) if args.report else None)
    except (RuntimeError, UnityPyUnavailable) as exc:
        print(f"\n[PARADO] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
