#!/usr/bin/env python3
"""Small, dependency-free operator CLI for the Revival admin API.

The browser panel is the primary interface. This companion keeps the same
administrative operations usable from a terminal/cron without editing runtime
JSON by hand. It only calls routes already implemented by server/src/admin.js.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def payload(value: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"JSON inválido: {exc.msg}") from exc


class AdminClient:
    def __init__(self, base: str, token: str | None, timeout: float = 15) -> None:
        self.base = base.rstrip("/")
        self.token = token
        self.timeout = timeout

    def call(self, path: str, method: str = "GET", body: object | None = None) -> object:
        headers = {"accept": "application/json"}
        if self.token:
            headers["authorization"] = f"Bearer {self.token}"
        data = None
        if body is not None:
            headers["content-type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        request = Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                details = json.loads(raw)
            except json.JSONDecodeError:
                details = raw
            raise RuntimeError(f"HTTP {exc.code}: {details}") from exc
        except URLError as exc:
            raise RuntimeError(f"Não foi possível conectar ao servidor: {exc.reason}") from exc


def add_json_argument(parser: argparse.ArgumentParser, name: str = "body") -> None:
    parser.add_argument(name, type=payload, help="objeto JSON enviado ao endpoint")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Administração do Mighty DOOM Revival")
    parser.add_argument("--server", default=os.getenv("REVIVAL_SERVER_URL", "http://127.0.0.1:8080"), help="URL base do servidor")
    parser.add_argument("--token", default=os.getenv("REVIVAL_ADMIN_TOKEN"), help="REVIVAL_ADMIN_TOKEN (ou variável de ambiente)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="mostra a saúde pública do servidor")
    sub.add_parser("overview", help="mostra o resumo administrativo")
    reload_parser = sub.add_parser("reload", help="recarrega configs runtime")
    reload_parser.set_defaults(method="POST", path="/revival/reload")

    users = sub.add_parser("users", help="lista usuários")
    users.add_argument("--query", default="")
    grant = sub.add_parser("grant", help="concede recurso a um usuário")
    grant.add_argument("user_id", type=int)
    grant.add_argument("resource")
    grant.add_argument("amount", type=int)
    grant.add_argument("--kind")

    for resource in ("packs", "events", "notifications"):
        item = sub.add_parser(resource, help=f"lista {resource} ou envia uma operação JSON")
        item.add_argument("--id", type=int)
        item.add_argument("--delete", action="store_true")
        item.add_argument("--method", choices=("POST", "PATCH"), help="método para --body")
        item.add_argument("--body", type=payload, help="objeto JSON para criar/editar")

    for resource in ("site", "smtp"):
        item = sub.add_parser(resource, help=f"lê ou atualiza {resource}")
        item.add_argument("--body", type=payload, help="objeto JSON para atualizar")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = AdminClient(args.server, args.token)
    try:
        if args.command == "health":
            result = client.call("/revival/health")
        elif args.command == "overview":
            result = client.call("/account/admin/overview")
        elif args.command == "reload":
            result = client.call("/revival/reload", "POST")
        elif args.command == "users":
            query = urlencode({"query": args.query})
            result = client.call(f"/account/admin/users?{query}")
        elif args.command == "grant":
            body = {"resource": args.resource, "amount": args.amount}
            if args.kind:
                body["kind"] = args.kind
            result = client.call(f"/account/admin/users/{args.user_id}/grant", "POST", body)
        elif args.command in {"packs", "events", "notifications"}:
            path = f"/account/admin/{args.command}"
            if args.id is not None:
                path += f"/{args.id}"
            if args.delete:
                result = client.call(path, "DELETE")
            elif args.body is not None:
                result = client.call(path, args.method or ("PATCH" if args.id is not None else "POST"), args.body)
            else:
                result = client.call(path)
        else:
            path = f"/account/admin/{args.command}"
            result = client.call(path, "PATCH" if args.body is not None else "GET", args.body)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except RuntimeError as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
