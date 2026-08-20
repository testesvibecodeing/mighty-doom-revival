#!/usr/bin/env python3
"""Harness ADB do cliente real — valida fluxos de gameplay de ponta a ponta.

Cadeia de evidência (uma execução = uma prova isolada):

  1. resolve `adb` e o dispositivo; valida /revival/health;
  2. tira BASELINE antes de abrir o app: cursor do request_log (max id via
     /revival/requests) e contagem de fallbacks (/revival/research);
  3. (opcional) instala o APK (--apk) e abre o jogo;
  4. observa o logcat por --duration segundos (corta cedo se o boot morrer);
  5. captura o DELTA da execução: /revival/requests?since_id=<cursor> em ordem
     crescente (sequência temporal real, requests antigos excluídos) e o delta
     de fallbacks desde o baseline;
  6. com --capture-fixtures/--update-registry, grava uma fixture sanitizada
     provenance=client por endpoint observado (request e response da MESMA
     chamada, pareados pelo servidor) em tests/fixtures/protocol/client/;
  7. veredito SEM ambiguidade: flow_validated | captured | diagnostic_clean |
     no_observed_traffic | inconclusive | failed;
     `no_observed_traffic` = o app foi aberto, a janela estava certa e o cursor
     da instância observada não andou. Prova SÓ isso — não decide entre rig
     quebrado, outra instância atendendo ou sessão persistida;
  8. com --update-registry, NÃO edita compatibility.json à mão: escreve as
     fixtures e deixa scripts/generate_endpoint_matrix.py derivar os gates
     (usa --set/--note do gerador para evidência declarada).

Importante: sem --admin-token não existe captura de endpoints. O veredito
nesse caso é `inconclusive` (exit 3) — exceto com --diagnostic explícito,
que declara que a execução é apenas diagnóstico de logcat (`diagnostic_clean`).

Uso:
  python scripts/client_harness.py --server https://doom.exemplo.br --diagnostic
  python scripts/client_harness.py --server http://192.168.0.10:8080 \
      --apk output/mighty-doom-revival.apk --admin-token <token> \
      --flow boot --require-endpoint game/player/user-data \
      --duration 300 --update-registry
  (o token também pode vir da env REVIVAL_ADMIN_TOKEN)

Exit codes: 0 sucesso (captured/flow_validated/diagnostic_clean);
1 fluxo falhou (assinatura fatal, milestone/endpoint obrigatório ausente,
fallback em fluxo validado) ou captura pedida falhou; 2 ambiente/uso
(adb/dispositivo/servidor/token ausente); 3 inconclusivo (sem captura).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PACKAGE = "com.bethsoft.ubu"
FIXTURES_CLIENT_DIR = ROOT / "tests" / "fixtures" / "protocol" / "client"

# (padrão, classificação, descrição). fatal = falha do fluxo; warning = vive no
# log de um boot são e registrável, não derruba a validação.
SIGNATURES: list[tuple[str, str, str]] = [
    (r"Malformed response payload", "fatal", "parse do cliente rejeitou um payload do servidor"),
    (r"Failed to launch after \d+ attempts", "fatal", "boot abortou após 3 tentativas (Relaunch)"),
    (r"CRC Mismatch", "fatal", "bundle Addressables alterado sem zero_catalog_crc"),
    (r"RemoteProviderException", "fatal", "load de cena morreu (provider Addressables)"),
    (r"FATAL EXCEPTION", "fatal", "crash nativo/gerenciado"),
    (r"signal \d+ \(SIGSEGV\)", "fatal", "segfault nativo"),
    # Medido no rig local 2026-08-19 (fase4-restart1, logcat 22:57:07.281): o
    # Newtonsoft do cliente recusa o token de sessão quando `aud`/`audience`
    # chega como string — o DTO GameSessionToken tipa audience como String[].
    # UpdateSessionToken morre, o boot termina em NETWORK ERROR e a execução
    # já está condenada; classificar como warning esconderia a falha real.
    (r"Could not cast or convert from System\.String to System\.String\[\]", "fatal",
     "cliente recusou o token de sessão: aud/audience veio string onde o DTO tipa String[]"),
    (r"Session token is not a well formed JWT", "warning", "token opaco; warning comprovadamente não fatal (DEAD-ENDS #9)"),
    (r"Cant find corresponding data tool data", "warning", "game-data sem definição da ability citada"),
]

# Assinaturas que condenam a execução na hora: continuar observando não muda o
# veredito e queima a janela inteira (foram 4 minutos por tentativa em
# fase4-restart1/2/3). Comparadas pelo padrão, não pela mensagem.
EARLY_STOP_SIGNATURES = frozenset({
    r"Failed to launch after \d+ attempts",
    r"Could not cast or convert from System\.String to System\.String\[\]",
})

# Perfis de fluxo: milestones mínimos que a sequência temporal da execução tem
# que conter. Conservador de propósito — só exige o que já foi comprovado no
# emulador (RELATORIO-STATUS 2026-08-16: bootstrap, menu com eventos, 1-1).
FLOW_PROFILES: dict[str, dict] = {
    "boot": {
        "description": "bootstrap: autenticação (register ou login-device) + user-data",
        "milestones": [
            {"any_of": ["game/auth/register", "game/auth/login-device"], "label": "autenticação (register|login-device)"},
            {"endpoint": "game/player/user-data"},
        ],
    },
    "menu": {
        "extends": "boot",
        "description": "boot + agenda de eventos carregada (menu)",
        "milestones": [
            {"endpoint": "game/events/get-schedule"},
        ],
    },
    "chapter": {
        "extends": "menu",
        "description": "menu + início de partida de capítulo",
        "milestones": [
            {"endpoint": "game/chapters/start"},
        ],
    },
}

# ---------------------------------------------------------------------------
# Sanitização — o que sai daqui vai para arquivo versionado. Preserva chaves,
# tipos, arrays, omissões e nullabilidade do wire; só o valor sensível muda.
# ---------------------------------------------------------------------------

# chave do wire -> placeholder na fixture (formato dos server-replay).
SECRET_KEYS = {
    "token": "<token>",
    "password": "<password>",
    "recovery_code": "<recovery-code>",
    "push_token": "<push-token>",
    "device_id": "<device-id>",
    "authorization": "<token>",
    "ubu_sid": "<ubu-sid>",
    "ubu_nonce": "<ubu-nonce>",
    "session_ticket": "<token>",
    # puuid não é credencial: é o identificador ESTÁVEL da conta no wire. Não
    # dá acesso a nada sozinho, mas correlaciona execuções e sobrevive a
    # restart — fixture versionada não precisa carregar o valor. A chave e o
    # tipo continuam no arquivo; só o valor vira placeholder.
    "puuid": "<puuid>",
}
# voláteis por execução (formato documentado no README das fixtures).
VOLATILE_PLACEHOLDERS = {"uts": "<uts>"}
ZEROED_KEYS = {"account_age", "last_login"}

JWT_RE = re.compile(r"^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*$")
URL_RE = re.compile(r"^(https?)://[^/\s]+(/.*)?$")


def _redigivel(item) -> bool:
    """Só STRING não vazia é credencial.

    Medido em 2026-08-19: `device_id` é a credencial (UUID string) em
    game/auth/*, mas é o id NUMÉRICO da linha de dispositivo em
    game/devices/describe e game/devices/unregister. Trocar o inteiro por
    "<device-id>" mudaria o TIPO do wire na fixture — e tipo errado é
    exatamente o que derruba o parse do cliente (DEAD-ENDS #3).
    """
    return isinstance(item, str) and item != ""


def sanitize_value(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in SECRET_KEYS and _redigivel(item):
                out[key] = SECRET_KEYS[key]
            elif key in VOLATILE_PLACEHOLDERS and isinstance(item, str) and item:
                out[key] = VOLATILE_PLACEHOLDERS[key]
            elif key in ZEROED_KEYS and isinstance(item, (int, float)):
                out[key] = 0
            else:
                out[key] = sanitize_value(item)
        return out
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, str):
        if JWT_RE.match(value):
            return "<token>"
        if value.startswith("Bearer ") and len(value) > 7:
            return "Bearer <token>"
        match = URL_RE.match(value)
        if match:
            # host privado ou público: a fixture não carrega infra — só o path.
            return "<base>" + (match.group(2) or "")
        return value
    return value


def parse_json_or_none(raw):
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def row_endpoint(row: dict) -> str:
    return str(row.get("path", "")).lstrip("/")


def build_fixture(row: dict, captured_at: str) -> dict | None:
    """Fixture provenance=client a partir de UMA linha do request_log.

    Sem response pareado na linha, não há fixture: response_observed não pode
    ser derivado de logcat limpo.
    """
    route = row_endpoint(row)
    if not route.startswith("game/"):
        return None
    request_body = parse_json_or_none(row.get("body_json"))
    response_body = parse_json_or_none(row.get("response_json"))
    if response_body is None:
        return None
    status = row.get("status")
    if not isinstance(status, int):
        return None
    return {
        "endpoint": route,
        "provenance": "client",
        "captured_at": captured_at,
        "sanitized": True,
        "source": "client_harness.py (request_log pareado do servidor)",
        "request": {
            "method": row.get("method") or "POST",
            "path": "/" + route,
            # headers não são persistidos pelo servidor — e não faz falta:
            # guard é igual para toda rota /game/* (skill revival-server).
            "body": sanitize_value(request_body if request_body is not None else {}),
        },
        "response": {
            "status": status,
            "code": row.get("code"),
            "body": sanitize_value(response_body),
        },
    }


def fixture_path_for(route: str) -> Path:
    module = route.split("/")[1] if route.count("/") >= 1 else "raiz"
    name = route.replace("/", "__")
    return FIXTURES_CLIENT_DIR / module / f"{name}.json"


def write_client_fixtures(rows: list[dict], captured_at: str) -> list[str]:
    """Uma fixture por endpoint observado (última chamada com response)."""
    latest: dict[str, dict] = {}
    for row in rows:
        route = row_endpoint(row)
        if not route.startswith("game/"):
            continue
        if parse_json_or_none(row.get("response_json")) is None:
            continue
        latest[route] = row
    written: list[str] = []
    for route, row in sorted(latest.items()):
        fixture = build_fixture(row, captured_at)
        if fixture is None:
            continue
        target = fixture_path_for(route)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Sobrescreve capturas client anteriores (mais frescas) e substitui
        # server-replay por evidência real — o gerador prioriza provenance
        # client ao derivar os gates.
        target.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            written.append(str(target.relative_to(ROOT)).replace("\\", "/"))
        except ValueError:  # destino fora do repo (testes)
            written.append(str(target))
    return written


# ---------------------------------------------------------------------------
# Captura incremental e fluxos
# ---------------------------------------------------------------------------

def http_get_json(url: str, token: str | None = None) -> dict | None:
    request = urllib.request.Request(url)
    if token:
        request.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - diagnóstico no relatório
        return {"error": str(exc)}


def fetch_baseline(server: str, token: str | None) -> dict:
    """Cursor do request_log + snapshot de fallbacks ANTES de abrir o app."""
    baseline: dict = {"requests_cursor": None, "research": None}
    if token:
        state = http_get_json(f"{server}/revival/requests?limit=1", token)
        if isinstance(state, dict) and not state.get("error"):
            baseline["requests_cursor"] = state.get("last_id")
    baseline["research"] = http_get_json(f"{server}/revival/research")
    return baseline


def fetch_execution_delta(server: str, token: str | None, cursor) -> tuple[list[dict], dict | None]:
    if not token or not isinstance(cursor, int):
        return [], None
    state = http_get_json(f"{server}/revival/requests?since_id={cursor}&limit=1000", token)
    if not isinstance(state, dict) or state.get("error"):
        return [], state or {"error": "unknown"}
    return state.get("requests", []) or [], state


# ---------------------------------------------------------------------------
# Prova de ATERRISSAGEM — onde o tráfego do cliente realmente caiu.
#
# Medido em 2026-08-19 (work/audit-opus/FASE-0-DIVERGENCIAS.md): as sete
# execuções do rig declararam o MESMO --server, inclusive a única boa. Comparar
# o host do APK com o host de --server, sozinho, não separou o boot bom dos
# ruins. E `client_version`/`api_version` eram idênticos entre local e VPS.
#
# O que separa de fato é a correlação abaixo. `--expected-game-host` continua
# útil, mas é guard SECUNDÁRIO: prova declaração, não aterrissagem.
# ---------------------------------------------------------------------------

def instance_fingerprint(health: dict | None) -> dict:
    """Identidade publicável da instância que respondeu (/revival/health).

    `identified=False` significa servidor antigo, sem server/src/instance.js —
    é um FATO sobre a instância (drift de build), não um erro do harness.
    """
    if not isinstance(health, dict):
        return {"identified": False, "reason": "health indisponível"}
    campos = {k: health.get(k) for k in
              ("instance_id", "boot_id", "build_id", "build_id_source", "environment")
              if health.get(k) is not None}
    if not campos:
        return {"identified": False,
                "reason": "health sem identificador de instância (build anterior a instance.js)"}
    return {"identified": True, **campos}


def landing_evidence(*, apk_host: str | None, expected_host: str | None,
                     cursor_before, cursor_after, requests_in_window: int,
                     launched: bool, window_seconds: float,
                     instance: dict) -> dict:
    """Correlaciona APK, instância, cursor e janela — sem concluir causa.

    Regra dura: cursor parado prova SÓ "nenhum tráfego observado nesta
    instância durante esta janela". Não prova rig quebrado, nem servidor
    público antigo, nem sessão persistida. Quem decide entre essas hipóteses é
    a próxima experiência discriminante, não este campo.
    """
    avancou = (isinstance(cursor_before, int) and isinstance(cursor_after, int)
               and cursor_after > cursor_before)
    host_declarado_bate = None
    if apk_host and expected_host:
        host_declarado_bate = apk_host.lower() == expected_host.lower()
    return {
        "apk_host": apk_host,
        "expected_game_host": expected_host,
        "declared_host_matches": host_declarado_bate,
        "instance": instance,
        "cursor_before": cursor_before,
        "cursor_after": cursor_after,
        "cursor_advanced": avancou,
        "requests_in_window": requests_in_window,
        "network_expected": bool(launched),
        "window_seconds": round(window_seconds, 1),
        # O que este conjunto PROVA, literalmente. Nada além disso.
        "proves": (
            "tráfego do cliente aterrissou nesta instância durante a janela"
            if avancou and requests_in_window > 0 else
            "nenhum tráfego observado nesta instância durante esta janela"
        ),
        "does_not_prove": [
            "rig de interceptação quebrado",
            "tráfego atendido por outra instância",
            "sessão persistida sem chamada de rede",
        ] if not avancou else [],
    }


def apk_proof(report_path: Path | None) -> dict:
    """Host PROVADO dentro do APK, lido do relatório de verify_patched_apk.py.

    Um relatório com `verified=false` (ou com host oficial ainda presente) não
    vira prova: o campo `proven` fica falso e o motivo é registrado.
    """
    if report_path is None:
        return {"proven": False, "reason": "sem --apk-verify-report"}
    try:
        data = json.loads(Path(report_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"proven": False, "reason": f"relatório ilegível: {exc}"}
    host = data.get("server_host")
    oficiais = data.get("official_occurrences")
    if not data.get("verified") or not host:
        return {"proven": False, "reason": "relatório não declara verified=true", "host": host}
    if isinstance(oficiais, int) and oficiais > 0:
        return {"proven": False, "reason": f"{oficiais} ocorrência(s) do host oficial no APK", "host": host}
    return {
        "proven": True,
        "host": host,
        "apk_sha256": data.get("sha256"),
        "target_occurrences": data.get("target_occurrences"),
        "official_occurrences": oficiais,
    }


def landing_verdict(landing: dict) -> str | None:
    """`no_observed_traffic` quando a ação deveria gerar rede e nada apareceu."""
    if not landing.get("network_expected"):
        return None
    if landing.get("cursor_before") is None or landing.get("cursor_after") is None:
        return None
    if landing.get("cursor_advanced"):
        return None
    return "no_observed_traffic"


def research_snapshot(state: dict | None) -> tuple[dict[str, int], int]:
    if not isinstance(state, dict) or state.get("error"):
        return {}, -1
    counts = {str(e.get("path", "")).lstrip("/"): int(e.get("count", 0))
              for e in state.get("fallback_endpoints", [])}
    total = state.get("fallback_total")
    if not isinstance(total, int):
        total = sum(counts.values())
    return counts, total


def research_delta(before: dict | None, after: dict | None) -> dict:
    """Fallbacks atribuíveis a ESTA execução (delta), não ao histórico do boot.

    `reset=True` significa que o servidor reiniciou durante a janela (contagem
    zerou): o delta não é confiável e a execução não pode validar fallback.
    """
    before_counts, before_total = research_snapshot(before)
    after_counts, after_total = research_snapshot(after)
    if before_total < 0 or after_total < 0:
        return {"delta": {}, "total": 0, "reset": False, "unavailable": True}
    delta: dict[str, int] = {}
    for path, count in after_counts.items():
        diff = count - before_counts.get(path, 0)
        if diff > 0:
            delta[path] = diff
    return {"delta": delta, "total": after_total - before_total,
            "reset": after_total < before_total, "unavailable": False}


def resolve_profile(name: str) -> dict:
    profile = FLOW_PROFILES.get(name)
    if not profile:
        return {"milestones": [], "description": name}
    milestones = list(profile.get("milestones", []))
    parent = profile.get("extends")
    seen = {name}
    while parent and parent in FLOW_PROFILES and parent not in seen:
        seen.add(parent)
        milestones = list(FLOW_PROFILES[parent].get("milestones", [])) + milestones
        parent = FLOW_PROFILES[parent].get("extends")
    return {"milestones": milestones, "description": profile.get("description", name)}


def evaluate_milestones(milestones: list[dict], observed: set[str]) -> list[dict]:
    status = []
    for milestone in milestones:
        if "any_of" in milestone:
            hit = next((route for route in milestone["any_of"] if route in observed), None)
            status.append({"label": milestone.get("label") or "|".join(milestone["any_of"]),
                           "matched": hit is not None, "observed": hit})
        else:
            route = milestone["endpoint"]
            status.append({"label": milestone.get("label") or route,
                           "matched": route in observed, "observed": route if route in observed else None})
    return status


def summarize_sequence(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Sequência temporal real (ordem por id) + resumo por contagem separado."""
    sequence = []
    for row in sorted(rows, key=lambda r: r.get("id") or 0):
        route = row_endpoint(row)
        if not route.startswith("game/"):
            continue
        sequence.append({
            "id": row.get("id"),
            "endpoint": route,
            "status": row.get("status"),
            "code": row.get("code"),
            "user_id": row.get("user_id"),
            "note": row.get("note"),
            "has_response": parse_json_or_none(row.get("response_json")) is not None,
        })
    counts: dict[str, int] = {}
    for entry in sequence:
        counts[entry["endpoint"]] = counts.get(entry["endpoint"], 0) + 1
    summary = [{"endpoint": route, "calls": count} for route, count in sorted(counts.items())]
    return sequence, summary


# ---------------------------------------------------------------------------
# Registro: o gerador é a única escrita autorizada
# ---------------------------------------------------------------------------

def registry_update_command(flow_validated: bool, fallback_routes: list[str],
                            milestone_routes: list[str], note: str) -> list[str] | None:
    """Argumentos para generate_endpoint_matrix.py; None = nada a declarar.

    Nunca chamado para veredito inconclusive/failed — execução sem prova não
    muta o registro.
    """
    command: list[str] = []
    for route in sorted(set(fallback_routes)):
        command += ["--set", f"{route}=uses_fallback=true"]
    if flow_validated:
        for route in sorted(set(milestone_routes)):
            command += ["--set", f"{route}=client_validated=true",
                        "--note", f"{route}={note}"]
    return command or None


def decide_verdict(*, has_fatal: bool, capture_error: bool, missing_milestones: list[str],
                   required_missing: list[str], validated_fallbacks: list[str],
                   capture_requested: bool, flow: str | None, diagnostic: bool,
                   landing: dict | None = None) -> tuple[str, bool]:
    """Veredito sem ambiguidade (ver docstring do módulo) + flow_validated.

    Regra central: sem captura de endpoints não existe validação — no máximo
    diagnóstico de logcat declarado explicitamente.

    `no_observed_traffic` fica ACIMA dos gates de milestone porque é mais
    informativo: quando a instância observada não viu nada, dizer "milestone
    ausente" descreve o sintoma e esconde que a própria observação não
    aconteceu. Fatal continua vencendo — um crash é fato do cliente, e o
    logcat é evidência independente do cursor.
    """
    if has_fatal:
        return "failed", False
    if capture_error:
        return "inconclusive", False
    if landing and landing_verdict(landing) == "no_observed_traffic":
        return "no_observed_traffic", False
    if missing_milestones or required_missing or validated_fallbacks:
        return "failed", False
    if capture_requested:
        validated = bool(flow)
        return ("flow_validated" if validated else "captured"), validated
    if diagnostic:
        return "diagnostic_clean", False
    return "inconclusive", False


def should_update_registry(verdict: str) -> bool:
    """O registro só muda com prova desta execução; inconclusive/failed não mutam."""
    return verdict in ("captured", "flow_validated")


# ---------------------------------------------------------------------------
# ADB
# ---------------------------------------------------------------------------

def find_adb() -> str | None:
    direct = shutil.which("adb")
    if direct:
        return direct
    candidates = [
        Path.home() / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools" / "adb.exe",
        Path.home() / "Android" / "Sdk" / "platform-tools" / "adb.exe",
        Path("C:/Android/Sdk/platform-tools/adb.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def adb(adb_path: str, serial: str | None, *args: str, timeout: int = 60) -> tuple[int, str]:
    command = [adb_path]
    if serial:
        command += ["-s", serial]
    command += list(args)
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout)
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, ""


def list_devices(adb_path: str) -> list[str]:
    code, output = adb(adb_path, None, "devices")
    if code != 0:
        return []
    serials = []
    for line in output.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "device":
            serials.append(fields[0])
    return serials


def scan_logcat(text: str) -> list[dict]:
    findings: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for pattern, severity, description in SIGNATURES:
        for match in re.finditer(pattern, text):
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            line = text[line_start:line_end if line_end != -1 else None].strip()
            key = (pattern, hash(line))
            if key in seen:
                continue
            seen.add(key)
            findings.append({"signature": pattern, "severity": severity,
                             "description": description, "line": line[:400]})
    return findings


def early_stop_hits(text: str) -> list[dict]:
    """Achados fatais que autorizam cortar a janela de observação agora."""
    return [f for f in scan_logcat(text)
            if f["severity"] == "fatal" and f["signature"] in EARLY_STOP_SIGNATURES]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--server", required=True, help="URL base do Revival Server")
    parser.add_argument("--apk", type=Path, help="APK a instalar antes do fluxo")
    parser.add_argument("--package", default=PACKAGE)
    parser.add_argument("--serial", help="serial adb do dispositivo/emulador")
    parser.add_argument("--duration", type=int, default=180, help="segundos de observação (default 180)")
    parser.add_argument("--admin-token", help="Bearer de admin para a captura (ou env REVIVAL_ADMIN_TOKEN)")
    parser.add_argument("--flow", choices=sorted(FLOW_PROFILES),
                        help="perfil de milestones mínimos (boot/menu/chapter)")
    parser.add_argument("--require-endpoint", action="append", default=[], metavar="ROTA",
                        help="endpoint que precisa aparecer no delta desta execução (repetível)")
    parser.add_argument("--capture-fixtures", action="store_true",
                        help="grava fixtures provenance=client para cada endpoint observado")
    parser.add_argument("--update-registry", action="store_true",
                        help="escreve fixtures e deriva os gates via generate_endpoint_matrix.py")
    parser.add_argument("--diagnostic", action="store_true",
                        help="declara execução APENAS diagnóstico de logcat (sem captura)")
    parser.add_argument("--no-launch", action="store_true", help="não (re)abre o app; só observa")
    parser.add_argument("--report", type=Path, help="caminho do relatório JSON (default work/harness/<ts>.json)")
    # Aterrissagem. --expected-game-host é guard SECUNDÁRIO (prova declaração);
    # --apk-verify-report traz o host PROVADO dentro do APK, medido por
    # verify_patched_apk.py, e o SHA-256 do arquivo que gerou a prova.
    parser.add_argument("--expected-game-host",
                        help="host que o APK deve chamar (guard secundário; não prova aterrissagem)")
    parser.add_argument("--apk-verify-report", type=Path,
                        help="JSON de scripts/verify_patched_apk.py do APK realmente instalado")
    args = parser.parse_args(argv)

    token = args.admin_token or os.environ.get("REVIVAL_ADMIN_TOKEN", "")
    capture_requested = bool(args.capture_fixtures or args.update_registry or args.flow or args.require_endpoint)

    # Gate de credencial ANTES de qualquer efeito colateral: captura de
    # evidência sem como ler o servidor é erro de uso, não diagnóstico.
    if capture_requested and not token:
        print("ERRO: --capture-fixtures/--update-registry/--flow/--require-endpoint exigem "
              "--admin-token (ou env REVIVAL_ADMIN_TOKEN) para ler a captura do servidor.", file=sys.stderr)
        return 2

    started = datetime.now(timezone.utc)
    report: dict = {
        "harness": "client_harness.py",
        "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "server": args.server.rstrip("/"),
        "package": args.package,
        "duration_planned": args.duration,
        "flow": args.flow,
        "capture_requested": capture_requested,
    }

    adb_path = find_adb()
    if not adb_path:
        print("ERRO: adb não encontrado no PATH nem no Android SDK padrão.", file=sys.stderr)
        return 2
    report["adb"] = adb_path

    devices = list_devices(adb_path)
    if not devices:
        print("ERRO: nenhum dispositivo adb conectado ('adb devices' vazio).", file=sys.stderr)
        return 2
    serial = args.serial or devices[0]
    if args.serial and args.serial not in devices:
        print(f"ERRO: serial {args.serial} não está conectado. Disponíveis: {devices}", file=sys.stderr)
        return 2
    report["device"] = serial

    base = args.server.rstrip("/")
    health = http_get_json(f"{base}/revival/health")
    if not health or not health.get("ok"):
        print(f"ERRO: servidor {base} não respondeu health ok: {health}", file=sys.stderr)
        return 2
    report["health"] = health
    print(f"[ambiente] adb={serial} · servidor={base} (client {health.get('client_version')})")

    # Baseline ANTES de qualquer movimento no app — requests/fallbacks antigos
    # pertencem a execuções anteriores e não podem contaminar esta.
    baseline = fetch_baseline(base, token or None)
    cursor = baseline["requests_cursor"]
    research_before = baseline["research"]
    report["baseline_requests_cursor"] = cursor
    if capture_requested:
        if not isinstance(cursor, int):
            print("ERRO: sem cursor do request_log a captura incremental não é possível.", file=sys.stderr)
            return 1

    if args.apk:
        print(f"[instala] {args.apk}")
        code, output = adb(adb_path, serial, "install", "-r", str(args.apk), timeout=600)
        if code != 0:
            print(f"ERRO: falha ao instalar APK: {output[-500:]}", file=sys.stderr)
            return 2
        report["installed_apk"] = str(args.apk)

    adb(adb_path, serial, "logcat", "-c")

    if not args.no_launch:
        code, _ = adb(adb_path, serial, "shell", "monkey", "-p", args.package,
                      "-c", "android.intent.category.LAUNCHER", "1")
        if code != 0:
            print(f"ERRO: não consegui abrir {args.package} (instalado?)", file=sys.stderr)
            return 2
        report["launched"] = True

    fatal_seen = False
    deadline = time.monotonic() + args.duration
    while time.monotonic() < deadline:
        time.sleep(10)
        code, tail = adb(adb_path, serial, "logcat", "-d", "-t", "400")
        if code == 0:
            hits = early_stop_hits(tail)
            if hits:
                fatal_seen = True
                print(f"[corta] {hits[0]['description']}")
                break

    code, logcat = adb(adb_path, serial, "logcat", "-d", timeout=120)
    logcat = logcat if code == 0 else ""
    findings = scan_logcat(logcat)
    fatal = [f for f in findings if f["severity"] == "fatal"]
    warnings = [f for f in findings if f["severity"] == "warning"]
    report["signatures_fatal"] = fatal
    report["signatures_warning_count"] = len(warnings)

    report_dir = args.report or (ROOT / "work" / "harness")
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%d-%H%M%S")
    (report_dir / f"logcat-{stamp}.txt").write_text(logcat, encoding="utf-8", errors="replace")

    research_after = http_get_json(f"{base}/revival/research")
    fb = research_delta(research_before, research_after)
    fallback_delta_paths = sorted(fb["delta"])
    report["fallback_delta"] = fb
    report["fallback_delta_endpoints"] = fallback_delta_paths

    # ---- delta da execução: só requests com id > cursor, ordem crescente ----
    rows, requests_state = fetch_execution_delta(base, token or None, cursor)
    capture_error = bool(capture_requested and (not rows and (requests_state or {}).get("error")))
    sequence, counts_summary = summarize_sequence(rows)
    observed_routes = {entry["endpoint"] for entry in sequence}
    report["endpoint_sequence"] = sequence
    report["endpoint_counts"] = counts_summary
    report["endpoints_called"] = len(observed_routes)
    report["requests_captured"] = len(sequence)
    report["capture_error"] = capture_error

    # ---- gates de fluxo ----
    milestones_status: list[dict] = []
    missing_milestones: list[str] = []
    profile_milestone_routes: list[str] = []
    if args.flow:
        profile = resolve_profile(args.flow)
        milestones_status = evaluate_milestones(profile["milestones"], observed_routes)
        missing_milestones = [m["label"] for m in milestones_status if not m["matched"]]
        for milestone in profile["milestones"]:
            if "any_of" in milestone:
                profile_milestone_routes += [r for r in milestone["any_of"] if r in observed_routes]
            elif milestone["endpoint"] in observed_routes:
                profile_milestone_routes.append(milestone["endpoint"])
    report["milestones"] = milestones_status
    report["milestones_missing"] = missing_milestones

    required_missing = [route for route in args.require_endpoint if route not in observed_routes]
    report["required_endpoints"] = args.require_endpoint
    report["required_endpoints_missing"] = required_missing

    # fallback em rota já validada = gate quebrado (DEAD-ENDS #11)
    validated_fallbacks: list[str] = []
    compat_path = ROOT / "compatibility.json"
    if compat_path.is_file():
        compat = json.loads(compat_path.read_text(encoding="utf-8"))
        validated = {r for r, d in compat.get("endpoints", {}).items() if d.get("client_validated")}
        validated_fallbacks = sorted(p for p in fallback_delta_paths if p in validated)
    report["validated_flow_used_fallback"] = validated_fallbacks

    # ---- prova de aterrissagem (onde o tráfego caiu de fato) ----
    cursor_after = (requests_state or {}).get("last_id") if isinstance(requests_state, dict) else None
    if cursor_after is None and isinstance(cursor, int):
        cursor_after = cursor + len(rows)
    apk = apk_proof(args.apk_verify_report)
    report["apk_proof"] = apk
    landing = landing_evidence(
        apk_host=apk.get("host") if apk.get("proven") else None,
        expected_host=args.expected_game_host,
        cursor_before=cursor,
        cursor_after=cursor_after,
        requests_in_window=len(rows),
        launched=bool(report.get("launched")),
        window_seconds=(datetime.now(timezone.utc) - started).total_seconds(),
        instance=instance_fingerprint(health),
    )
    landing["apk_proof"] = apk
    report["landing"] = landing

    # ---- veredito sem ambiguidade ----
    verdict, flow_validated = decide_verdict(
        has_fatal=bool(fatal_seen or fatal),
        capture_error=capture_error,
        missing_milestones=missing_milestones,
        required_missing=required_missing,
        validated_fallbacks=validated_fallbacks,
        capture_requested=capture_requested,
        flow=args.flow,
        diagnostic=args.diagnostic,
        landing=landing,
    )
    report["verdict"] = verdict
    report["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ---- fixtures client (sanitizadas) ----
    report["fixtures_client_written"] = []
    if should_update_registry(verdict) and (args.capture_fixtures or args.update_registry):
        report["fixtures_client_written"] = write_client_fixtures(rows, report["finished_at"])
        print(f"[fixtures] {len(report['fixtures_client_written'])} provenance=client sanitizadas")

    # ---- registro via gerador (nunca edição direta) ----
    if args.update_registry:
        if should_update_registry(verdict):
            fallback_routes_in_registry = []
            if compat_path.is_file():
                compat = json.loads(compat_path.read_text(encoding="utf-8"))
                known = set(compat.get("endpoints", {}))
                fallback_routes_in_registry = [p for p in fallback_delta_paths if p in known]
            note = f"client_harness {report['finished_at']} fluxo {args.flow or 'captured'} contra {base}"
            command = registry_update_command(flow_validated, fallback_routes_in_registry,
                                              profile_milestone_routes, note)
            generator = [sys.executable, str(ROOT / "scripts" / "generate_endpoint_matrix.py")]
            if command:
                regen = subprocess.run(generator + command, capture_output=True, text=True,
                                       encoding="utf-8", errors="replace")
                if regen.returncode != 0:
                    print(f"[registro] falha ao declarar evidência: {regen.stdout} {regen.stderr}", file=sys.stderr)
                    return 1
            else:
                regen = subprocess.run(generator, capture_output=True, text=True,
                                       encoding="utf-8", errors="replace")
                if regen.returncode != 0:
                    print(f"[registro] falha ao regenerar matriz: {regen.stdout} {regen.stderr}", file=sys.stderr)
                    return 1
            print("[registro] gates derivados pelo gerador a partir das fixtures")
        else:
            print(f"[registro] veredito {verdict!r} não muta compatibility.json — nada declarado")

    report_file = report_dir / f"harness-{stamp}.json"
    report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print()
    print(f"logcat:   {report_dir / f'logcat-{stamp}.txt'}")
    print(f"relatório: {report_file}")
    print(f"veredito: {verdict} · fatais: {len(fatal)} · warnings: {len(warnings)}")
    print(f"requests desta execução: {len(sequence)} · endpoints distintos: {len(observed_routes)}")
    if fallback_delta_paths:
        print(f"fallbacks no delta: {fb['total']} -> {', '.join(fallback_delta_paths)}")
    if fb.get("reset"):
        print("AVISO: servidor reiniciou durante a janela — delta de fallback não confiável")
    if missing_milestones:
        print(f"GATE: milestones ausentes do fluxo {args.flow}: {', '.join(missing_milestones)}")
    if required_missing:
        print(f"GATE: --require-endpoint ausente no delta: {', '.join(required_missing)}")
    if validated_fallbacks:
        print(f"ERRO DE GATE: fluxo validado usando fallback: {', '.join(validated_fallbacks)}")
    for finding in fatal[:10]:
        print(f"  [fatal] {finding['description']}: {finding['line'][:160]}")

    if verdict == "no_observed_traffic":
        print("A instância observada NÃO registrou tráfego nesta janela, embora o app "
              "tenha sido aberto.")
        print(f"  APK provado: {landing['apk_proof'].get('host') or 'não provado'} · "
              f"instância: {landing['instance'].get('instance_id', '?')}"
              f"/{landing['instance'].get('build_id', '?')} · "
              f"cursor {landing['cursor_before']} -> {landing['cursor_after']}")
        print("  Isto NÃO decide entre: rig quebrado, outra instância atendendo, ou "
              "sessão persistida. Correlacione logcat + build id antes de concluir.")
        return 3
    if verdict == "failed":
        return 1
    if verdict == "inconclusive":
        print("Sem captura de endpoints esta execução não prova endpoints — "
              "use --admin-token para capturar ou --diagnostic para declarar modo logcat.")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
