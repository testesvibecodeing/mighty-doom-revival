#!/usr/bin/env python3
"""Extrator read-only do global-metadata.dat (IL2CPP v29) do Mighty DOOM 1.13.1.

Produz os dados que alimentam `compatibility.json` e a matriz de endpoints a
partir do binário real do cliente, em vez de listas transcritas à mão:
toda rota `game/*` vem da tabela de string literals do metadata.

Fontes suportadas (uma por invocação):
  --metadata <global-metadata.dat>   arquivo já extraído do APK
  --apk <mighty-doom.apk>            lê a entrada zip do metadata diretamente

Saída JSON em stdout (ou --out <file>):
  { "version": 29, "sanity": "0xFAB11BAF", "string_literals": N,
    "routes": ["game/auth/register", ...] }

Exit codes: 0 ok; 2 uso/entrada inválida; 3 metadata com sanity/version
inesperados (base trocou — não prosiga sem revalidar).
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import zipfile
from pathlib import Path

EXPECTED_SANITY = 0xFAB11BAF
EXPECTED_VERSION = 29
METADATA_ENTRY = "assets/bin/Data/Managed/Metadata/global-metadata.dat"

# v29: pares (offset u32, size i32) nesta ordem, começando no byte 8.
HEADER_FIELDS = (
    "stringLiteral", "stringLiteralData", "string", "events", "properties",
    "methods", "parameterDefaultValues", "fieldDefaultValues",
    "fieldAndParameterDefaultValueData", "fieldMarshaledSizes", "parameters",
    "fields", "genericParameters", "genericMethodConstraints", "nestedTypes",
    "interfaces", "vtableMethods", "interfaceOffsets", "typeDefinitions",
    "images", "assemblies", "fieldRefs", "referencedAssemblies",
    "attributeData", "attributeDataRange",
)


def load_metadata_bytes(source: Path) -> bytes:
    if source.name.lower().endswith((".apk", ".xapk")):
        with zipfile.ZipFile(source) as apk:
            return apk.read(METADATA_ENTRY)
    return source.read_bytes()


def parse_header(data: bytes) -> dict[str, tuple[int, int]]:
    sanity, version = struct.unpack_from("<Ii", data, 0)
    if sanity != EXPECTED_SANITY:
        raise ValueError(f"sanity inesperado: {hex(sanity)}")
    if version != EXPECTED_VERSION:
        raise ValueError(f"versão de metadata inesperada: {version} (esperado {EXPECTED_VERSION})")
    header: dict[str, tuple[int, int]] = {}
    offset = 8
    for name in HEADER_FIELDS:
        header[name] = struct.unpack_from("<Ii", data, offset)
        offset += 8
    return header


def string_literals(data: bytes, header: dict[str, tuple[int, int]]):
    """Gera (texto, índice) de cada literal; pula entradas corrompidas."""
    table_offset, table_size = header["stringLiteral"]
    data_offset, _ = header["stringLiteralData"]
    count = table_size // 8
    for index in range(count):
        length, data_index = struct.unpack_from("<II", data, table_offset + index * 8)
        if length == 0:
            yield "", index
            continue
        start = data_offset + data_index
        yield data[start:start + length].decode("utf-8", errors="replace"), index


def extract_routes(source: Path) -> dict:
    data = load_metadata_bytes(source)
    header = parse_header(data)
    routes = set()
    literal_count = 0
    for text, _ in string_literals(data, header):
        literal_count += 1
        # Rotas de API são literais exatos "game/..." sem espaços ou curingas;
        # isso exclui strings de log/UX que por acaso comecem com "game/".
        if text.startswith("game/") and " " not in text and "\n" not in text:
            routes.add(text)
    return {
        "version": EXPECTED_VERSION,
        "sanity": hex(EXPECTED_SANITY),
        "string_literals": literal_count,
        "routes": sorted(routes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--metadata", type=Path, help="global-metadata.dat já extraído")
    source.add_argument("--apk", type=Path, help="APK contendo o metadata")
    parser.add_argument("--out", type=Path, help="escreve o JSON em vez de stdout")
    args = parser.parse_args()

    path = (args.metadata or args.apk).expanduser().resolve()
    if not path.is_file():
        print(f"ERRO: arquivo não encontrado: {path}", file=sys.stderr)
        return 2

    try:
        result = extract_routes(path)
    except ValueError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 3

    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print(f"{len(result['routes'])} rotas -> {args.out}")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
