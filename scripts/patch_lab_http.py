#!/usr/bin/env python3
"""LAB_ONLY_INSECURE_HTTP — rebaixa o wire do cliente para HTTP, só no rig.

POR QUE ISTO EXISTE
-------------------
O cliente 1.13.1 chama `https://<host>/collections/doom` e o stack TLS da Unity
não aceita CA de laboratório neste emulador Android 14 (medido em
`work/audit-opus/FASE-3-ADB-APK.md`: CA visível em
`/system/etc/security/cacerts` dentro do namespace do app E declarada como
trust-anchor no `network_security_config`, e ainda assim o handshake é recusado;
o trust store do Conscrypt vive no APEX, cuja propagação de mount é privada).

Sem transporte não existe prova dinâmica. Este módulo troca o esquema por HTTP
**apenas em um APK descartável de laboratório**, autorizado explicitamente pelo
usuário para o rig local isolado.

O QUE ISTO NUNCA FAZ
--------------------
- não roda sem `--allow-insecure-lab` (recusa por padrão);
- não aceita destino público: só loopback/RFC1918/`.local`/emulador (10.0.2.2);
- não escreve em `output/` — o artefato final nunca pode ser HTTP;
- não é chamado pelo pipeline/Studio do fluxo normal;
- não realoca `global-metadata.dat`: cada troca preserva o comprimento EXATO em
  bytes, com preimage única e postimage conferida;
- não faz substituição global cega: cada ocorrência é casada por preimage
  completa e contada.

COMO O COMPRIMENTO É PRESERVADO
-------------------------------
`https://` tem 8 bytes e `http://` tem 7. O byte que falta é reposto por padding
SINTÁTICO que não muda o destino:

- `https://<host>/...`         -> `http://<host>./...`   (ponto final do FQDN)
- `https://<userinfo>@<host>/` -> `http://<userinfo>0@<host>/` (userinfo cresce 1)

O ponto final do FQDN é a forma absoluta do nome: `doom.exemplo.br.` resolve
para o mesmo endereço que `doom.exemplo.br`. O userinfo é ignorado por DNS, SNI
e pelo header `Host`. Nos dois casos o path e o Host efetivo continuam iguais —
provado por `describe_target()` e pelos testes.

Uso:
    python scripts/patch_lab_http.py --apk <entrada> --out work/audit-opus/rig/x.apk \\
        --host 10.0.2.2 --allow-insecure-lab
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

MARKER = "LAB_ONLY_INSECURE_HTTP"

# Diretório único onde o artefato inseguro pode nascer.
LAB_DIR = ROOT / "work" / "audit-opus" / "rig"

# Onde o endpoint vive (skill apk-patch): metadata IL2CPP + bundles Addressables.
METADATA_ENTRY = "assets/bin/Data/Managed/Metadata/global-metadata.dat"

_HOST_RE = re.compile(rb"[A-Za-z0-9.\-]{1,253}")


class LabPatchError(Exception):
    """Recusa deliberada. Nunca degrada para 'tentar assim mesmo'."""


# ---------------------------------------------------------------------------
# Destino: só laboratório
# ---------------------------------------------------------------------------

def is_lab_target(host: str) -> bool:
    """Loopback, RFC1918, link-local, `.local`, ou o alias 10.0.2.2 do emulador.

    Nome público (mesmo o do projeto) é recusado: HTTP na Internet, nunca.
    """
    if not host:
        return False
    alvo = host.rstrip(".").lower()
    if alvo in ("localhost", "10.0.2.2"):
        return True
    if alvo.endswith(".local") or alvo.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(alvo)
    except ValueError:
        return False
    return bool(ip.is_loopback or ip.is_private or ip.is_link_local)


def describe_target(url: bytes) -> dict:
    """Host efetivo e path de uma URL do wire — para provar que não mudaram."""
    texto = url.decode("ascii", "replace")
    sem_esquema = texto.split("://", 1)[1] if "://" in texto else texto
    autoridade, _, caminho = sem_esquema.partition("/")
    _, _, host = autoridade.rpartition("@")           # descarta userinfo
    return {
        "scheme": texto.split("://", 1)[0] if "://" in texto else "",
        "host": host.rstrip("."),                      # ponto final = mesmo FQDN
        "path": "/" + caminho,
    }


# ---------------------------------------------------------------------------
# A troca, byte a byte
# ---------------------------------------------------------------------------

def downgrade_url(url: bytes, new_host: str | None = None) -> bytes:
    """`https://…` -> `http://…` do MESMO comprimento. Erro se não der.

    Com `new_host`, troca também o host (o rig fica num endereço privado de
    verdade, em vez de depender de um override de DNS no device). O byte que
    sobra ou falta vira *userinfo*, que DNS, SNI e o header `Host` ignoram.
    """
    if not url.startswith(b"https://"):
        raise LabPatchError("preimage não começa em https://")
    resto = url[len(b"https://"):]
    autoridade, barra, caminho = resto.partition(b"/")
    _, _, host_atual = autoridade.rpartition(b"@")
    host_final = new_host.encode("ascii") if new_host else host_atual

    fixo = len(b"http://") + len(host_final) + len(barra) + len(caminho)
    folga = len(url) - fixo
    if folga < 0:
        raise LabPatchError(
            f"host {host_final.decode()!r} não cabe no orçamento de "
            f"{len(url)} bytes da URL original (faltam {-folga})")
    if folga == 0:
        nova_autoridade = host_final
    elif folga == 1:
        # 1 byte só: não cabe "x@", então usa a forma absoluta do FQDN.
        if host_final.replace(b".", b"").isdigit():
            raise LabPatchError("não dá para pôr ponto final em literal IPv4")
        nova_autoridade = host_final + b"."
    else:
        nova_autoridade = b"u" + b"0" * (folga - 2) + b"@" + host_final

    saida = b"http://" + nova_autoridade + barra + caminho
    if len(saida) != len(url):
        raise LabPatchError(
            f"padding não fechou o comprimento: {len(saida)} != {len(url)}")
    antes, depois = describe_target(url), describe_target(saida)
    if depois["scheme"] != "http":
        raise LabPatchError("postimage não ficou em http")
    if antes["path"] != depois["path"]:
        raise LabPatchError(f"o padding mudou o path: {antes} -> {depois}")
    esperado = (new_host or antes["host"]).rstrip(".")
    if depois["host"] != esperado:
        raise LabPatchError(f"host efetivo errado: {depois['host']!r} != {esperado!r}")
    return saida


def _metadata_literals(dados: bytes) -> list[tuple[int, int]]:
    """(offset, comprimento) de cada string literal do global-metadata.dat v29.

    A tabela dá o comprimento EXATO. Varrer por delimitador não serve: no blob
    de literais as strings ficam coladas, e um scan guloso engole a próxima
    (`.../collections/doomhttps://oauth2.googleap…`).
    """
    import struct  # noqa: PLC0415
    if len(dados) < 128:
        return []
    h = struct.unpack_from("<32I", dados, 0)
    if h[0] != 0xFAB11BAF or h[1] != 29:
        return []
    lit_off, lit_size, data_off = h[2], h[3], h[4]
    if lit_off + lit_size > len(dados):
        return []
    saida = []
    for i in range(lit_size // 8):
        comprimento, indice = struct.unpack_from("<Ii", dados, lit_off + i * 8)
        inicio = data_off + indice
        if 0 < comprimento < 4096 and 0 <= inicio and inicio + comprimento <= len(dados):
            saida.append((inicio, comprimento))
    return saida


def _unity_length_prefixed(dados: bytes, inicio: int) -> int | None:
    """Comprimento de uma string Unity serializada que começa em `inicio`.

    Unity grava `int32 LE` com o número de bytes, seguido do UTF-8. Só aceita
    quando o prefixo bate com um comprimento plausível — nunca no chute.
    """
    import struct  # noqa: PLC0415
    if inicio < 4:
        return None
    (comprimento,) = struct.unpack_from("<i", dados, inicio - 4)
    if not (0 < comprimento < 4096) or inicio + comprimento > len(dados):
        return None
    corpo = dados[inicio:inicio + comprimento]
    # Uma URL não tem byte de controle nem espaço no meio.
    if any(b <= 0x20 or b >= 0x7F for b in corpo):
        return None
    return comprimento


def find_https_urls(dados: bytes, host: str) -> list[bytes]:
    """Preimages EXATAS de URL https:// para `host`, com fronteira provada.

    Duas fontes de fronteira, nesta ordem: a tabela de literais do metadata
    IL2CPP (comprimento explícito) e o prefixo `int32` das strings Unity nos
    bundles. Ocorrência cuja fronteira não puder ser provada é IGNORADA — nunca
    recortada no palpite.
    """
    alvo = host.encode("ascii")
    achados: set[bytes] = set()

    # 1) metadata IL2CPP: a tabela manda.
    por_offset = {off: comp for off, comp in _metadata_literals(dados)}
    if por_offset:
        for off, comp in por_offset.items():
            literal = dados[off:off + comp]
            if literal.startswith(b"https://") and alvo in literal:
                achados.add(literal)
        if achados:
            return sorted(achados)

    # 2) bundles Unity: prefixo de comprimento.
    for m in re.finditer(re.escape(b"https://"), dados):
        comp = _unity_length_prefixed(dados, m.start())
        if comp is None:
            continue
        url = dados[m.start():m.start() + comp]
        if alvo in url:
            achados.add(url)
    return sorted(achados)


@dataclass
class EntryPatch:
    entry: str
    replacements: list[dict] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(r["count"] for r in self.replacements)


def patch_blob(dados: bytes, host: str, new_host: str | None = None) -> tuple[bytes, EntryPatch, str]:
    """Aplica todas as trocas num blob, provando comprimento e contagem."""
    relatorio = EntryPatch(entry="")
    saida = dados
    for preimage in find_https_urls(dados, host):
        postimage = downgrade_url(preimage, new_host)
        contagem = saida.count(preimage)
        if contagem == 0:
            continue
        saida = saida.replace(preimage, postimage)
        relatorio.replacements.append({
            "preimage": preimage.decode("ascii", "replace"),
            "postimage": postimage.decode("ascii", "replace"),
            "bytes": len(preimage),
            "count": contagem,
            "target_before": describe_target(preimage),
            "target_after": describe_target(postimage),
        })
    if len(saida) != len(dados):
        raise LabPatchError("o blob mudou de tamanho — nenhum offset pode se deslocar")
    return saida, relatorio, hashlib.sha256(saida).hexdigest()


# ---------------------------------------------------------------------------
# APK
# ---------------------------------------------------------------------------

def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _candidate_entries(zf: zipfile.ZipFile) -> list[str]:
    nomes = [METADATA_ENTRY] if METADATA_ENTRY in zf.namelist() else []
    nomes += [n for n in zf.namelist() if n.startswith("assets/aa/") and n.endswith(".bundle")]
    return nomes


def patch_apk(*, apk_in: Path, apk_out: Path, host: str, allow_insecure_lab: bool,
              from_host: str | None = None, analyze: bool = False) -> dict:
    """Gera o APK de laboratório. Recusa tudo que não for laboratório."""
    if not allow_insecure_lab:
        raise LabPatchError(
            "modo inseguro exige --allow-insecure-lab: este patch rebaixa o wire "
            "para HTTP e só pode existir em rig local isolado")
    if not is_lab_target(host):
        raise LabPatchError(
            f"destino {host!r} não é de laboratório — HTTP só é permitido para "
            "loopback, rede privada, .local ou o alias 10.0.2.2 do emulador")
    if not apk_in.is_file():
        raise LabPatchError(f"APK de entrada não existe: {apk_in}")

    saida = Path(apk_out).resolve()
    if not analyze:
        if (ROOT / "output") in saida.parents:
            raise LabPatchError(
                "artefato de laboratório NUNCA pode nascer em output/ — "
                f"use {LAB_DIR.relative_to(ROOT).as_posix()}/")
        if LAB_DIR.resolve() not in saida.parents and saida.parent != LAB_DIR.resolve():
            raise LabPatchError(
                f"artefato de laboratório só pode ser gravado em "
                f"{LAB_DIR.relative_to(ROOT).as_posix()}/, veio {saida}")
        if MARKER not in saida.name and "LAB" not in saida.name.upper():
            raise LabPatchError(
                "o nome do arquivo tem que identificar o artefato como de "
                "laboratório (ex.: mighty-doom-revival-LAB-HTTP.apk)")

    origem = from_host or host
    relatorio = {
        "marker": MARKER,
        "insecure_http": True,
        "lab_only": True,
        "input_apk": apk_in.name,
        "input_sha256": _sha256(apk_in),
        "from_host": origem,
        "host": host,
        "analyze": analyze,
        "entries": [],
        "total_replacements": 0,
    }

    with zipfile.ZipFile(apk_in) as zin:
        alvos = _candidate_entries(zin)
        if not alvos:
            raise LabPatchError("APK sem metadata IL2CPP nem bundles Addressables")
        patches: dict[str, bytes] = {}
        for nome in alvos:
            dados = zin.read(nome)
            if b"https://" not in dados or origem.encode("ascii") not in dados:
                continue
            novos, detalhe, sha = patch_blob(dados, origem, host if from_host else None)
            if not detalhe.replacements:
                continue
            detalhe.entry = nome
            patches[nome] = novos
            relatorio["entries"].append({
                "entry": nome,
                "size": len(dados),
                "sha256_after": sha,
                "replacements": detalhe.replacements,
            })
            relatorio["total_replacements"] += detalhe.total

        if relatorio["total_replacements"] == 0:
            # Falha segura na segunda execução: nada a trocar significa APK já
            # rebaixado (ou host errado). Nos dois casos, escrever um artefato
            # novo só criaria uma cópia confusa — recusa e não escreve nada.
            raise LabPatchError(
                f"nenhuma URL https:// de {origem!r} encontrada — o APK já foi "
                "rebaixado ou o host de origem está errado; nada foi escrito")

        if analyze:
            relatorio["written"] = False
            return relatorio

        # ---- CRC do catálogo: obrigatório para todo bundle alterado ----------
        # Regra 3 do AGENTS.md e DEAD-ENDS #7. A Unity só valida CRC não-zero;
        # bundle reserializado com CRC antigo no catálogo derruba o load da cena
        # com "CRC Mismatch ... Will not load AssetBundle". Antes isto funcionava
        # por acidente — herdando um catálogo já zerado do APK de entrada.
        bundles_alterados = [n for n in patches if n.startswith("assets/aa/") and n.endswith(".bundle")]
        catalogo_nome = next((n for n in zin.namelist() if n.endswith("assets/aa/catalog.json")), None)
        if bundles_alterados and catalogo_nome is None:
            raise LabPatchError(
                f"{len(bundles_alterados)} bundle(s) alterado(s) e nenhum assets/aa/catalog.json "
                "no APK — sem catálogo não dá para zerar o CRC")
        if bundles_alterados:
            patches[catalogo_nome], relatorio["catalog_crc"] = _zerar_crcs(
                zin.read(catalogo_nome), bundles_alterados)
            relatorio["bundles_alterados"] = bundles_alterados

        saida.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                dados = patches.get(info.filename)
                if dados is None:
                    dados = zin.read(info.filename)
                novo = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                novo.compress_type = info.compress_type
                novo.external_attr = info.external_attr
                zout.writestr(novo, dados)

        # ---- pós-condição: prova, não promessa -------------------------------
        if bundles_alterados:
            restantes = verify_catalog_crc_zero(saida, bundles_alterados)
            if restantes:
                raise LabPatchError(
                    "CRC do catálogo continua não-zero para: " + ", ".join(restantes))
            relatorio["catalog_crc_verified"] = True

    relatorio["written"] = True
    relatorio["output_apk"] = saida.name
    relatorio["output_sha256"] = _sha256(saida)
    return relatorio


def _zerar_crcs(catalogo: bytes, bundles: list[str]) -> tuple[bytes, list[dict]]:
    """Zera o `m_Crc` de cada bundle alterado, pela rotina canônica do projeto.

    Delega para `patch_unity_bundle.zero_catalog_crc`, que faz a substituição
    preservando o comprimento em bytes (o JSON vive em UTF-16LE dentro do base64
    de `m_ExtraDataString`, e deslocar offsets quebraria o catálogo inteiro).
    """
    import tempfile  # noqa: PLC0415
    from patch_unity_bundle import zero_catalog_crc  # noqa: PLC0415

    relatorios: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="revival-lab-crc-") as tmp:
        alvo = Path(tmp) / "catalog.json"
        alvo.write_bytes(catalogo)
        for nome in bundles:
            fake_bundle = Path(tmp) / Path(nome).name
            fake_bundle.write_bytes(b"")     # só o NOME importa: o hash de 32 hex
            info = zero_catalog_crc(alvo, fake_bundle)
            relatorios.append({"bundle": nome, **{k: info.get(k) for k in
                                                  ("zeroed", "matched", "entries", "reason")}})
        return alvo.read_bytes(), relatorios


def verify_catalog_crc_zero(apk: Path, bundles: list[str]) -> list[str]:
    """Bundles cujo `m_Crc` no catálogo do APK AINDA não é zero."""
    import base64  # noqa: PLC0415
    import json as _json  # noqa: PLC0415

    faltando: list[str] = []
    with zipfile.ZipFile(apk) as zf:
        nome_catalogo = next((n for n in zf.namelist() if n.endswith("assets/aa/catalog.json")), None)
        if nome_catalogo is None:
            return [f"{b} (catálogo ausente)" for b in bundles]
        catalogo = _json.loads(zf.read(nome_catalogo).decode("utf-8"))
    extras = catalogo.get("m_ExtraDataString") or ""
    try:
        bruto = base64.b64decode(extras).decode("utf-16-le", "replace")
    except Exception:
        return [f"{b} (m_ExtraDataString ilegível)" for b in bundles]
    for nome in bundles:
        m = re.search(r"([0-9a-f]{32})", Path(nome).name)
        if not m:
            continue
        # Cada AssetBundleRequestOptions carrega o hash e o m_Crc do seu bundle.
        for trecho in re.finditer(r'\{[^{}]*' + m.group(1) + r'[^{}]*\}', bruto):
            crc = re.search(r'"m_Crc"\s*:\s*(\d+)', trecho.group(0))
            if crc and crc.group(1) != "0":
                faltando.append(nome)
                break
    return faltando


def write_lab_network_security(decoded: Path, host: str, *, allow_insecure_lab: bool,
                               revival_host: str = "doom.sualoja.app.br") -> dict:
    """Permite cleartext para o host do rig — SÓ na árvore de laboratório.

    Necessário porque a `RevivalAuthActivity` usa `HttpURLConnection`, ou seja, a
    stack HTTP do **Android**, que honra o `network_security_config`. Desde a API
    28 o padrão é cleartext PROIBIDO, então o `http://` do rig é bloqueado antes
    de sair (medido em 2026-08-20: a Activity mostrou "Sem conexão" e nenhum
    request chegou ao servidor). O cliente Unity não passa por aqui — ele tem
    stack própria, e foi por isso que o jogo funcionou e a Activity não.

    O host público continua com `cleartextTrafficPermitted="false"`: mesmo no
    artefato de laboratório, a Internet nunca fica liberada em texto claro.
    """
    if not allow_insecure_lab:
        raise LabPatchError("cleartext exige --allow-insecure-lab")
    if not is_lab_target(host):
        raise LabPatchError(f"cleartext só para destino de laboratório, não {host!r}")
    alvo = Path(decoded) / "res" / "xml" / "network_security_config.xml"
    if not alvo.parent.is_dir():
        raise LabPatchError(f"árvore sem res/xml: {decoded}")
    conteudo = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<network-security-config>\n'
        f'    <!-- {MARKER}: cleartext liberado APENAS para o rig local. -->\n'
        '    <domain-config cleartextTrafficPermitted="true">\n'
        f'        <domain includeSubdomains="false">{host}</domain>\n'
        '    </domain-config>\n'
        '    <domain-config cleartextTrafficPermitted="false">\n'
        f'        <domain includeSubdomains="true">{revival_host}</domain>\n'
        '        <trust-anchors>\n'
        '            <certificates src="system"/>\n'
        '        </trust-anchors>\n'
        '    </domain-config>\n'
        '</network-security-config>\n'
    )
    alvo.write_text(conteudo, encoding="utf-8")
    return {"path": alvo.as_posix(), "cleartext_host": host,
            "public_host_still_https": True, "marker": MARKER}


def verify_lab_apk(apk: Path, host: str) -> dict:
    """Confere o artefato de laboratório: esquema, host e host oficial zerado."""
    # Só o host da API de GAMEPLAY desqualifica. `slayersclub.bethesda.net` é
    # ancilar e permanece no metadata legitimamente (skill apk-patch) — contá-lo
    # como "oficial" reprovaria todo APK correto.
    from patch_apk import KNOWN_HOSTS, PRIMARY_API_HOST  # noqa: PLC0415

    resultado = {"apk": apk.name, "sha256": _sha256(apk), "host": host,
                 "http_occurrences": 0, "https_occurrences": 0,
                 "official_occurrences": 0, "ancillary_occurrences": 0}
    alvo = re.escape(host.encode("ascii"))
    # O host efetivo pode vir depois de userinfo de padding (`http://u000@host`),
    # então contar a string literal `http://<host>` não serve.
    http_re = re.compile(rb"http://(?:[A-Za-z0-9._~%!$&'()*+,;=:-]*@)?" + alvo)
    https_re = re.compile(rb"https://(?:[A-Za-z0-9._~%!$&'()*+,;=:-]*@)?" + alvo)
    with zipfile.ZipFile(apk) as zf:
        for nome in _candidate_entries(zf):
            dados = zf.read(nome)
            resultado["http_occurrences"] += len(http_re.findall(dados))
            resultado["https_occurrences"] += len(https_re.findall(dados))
            resultado["official_occurrences"] += dados.count(PRIMARY_API_HOST.encode("ascii"))
            for ancilar in KNOWN_HOSTS:
                if ancilar != PRIMARY_API_HOST:
                    resultado["ancillary_occurrences"] += dados.count(ancilar.encode("ascii"))
    resultado["verified"] = (resultado["http_occurrences"] > 0
                             and resultado["official_occurrences"] == 0)
    return resultado


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--apk", type=Path, required=True)
    p.add_argument("--out", type=Path)
    p.add_argument("--host", required=True, help="destino do rig (loopback/privado)")
    p.add_argument("--from-host", help="host atualmente no APK, se for trocar também o host")
    p.add_argument("--allow-insecure-lab", action="store_true",
                   help="OBRIGATÓRIO: declara ciência de que o artefato é inseguro")
    p.add_argument("--analyze", action="store_true", help="não escreve nada")
    p.add_argument("--report", type=Path)
    args = p.parse_args(argv)

    if not args.analyze and not args.out:
        print("ERRO: --out é obrigatório fora do --analyze", file=sys.stderr)
        return 2
    try:
        rel = patch_apk(apk_in=args.apk, apk_out=args.out or Path("x"), host=args.host,
                        from_host=args.from_host,
                        allow_insecure_lab=args.allow_insecure_lab, analyze=args.analyze)
    except LabPatchError as exc:
        print(f"RECUSADO: {exc}", file=sys.stderr)
        return 4
    print(f"[{MARKER}] {rel['total_replacements']} troca(s) em "
          f"{len(rel['entries'])} entrada(s)")
    for entrada in rel["entries"]:
        for r in entrada["replacements"]:
            print(f"  {entrada['entry']}")
            print(f"    {r['preimage']}  ({r['bytes']} bytes)")
            print(f" -> {r['postimage']}  ({r['bytes']} bytes, x{r['count']})")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(rel, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"relatório: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
