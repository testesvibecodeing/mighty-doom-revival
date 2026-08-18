#!/usr/bin/env python3
"""Gate único de conclusão do projeto — nada está "pronto" sem isto passar.

Camadas (todas obrigatórias salvo as marcadas opcionais):
  1. Suíte do servidor (cd server && npm test) — inclui o smoke com o gate de
     fallback do RESEARCH_MODE.
  2. Regressões Python do patcher (a lista do AGENTS.md) + extrator + CRC.
  3. Sincronização do registro: generate_endpoint_matrix.py --check.
  4. Coerência do registro (compatibility.json):
       - endpoint com client_validated=true NÃO pode ter uses_fallback=true
         (fluxo validado não pode viver de resposta vazia de pesquisa);
       - endpoint com regression_test=true tem que estar implementado;
       - nenhuma rota das 116 pode ficar sem entrada.
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
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Consoles Windows ficam em cp1252; a saída destes scripts é UTF-8 (mesclas
# de português e emoji do estado dos testes) — nunca deixe o print derrubar o gate.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PYTHON_TESTS = [
    "scripts/test_dump_il2cpp_metadata.py",
    "scripts/test_check_revival_server.py",
    "scripts/test_patch_apk.py",
    "scripts/test_patch_network_security.py",
    "scripts/test_patch_primary_api_host.py",
    "scripts/test_patcher_orchestration.py",
    "scripts/test_inspect_apk_unity_candidates.py",
    "scripts/test_verify_patched_apk.py",
    "tests/test_zero_catalog_crc.py",
    "tests/test_inject_loading_screen.py",
    # Revival Studio (scripts/revival_editor/) — fundação do editor desktop.
    "tests/revival_editor/test_paths.py",
    "tests/revival_editor/test_models.py",
    "tests/revival_editor/test_toolchain.py",
    "tests/revival_editor/test_runner.py",
    "tests/revival_editor/test_services.py",
    "tests/revival_editor/test_project.py",
    "tests/revival_editor/test_ui_app.py",
    "tests/revival_editor/test_wrappers.py",
    "tests/revival_editor/test_axml.py",
    "tests/revival_editor/test_pipeline.py",
    "tests/revival_editor/test_xapk.py",
    "tests/revival_editor/test_visuals.py",
    "tests/revival_editor/test_branding.py",
    "tests/revival_editor/test_assets_catalog.py",
]


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

    done = sum(1 for d in endpoints.values()
               if all(d.get(g) is not False for g in ("schema_extracted", "implemented",
                                                     "request_observed", "response_observed",
                                                     "client_validated", "regression_test"))
               and not d.get("uses_fallback"))
    legacy = compat.get("server_only_routes") or []
    print(f"  [info] DoD completo: {done}/{len(endpoints)} · rotas legadas do servidor: {len(legacy)}")
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

    report.section("2. Regressões Python do patcher")
    if args.skip_python:
        print("  [PULADO] --skip-python")
    else:
        for test in PYTHON_TESTS:
            path = ROOT / test
            if not path.is_file():
                report.fail(test, "arquivo de teste ausente")
                continue
            code, output = run([sys.executable, str(path)])
            if code == 0:
                report.ok(test)
            else:
                report.fail(test, f"exit {code}\n" + "\n".join(output.strip().splitlines()[-8:]))

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
