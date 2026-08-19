# Estado de implementação — Mighty DOOM Revival

Este arquivo é o ponto de retomada técnico do projeto. Atualize-o quando um fluxo passar de implementação teórica para teste real.

## Regra de status

- ✅ **VALIDADO**: executado em processo real com persistência/teste de regressão;
- 🧪 **IMPLEMENTADO**: código existe, mas ainda precisa do cliente 1.13.1 real;
- 🔬 **EM PESQUISA**: schema/comportamento ainda incompleto;
- ⛔ **REMOVIDO**: serviço externo propositalmente não usado no Revival.

## Servidor

| Área | Estado | Observação |
|---|---:|---|
| Node HTTP standalone | ✅ | `node:http`, sem Koa/npm runtime |
| SQLite | ✅ | `node:sqlite`, persistência real |
| Auth register/login-device | ✅ | testado via HTTP |
| Starter bundle | ✅/🧪 | lógica testada; filtro por `slot.type` alinhado ao backend preservado, aguardando GameData/APK final |
| Inventory/currencies/energy/slots | ✅ | testado via HTTP + SQLite |
| GameData token + `/data` | ✅ | testado com dataset sintético |
| Tutorial dependencies/rewards | ✅ | SQLite isolado + HTTP integrado |
| Chapters start/update/revive/end | ✅/🧪 | persistência testada; payload alinhado ao backend preservado; loot/rewards finais ainda incompletos |
| Player stats | 🧪 | incrementos agora são normalizados, acumulados em SQLite e devolvidos no `user-data`; validar IDs/formato do APK real |
| Store Revival | ✅ | compra transacional, quotas e moeda interna |
| IAP dinheiro real | ⛔ | explicitamente bloqueado |
| Ads externos | ⛔ | desativados |
| Custom events | ✅ | schedule/progress testados e validados no cliente real (get-schedule/get-progress no boot da sessão) |
| Battle Pass arquivado | ✅/🧪 | start/mission/tier/premium reward testados; missões declarativas por stat agora recebem progresso automático |
| Daily rewards | ✅/🧪 | estado, claim e persistência cobertos por regressão; validar payload/recompensas no APK real |
| Idle rewards | ✅/🧪 | geração, claim e persistência cobertos por regressão; boost e validação no APK real pendentes |
| Daily quests | 🧪 | endpoint explícito; geração/progresso/claim ainda pendentes |
| Gear upgrades | 🧪 | upgrade e multi-upgrade transacionais por custos do GameData; validar schema real do dataset/APK |
| Slayer upgrades | 🧪 | upgrade transacional com moedas/recursos internos e level cap; validar schema real do dataset/APK |
| Talents | 🧪 | get/buy, pré-requisitos, custos e persistência implementados; validar payload real do cliente |
| Reward tracks | 🔬 | baseline existe; progress/claim pendentes |
| Inbox | 🧪 | lista segura vazia; mensagens/grants pendentes |
| Identity externa | ⛔ | Google/Game Center/Xbox não necessários ao servidor pessoal |

## GameData preservado

Formato confirmado pelo backend comunitário preservado:

- `resources`
- `weapons`, `equipment`, `launchers`, `ultimates`, `energies`, `slayers`, `cosmetics`
- `bundles`
- `inventory.slots`
- `chapter_mode.chapters`
- `talents.talents`
- `tutorial.sequences`
- `store.catalogs`
- `story_battle_passes`

`server/src/game-data-schema.js` normaliza esse layout e também aceita alguns nomes usados por snapshots alternativos.

## Progressão Gear / Slayer / Talents

`server/src/progression.js` acrescenta uma camada conservadora para os endpoints conhecidos de progressão:

- `/game/gear/upgrade`;
- `/game/gear/multi-upgrade`;
- `/game/slayers/upgrade`;
- `/game/talents/get`;
- `/game/talents/buy`.

O servidor nunca inventa um upgrade gratuito quando o GameData não fornece custo: retorna `upgrade-cost-missing`/`talent-cost-missing`. Custos são debitados de forma transacional usando apenas recursos/moedas internas já existentes no perfil. Falha de saldo, cap de nível ou pré-requisito causa rollback integral.

A regressão sintética em `server/test/progression.mjs` cobre upgrade simples, multi-upgrade, cap, Slayer com dois recursos de custo, pré-requisito de talento, compra e proteção contra compra duplicada. Ainda é obrigatório confirmar os nomes/campos exatos do GameData final e os payloads emitidos pelo APK 1.13.1.

## Player stats e missões

`server/src/stats.js` agora normaliza os formatos conservadores de incremento conhecidos (`stats` em lista, mapa ou `increments`), rejeita zero/negativos e persiste totais acumulados em `user_state`.

O endpoint `/game/player/increment-stats` deixou de ser apenas um ACK: ele grava os incrementos e tenta atualizar missões de Battle Pass quando a definição da missão expõe de forma explícita um `stat_id`/`stat.id` e um alvo (`target`, `amount`, `required` ou `count`). Não há heurística para conceder progresso quando a definição não diz qual stat deve ser usado.

Os totais persistidos também aparecem em `player.stats` dentro de `/game/player/user-data`, permitindo reinício do servidor sem perder contadores.

Regressão: `server/test/stats.mjs` cobre normalização, soma cumulativa, persistência após reabrir SQLite, duas formas de identificador de stat, conclusão automática de missão e claim de pontos de Battle Pass.

## Battle Pass / modo arquivo

Config padrão:

```json
{
  "archive_mode": true,
  "unlock_premium_battle_pass": true
}
```

Com `archive_mode`, temporadas presentes em `story_battle_passes` podem ser expostas pelo `/game/events/get-schedule` mesmo que as datas históricas já tenham expirado. O cliente recebe os `args` em Base64/JSON como no protocolo preservado.

A trilha premium pode ser tratada como conteúdo preservado desbloqueado sem Google Play Billing/IAP real.

### Teste já executado

Uma temporada histórica sintética com `start_time/end_time` expirados foi executada contra SQLite real:

1. apareceu no schedule com datas neutralizadas;
2. `start-season` criou estado persistente;
3. start duplicado foi bloqueado;
4. missão não concluída não pôde ser resgatada;
5. missão concluída concedeu pontos;
6. tier premium foi resgatado;
7. recompensa em moeda interna foi persistida;
8. claim repetido não duplicou recompensa;
9. estado apareceu em `events/get-progress`.

A camada nova de stats remove a dependência de `setBattlePassMissionProgress()` para missões que declaram stat + alvo: incrementos reais do jogador podem completar a missão automaticamente.

## APK / patcher

Cliente alvo:

- package `com.bethsoft.ubu`
- versão `1.13.1` / build `84862`
- SHA-256 alvo `519bfbb18c5bbab78f450b549777774e7d0ed78cd8b42cc25c7a2d3167669f35`

### Validado

O APK real 1.13.1 (`input/mighty-doom.apk`, SHA-256 alvo confirmado) foi baixado e analisado neste ambiente:

- `slayersclub.bethesda.net` (24 bytes) aparece **duas vezes** dentro de `assets/bin/Data/Managed/Metadata/global-metadata.dat`, **não** em `assets/aa/` — a suposição anterior (bundle Addressable) estava errada para este build. As duas ocorrências são a URL completa `https://slayersclub.bethesda.net/` (33 bytes). `scripts/analyze_apk.py` e `scripts/patch_apk.py` agora escaneiam `global-metadata.dat` também.
- Localizados por análise binária do header IL2CPP (`Il2CppGlobalMetadataHeader`, sanity check `0xFAB11BAF`, versão `29`): uma ocorrência na tabela `stringLiteralData` (offset 538684), outra no blob `fieldAndParameterDefaultValueData` (offset 6380401) — duas codificações diferentes dentro do mesmo arquivo.
- `d.debruinsistemas.com.br` (24 bytes) foi testado de ponta a ponta contra o `global-metadata.dat` real: as duas ocorrências são trocadas, tamanho do arquivo idêntico ao original, zero bytes do host oficial restantes.
- Hostnames **menores** que 24 bytes agora também são aceitos: `same_length_patch` troca a URL inteira `https://<host>/` por outra de mesmo comprimento com padding de userinfo (`https://u000@doom.sualoja.app.br/`). Validado contra o `global-metadata.dat` real com `doom.sualoja.app.br` (19 bytes): 2 ocorrências trocadas, tamanho idêntico (11.889.520 bytes), zero bytes oficiais. Userinfo é ignorado por DNS/SNI/Host.
- `doom.debruinsistemas.com.br` (27 bytes) foi testado contra o mesmo arquivo e **bloqueado corretamente** (`BLOQUEADO COM SEGURANÇA`, exit 4) — hostname maior que o oficial exige o rebuild variável-comprimento do metadata, que ainda não existe.
- Novo gate `scripts/check_patch_length.py` roda antes do apktool (só lê o ZIP) e avisa incompatibilidade de comprimento antes do usuário esperar o decode; plugado na orquestração do patch (hoje o serviço `revival_editor/pipeline.py`).
- Manifest/TLS são atualizados; hostname incompatível é recusado antes de alterar o bundle/metadata; verificação final rejeita APK que ainda contenha hosts oficiais.
- Login local (`/game/auth/register` + `/game/auth/login-device`) testado via smoke test real; login social (`/game/auth/login-google-play-games`, `/game/auth/login-game-center`, `/game/identity/link-*`) já é rejeitado pelo servidor (400/2000) — decisão do projeto: bloqueio no servidor é suficiente, sem remover o botão da UI do cliente por ora.
- **Pipeline completo executado no APK real 1.13.1**: `apktool d`/`b`, patch direto + fallback bundle-aware com `--sweep-all-bundles` (o endpoint da API vive em um bundle Addressables LZ4 como campo de objeto Unity serializado — `ProdGameServer.baseUrl` — não como ASCII no `global-metadata.dat`), patch raw-string com prova estrutural, assinatura com `uber-apk-signer` (`output/mighty-doom-revival.apk`).
- **CRC do catálogo Addressables**: qualquer bundle resserializado precisa do `m_Crc` zerado no `assets/aa/catalog.json` (JSON UTF-16LE dentro do base64 de `m_ExtraDataString`; a Unity só valida CRC não-zero). Sem isso o app abre o menu e derruba o load de cena com `CRC Mismatch` / `RemoteProviderException` "Invalid path". Implementado em `zero_catalog_crc` com substituição de mesmo comprimento; regressão em `tests/test_zero_catalog_crc.py`.
- **Instalado e jogado em emulador Android real** (conta criada via register dentro do app, login-device, bootstrap de sessão completo — login-device → game-data-token → user-data → armory/get → get-schedule → get-progress → session/refresh — menu com eventos do servidor, e gameplay completa do estágio 1-1: combate, vitória, recompensas e desbloqueio do 1-2).
- Handshake HTTPS do APK real contra o Revival confirmado (Let's Encrypt na VPS; requisições do emulador visíveis no access.log).

### Contrato do cliente 1.13.1 confirmado no emulador

- `uts`: a chave do timestamp do servidor é `uts` **sozinha**, formato `yyyy-MM-ddTHH:mm:ss` UTC (bisseção: unix epoch, `yyyy-MM-dd HH:mm:ss` e chaves extras falham no `ParseServerTimestamp` do `StartSession`).
- `armory/get`: `ArmoryController.Init(upgrades)` faz `foreach` — sem o array no wire a desserialização deixa null e NRE-derruba o boot; resposta envia `upgrades: []`.
- `events/get-schedule`: o DTO do cliente (cluster do `global-metadata`) é `id, event_definition_id, start_time, end_time, availability, min_api_version, max_api_version, stop_time, args` — **sem** `event_type`; campos numéricos não-nullable enviados como `null` explícito derrubam o parse com "Malformed response payload" (boot aborta após 3 tentativas). Valores ausentes são omitidos; regressão no smoke test.

### Ainda NÃO validado

- reserialização de tamanho variável do `global-metadata.dat` ainda não existe — bloqueia hostnames **maiores** que 24 bytes no patch direto (inclui `doom.debruinsistemas.com.br`, 27 bytes); o caminho bundle-aware cobre o endpoint de API deste build independentemente disso;
- progressão além do 1-2 (capítulos avançados, gear/slayers/talents com o dataset real, daily quests, reward tracks, inbox) ainda depende dos payloads reais do cliente — a base está jogável, o miolo de progressão segue na ordem de trabalho abaixo.

## Infra/CI

O GitHub Actions está configurado, porém os runners da conta continuam sem iniciar por bloqueio de Billing/Spending Limit. Não usar falha de Actions como falha do código enquanto esse bloqueio existir.

Os testes locais são a fonte atual de validação.

## Próxima ordem de trabalho

1. validar o formato real de stats/missões no GameData comunitário completo e adaptar os leitores sem hardcode;
2. implementar Daily Quests completos e Reward Tracks reutilizando a camada persistente de stats;
3. completar chapter rewards/loot e progressão de jogador;
4. ligar todas as missões preservadas ao fluxo de stats observado no cliente;
5. implementar inbox/grants necessários pelos eventos preservados;
6. eliminar endpoints ainda vistos apenas em `RESEARCH_MODE`;
7. repetir fluxos no emulador até o cliente não depender de fallback de pesquisa;
8. estender a validação de gameplay além do início do capítulo 1 (gear, slayers, talents, battle pass com o dataset real).

Concluído nesta fase: patcher end-to-end no APK real (bundle-aware + CRC do
catálogo), APK assinado instalado em emulador, conta criada e logada pelo
próprio cliente, bootstrap de sessão completo e gameplay real validada
(1-1 até a vitória com desbloqueio do 1-2) contra o Revival em VPS com HTTPS.
