#!/usr/bin/env python3
"""Extrator read-only do global-metadata.dat (IL2CPP v29) do Mighty DOOM 1.13.1.

Produz os dados que alimentam `compatibility.json` e a matriz de endpoints a
partir do binário real do cliente, em vez de listas transcritas à mão.

Layout v29 derivado empiricamente contra o metadata real (2026-08-18, ver
probe chain registrada na sessão) e validado por fechamentos exatos:

  header      256 bytes = 8 (sanity u32 + version i32) + 31 regiões de
              (offset u32, size i32). A soma `parameterCount` dos methods
              fecha em 93.356 = contagem da região `parameters` (prova do
              stride 32B e dos offsets 20/30); `nestedTypes`/`interfaces`/
              `vtableMethods` fecham por soma dos u16 de cada typeDef
              (4.669 / 4.953 / 140.237); o fim de `fieldStart+fieldCount`
              fecha em 65.722 e o de `methodStart+methodCount` em 96.077.
  typeDef     88 bytes: name@0 ns@4 byval@8 declaring@12 parent@16
              byref@20 genericContainer@24 flags@28 fieldStart@32
              methodStart@36 eventStart@40 propertyStart@44 nestedStart@48
              interfacesStart@52 vtableStart@56 ifoffStart@60
              u16 method@64 property@66 field@68 event@70 nested@72
              vtable@74 interfaces@76 ifoff@78 | bitfield u32@80 token@84
              declaring@12/parent@16/byval@8 são índices da tabela NATIVA
              il2CppType (inúteis sem o libil2cpp.so) — o nesting legível
              vem da região nestedTypes via nestedStart@48, provado por
              encadeamento exato no metadata real (0 divergências, fim
              4.669 = entradas); parameterStart@12 idem (métodos sem
              parâmetros carregam -1; cadeia fecha em 93.356).
  methods     32 bytes: nameIndex@0 ... token@20 ... parameterStart@12
              ... parameterCount u16@30
  fields      12 bytes: nameIndex@0 typeIndex@4 token@8
  fdv         12 bytes: fieldIndex@0 typeIndex@4 dataIndex@8
  images      40 bytes: nameIndex@0 assemblyIndex@4 typeStart@8 typeCount@12
  defaults    ECMA-335 signed comprimido no blob
              `fieldAndParameterDefaultValueData`: raw par → raw>>1;
              raw ímpar → -((raw+1)>>1). Âncoras do real: Success=1000
              ← varint 2000; System.Handles STD_INPUT/OUTPUT/ERROR
              ← 19/21/23 → -10/-11/-12 (valores Win32).
  enums       detecção estrutural: field[0] == "value__" e TODOS os demais
              fields com default numérico. No metadata real: 1.555 de
              1.555 candidatos fecham, zero falsos positivos.
  wire names  strings `len<<1` dentro do blob `attributeData`.

Regiões 12-14/22-23/25-27/30 não têm uso neste extrator; os nomes posicionais
entre 12-14 não foram fechados por derivação (uma seção extra do v29 fica
entre `fields` e `nestedTypes`) e não são lidas em nenhum modo.

Fontes suportadas (uma por invocação):
  --metadata <global-metadata.dat>   arquivo já extraído do APK
  --apk <mighty-doom.apk>            lê a entrada zip do metadata diretamente

Modos (acumuláveis; sem modo algum, extrai rotas — compatibilidade):
  --routes           literais "game/*" (formato histórico de compatibility.json)
  --enums            enums com valores resolvidos (filtro opcional --pattern)
  --dtos             types *Request/*Response/*Dto/*Data com fields e wire
                     fallback snake_case (nenhum tipo C# resolvido: isso
                     exigiria a tabela il2CppType do binário nativo)
  --wire-names       strings snake_case do attributeData (pareamento com
                     fields é A VERIFICAR — não inventado aqui)
  --response-codes   enums *ResponseCode + sanity das âncoras do protocolo
  --all              todos acima + sanity de gate (116 rotas, rotas-âncora
                     e Ubu.GameApi.ResponseCode Success=1000 / JWT 2110-2113)

AVISO: --enums/--dtos/--wire-names sobre o APK real expõem identificadores
do assembly do jogo — nunca versione os dumps gerados.

Exit codes: 0 ok; 2 uso/entrada inválida; 3 metadata reprovado em
sanity/validação (base trocou — não prosiga sem revalidar; offsets nunca
são ajustados por tentativa).
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

EXPECTED_SANITY = 0xFAB11BAF
EXPECTED_VERSION = 29
METADATA_ENTRY = "assets/bin/Data/Managed/Metadata/global-metadata.dat"
REGION_COUNT = 31

# 31 regiões (offset u32, size i32) a partir do byte 8. Nomes derivados por
# fechamento nas posições usadas; 12-14/22-23/25-30 são posicionais (docstring).
HEADER_FIELDS = (
    "stringLiteral", "stringLiteralData", "string",                     # 0-2
    "events", "properties", "methods",                                  # 3-5
    "parameterDefaultValues", "fieldDefaultValues",                     # 6-7
    "fieldAndParameterDefaultValueData", "fieldMarshaledSizes",         # 8-9
    "parameters", "fields",                                             # 10-11
    "genericParameters", "genericMethodConstraints", "unknownSection14",  # 12-14
    "nestedTypes", "interfaces", "vtableMethods", "interfaceOffsets",   # 15-18
    "typeDefinitions", "images", "assemblies",                          # 19-21
    "fieldRefs", "attributeDataRange",                                  # 22-23
    "attributeData",                                                    # 24
    "unresolvedVirtualCallParameterTypes",                              # 25
    "unresolvedVirtualCallParameterRanges", "unknownSection27",         # 26-27
    "unknownSection28", "unknownSection29", "unknownSection30",         # 28-30
)

# Tamanho de entrada das regiões cujo stride foi provado por fechamento.
REGION_ENTRY_SIZES = {
    "stringLiteral": 8,
    "methods": 32,
    "fieldDefaultValues": 12,
    "parameters": 12,
    "fields": 12,
    "nestedTypes": 4,
    "interfaces": 4,
    "vtableMethods": 4,
    "typeDefinitions": 88,
    "images": 40,
}

TYPEDEF_SIZE = 88
TD_NAME = 0
TD_NAMESPACE = 4
TD_PARENT = 16
TD_FIELD_START = 32
TD_METHOD_START = 36
TD_METHOD_COUNT = 64
TD_FIELD_COUNT = 68
TD_NESTED_START = 48
TD_NESTED_COUNT = 72
TD_VTABLE_COUNT = 74
TD_INTERFACES_COUNT = 76
TD_TOKEN = 84

METHOD_SIZE = 32
METHOD_PARAM_START = 12
METHOD_PARAM_COUNT = 30  # u16

FIELD_SIZE = 12
FDV_SIZE = 12
IMAGE_SIZE = 40
IMG_NAME = 0
IMG_ASSEMBLY = 4
IMG_TYPE_START = 8
IMG_TYPE_COUNT = 12

# Âncoras de gate (plano §19; valores CONFIRMADOS em server/src/response-codes.js)
EXPECTED_ROUTE_COUNT = 116
EXPECTED_ROUTES = ("game/auth/login-device", "game/events/get-schedule")
RESPONSE_CODE_ENUM = "Ubu.GameApi.ResponseCode"
RESPONSE_ANCHORS = {
    "Success": 1000,
    "JwtInvalid": 2110,
    "JwtExpired": 2111,
    "JwtBadSignature": 2112,
    "JwtBadSub": 2113,
}

DTO_SUFFIXES = ("Request", "Response", "Dto", "Data")
WIRE_NAME_RE = re.compile(rb"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")


class MetadataError(ValueError):
    """Metadata reprovado em sanity/validação — abortar, nunca ajustar."""


@dataclass(slots=True)
class TypeDefRow:
    index: int
    name: str
    namespace: str
    field_start: int
    field_count: int
    method_start: int
    method_count: int
    token: int


def load_metadata_bytes(source: Path | str) -> bytes:
    source = Path(source)
    if source.name.lower().endswith((".apk", ".xapk")):
        with zipfile.ZipFile(source) as apk:
            return apk.read(METADATA_ENTRY)
    return source.read_bytes()


def parse_header(data: bytes) -> dict[str, tuple[int, int]]:
    if len(data) < 8:
        raise MetadataError("metadata truncado antes do header")
    sanity, version = struct.unpack_from("<Ii", data, 0)
    if sanity != EXPECTED_SANITY:
        raise MetadataError(f"sanity inesperado: {hex(sanity)}")
    if version != EXPECTED_VERSION:
        raise MetadataError(f"versão de metadata inesperada: {version} (esperado {EXPECTED_VERSION})")
    first_offset = struct.unpack_from("<I", data, 8)[0]
    if first_offset < 8 or (first_offset - 8) % 8 != 0:
        raise MetadataError(f"offset da primeira região inválido: {first_offset}")
    if (first_offset - 8) // 8 != REGION_COUNT:
        raise MetadataError(
            f"contagem de regiões inesperada: {(first_offset - 8) // 8} (esperado {REGION_COUNT})"
        )
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


def read_compressed_uint(blob: bytes, pos: int) -> tuple[int, int]:
    """Inteiro sem sinal comprimido ECMA-335 (formato dos defaults v29)."""
    if pos >= len(blob):
        raise MetadataError(f"blob truncado em +{pos}")
    first = blob[pos]
    if first < 0x80:
        return first, pos + 1
    if first < 0xC0:
        if pos + 1 >= len(blob):
            raise MetadataError(f"blob truncado em +{pos}")
        return ((first & 0x3F) << 8) | blob[pos + 1], pos + 2
    if pos + 3 >= len(blob):
        raise MetadataError(f"blob truncado em +{pos}")
    value = ((first & 0x1F) << 24) | (blob[pos + 1] << 16) | (blob[pos + 2] << 8) | blob[pos + 3]
    if value & 0xE0000000:
        raise MetadataError(f"varint de 4 bytes com bits altos: {value:#x}")
    return value, pos + 4


def snake_case(name: str) -> str:
    """Fallback SnakeCaseNamingStrategy (Newtonsoft): separa maiúsculas que
    iniciam palavra — AccessToken→access_token, APIVersion→api_version,
    XpData→xp_data, ID→id."""
    out: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i:
            prev = name[i - 1]
            nxt = name[i + 1] if i + 1 < len(name) else ""
            if prev.islower() or prev.isdigit() or (nxt.islower() and prev.isupper()):
                out.append("_")
        out.append(ch.lower())
    return "".join(out)


class MetadataFile:
    """Metadata v29 validado e indexado (somente leitura)."""

    def __init__(self, data: bytes):
        self.data = data
        self.regions = parse_header(data)
        self._validate_regions()
        self.typedefs: list[TypeDefRow] = []
        self._fdv_by_field: dict[int, int] = {}
        self._parent_of: dict[int, int] = {}
        self._children_of: dict[int, list[int]] = {}
        self._qualified_cache: dict[int, str] = {}
        self._parse_content()
        self._validate_closures()

    @classmethod
    def from_source(cls, source: Path | str) -> "MetadataFile":
        return cls(load_metadata_bytes(source))

    # ------------------------------------------------------------------ validação

    def _validate_regions(self) -> None:
        end = len(self.data)
        spans: list[tuple[str, int, int]] = []
        for name in HEADER_FIELDS:
            offset, size = self.regions[name]
            if size < 0:
                raise MetadataError(f"região {name} com size negativo: {size}")
            if size == 0:
                continue
            if offset < 8 + 8 * REGION_COUNT:
                raise MetadataError(f"região {name} começa dentro do header: {offset}")
            if offset + size > end:
                raise MetadataError(
                    f"região {name} ultrapassa o arquivo: fim {offset + size} > {end}"
                )
            entry = REGION_ENTRY_SIZES.get(name)
            if entry and size % entry != 0:
                raise MetadataError(
                    f"região {name} com size {size} não múltiplo da entrada de {entry} bytes"
                )
            spans.append((name, offset, offset + size))
        for i, (name_a, start_a, end_a) in enumerate(spans):
            for name_b, start_b, end_b in spans[i + 1:]:
                if start_a < end_b and start_b < end_a:
                    raise MetadataError(f"regiões sobrepostas: {name_a} × {name_b}")
        if self.regions["fieldDefaultValues"][1] and not self.regions["fieldAndParameterDefaultValueData"][1]:
            raise MetadataError("fieldDefaultValues sem blob de defaults")

    def _parse_content(self) -> None:
        data = self.data
        str_offset = self.regions["string"][0]
        fdv_offset, fdv_size = self.regions["fieldDefaultValues"]
        for i in range(fdv_size // FDV_SIZE):
            field_index, _type_index, data_index = struct.unpack_from(
                "<iii", data, fdv_offset + i * FDV_SIZE
            )
            self._fdv_by_field[field_index] = data_index

        td_offset, td_size = self.regions["typeDefinitions"]
        count = td_size // TYPEDEF_SIZE
        rows: list[TypeDefRow] = []
        for i in range(count):
            base = td_offset + i * TYPEDEF_SIZE
            name_idx, ns_idx = struct.unpack_from("<ii", data, base + TD_NAME)
            field_start, method_start = struct.unpack_from("<ii", data, base + TD_FIELD_START)
            field_count, = struct.unpack_from("<H", data, base + TD_FIELD_COUNT)
            method_count, = struct.unpack_from("<H", data, base + TD_METHOD_COUNT)
            token, = struct.unpack_from("<I", data, base + TD_TOKEN)
            rows.append(TypeDefRow(
                index=i,
                name=self.string(name_idx, str_offset),
                namespace=self.string(ns_idx, str_offset),
                field_start=field_start,
                field_count=field_count,
                method_start=method_start,
                method_count=method_count,
                token=token,
            ))
        self.typedefs = rows
        self.n_typedefs = count
        self.n_fields = self.regions["fields"][1] // FIELD_SIZE
        self.n_methods = self.regions["methods"][1] // METHOD_SIZE
        self.n_parameters = self.regions["parameters"][1] // 12

        # nesting: a região nestedTypes encadeia por ordem de typedef (como
        # images.typeStart) — declaring@12 aponta para a tabela NATIVA
        # il2CppType e não é legível sem o libil2cpp.so.
        nt_offset = self.regions["nestedTypes"][0]
        for td in rows:
            base = td_offset + td.index * TYPEDEF_SIZE
            nested_start, = struct.unpack_from("<i", data, base + TD_NESTED_START)
            nested_count, = struct.unpack_from("<H", data, base + TD_NESTED_COUNT)
            if nested_count == 0:
                continue
            for j in range(nested_count):
                child, = struct.unpack_from(
                    "<i", data, nt_offset + (nested_start + j) * 4)
                self._parent_of[child] = td.index
                self._children_of.setdefault(td.index, []).append(child)

    def _validate_closures(self) -> None:
        """Fechamentos provados no metadata real — qualquer divergência aborta."""
        data = self.data
        max_field_end = max_method_end = 0
        sum_nested = sum_vtable = sum_interfaces = 0
        td_offset = self.regions["typeDefinitions"][0]
        for row in self.typedefs:
            max_field_end = max(max_field_end, row.field_start + row.field_count)
            max_method_end = max(max_method_end, row.method_start + row.method_count)
            base = td_offset + row.index * TYPEDEF_SIZE
            sum_nested += struct.unpack_from("<H", data, base + TD_NESTED_COUNT)[0]
            sum_vtable += struct.unpack_from("<H", data, base + TD_VTABLE_COUNT)[0]
            sum_interfaces += struct.unpack_from("<H", data, base + TD_INTERFACES_COUNT)[0]
        if self.typedefs:
            if max_field_end != self.n_fields:
                raise MetadataError(
                    f"fim de fields {max_field_end} != contagem da tabela {self.n_fields}"
                )
            if max_method_end != self.n_methods:
                raise MetadataError(
                    f"fim de methods {max_method_end} != contagem da tabela {self.n_methods}"
                )

        m_offset, m_size = self.regions["methods"]
        sum_params = sum(
            struct.unpack_from("<H", data, m_offset + i * METHOD_SIZE + METHOD_PARAM_COUNT)[0]
            for i in range(m_size // METHOD_SIZE)
        )
        if sum_params != self.n_parameters:
            raise MetadataError(
                f"soma de parameterCount {sum_params} != contagem da tabela {self.n_parameters}"
            )
        expected_param_start = 0
        for i in range(m_size // METHOD_SIZE):
            base = m_offset + i * METHOD_SIZE
            count, = struct.unpack_from("<H", data, base + METHOD_PARAM_COUNT)
            pstart, = struct.unpack_from("<i", data, base + METHOD_PARAM_START)
            if count == 0:
                if pstart != -1:
                    raise MetadataError(
                        f"method[{i}] sem parâmetros com parameterStart {pstart} != -1"
                    )
                continue
            if pstart != expected_param_start:
                raise MetadataError(
                    f"parameterStart de method[{i}] {pstart} fora do encadeamento "
                    f"(esperado {expected_param_start})"
                )
            expected_param_start += count
        if expected_param_start != self.n_parameters:
            raise MetadataError(
                f"fim da cadeia de parameterStart {expected_param_start} != {self.n_parameters}"
            )

        # Encadeamento da região nestedTypes (prova do offset nestedStart@48):
        # na ordem dos typedefs, os alcances somam exatamente a tabela.
        nt_offset, nt_size = self.regions["nestedTypes"]
        nt_entries = nt_size // 4
        expected_nested_start = 0
        for row in self.typedefs:
            base = td_offset + row.index * TYPEDEF_SIZE
            nested_start, = struct.unpack_from("<i", data, base + TD_NESTED_START)
            nested_count, = struct.unpack_from("<H", data, base + TD_NESTED_COUNT)
            if nested_count == 0:
                continue
            if nested_start != expected_nested_start:
                raise MetadataError(
                    f"nestedStart do typedef {row.index} {nested_start} fora do "
                    f"encadeamento (esperado {expected_nested_start})"
                )
            if nested_start + nested_count > nt_entries:
                raise MetadataError(
                    f"alcance nestedTypes do typedef {row.index} ultrapassa a tabela"
                )
            expected_nested_start += nested_count
        if expected_nested_start != nt_entries:
            raise MetadataError(
                f"fim da cadeia de nestedTypes {expected_nested_start} != entradas {nt_entries}"
            )

        for name, total in (
            ("nestedTypes", sum_nested),
            ("vtableMethods", sum_vtable),
            ("interfaces", sum_interfaces),
        ):
            entries = self.regions[name][1] // 4
            if entries != total:
                raise MetadataError(f"soma de u16 de {name} {total} != entradas {entries}")

        img_offset, img_size = self.regions["images"]
        expected_start = 0
        for i in range(img_size // IMAGE_SIZE):
            base = img_offset + i * IMAGE_SIZE
            type_start, type_count = struct.unpack_from("<ii", data, base + IMG_TYPE_START)
            if type_start != expected_start or type_count < 0:
                raise MetadataError(
                    f"image[{i}] com typeStart {type_start} fora do encadeamento (esperado {expected_start})"
                )
            expected_start += type_count
        if expected_start != self.n_typedefs:
            raise MetadataError(
                f"soma de typeCount das images {expected_start} != typedefs {self.n_typedefs}"
            )
        if self.n_typedefs and not img_size:
            raise MetadataError("typedefs sem nenhuma image")

    # ------------------------------------------------------------------ leitura

    def string(self, index: int, str_offset: int | None = None) -> str:
        base = self.regions["string"][0] if str_offset is None else str_offset
        end = self.data.find(b"\x00", base + index)
        return self.data[base + index:end].decode("utf-8", "replace")

    def field_name(self, field_index: int) -> str:
        fields_offset = self.regions["fields"][0]
        name_index, = struct.unpack_from("<i", self.data, fields_offset + field_index * FIELD_SIZE)
        return self.string(name_index)

    def field_token(self, field_index: int) -> int:
        fields_offset = self.regions["fields"][0]
        token, = struct.unpack_from("<I", self.data, fields_offset + field_index * FIELD_SIZE + 8)
        return token

    def read_default(self, data_index: int) -> int:
        """Valor default de enum como int com sinal.

        ECMA-335 signed comprimido, derivado de âncoras do metadata real:
        raw par → raw>>1 (Success=1000 ← 2000; JwtInvalid=2110 ← 4220);
        raw ímpar → -((raw+1)>>1) (Sign.Negative=1 → -1; System.Handles
        STD_INPUT/OUTPUT/ERROR = 19/21/23 → -10/-11/-12, os valores Win32).
        """
        blob_offset, blob_size = self.regions["fieldAndParameterDefaultValueData"]
        if not 0 <= data_index < blob_size:
            raise MetadataError(f"dataIndex {data_index} fora do blob de defaults")
        raw, _ = read_compressed_uint(self.data, blob_offset + data_index)
        if raw & 1:
            return -((raw + 1) >> 1)
        return raw >> 1

    def assembly_of_typedef(self, index: int) -> str:
        img_offset, img_size = self.regions["images"]
        for i in range(img_size // IMAGE_SIZE):
            base = img_offset + i * IMAGE_SIZE
            type_start, type_count = struct.unpack_from("<ii", self.data, base + IMG_TYPE_START)
            if type_start <= index < type_start + type_count:
                name_index, = struct.unpack_from("<i", self.data, base + IMG_NAME)
                return self.string(name_index)
        return "?"

    def parent_of(self, td: TypeDefRow) -> TypeDefRow | None:
        """Tipo externo (nested) lido da região nestedTypes — ou None."""
        pai = self._parent_of.get(td.index)
        return self.typedefs[pai] if pai is not None else None

    def children_of(self, td: TypeDefRow) -> list[TypeDefRow]:
        return [self.typedefs[i] for i in self._children_of.get(td.index, [])]

    def qualified_name(self, td: TypeDefRow) -> str:
        """Nome completo com cadeia de declaring types (namespace só na raiz).

        Derivado da região nestedTypes; guardião de ciclo por segurança (a
        prova de encadeamento já impõe árvore).
        """
        if td.index in self._qualified_cache:
            return self._qualified_cache[td.index]
        partes: list[str] = []
        atual = td
        vistos: set[int] = set()
        while True:
            if atual.index in vistos:
                raise MetadataError(f"ciclo de declaring no typedef {atual.index}")
            vistos.add(atual.index)
            partes.append(atual.name)
            pai = self._parent_of.get(atual.index)
            if pai is None:
                if atual.namespace:
                    partes.append(atual.namespace)
                break
            atual = self.typedefs[pai]
        qualificado = ".".join(reversed(partes))
        self._qualified_cache[td.index] = qualificado
        return qualificado

    def methods_of(self, td: TypeDefRow) -> list[dict]:
        """Métodos do tipo com nomes de parâmetros (nomes: metadata).

        Tipos C# (retorno e parâmetros) não são resolvíveis sem a tabela
        il2CppType do libil2cpp.so — saem como `unresolved`, nunca adivinhados.
        """
        m_offset = self.regions["methods"][0]
        p_offset = self.regions["parameters"][0]
        saida: list[dict] = []
        for mi in range(td.method_start, td.method_start + td.method_count):
            base = m_offset + mi * METHOD_SIZE
            name_index, = struct.unpack_from("<i", self.data, base)
            pstart, = struct.unpack_from("<i", self.data, base + METHOD_PARAM_START)
            pcount, = struct.unpack_from("<H", self.data, base + METHOD_PARAM_COUNT)
            parametros = []
            for pi in range(pstart, pstart + pcount):
                pname, = struct.unpack_from("<i", self.data, p_offset + pi * 12)
                parametros.append({
                    "name": self.string(pname),
                    "type": "unresolved",
                    "type_source": "unresolved",
                })
            saida.append({
                "name": self.string(name_index),
                "parameters": parametros,
                "return_type": "unresolved",
                "return_type_source": "unresolved",
            })
        return saida

    def iter_enums(self):
        """Gera (typedef, [(field_name, valor), ...]) para enums estruturais."""
        for td in self.typedefs:
            if td.field_count < 2:
                continue
            if self.field_name(td.field_start) != "value__":
                continue
            members: list[tuple[str, int]] = []
            ok = True
            for fi in range(td.field_start + 1, td.field_start + td.field_count):
                data_index = self._fdv_by_field.get(fi)
                if data_index is None:
                    ok = False
                    break
                members.append((self.field_name(fi), self.read_default(data_index)))
            if ok:
                yield td, members

    def validation_summary(self) -> dict:
        return {
            "regions": REGION_COUNT,
            "typedefs": self.n_typedefs,
            "fields": self.n_fields,
            "methods": self.n_methods,
            "parameters": self.n_parameters,
            "field_defaults": len(self._fdv_by_field),
        }


# ---------------------------------------------------------------------- modos

def routes_payload(mf: MetadataFile) -> dict:
    routes = set()
    literal_count = 0
    for text, _ in string_literals(mf.data, mf.regions):
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


def extract_routes(source: Path | str) -> dict:
    return routes_payload(MetadataFile.from_source(source))


def _matches(mf: MetadataFile, td: TypeDefRow, pattern: str | None) -> bool:
    """Casa o padrão contra o qualified_name — tipos aninhados são achados
    pelo tipo externo (ex.: --pattern GearApi acha GearApi.UpgradeResponse)."""
    if not pattern:
        return True
    return pattern.lower() in mf.qualified_name(td).lower()


def extract_enums(mf: MetadataFile, pattern: str | None = None) -> dict:
    enums = []
    for td, members in mf.iter_enums():
        if not _matches(mf, td, pattern):
            continue
        enums.append({
            "typedef": td.index,
            "namespace": td.namespace,
            "name": td.name,
            "qualified_name": mf.qualified_name(td),
            "token": td.token,
            "fields": [{"name": name, "value": value} for name, value in members],
        })
    return {"version": EXPECTED_VERSION, "sanity": hex(EXPECTED_SANITY), "enums": enums}


def extract_response_codes(mf: MetadataFile) -> dict:
    payload = extract_enums(mf, "ResponseCode")
    failures: list[str] = []
    target = next(
        (e for e in payload["enums"] if f"{e['namespace']}.{e['name']}" == RESPONSE_CODE_ENUM),
        None,
    )
    if target is None:
        failures.append(f"âncora ausente: enum {RESPONSE_CODE_ENUM} não encontrado")
    else:
        values = {f["name"]: f["value"] for f in target["fields"]}
        for name, expected in RESPONSE_ANCHORS.items():
            got = values.get(name)
            if got != expected:
                failures.append(
                    f"{RESPONSE_CODE_ENUM}.{name}={got!r} (esperado {expected})"
                )
    payload["sanity_checks"] = {"ok": not failures, "failures": failures}
    return payload


def extract_dtos(mf: MetadataFile, pattern: str | None = None) -> dict:
    """DTOs e contêineres de DTOs com contratos focáveis por --pattern.

    Um tipo entra na lista quando é um DTO (sufixo *Request/*Response/*Dto/
    *Data com fields) OU quando possui tipos aninhados que são DTOs — é o que
    faz `--pattern GearApi` devolver o tipo externo (com métodos e parâmetros)
    junto dos responses aninhados dele. O qualified_name diferencia homônimos:
    GearApi.UpgradeResponse e ArmoryApi.UpgradeResponse não se misturam.
    """
    dtos = []
    for td in mf.typedefs:
        if not _matches(mf, td, pattern):
            continue
        is_dto = td.field_count > 0 and td.name.endswith(DTO_SUFFIXES)
        nested_dtos = [
            filho for filho in mf.children_of(td)
            if filho.field_count > 0 and filho.name.endswith(DTO_SUFFIXES)
        ]
        if not (is_dto or nested_dtos):
            continue
        fields = []
        for fi in range(td.field_start, td.field_start + td.field_count):
            name = mf.field_name(fi)
            fields.append({
                "name": name,
                "token": mf.field_token(fi),
                "wire": snake_case(name),
                "wire_source": "fallback_snakecase",
                "type": "unresolved",
                "type_source": "unresolved",
            })
        pai = mf.parent_of(td)
        dtos.append({
            "typedef": td.index,
            "namespace": td.namespace,
            "name": td.name,
            "declaring_type": pai.name if pai else None,
            "qualified_name": mf.qualified_name(td),
            "assembly": mf.assembly_of_typedef(td.index),
            "token": td.token,
            "field_count": td.field_count,
            "fields": fields,
            "methods": mf.methods_of(td),
            "nested": [
                {"name": filho.name, "qualified_name": mf.qualified_name(filho)}
                for filho in nested_dtos
            ],
        })
    return {
        "version": EXPECTED_VERSION,
        "sanity": hex(EXPECTED_SANITY),
        "wire_note": (
            "wire = fallback SnakeCaseNamingStrategy; overrides de JsonProperty "
            "exigem pareamento attributeDataRange×field ainda A VERIFICAR"
        ),
        "provenance": {
            "name": "metadata",
            "wire": "fallback_snakecase",
            "type": "unresolved",
            "note": (
                "tipos C# exigem a tabela il2CppType do libil2cpp.so; "
                "binding rota->método não é demonstrável só do metadata"
            ),
        },
        "dtos": dtos,
    }


def extract_wire_names(mf: MetadataFile) -> dict:
    blob_offset, blob_size = mf.regions["attributeData"]
    blob = mf.data[blob_offset:blob_offset + blob_size]
    found: set[bytes] = set()
    i = 0
    while i < len(blob) - 2:
        prefix = blob[i]
        if prefix and prefix % 2 == 0 and 2 <= prefix <= 120:
            length = prefix >> 1
            candidate = blob[i + 1:i + 1 + length]
            if candidate and all(33 <= b < 127 for b in candidate) and WIRE_NAME_RE.fullmatch(candidate):
                found.add(candidate)
                i += 1 + length
                continue
        i += 1
    return {
        "version": EXPECTED_VERSION,
        "sanity": hex(EXPECTED_SANITY),
        "wire_names": sorted(name.decode() for name in found),
        "note": (
            "strings len<<1 extraídas do attributeData; pareamento com fields "
            "é A VERIFICAR — este modo não assume nada sobre eles"
        ),
    }


def all_payload(mf: MetadataFile) -> dict:
    routes = routes_payload(mf)
    response = extract_response_codes(mf)
    failures: list[str] = list(response["sanity_checks"]["failures"])
    if len(routes["routes"]) != EXPECTED_ROUTE_COUNT:
        failures.append(
            f"contagem de rotas {len(routes['routes'])} != {EXPECTED_ROUTE_COUNT}"
        )
    for route in EXPECTED_ROUTES:
        if route not in routes["routes"]:
            failures.append(f"rota-âncora ausente: {route}")
    return {
        "version": EXPECTED_VERSION,
        "sanity": hex(EXPECTED_SANITY),
        "validation": mf.validation_summary(),
        "string_literals": routes["string_literals"],
        "routes": routes["routes"],
        "response_codes": response,
        "dtos": extract_dtos(mf),
        "wire_names": extract_wire_names(mf)["wire_names"],
        "sanity_checks": {"ok": not failures, "failures": failures},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--metadata", type=Path, help="global-metadata.dat já extraído")
    source.add_argument("--apk", type=Path, help="APK contendo o metadata")
    parser.add_argument("--out", type=Path, help="escreve o JSON em vez de stdout")
    parser.add_argument("--pattern", help="substring case-insensitive (namespace.nome) p/ --enums/--dtos")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--routes", action="store_true", help="literais game/* (padrão)")
    modes.add_argument("--enums", action="store_true", help="enums com valores")
    modes.add_argument("--dtos", action="store_true", help="types *Request/*Response/*Dto/*Data")
    modes.add_argument("--wire-names", action="store_true", help="strings snake_case do attributeData")
    modes.add_argument("--response-codes", action="store_true", help="enums *ResponseCode + sanity")
    modes.add_argument("--all", action="store_true", help="tudo + sanity de gate")
    args = parser.parse_args()

    path = (args.metadata or args.apk).expanduser().resolve()
    if not path.is_file():
        print(f"ERRO: arquivo não encontrado: {path}", file=sys.stderr)
        return 2

    try:
        mf = MetadataFile.from_source(path)
        if args.enums:
            result = extract_enums(mf, args.pattern)
            summary = f"{len(result['enums'])} enums"
        elif args.dtos:
            result = extract_dtos(mf, args.pattern)
            summary = f"{len(result['dtos'])} dtos"
        elif args.wire_names:
            result = extract_wire_names(mf)
            summary = f"{len(result['wire_names'])} wire names"
        elif args.response_codes:
            result = extract_response_codes(mf)
            summary = f"{len(result['enums'])} enums ResponseCode"
        elif args.all:
            result = all_payload(mf)
            enums = extract_enums(mf, args.pattern)
            result["enums"] = enums["enums"]
            summary = (
                f"{len(result['routes'])} rotas, {len(result['enums'])} enums, "
                f"{len(result['dtos']['dtos'])} dtos, {len(result['wire_names'])} wire names"
            )
        else:
            result = routes_payload(mf)
            summary = f"{len(result['routes'])} rotas"
    except (ValueError, struct.error) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 3

    sanity = result.get("sanity_checks")
    if sanity and not sanity["ok"]:
        for failure in sanity["failures"]:
            print(f"SANITY FALHOU: {failure}", file=sys.stderr)

    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print(f"{summary} -> {args.out}")
    else:
        sys.stdout.write(payload)
    return 3 if sanity and not sanity["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
