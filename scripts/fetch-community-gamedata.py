#!/usr/bin/env python3
"""Fetch an optional community-preserved Mighty DOOM GameData snapshot.

The snapshot is NOT part of this repository. It is downloaded directly from a
public community Gist into server/data/, which is gitignored. Prefer data
recovered/validated from the user's own client whenever available; this helper
exists to bootstrap protocol compatibility and compare schemas.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = (
    "https://gist.githubusercontent.com/OyunErbabi/"
    "d567123cb654ddd7a14c63c36b333c50/raw/GameData.json"
)
USER_AGENT = "Mighty-Doom-Revival/0.1 (+personal-preservation)"

REQUIRED_TOP_LEVEL = (
    "resources",
    "currencies",
    "weapons",
    "equipment",
    "slayers",
    "bundles",
    "inventory",
)


def download(url: str, destination: Path) -> tuple[str, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".part")
    h = hashlib.sha256()
    total = 0

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=120) as response, tmp.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                total += len(chunk)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    tmp.replace(destination)
    return h.hexdigest(), total


def validate_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("GameData deve ser um objeto JSON no nível raiz")

    missing = [key for key in REQUIRED_TOP_LEVEL if key not in data]
    if missing:
        raise ValueError(f"snapshot incompleto; chaves ausentes: {', '.join(missing)}")

    def count(name: str) -> int:
        value = data.get(name)
        return len(value) if isinstance(value, list) else 0

    return {
        "resources": count("resources"),
        "currencies": count("currencies"),
        "weapons": count("weapons"),
        "equipment": count("equipment"),
        "launchers": count("launchers"),
        "energies": count("energies"),
        "ultimates": count("ultimates"),
        "slayers": count("slayers"),
        "cosmetics": count("cosmetics"),
        "bundles": count("bundles"),
        "story_battle_passes": count("story_battle_passes"),
        "abilities": count("abilities"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--output", default="server/data/game-data.json")
    ap.add_argument("--sha256", default="", help="SHA-256 esperado, se quiser fixar um snapshot")
    args = ap.parse_args()

    destination = Path(args.output).expanduser().resolve()
    try:
        digest, size = download(args.url, destination)
        counts = validate_json(destination)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        destination.unlink(missing_ok=True)
        print(f"ERRO: não foi possível importar GameData: {exc}", file=sys.stderr)
        return 2

    expected = args.sha256.strip().lower()
    if expected and digest.lower() != expected:
        destination.unlink(missing_ok=True)
        print("ERRO: SHA-256 diferente do snapshot esperado; arquivo removido.", file=sys.stderr)
        print(f"Esperado: {expected}", file=sys.stderr)
        print(f"Obtido:   {digest}", file=sys.stderr)
        return 3

    print("Snapshot comunitário importado localmente.")
    print(f"Arquivo:  {destination}")
    print(f"Tamanho:  {size} bytes")
    print(f"SHA-256:  {digest}")
    for key, value in counts.items():
        print(f"{key:22s}: {value}")
    print()
    print("IMPORTANTE: este snapshot é uma fonte comunitária, não um arquivo oficial.")
    print("Use-o para bootstrap/comparação e valide contra o cliente 1.13.1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
