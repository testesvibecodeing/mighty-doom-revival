---
name: il2cpp-recon
description: Extrair fatos reais do cliente Mighty DOOM a partir do global-metadata.dat (v29) — as 116 rotas game/*, a tabela Ubu.GameApi.ResponseCode, DTOs de request/response, enums e os nomes de wire dos [JsonProperty]. Use antes de implementar qualquer endpoint, campo de JSON ou código de erro, e sempre que a alternativa seria adivinhar o contrato do cliente.
---

# Recon IL2CPP — global-metadata.dat v29

**Regra desta skill: nada aqui se responde de memória.** Ou você extraiu do
metadata nesta sessão e marca `CONFIRMADO` com o comando que usou, ou marca
`A VERIFICAR` e diz que é hipótese.

## Onde está

```text
input/mighty-doom.apk
  └── assets/bin/Data/Managed/Metadata/global-metadata.dat   ← v29, sanity 0xFAB11BAF
  └── lib/arm64-v8a/libil2cpp.so                             ← 68 MB, código nativo
```

Leia direto do ZIP com `zipfile` — **não** extraia o APK inteiro (615 MB) nem rode
`apktool d` só para isso.

## Cabeçalho (CONFIRMADO nesta base)

`int32` little-endian. Após `sanity` e `version`, o header é um vetor de pares
`(offset, size)` em bytes:

| Índice | Campo | Valor medido no 1.13.1 |
|---:|---|---:|
| `h[0]` | sanity | `0xFAB11BAF` |
| `h[1]` | version | `29` |
| `h[2]/h[3]` | stringLiteral (tabela) | `256` / `130104` |
| `h[4]/h[5]` | stringLiteralData | `130360` / `519296` |
| `h[6]/h[7]` | string (identificadores C) | `649656` / `2003208` |

Cada entrada da tabela de literais tem 8 bytes: `(length: uint32, dataIndex: int32)`,
com `dataIndex` relativo a `stringLiteralData`. **16.263 literais** no total.

Os pares seguintes (`events`, `properties`, `methods`, `parameterDefaultValues`,
`fieldDefaultValues`, `fieldAndParameterDefaultValueData`, `fieldMarshaledSizes`,
`parameters`, `fields`, `genericParameters`, …, `typeDefinitions`, `images`,
`assemblies`, `attributeData`, `attributeDataRange`) seguem a ordem canônica do
v29, mas **valide cada região antes de confiar nela** (ver "Como validar" abaixo).

## Nível 1 — literais (sempre funciona)

Extrai as 116 rotas, os nomes de wire candidatos e qualquer string do cliente.
Este bloco foi executado nesta base e devolve `116`:

```python
import zipfile, struct

z = zipfile.ZipFile("input/mighty-doom.apk")
d = z.open("assets/bin/Data/Managed/Metadata/global-metadata.dat").read()

h = struct.unpack("<32I", d[:128])
assert h[0] == 0xFAB11BAF and h[1] == 29, "metadata não é v29"
lit_off, lit_size, data_off = h[2], h[3], h[4]

lits = []
for i in range(lit_size // 8):
    ln, di = struct.unpack_from("<Ii", d, lit_off + i * 8)
    lits.append(d[data_off + di : data_off + di + ln].decode("utf-8", "replace"))

routes = sorted({s for s in lits if s.startswith("game/")})
print(len(routes))      # 116
```

Variações úteis sobre a mesma lista `lits`:

- rotas por módulo: `game/auth/*`, `game/player/*`, `game/session/*`,
  `game/inventory/*`, `game/store/*`, `game/events/*`, `game/battle-pass/*`,
  `game/chapters/*`, `game/quests/*`, `game/gear/*`, `game/slayers/*`,
  `game/talents/*`, `game/armory/*`, `game/daily-rewards/*`, `game/idle-rewards/*`,
  `game/inbox/*`, `game/reward-tracks/*`, `game/codes/*`, `game/devices/*`,
  `game/identity/*`, `game/iap/*`, `game/ads/*`, `game/xbox/*`, `game/bnet/*`;
- candidatos a nome de wire: literais `^[a-z0-9]+(_[a-z0-9]+)*$` (snake_case);
- literais de sessão conhecidos: `ubu_sid`, `ubu_nonce`.

## Nível 2 — identificadores, tipos e enums

A tabela `string` (`h[6]/h[7]`) é um blob de C-strings `NUL`-terminadas com nomes
de tipo, campo, método e namespace. Dela saem:

- `Ubu.GameApi.Methods.*Api` / `*Response` — os DTOs de cada endpoint;
- `Ubu.GameApi.ResponseCode` — a tabela de códigos;
- `Ubu.GameApi.DataObjects.GameSessionToken` e seus campos
  (`issuer`, `audience`, `issuedTimestamp`, `expiresTimestamp`, `subject`,
  `sessionId`, `sessionNonce`);
- enums de evento (`EventType`, `ScheduledEventAvailability`, `BattlePassTaskType`,
  `BattlePassSeasonActiveState/PremiumState`, `StatCategory`, `InventorySlotType`,
  `ChapterState`).

Para **valores** de enum: os campos constantes vivem em `fieldDefaultValues`,
apontando para `fieldAndParameterDefaultValueData`, onde inteiros estão em
**compressed int** (mesmo esquema do `il2cpp` para `int32` variável). Para DTOs
aninhados (`XApi/XResponse`), resolva pela tabela `nestedTypes` a partir do
`typeDefinition` do tipo externo.

Para os nomes de wire (`[JsonProperty("...")]`), o argumento do atributo está no
blob `attributeData`/`attributeDataRange`; o par (tipo do atributo → literal) sai
cruzando com a tabela de literais do Nível 1.

**Fallback de serialização:** `Newtonsoft.Json` com `SnakeCaseNamingStrategy` — um
campo sem `[JsonProperty]` vira `snake_case` do nome C#.

## Como validar antes de afirmar

Toda região que você derivar do header precisa passar por um sanity check antes de
virar tabela em documento ou código:

1. `offset + size <= len(d)` e `offset` alinhado a 4;
2. decodifique **3 entradas** e confira que o resultado é plausível (nome de tipo
   imprimível, `dataIndex` dentro da região de dados, contagem inteira);
3. cruze com um fato independente: por exemplo, `ResponseCode` tem que conter
   `Success = 1000` e a família `2100–2120` de auth/JWT; a lista de rotas tem que
   conter `game/auth/login-device` e `game/events/get-schedule`;
4. se qualquer passo falhar, **pare e reporte** — não ajuste offsets no chute.

## Tabela ResponseCode (referência de conferência)

Faixas conhecidas do `Ubu.GameApi.ResponseCode`; use como *checksum* da extração,
não como substituto dela:

| Faixa | Significado |
|---|---|
| `1000` | Success |
| `2000` | ClientError |
| `2010`, `2011` | versão de cliente/API |
| `2100–2120` | auth/JWT (`JwtInvalid/JwtExpired/JwtBadSignature/JwtBadSub` em 2110–2113) |
| `2200`, `2210` | parâmetros inválidos |
| `2300–2350` | estado inválido |
| `2400–2410` | IAP |
| `3000–3131` | erro de servidor / plataformas |

O servidor usa hoje `1000`, `2000`, `2101`, `2200` (`server/src/protocol.js`).

## Script reutilizável

`melhorias.md` prevê `scripts/dump_il2cpp_metadata.py` (stdlib pura, sem UnityPy)
com `--routes`, `--enums`, `--dtos`, `--wire-names`. **Ele ainda não existe.** Se a
tarefa precisar de extração repetível, crie-o nesse caminho, com teste em
`tests/test_dump_il2cpp_metadata.py` usando um metadata sintético mínimo — não
cole um dump congelado em documento.

Critério de aceite do extrator:

```bash
python scripts/dump_il2cpp_metadata.py --apk input/mighty-doom.apk --routes
# esperado: 116 rotas
# esperado: ResponseCode com Success=1000
```

## Comparar com o que o servidor implementa

```bash
grep -o "game/[a-z0-9/-]*" server/src/*.js | sort -u
```

`server/src/index.js` responde hoje ~30 caminhos `game/*` diretamente, mais o que
`compat.js`, `chapters.js` e `tutorial.js` agrupam — contra 116 no cliente. A
diferença é o roadmap (`docs/ENDPOINT-MATRIX.md`, `docs/ROADMAP-100-PERCENT.md`).

## Não faça

- Não rode Il2CppDumper/jadx "para ver" — é lento neste APK e o output não cabe no
  repositório (e está no `.gitignore` por isso).
- Não cole dumps brutos, listas completas de assets ou trechos de código
  descompilado em arquivos versionados. Registre só o dado técnico necessário.
- Não afirme a que enum pertence um índice numérico de log (`Network response (5)`)
  sem ter resolvido o enum — use a skill `boot-diagnostics` e o método de bisseção.
