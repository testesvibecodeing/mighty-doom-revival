#!/usr/bin/env python3
"""Testes do extrator dump_il2cpp_metadata.py com metadata sintético.

O builder completo (build_full_metadata) monta um v29 coerente com TODAS as
tabelas usadas pelo extrator, fechando as mesmas validações do arquivo real.
Identificadores são Synthetic*; as âncoras de protocolo (Ubu.GameApi.ResponseCode,
Success=1000, JWT 2110-2113) são interface já documentada em
server/src/response-codes.js — nenhum material proprietário aqui.
"""
from __future__ import annotations

import contextlib
import io
import struct
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dump_il2cpp_metadata as dump  # noqa: E402


def build_synthetic_metadata(literals: list[bytes], filler: bytes = b"\x00" * 16) -> bytes:
    """Monta um global-metadata.dat v29 mínimo com a tabela de literals dada."""
    data_blob = b"".join(literals)
    table = b"".join(struct.pack("<II", len(item), offset) for offset, item in
                     ((sum(len(x) for x in literals[:i]), item) for i, item in enumerate(literals)))
    header_size = 8 + 8 * len(dump.HEADER_FIELDS)
    literal_offset = header_size
    literal_data_offset = literal_offset + len(table)
    string_offset = literal_data_offset + len(data_blob)

    out = bytearray()
    out += struct.pack("<Ii", dump.EXPECTED_SANITY, dump.EXPECTED_VERSION)
    out += struct.pack("<Ii", literal_offset, len(table))
    out += struct.pack("<Ii", literal_data_offset, len(data_blob))
    out += struct.pack("<Ii", string_offset, len(filler))
    for _ in dump.HEADER_FIELDS[3:]:
        out += struct.pack("<Ii", 0, 0)
    assert len(out) == header_size
    out += table + data_blob + filler
    return bytes(out)


def compress(value: int) -> bytes:
    """Codificador ECMA-335 signed espelho do read_default.

    v>=0 → raw = v<<1; v<0 → raw = (-v<<1)-1 (âncoras do real:
    -1→1, -10→19, -11→21, -12→23); raw segue como varint unsigned.
    """
    raw = (value << 1) if value >= 0 else ((-value << 1) - 1)
    if raw < 0x80:
        return bytes([raw])
    if raw < 0x4000:
        return bytes([0x80 | (raw >> 8), raw & 0xFF])
    return bytes([0xC0 | (raw >> 24), (raw >> 16) & 0xFF, (raw >> 8) & 0xFF, raw & 0xFF])


def build_full_metadata(
    *,
    n_routes: int = 116,
    response_values: dict[str, int] | None = None,
    break_region: str | None = None,
) -> bytes:
    """Monta um metadata v29 completo e coerente (5 typedefs, 2 methods, 1 image).

    break_region injura uma violação específica para os testes de validação.
    """
    values = dict(dump.RESPONSE_ANCHORS)
    values["NotReceived"] = 0
    values["ClientVersionNotSupported"] = 2010
    if response_values:
        values.update(response_values)

    # ---- tabela de strings (nomes usados por fields/methods/typedefs/images)
    names = [
        "", "value__",
        "SyntheticSuccess", "SyntheticClientVersionNotSupported",
        "Success", "JwtInvalid", "JwtExpired", "JwtBadSignature", "JwtBadSub",
        "NotReceived", "AccessToken", "Xp", "APIVersion",
        "SyntheticValue", "SyntheticMissing",
        "SyntheticNone", "SyntheticStdIn", "SyntheticStdOut", "SyntheticStdErr",
        "SyntheticEnum", "ResponseCode", "SyntheticDtoRequest",
        "SyntheticBrokenEnum", "SyntheticNotEnum",
        "Synthetic.Api", "Ubu.GameApi", "SyntheticAssembly.dll",
        ".ctor", "SyntheticMethod",
    ]
    str_offset_of: dict[str, int] = {}
    string_blob = bytearray()
    for name in names:
        str_offset_of[name] = len(string_blob)
        string_blob += name.encode() + b"\x00"

    # ---- fields por typedef na ordem: (nome, valor_default | None)
    typedefs: list[dict] = [
        {"name": "SyntheticEnum", "ns": "", "fields": [
            ("value__", None), ("SyntheticSuccess", 1000),
            ("SyntheticClientVersionNotSupported", 2010),
            ("SyntheticNone", -1), ("SyntheticStdIn", -10),
            ("SyntheticStdOut", -11), ("SyntheticStdErr", -12)],
         "methods": (0, 1)},
        {"name": "ResponseCode", "ns": "Ubu.GameApi", "fields": [
            ("value__", None), ("Success", values["Success"]),
            ("JwtInvalid", values["JwtInvalid"]), ("JwtExpired", values["JwtExpired"]),
            ("JwtBadSignature", values["JwtBadSignature"]),
            ("JwtBadSub", values["JwtBadSub"]), ("NotReceived", values["NotReceived"])],
         "methods": (1, 1)},
        {"name": "SyntheticDtoRequest", "ns": "Synthetic.Api", "fields": [
            ("AccessToken", None), ("Xp", None), ("APIVersion", None)],
         "methods": (0, 0)},
        {"name": "SyntheticBrokenEnum", "ns": "", "fields": [
            ("value__", None), ("SyntheticValue", 1), ("SyntheticMissing", None)],
         "methods": (0, 0)},
        {"name": "SyntheticNotEnum", "ns": "", "fields": [
            ("SyntheticValue", 1), ("SyntheticSuccess", 1000)],
         "methods": (0, 0)},
    ]

    fields_blob = bytearray()
    defaults_blob = bytearray()
    fdv_blob = bytearray()
    field_index = 0
    for td in typedefs:
        td["field_start"] = field_index
        for fname, fvalue in td["fields"]:
            fields_blob += struct.pack("<iii", str_offset_of[fname], 0, 0x04000001 + field_index)
            if fvalue is not None:
                fdv_blob += struct.pack("<iii", field_index, 0, len(defaults_blob))
                defaults_blob += compress(fvalue)
            field_index += 1
        td["field_count"] = len(td["fields"])

    # ---- methods (2) e parameters (1): soma de parameterCount == 1
    methods_blob = bytearray()
    for i, (pstart, pcount) in enumerate([(0, 1), (1, 0)]):
        row = bytearray(32)
        struct.pack_into("<i", row, 0, str_offset_of[".ctor" if i == 0 else "SyntheticMethod"])
        struct.pack_into("<i", row, 20, pstart)
        struct.pack_into("<I", row, 24, 0x06000001 + i)
        struct.pack_into("<H", row, 30, pcount)
        methods_blob += row
    if break_region == "param_sum_off":
        struct.pack_into("<H", methods_blob, dump.METHOD_PARAM_COUNT, 2)
    parameters_blob = struct.pack("<iii", 0, 0, 0)

    # ---- typedefs (88B cada)
    td_blob = bytearray()
    for i, td in enumerate(typedefs):
        row = bytearray(dump.TYPEDEF_SIZE)
        struct.pack_into("<i", row, dump.TD_NAME, str_offset_of[td["name"]])
        struct.pack_into("<i", row, dump.TD_NAMESPACE, str_offset_of[td["ns"]])
        struct.pack_into("<i", row, 12, -1)   # declaring
        struct.pack_into("<i", row, 16, -1)   # parent
        struct.pack_into("<i", row, 24, -1)   # genericContainer
        struct.pack_into("<i", row, dump.TD_FIELD_START, td["field_start"])
        struct.pack_into("<i", row, dump.TD_METHOD_START, td["methods"][0])
        struct.pack_into("<H", row, dump.TD_FIELD_COUNT, td["field_count"])
        struct.pack_into("<H", row, dump.TD_METHOD_COUNT, td["methods"][1])
        struct.pack_into("<I", row, dump.TD_TOKEN, 0x02000001 + i)
        td_blob += row

    # ---- images (1): encadeia todos os typedefs
    images_blob = struct.pack(
        "<iiiiiiiiii", str_offset_of["SyntheticAssembly.dll"], 0, 0, len(typedefs),
        0, -1, 0x00000001, -1, 0, 0,
    )

    # ---- attributeData: strings len<<1 (wire names) + uma não-snake p/ filtro
    wire_pairs = [(b"access_token", b"\x18"), (b"user_id", b"\x0e"), (b"session_key", b"\x16")]
    attribute_blob = bytearray()
    for text, prefix in wire_pairs:
        attribute_blob += prefix + text
    attribute_blob += b"\x04hi"  # "hi": ASCII mas sem underscore — fora do shape

    # ---- literals: n_routes rotas no TOTAL (âncoras incluídas) + ruído
    routes = [
        f"game/synthetic/route-{i}".encode()
        for i in range(max(0, n_routes - len(dump.EXPECTED_ROUTES)))
    ]
    for anchor in dump.EXPECTED_ROUTES:
        routes.append(anchor.encode())
    literals = routes + [b"not a game route", b"gameplay tips", b""]
    lit_table = b"".join(
        struct.pack("<II", len(item), offset) for offset, item in
        ((sum(len(x) for x in literals[:i]), item) for i, item in enumerate(literals))
    )
    lit_blob = b"".join(literals)

    regions: dict[str, bytes] = {
        "stringLiteral": lit_table,
        "stringLiteralData": lit_blob,
        "string": bytes(string_blob),
        "methods": bytes(methods_blob),
        "fieldDefaultValues": bytes(fdv_blob),
        "fieldAndParameterDefaultValueData": bytes(defaults_blob),
        "parameters": parameters_blob,
        "fields": bytes(fields_blob),
        "typeDefinitions": bytes(td_blob),
        "images": images_blob,
        "attributeData": bytes(attribute_blob),
    }
    if break_region == "field_count_off":
        regions["fields"] = regions["fields"][:-12]

    # ---- montagem: header de 31 regiões + conteúdos sequenciais
    out = bytearray()
    out += struct.pack("<Ii", dump.EXPECTED_SANITY, dump.EXPECTED_VERSION)
    out += bytes(8 * len(dump.HEADER_FIELDS))
    cursor = 8 + 8 * len(dump.HEADER_FIELDS)
    offsets: dict[str, tuple[int, int]] = {}
    bodies = bytearray()
    for name in dump.HEADER_FIELDS:
        content = regions.get(name, b"")
        offsets[name] = (cursor, len(content))
        bodies += content
        cursor += len(content)
    for name, (offset, size) in offsets.items():
        index = dump.HEADER_FIELDS.index(name)
        struct.pack_into("<Ii", out, 8 + index * 8, offset, size)
    if break_region == "region_past_end":
        struct.pack_into("<Ii", out, 8 + 2 * 8, 10 ** 7, 16)
    if break_region == "overlap":
        struct.pack_into("<Ii", out, 8 + 1 * 8, offsets["stringLiteral"][0], 8)
    out += bodies
    return bytes(out)


# ------------------------------------------------------------------ testes

def test_routes_from_literals(tmp: Path) -> None:
    meta = tmp / "global-metadata.dat"
    meta.write_bytes(build_synthetic_metadata([
        b"game/auth/register",
        b"Ok button label",
        b"game/chapters/start",
        b"gameplay tips",          # com espaço: não é rota
        b"game/store/get",
        b"game/auth/register",     # duplicata no literal stream vira uma rota
    ]))
    result = dump.extract_routes(meta)
    assert result["routes"] == [
        "game/auth/register", "game/chapters/start", "game/store/get"
    ], result["routes"]
    assert result["string_literals"] == 6


def test_routes_from_apk(tmp: Path) -> None:
    apk = tmp / "game.apk"
    with zipfile.ZipFile(apk, "w") as zf:
        zf.writestr(dump.METADATA_ENTRY, build_synthetic_metadata([b"game/talents/buy"]))
    result = dump.extract_routes(apk)
    assert result["routes"] == ["game/talents/buy"]


def test_rejects_wrong_sanity(tmp: Path) -> None:
    meta = tmp / "bad.dat"
    meta.write_bytes(struct.pack("<Ii", 0xDEADBEEF, 29) + b"\x00" * 64)
    try:
        dump.extract_routes(meta)
    except ValueError as exc:
        assert "sanity" in str(exc)
    else:
        raise AssertionError("deveria rejeitar sanity inválido")


def test_rejects_wrong_version(tmp: Path) -> None:
    meta = tmp / "bad.dat"
    meta.write_bytes(struct.pack("<Ii", dump.EXPECTED_SANITY, 31) + b"\x00" * 64)
    try:
        dump.extract_routes(meta)
    except ValueError as exc:
        assert "versão" in str(exc)
    else:
        raise AssertionError("deveria rejeitar versão diferente de 29")


def test_builder_completo_passa_validacao(tmp: Path) -> None:
    mf = dump.MetadataFile(build_full_metadata())
    summary = mf.validation_summary()
    assert summary["typedefs"] == 5, summary
    assert summary["fields"] == 22, summary
    assert summary["methods"] == 2, summary
    assert summary["parameters"] == 1, summary
    assert summary["field_defaults"] == 15, summary


def test_rejeita_regiao_fora_do_arquivo(tmp: Path) -> None:
    try:
        dump.MetadataFile(build_full_metadata(break_region="region_past_end"))
    except dump.MetadataError as exc:
        assert "ultrapassa" in str(exc), exc
    else:
        raise AssertionError("deveria rejeitar região fora do arquivo")


def test_rejeita_regioes_sobrepostas(tmp: Path) -> None:
    try:
        dump.MetadataFile(build_full_metadata(break_region="overlap"))
    except dump.MetadataError as exc:
        assert "sobrepostas" in str(exc), exc
    else:
        raise AssertionError("deveria rejeitar regiões sobrepostas")


def test_rejeita_contagem_de_fields_quebrada(tmp: Path) -> None:
    try:
        dump.MetadataFile(build_full_metadata(break_region="field_count_off"))
    except dump.MetadataError as exc:
        assert "fim de fields" in str(exc), exc
    else:
        raise AssertionError("deveria rejeitar fechamento de fields quebrado")


def test_rejeita_soma_de_parametros_quebrada(tmp: Path) -> None:
    try:
        dump.MetadataFile(build_full_metadata(break_region="param_sum_off"))
    except dump.MetadataError as exc:
        assert "parameterCount" in str(exc), exc
    else:
        raise AssertionError("deveria rejeitar soma de parameterCount divergente")


def test_enums_resolvidos(tmp: Path) -> None:
    mf = dump.MetadataFile(build_full_metadata())
    achados = {(td.namespace, td.name): dict(members) for td, members in mf.iter_enums()}
    assert set(achados) == {("", "SyntheticEnum"), ("Ubu.GameApi", "ResponseCode")}, achados
    assert achados[("", "SyntheticEnum")]["SyntheticSuccess"] == 1000
    assert achados[("Ubu.GameApi", "ResponseCode")]["Success"] == 1000
    # SyntheticBrokenEnum (field sem default) e SyntheticNotEnum (field[0] != value__) ficam de fora


def test_valores_comprimidos_batem_com_o_real(tmp: Path) -> None:
    # Success=1000 vira raw 2000 = 0x87D0 e JwtInvalid=2110 vira 4220 = 0x907C —
    # os mesmos bytes observados no metadata real.
    assert compress(1000) == b"\x87\xd0"
    assert compress(2110) == b"\x90\x7c"
    assert compress(-1) == b"\x01" and compress(-10) == b"\x13"


def test_read_compressed_uint_formas(tmp: Path) -> None:
    assert dump.read_compressed_uint(b"\x05", 0) == (5, 1)
    assert dump.read_compressed_uint(b"\x87\xd0", 0) == (2000, 2)
    four = 0x1234ABCD
    blob = bytes([0xC0 | (four >> 24), (four >> 16) & 0xFF, (four >> 8) & 0xFF, four & 0xFF])
    assert dump.read_compressed_uint(blob, 0) == (four, 4)
    try:
        dump.read_compressed_uint(b"\x87", 0)
    except dump.MetadataError:
        pass
    else:
        raise AssertionError("deveria rejeitar varint truncado")


def test_default_negativo_decodifica(tmp: Path) -> None:
    """Âncoras de sinal: -1←1 e a família Win32 -10/-11/-12 ← 19/21/23."""
    mf = dump.MetadataFile(build_full_metadata())
    achados = {(td.namespace, td.name): dict(members) for td, members in mf.iter_enums()}
    synthetic = achados[("", "SyntheticEnum")]
    assert synthetic["SyntheticNone"] == -1, synthetic
    assert synthetic["SyntheticStdIn"] == -10, synthetic
    assert synthetic["SyntheticStdOut"] == -11, synthetic
    assert synthetic["SyntheticStdErr"] == -12, synthetic
    # bytes crus no blob: 1, 19, 21, 23 (varint de 1 byte, bit baixo em 1)
    blob_offset = mf.regions["fieldAndParameterDefaultValueData"][0]
    primeiro = mf.data[blob_offset]
    assert primeiro == 0x87, hex(primeiro)  # primeiro default é SyntheticSuccess=1000


def test_response_codes_ancoras_ok(tmp: Path) -> None:
    result = dump.extract_response_codes(dump.MetadataFile(build_full_metadata()))
    assert result["sanity_checks"]["ok"] is True, result["sanity_checks"]
    assert result["sanity_checks"]["failures"] == []


def test_response_codes_ancora_errada_falha(tmp: Path) -> None:
    result = dump.extract_response_codes(
        dump.MetadataFile(build_full_metadata(response_values={"Success": 999}))
    )
    assert result["sanity_checks"]["ok"] is False
    assert any("Success" in f for f in result["sanity_checks"]["failures"])


def test_dtos_com_wire_fallback(tmp: Path) -> None:
    result = dump.extract_dtos(dump.MetadataFile(build_full_metadata()))
    names = {dto["name"] for dto in result["dtos"]}
    assert names == {"SyntheticDtoRequest"}, names
    dto = result["dtos"][0]
    assert dto["assembly"] == "SyntheticAssembly.dll"
    assert dto["namespace"] == "Synthetic.Api"
    wires = {f["name"]: f["wire"] for f in dto["fields"]}
    assert wires == {"AccessToken": "access_token", "Xp": "xp", "APIVersion": "api_version"}, wires
    assert all(f["wire_source"] == "fallback_snakecase" for f in dto["fields"])


def test_snake_case(tmp: Path) -> None:
    cases = {
        "AccessToken": "access_token",
        "APIVersion": "api_version",
        "XpData": "xp_data",
        "ID": "id",
        "UserId2": "user_id2",
        "AlreadySnake": "already_snake",
    }
    for source, expected in cases.items():
        got = dump.snake_case(source)
        assert got == expected, f"{source} -> {got} (esperado {expected})"


def test_wire_names_extraidos(tmp: Path) -> None:
    result = dump.extract_wire_names(dump.MetadataFile(build_full_metadata()))
    assert "access_token" in result["wire_names"]
    assert "user_id" in result["wire_names"]
    assert "session_key" in result["wire_names"]
    assert "hi" not in result["wire_names"]
    assert "pareamento" in result["note"]


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    old_argv = sys.argv
    sys.argv = ["dump_il2cpp_metadata.py", *argv]
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = dump.main()
    finally:
        sys.argv = old_argv
    return code, out.getvalue(), err.getvalue()


def test_cli_routes_escreve_json(tmp: Path) -> None:
    meta = tmp / "global-metadata.dat"
    meta.write_bytes(build_full_metadata(n_routes=3))
    out_file = tmp / "routes.json"
    code, stdout, _ = _run_cli(["--metadata", str(meta), "--routes", "--out", str(out_file)])
    assert code == 0, stdout
    assert "rotas" in stdout
    payload = __import__("json").loads(out_file.read_text(encoding="utf-8"))
    assert payload["routes"][0].startswith("game/")


def test_cli_all_gate_aprovado(tmp: Path) -> None:
    meta = tmp / "global-metadata.dat"
    meta.write_bytes(build_full_metadata())  # 116 rotas + âncoras + enums ok
    out_file = tmp / "all.json"
    code, _, stderr = _run_cli(["--metadata", str(meta), "--all", "--out", str(out_file)])
    assert code == 0, stderr
    payload = __import__("json").loads(out_file.read_text(encoding="utf-8"))
    assert payload["sanity_checks"]["ok"] is True, payload["sanity_checks"]
    assert len(payload["routes"]) == dump.EXPECTED_ROUTE_COUNT
    assert payload["validation"]["typedefs"] == 5


def test_cli_all_gate_reprovado_sem_116_rotas(tmp: Path) -> None:
    meta = tmp / "global-metadata.dat"
    meta.write_bytes(build_full_metadata(n_routes=7))
    code, _, stderr = _run_cli(["--metadata", str(meta), "--all", "--out", str(tmp / "a.json")])
    assert code == 3, stderr
    assert "SANITY FALHOU" in stderr
    assert "116" in stderr


def main() -> int:
    import tempfile
    tests = (
        test_routes_from_literals, test_routes_from_apk,
        test_rejects_wrong_sanity, test_rejects_wrong_version,
        test_builder_completo_passa_validacao,
        test_rejeita_regiao_fora_do_arquivo, test_rejeita_regioes_sobrepostas,
        test_rejeita_contagem_de_fields_quebrada, test_rejeita_soma_de_parametros_quebrada,
        test_enums_resolvidos, test_valores_comprimidos_batem_com_o_real,
        test_read_compressed_uint_formas, test_default_negativo_decodifica,
        test_response_codes_ancoras_ok, test_response_codes_ancora_errada_falha,
        test_dtos_com_wire_fallback, test_snake_case, test_wire_names_extraidos,
        test_cli_routes_escreve_json, test_cli_all_gate_aprovado,
        test_cli_all_gate_reprovado_sem_116_rotas,
    )
    with tempfile.TemporaryDirectory() as name:
        tmp = Path(name)
        for test in tests:
            test(tmp)
            print(f"[OK] {test.__name__}")
    print(f"test_dump_il2cpp_metadata: {len(tests)}/{len(tests)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
