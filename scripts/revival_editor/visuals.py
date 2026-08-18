"""Visuais do Revival Studio (fase 7 do plano): tela de loading.

Fonte única, sem duplicação: a composição vive em
`scripts/inject_loading_screen.py` (onde é testada por
`tests/test_inject_loading_screen.py`) e é **importada** daqui. O plano é
explícito — *"mover a composição reutilizável para o pacote de domínio sem
duplicar `compose_loading_image()`"* — então este módulo agrega o que a UI
precisa em volta dela:

- validação honesta da arte de entrada (PNG/JPG/WebP, dimensões, memória,
  perfil de cor) com avisos, não só recusas;
- recortes de pré-visualização nas proporções comuns de tela + safe area;
- exportação de PNG sem injetar;
- injeção encadeada para o fluxo já validado (`inject_loading_screen`),
  que troca **somente** as texturas de loading, reabre o bundle com UnityPy,
  zera o CRC do catálogo e assina o APK de novo.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from inject_loading_screen import (  # noqa: E402
    TEXTURE_SIZE,
    compose_loading_image,  # fonte única da composição — não copiar
    inject_loading_screen,
)

__all__ = [
    "VisualsError",
    "SourceImageInfo",
    "TEXTURE_SIZE",
    "COMPOSE_MODES",
    "COMMON_RATIOS",
    "MAX_PIXELS",
    "ALLOWED_FORMATS",
    "open_source_image",
    "compose",
    "aspect_crops",
    "safe_area_rect",
    "export_png",
    "inject_loading_into_apk",
]


class VisualsError(Exception):
    """Arte rejeitada — mensagem pronta para a UI."""


#: Modos preservados do editor original (plano fase 7).
COMPOSE_MODES = ("image", "image+text", "text")

#: Proporções comuns de tela para pré-visualização de corte.
COMMON_RATIOS: tuple[tuple[int, int], ...] = ((16, 9), (195, 90), (4, 3))

#: Acima disso a decodificação passa de ~240 MB só em pixels RGB — recusar
#: antes de abrir, não estourar memória no meio do job.
MAX_PIXELS = 80_000_000

ALLOWED_FORMATS = ("PNG", "JPEG", "WEBP")

#: Margem de segurança sugerida: conteúdo fora dela pode ser cortado por
#: notch/barra em alguma proporção de tela.
SAFE_AREA_MARGIN = 0.05


@dataclass
class SourceImageInfo:
    """Fatos medidos da arte de entrada — sem byte proprietário."""

    path: str
    format: str
    width: int
    height: int
    icc_profile: bool
    animated: bool
    warnings: list[str] = field(default_factory=list)

    @property
    def megapixels(self) -> float:
        return round(self.width * self.height / 1_000_000, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "format": self.format,
            "width": self.width,
            "height": self.height,
            "megapixels": self.megapixels,
            "icc_profile": self.icc_profile,
            "animated": self.animated,
            "warnings": list(self.warnings),
        }


def open_source_image(path: Path | str, *, max_pixels: int | None = None) -> tuple[Any, SourceImageInfo]:
    """Abre e valida a arte de entrada.

    Recusa o que o pipeline não suporta com segurança (formato fora da lista,
    dimensão que estoura memória). O resto — imagem pequena, sem perfil ICC,
    animação, modo com transparência — vira **aviso** na UI, não recusa: são
    fatos, não verdes inventados nem bloqueios imaginários.
    """
    from PIL import Image  # noqa: PLC0415 - Pillow é opcional na toolchain

    # limite resolvido em chamada (não em def) para o teste poder apertá-lo
    limite = max_pixels if max_pixels is not None else MAX_PIXELS
    caminho = Path(path)
    if not caminho.is_file():
        raise VisualsError(f"arquivo não encontrado: {caminho}")
    try:
        imagem = Image.open(caminho)
        imagem.load()
    except OSError as exc:
        raise VisualsError(f"não consegui abrir a imagem: {exc}") from exc

    formato = (getattr(imagem, "format", "") or "").upper()
    if formato not in ALLOWED_FORMATS:
        raise VisualsError(
            f"formato {formato or 'desconhecido'} não suportado — use PNG, JPG ou WebP."
        )
    largura, altura = imagem.size
    if largura < 1 or altura < 1:
        raise VisualsError(f"dimensões inválidas: {largura}x{altura}")
    if largura * altura > limite:
        raise VisualsError(
            f"imagem grande demais: {largura}x{altura} = "
            f"{largura * altura / 1_000_000:.0f} MP (máximo {limite / 1_000_000:.0f} MP). "
            "Reduza a resolução antes de importar."
        )

    avisos: list[str] = []
    if min(largura, altura) < 1024:
        avisos.append(
            f"resolução baixa ({largura}x{altura}): a textura final é 2048x2048 e a arte "
            "será ampliada — pode ficar desfocada"
        )
    tem_icc = bool(imagem.info.get("icc_profile"))
    if not tem_icc:
        avisos.append("sem perfil de cor (ICC): as cores podem mudar ligeiramente na conversão para RGB")
    animada = bool(getattr(imagem, "n_frames", 1) > 1)
    if animada:
        avisos.append("imagem animada: só o primeiro quadro é usado")
    if imagem.mode not in ("RGB", "L"):
        avisos.append(f"modo {imagem.mode}: convertido para RGB na composição")

    return imagem, SourceImageInfo(
        path=str(caminho),
        format=formato,
        width=largura,
        height=altura,
        icc_profile=tem_icc,
        animated=animada,
        warnings=avisos,
    )


#: Alias literal da composição original — **fonte única**. O teste de
#: identidade em `test_visuals.py` falha se alguém "copiar para evoluir".
compose = compose_loading_image


def aspect_crops(
    imagem: Any,
    ratios: tuple[tuple[int, int], ...] = COMMON_RATIOS,
    thumb: int = 320,
) -> list[tuple[str, Any]]:
    """Recortes centrais da arte nas proporções comuns (pré-visualização)."""
    largura, altura = imagem.size
    recortes: list[tuple[str, Any]] = []
    for rw, rh in ratios:
        alvo = rw / rh
        atual = largura / altura
        if atual > alvo:  # mais larga: corta as laterais
            nova_largura = int(altura * alvo)
            x0 = (largura - nova_largura) // 2
            caixa = (x0, 0, x0 + nova_largura, altura)
        else:  # mais alta: corta topo/base
            nova_altura = int(largura / alvo)
            y0 = (altura - nova_altura) // 2
            caixa = (0, y0, largura, y0 + nova_altura)
        recorte = imagem.crop(caixa)
        recorte.thumbnail((thumb, thumb))
        recortes.append((f"{rw}:{rh}" if rw < 100 else f"{rw / 10:g}:{rh / 10:g}", recorte))
    return recortes


def safe_area_rect(
    size: tuple[int, int], margin: float = SAFE_AREA_MARGIN
) -> tuple[int, int, int, int]:
    """Retângulo (x0, y0, x1, y1) da área segura sugerida."""
    largura, altura = size
    dx, dy = int(largura * margin), int(altura * margin)
    return dx, dy, largura - dx, altura - dy


def export_png(imagem: Any, destino: Path | str) -> Path:
    """Salva a arte composta em PNG — sem injetar nada em APK nenhum."""
    caminho = Path(destino)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    imagem.save(caminho, "PNG", optimize=True)
    return caminho


def inject_loading_into_apk(
    apk_in: Path | str,
    imagem: Any,
    apk_out: Path | str | None = None,
    log: Callable[[str], None] = print,
    report_path: Path | str | None = None,
) -> dict[str, Any]:
    """Encadeia para o fluxo validado de injeção (gates internos dele):

    só texturas de loading identificadas → bundle reserializado é reaberto e
    comparado → CRC do catálogo zerado → APK reconstruído membro a membro →
    assinado e verificado. A UI não reimplementa nada disso.
    """
    return inject_loading_screen(
        Path(apk_in),
        imagem,
        Path(apk_out) if apk_out else None,
        log=log,
        report_path=Path(report_path) if report_path else None,
    )
