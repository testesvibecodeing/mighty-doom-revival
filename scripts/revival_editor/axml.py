"""Parser mínimo de AndroidManifest.xml binário (AXML) do Revival Studio.

Fecha a lacuna registrada no baseline (work/revival-studio/baseline/BASELINE.md,
achado nº 6): sem `aapt` no PATH, `analyze_apk` devolvia `package: {}`, e
package/versão/build ficavam "não medido" — o que pela regra da fase 4
(desconhecido não é aprovação) mantinha `matches_target=False` para sempre.

Este módulo lê o manifest direto do ZIP, decodificando o formato binário
documentado em `resourceTypes.h` do AOSP: cabeçalho de arquivo, *string pool*
(UTF-8 ou UTF-16) e elementos de abertura. Só o que o manifest precisa —
nada de reconstruir o XML inteiro, nada de regex sobre bytes (o formato é
estruturado; procurar substring em binário é exatamente o tipo de busca cega
que o projeto proíbe).

Sanidade antes de tudo: se o conteúdo não bater com a estrutura (magic,
limites de chunk, índices do pool), levanta `AxmlError` com o motivo. O
chamador trata como "não medido" — nunca adivinha.
"""
from __future__ import annotations

import struct
import zipfile
from pathlib import Path

__all__ = ["AxmlError", "parse_axml_manifest", "read_manifest_facts"]

#: Magic do arquivo AXML: chunk raiz RES_XML_TYPE.
RES_XML_TYPE = 0x0003
RES_STRING_POOL_TYPE = 0x0001
RES_XML_START_ELEMENT_TYPE = 0x0102

#: flags do string pool ( SortedFlag=1, UTF8_FLAG=1<<8 )
UTF8_FLAG = 0x0100

#: Res_value: data types que o manifest usa.
TYPE_STRING = 0x03
TYPE_INT_DEC = 0x10
TYPE_INT_HEX = 0x11
TYPE_BOOL = 0x12

_NO_REF = 0xFFFFFFFF


class AxmlError(Exception):
    """AXML ilegível/inesperado — mensagem já serve de aviso no log."""


# ----------------------------------------------------------------------
# string pool
# ----------------------------------------------------------------------


def _tamanho_utf8(dados: bytes, pos: int) -> tuple[int, int]:
    """Comprimento variável (1 ou 2 bytes) de string UTF-8 do pool."""
    byte = dados[pos]
    pos += 1
    if byte & 0x80:
        byte = ((byte & 0x7F) << 8) | dados[pos]
        pos += 1
    return byte, pos


def _tamanho_utf16(dados: bytes, pos: int) -> tuple[int, int]:
    """Comprimento variável (1 ou 2 words) de string UTF-16 do pool."""
    (palavra,) = struct.unpack_from("<H", dados, pos)
    pos += 2
    if palavra & 0x8000:
        (baixa,) = struct.unpack_from("<H", dados, pos)
        pos += 2
        palavra = ((palavra & 0x7FFF) << 16) | baixa
    return palavra, pos


def _ler_string_pool(chunk: bytes) -> list[str]:
    """Decodifica o pool de strings inteiro (UTF-8 ou UTF-16)."""
    if len(chunk) < 28:
        raise AxmlError("string pool truncado no cabeçalho")
    (
        _tipo,
        header_size,
        _tamanho,
        quantidade,
        _estilos,
        flags,
        inicio_strings,
        _inicio_estilos,
    ) = struct.unpack_from("<HHIIIIII", chunk, 0)
    if quantidade > 65535:
        raise AxmlError(f"string pool com {quantidade} strings é nonsense")
    utf8 = bool(flags & UTF8_FLAG)

    deslocamentos: list[int] = []
    base = header_size
    for i in range(quantidade):
        if base + 4 * (i + 1) > len(chunk):
            raise AxmlError(f"offset de string {i} fora do chunk")
        (valor,) = struct.unpack_from("<I", chunk, base + 4 * i)
        deslocamentos.append(valor)

    strings: list[str] = []
    for deslocamento in deslocamentos:
        pos = inicio_strings + deslocamento
        if pos >= len(chunk):
            raise AxmlError("string aponta fora do pool")
        if utf8:
            _nchars, pos = _tamanho_utf8(chunk, pos)
            nbytes, pos = _tamanho_utf8(chunk, pos)
            if pos + nbytes > len(chunk):
                raise AxmlError("string UTF-8 truncada")
            strings.append(chunk[pos : pos + nbytes].decode("utf-8", "replace"))
        else:
            nchars, pos = _tamanho_utf16(chunk, pos)
            if pos + nchars * 2 > len(chunk):
                raise AxmlError("string UTF-16 truncada")
            trecho = chunk[pos : pos + nchars * 2]
            strings.append(trecho.decode("utf-16-le", "replace"))
    return strings


def _referencia(pool: list[str], indice: int) -> str | None:
    if indice == _NO_REF or indice < 0 or indice >= len(pool):
        return None
    return pool[indice]


# ----------------------------------------------------------------------
# parser principal
# ----------------------------------------------------------------------


def parse_axml_manifest(dados: bytes) -> dict[str, str]:
    """Extrai package/versionName/versionCode do AXML do manifest.

    Devolve só o que encontrou; o que não veio fica fora do dicionário
    (chamador decide o que é "não medido").
    """
    if len(dados) < 8:
        raise AxmlError(f"AXML com {len(dados)} bytes é truncado demais")
    tipo, header_size, tamanho = struct.unpack_from("<HHI", dados, 0)
    if tipo != RES_XML_TYPE:
        raise AxmlError(f"não é AXML (tipo do chunk raiz 0x{tipo:04X})")
    limite = min(tamanho, len(dados))

    pool: list[str] = []
    pos = header_size
    achado: dict[str, str] = {}
    while pos + 8 <= limite:
        ctipo, chdr, ctam = struct.unpack_from("<HHI", dados, pos)
        if ctam < 8 or pos + ctam > limite:
            raise AxmlError(f"chunk 0x{ctipo:04X} estoura o arquivo em {pos}")
        if ctipo == RES_STRING_POOL_TYPE:
            pool = _ler_string_pool(dados[pos : pos + ctam])
        elif ctipo == RES_XML_START_ELEMENT_TYPE:
            nome, atributos = _ler_elemento(dados, pos, ctam, pool)
            if nome == "manifest":
                achado = atributos
                break  # o manifest é a raiz; nada depois interessa aqui
        pos += ctam

    if not pool:
        raise AxmlError("AXML sem string pool legível")
    if not achado:
        raise AxmlError("elemento <manifest> não encontrado")

    interesses = {"package", "versionName", "versionCode"}
    return {chave: valor for chave, valor in achado.items() if chave in interesses}


def _ler_elemento(
    dados: bytes, pos: int, _tamanho: int, pool: list[str]
) -> tuple[str | None, dict[str, str]]:
    """Lê um RES_XML_START_ELEMENT: (nome do elemento, atributos {nome: valor})."""
    if pos + 36 > len(dados):
        raise AxmlError("elemento de abertura truncado")
    # node comum: lineNumber u32 + comment u32; depois attrExt
    (nome_idx,) = struct.unpack_from("<I", dados, pos + 20)
    (
        attribute_start,
        attribute_size,
        attribute_count,
    ) = struct.unpack_from("<HHH", dados, pos + 24)
    if attribute_size < 20:
        attribute_size = 20
    base = pos + 16 + attribute_start
    atributos: dict[str, str] = {}
    for i in range(attribute_count):
        offset = base + i * attribute_size
        if offset + 20 > len(dados):
            raise AxmlError(f"atributo {i} do elemento fora do arquivo")
        _ns, nome_attr, raw_value = struct.unpack_from("<III", dados, offset)
        _tamanho_valor, _res0, data_type, data = struct.unpack_from("<HBBI", dados, offset + 12)
        nome = _referencia(pool, nome_attr)
        if nome is None:
            continue
        if raw_value != _NO_REF:
            bruto = _referencia(pool, raw_value)
            if bruto is not None:
                atributos[nome] = bruto
                continue
        if data_type == TYPE_STRING:
            bruto = _referencia(pool, data)
            if bruto is not None:
                atributos[nome] = bruto
        elif data_type in (TYPE_INT_DEC, TYPE_INT_HEX):
            # signed: versionCode é INT_DEC pequeno, mas negativo existe em
            # outros atributos e não deve virar uint gigante.
            atributos[nome] = str(data - 0x100000000 if data >= 0x80000000 else data)
        elif data_type == TYPE_BOOL:
            atributos[nome] = "true" if data else "false"
    nome_elemento = _referencia(pool, nome_idx)
    return nome_elemento, atributos


def read_manifest_facts(apk: Path | str, membro: str = "AndroidManifest.xml") -> dict[str, str]:
    """Abre o manifest direto do ZIP do APK e devolve os fatos medidos."""
    caminho = Path(apk)
    try:
        with zipfile.ZipFile(caminho, "r") as zf:
            with zf.open(membro, "r") as stream:
                dados = stream.read()
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise AxmlError(f"não foi possível ler {membro} do APK: {exc}") from exc
    return parse_axml_manifest(dados)
