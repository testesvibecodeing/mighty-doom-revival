#!/usr/bin/env python3
"""Patch a decoded Mighty DOOM APK tree for a self-hosted endpoint.

The fast path changes a hardcoded Unity hostname only when the replacement has
the exact same byte length. Variable-length replacement is delegated to the
bundle-aware reserializer by the Windows orchestration script.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

ANDROID_NS = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", ANDROID_NS)

KNOWN_HOSTS = (
    "slayersclub.bethesda.net",
    "game.9095be396f3547555fe1039cbc894c88.net",
)

HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[A-Za-z]{2,63}$"
)


def normalize_host(value: str) -> str:
    value = value.strip()
    if "://" in value:
        parsed = urlparse(value)
        if not parsed.hostname:
            raise ValueError("URL do servidor inválida")
        host = parsed.hostname
    else:
        host = value.split("/", 1)[0].split(":", 1)[0]
    host = host.strip().lower().rstrip(".")
    if not HOST_RE.match(host):
        raise ValueError(
            "Informe um hostname DNS (ex.: doom.exemplo.com). "
            "IP puro ainda não é suportado pelo patcher de hostname."
        )
    return host


def patch_manifest(decoded: Path) -> None:
    manifest = decoded / "AndroidManifest.xml"
    if not manifest.exists():
        raise RuntimeError("AndroidManifest.xml não encontrado após apktool")

    tree = ET.parse(manifest)
    root = tree.getroot()
    app = root.find("application")
    if app is None:
        raise RuntimeError("<application> não encontrado no AndroidManifest.xml")
    app.set(f"{{{ANDROID_NS}}}networkSecurityConfig", "@xml/network_security_config")
    tree.write(manifest, encoding="utf-8", xml_declaration=True)


def write_network_security(decoded: Path, host: str, ca: Path | None) -> None:
    xml_dir = decoded / "res" / "xml"
    xml_dir.mkdir(parents=True, exist_ok=True)
    target = xml_dir / "network_security_config.xml"

    # The patched client should explicitly trust only the Revival endpoint.
    # Keeping official hosts here would make a stale/unpatched endpoint look
    # legitimate and would defeat the final APK verification gate.
    domains = [host]

    trust = ['            <certificates src="system"/>']
    if ca is not None:
        raw_dir = decoded / "res" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        ca_target = raw_dir / "mightydoom_ca.pem"
        shutil.copyfile(ca, ca_target)
        trust.append('            <certificates src="@raw/mightydoom_ca"/>')

    domain_lines = "\n".join(
        f'        <domain includeSubdomains="true">{d}</domain>' for d in domains
    )
    trust_lines = "\n".join(trust)
    target.write_text(
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
        "<network-security-config>\n"
        "    <domain-config cleartextTrafficPermitted=\"false\">\n"
        f"{domain_lines}\n"
        "        <trust-anchors>\n"
        f"{trust_lines}\n"
        "        </trust-anchors>\n"
        "    </domain-config>\n"
        "</network-security-config>\n",
        encoding="utf-8",
    )


def find_host_occurrences(root: Path) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    search_root = root / "assets" / "aa"
    if not search_root.exists():
        return hits

    for path in search_root.rglob("*"):
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        for host in KNOWN_HOSTS:
            b = host.encode("ascii")
            count = data.count(b)
            if count:
                hits.append(
                    {
                        "path": str(path.relative_to(root)).replace("\\", "/"),
                        "host": host,
                        "count": count,
                        "length": len(b),
                    }
                )
    return hits


def exact_length_patch(root: Path, target_host: str, hits: list[dict[str, object]]) -> list[str]:
    patched: list[str] = []
    target = target_host.encode("ascii")

    compatible = [h for h in hits if int(h["length"]) == len(target)]
    if not compatible:
        return patched

    for hit in compatible:
        rel = str(hit["path"])
        path = root / Path(rel)
        source = str(hit["host"]).encode("ascii")
        data = path.read_bytes()
        changed = data.replace(source, target)
        if changed != data:
            path.write_bytes(changed)
            patched.append(rel)
    return sorted(set(patched))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decoded", required=True, help="Diretório produzido pelo apktool")
    parser.add_argument("--server", required=True, help="Hostname ou URL HTTPS do servidor")
    parser.add_argument("--ca", help="CA PEM/CRT opcional a incorporar no APK")
    parser.add_argument("--report", help="Arquivo JSON para relatório")
    args = parser.parse_args()

    decoded = Path(args.decoded).resolve()
    if not decoded.is_dir():
        print(f"ERRO: diretório decoded inexistente: {decoded}", file=sys.stderr)
        return 2

    try:
        host = normalize_host(args.server)
    except ValueError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    ca: Path | None = None
    if args.ca:
        ca = Path(args.ca).expanduser().resolve()
        if not ca.is_file():
            print(f"ERRO: CA não encontrada: {ca}", file=sys.stderr)
            return 2

    try:
        patch_manifest(decoded)
        write_network_security(decoded, host, ca)
    except Exception as exc:
        print(f"ERRO ao preparar TLS/manifest: {exc}", file=sys.stderr)
        return 2

    hits = find_host_occurrences(decoded)
    patched_files: list[str] = []

    already_present = any(str(h["host"]) == host for h in hits)
    if not already_present:
        patched_files = exact_length_patch(decoded, host, hits)

    report = {
        "server_host": host,
        "ca_embedded": bool(ca),
        "known_host_hits": hits,
        "host_already_present": already_present,
        "binary_patched_files": patched_files,
        "status": "ok" if already_present or patched_files else "needs_bundle_aware_patch",
    }

    payload = json.dumps(report, indent=2, ensure_ascii=False)
    print(payload)
    if args.report:
        Path(args.report).write_text(payload + "\n", encoding="utf-8")

    if not hits:
        print(
            "\nERRO: nenhum hostname conhecido foi encontrado em assets/aa/. "
            "Precisamos analisar este APK antes de recompilar.",
            file=sys.stderr,
        )
        return 3

    if not already_present and not patched_files:
        lengths = sorted({int(h["length"]) for h in hits})
        print(
            "\nBLOQUEADO COM SEGURANÇA: o hostname solicitado possui "
            f"{len(host.encode('ascii'))} bytes, mas os hosts encontrados possuem "
            f"comprimento(s) {lengths}. O fluxo deve continuar pelo patch bundle-aware.",
            file=sys.stderr,
        )
        return 4

    print("\nPatch lógico concluído. O APK decoded pode ser recompilado e assinado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
