# AGENTS.md — contrato para agentes neste repositório

Projeto de **preservação pessoal** do Mighty DOOM 1.13.1 (`com.bethsoft.ubu`, Unity
2021.3.25f1, IL2CPP, arm64). Três peças: um **patcher de APK** (Python), um
**servidor de compatibilidade clean-room** (Node + SQLite) e um **site/painel**.

Leia este arquivo inteiro antes de tocar em qualquer coisa. Ele é curto de
propósito. O detalhe operacional está nas skills (`.claude/skills/`) e em `docs/`.

---

## Regras inegociáveis

1. **Nunca commitar material proprietário.** APK, `.xapk`, `.aab`, assets, bundles,
   dumps, logcats, pcaps, screenshots, keystores e certificados. O `.gitignore` já
   bloqueia `input/`, `output/`, `work/`, `reports/`, `.tools/`, `*.apk`, `*.png`,
   `*.jks`, `*.pem`. **Nunca use `git add -f`** para contornar isso.
2. **Nunca aumente o hostname além do orçamento de bytes.** O endpoint vive dentro
   do `global-metadata.dat`; crescer a string exigiria realocar seções e desloca os
   offsets de todo o resto do arquivo — o app deixa de bootar. O orçamento é o
   comprimento do host oficial encontrado (no 1.13.1: `international.gear.bethesda.net`,
   **31 bytes**; o `slayersclub.bethesda.net` citado em docs antigos tem 24).
   **Quem decide é `scripts/check_patch_length.py`, não o seu palpite.** Exit 4 =
   não cabe no fast path.
3. **Alterou qualquer bundle em `assets/aa/**`? Zere o `m_Crc` no
   `assets/aa/catalog.json`** (`zero_catalog_crc`). Sem isso o jogo abre o menu e
   morre no load da cena com `CRC Mismatch` / `RemoteProviderException`.
4. **Nunca declare um APK pronto sem `scripts/verify_patched_apk.py` passando** no
   arquivo final — depois de assinar, não antes.
5. **Nunca invente uma rota, um campo de wire ou um código de erro.** Todos os 116
   endpoints, os DTOs e a tabela `ResponseCode` existem como dado extraível do
   `global-metadata.dat`. Extraia (skill `il2cpp-recon`) ou diga que não sabe.
6. **Nunca envie campo numérico não-nullable como `null`** no JSON do wire. O parse
   do cliente derruba com `Malformed response payload` e o jogo aborta. Campo sem
   valor é **omitido**.
7. **Separe fato de hipótese** em tudo que escrever: `CONFIRMADO` (medido nesta
   base, com o comando que mediu) vs `A VERIFICAR` (hipótese). Não promova hipótese
   a fato porque "faz sentido". **Antes de tentar consertar algo, consulte
   `research/DEAD-ENDS.md`** — hipótese refutada só volta com evidência nova.
   Endpoint não é "done" porque responde 200: o DoD por rota vive em
   `compatibility.json` (8 gates) e quem seleciona o próximo trabalho é
   `scripts/next_task.py`.
8. **Não edite `server/config/revival.json`, `packs.json`, `events.json`** — são
   runtime local e estão no `.gitignore`. Mexa nos `*.example.json` correspondentes.
9. **Rode a suíte antes de dizer "pronto"** (bloco Verificação abaixo). Se algo
   falhou, diga que falhou e cole a saída.

---

## Mapa do repositório

| Caminho | O que é |
|---|---|
| `scripts/patch_apk.py` | Patch direto de hostname (fast path, byte-preserving + userinfo padding) |
| `scripts/patch_unity_bundle.py` | Reserialização UnityPy de bundles + `zero_catalog_crc()` |
| `scripts/patch_bundle_from_report.py` | Fallback bundle-aware (`--sweep-all-bundles`) |
| `scripts/patch_unity_raw_strings.py` | Troca de string Unity crua, com prova de comprimento/alinhamento |
| `scripts/analyze_apk.py` | SHA-256, indicadores Unity/IL2CPP, hosts encontrados |
| `scripts/check_patch_length.py` | Precheck do orçamento de bytes (exit 0 / 4) |
| `scripts/verify_patched_apk.py` | Verificação do endpoint dentro do APK (obrigatória) |
| `scripts/inject_loading_screen.py` / `loading_screen_editor.py` | Loading screen custom (CLI + GUI Tkinter) |
| `scripts/check_revival_server.py` | Preflight HTTPS do servidor (health + `uts`) |
| `compatibility.json` | **Fonte de verdade dos 116 endpoints** — DoD por rota, evidências e fallbacks; gerada por script, não editada à mão |
| `scripts/dump_il2cpp_metadata.py` | Extrator read-only do `global-metadata.dat` v29 — modos `--routes`/`--enums`/`--dtos`/`--wire-names`/`--response-codes`/`--all` com validação por fechamentos (layout derivado e provado contra o APK real; teste com metadata sintético) |
| `scripts/generate_endpoint_matrix.py` | Sincroniza `compatibility.json` (campos derivados de `server/src`, `server/test`, fixtures) e regenera `docs/ENDPOINT-MATRIX.md`; `--check` é gate de CI |
| `scripts/next_task.py` | Seleciona deterministicamente o próximo gap (módulo por prioridade → primeiro gate DoD falso) |
| `scripts/verify_everything.py` | **Gate único de conclusão**: npm test + regressões Python + sync do registro + coerência + servidor vivo/APK opcionais |
| `scripts/client_harness.py` | Valida fluxo no cliente/emulador via ADB (logcat, assinaturas fatais, sequência de endpoints, fallbacks; exit != 0 = fluxo falhou) |
| `scripts/capture_protocol_fixtures.mjs` | Captura fixtures `server-replay` de req/res sanitizados |
| `tests/fixtures/protocol/` | Pares req/res reais sanitizados; provenance `client` (harness) liga `request/response_observed` no registro |
| `research/DEAD-ENDS.md` | Hipóteses refutadas com evidência — **consulte antes de tentar consertar qualquer coisa** |
| `scripts/patch-apk.{bat,sh}` | Orquestração fim-a-fim em 8 passos |
| `server/src/index.js` | HTTP builtin, roteamento `/game/*`, `/revival/*`, `/data`; **envelope vivo `wire()`/`ok()`/`fail()` nas linhas 52/84/88** |
| `server/src/protocol.js` + `baseline.js` | **Código legado/morto** — nada os importa (só `baseline.js` importa `protocol.js`). Não os use em código novo; o envelope real é o local do `index.js` |
| `server/src/db.js` | SQLite, usuários, token de sessão |
| `server/src/events.js` | `eventSchedule()` / `eventProgress()` / `wireEvent()` |
| `server/src/compat.js` | Rotas de compatibilidade agrupadas |
| `server/src/admin.js` | Sub-rotas `/account/admin/*` (users, grants, packs, events CRUD, site, notifications) |
| `server/src/site.js` | Site estático, `/revival/apk`, upload/download do APK |
| `melhorias.md` | Plano de melhorias e specs pendentes (documento de trabalho, não versionado) |
| `docs/APK-PATCH.md` | Detalhe do patcher, orçamento de bytes, CRC do catálogo |
| `docs/ENDPOINT-MATRIX.md` | Estado por módulo da API |
| `docs/ROADMAP-100-PERCENT.md` | Plano até paridade |
| `RELATORIO-STATUS.md` | Estado atual medido |
| `work/apk-patch/*.txt` | Logcats de boot (ignorados pelo git) |

Ignorados e **não versionados**: `input/`, `output/`, `work/`, `.tools/`,
`reports/`, `server/data/*`, `server/config/{revival,packs,events,site}.json`.

---

## Skills

Invoque a skill antes de começar o trabalho correspondente — elas trazem os
comandos exatos, os exit codes e as armadilhas já pagas neste projeto.

| Skill | Use quando |
|---|---|
| `apk-patch` | Gerar/alterar/assinar/verificar o APK, trocar hostname, injetar loading screen |
| `il2cpp-recon` | Precisar de rota, DTO, enum, wire name ou código de erro reais do cliente |
| `revival-server` | Mexer em `server/src/**`, criar endpoint, depurar wire/JSON, criar evento |
| `boot-diagnostics` | O jogo travar (barra em 100%, tela preta, crash), triagem de logcat |

---

## Verificação

```bash
# Gate único (npm test do servidor + regressões Python + sync do registro +
# coerência do compatibility.json; opcional --server/--apk para o resto)
python scripts/verify_everything.py

# Próximo gap determinístico (módulo por prioridade, gate DoD)
python scripts/next_task.py

# Resincronizar registro/matriz após implementar algo
python scripts/generate_endpoint_matrix.py
```

Ciclo por funcionalidade (obrigatório): extrair contrato → implementar →
teste servidor → `scripts/client_harness.py` no emulador → persistência após
restart → `generate_endpoint_matrix.py --set/--note` com a evidência → commit
→ `next_task.py`.

```bash
# Servidor (a suíte que o CI roda)
cd server && npm test

# Regressões do patcher (as mesmas do .github/workflows/server-ci.yml)
python scripts/test_check_revival_server.py
python scripts/test_patch_apk.py
python scripts/test_patch_network_security.py
python scripts/test_patch_primary_api_host.py
python scripts/test_patcher_orchestration.py
python tests/test_zero_catalog_crc.py
python tests/test_inject_loading_screen.py

# APK final (obrigatório antes de dizer que está pronto)
python scripts/verify_patched_apk.py --apk output/mighty-doom-revival.apk \
  --server <host> --report work/apk-patch/final-apk-verification.json
```

Na primeira execução do servidor, copie os configs de exemplo:

```bash
cd server && cp config/revival.example.json config/revival.json \
  && cp config/packs.example.json config/packs.json \
  && cp config/events.example.json config/events.json
npm install && npm start
```

---

## Fatos confirmados desta base

Medidos neste repositório — pode citar sem re-verificar, mas re-verifique se o APK
de entrada mudar.

- APK alvo: `com.bethsoft.ubu` 1.13.1 build 84862, Unity 2021.3.25f1, IL2CPP arm64.
- `assets/bin/Data/Managed/Metadata/global-metadata.dat`: **v29**, sanity
  `0xFAB11BAF`, 16.263 string literals, **116 rotas `game/*`**.
- Base da API oficial: `https://international.gear.bethesda.net/collections/doom`.
  O patch preserva o path, então o cliente chama `/collections/doom/game/...`;
  `normalizePath()` em `server/src/index.js` remove o prefixo.
- Envelope de resposta: `{ "uts": "yyyy-MM-ddTHH:mm:ss", "code": 1000, ... }`.
  `uts` é UTC e o parse do cliente é estrito (epoch e `yyyy-MM-dd HH:mm:ss` falham).
- Guard de toda rota `/game/*`: `POST` + header `x-ubu-apiversion` igual ao
  `api_version` do config + `content-type: application/json`.
- `java` no PATH desta máquina é **11**; apktool/uber-apk-signer precisam de **17+**:
  use `.tools/jre17/jdk-17.0.20+8-jre/bin/java.exe`.
- Toolchain pinada: **Apktool 3.0.3** e **uber-apk-signer 1.3.0** (SHA-256 fixados em
  `scripts/setup-patcher-tools.*`), **UnityPy 1.25.3** exata. Não "atualize para
  resolver" — outra versão reserializa diferente e invalida os testes.
- O servidor implementa **57 caminhos `/game/*` distintos** (medido com
  `grep -o "game/[a-z0-9/-]*" server/src/*.js | sort -u` em 2026-08-17), contra as
  116 rotas do cliente. A diferença é o roadmap.
- O token de sessão do jogo é `randomBytes(32).toString('base64url')` (`db.js`
  `createUser()`), **estático por usuário**, em texto claro em `users.token`. O
  cliente espera JWT — ver skill `boot-diagnostics`, assinatura 2.
- `RESEARCH_MODE` (env, default `true`): endpoint `/game/*` desconhecido é logado
  como `[research] endpoint ainda não implementado` e responde `ok()` vazio em vez
  de 404 (`index.js:719-722`). Útil para mapear o cliente; perigoso se esquecido
  ligado.

## Escopo e limites

- Uso pessoal / preservação. Não baixe, não redistribua e não peça o APK oficial.
- Não altere `server/src/**` quando a tarefa for só documentação — entregue o código
  proposto no documento, marcado como não aplicado.
- O usuário edita esta árvore ao vivo. **Confira `git status` e `git diff --cached`
  antes de commitar** e nunca faça `git add .` às cegas.
