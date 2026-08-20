"""`credentials.json` — o formato real que `Ubu.CredentialStore` lê.

CONFIRMADO (2026-08-20) por duas fontes independentes:

1. `global-metadata.dat` v29, via `scripts/dump_il2cpp_metadata.py --dtos
   --pattern CredentialStore`:

   ```text
   Ubu.CredentialStore.SaveData  campos: version, userId, deviceId, password,
                                          region, platform
   Ubu.CredentialStore           CredentialsFilePath, TempPath, SaveDataVersion
                                 Create(userId, deviceId, password, region, platform)
                                 Load() / TryLoadCredentials(filePath, credentials) / Delete()
   ```

2. O arquivo real do dispositivo (150 bytes), cuja estrutura é exatamente:

   ```text
   version: int = 3     user_id: int        device_id: string de 36 (UUID)
   password: string 32  region: "US"        platform: int = 4
   ```

O `TempPath` do próprio cliente confirma que a gravação correta é **temporário +
rename atômico** — é o que `write_credentials()` faz.

`device_id` NÃO é inventado aqui: `CredentialStore.Create` o recebe como
PARÂMETRO, e o response real de `game/auth/register` traz `device_id`. Este
módulo só transporta o valor que o servidor emitiu.

Nada neste módulo imprime, loga ou serializa `password`/`device_id` em mensagem
de erro. `Credentials.redacted()` existe para relatório.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

CREDENTIALS_FILENAME = "credentials.json"

# Ubu.CredentialStore.SaveDataVersion no build 1.13.1.
SAVE_DATA_VERSION = 3

# Ordem observada no arquivo real; mantida na escrita para o diff ficar legível.
FIELD_ORDER = ("version", "user_id", "device_id", "password", "region", "platform")

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class CredentialsError(Exception):
    """Erro de contrato das credenciais. Nunca carrega valor sensível."""


@dataclass(frozen=True)
class Credentials:
    user_id: int
    device_id: str
    password: str
    region: str = "US"
    platform: int = 4
    version: int = SAVE_DATA_VERSION

    def __post_init__(self) -> None:
        # Tipos primeiro: o cliente é IL2CPP com tipos concretos, e `true`/`"3"`
        # onde se espera int derruba a desserialização.
        if isinstance(self.user_id, bool) or not isinstance(self.user_id, int):
            raise CredentialsError("user_id tem que ser inteiro")
        if self.user_id <= 0:
            raise CredentialsError("user_id tem que ser positivo")
        if isinstance(self.platform, bool) or not isinstance(self.platform, int):
            raise CredentialsError("platform tem que ser inteiro")
        if isinstance(self.version, bool) or not isinstance(self.version, int):
            raise CredentialsError("version tem que ser inteiro")
        if self.version != SAVE_DATA_VERSION:
            raise CredentialsError(
                f"version {self.version} não é a suportada ({SAVE_DATA_VERSION}); "
                "gravar outra versão faz o cliente recusar ou migrar o arquivo")
        if not isinstance(self.device_id, str) or not _UUID_RE.match(self.device_id):
            # Sem ecoar o valor: só o formato esperado.
            raise CredentialsError("device_id tem que ser UUID de 36 caracteres, "
                                   "exatamente como veio do register")
        if not isinstance(self.password, str) or not self.password:
            raise CredentialsError("password ausente")
        if not isinstance(self.region, str) or len(self.region) != 2 or not self.region.isalpha():
            raise CredentialsError("region tem que ser código de 2 letras (ex.: US)")

    def to_wire(self) -> dict:
        bruto = {
            "version": self.version,
            "user_id": self.user_id,
            "device_id": self.device_id,
            "password": self.password,
            "region": self.region,
            "platform": self.platform,
        }
        return {chave: bruto[chave] for chave in FIELD_ORDER}

    def redacted(self) -> dict:
        """Forma publicável: tipos e tamanhos, nunca os valores secretos."""
        return {
            "version": self.version,
            "user_id": "<user-id>",
            "device_id": f"<device-id:{len(self.device_id)}>",
            "password": f"<password:{len(self.password)}>",
            "region": self.region,
            "platform": self.platform,
        }


def credentials_from_register_response(payload: dict) -> Credentials:
    """Reproduz `CredentialStore.Create` a partir do response real de register.

    `region` e `platform` vêm do REQUEST (o cliente 1.13.1 envia
    `platform_id: 4`, `region: "US"`); o response traz `user_id`, `device_id` e
    `password`. Campo ausente é erro explícito — nunca default silencioso.
    """
    if not isinstance(payload, dict):
        raise CredentialsError("response de register não é um objeto")
    codigo = payload.get("code")
    if codigo is not None and codigo != 1000:
        raise CredentialsError(f"register não retornou sucesso (code {codigo})")
    faltando = [c for c in ("user_id", "device_id", "password") if payload.get(c) in (None, "")]
    if faltando:
        raise CredentialsError(f"response de register sem {', '.join(faltando)}")
    return Credentials(
        user_id=payload["user_id"],
        device_id=payload["device_id"],
        password=payload["password"],
        region=payload.get("region") or "US",
        platform=payload.get("platform_id", payload.get("platform", 4)),
    )


def load_credentials(path: Path | str) -> Credentials:
    """Lê e VALIDA. Arquivo parcial/corrompido vira erro, não credencial torta."""
    caminho = Path(path)
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CredentialsError(f"{caminho.name} não existe") from exc
    except json.JSONDecodeError as exc:
        raise CredentialsError(f"{caminho.name} não é JSON válido: {exc.msg}") from exc
    if not isinstance(dados, dict):
        raise CredentialsError(f"{caminho.name} não é um objeto JSON")
    desconhecidos = sorted(set(dados) - set(FIELD_ORDER))
    if desconhecidos:
        raise CredentialsError(f"{caminho.name} tem campo fora do contrato: {', '.join(desconhecidos)}")
    faltando = sorted(set(FIELD_ORDER) - set(dados))
    if faltando:
        raise CredentialsError(f"{caminho.name} sem os campos: {', '.join(faltando)}")
    return Credentials(
        user_id=dados["user_id"], device_id=dados["device_id"], password=dados["password"],
        region=dados["region"], platform=dados["platform"], version=dados["version"],
    )


def write_credentials(path: Path | str, credentials: Credentials, *, overwrite: bool = False) -> Path:
    """Grava de forma ATÔMICA (temporário no mesmo diretório + rename).

    O próprio cliente tem `CredentialStore.TempPath`, ou seja, é assim que ele
    grava. Escrita interrompida não pode deixar JSON parcial: o rename é a única
    operação visível, e no POSIX/NTFS ele é atômico dentro do mesmo volume.

    `overwrite=False` (default) RECUSA sobrescrever credencial existente — perder
    o arquivo é perder a conta e o progresso do jogador.
    """
    destino = Path(path)
    if destino.exists() and not overwrite:
        raise CredentialsError(
            f"{destino.name} já existe; sobrescrever exige ação explícita "
            "(overwrite=True) — apagar credencial é perder a conta")
    destino.parent.mkdir(parents=True, exist_ok=True)
    corpo = json.dumps(credentials.to_wire(), ensure_ascii=False, separators=(",", ":"))

    fd, temporario = tempfile.mkstemp(dir=str(destino.parent), prefix=".credentials-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as arquivo:
            arquivo.write(corpo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, destino)
    except BaseException:
        # Nunca deixe o temporário para trás virando "credencial parcial".
        try:
            os.unlink(temporario)
        except OSError:
            pass
        raise
    return destino
