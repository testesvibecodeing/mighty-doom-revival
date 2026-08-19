---
name: revival-server
description: Contrato do servidor de compatibilidade Mighty DOOM Revival (Node + SQLite) — envelope uts/code, guard de headers, token de sessão, regra de nunca enviar numérico não-nullable como null, como adicionar endpoint e como criar eventos em server/config/events.json. Use ao mexer em server/src/**, ao depurar "Malformed response payload" e ao configurar eventos, packs ou game data.
---

# Servidor Revival — contrato do wire

Node builtin `http` + SQLite (`node:sqlite`), ESM, sem framework. Entrada:
`server/src/index.js`. Requer Node **>= 22.5.0** (CI usa 24).

## Subir local

```bash
cd server
cp config/revival.example.json config/revival.json
cp config/packs.example.json  config/packs.json
cp config/events.example.json config/events.json
npm install
npm start          # ou: npm run dev  (node --watch)
```

Configs `*.json` (sem `.example`) são **runtime local e estão no `.gitignore`** —
edite os `.example.json` quando a mudança tiver que ser versionada.

Health: `GET /revival/health` → `{ ok, client_version, api_version,
game_data_loaded, packs, events, players, ... }`.

## Envelope — obrigatório em toda rota `/game/*`

```js
// server/src/index.js:52, 84, 88 (definições locais — são as vivas)
wire(data, code = 1000) → { uts: "yyyy-MM-ddTHH:mm:ss", code, ...data }
ok(res, data)           → 200 + wire(data)
fail(res, status, code) → status + wire({}, code)
```

> **Atenção — código morto:** `server/src/protocol.js` exporta as mesmas três
> funções e `server/src/baseline.js` as importa, mas **nada importa
> `baseline.js`/`protocol.js`** (medido com grep em 2026-08-17). O envelope real é
> o local do `index.js`. Em código novo, use os helpers já em escopo no módulo —
> **não adicione import de `protocol.js`**.

- `uts` é **UTC**, formato exato `yyyy-MM-ddTHH:mm:ss`. O parse do cliente é
  estrito (`ParseServerTimestamp`): epoch e `yyyy-MM-dd HH:mm:ss` **falham**.
  Confirmado por bisseção no emulador.
- `code` `1000` = sucesso. Demais faixas: `2000` cliente, `2100–2120` auth/JWT,
  `2200` parâmetros, `2300–2350` estado, `3000+` servidor
  (tabela completa: skill `il2cpp-recon`).

## Guard de requisição

Toda rota `/game/*` exige:

| Requisito | Falha |
|---|---|
| método `POST` | `405` code `2200` |
| header `x-ubu-apiversion` == `revival.api_version` do config | `403` code `2200` |
| `content-type: application/json` | `400` code `2200` |
| token em `x-ubu-token` ou `Authorization: Bearer` (rotas autenticadas) | `401` code `2101` |

`/game/auth/register` exige `client_version` igual ao config e **rejeita** requests
que já trazem `x-ubu-token` (`403`/`2200`).

## Prefixo `/collections/doom`

O cliente monta as URLs a partir de
`https://international.gear.bethesda.net/collections/doom` e o patch de hostname
preserva o path — então as chamadas chegam como `/collections/doom/game/...`.
`normalizePath()` (`server/src/index.js`) remove o prefixo `^/collections/<slug>`.
**As rotas internas são sempre só `/game/*`.** Não registre rota com o prefixo.

## Regra do `null` — a que mais quebra o boot

O parse do cliente é gerado por IL2CPP com tipos concretos. **Campo numérico
não-nullable que chega como `null` explícito derruba a desserialização inteira**,
o cliente loga `Malformed response payload` e, após 3 tentativas,
`Failed to launch after 3 attempts. Aborting.` — é o travamento em 100%.

```js
// errado
{ min_api_version: null }
// certo
if (event.min_api_version != null) wire.min_api_version = event.min_api_version
```

Campo sem valor é **omitido**, nunca `null`. Vale para todo DTO. Ao adicionar
qualquer campo novo, confirme a nulabilidade real do tipo C# (skill `il2cpp-recon`)
antes de emiti-lo.

## Adicionar um endpoint

1. **Confirme que a rota existe** na lista de 116 do `global-metadata.dat` (skill
   `il2cpp-recon`). Rota inventada = 404 no cliente e diagnóstico envenenado.
2. Escolha o lugar:
   - módulo próprio (`chapters.js`, `tutorial.js`, `battle-pass.js`, `quests.js`,
     `reward-tracks.js`, `progression.js`, `store.js`, `stats.js`) exportando um
     `handleXRequest(path, body, userId, repo, runtime)` que devolve
     `{ data }` | `{ error: [status, code, extra?] }` | `null` (não é minha rota);
   - agregado em `compat.js` (que encadeia os handlers acima);
   - direto no `handle()` de `index.js` para casos simples.
3. Responda com `ok(res, data)` / `fail(res, status, code)` — nunca monte o JSON na
   mão; o envelope vivo é o local do `index.js` (ver a nota de código morto acima).
4. Persistência via `Repository` (`db.js`), em transação quando houver concessão de
   recurso.
5. Teste em `server/test/<área>.mjs` e registre no `npm test` do
   `server/package.json` (o script `check` também lista cada arquivo novo).

## Eventos

`server/config/events.json` (exemplo em `events.example.json`):

```json
{
  "events": [
    {
      "id": 990001,
      "event_definition_id": 990001,
      "active": false,
      "always": true,
      "availability": 1,
      "event_type": 0,
      "channel": "game_mode",
      "args": {},
      "progress_template": { "event_id": 990001 }
    }
  ]
}
```

(Este é o conteúdo real do `events.example.json` — e do `events.json` local —
nesta base.)

- `active: false` desliga; `always: true` ignora janela de tempo; caso contrário
  `start_time`/`end_time` (ISO ou epoch) definem a janela. String de data
  inválida **lança exceção** em `active()` — valide antes de salvar.
- `availability`: `ScheduledEventAvailability { Archived=0, Available=1, Unpublished=2 }`.
- `channel`: para onde o progresso vai em `get-progress` — `game_mode` (default),
  `store_offer` ou `battle_pass`. `eventProgress()` roteia por este campo.
- `progress_template`: JSON inicial do estado por jogador, usado como semente em
  `repo.getState(userId, 'event', String(id), progress_template)`.
- `event_type`: existe **no config** mas **não é emitido no wire** (ver seção da
  hipótese abaixo).
- `args` é serializado como **JSON → UTF-8 → Base64** por `wireEvent()`.
- `wireEvent()` emite hoje: `id`, `event_definition_id`, `start_time`, `end_time`,
  `availability`, `args`, mais `min_api_version`/`max_api_version` **só quando
  presentes**. Em modo arquivo (`archive_mode`) `start_time`/`end_time` vão nulos
  de propósito (evento encerrado, não-editável).
- Rotas: `/game/events/get-schedule` (`eventSchedule`) e `/game/events/get-progress`
  (`eventProgress`, com `game_mode_events_progress`, `store_offer_events_states`,
  `battle_pass_events_states`). O schedule **NÃO inclui os battle passes de
  história do game-data**: o cliente 1.13.1 processa todo evento agendado como
  game-mode no `EventModeController` e NRE com o FTUE_BattlePass na lista
  (CARREGANDO eterno; provado no emulador 2026-08-19). O season fica visível no
  `get-progress` e operável via start/end-season. A VERIFICAR: com game-data
  completo, o conversor por `args` talvez tolere a entrada.

### CRUD de eventos pelo painel (sem editar arquivo)

O painel expõe `/account/admin/events` (admin.js, exige `is_admin`):

| Método/rota | Ação |
|---|---|
| `GET /account/admin/events` | lista |
| `POST /account/admin/events` | cria |
| `PATCH /account/admin/events/:id` | edita |
| `DELETE /account/admin/events/:id` | remove |

Mudanças por aí escrevem no `events.json` runtime (que está no `.gitignore`).
Para mudança **versionada**, edite o `events.example.json`.

### `event_type` — hipótese aberta (A VERIFICAR)

O cliente tem `ScheduledEventJsonConverter.conversions`,
`EventType { None=0, GameMode=1, StoreOffer=2, BattlePass=3 }` e o literal
`event_type` no dicionário de `[JsonProperty]`. Isso **sugere** que `event_type` é
o discriminador que escolhe a subclasse (`ScheduledGameModeEvent` /
`ScheduledStoreOfferEvent` / `ScheduledBattlePassEvent`) e o formato de `args`.

**Mas** o comentário em `server/src/events.js` registra a conclusão oposta, obtida
por bisseção anterior: o cluster do DTO no metadata seria exatamente
`id, event_definition_id, start_time, end_time, availability, min_api_version,
max_api_version, stop_time, args` — sem `event_type`. E o único evento do
`events.example.json` está com `active: false`.

Procedimento correto: **teste, não escolha por preferência.** Ative um evento,
emita `event_type` e observe o logcat (`boot-diagnostics`). Se `Malformed response
payload` aparecer só com o campo, a conclusão anterior se confirma. Registre o
resultado com o comando que o produziu.

Limite honesto: eventos configuram o que já existe no `game-data.json` + bundles.
**Não dá para criar cena, mapa ou capítulo novo** por configuração.

## Token de sessão — divergência conhecida (CONFIRMADO)

`db.js: createUser()` emite `randomBytes(32).toString('base64url')` — string opaca
de ~43 chars. Características medidas nesta base:

- gerado **uma vez no registro** e **estático por usuário** — todo login devolve o
  mesmo (`index.js`: `token: user.token`);
- guardado **em texto claro** na coluna `users.token`, sem expiração nem rotação;
- lookup por `userByToken` (`SELECT * FROM users WHERE token = ?`);
- existe um **segundo token, separado**, só para a sessão web do painel
  (`createWebSession()`, TTL de 30 dias) — não confunda os dois.

O cliente loga:

```text
E Unity : Session token is not a well formed JWT as expected
          Ubu.GameController:UpdateSessionToken(String)
```

e o metadata tem `Ubu.GameApi.DataObjects.GameSessionToken` com
`issuer/audience/issuedTimestamp/expiresTimestamp/subject/sessionId/sessionNonce`,
mais os literais `ubu_sid`/`ubu_nonce` e a família `JwtInvalid/JwtExpired/
JwtBadSignature/JwtBadSub` (2110–2113) no `ResponseCode`. Ou seja: espera um **JWT**
com claims `iss/aud/iat/exp/sub` + `ubu_sid` + `ubu_nonce`.

**RESOLVIDO** (implementado em `server/src/jwt.js`, validado no emulador
2026-08-19): register/login-device/refresh devolvem `issueSessionToken` e o
`user.token` opaco virou fallback legado. Contrato crítico: **`aud`/`audience`
precisam ser ARRAY** — o cliente tipa audience como `String[]` e string crua
derruba o `UpdateSessionToken` com `Could not cast or convert from System.String
to System.String[]` em todo register/login/refresh (bisseção no emulador).

## Outros pontos de atenção

- `game-data.json` incompleto gera centenas de `Cant find corresponding data tool
  data for ability <Nome> id <N>` no cliente. `/data` só serve o arquivo se o
  `Authorization` terminar com `revival.game_data_token`; sem arquivo, `503`.
- `research_mode` (env `RESEARCH_MODE`, default `true`): endpoint `/game/*`
  **desconhecido** não devolve 404 — é logado como `[research] endpoint ainda não
  implementado: <path>` e responde `ok()` vazio (`index.js:719-722`). Serve para
  mapear o que o cliente chama; ligado em produção, mascara rota faltante como
  "sucesso vazio" e envenena o diagnóstico. `archive_mode` muda o comportamento de
  battle pass/eventos.
- Log de request: `[req] METHOD url -> status Nbytes Xms` no stdout do servidor —
  é o lado servidor da correlação com o logcat.
- IAP e ads estão **deliberadamente desligados** (`/game/iap/*` → `400`/`2000`,
  `/game/ads/*` → `ads_disabled`). Não reative.
- Admin: `REVIVAL_ADMIN_TOKEN` no header `Authorization: Bearer` para
  `/revival/reload`, `/revival/requests` e o painel `/slayer`.

## Verificação

```bash
cd server && npm test        # check + todas as suítes .mjs
python scripts/check_revival_server.py --server meu.host.exemplo   # preflight HTTPS + uts
```

Estado por módulo: `docs/ENDPOINT-MATRIX.md`. Plano: `docs/ROADMAP-100-PERCENT.md`.
