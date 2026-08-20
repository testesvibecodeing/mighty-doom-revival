"""Autenticação Revival — o que a Unity do 1.13.1 já sabe ler.

Dois artefatos locais do app, ambos medidos no dispositivo real em 2026-08-20
(backup em `work/audit-opus/backup/`, nunca versionado):

- `credentials.json` — lido por `Ubu.CredentialStore`; ver `credentials.py`;
- `gpg.config` — `Ubu.GooglePlay.GooglePlayLocalConfig` serializado pelo
  BinaryFormatter do .NET; ver `gpg_config.py`.

Este pacote é a camada PROVÁVEL da autenticação Revival: produz e valida os dois
arquivos byte a byte, sem depender de emulador. Quem os grava no dispositivo
(uma Activity Android própria, ou o rig via ADB) é outra camada.
"""

from .credentials import (
    CREDENTIALS_FILENAME,
    SAVE_DATA_VERSION,
    Credentials,
    CredentialsError,
    credentials_from_register_response,
    load_credentials,
    write_credentials,
)
from .gpg_config import (
    GPG_CONFIG_FILENAME,
    GooglePlayLocalConfig,
    GpgConfigError,
    parse_gpg_config,
    serialize_gpg_config,
)

__all__ = [
    "CREDENTIALS_FILENAME",
    "SAVE_DATA_VERSION",
    "Credentials",
    "CredentialsError",
    "credentials_from_register_response",
    "load_credentials",
    "write_credentials",
    "GPG_CONFIG_FILENAME",
    "GooglePlayLocalConfig",
    "GpgConfigError",
    "parse_gpg_config",
    "serialize_gpg_config",
]
