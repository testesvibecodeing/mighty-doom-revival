#!/usr/bin/env python3
"""Injeta a RevivalAuthActivity num APK: dex novo + Manifest + verificação.

Pipeline, com precondição e pós-condição em cada etapa:

  1. **precondição**: o APK tem `classes.dex`, a Activity Unity no Manifest e
     exatamente um MAIN/LAUNCHER; o alvo é o build suportado.
  2. compila a Activity e gera um `classesN.dex` só com ela (`revival_auth.build`).
  3. patcha o `AndroidManifest.xml` da árvore decodificada
     (`revival_auth.manifest`) — MAIN/LAUNCHER migra para a Activity Revival.
  4. **pós-condição**: um único launcher, Activity Unity preservada com deep
     link e meta-data, dex presente, relatório sanitizado.

Idempotente: rodar duas vezes sobre a mesma árvore não duplica Activity nem dex.

Este script NÃO assina e NÃO verifica o APK final — quem faz isso é o pipeline
do Studio, com `uber-apk-signer` + `verify_patched_apk.py` DEPOIS da assinatura.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from revival_auth.build import ACTIVITY_CLASS, BuildError, build_dex, detect_toolchain  # noqa: E402
from revival_auth.manifest import (  # noqa: E402
    UNITY_ACTIVITY, ManifestError, count_launchers, patch_manifest_file,
)

SUPPORTED_PACKAGE = "com.bethsoft.ubu"
SUPPORTED_VERSION = "1.13.1"


class AuthPatchError(Exception):
    """Falha segura: nada é promovido pela metade."""


def next_dex_name(decoded: Path) -> str:
    """`classes3.dex` quando já existem `classes.dex` e `classes2.dex`."""
    existentes = {p.name for p in decoded.glob("classes*.dex")}
    indice = 2
    while True:
        nome = "classes.dex" if indice == 1 else f"classes{indice}.dex"
        if nome not in existentes:
            return nome
        indice += 1


def check_preconditions(decoded: Path) -> dict:
    manifest = decoded / "AndroidManifest.xml"
    if not manifest.is_file():
        raise AuthPatchError(f"árvore decodificada sem AndroidManifest.xml: {decoded}")
    texto = manifest.read_text(encoding="utf-8")

    pacote = re.search(r'package="([^"]+)"', texto)
    if pacote and pacote.group(1) != SUPPORTED_PACKAGE:
        raise AuthPatchError(
            f"pacote {pacote.group(1)!r} não é o suportado ({SUPPORTED_PACKAGE})")
    if UNITY_ACTIVITY not in texto:
        raise AuthPatchError(f"Activity Unity {UNITY_ACTIVITY} ausente")

    ja = ACTIVITY_CLASS in texto
    launchers = count_launchers(texto)
    if not ja and launchers != 1:
        raise AuthPatchError(f"esperava 1 MAIN/LAUNCHER, achei {launchers}")
    if not (decoded / "classes.dex").is_file() and not any(decoded.glob("smali*")):
        raise AuthPatchError("árvore sem classes.dex nem smali — decodificação incompleta?")
    return {"package": SUPPORTED_PACKAGE, "already_patched": ja, "launcher_count": launchers}


def apply(*, decoded: Path, base_url: str, api_version: str, client_version: str,
          analyze: bool = False, dex_out: Path | None = None) -> dict:
    decoded = Path(decoded)
    # O dex fica FORA da árvore decodificada de propósito: o Apktool reconstrói
    # `classes*.dex` a partir do smali, e um arquivo com esse nome na raiz
    # colidiria com o que ele gera. A injeção acontece no APK já construído.
    dex_out = Path(dex_out) if dex_out else decoded.parent / "revival-auth" / "classes-revival.dex"
    pre = check_preconditions(decoded)

    relatorio: dict = {
        "decoded": decoded.name,
        "package": pre["package"],
        "client_version": client_version,
        "activity_class": ACTIVITY_CLASS,
        "unity_activity": UNITY_ACTIVITY,
        "base_url_scheme": base_url.split("://", 1)[0],
        "analyze": analyze,
        "already_patched": pre["already_patched"],
        # A URL completa NÃO entra no relatório: host de laboratório é ruído e
        # host de produção não precisa ficar em artefato de auditoria.
        "secrets_redacted": True,
    }

    if analyze:
        relatorio["manifest_changed"] = False
        relatorio["dex_added"] = None
        relatorio["toolchain"] = detect_toolchain().describe()
        return relatorio

    info = build_dex(base_url=base_url, api_version=api_version,
                     client_version=client_version, unity_activity=UNITY_ACTIVITY,
                     out_dex=dex_out)
    relatorio.update({k: v for k, v in info.items() if k != "base_url_scheme"})
    relatorio["dex_path"] = dex_out.as_posix()
    relatorio["dex_added"] = dex_out.name

    relatorio.update(patch_manifest_file(decoded / "AndroidManifest.xml"))

    # -------- pós-condição: falha aqui é falha do patch, não "quase pronto" ---
    if relatorio["launcher_count"] != 1:
        raise AuthPatchError(f"{relatorio['launcher_count']} launchers após o patch")
    if not relatorio["revival_is_launcher"]:
        raise AuthPatchError("a Activity Revival não ficou como launcher")
    if relatorio["unity_activity_is_launcher"]:
        raise AuthPatchError("a Activity Unity continuou como launcher")
    if not relatorio["unity_activity_preserved"]:
        raise AuthPatchError("Activity Unity não preservada")
    if not relatorio["deep_link_preserved"]:
        raise AuthPatchError("deep link mightydoom:// perdido")
    if not dex_out.is_file():
        raise AuthPatchError("dex da Activity não foi gerado")
    if not _dex_has_activity(dex_out):
        raise AuthPatchError("o dex gerado não contém a Activity")
    relatorio["verified"] = True
    return relatorio


def _dex_has_activity(dex: Path) -> bool:
    """A string do nome da classe aparece crua na tabela de strings do dex."""
    try:
        return ACTIVITY_CLASS.replace(".", "/").encode() in dex.read_bytes()
    except OSError:
        return False


def inject_dex(apk_in: Path, dex: Path, *, apk_out: Path, dex_name: str | None = None) -> dict:
    """Põe o `classesN.dex` da Activity dentro de um APK já construído.

    O Apktool reconstrói `classes*.dex` a partir do smali, então um dex solto na
    árvore decodificada NÃO entra no build — ele é injetado aqui, no ZIP. O
    Android carrega todos os `classesN.dex` do APK, sem `MultiDex` no código.

    Idempotente: se o dex da Activity já estiver no APK, devolve sem duplicar.
    """
    apk_in, dex, apk_out = Path(apk_in), Path(dex), Path(apk_out)
    if not dex.is_file():
        raise AuthPatchError(f"dex da Activity não existe: {dex}")

    with zipfile.ZipFile(apk_in) as zin:
        nomes = zin.namelist()
        existente = next((n for n in nomes if n.endswith(".dex")
                          and ACTIVITY_CLASS.replace(".", "/").encode() in zin.read(n)), None)
        if existente:
            if apk_out != apk_in:
                apk_out.write_bytes(apk_in.read_bytes())
            return {"dex_entry": existente, "injected": False, "reason": "já presente"}

        usados = {n for n in nomes if n.startswith("classes") and n.endswith(".dex")}
        indice = 2
        while (f"classes{indice}.dex" if indice > 1 else "classes.dex") in usados:
            indice += 1
        alvo = dex_name or f"classes{indice}.dex"

        apk_out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(apk_out, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                novo = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                novo.compress_type = info.compress_type
                novo.external_attr = info.external_attr
                zout.writestr(novo, zin.read(info.filename))
            zout.writestr(alvo, dex.read_bytes())
    return {"dex_entry": alvo, "injected": True, "dex_bytes": dex.stat().st_size}


def verify_apk(apk: Path) -> dict:
    """Confere no APK CONSTRUÍDO que a Activity entrou e a Unity ficou."""
    resultado = {"apk": Path(apk).name, "activity_dex": None,
                 "unity_activity_present": False, "dex_entries": []}
    with zipfile.ZipFile(apk) as zf:
        for nome in zf.namelist():
            if not nome.endswith(".dex"):
                continue
            resultado["dex_entries"].append(nome)
            dados = zf.read(nome)
            if ACTIVITY_CLASS.replace(".", "/").encode() in dados:
                resultado["activity_dex"] = nome
        manifesto = zf.read("AndroidManifest.xml")
        resultado["unity_activity_present"] = UNITY_ACTIVITY.encode("utf-16-le") in manifesto
        resultado["revival_activity_present"] = ACTIVITY_CLASS.encode("utf-16-le") in manifesto
    resultado["verified"] = bool(resultado["activity_dex"]
                                 and resultado["unity_activity_present"]
                                 and resultado["revival_activity_present"])
    return resultado


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--decoded", type=Path, help="árvore do apktool a patchar")
    p.add_argument("--base-url", help="base da API que a Activity vai chamar")
    p.add_argument("--api-version", default="24.0.0")
    p.add_argument("--client-version", default=SUPPORTED_VERSION)
    p.add_argument("--analyze", action="store_true", help="não altera nada")
    p.add_argument("--verify-apk", type=Path, help="confere um APK já construído")
    p.add_argument("--report", type=Path)
    args = p.parse_args(argv)

    try:
        if args.verify_apk:
            rel = verify_apk(args.verify_apk)
        else:
            if not args.decoded or not args.base_url:
                print("ERRO: --decoded e --base-url são obrigatórios", file=sys.stderr)
                return 2
            rel = apply(decoded=args.decoded, base_url=args.base_url,
                        api_version=args.api_version, client_version=args.client_version,
                        analyze=args.analyze)
    except (AuthPatchError, ManifestError, BuildError) as exc:
        print(f"FALHOU: {exc}", file=sys.stderr)
        return 4

    print(json.dumps(rel, indent=2, ensure_ascii=False))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(rel, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if rel.get("verified", True) else 4


if __name__ == "__main__":
    raise SystemExit(main())
