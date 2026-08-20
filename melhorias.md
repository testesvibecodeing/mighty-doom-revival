# Plano — Documentação de melhorias + AGENTS.md/Skills + GUI

## Context

O projeto já tem um pipeline funcional (patcher de APK, servidor Node/SQLite, site,
editor de loading screen), mas o conhecimento crítico está espalhado entre
`RELATORIO-STATUS.md`, `docs/*.md` e logcats soltos em `work/apk-patch/`. LLMs mais
fracas "patinam" ao mexer no APK porque não existe um documento único, prescritivo e
verificável, e porque as tabelas reais do cliente (rotas, DTOs, códigos de erro)
nunca foram extraídas — foram inferidas por tentativa e erro.

O sintoma que o usuário relata (**jogo trava em 100% e não sai disso**) está
reproduzido nos logs do próprio repositório e tem causas identificáveis. Este plano
entrega: (1) um `.md` único passo a passo na raiz, (2) `AGENTS.md` + Skills para
guiar qualquer LLM, (3) um extrator IL2CPP reutilizável, (4) uma GUI Python unificada.

**Escopo confirmado com o usuário:** apenas criação de documentação/ferramentas.
Não altero `server/src/**` — as correções entram no `.md` como passos prescritivos
com código pronto para colar.

---

## Achados da análise (base factual do documento)

Extraídos nesta sessão de `input/mighty-doom.apk` (615 MB, `com.bethsoft.ubu`
1.13.1, Unity 2021.3.25f1 / IL2CPP / arm64) e de `work/apk-patch/boot*-logcat.txt`.

### Confirmado por parse do `global-metadata.dat` (v29, sanity `0xFAB11BAF`)

- **116 rotas** `game/*` na tabela de string literals — hoje o servidor implementa
  ~40. Lista completa extraída (auth, player, session, inventory, store, events,
  battle-pass, chapters, quests, gear, slayers, talents, armory, daily/idle-rewards,
  inbox, reward-tracks, codes, devices, identity, iap, ads, xbox, bnet).
- **Tabela `Ubu.GameApi.ResponseCode` completa** (decodificada dos default values em
  compressed-int): `1000 Success`, `2000 ClientError`, `2010/2011` versão,
  `2100–2120` auth/JWT, `2200/2210` parâmetros, `2300–2350` estado,
  `2400–2410` IAP, `3000–3131` servidor/plataformas.
- **DTO de request/response de todos os 116 endpoints** (`Ubu.GameApi.Methods.*Api/*Response`),
  resolvidos via tabela `nestedTypes`.
- **Dicionário de 487 nomes de wire** (`[JsonProperty]` no blob de custom attributes)
  + confirmação de `Newtonsoft.Json` com `SnakeCaseNamingStrategy` como fallback.
- **Enums de evento**: `EventType {None=0, GameMode=1, StoreOffer=2, BattlePass=3}`,
  `ScheduledEventAvailability {Archived=0, Available=1, Unpublished=2}`, mais
  `BattlePassTaskType`, `BattlePassSeasonActiveState/PremiumState`, `StatCategory`,
  `InventorySlotType`, `ChapterState`.

### Causas do travamento em 100%

1. **Session token não é JWT.** O logcat traz
   `Session token is not a well formed JWT as expected` em
   `Ubu.GameController:UpdateSessionToken(String)`. O servidor emite
   `randomBytes(32).toString('base64url')` ([db.js:187](server/src/db.js#L187)).
   O cliente tem `Ubu.GameApi.DataObjects.GameSessionToken` com
   `issuer/audience/issuedTimestamp/expiresTimestamp/subject/sessionId/sessionNonce`
   e os literais `ubu_sid`/`ubu_nonce` no dicionário de wire — ou seja, espera um JWT
   com claims `iss/aud/iat/exp/sub` + `ubu_sid` + `ubu_nonce`. Confirma também o
   bloco `JwtInvalid/JwtExpired/JwtBadSignature/JwtBadSub` (2110–2113) no ResponseCode.
2. **`Malformed response payload` → abort.** `Network response (5)` e
   `Network response (17)` seguidos de `Failed to launch after 3 attempts. Aborting.`
   em `Ubu.GameController:Relaunch()`. É exatamente o "enche a barra e morre".
   *Não consegui resolver a que enum pertencem os índices 5 e 17* — o `.md` vai
   documentar o método de bisseção (correlacionar com o log `[req]` do servidor)
   em vez de afirmar um palpite.
3. **GameData incompleto.** Centenas de
   `Cant find corresponding data tool data for ability <Nome> id <N>` em
   `Ubu.GameController:ProcessGameData(String)`. O `game-data.json` servido não tem
   as definições de ability que o cliente exige.
4. **CRC do catálogo Addressables** (já resolvido, mas é regressão fácil):
   `CRC Mismatch ... Will not load AssetBundle` → `RemoteProviderException`.

### Hipótese a testar (não afirmar como fato)

`ScheduledEventJsonConverter.conversions` + `EventType` + `event_type` presente no
dicionário de `[JsonProperty]` sugerem que `event_type` é o **discriminador** que
escolhe a subclasse (`ScheduledGameModeEvent` / `ScheduledStoreOfferEvent` /
`ScheduledBattlePassEvent`) e o tipo de `args`. O `wireEvent()` atual
([events.js:29](server/src/events.js#L29)) **omite** `event_type`, e o único evento
em `server/config/events.json` está com `active: false`. O `.md` registra isso como
teste #1 do roteiro de eventos, com o aviso de que a bisseção anterior do projeto
concluiu o contrário.

---

## Arquivos a criar

### 1. `MELHORIAS-PASSO-A-PASSO.md` (raiz) — entrega principal

Escrito em português, tom prescritivo, numerado, cada passo com **comando exato +
resultado esperado + como saber que falhou**. Regra editorial: todo bloco separa
`CONFIRMADO` (medido nesta base) de `A VERIFICAR` (hipótese).

Seções:

1. Como usar este documento (contrato para LLM fraca: nunca inventar rota, sempre
   rodar o verificador antes de dizer "pronto").
2. Mapa do repositório e o que cada script faz.
3. Toolchain: Python 3.11+/UnityPy 1.25.3, **JDK 17+** (atenção: o `PATH` desta
   máquina tem Java 11; usar `.tools/jre17`), Node 25, ADB.
4. **Manipulação de APK — completa.** Estrutura real do APK (202 entradas
   `assets/bin`, `assets/aa/` com bundle de 494 MB, `libil2cpp.so` de 68 MB),
   os três caminhos de patch (metadata direto com padding de userinfo /
   bundle-aware UnityPy / `zero_catalog_crc`), limite de hostname ditado pelo
   precheck (`check_patch_length.py`; host de gameplay medido: 31 bytes),
   assinatura, injeção de loading screen, e o fluxo de rebuild sem `apktool`.
5. **Recon IL2CPP**: como o `global-metadata.dat` v29 é lido, com o script novo.
6. **As 116 rotas** em tabela, com coluna "implementado no Revival" (comparação
   contra `server/src/index.js`, `compat.js`, `chapters.js`, `tutorial.js`).
7. **Tabela ResponseCode** completa.
8. **Dicionário de wire names** + regra de serialização (snake_case + overrides).
9. **Eventos**: enums, formato do `ScheduledEvent`, `args` em Base64/JSON, como
   criar eventos próprios em `server/config/events.json`, o que é game-mode event,
   store offer event e battle pass, e os limites (mapas/capítulos vêm do
   `game-data.json` + bundles — dá para configurar, não para criar cena nova).
10. **Diagnóstico do travamento em 100%** — roteiro passo a passo com os 4 achados.
11. **Correções prescritas do servidor** (código pronto, não aplicado): JWT de
    sessão, `event_type`, campos faltantes de `user_data`
    (`daily_reward_brief`, `first_install`), `session/refresh` devolvendo JWT novo.
12. **MCP opcional**: `apktool-mcp-server` e `jadx-mcp-server` (zinja-coder), com o
    alerta de que full-decode neste APK é lento/frágil e o caminho
    `ZipFile` + UnityPy do projeto continua sendo o principal.
13. Roadmap numerado até 100%.

### 2. `AGENTS.md` (raiz)

Contrato curto para qualquer agente: regras inegociáveis (nunca commitar APK/assets,
nunca aumentar hostname além do orçamento do precheck (31 bytes no build
   atual), sempre `zero_catalog_crc` após alterar
bundle, sempre rodar `verify_patched_apk.py`), mapa de skills, e ponteiros para o
`.md` grande.

### 3. Skills em `.claude/skills/<nome>/SKILL.md`

- `apk-patch` — pipeline de patch fim-a-fim e armadilhas.
- `il2cpp-recon` — extrair rotas/DTOs/enums/wire-names do `global-metadata.dat`.
- `revival-server` — contrato do wire, envelope `uts`/`code`, regra de nunca mandar
  numérico não-nullable como `null`.
- `boot-diagnostics` — triagem do logcat até a causa raiz do travamento.

Ajustar `.gitignore`: manter `.claude/` ignorado mas liberar
`!.claude/skills/` e `!.claude/skills/**`.

### 4. `scripts/dump_il2cpp_metadata.py`

Extrator reutilizável (stdlib pura, sem UnityPy) que produz os JSONs que alimentam
as tabelas do `.md`: `--routes`, `--enums`, `--dtos`, `--wire-names`.
É o que torna o documento reproduzível em vez de um dump congelado.
Teste em `tests/test_dump_il2cpp_metadata.py` com um metadata sintético mínimo.

### 5. `scripts/revival_studio.py` + `.bat`/`.sh` — GUI unificada

Tkinter/ttk, seguindo o padrão já estabelecido em
[loading_screen_editor.py](scripts/loading_screen_editor.py) (worker thread +
`queue.Queue` para log, `drain_log_queue`, preview). Reusa
`inject_loading_screen.py` e chama os scripts existentes por `subprocess`.

Abas: **Analisar** (`analyze_apk.py`) · **Patch** (hostname com validação de 24
bytes ao vivo via `check_patch_length.py`) · **Loading screen** (embute o editor
atual) · **Servidor** (`check_revival_server.py` + health) · **Recon**
(`dump_il2cpp_metadata.py`, com busca nas 116 rotas) · **Diagnóstico**
(carrega logcat e destaca as assinaturas conhecidas).
Tema escuro estilo DOOM, barra de progresso, log com cores.

---

## Verificação

```bash
# 1. Extrator: reproduz as tabelas do .md a partir do APK real
python scripts/dump_il2cpp_metadata.py --apk input/mighty-doom.apk --routes
#    esperado: 116 rotas; ResponseCode com Success=1000 e InvalidCredentials=2101

# 2. Testes
python -m pytest tests/ scripts/ -q          # suíte Python (inclui o teste novo)
cd server && npm test                        # suíte do servidor, deve seguir PASS

# 3. GUI abre e cada aba responde
python scripts/revival_studio.py

# 4. Skills carregam
#    /apk-patch, /il2cpp-recon, /revival-server, /boot-diagnostics no Claude Code
git check-ignore -v .claude/skills/apk-patch/SKILL.md   # deve NÃO estar ignorado

# 5. Links do .md
#    conferir que todo caminho citado existe (script de checagem no fim do doc)
```

Critério de aceite do `.md`: uma LLM sem contexto consegue, lendo só ele,
(a) gerar um APK patchado válido, (b) subir o servidor, (c) explicar por que o
jogo trava em 100% e (d) criar um evento próprio.
