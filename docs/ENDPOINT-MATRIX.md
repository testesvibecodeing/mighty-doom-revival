# Matriz de compatibilidade da API

<!-- GERADO por scripts/generate_endpoint_matrix.py a partir de compatibility.json.
     Não edite à mão: rode o script. -->

Fonte de verdade: `compatibility.json` · atualizado em 2026-08-17T11:45:30Z ·
116 rotas `game/*` extraídas do global-metadata.dat v29
do cliente com.bethsoft.ubu 1.13.1 build 84862.

DEFINITION OF DONE por endpoint (todos devem ser verdadeiros;
`persistence_validated` nulo = não aplicável):
`schema_extracted` · `implemented` · `request_observed` · `response_observed` ·
`client_validated` · `persistence_validated` · `regression_test` · `uses_fallback=false`.

| Módulo | Pri | Endpoints | ✅ DoD | 🧪 impl. | ❌ falta | 🔬 schema | Estado |
|---|---:|---:|---:|---:|---:|---:|---|
| [gear](#gear) | 1 | 5 | 0 | 5 | 0 | 5 | 🧪 em convergência |
| [slayers](#slayers) | 2 | 2 | 0 | 2 | 0 | 2 | 🧪 em convergência |
| [talents](#talents) | 3 | 1 | 0 | 1 | 0 | 1 | 🧪 em convergência |
| [chapters](#chapters) | 4 | 13 | 3 | 10 | 0 | 10 | 🧪 em convergência |
| [quests](#quests) | 5 | 3 | 0 | 3 | 0 | 3 | 🧪 em convergência |
| [reward-tracks](#reward-tracks) | 6 | 3 | 0 | 3 | 0 | 3 | 🧪 em convergência |
| [inbox](#inbox) | 7 | 4 | 0 | 4 | 0 | 4 | 🧪 em convergência |
| [player](#player) | 8 | 7 | 0 | 6 | 1 | 1 | 🧪 em convergência |
| [events](#events) | 9 | 11 | 0 | 11 | 0 | 9 | 🧪 em convergência |
| [battle-pass](#battle-pass) | 10 | 9 | 0 | 3 | 6 | 0 | 🧪 em convergência |
| [daily-rewards](#daily-rewards) | 11 | 2 | 0 | 2 | 0 | 0 | 🧪 em convergência |
| [idle-rewards](#idle-rewards) | 12 | 4 | 0 | 2 | 2 | 0 | 🧪 em convergência |
| [store](#store) | 13 | 10 | 0 | 5 | 5 | 0 | 🧪 em convergência |
| [inventory](#inventory) | 14 | 3 | 0 | 2 | 1 | 0 | 🧪 em convergência |
| [armory](#armory) | 15 | 2 | 0 | 1 | 1 | 0 | 🧪 em convergência |
| [tutorial](#tutorial) | 16 | 1 | 0 | 1 | 0 | 0 | 🧪 em convergência |
| [session](#session) | 17 | 3 | 0 | 2 | 1 | 0 | 🧪 em convergência |
| [auth](#auth) | 18 | 5 | 0 | 4 | 1 | 0 | 🧪 em convergência |
| [identity](#identity) | 19 | 8 | 0 | 3 | 5 | 0 | 🧪 em convergência |
| [devices](#devices) | 20 | 4 | 0 | 0 | 4 | 0 | ❌ nada implementado |
| [codes](#codes) | 21 | 1 | 0 | 0 | 1 | 0 | ❌ nada implementado |
| [xbox](#xbox) | 22 | 4 | 0 | 0 | 4 | 0 | ❌ nada implementado |
| [bnet](#bnet) | 23 | 1 | 0 | 0 | 1 | 0 | ❌ nada implementado |
| [ads ⛔](#ads) | 99 | 4 | 0 | 4 | 0 | 0 | ⛔ fora de escopo (dependência externa) |
| [iap ⛔](#iap) | 99 | 6 | 0 | 6 | 0 | 0 | ⛔ fora de escopo (dependência externa) |

## Detalhe por módulo

### gear

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/gear/apply-cosmetic` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: GearApi.ApplyCosmetic(gearUid, cosmeticId); cosmetic_id literal confirmado |
| `game/gear/dismantle` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: GearApi.Dismantle(gearUid); refund via dismantle.tiers no game-data |
| `game/gear/fuse` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: GearApi.Fuse(inputUids); requer gear_fusion no game-data (erro 2300 explicito sem config) |
| `game/gear/multi-upgrade` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: GearApi.MultiUpgrade(gearUid, levelsToUpgrade) |
| `game/gear/upgrade` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29 2026-08-17: GearApi.Upgrade(gearUid); levels_to_upgrade e literal confirmado, gear_uid do fallback snake (A VERIFICAR em captura cliente) |

### slayers

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/slayers/apply-cosmetic` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: SlayerApi.ApplyCosmetic(slayerUid, cosmeticId) |
| `game/slayers/upgrade` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: SlayerApi.Upgrade(slayerUid) |

### talents

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/talents/buy` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: TalentsApi.Buy() sem parametros de metodo; talent_id e literal do wire |

### chapters

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/chapters/ad-ability-reroll` | ✅ | ✅ | · | · | · | — | ✅ | · | — | schema extraído |
| `game/chapters/ad-revive` | ✅ | ✅ | · | · | · | — | ✅ | · | — | schema extraído |
| `game/chapters/claim-challenge-reward` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |
| `game/chapters/claim-rewards` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |
| `game/chapters/claim-stage-reward` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |
| `game/chapters/claim-vip-reward` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |
| `game/chapters/claim-vip-rewards-all` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |
| `game/chapters/claim-vip-rewards-chapter` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |
| `game/chapters/end` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | RELATORIO-STATUS 2026-08-16: vitória do 1-1, recompensas, 1-2 desbloqueado; current_run persistido. |
| `game/chapters/redeem-voucher` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |
| `game/chapters/revive` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |
| `game/chapters/start` | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | RELATORIO-STATUS 2026-08-16: partida completa do estágio 1-1 no emulador. |
| `game/chapters/update` | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | RELATORIO-STATUS 2026-08-16: avanço nas 5 salas do 1-1. |

### quests

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/quests/claim-daily-quest` | ✅ | ✅ | · | · | · | — | · | · | — | schema extraído |
| `game/quests/claim-milestone` | ✅ | ✅ | · | · | · | — | · | · | — | schema extraído |
| `game/quests/get-daily-quests` | ✅ | ✅ | · | · | · | — | · | ✅ | — | schema extraído |

### reward-tracks

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/reward-tracks/claim` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |
| `game/reward-tracks/get-all` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |
| `game/reward-tracks/get-track` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |

### inbox

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/inbox/claim` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |
| `game/inbox/delete` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |
| `game/inbox/get-messages` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |
| `game/inbox/read` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |

### player

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/player/game-data-token` | ✅ | · | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | RELATORIO-STATUS 2026-08-16: bootstrap completo no emulador; /data baixado com o token. |
| `game/player/increment-stats` | ✅ | · | · | · | · | — | · | ✅ | — | implementado, aguardando validação |
| `game/player/level-up` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/player/set-push-token` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/player/stats` | ✅ | ✅ | · | · | · | — | · | ✅ | — | schema extraído |
| `game/player/update-settings` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/player/user-data` | ✅ | · | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | RELATORIO-STATUS 2026-08-16: user-data no bootstrap e refletindo progressão persistida após restart do servidor. |

### events

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/events/activate-store-offer-event` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | EventsApi.ActivateStoreOfferEvent(scheduledEventId) -> ActivateStoreOfferEventResponse{offer}; offer = PlayerOfferModel{id,offerDefinitionId,itemId,allowedPurchases,purchaseAmount,startTime,endTime,altResources,targetedOfferType,offerGroup,apiVersion} extraido; estado = StoreOfferEventState{scheduledEventId}. |
| `game/events/end-game-mode-event` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | EventsApi.EndGameModeEvent(scheduledEventId,progress) -> EndGameModeEventResponse{resources,stageRewards}; stage_rewards = EventStageReward{stage,resources,lootRolls,display} extraido; resources com semantica de saldo (giveGameResource). |
| `game/events/game-mode-event-ad-ability-reroll` | ✅ | ✅ | · | · | · | — | ✅ | · | — | EventsApi.AdAbilityReroll(rewardTokenId,scheduledEventId); mesmo padrao do ad-revive com tipo ability_reroll. |
| `game/events/game-mode-event-ad-revive` | ✅ | ✅ | · | · | · | — | ✅ | · | — | EventsApi.AdRevive(rewardTokenId,scheduledEventId); valida/consome AdRewardToken do namespace ads; sem emissor (modulo ads fora de escopo) -> 2300 explicito, sem fixture. |
| `game/events/game-mode-event-redeem-voucher` | ✅ | ✅ | · | · | · | — | ✅ | · | — | EventsApi.GameModeEventRedeemVoucher(voucherId); voucher_id literal CONFIRMADO; consome item do inventario, aplica ao run ativo (sem scheduledEventId no contrato). |
| `game/events/game-mode-event-revive` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | EventsApi.Revive(scheduledEventId) sem DTO -> envelope puro; +1 revive no run do evento. |
| `game/events/get-instance` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | EventsApi.GetInstance(instanceId) -> GetInstanceResponse{eventInstance}; sem DTO EventInstance no metadata — respondido com o wire do schedule (mesmo DTO que o cliente parseia em get-schedule). A VERIFICAR ate captura do cliente. |
| `game/events/get-progress` | ✅ | · | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | RELATORIO-STATUS 2026-08-16: eventos do menu com progresso/timers vindos do servidor. |
| `game/events/get-schedule` | ✅ | · | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | RELATORIO-STATUS 2026-08-16: menu com eventos do servidor (Slayers Energy / Speedrun Challenge) no emulador. |
| `game/events/start-game-mode-event` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | EventsApi.StartGameModeEvent(scheduledEventId) -> StartGameModeEventResponse{attempt}; attempt = GameModeEventRun{scheduledEventId,seed,startTime,slots,maxLoot,battlePassPointsLoot,gameModeEventProgress,lootPools} extraido do metadata; teste events.mjs + fixture server-replay. |
| `game/events/update-game-mode-event-progress` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | EventsApi.UpdateGameModeEventProgress(scheduledEventId,progress) -> {minUpdateTime}; progress literal CONFIRMADO; espelha chapters/update (min_update_time nullable validado com cliente real). |

### battle-pass

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/battle-pass/buy-next-track-tier` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/battle-pass/claim-mission` | ✅ | · | · | · | · | — | ✅ | · | — | implementado, aguardando validação |
| `game/battle-pass/claim-track-all` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/battle-pass/claim-track-reward` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/battle-pass/claim-track-tier` | ✅ | · | · | · | · | — | ✅ | · | — | implementado, aguardando validação |
| `game/battle-pass/end-season` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/battle-pass/prestige` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/battle-pass/redeem-premium-entitlement` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/battle-pass/start-season` | ✅ | · | · | · | · | — | ✅ | · | — | implementado, aguardando validação |

### daily-rewards

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/daily-rewards/claim` | ✅ | · | · | · | · | — | ✅ | ✅ | — | implementado, aguardando validação |
| `game/daily-rewards/get-state` | ✅ | · | · | · | · | — | ✅ | ✅ | — | implementado, aguardando validação |

### idle-rewards

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/idle-rewards/ad-boost` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/idle-rewards/boost` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/idle-rewards/claim` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/idle-rewards/get-state` | ✅ | · | · | · | · | — | ✅ | ✅ | — | implementado, aguardando validação |

### store

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/store/activate-daily-offers` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/store/activate-offer` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/store/ad-purchase` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/store/get` | ✅ | · | · | · | · | — | ✅ | ✅ | — | implementado, aguardando validação |
| `game/store/get-daily-offers` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/store/get-items` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/store/get-offer-items` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/store/get-offers` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/store/get-player-offers` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/store/purchase` | ✅ | · | · | · | · | — | ✅ | · | — | implementado, aguardando validação |

### inventory

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/inventory/equip` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/inventory/exchange-currency` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/inventory/get-equip-sequence-id` | ✅ | · | · | · | · | — | · | ✅ | — | implementado, aguardando validação |

### armory

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/armory/get` | ✅ | · | ✅ | ✅ | ✅ | — | · | ✅ | — | RELATORIO-STATUS 2026-08-16: boot completo; upgrades:[] evita o NRE do ArmoryController.Init. |
| `game/armory/upgrade` | · | · | · | · | · | — | · | · | — | não implementado |

### tutorial

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/tutorial/complete-sequence` | ✅ | · | · | · | · | — | ✅ | · | — | implementado, aguardando validação |

### session

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/session/heartbeat` | ✅ | · | · | · | · | — | ✅ | ✅ | — | implementado, aguardando validação |
| `game/session/refresh` | ✅ | · | ✅ | ✅ | ✅ | — | · | ✅ | — | RELATORIO-STATUS 2026-08-16: session/refresh contínuo durante o combate (keepalive). |
| `game/session/update-legal` | · | · | · | · | · | — | · | · | — | não implementado |

### auth

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/auth/login-device` | ✅ | · | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | RELATORIO-STATUS 2026-08-16: login-device no bootstrap do emulador, resposta aceita pelo cliente. |
| `game/auth/login-game-center` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/auth/login-google-play-games` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/auth/login-xbox` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/auth/register` | ✅ | · | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | RELATORIO-STATUS 2026-08-16: registro da conta revivaltest feito pelo cliente no emulador, boot completo sem erros no logcat. |

### identity

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/identity/authorize-xbox` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/identity/describe-conflict` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/identity/link-game-center` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/identity/link-google-play-games` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/identity/link-xbox` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/identity/list` | ✅ | · | · | · | · | — | · | ✅ | — | implementado, aguardando validação |
| `game/identity/resolve-conflict` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/identity/unlink` | · | · | · | · | · | — | · | · | — | não implementado |

### devices

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/devices/describe` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/devices/list` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/devices/register` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/devices/unregister` | · | · | · | · | · | — | · | · | — | não implementado |

### codes

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/codes/redeem` | · | · | · | · | · | — | · | · | — | não implementado |

### xbox

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/xbox/claim-perk` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/xbox/get-game-pass` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/xbox/get-gamertag` | · | · | · | · | · | — | · | · | — | não implementado |
| `game/xbox/get-perks` | · | · | · | · | · | — | · | · | — | não implementado |

### bnet

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/bnet/claim-slayers-club` | · | · | · | · | · | — | · | · | — | não implementado |

### ads

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/ads/begin-watch` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/ads/cancel-watch` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/ads/get-state` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/ads/refresh-token` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |

### iap

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/iap/begin-purchase` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/iap/cancel-purchase` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/iap/confirm-purchase` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/iap/get-purchase-history-info` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/iap/recover-purchase` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/iap/validate-purchase` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |

## Rotas legadas do servidor (não existem no cliente)

Implementadas em `server/src` mas ausentes das 116 rotas do metadata —
provável erro de transcrição histórico. Candidatas a remoção;
nenhum cliente 1.13.1 as chama.

- `game/events`
- `game/idle-rewards/claim-rewards`
- `game/quests/claim`
- `game/quests/claim-daily-milestone`
- `game/reward-tracks/claim-reward`
- `game/reward-tracks/claim-tier`
- `game/reward-tracks/get-progress`
- `game/reward-tracks/get-state`
- `game/talents/get`
