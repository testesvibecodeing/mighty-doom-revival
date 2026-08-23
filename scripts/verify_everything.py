#!/usr/bin/env python3
"""Gate único de conclusão do projeto — nada está "pronto" sem isto passar.

Camadas (todas obrigatórias salvo as marcadas opcionais):
  1. Suíte do servidor (cd server && npm test) — inclui o smoke com o gate de
     fallback do RESEARCH_MODE.
  2. Regressões Python: TODA a suíte autodescoberta pelo run_tests.py
     (scripts/test_*.py + tests/**/test_*.py) — sem lista manual paralela.
  3. Sincronização do registro: generate_endpoint_matrix.py --check.
  4. Coerência do registro (compatibility.json):
       - endpoint com client_validated=true NÃO pode ter uses_fallback=true
         (fluxo validado não pode viver de resposta vazia de pesquisa);
       - endpoint com regression_test=true tem que estar implementado;
       - request/response_observed=true exige provenance de evidência aceita
         (client-fixture | legacy-observation | client-manual);
       - response_observed sem request_observed é combinação impossível;
       - fixture provenance=client tem que ter sanitized=true;
       - fixture cujo endpoint diverge da rota do próprio arquivo reprova;
       - nenhum material sensível (JWT, Bearer, recovery code, segredo em
         texto claro, host privado) em fixture versionada.
  5. (opcional --server URL) servidor vivo: /revival/health ok e, com
     --strict-research, /revival/research com fallback_total == 0.
  6. (opcional --apk FILE) verify_patched_apk.py no APK final.

Uso:
  python scripts/verify_everything.py
  python scripts/verify_everything.py --server https://host --strict-research
  python scripts/verify_everything.py --apk output/mighty-doom-revival.apk --server https://host

Exit codes: 0 tudo passou; 1 alguma camada falhou; 2 uso inválido.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# A suíte Python tem UMA fonte de verdade: a autodescoberta do run_tests.py
# (scripts/test_*.py + tests/**/test_*.py). Manter uma segunda lista aqui já
# deixou tests/test_client_harness.py e tests/test_green_gate.py fora do gate
# enquanto o run_tests.py os executava — o gate ficava verde por omissão.
sys.path.insert(0, str(ROOT))
from run_tests import descobrir as descobrir_testes_python  # noqa: E402
sys.path.insert(0, str(ROOT / "scripts"))
# "DoD completo" tem UMA fonte de verdade: generate_endpoint_matrix.endpoint_done().
# Uma fórmula própria aqui já divergiu da real (contava rota client_authoritative
# sem prova real como "done" porque `is not False` aceita None de qualquer gate,
# sem saber que None ali é marcador terminal, não "não aplicável" genérico).
from generate_endpoint_matrix import endpoint_done, endpoint_terminal  # noqa: E402

# Consoles Windows ficam em cp1252; a saída destes scripts é UTF-8 (mesclas
# de português e emoji do estado dos testes) — nunca deixe o print derrubar o gate.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")



class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passed = 0

    def ok(self, label: str) -> None:
        self.passed += 1
        print(f"  [OK] {label}")

    def fail(self, label: str, detail: str = "") -> None:
        self.failures.append(f"{label}: {detail}" if detail else label)
        print(f"  [FALHOU] {label}" + (f" — {detail}" if detail else ""))

    def section(self, title: str) -> None:
        print(f"\n== {title} ==")


def run(command: list[str], cwd: Path | None = None) -> tuple[int, str]:
    # No Windows npm/node vivem como .cmd — resolve pelo PATH antes de
    # CreateProcess, que não faz lookup de extensão.
    resolved = [shutil.which(command[0]) or command[0], *command[1:]]
    result = subprocess.run(
        resolved, cwd=cwd or ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


ACCEPTED_OBSERVED_PROVENANCE = ("client-fixture", "legacy-observation", "client-manual")

# Padrões que nunca podem aparecer em fixture versionada (sanitização falhou).
SECRET_IN_FIXTURE_RES = [
    (re.compile(r"eyJ[A-Za-z0-9_-]{20,}\."), "JWT em texto claro"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._-]{8,}"), "header Authorization com valor"),
    (re.compile(r"RV-[0-9A-F]{12}"), "código de recuperação em texto claro"),
    # puuid entra aqui como identificador estável de conta (não é credencial):
    # a fixture guarda a chave e o tipo, nunca o valor.
    (re.compile(r"\"(token|password|recovery_code|push_token|device_id|ubu_sid|ubu_nonce|puuid)\"\s*:\s*\"(?!<)[^\"]+\""),
     "chave sensível com valor não sanitizado"),
    (re.compile(r"https?://(localhost|127\.0\.0\.1|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)"),
     "host privado/loopback em fixture"),
]


def check_python_tests(report: Report, arquivos: list[Path] | None = None) -> None:
    """Camada 2: roda TODOS os test_*.py que o run_tests.py descobre.

    `arquivos` existe só para a regressão do gate (injeta um arquivo sintético);
    em produção é sempre a descoberta real — nunca uma lista escrita à mão.
    """
    alvos = descobrir_testes_python() if arquivos is None else list(arquivos)
    if not alvos:
        report.fail("descoberta da suíte Python", "nenhum test_*.py encontrado")
        return
    for path in alvos:
        path = Path(path)
        try:
            rotulo = path.relative_to(ROOT).as_posix()
        except ValueError:
            rotulo = path.as_posix()
        if not path.is_file():
            report.fail(rotulo, "arquivo de teste ausente")
            continue
        code, output = run([sys.executable, str(path)])
        if code == 0:
            report.ok(rotulo)
        else:
            report.fail(rotulo, f"exit {code}\n" + "\n".join(output.strip().splitlines()[-8:]))


def check_fixtures(report: Report) -> None:
    fixtures_dir = ROOT / "tests" / "fixtures" / "protocol"
    if not fixtures_dir.is_dir():
        report.ok("nenhuma fixture de protocolo")
        return
    problems: list[str] = []
    client_count = 0
    for path in sorted(fixtures_dir.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            problems.append(f"{path.name}: JSON inválido ({exc})")
            continue
        endpoint = data.get("endpoint")
        if not (isinstance(endpoint, str) and endpoint.startswith("game/")):
            continue
        raw = path.read_text(encoding="utf-8")
        for pattern, label in SECRET_IN_FIXTURE_RES:
            if pattern.search(raw):
                problems.append(f"{path.name}: {label}")
        # Convenção de nome: game__auth__login-device.json -> game/auth/login-device
        expected_route = path.stem.replace("__", "/")
        if expected_route != endpoint:
            problems.append(f"{path.name}: endpoint {endpoint!r} diverge do arquivo (esperado {expected_route!r})")
        if data.get("provenance") == "client":
            client_count += 1
            if data.get("sanitized") is not True:
                problems.append(f"{path.name}: fixture client sem sanitized=true")
            if not (data.get("response", {}).get("body") and data.get("request")):
                problems.append(f"{path.name}: fixture client sem par request/response")
    if problems:
        report.fail("fixtures de protocolo coerentes", "; ".join(problems[:10]))
    else:
        report.ok(f"fixtures de protocolo coerentes ({client_count} client sanitizadas)")


def check_registry(report: Report) -> None:
    compat_path = ROOT / "compatibility.json"
    if not compat_path.is_file():
        report.fail("compatibility.json existe", "arquivo ausente")
        return
    compat = json.loads(compat_path.read_text(encoding="utf-8"))
    endpoints = compat.get("endpoints", {})

    leaked_fallback = [r for r, d in endpoints.items() if d.get("client_validated") and d.get("uses_fallback")]
    if leaked_fallback:
        report.fail("fluxo validado sem fallback", f"{len(leaked_fallback)} rota(s): {', '.join(sorted(leaked_fallback))}")
    else:
        report.ok(f"nenhum endpoint client_validated depende de fallback ({len(endpoints)} rotas)")

    orphan_tests = [r for r, d in endpoints.items() if d.get("regression_test") and not d.get("implemented")]
    if orphan_tests:
        report.fail("teste sem implementação", f"rota com teste mas sem implementação: {', '.join(sorted(orphan_tests))}")
    else:
        report.ok("todo endpoint com teste de regressão está implementado")

    observed_without_provenance = sorted(
        r for r, d in endpoints.items()
        if (d.get("request_observed") or d.get("response_observed"))
        and d.get("evidence_provenance") not in ACCEPTED_OBSERVED_PROVENANCE
    )
    if observed_without_provenance:
        report.fail("observed sem provenance de evidência",
                    f"{len(observed_without_provenance)} rota(s): {', '.join(observed_without_provenance[:8])}"
                    + (" …" if len(observed_without_provenance) > 8 else ""))
    else:
        report.ok("todo request/response_observed tem provenance de evidência aceita")

    response_without_request = sorted(
        r for r, d in endpoints.items() if d.get("response_observed") and not d.get("request_observed"))
    if response_without_request:
        report.fail("response sem request", f"rota(s): {', '.join(response_without_request)}")
    else:
        report.ok("nenhum response_observed sem request_observed")

    check_fixtures(report)

    done = sum(1 for d in endpoints.values() if endpoint_done(d))
    terminal = sum(1 for d in endpoints.values() if endpoint_terminal(d))
    legacy = compat.get("server_only_routes") or []
    print(f"  [info] DoD completo: {done}/{len(endpoints)} · "
          f"terminal (client-autoritativo, não é paridade): {terminal} · "
          f"rotas legadas do servidor: {len(legacy)}")
    report.ok("compatibility.json coerente")


def check_live_server(report: Report, base_url: str, strict_research: bool) -> None:
    base = base_url.rstrip("/")

    def get(path: str) -> dict:
        with urllib.request.urlopen(base + path, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        health = get("/revival/health")
    except Exception as exc:  # noqa: BLE001 - diagnóstico no relatório
        report.fail("servidor vivo", f"{base}/revival/health indisponível: {exc}")
        return
    if not health.get("ok"):
        report.fail("servidor vivo", f"health retornou ok=false: {health}")
        return
    report.ok(f"servidor vivo ({health.get('client_version')} / api {health.get('api_version')}, "
              f"game_data={'sim' if health.get('game_data_loaded') else 'NÃO'})")

    try:
        research = get("/revival/research")
    except Exception as exc:  # noqa: BLE001
        report.fail("estado RESEARCH_MODE", f"/revival/research indisponível: {exc}")
        return

    compat = json.loads((ROOT / "compatibility.json").read_text(encoding="utf-8"))
    validated = {r for r, d in compat.get("endpoints", {}).items() if d.get("client_validated")}

    fallbacks = research.get("fallback_endpoints", [])
    validated_leaks = [f for f in fallbacks if f.get("path", "").lstrip("/") in validated]
    if validated_leaks:
        report.fail("fallback em fluxo validado",
                    f"{len(validated_leaks)} rota(s) validada(s) usando fallback: "
                    + ", ".join(sorted(f['path'] for f in validated_leaks)))
    else:
        report.ok("nenhum fluxo validado usando fallback no servidor vivo")

    if strict_research:
        total = research.get("fallback_total", 0)
        if research.get("research_mode"):
            report.fail("RESEARCH_MODE zero-fallback",
                        f"modo pesquisa ligado com {total} fallback(s) registrados — "
                        "meta do projeto é zero")
        elif total:
            report.fail("RESEARCH_MODE zero-fallback", f"{total} fallback(s) mesmo com modo desligado")
        else:
            report.ok("RESEARCH_MODE desligado e zero fallbacks")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--server", help="URL base de um servidor vivo (ex.: https://doom.exemplo)")
    parser.add_argument("--strict-research", action="store_true",
                        help="com --server: exige research_mode=false e zero fallbacks")
    parser.add_argument("--apk", type=Path, help="APK final para verify_patched_apk.py (exige --server também)")
    parser.add_argument("--skip-node", action="store_true", help="pula a suíte do servidor (emergência)")
    parser.add_argument("--skip-python", action="store_true", help="pula as regressões Python (emergência)")
    args = parser.parse_args()

    if args.apk and not args.server:
        print("ERRO: --apk exige --server (o verificador confere o hostname alvo)", file=sys.stderr)
        return 2

    report = Report()
    print("verify_everything — gate único de conclusão")

    report.section("1. Suíte do servidor (npm test)")
    if args.skip_node:
        print("  [PULADO] --skip-node")
    else:
        code, output = run(["npm", "test"], cwd=ROOT / "server")
        tail = "\n".join(output.strip().splitlines()[-6:])
        if code == 0:
            report.ok("npm test")
            print("    " + tail.replace("\n", "\n    "))
        else:
            report.fail("npm test", f"exit {code}\n{tail}")

    report.section("2. Regressões Python (autodescobertas, iguais às do run_tests.py)")
    if args.skip_python:
        print("  [PULADO] --skip-python")
    else:
        check_python_tests(report)

    report.section("3. Sincronização do registro (generate_endpoint_matrix --check)")
    code, output = run([sys.executable, str(ROOT / "scripts" / "generate_endpoint_matrix.py"), "--check"])
    if code == 0:
        report.ok("compatibility.json + docs/ENDPOINT-MATRIX.md sincronizados")
    else:
        report.fail("registro sincronizado", output.strip() or f"exit {code}")

    report.section("4. Coerência do registro")
    check_registry(report)

    if args.server:
        report.section("5. Servidor vivo")
        check_live_server(report, args.server, args.strict_research)

    if args.apk:
        report.section("6. APK final (verify_patched_apk)")
        report_path = ROOT / "work" / "apk-patch" / "final-apk-verification.json"
        code, output = run([sys.executable, str(ROOT / "scripts" / "verify_patched_apk.py"),
                            "--apk", str(args.apk), "--server", args.server,
                            "--report", str(report_path)])
        if code == 0:
            report.ok(f"verify_patched_apk ({report_path})")
        else:
            report.fail("verify_patched_apk", f"exit {code}\n" + "\n".join(output.strip().splitlines()[-8:]))

    print(f"\n{'=' * 60}")
    if report.failures:
        print(f"RESULTADO: FALHOU — {len(report.failures)} camada(s), {report.passed} passaram")
        for failure in report.failures:
            print(f"  - {failure}")
        return 1
    print(f"RESULTADO: PASS — {report.passed} verificações")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
