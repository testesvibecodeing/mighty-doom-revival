#!/usr/bin/env python3
"""Patch a decoded Mighty DOOM APK tree for a self-hosted endpoint.

The fast path replaces the official https://<host>/ URL with another URL of
the exact same byte length:

* same-length hostname: direct byte swap;
* shorter hostname: the URL is padded back to the original length with a URI
  userinfo segment (``https://u0..@<host>/``). Userinfo is ignored by DNS,
  SNI and the HTTP Host header, so the server sees the real hostname while
  every byte offset in global-metadata.dat stays untouched;
* longer hostname: blocked (would require rebuilding the IL2CPP metadata
  tables). Variable-length replacement is delegated to the bundle-aware
  reserializer by the Windows orchestration script.

The 1.13.1 target contains several Bethesda-related host strings. Static
inspection of the real build showed that the gameplay API base is
``international.gear.bethesda.net`` (the literal continues with
``/collections/doom``), while ``slayersclub.bethesda.net`` is an ancillary
club/site URL. When the Gear host is present we therefore patch only Gear;
otherwise older/synthetic inputs retain the previous all-known-host fallback.
This prevents an unrelated shorter URL from blocking a perfectly safe patch
of the real API host.
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

PRIMARY_API_HOST = "international.gear.bethesda.net"
KNOWN_HOSTS = (
    "slayersclub.bethesda.net",
    "game.9095be396f3547555fe1039cbc894c88.net",
    # Base real da API do jogo (plataforma "Gear" da Bethesda) no build 1.13.1:
    # literal completo "https://international.gear.bethesda.net/collections/doom".
    PRIMARY_API_HOST,
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

    candidates: list[Path] = []
    addressables = root / "assets" / "aa"
    if addressables.exists():
        candidates.extend(p for p in addressables.rglob("*") if p.is_file())

    # The backend hostname is a plain C# string literal, so IL2CPP builds
    # commonly bake it into global-metadata.dat's string-literal table
    # instead of (or in addition to) an Addressables bundle. A same-length
    # swap there is safe: the literal's byte length is recorded in a
    # separate metadata table, not derived from the string bytes
    # themselves, so overwriting N bytes with N different bytes doesn't
    # shift anything else in the file.
    candidates.extend(root.rglob("global-metadata.dat"))

    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
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


def select_patch_hits(hits: list[dict[str, object]]) -> list[dict[str, object]]:
    """Select endpoint occurrences that are safe/relevant to redirect.

    The real 1.13.1 build identifies Gear as the gameplay API. If that host is
    present, unrelated Bethesda URLs must not be rewritten and, importantly,
    must not participate in the length/unsupported gate. For old fixtures or
    yet-unseen variants where Gear is absent, preserve the historical fallback
    and attempt the known hosts discovered in that input.
    """
    primary = [hit for hit in hits if str(hit.get("host")) == PRIMARY_API_HOST]
    return primary or hits


def build_url_replacement(old_url: bytes, new_host: str) -> bytes | None:
    """Build an https URL of the exact same length for ``new_host``.

    ``old_url`` is the full ``https://<official-host>/`` prefix found in the
    APK. When ``new_host`` is shorter, the difference is padded as URI
    userinfo (``https://u00...@<host>/``), which is syntactically valid and
    invisible to DNS/SNI/Host. A 1-byte deficit uses the FQDN trailing dot
    instead (``<host>.``), also valid DNS. Longer hosts cannot be padded.
    """
    deficit = len(old_url) - (len("https://") + len(new_host.encode("ascii")) + 1)
    if deficit < 0:
        return None

    host = new_host
    pad = ""
    if deficit == 1:
        host = new_host + "."
    elif deficit >= 2:
        pad = "u" + "0" * (deficit - 2) + "@"

    new_url = f"https://{pad}{host}/".encode("ascii")
    if len(new_url) != len(old_url):
        return None
    return new_url


def same_length_patch(
    root: Path, target_host: str, hits: list[dict[str, object]]
) -> tuple[list[str], list[dict[str, object]]]:
    """Swap selected official endpoint occurrences for ``target_host`` without
    ever changing any byte offsets.

    Returns ``(patched_files, unsupported_occurrences)``. An occurrence is
    unsupported when it is neither an ``https://<host>/`` URL (which can be
    padded) nor a same-length bare hostname; those keep the patcher blocked.
    """
    patched: list[str] = []
    unsupported: list[dict[str, object]] = []
    target = target_host.encode("ascii")

    for hit in hits:
        rel = str(hit["path"])
        path = root / Path(rel)
        source = str(hit["host"]).encode("ascii")
        data = path.read_bytes()
        out = bytearray(data)
        changed = False

        pos = data.find(source)
        while pos != -1:
            end = pos + len(source)
            if data[pos - 8 : pos] == b"https://" and data[end : end + 1] == b"/":
                old_url = bytes(data[pos - 8 : end + 1])
                new_url = build_url_replacement(old_url, target_host)
                if new_url is not None:
                    out[pos - 8 : end + 1] = new_url
                    changed = True
                else:
                    unsupported.append(
                        {
                            "path": rel,
                            "host": hit["host"],
                            "offset": pos,
                            "reason": "hostname maior que a URL oficial encontrada",
                        }
                    )
            elif len(target) == len(source):
                out[pos:end] = target
                changed = True
            else:
                unsupported.append(
                    {
                        "path": rel,
                        "host": hit["host"],
                        "offset": pos,
                        "reason": "ocorrência fora de contexto https://<host>/ com comprimento diferente",
                    }
                )
            pos = data.find(source, end)

        if changed and bytes(out) != data:
            path.write_bytes(bytes(out))
            patched.append(rel)

    return sorted(set(patched)), unsupported


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
    patch_hits = select_patch_hits(hits)
    ignored_hits = [hit for hit in hits if hit not in patch_hits]
    patched_files: list[str] = []
    unsupported: list[dict[str, object]] = []

    already_present = any(str(h["host"]) == host for h in patch_hits)
    if not already_present:
        patched_files, unsupported = same_length_patch(decoded, host, patch_hits)

    fully_patched = (already_present or patched_files) and not unsupported
    report = {
        "server_host": host,
        "ca_embedded": bool(ca),
        "known_host_hits": hits,
        "patch_target_hits": patch_hits,
        "ignored_known_host_hits": ignored_hits,
        "host_already_present": already_present,
        "binary_patched_files": patched_files,
        "unsupported_occurrences": unsupported,
        "status": "ok" if fully_patched else "needs_bundle_aware_patch",
    }

    payload = json.dumps(report, indent=2, ensure_ascii=False)
    print(payload)
    if args.report:
        Path(args.report).write_text(payload + "\n", encoding="utf-8")

    if not hits:
        print(
            "\nERRO: nenhum hostname conhecido foi encontrado em assets/aa/ nem em "
            "global-metadata.dat. Precisamos analisar este APK antes de recompilar.",
            file=sys.stderr,
        )
        return 3

    if not already_present and not fully_patched:
        lengths = sorted({int(h["length"]) for h in patch_hits})
        host_len = len(host.encode("ascii"))
        if any(host_len > length for length in lengths):
            print(
                "\nBLOQUEADO COM SEGURANÇA: o hostname solicitado possui "
                f"{host_len} bytes, mas os hosts de endpoint selecionados possuem "
                f"comprimento(s) {lengths}. Hostname MAIOR que o oficial exigiria "
                "reconstruir as tabelas de metadata do IL2CPP (realocar seções "
                "inteiras do arquivo), o que não é suportado com segurança.",
                file=sys.stderr,
            )
        else:
            print(
                "\nBLOQUEADO COM SEGURANÇA: este APK tem ocorrência(ões) do host "
                "de endpoint fora de contexto https://<host>/ (ver "
                '"unsupported_occurrences" no relatório), e o patch direto só '
                "substitui URLs completas de mesmo comprimento.",
                file=sys.stderr,
            )
        return 4

    print("\nPatch lógico concluído. O APK decoded pode ser recompilado e assinado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
