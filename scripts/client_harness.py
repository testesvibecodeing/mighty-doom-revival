#!/usr/bin/env python3
"""Harness ADB do cliente real — valida fluxos de gameplay de ponta a ponta.

O que faz numa execução:
  1. resolve `adb` (PATH ou Android SDK padrão) e o dispositivo;
  2. (opcional) instala o APK (--apk) e abre o jogo;
  3. limpa o logcat e observa por --duration segundos (aborta cedo se o boot
     morrer com "Failed to launch after N attempts");
  4. captura o logcat completo e varre as assinaturas conhecidas de falha
     (Malformed response payload, CRC Mismatch, abort, exceção fatal);
  5. consulta o servidor (/revival/health, /revival/research e, com
     --admin-token, /revival/requests) para reconstruir a sequência de
     endpoints realmente chamada pelo cliente;
  6. grava relatório JSON em work/harness/ e devolve exit != 0 se o fluxo
     falhou;
  7. com --update-registry, grava a evidência no compatibility.json
     (request/response observados, uses_fallback) e regenera a matriz.

Uso:
  python scripts/client_harness.py --server https://doom.exemplo.br
  python scripts/client_harness.py --server http://192.168.0.10:8080 \
      --apk output/mighty-doom-revival.apk --admin-token <token> \
      --duration 300 --update-registry

Exit codes: 0 fluxo limpo; 1 fluxo falhou (assinatura de erro ou fallback em
fluxo validado); 2 ambiente indisponível (adb/device/servidor).
"""
from __future__ import annotations

import argparse
import json
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

# (padrão, classificação, descrição). fatal = falha do fluxo; warning = vive no
# log de um boot são e registrável, não derruba a validação.
SIGNATURES: list[tuple[str, str, str]] = [
    (r"Malformed response payload", "fatal", "parse do cliente rejeitou um payload do servidor"),
    (r"Failed to launch after \d+ attempts", "fatal", "boot abortou após 3 tentativas (Relaunch)"),
    (r"CRC Mismatch", "fatal", "bundle Addressables alterado sem zero_catalog_crc"),
    (r"RemoteProviderException", "fatal", "load de cena morreu (provider Addressables)"),
    (r"FATAL EXCEPTION", "fatal", "crash nativo/gerenciado"),
    (r"signal \d+ \(SIGSEGV\)", "fatal", "segfault nativo"),
    (r"Session token is not a well formed JWT", "warning", "token opaco; warning comprovadamente não fatal (DEAD-ENDS #9)"),
    (r"Cant find corresponding data tool data", "warning", "game-data sem definição da ability citada"),
]


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


def http_get_json(url: str) -> tuple[int, dict | None]:
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - diagnóstico no relatório
        return 0, {"error": str(exc)}


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--server", required=True, help="URL base do Revival Server")
    parser.add_argument("--apk", type=Path, help="APK a instalar antes do fluxo")
    parser.add_argument("--package", default=PACKAGE)
    parser.add_argument("--serial", help="serial adb do dispositivo/emulador")
    parser.add_argument("--duration", type=int, default=180, help="segundos de observação (default 180)")
    parser.add_argument("--admin-token", help="Bearer token de admin para ler /revival/requests")
    parser.add_argument("--no-launch", action="store_true", help="não (re)abre o app; só observa")
    parser.add_argument("--report", type=Path, help="caminho do relatório JSON (default work/harness/<ts>.json)")
    parser.add_argument("--update-registry", action="store_true",
                        help="grava evidência no compatibility.json e regenera a matriz")
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    report: dict = {
        "harness": "client_harness.py",
        "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "server": args.server.rstrip("/"),
        "package": args.package,
        "duration_planned": args.duration,
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
    status, health = http_get_json(f"{base}/revival/health")
    if not health or not health.get("ok"):
        print(f"ERRO: servidor {base} não respondeu health ok: {health}", file=sys.stderr)
        return 2
    report["health"] = health
    print(f"[ambiente] adb={serial} · servidor={base} (client {health.get('client_version')})")

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
            hits = [f for f in scan_logcat(tail) if f["severity"] == "fatal"]
            if any("Failed to launch" in f["signature"] for f in hits):
                fatal_seen = True
                print("[corta] boot abortou antes do fim da janela de observação")
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

    status, research = http_get_json(f"{base}/revival/research")
    report["research"] = research if research else {"error": "indisponível"}
    fallbacks = (research or {}).get("fallback_endpoints", [])
    fallback_paths = sorted({f["path"].lstrip("/") for f in fallbacks})

    sequence: list[dict] = []
    if args.admin_token:
        status, requests_state = http_get_json(f"{base}/revival/requests?limit=500")
        # http_get_json não envia header; refaz com token quando necessário.
        try:
            request = urllib.request.Request(f"{base}/revival/requests?limit=500",
                                             headers={"authorization": f"Bearer {args.admin_token}"})
            with urllib.request.urlopen(request, timeout=15) as response:
                requests_state = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            requests_state = {"error": str(exc)}
        rows = requests_state.get("requests", [])
        counts: dict[str, int] = {}
        for row in rows:
            path = str(row.get("path", "")).lstrip("/")
            if path.startswith("game/"):
                counts[path] = counts.get(path, 0) + 1
        sequence = [{"endpoint": path, "calls": count} for path, count in sorted(counts.items())]
        report["endpoint_sequence"] = sequence
        report["endpoints_called"] = len(sequence)
    else:
        report["endpoint_sequence"] = None
        report["endpoints_called"] = None

    clean = not fatal_seen and not fatal
    report["verdict"] = "clean" if clean else "failed"
    report["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    compat_path = ROOT / "compatibility.json"
    validated_fallbacks = []
    if compat_path.is_file():
        compat = json.loads(compat_path.read_text(encoding="utf-8"))
        validated = {r for r, d in compat.get("endpoints", {}).items() if d.get("client_validated")}
        validated_fallbacks = [p for p in fallback_paths if p in validated]
        if args.update_registry:
            note = f"client_harness {report['finished_at']} contra {base}"
            changed = False
            for entry in compat["endpoints"].values():
                entry["uses_fallback"] = entry.get("uses_fallback", False)
            for path in fallback_paths:
                endpoint = compat["endpoints"].get(path)
                if endpoint and not endpoint["uses_fallback"]:
                    endpoint["uses_fallback"] = True
                    endpoint["evidence"] = (endpoint.get("evidence", "") + f" | fallback observado: {note}").strip(" |")
                    changed = True
            if clean and sequence:
                for entry in sequence:
                    endpoint = compat["endpoints"].get(entry["endpoint"])
                    if endpoint and not endpoint.get("request_observed"):
                        endpoint["request_observed"] = True
                        endpoint["evidence"] = (endpoint.get("evidence", "") + f" | chamada real do cliente: {note}").strip(" |")
                        changed = True
                    if endpoint and not endpoint.get("response_observed") and clean:
                        endpoint["response_observed"] = True
                        changed = True
            if changed:
                compat_path.write_text(json.dumps(compat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                print("[registro] compatibility.json atualizado com a evidência do harness")
    report["fallback_endpoints"] = fallback_paths
    report["validated_flow_used_fallback"] = validated_fallbacks

    report_file = report_dir / f"harness-{stamp}.json"
    report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print()
    print(f"logcat:   {report_dir / f'logcat-{stamp}.txt'}")
    print(f"relatório: {report_file}")
    print(f"fatais: {len(fatal)} · warnings: {len(warnings)} · endpoints chamados: {report['endpoints_called']}")
    print(f"fallbacks de pesquisa: {len(fallback_paths)}" + (f" -> {', '.join(fallback_paths)}" if fallback_paths else ""))
    if validated_fallbacks:
        print(f"ERRO DE GATE: fluxo validado usando fallback: {', '.join(validated_fallbacks)}")
    if args.update_registry:
        regen = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_endpoint_matrix.py")],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
        if regen.returncode == 0:
            print("[registro] docs/ENDPOINT-MATRIX.md regenerado")
        else:
            print(f"[registro] falha ao regenerar matriz: {regen.stdout} {regen.stderr}", file=sys.stderr)

    if not clean or validated_fallbacks:
        for finding in fatal[:10]:
            print(f"  [fatal] {finding['description']}: {finding['line'][:160]}")
        return 1
    print("VEREDITO: fluxo limpo (sem assinaturas fatais no logcat)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
