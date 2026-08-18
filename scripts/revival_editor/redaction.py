"""Mascaramento de segredos para log e relatório do Revival Studio.

Exigido em três pontos do plano: fase 2 (*"mascarar tokens, senhas, userinfo de
URL e caminhos de segredo no painel"*), fase 5 (*"o relatório não contém segredo
nem chave privada"*) e §6.3 (*"não salvar senha de keystore, token admin,
segredo JWT"*).

Filosofia: mascarar **o que é comprovadamente segredo** (rótulo explícito,
userinfo de URL, corpo de PEM, JWT), não qualquer string longa. Mascarar demais
destrói o log de diagnóstico — e a skill `boot-diagnostics` depende de correlacionar
`[req]` do servidor com o logcat. Um hash SHA-256 precisa continuar legível.

Nota de arquitetura: o §6 do plano não lista este módulo. Ele foi extraído
porque `runner.py` (painel de log) e `reports.py` (JSON sanitizado) precisam da
mesma regra, e duplicá-la garantiria divergência entre o que a UI esconde e o
que o relatório grava.
"""
from __future__ import annotations

import re
from typing import Any

__all__ = ["MASK", "mask_secrets", "mask_mapping", "SECRET_KEY_HINTS"]

MASK = "***"

#: Nomes de chave que carregam segredo. Usado tanto no texto (`chave=valor`)
#: quanto na sanitização de dicionários antes de virar JSON.
SECRET_KEY_HINTS = (
    "token",
    "password",
    "passwd",
    "senha",
    "secret",
    "segredo",
    "apikey",
    "api_key",
    "authorization",
    "keystore_pass",
    "storepass",
    "keypass",
    "private_key",
    "jwt_secret",
)

_KEY_ALTERNATIVA = "|".join(re.escape(k) for k in SECRET_KEY_HINTS)

_REGRAS: tuple[tuple[re.Pattern[str], str], ...] = (
    # 1. userinfo de URL — o padding do fast path (https://u000@host/) e
    #    qualquer credencial colada pelo usuário.
    (re.compile(r"(?P<esquema>\bhttps?://)[^/\s@:]+(?::[^/\s@]*)?@"), r"\g<esquema>" + MASK + "@"),
    # 2. Authorization: Bearer <token>  /  Authorization: Basic <b64>
    (re.compile(r"(?i)\b(authorization\s*:\s*)(bearer|basic|token)\s+\S+"), r"\1\2 " + MASK),
    # 3. Bearer solto (linha de comando, log do servidor)
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-+/=]{8,}"), "Bearer " + MASK),
    # 4. chave=valor e chave: valor com nome sensível.
    #    O prefixo `[A-Za-z0-9_.\-]*` é essencial: sem ele, `\b` não casa em
    #    REVIVAL_ADMIN_TOKEN=... porque o `_` antes de TOKEN é caractere de
    #    palavra e não há fronteira ali. Regressão coberta em test_runner.py.
    (
        re.compile(rf"(?i)\b([A-Za-z0-9_.\-]*(?:{_KEY_ALTERNATIVA}))(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)"),
        r"\1\2" + MASK,
    ),
    # 5. flags de linha de comando: --admin-token XYZ, --password XYZ
    (re.compile(rf"(?i)(--(?:[a-z0-9-]*-)?(?:{_KEY_ALTERNATIVA})[a-z0-9-]*)(\s+|=)(\S+)"), r"\1\2" + MASK),
    # 6. cabeçalho de token do jogo
    (re.compile(r"(?i)\b(x-ubu-token\s*:\s*)\S+"), r"\1" + MASK),
    # 7. JWT (três segmentos base64url) — o token de sessão do cliente
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]*"), MASK + ".jwt"),
    # 8. corpo de PEM: nunca deixar chave privada entrar em log/relatório
    (
        re.compile(
            r"-----BEGIN ([A-Z ]*PRIVATE KEY|CERTIFICATE)-----.*?-----END \1-----",
            re.DOTALL,
        ),
        r"-----BEGIN \1----- " + MASK + r" -----END \1-----",
    ),
)


def mask_secrets(text: Any) -> str:
    """Devolve `text` com segredos conhecidos substituídos por `***`.

    Idempotente: aplicar duas vezes dá o mesmo resultado.
    """
    if text is None:
        return ""
    resultado = text if isinstance(text, str) else str(text)
    for padrao, substituto in _REGRAS:
        resultado = padrao.sub(substituto, resultado)
    return resultado


def mask_mapping(data: Any) -> Any:
    """Sanitiza estrutura (dict/list) antes de virar JSON de relatório.

    Mascara pelo **nome da chave** e também pelo conteúdo textual dos valores,
    recursivamente.
    """
    if isinstance(data, dict):
        limpo: dict[Any, Any] = {}
        for chave, valor in data.items():
            nome = str(chave).lower()
            if any(dica in nome for dica in SECRET_KEY_HINTS):
                limpo[chave] = MASK
            else:
                limpo[chave] = mask_mapping(valor)
        return limpo
    if isinstance(data, (list, tuple)):
        convertido = [mask_mapping(item) for item in data]
        return type(data)(convertido) if isinstance(data, tuple) else convertido
    if isinstance(data, str):
        return mask_secrets(data)
    return data
