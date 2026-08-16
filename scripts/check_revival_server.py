#!/usr/bin/env python3
"""Preflight a Revival HTTPS endpoint before rebuilding the APK.

The patcher is expensive and the client hardcodes an HTTPS host. This gate makes
sure the requested hostname resolves to a compatible Revival server with valid
TLS and the expected Mighty DOOM client/API versions before apktool starts.
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

from patch_apk import normalize_host

EXPECTED_CLIENT_VERSION = "1.13.1"
EXPECTED_API_VERSION = "24.0.0"


def build_ssl_context(ca_file: Path | None) -> ssl.SSLContext:
    if ca_file is None:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=str(ca_file))


def check_server(host: str, ca_file: Path | None, timeout: float, require_game_data: bool = True) -> dict[str, object]:
    url = f"https://{host}/revival/health"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mighty-DOOM-Revival-Patcher/1.0",
        },
        method="GET",
    )
    context = build_ssl_context(ca_file)

    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        status = int(getattr(response, "status", response.getcode()))
        content_type = str(response.headers.get("Content-Type", ""))
        raw = response.read(1024 * 1024)

    if status != 200:
        raise RuntimeError(f"health retornou HTTP {status}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("health não retornou JSON UTF-8 válido") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("health retornou JSON incompatível")

    errors: list[str] = []
    if payload.get("ok") is not True:
        errors.append("campo ok não é true")
    if payload.get("client_version") != EXPECTED_CLIENT_VERSION:
        errors.append(
            f"client_version={payload.get('client_version')!r}; esperado {EXPECTED_CLIENT_VERSION!r}"
        )
    if payload.get("api_version") != EXPECTED_API_VERSION:
        errors.append(
            f"api_version={payload.get('api_version')!r}; esperado {EXPECTED_API_VERSION!r}"
        )
    if require_game_data and payload.get("game_data_loaded") is not True:
        errors.append("game_data_loaded não é true")
    if errors:
        raise RuntimeError("servidor Revival incompatível: " + "; ".join(errors))

    return {
        "verified": True,
        "url": url,
        "http_status": status,
        "content_type": content_type,
        "server": payload.get("server"),
        "client_version": payload.get("client_version"),
        "api_version": payload.get("api_version"),
        "game_data_loaded": payload.get("game_data_loaded"),
        "research_mode": payload.get("research_mode"),
        "runtime": payload.get("runtime"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True, help="Hostname ou URL HTTPS do Revival")
    parser.add_argument("--ca", help="CA PEM/CRT opcional para HTTPS privado")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--allow-missing-game-data", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()

    try:
        host = normalize_host(args.server)
    except ValueError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    ca_file: Path | None = None
    if args.ca:
        ca_file = Path(args.ca).expanduser().resolve()
        if not ca_file.is_file():
            print(f"ERRO: CA não encontrada: {ca_file}", file=sys.stderr)
            return 2

    try:
        result = check_server(
            host,
            ca_file,
            max(1.0, args.timeout),
            require_game_data=not args.allow_missing_game_data,
        )
    except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
        print(f"ERRO de rede/TLS ao acessar https://{host}/revival/health: {exc}", file=sys.stderr)
        return 3
    except RuntimeError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 4

    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.report:
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    print("Revival HTTPS validado: versão/API/GameData compatíveis com o patcher.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
