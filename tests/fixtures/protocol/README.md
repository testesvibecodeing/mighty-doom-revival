# Fixtures de protocolo — request/response reais sanitizados

Cada arquivo é um par request/response observado de um endpoint `game/*`,
um por endpoint, no formato:

```json
{
  "endpoint": "game/auth/register",
  "provenance": "client | server-replay",
  "captured_at": "2026-08-17T10:36:00Z",
  "sanitized": true,
  "request": { "method": "POST", "path": "/game/auth/register", "headers": {...}, "body": {...} },
  "response": { "status": 200, "body": { "uts": "<uts>", "code": 1000, ... } }
}
```

## Provenance — a diferença que importa

- `server-replay`: capturado contra o servidor Revival com dataset sintético
  (`scripts/capture_protocol_fixtures.mjs`). Prova o contrato que o servidor
  fala HOJE; não prova que o cliente aceita.
- `client`: capturado do cliente real/emulador via `scripts/client_harness.py`.
  Só esta provenance liga `request_observed`/`response_observed` no
  `compatibility.json` (o gerador lê estes arquivos).

## Sanitização

Tokens, passwords e recovery codes viram `<token>`/`<password>`/
`<recovery-code>`; `device_id` e `push_token` viram `<device-id>`/`<push-token>`;
`puuid` vira `<puuid>`; timestamps voláteis (`uts`) viram `<uts>`; URLs absolutas
perdem o host (`<base>/data`); `account_age`/`last_login` zeram. O shape do
wire — chaves, tipos, nullabilidade — permanece exatamente o observado.

`puuid` **não é credencial**: é o identificador estável da conta no wire, que
sozinho não dá acesso a nada. Ele é redigido porque correlaciona execuções e
sobrevive a restart, e a fixture só precisa provar a chave e o tipo. As
fixtures `server-replay` são geradas contra um servidor de captura descartável
(`scripts/capture_protocol_fixtures.mjs`), então nem todo valor que aparecia
nelas vinha de uma conta real — a redação vale para as duas provenances por
uniformidade, não por classificação de risco.

## Regras

1. Nenhum dump de material proprietário aqui (só wire JSON sanitizado).
2. Campos numéricos não-nullable nunca podem aparecer como `null` em um
   response com provenance `client` — se apareceram, o parse do cliente
   derrubaria (`Malformed response payload`).
3. Regenerar os server-replay: `node scripts/capture_protocol_fixtures.mjs`.
   Atualizar o registro depois: `python scripts/generate_endpoint_matrix.py`.
