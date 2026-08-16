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
| Custom events | ✅ | schedule/progress testados |
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

O patcher foi testado contra bundle Unity sintético:

- `slayersclub.bethesda.net` possui 24 bytes;
- `d.debruinsistemas.com.br` possui 24 bytes;
- substituição 24→24 não altera tamanho do bundle;
- Manifest/TLS são atualizados;
- hostname incompatível é recusado antes de alterar o bundle;
- verificação final rejeita APK que ainda contenha hosts oficiais.

Testes: `scripts/test_patch_apk.py`, `scripts/test_patch_unity_bundle.py` e `scripts/test_verify_patched_apk.py`.

### Ainda NÃO validado

- o APK real 1.13.1 não foi executado neste ambiente;
- ainda não foi confirmado no binário real que o host oficial aparece exatamente no bundle esperado;
- reconstrução/assinatura do APK real ainda não foi instalada em Android;
- handshake HTTPS do APK real contra Revival ainda não foi confirmado;
- gameplay real no cliente ainda não foi confirmado.

Não marcar o projeto como jogável/100% antes desses testes.

## Infra/CI

O GitHub Actions está configurado, porém os runners da conta continuam sem iniciar por bloqueio de Billing/Spending Limit. Não usar falha de Actions como falha do código enquanto esse bloqueio existir.

Os testes locais são a fonte atual de validação.

## Próxima ordem de trabalho

1. validar o formato real de stats/missões no GameData comunitário completo e adaptar os leitores sem hardcode;
2. implementar Daily Quests completos e Reward Tracks reutilizando a camada persistente de stats;
3. completar chapter rewards/loot e progressão de jogador;
4. ligar todas as missões preservadas ao fluxo de stats observado no cliente;
5. implementar inbox/grants necessários pelos eventos preservados;
6. executar `scripts/analyze-official-apk.bat` em ambiente com acesso ao APK;
7. executar `scripts/patch-apk.bat` no APK real;
8. apontar `d.debruinsistemas.com.br` para um Revival HTTPS válido;
9. instalar APK assinado em Android e capturar `/revival/requests`;
10. eliminar endpoints ainda vistos apenas em `RESEARCH_MODE`;
11. repetir fluxos até o cliente não depender de fallback de pesquisa;
12. só então declarar o caminho server + patcher + client como jogável.
