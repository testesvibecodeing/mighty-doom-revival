#!/usr/bin/env python3
"""Preflight a Revival HTTPS endpoint before rebuilding the APK.

The patcher is expensive and the client hardcodes an HTTPS host. This gate makes
sure the requested hostname resolves to a compatible Revival server with valid
TLS and the expected Mighty DOOM client/API versions before apktool starts.

Besides the canonical health endpoint, the preflight exercises the exact Gear
collection prefix baked into Mighty DOOM 1.13.1 and performs a non-mutating auth
contract probe. This catches reverse-proxy configurations that serve
``/revival/health`` correctly but fail the real client path
``/collections/doom/game/...`` before an APK is rebuilt and signed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

from patch_apk import normalize_host

EXPECTED_CLIENT_VERSION = "1.13.1"
EXPECTED_API_VERSION = "24.0.0"
GEAR_COLLECTION = "doom"


def build_ssl_context(ca_file: Path | None) -> ssl.SSLContext:
    if ca_file is None:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=str(ca_file))


def read_json_response(response, limit: int = 1024 * 1024) -> tuple[int, str, dict[str, object]]:
    status = int(getattr(response, "status", response.getcode()))
    content_type = str(response.headers.get("Content-Type", ""))
    raw = response.read(limit)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"HTTP {status} não retornou JSON UTF-8 válido") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"HTTP {status} retornou JSON incompatível")
    return status, content_type, payload


def get_json(url: str, context: ssl.SSLContext, timeout: float) -> tuple[int, str, dict[str, object]]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mighty-DOOM-Revival-Patcher/1.1",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return read_json_response(response)


def post_json(
    url: str,
    payload: dict[str, object],
    context: ssl.SSLContext,
    timeout: float,
    expected_http_error: int | None = None,
) -> tuple[int, str, dict[str, object]]:
    raw = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=raw,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Content-Length": str(len(raw)),
            "User-Agent": "Mighty-DOOM-Revival-Patcher/1.1",
            "x-ubu-apiversion": EXPECTED_API_VERSION,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return read_json_response(response)
    except urllib.error.HTTPError as exc:
        if expected_http_error is None or exc.code != expected_http_error:
            raise
        return read_json_response(exc)


def validate_health(payload: dict[str, object], require_game_data: bool) -> list[str]:
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
    return errors


def validate_wire_timestamp(payload: dict[str, object], label: str) -> str:
    """Require the wire timestamp shape consumed by client 1.13.1.

    ``Ubu.GameController.ParseServerTimestamp`` ultimately feeds ``uts`` to
    ``DateTime.Parse``. A numeric unix epoch reaches the correct auth handler
    but crashes the client callback with ``FormatException``. The preflight
    therefore treats a parseable, timezone-aware UTC ISO-8601 string as part
    of the compatibility contract, not merely an implementation detail.
    """
    value = payload.get("uts")
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(
            f"{label} retornou uts={value!r}; cliente 1.13.1 exige string ISO 8601 UTC"
        )

    normalized = value.strip()
    parse_value = normalized[:-1] + "+00:00" if normalized.endswith("Z") else normalized
    try:
        parsed = datetime.fromisoformat(parse_value)
    except ValueError as exc:
        raise RuntimeError(
            f"{label} retornou uts={value!r}; timestamp ISO 8601 inválido"
        ) from exc

    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise RuntimeError(
            f"{label} retornou uts={value!r}; timestamp deve possuir offset UTC explícito"
        )
    return normalized


def check_server(host: str, ca_file: Path | None, timeout: float, require_game_data: bool = True) -> dict[str, object]:
    context = build_ssl_context(ca_file)
    canonical_url = f"https://{host}/revival/health"
    gear_health_url = f"https://{host}/collections/{GEAR_COLLECTION}/revival/health"
    auth_probe_url = f"https://{host}/collections/{GEAR_COLLECTION}/game/auth/register"

    status, content_type, payload = get_json(canonical_url, context, timeout)
    if status != 200:
        raise RuntimeError(f"health retornou HTTP {status}")
    errors = validate_health(payload, require_game_data)
    if errors:
        raise RuntimeError("servidor Revival incompatível: " + "; ".join(errors))

    # The patched 1.13.1 client retains /collections/doom after the host swap.
    # A proxy can accidentally make /revival/health work while rejecting this
    # path, so verify the exact prefix before spending time on apktool/signing.
    gear_status, _, gear_payload = get_json(gear_health_url, context, timeout)
    if gear_status != 200:
        raise RuntimeError(f"health com prefixo Gear retornou HTTP {gear_status}")
    gear_errors = validate_health(gear_payload, require_game_data)
    if gear_errors:
        raise RuntimeError("rota Gear incompatível: " + "; ".join(gear_errors))

    # Non-mutating API contract probe: an intentionally wrong client_version
    # must be routed to the Revival auth handler and rejected with game code
    # 2200. If the proxy/path is wrong we normally see 404/HTML instead.
    auth_status, auth_content_type, auth_payload = post_json(
        auth_probe_url,
        {"client_version": "revival-preflight-invalid"},
        context,
        timeout,
        expected_http_error=400,
    )
    if auth_status != 400 or auth_payload.get("code") != 2200:
        raise RuntimeError(
            "auth probe pelo prefixo Gear não atingiu o handler esperado "
            f"(HTTP {auth_status}, code={auth_payload.get('code')!r})"
        )
    auth_uts = validate_wire_timestamp(auth_payload, "auth probe")

    return {
        "verified": True,
        "url": canonical_url,
        "http_status": status,
        "content_type": content_type,
        "server": payload.get("server"),
        "client_version": payload.get("client_version"),
        "api_version": payload.get("api_version"),
        "game_data_loaded": payload.get("game_data_loaded"),
        "research_mode": payload.get("research_mode"),
        "runtime": payload.get("runtime"),
        "gear_prefix": {
            "collection": GEAR_COLLECTION,
            "health_url": gear_health_url,
            "health_status": gear_status,
            "auth_probe_url": auth_probe_url,
            "auth_probe_status": auth_status,
            "auth_probe_code": auth_payload.get("code"),
            "auth_probe_uts": auth_uts,
            "auth_probe_content_type": auth_content_type,
        },
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
        print(f"ERRO de rede/TLS ao validar https://{host}: {exc}", file=sys.stderr)
        return 3
    except RuntimeError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 4

    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.report:
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    print("Revival HTTPS validado: TLS, versão/API/GameData, rota Gear e wire timestamp compatíveis.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())