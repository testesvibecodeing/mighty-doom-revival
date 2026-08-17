#!/usr/bin/env python3
"""Extrai os ícones de conteúdo do Mighty DOOM para o painel do Revival.

A fonte é a cópia local do APK oficial (interoperabilidade com a própria
cópia do usuário — nunca redistribuída pelo Git). Os PNGs saem em
server/public/assets/img/game/ (gitignored) junto de um manifest.json que o
servidor lê em runtime para casar recurso -> ícone.

Uso:
    python scripts/extract-game-icons.py [--apk input/mighty-doom.apk]
                                         [--out server/public/assets/img/game]

Requer UnityPy + Pillow (pip install UnityPy Pillow).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

try:
    import UnityPy
except ImportError:  # pragma: no cover
    print("ERRO: instale as dependências: pip install UnityPy Pillow", file=sys.stderr)
    raise SystemExit(2)

# Sprites de conteúdo do jogo. UI genérica (botões, barras, HUD) fica de fora:
# o painel tem CSS próprio e só interessa o catálogo (armas, skins, slayers,
# gear, launchers, ultimates, crates, packs de moeda e perks).
NAME_PATTERN = re.compile(
    r"^(?:"
    r"WPN_Icon_|SLAY_Icon_|SKIN_Icon_|GEAR_Icon_|LCH_Icon_|ULT_Icon_|"
    r"CRT_Icon_|Icon_Crate_Sentinel|STORE_|OFFERS_|item_rarity_|"
    r"Icon_Ability_|icon_ability_"
    r")"
)

# Slugs encurtados: mantém o nome estável e legível no manifest.
SLUG_STRIP = re.compile(r"_?SPRITE$")


def slugify(name: str) -> str:
    slug = SLUG_STRIP.sub("", name)
    slug = re.sub(r"[^A-Za-z0-9]+", "_", slug).strip("_").lower()
    return slug or "icon"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--apk", default=str(repo / "input" / "mighty-doom.apk"))
    ap.add_argument("--out", default=str(repo / "server" / "public" / "assets" / "img" / "game"))
    args = ap.parse_args()

    apk = Path(args.apk).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    if not apk.is_file():
        print(f"ERRO: APK não encontrado: {apk}", file=sys.stderr)
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Carregando {apk.name} ({apk.stat().st_size / 1048576:.0f} MB)…")
    env = UnityPy.load(str(apk))

    exported: dict[str, dict[str, int]] = {}
    for obj in env.objects:
        if obj.type.name != "Sprite":
            continue
        try:
            sprite = obj.read()
        except Exception:
            continue
        name = sprite.m_Name
        if not NAME_PATTERN.match(name):
            continue
        slug = slugify(name)
        if slug in exported:
            continue  # mesmo sprite em bundles diferentes: fica o primeiro
        try:
            image = sprite.image
            if image is None or image.width < 8 or image.height < 8:
                continue
            image.save(out_dir / f"{slug}.png")
        except Exception:
            continue
        exported[slug] = {"w": image.width, "h": image.height}

    if not exported:
        print("ERRO: nenhum sprite exportado — o APK é da versão esperada?", file=sys.stderr)
        return 3

    manifest = {
        "source": {"file": apk.name, "sha256": sha256_of(apk)},
        "count": len(exported),
        "files": dict(sorted(exported.items())),
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"OK: {len(exported)} ícones em {out_dir}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
