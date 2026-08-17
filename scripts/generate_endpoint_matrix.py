#!/usr/bin/env python3
"""Fonte de verdade única da convergência para paridade funcional.

Sincroniza `compatibility.json` e regenera `docs/ENDPOINT-MATRIX.md` — nunca
edite nenhum dos dois à mão. Campos derivados de código são recomputados a cada
execução; campos de evidência (observado no cliente, validado, persistência)
vêm do JSON existente ou de relatórios do harness.

Campos DERIVADOS (recomputados, escrever à mão não tem efeito):
  implemented      rota aparece como literal em server/src/*.js (exata ou via
                   prefixo registrado em PREFIX_ROUTES)
  regression_test  rota aparece como literal em server/test/*.mjs
  fixture          existe captura em tests/fixtures/protocol/<slug>.json
  request_observed/response_observed  auto-true quando a captura tem
                   provenance "client" (harness real); senão preserva o manual
  server_only      rotas implementadas no servidor que NÃO existem nas 116 do
                   cliente (código legado; candidatas a remoção)

Campos de EVIDÊNCIA (só mudam com prova, via --set ou edição consciente):
  schema_extracted, client_validated, persistence_validated, uses_fallback

Uso:
  python scripts/generate_endpoint_matrix.py                     # sync + doc
  python scripts/generate_endpoint_matrix.py --check             # gate: sujo = exit 1
  python scripts/generate_endpoint_matrix.py --metadata work/meta-check/global-metadata.dat
  python scripts/generate_endpoint_matrix.py --set game/talents/buy schema_extracted=true \
      --note game/talents/buy "DTO extraído do metadata 2026-08-17"

Exit codes: 0 ok; 1 --check falhou (drift); 2 uso inválido; 3 drift de rotas
entre metadata e compatibility.json (base trocou).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from dump_il2cpp_metadata import extract_routes  # noqa: E402

COMPAT_JSON = ROOT / "compatibility.json"
MATRIX_MD = ROOT / "docs" / "ENDPOINT-MATRIX.md"
SERVER_SRC = ROOT / "server" / "src"
SERVER_TEST = ROOT / "server" / "test"
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "protocol"

# Rotas atendidas por prefixo no servidor (startsWith), não por literal exato.
PREFIX_ROUTES = {
    "game/iap/": "desativado deliberadamente (erro 2000 explícito)",
    "game/ads/": "desativado deliberadamente (payload ads_disabled)",
}

# Módulos fora do escopo de gameplay (dependência externa de dinheiro/plataforma).
OUT_OF_SCOPE = {"iap", "ads"}

# Ordem de ataque definida no plano de convergência (menor = antes).
MODULE_PRIORITY = {
    "gear": 1, "slayers": 2, "talents": 3, "chapters": 4, "quests": 5,
    "reward-tracks": 6, "inbox": 7, "player": 8, "events": 9, "battle-pass": 10,
    "daily-rewards": 11, "idle-rewards": 12, "store": 13, "inventory": 14,
    "armory": 15, "tutorial": 16, "session": 17, "auth": 18, "identity": 19,
    "devices": 20, "codes": 21, "xbox": 22, "bnet": 23,
}

# Ordem dos gates do DEFINITION OF DONE; o primeiro gate falso é a próxima tarefa.
DOD_GATES = (
    "schema_extracted", "implemented", "request_observed", "response_observed",
    "client_validated", "persistence_validated", "regression_test",
)

ROUTE_RE = re.compile(r"['\"](/game/[a-z0-9/-]*?)['\"]")

EVIDENCE_SEED = {
    # Bootstrap validado ponta a ponta no emulador (RELATORIO-STATUS 2026-08-16):
    # conta revivaltest criada pelo cliente, zero erros no logcat.
    "game/auth/register": {
        "request_observed": True, "response_observed": True, "client_validated": True,
        "evidence": "RELATORIO-STATUS 2026-08-16: registro da conta revivaltest feito pelo cliente no emulador, boot completo sem erros no logcat.",
    },
    "game/auth/login-device": {
        "request_observed": True, "response_observed": True, "client_validated": True,
        "evidence": "RELATORIO-STATUS 2026-08-16: login-device no bootstrap do emulador, resposta aceita pelo cliente.",
    },
    "game/player/game-data-token": {
        "request_observed": True, "response_observed": True, "client_validated": True,
        "evidence": "RELATORIO-STATUS 2026-08-16: bootstrap completo no emulador; /data baixado com o token.",
    },
    "game/player/user-data": {
        "request_observed": True, "response_observed": True, "client_validated": True,
        "persistence_validated": True,
        "evidence": "RELATORIO-STATUS 2026-08-16: user-data no bootstrap e refletindo progressão persistida após restart do servidor.",
    },
    "game/armory/get": {
        "request_observed": True, "response_observed": True, "client_validated": True,
        "evidence": "RELATORIO-STATUS 2026-08-16: boot completo; upgrades:[] evita o NRE do ArmoryController.Init.",
    },
    "game/events/get-schedule": {
        "request_observed": True, "response_observed": True, "client_validated": True,
        "evidence": "RELATORIO-STATUS 2026-08-16: menu com eventos do servidor (Slayers Energy / Speedrun Challenge) no emulador.",
    },
    "game/events/get-progress": {
        "request_observed": True, "response_observed": True, "client_validated": True,
        "evidence": "RELATORIO-STATUS 2026-08-16: eventos do menu com progresso/timers vindos do servidor.",
    },
    "game/session/refresh": {
        "request_observed": True, "response_observed": True, "client_validated": True,
        "evidence": "RELATORIO-STATUS 2026-08-16: session/refresh contínuo durante o combate (keepalive).",
    },
    # Partida 1-1 completa no emulador: start -> update (5 salas) -> end -> 1-2 desbloqueado.
    "game/chapters/start": {
        "request_observed": True, "response_observed": True, "client_validated": True,
        "evidence": "RELATORIO-STATUS 2026-08-16: partida completa do estágio 1-1 no emulador.",
    },
    "game/chapters/update": {
        "request_observed": True, "response_observed": True, "client_validated": True,
        "evidence": "RELATORIO-STATUS 2026-08-16: avanço nas 5 salas do 1-1.",
    },
    "game/chapters/end": {
        "request_observed": True, "response_observed": True, "client_validated": True,
        "persistence_validated": True,
        "evidence": "RELATORIO-STATUS 2026-08-16: vitória do 1-1, recompensas, 1-2 desbloqueado; current_run persistido.",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def module_of(route: str) -> str:
    parts = route.split("/")
    return parts[1] if len(parts) > 1 else "raiz"


def scan_literals(directory: Path, suffixes: tuple[str, ...]) -> set[str]:
    """Literals '/game/...' citados em código (exatos e prefixos)."""
    found: set[str] = set()
    if not directory.is_dir():
        return found
    for path in sorted(directory.iterdir()):
        if path.suffix not in suffixes or not path.is_file():
            continue
        for match in ROUTE_RE.findall(path.read_text(encoding="utf-8", errors="replace")):
            route = match.lstrip("/")
            if route == "game" or route == "game/":
                continue
            found.add(route.rstrip("/") or route)
    return found


def implemented_routes() -> set[str]:
    exact = scan_literals(SERVER_SRC, (".js",))
    resolved = {r for r in exact if not r.endswith("/")}
    for prefix in PREFIX_ROUTES:
        resolved.add(prefix)
    return resolved


def test_routes() -> set[str]:
    return scan_literals(SERVER_TEST, (".mjs", ".js"))


def load_fixtures() -> dict[str, dict]:
    fixtures: dict[str, dict] = {}
    if not FIXTURES_DIR.is_dir():
        return fixtures
    for path in sorted(FIXTURES_DIR.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        endpoint = data.get("endpoint")
        if isinstance(endpoint, str) and endpoint.startswith("game/"):
            fixtures[endpoint] = {
                "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                "provenance": data.get("provenance", "unknown"),
            }
    return fixtures


def resolve_implementation(route: str, implemented: set[str]) -> bool:
    if route in implemented:
        return True
    return any(route.startswith(prefix) for prefix in PREFIX_ROUTES)


def first_failed_gate(endpoint: dict) -> str | None:
    for gate in DOD_GATES:
        value = endpoint.get(gate)
        if value is None:  # persistence_validated: null = não aplicável
            continue
        if value is False:
            return gate
    if endpoint.get("uses_fallback"):
        return "uses_fallback"
    return None


def endpoint_done(endpoint: dict) -> bool:
    return first_failed_gate(endpoint) is None


def build_compat(metadata: Path | None, previous: dict | None) -> dict:
    metadata_routes: list[str] | None = None
    metadata_version = previous.get("_meta", {}).get("metadata_version", 29) if previous else 29
    if metadata:
        extracted = extract_routes(metadata)
        metadata_routes = extracted["routes"]
        metadata_version = extracted["version"]

    prev_meta = (previous or {}).get("_meta", {})
    prev_endpoints = (previous or {}).get("endpoints", {})
    prev_routes = set(prev_endpoints)

    routes = metadata_routes or sorted(prev_routes)
    if metadata_routes is not None and prev_routes and set(metadata_routes) != prev_routes:
        added = sorted(set(metadata_routes) - prev_routes)
        removed = sorted(prev_routes - set(metadata_routes))
        print(f"ERRO: drift de rotas entre metadata e compatibility.json: +{added} -{removed}", file=sys.stderr)
        raise SystemExit(3)

    implemented = implemented_routes()
    tests = test_routes()
    fixtures = load_fixtures()

    endpoints: dict[str, dict] = {}
    for route in routes:
        module = module_of(route)
        prev = prev_endpoints.get(route, {})
        seed = EVIDENCE_SEED.get(route, {})
        fixture = fixtures.get(route)

        request_observed = bool(prev.get("request_observed") or seed.get("request_observed"))
        response_observed = bool(prev.get("response_observed") or seed.get("response_observed"))
        if fixture and fixture["provenance"] == "client":
            request_observed = True
            response_observed = True

        endpoints[route] = {
            "module": module,
            "implemented": resolve_implementation(route, implemented),
            "schema_extracted": bool(prev.get("schema_extracted", False)),
            "request_observed": request_observed,
            "response_observed": response_observed,
            "client_validated": bool(prev.get("client_validated") or seed.get("client_validated", False)),
            "persistence_validated": prev.get("persistence_validated", seed.get("persistence_validated")),
            "regression_test": route in tests,
            "fixture": fixture["file"] if fixture else None,
            "fixture_provenance": fixture["provenance"] if fixture else None,
            "uses_fallback": bool(prev.get("uses_fallback", False)),
            "evidence": prev.get("evidence") or seed.get("evidence", ""),
        }

    # Rotas implementadas no servidor que o cliente nunca chama (legado).
    server_only = sorted(
        r for r in implemented
        if not r.endswith("/") and not any(rt == r or rt.startswith(r + "/") for rt in endpoints) and r != "game"
    )
    # Prefixos atendidos que não cobrem nenhuma rota do cliente também são legado.
    for prefix in PREFIX_ROUTES:
        if not any(rt.startswith(prefix) for rt in endpoints):
            server_only.append(prefix)

    client_routes = set(metadata_routes or prev_routes)
    prefix_stems = {p.rstrip("/") for p in PREFIX_ROUTES}
    legacy = sorted(r for r in scan_literals(SERVER_SRC, (".js",))
                    if not r.endswith("/") and r != "game" and r not in client_routes
                    and r not in prefix_stems)

    return {
        "_meta": {
            "version": 1,
            "client": "com.bethsoft.ubu 1.13.1 build 84862",
            "metadata_version": metadata_version,
            "route_count": len(endpoints),
            "updated": utc_now(),
            "dod_gates": list(DOD_GATES),
            "derived": ["implemented", "regression_test", "fixture", "fixture_provenance",
                        "request_observed*", "response_observed*"],
            "note": "Gerado por scripts/generate_endpoint_matrix.py; não edite campos derivados à mão.",
        },
        "endpoints": endpoints,
        "server_only_routes": legacy if legacy else server_only,
        "out_of_scope_modules": sorted(OUT_OF_SCOPE),
        "module_priority": MODULE_PRIORITY,
    }


STATUS_ICON = {
    "done": "✅", "client": "🧪", "schema": "🔬", "missing": "❌", "fallback": "🔁",
}


def endpoint_status(endpoint: dict) -> tuple[str, str]:
    """(ícone, rótulo) do estado resumido na matriz."""
    if endpoint.get("uses_fallback"):
        return STATUS_ICON["fallback"], "usa fallback RESEARCH_MODE"
    if endpoint_done(endpoint):
        return STATUS_ICON["done"], "DoD completo"
    if endpoint.get("client_validated"):
        return STATUS_ICON["client"], "cliente OK, falta DoD"
    if endpoint.get("schema_extracted"):
        return STATUS_ICON["schema"], "schema extraído"
    if not endpoint.get("implemented"):
        return STATUS_ICON["missing"], "não implementado"
    return STATUS_ICON["client"], "implementado, aguardando validação"


def render_matrix(compat: dict) -> str:
    endpoints = compat["endpoints"]
    modules: dict[str, list[str]] = {}
    for route, data in endpoints.items():
        modules.setdefault(data["module"], []).append(route)

    priority = compat.get("module_priority", {})
    ordered = sorted(modules, key=lambda m: (priority.get(m, 99), m))
    out_of_scope = set(compat.get("out_of_scope_modules", []))

    lines = [
        "# Matriz de compatibilidade da API",
        "",
        "<!-- GERADO por scripts/generate_endpoint_matrix.py a partir de compatibility.json.",
        "     Não edite à mão: rode o script. -->",
        "",
        f"Fonte de verdade: `compatibility.json` · atualizado em {compat['_meta']['updated']} ·",
        f"{compat['_meta']['route_count']} rotas `game/*` extraídas do global-metadata.dat v{compat['_meta']['metadata_version']}",
        f"do cliente {compat['_meta']['client']}.",
        "",
        "DEFINITION OF DONE por endpoint (todos devem ser verdadeiros;",
        "`persistence_validated` nulo = não aplicável):",
        "`schema_extracted` · `implemented` · `request_observed` · `response_observed` ·",
        "`client_validated` · `persistence_validated` · `regression_test` · `uses_fallback=false`.",
        "",
        "| Módulo | Pri | Endpoints | ✅ DoD | 🧪 impl. | ❌ falta | 🔬 schema | Estado |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for module in ordered:
        routes = sorted(modules[module])
        done = client = missing = schema = 0
        for route in routes:
            data = endpoints[route]
            if endpoint_done(data):
                done += 1
            elif data.get("client_validated"):
                client += 1
            elif not data.get("implemented"):
                missing += 1
            elif data.get("schema_extracted"):
                schema += 1
            else:
                client += 1
        implemented_count = sum(1 for r in routes if endpoints[r].get("implemented"))
        if module in out_of_scope:
            state = "⛔ fora de escopo (dependência externa)"
        elif done == len(routes):
            state = "✅ paridade"
        elif missing == len(routes):
            state = "❌ nada implementado"
        else:
            state = "🧪 em convergência"
        scope = " ⛔" if module in out_of_scope else ""
        lines.append(
            f"| [{module}{scope}](#{module}) | {priority.get(module, 99)} | {len(routes)} "
            f"| {done} | {implemented_count - done} | {missing} | {schema} | {state} |"
        )

    lines += ["", "## Detalhe por módulo", ""]
    for module in ordered:
        lines.append(f"### {module}")
        lines.append("")
        lines.append("| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |")
        lines.append("|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|")
        for route in sorted(modules[module]):
            d = endpoints[route]
            def mark(value):
                if value is None:
                    return "—"
                return "✅" if value else "·"
            fixture = "✅" if d.get("fixture") else "·"
            note = d.get("evidence") or endpoint_status(d)[1]
            lines.append(
                f"| `{route}` | {mark(d['implemented'])} | {mark(d['schema_extracted'])} "
                f"| {mark(d['request_observed'])} | {mark(d['response_observed'])} "
                f"| {mark(d['client_validated'])} | {mark(d['persistence_validated'])} "
                f"| {mark(d['regression_test'])} | {fixture} "
                f"| {'🔁' if d['uses_fallback'] else '—'} | {note} |"
            )
        lines.append("")

    legacy = compat.get("server_only_routes") or []
    lines += [
        "## Rotas legadas do servidor (não existem no cliente)",
        "",
        "Implementadas em `server/src` mas ausentes das 116 rotas do metadata —",
        "provável erro de transcrição histórico. Candidatas a remoção;",
        "nenhum cliente 1.13.1 as chama.",
        "",
    ]
    if legacy:
        lines += [f"- `{route}`" for route in legacy]
    else:
        lines += ["- nenhuma"]
    lines.append("")
    return "\n".join(lines)


def apply_set(compat: dict, route: str, assignments: list[str], notes: dict[str, str]) -> None:
    endpoint = compat["endpoints"].get(route)
    if endpoint is None:
        print(f"ERRO: rota fora das {compat['_meta']['route_count']} do registro: {route}", file=sys.stderr)
        raise SystemExit(2)
    for assignment in assignments:
        if "=" not in assignment:
            print(f"ERRO: --set espera campo=valor, veio {assignment!r}", file=sys.stderr)
            raise SystemExit(2)
        key, _, raw = assignment.partition("=")
        if key not in ("schema_extracted", "client_validated", "uses_fallback"):
            print(f"ERRO: campo {key!r} não é campo de evidência editável", file=sys.stderr)
            raise SystemExit(2)
        if raw not in ("true", "false"):
            print(f"ERRO: {key} espera true/false, veio {raw!r}", file=sys.stderr)
            raise SystemExit(2)
        endpoint[key] = raw == "true"
    if route in notes:
        endpoint["evidence"] = notes[route]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--metadata", type=Path, default=None,
                        help="global-metadata.dat (ou APK) para verificar drift de rotas")
    parser.add_argument("--check", action="store_true",
                        help="não escreve nada; exit 1 se JSON/matriz estão desatualizados")
    parser.add_argument("--set", action="append", default=[], metavar="ROTA=campo=valor",
                        help="ex.: --set game/talents/buy=schema_extracted=true (repetível)")
    parser.add_argument("--note", action="append", default=[], metavar="ROTA=TEXTO",
                        help="anexa evidência à rota (repetível)")
    args = parser.parse_args()

    previous = None
    if COMPAT_JSON.is_file():
        previous = json.loads(COMPAT_JSON.read_text(encoding="utf-8"))

    compat = build_compat(args.metadata, previous)

    if args.set or args.note:
        notes = {}
        for item in args.note:
            route, sep, text = item.partition("=")
            if not sep:
                print(f"ERRO: --note espera rota=texto, veio {item!r}", file=sys.stderr)
                return 2
            notes[route] = text
        grouped: dict[str, list[str]] = {}
        for item in args.set:
            route, sep, assignment = item.partition("=")
            if not sep:
                print(f"ERRO: --set espera rota=campo=valor, veio {item!r}", file=sys.stderr)
                return 2
            grouped.setdefault(route, []).append(assignment)
        for route, assignments in grouped.items():
            apply_set(compat, route, assignments, notes)

    # Campos derivados não dependem de --set: --set só toca evidência.
    # Recalcula updated apenas quando algo mudou além do timestamp.
    compat["_meta"]["updated"] = utc_now()
    matrix = render_matrix(compat)

    if args.check:
        current_json = COMPAT_JSON.read_text(encoding="utf-8") if COMPAT_JSON.is_file() else ""
        current_md = MATRIX_MD.read_text(encoding="utf-8") if MATRIX_MD.is_file() else ""
        stale = []
        # Timestamps não são drift: mascara antes de comparar para o gate ser
        # determinístico (mesmo conteúdo -> check passa, hora não importa).
        def strip (doc: str) -> str:
            doc = re.sub(r'"updated": "[^"]+"', '"updated": "-"', doc)
            return re.sub(r"atualizado em \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", "atualizado em -", doc)
        if strip(current_json) != strip(json.dumps(compat, indent=2, ensure_ascii=False) + "\n"):
            stale.append("compatibility.json")
        if strip(current_md) != strip(matrix):
            stale.append("docs/ENDPOINT-MATRIX.md")
        if stale:
            print(f"DESATUALIZADO: {', '.join(stale)} — rode scripts/generate_endpoint_matrix.py", file=sys.stderr)
            return 1
        print("[OK] compatibility.json e docs/ENDPOINT-MATRIX.md estão sincronizados")
        return 0

    COMPAT_JSON.write_text(json.dumps(compat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    MATRIX_MD.parent.mkdir(parents=True, exist_ok=True)
    MATRIX_MD.write_text(matrix, encoding="utf-8")

    total = len(compat["endpoints"])
    done = sum(1 for d in compat["endpoints"].values() if endpoint_done(d))
    implemented = sum(1 for d in compat["endpoints"].values() if d["implemented"])
    fallbacks = sum(1 for d in compat["endpoints"].values() if d["uses_fallback"])
    print(f"compatibility.json: {total} rotas · {implemented} implementadas · {done} DoD completo · {fallbacks} em fallback")
    print(f"docs/ENDPOINT-MATRIX.md regenerado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
