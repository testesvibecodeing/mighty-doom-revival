"""`gpg.config` — `Ubu.GooglePlay.GooglePlayLocalConfig` no BinaryFormatter .NET.

CONFIRMADO (2026-08-20) contra o arquivo real do dispositivo, 180 bytes:

```text
0000  00 01 00 00 00 ff ff ff ff 01 00 00 00 00 00 00 00   SerializedStreamHeader
0011  0c 02 00 00 00 45 "Ubu.GooglePlay, Version=0.0.0.0,   BinaryLibrary(id=2)
                          Culture=neutral, PublicKeyToken=null"
0060  00 24 "Ubu.GooglePlay.GooglePlayLocalConfig"          ClassWithMembersAndTypes
      02 00 00 00                                           memberCount = 2
      11 "hasCancelledLogin"  0d "hasLoggedOut"             nomes dos membros
      00 00                                                 BinaryTypeEnum: Primitive, Primitive
      01 01                                                 PrimitiveTypeEnum: Boolean, Boolean
      02 00 00 00                                           libraryId = 2
      01 00                                                 VALORES: true, false
      0b                                                    MessageEnd
```

Os identificadores batem com o metadata (`hasCancelledLogin`, `hasLoggedOut`,
`GooglePlayLocalConfig`, `get_IsAutomaticAuthenticationAllowed` estão na tabela
de strings do `global-metadata.dat` v29).

Estado medido no dispositivo onde o boot COMPLETOU sem Google
(`hasCancelledLogin=True`, `hasLoggedOut=False`): nessa configuração o cliente
seguiu direto para `game/auth/register` e chegou a `user-data` — 12 requests,
sem nenhuma chamada a `login-google-play-games` (boot3, request_log 244–255).

Por isso este módulo existe: semear esse estado é a supressão do gate Google de
MENOR invasividade — não mexe em `libil2cpp.so`, não remove biblioteca Google
nenhuma, e é exatamente o arquivo que o próprio cliente escreve.

A VERIFICAR: se `hasCancelledLogin=True` suprime o popup em TODO primeiro boot,
ou só depois de um cancelamento real. Não foi possível medir (ver
`work/audit-opus/FASE-3-ADB-APK.md`).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

GPG_CONFIG_FILENAME = "gpg.config"

_ASSEMBLY = b"Ubu.GooglePlay, Version=0.0.0.0, Culture=neutral, PublicKeyToken=null"
_TYPE_NAME = b"Ubu.GooglePlay.GooglePlayLocalConfig"
_MEMBERS = (b"hasCancelledLogin", b"hasLoggedOut")
_LIBRARY_ID = 2
_OBJECT_ID = 1

# Cabeçalho do stream: SerializedStreamHeader(recordId=0) com rootId=1,
# headerId=-1, major=1, minor=0.
_HEADER = bytes([0x00]) + struct.pack("<iiii", _OBJECT_ID, -1, 1, 0)


class GpgConfigError(Exception):
    """Formato inesperado. Nunca "conserta" o arquivo no chute."""


@dataclass(frozen=True)
class GooglePlayLocalConfig:
    has_cancelled_login: bool
    has_logged_out: bool


def _length_prefixed(raw: bytes) -> bytes:
    """String do BinaryFormatter: comprimento em 7-bit encoded int + UTF-8."""
    tamanho = len(raw)
    saida = bytearray()
    while True:
        byte = tamanho & 0x7F
        tamanho >>= 7
        if tamanho:
            saida.append(byte | 0x80)
        else:
            saida.append(byte)
            break
    return bytes(saida) + raw


def _read_length_prefixed(dados: bytes, pos: int) -> tuple[bytes, int]:
    tamanho = 0
    deslocamento = 0
    while True:
        if pos >= len(dados):
            raise GpgConfigError("comprimento de string truncado")
        byte = dados[pos]
        pos += 1
        tamanho |= (byte & 0x7F) << deslocamento
        if not byte & 0x80:
            break
        deslocamento += 7
        if deslocamento > 28:
            raise GpgConfigError("comprimento de string absurdo")
    fim = pos + tamanho
    if fim > len(dados):
        raise GpgConfigError("string além do fim do arquivo")
    return dados[pos:fim], fim


def serialize_gpg_config(config: GooglePlayLocalConfig) -> bytes:
    """Reproduz o arquivo byte a byte, mudando só os dois booleanos."""
    if not isinstance(config.has_cancelled_login, bool) or not isinstance(config.has_logged_out, bool):
        raise GpgConfigError("os dois campos são Boolean primitivos do .NET")
    saida = bytearray(_HEADER)
    # BinaryLibrary (recordId 12)
    saida.append(0x0C)
    saida += struct.pack("<i", _LIBRARY_ID)
    saida += _length_prefixed(_ASSEMBLY)
    # ClassWithMembersAndTypes (recordId 5)
    saida.append(0x05)
    saida += struct.pack("<i", _OBJECT_ID)
    saida += _length_prefixed(_TYPE_NAME)
    saida += struct.pack("<i", len(_MEMBERS))
    for nome in _MEMBERS:
        saida += _length_prefixed(nome)
    saida += bytes([0x00] * len(_MEMBERS))        # BinaryTypeEnum.Primitive
    saida += bytes([0x01] * len(_MEMBERS))        # PrimitiveTypeEnum.Boolean
    saida += struct.pack("<i", _LIBRARY_ID)
    saida.append(0x01 if config.has_cancelled_login else 0x00)
    saida.append(0x01 if config.has_logged_out else 0x00)
    saida.append(0x0B)                            # MessageEnd
    return bytes(saida)


def parse_gpg_config(dados: bytes | Path | str) -> GooglePlayLocalConfig:
    """Lê os dois booleanos, recusando qualquer coisa que não seja este layout."""
    if isinstance(dados, (str, Path)):
        dados = Path(dados).read_bytes()
    if not dados.startswith(_HEADER):
        raise GpgConfigError("cabeçalho do BinaryFormatter inesperado")
    pos = len(_HEADER)
    if dados[pos] != 0x0C:
        raise GpgConfigError("esperava BinaryLibrary após o cabeçalho")
    pos += 1 + 4
    assembly, pos = _read_length_prefixed(dados, pos)
    if assembly != _ASSEMBLY:
        raise GpgConfigError("assembly diferente de Ubu.GooglePlay")
    if dados[pos] != 0x05:
        raise GpgConfigError("esperava ClassWithMembersAndTypes")
    pos += 1 + 4
    tipo, pos = _read_length_prefixed(dados, pos)
    if tipo != _TYPE_NAME:
        raise GpgConfigError("tipo diferente de GooglePlayLocalConfig")
    (quantidade,) = struct.unpack_from("<i", dados, pos)
    pos += 4
    if quantidade != len(_MEMBERS):
        raise GpgConfigError(f"esperava {len(_MEMBERS)} membros, veio {quantidade}")
    nomes = []
    for _ in range(quantidade):
        nome, pos = _read_length_prefixed(dados, pos)
        nomes.append(nome)
    if tuple(nomes) != _MEMBERS:
        raise GpgConfigError("nomes de membro fora da ordem conhecida")
    pos += quantidade      # BinaryTypeEnum
    pos += quantidade      # PrimitiveTypeEnum
    pos += 4               # libraryId
    if pos + quantidade + 1 > len(dados):
        raise GpgConfigError("arquivo truncado antes dos valores")
    cancelou = dados[pos]
    saiu = dados[pos + 1]
    if cancelou not in (0, 1) or saiu not in (0, 1):
        raise GpgConfigError("valor booleano fora de 0/1")
    if dados[pos + 2] != 0x0B:
        raise GpgConfigError("MessageEnd ausente")
    return GooglePlayLocalConfig(has_cancelled_login=bool(cancelou), has_logged_out=bool(saiu))
