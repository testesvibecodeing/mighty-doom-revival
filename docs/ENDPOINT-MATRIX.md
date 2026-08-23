# Matriz de compatibilidade da API

<!-- GERADO por scripts/generate_endpoint_matrix.py a partir de compatibility.json.
     Não edite à mão: rode o script. -->

Fonte de verdade: `compatibility.json` · atualizado em 2026-08-23T17:05:04Z ·
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
| [player](#player) | 8 | 7 | 0 | 7 | 0 | 2 | 🧪 em convergência |
| [events](#events) | 9 | 11 | 0 | 11 | 0 | 9 | 🧪 em convergência |
| [battle-pass](#battle-pass) | 10 | 9 | 0 | 9 | 0 | 9 | 🧪 em convergência |
| [daily-rewards](#daily-rewards) | 11 | 2 | 0 | 2 | 0 | 0 | 🧪 em convergência |
| [idle-rewards](#idle-rewards) | 12 | 4 | 0 | 4 | 0 | 2 | 🧪 em convergência |
| [store](#store) | 13 | 10 | 0 | 10 | 0 | 5 | 🧪 em convergência |
| [inventory](#inventory) | 14 | 3 | 0 | 3 | 0 | 1 | 🧪 em convergência |
| [armory](#armory) | 15 | 2 | 1 | 1 | 0 | 1 | 🧪 em convergência |
| [tutorial](#tutorial) | 16 | 1 | 0 | 1 | 0 | 0 | 🧪 em convergência |
| [session](#session) | 17 | 3 | 0 | 3 | 0 | 1 | 🧪 em convergência |
| [auth](#auth) | 18 | 5 | 0 | 5 | 0 | 1 | 🧪 em convergência |
| [identity](#identity) | 19 | 8 | 0 | 8 | 0 | 5 | 🧪 em convergência |
| [devices](#devices) | 20 | 4 | 0 | 4 | 0 | 4 | 🧪 em convergência |
| [codes](#codes) | 21 | 1 | 0 | 1 | 0 | 1 | 🧪 em convergência |
| [xbox](#xbox) | 22 | 4 | 0 | 4 | 0 | 4 | 🧪 em convergência |
| [bnet](#bnet) | 23 | 1 | 0 | 1 | 0 | 1 | 🧪 em convergência |
| [ads ⛔](#ads) | 99 | 4 | 0 | 4 | 0 | 1 | ⛔ fora de escopo (dependência externa) |
| [iap ⛔](#iap) | 99 | 6 | 0 | 6 | 0 | 0 | ⛔ fora de escopo (dependência externa) |

## Detalhe por módulo

### gear

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/gear/apply-cosmetic` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: GearApi.ApplyCosmetic(gearUid, cosmeticId); cosmetic_id literal confirmado | NEGATIVA 2026-08-23 rig: flows UI completos de compra por moedas e equip de uniforme + skin de arma (uniforms-fs1..6.png, weaponskins-fs1..5.png) com ZERO chamadas de rede e inventario do servidor inalterado entre cold boots - cosmetic e client-authoritative no 1.13.1. request_observed permanece false. DEAD-ENDS #21. |
| `game/gear/dismantle` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: GearApi.Dismantle(gearUid); refund via dismantle.tiers no game-data |
| `game/gear/fuse` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: GearApi.Fuse(inputUids); requer gear_fusion no game-data (erro 2300 explicito sem config) |
| `game/gear/multi-upgrade` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: GearApi.MultiUpgrade(gearUid, levelsToUpgrade) | NEGATIVA 2026-08-23 rig: mesmo painel e mesmo handler de upgrade do botao UPGRADE do BARRACKS - acao quebra o cliente antes do wire (ver game/gear/upgrade). Rota nunca emitida no UI medido. |
| `game/gear/upgrade` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29 2026-08-17: GearApi.Upgrade(gearUid); levels_to_upgrade e literal confirmado, gear_uid do fallback snake (A VERIFICAR em captura cliente) | NEGATIVA 2026-08-23 rig: tap medido no botao UPGRADE (826,1193, pixel scan) com app vivo (navegacao e selecao de carta respondem) produziu re-init COMPLETO da sessao em-processo (login-device..get-daily-quests, requests 1149-1166) SEM chamar game/gear/upgrade, seguido de wedge do main thread do Unity: 0 requests, 0 linhas Unity no logcat, render thread em spam continuo goldfish_vulkan QSRI (logcat-upgrade-tap.txt, 3920/3920 linhas). Reproduzido 2x. Causa raiz A VERIFICAR (hipotese: estado de controller nulo no handler, mesma familia do NRE de UpdateQuestState). Rota nunca emitida. |

### slayers

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/slayers/apply-cosmetic` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: SlayerApi.ApplyCosmetic(slayerUid, cosmeticId) | NEGATIVA 2026-08-23 rig: mesmo fluxo de equip de uniforme do slayer sem chamada de rede - client-authoritative (ver game/gear/apply-cosmetic). DEAD-ENDS #21. |
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
| `game/quests/claim-daily-quest` | ✅ | ✅ | · | · | · | — | · | · | — | NEGATIVA 2026-08-23 rig: botoes READY TO COLLECT do painel MISSIONS sao inertes - 3 taps medidos (coordenadas por pixel scan), 0 requests em janela harness --no-launch de 100s, 0 excecoes no logcat, painel byte-identico antes/depois (missions-claim1..3.png). NRE client-interno em UpdateQuestState presente em toda resposta de get-daily-quests. DEAD-ENDS #20. |
| `game/quests/claim-milestone` | ✅ | ✅ | · | · | · | — | · | · | — | NEGATIVA 2026-08-23 rig: milestone 1 exige 20 pontos e o jogador esta em 2/20 - botao indisponivel no estado medido; claim de quest no mesmo painel e inertes (ver claim-daily-quest). Rota nunca emitida pelo UI medido. |
| `game/quests/get-daily-quests` | ✅ | ✅ | ✅ | ✅ | · | — | ✅ | ✅ | — | metadata v29: GetDailyQuestsResponse{dayStartEpoch, dayEndEpoch, milestones, quests}; DailyQuestModel{id, questId, progress, claimed, points, goTo}; DailyQuestMilestoneModel{id, milestoneId, pointsRequired, claimed, rewards}. Wire recortado ao DTO em 2026-08-21 — o estado interno (target/completed) nao vai para a resposta. | 2026-08-23 rig (bissecao 8 degraus, server-fs2..fs10.log): nome de wire do membro de colecao e daily_quests (override JsonProperty no attributeData; fallback quests com conteudo derruba Malformed response payload, array vazia e tolerada). Com rename + arrays cheias: boot flow_validated, fatais 0, fixture provenance=client. NRE tolerado em DailyQuestController.UpdateQuestState em TODA resposta (vazio ou cheio), client-interno. Painel MISSIONS renderiza quests e barra de milestone com dados do servidor (menu-claim1.png, 2/20). |

### reward-tracks

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/reward-tracks/claim` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |
| `game/reward-tracks/get-all` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | RewardTrackEntryModel declara SOMENTE resources. Bisseção no emulador em 2026-08-21 (8 execucoes): entries com {id, resources} -> Malformed response payload e boot parado; entries com {resources} -> boot segue ate o menu. entries_claimed como array de ids confirmado. | 2026-08-23 rig: nome de wire do membro de colecao e reward_tracks (override JsonProperty no attributeData; fallback tracks com conteudo derruba Malformed response payload, array vazia e tolerada). Boot medido do 1.13.1 NAO chama get-all (sequencia 1077-1094) - rota aguarda porta de entrada na UI (painel de temporada). |
| `game/reward-tracks/get-track` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |

### inbox

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/inbox/claim` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |
| `game/inbox/delete` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |
| `game/inbox/get-messages` | ✅ | ✅ | ✅ | ✅ | · | — | ✅ | ✅ | — | schema extraído |
| `game/inbox/read` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | schema extraído |

### player

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/player/game-data-token` | ✅ | · | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | RELATORIO-STATUS 2026-08-16: bootstrap completo no emulador; /data baixado com o token. |
| `game/player/increment-stats` | ✅ | · | · | · | · | — | · | ✅ | — | implementado, aguardando validação |
| `game/player/level-up` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/player/set-push-token` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: PlayerApi.SetPushToken CONFIRMADO; envelope puro; push_token obrigatório (2200); nome de campo A VERIFICAR |
| `game/player/stats` | ✅ | ✅ | · | · | · | — | · | ✅ | — | schema extraído |
| `game/player/update-settings` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/player/user-data` | ✅ | · | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | RELATORIO-STATUS 2026-08-16: user-data no bootstrap e refletindo progressão persistida após restart do servidor. | client_harness 2026-08-20T21:06:49Z fluxo menu contra http://127.0.0.1:8110 | client_harness 2026-08-23T16:42:12Z fluxo boot contra http://127.0.0.1:8140 |

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
| `game/events/get-progress` | ✅ | · | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | RELATORIO-STATUS 2026-08-16: eventos do menu com progresso/timers vindos do servidor. | 2026-08-19: preview de archive dos story passes parseia no boot; o FTUE só chama end-season depois dele (sem start-season). |
| `game/events/get-schedule` | ✅ | · | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | RELATORIO-STATUS 2026-08-16: menu com eventos do servidor (Slayers Energy / Speedrun Challenge) no emulador. | 2026-08-19: story battle passes FORA do schedule — o EventModeController trata todo evento agendado como game-mode e NRE em InternalUpdateEventData com o FTUE_BattlePass na lista (CARREGANDO eterno); sem eles o boot flui. A VERIFICAR: com game-data completo, o conversor por args talvez tolere a entrada. | client_harness 2026-08-20T21:06:49Z fluxo menu contra http://127.0.0.1:8110 |
| `game/events/start-game-mode-event` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | EventsApi.StartGameModeEvent(scheduledEventId) -> StartGameModeEventResponse{attempt}; attempt = GameModeEventRun{scheduledEventId,seed,startTime,slots,maxLoot,battlePassPointsLoot,gameModeEventProgress,lootPools} extraido do metadata; teste events.mjs + fixture server-replay. |
| `game/events/update-game-mode-event-progress` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | EventsApi.UpdateGameModeEventProgress(scheduledEventId,progress) -> {minUpdateTime}; progress literal CONFIRMADO; espelha chapters/update (min_update_time nullable validado com cliente real). |

### battle-pass

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/battle-pass/buy-next-track-tier` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | BattlePassApi.BuyNextTrackTier(seasonId) -> Response sem campos (envelope puro); debita ceil(pontos_faltantes/out_points)*in_amount da in_currency via points_exchange_rate (BattlePassPointsExchangeRate extraido); 2300 no-next-tier/insufficient-currency. |
| `game/battle-pass/claim-mission` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | ClaimMissionResponse{resources}; missao completavel via player/increment-stats (applyBattlePassStatTotals) com stat_id/target no config. |
| `game/battle-pass/claim-track-all` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | BattlePassApi.ClaimTrackAll(seasonId) -> ClaimTrackAllResponse{resources}; varre tiers com pontos suficientes, 2300 nothing-to-claim quando vazio. |
| `game/battle-pass/claim-track-reward` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | BattlePassApi.ClaimTrackReward(seasonId,tierId,rewardId) -> {resources}; gates 2200 tier/reward-not-found, 2300 insufficient-points/reward-already-claimed/premium-required. |
| `game/battle-pass/claim-track-tier` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | ClaimTrackTierResponse{resources}; premium gate agora exige PremiumState=2 conforme enum extraido. |
| `game/battle-pass/end-season` | ✅ | ✅ | ✅ | ✅ | · | — | ✅ | ✅ | — | BattlePassApi.EndSeason(seasonId) -> EndSeasonResponse{resources}; concede os rewards ja conquistados e marca ActiveState=Ended(2); gates 2300 season-ended/season-not-started. | 2026-08-19: activeSeasonState materializa estado default quando não há start-season — o FTUE chama end-season direto após o preview de archive do get-progress (400 season-not-started em loop + diálogo de ERRO antes do fix). |
| `game/battle-pass/prestige` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | BattlePassApi.Prestige(seasonId) -> PrestigeResponse{resources}; exige ultimo tier, concede prestige_reward_pool, reseta pontos para prestige_point_start+(prestige-1)*increment e limpa reward_claims (A VERIFICAR); enums e DTOs extraidos do metadata. |
| `game/battle-pass/redeem-premium-entitlement` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | BattlePassApi.RedeemPremiumEntitlement(seasonId) -> Response sem campos (envelope puro); PremiumState None=0 -> Premium=2 mediante posse do premium_entitlement_id do args; teste battle-pass.mjs + fixture. |
| `game/battle-pass/start-season` | ✅ | ✅ | ✅ | ✅ | · | — | ✅ | ✅ | — | StartSeasonResponse{state} de BattlePassEventState{seasonId,activeState,premiumState,points,prestige,rewardClaims,missionProgress} extraido; premium_state corrigido para o enum (None/Free/Premium). |

### daily-rewards

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/daily-rewards/claim` | ✅ | · | · | · | · | — | ✅ | ✅ | — | implementado, aguardando validação |
| `game/daily-rewards/get-state` | ✅ | · | ✅ | ✅ | · | — | ✅ | ✅ | — | implementado, aguardando validação |

### idle-rewards

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/idle-rewards/ad-boost` | ✅ | ✅ | · | · | · | — | · | · | — | metadata v29: IdleRewardApi.AdBoost(rewardTokenId) CONFIRMADO; consome AdRewardToken IdleRewardBoost ignorando cooldown; sem emissor game/ads/* o 2300 é honesto; reward_token_id A VERIFICAR |
| `game/idle-rewards/boost` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: IdleRewardApi.Boost() CONFIRMADO; sem Response DTO -> envelope puro; concede períodos pendentes × gameData.idle_reward.boost.multiplier, cooldown do boost grátis |
| `game/idle-rewards/claim` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/idle-rewards/get-state` | ✅ | · | ✅ | ✅ | · | — | ✅ | ✅ | — | implementado, aguardando validação |

### store

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/store/activate-daily-offers` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/store/activate-offer` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: StoreApi.ActivateOffer(offerId, gearResourceId) CONFIRMADO; ActivateOfferResponse{offer}; fixture server-replay 2026-08-17; offer_id/gear_resource_id A VERIFICAR |
| `game/store/ad-purchase` | ✅ | ✅ | · | · | · | — | ✅ | · | — | metadata v29: StoreApi.AdPurchaseItem(itemId, rewardTokenId) CONFIRMADO; AdPurchaseResponse{resources}; token StoreItemCrate/StoreItemGold via ad-tokens.js; sem emissor ads -> 2300 honesto; item_id/reward_token_id A VERIFICAR |
| `game/store/get` | ✅ | · | ✅ | ✅ | · | — | ✅ | ✅ | — | implementado, aguardando validação |
| `game/store/get-daily-offers` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/store/get-items` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: StoreApi.GetItems() CONFIRMADO; GetItemsResponse{storeItems, iapItems, adItems}; iap_items vazio por design (IAP desligado); packs ad separados em ad_items |
| `game/store/get-offer-items` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: StoreApi.GetOfferItems() CONFIRMADO; mesmo DTO de GetItems; fixture server-replay 2026-08-17 |
| `game/store/get-offers` | ✅ | · | ✅ | ✅ | · | — | · | ✅ | — | implementado, aguardando validação |
| `game/store/get-player-offers` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: StoreApi.GetPlayerOffers() CONFIRMADO; GetPlayerOffersResponse{offers} com PlayerOfferModel das offers ativadas |
| `game/store/purchase` | ✅ | · | · | · | · | — | ✅ | · | — | NEGATIVA 2026-08-23 rig: compra de cosmetic por moedas/cristais concluida no UI sem chamada de rede e currencies do servidor inalteradas ([{rid:3,amount:60}]) - client-authoritative no 1.13.1. DEAD-ENDS #21. |

### inventory

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/inventory/equip` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/inventory/exchange-currency` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: InventoryApi.ExchangeCurrency(inputCurrencyId, outputCurrencyId, outputCurrencyAmount) CONFIRMADO; sem Response DTO -> envelope puro; taxa em gameData.currency_exchange rate; saída via giveGameResource; nomes de wire A VERIFICAR |
| `game/inventory/get-equip-sequence-id` | ✅ | · | · | · | · | — | · | ✅ | — | implementado, aguardando validação |

### armory

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/armory/get` | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | metadata v29: ArmoryApi.Get() CONFIRMADO; wire {upgrades:[{id,level}]} (fallback snake); array sempre presente — boot 1.13.1 itera em ArmoryController.Init |
| `game/armory/upgrade` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: ArmoryApi.Upgrade(id, level) CONFIRMADO; sem Response DTO -> envelope puro; semântica do level (alvo 1-based sequencial) A VERIFICAR até captura |

### tutorial

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/tutorial/complete-sequence` | ✅ | · | ✅ | ✅ | · | — | ✅ | ✅ | — | implementado, aguardando validação |

### session

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/session/heartbeat` | ✅ | · | ✅ | ✅ | · | — | ✅ | ✅ | — | implementado, aguardando validação |
| `game/session/refresh` | ✅ | · | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | RELATORIO-STATUS 2026-08-16: session/refresh contínuo durante o combate (keepalive). |
| `game/session/update-legal` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: SessionApi.UpdateLegal CONFIRMADO; envelope puro; persiste versões tos/pp/eula + flags em session/legal; nomes de campos A VERIFICAR |

### auth

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/auth/login-device` | ✅ | · | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | RELATORIO-STATUS 2026-08-16: login-device no bootstrap do emulador, resposta aceita pelo cliente. | client_harness 2026-08-20T21:06:49Z fluxo menu contra http://127.0.0.1:8110 | client_harness 2026-08-23T16:42:12Z fluxo boot contra http://127.0.0.1:8140 |
| `game/auth/login-game-center` | ✅ | · | · | · | · | — | ✅ | · | — | implementado, aguardando validação |
| `game/auth/login-google-play-games` | ✅ | · | · | · | · | — | ✅ | · | — | implementado, aguardando validação |
| `game/auth/login-xbox` | ✅ | ✅ | · | · | · | — | ✅ | · | — | metadata v29: AuthApi login de plataforma; ResponseCode EXTRAÍDO dos fieldDefaultValues (âncoras Success=1000/2200/2300/3000): XboxUnavailable=3127 — indisponibilidade real, Revival não fala com Xbox Live |
| `game/auth/register` | ✅ | · | ✅ | ✅ | ✅ | — | ✅ | ✅ | — | RELATORIO-STATUS 2026-08-16: registro da conta revivaltest feito pelo cliente no emulador, boot completo sem erros no logcat. | 2026-08-19: JWT aud/audience como ARRAY — o cliente tipa audience como String[] e string crua derruba o UpdateSessionToken com 'Could not cast or convert from System.String to System.String[]' em register/login/refresh (vale para todo token de sessão). |

### identity

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/identity/authorize-xbox` | ✅ | ✅ | · | · | · | — | ✅ | · | — | metadata v29: IdentityApi.AuthorizeXbox(xboxAuth) CONFIRMADO; XboxUnavailable=3127 real |
| `game/identity/describe-conflict` | ✅ | ✅ | · | · | · | — | ✅ | · | — | metadata v29: IdentityApi.DescribeConflict(linkToken) CONFIRMADO; gates verdadeiros: 2200 link-token-required / 2340 link-not-found (sem vínculo de plataforma nenhum token existe); link_token A VERIFICAR |
| `game/identity/link-game-center` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/identity/link-google-play-games` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/identity/link-xbox` | ✅ | ✅ | · | · | · | — | ✅ | · | — | metadata v29: IdentityApi.LinkXbox(xboxAuth) CONFIRMADO; XboxUnavailable=3127 real |
| `game/identity/list` | ✅ | · | · | · | · | — | · | ✅ | — | implementado, aguardando validação |
| `game/identity/resolve-conflict` | ✅ | ✅ | · | · | · | — | ✅ | · | — | metadata v29: IdentityApi.ResolveConflict(linkToken, userChoice) CONFIRMADO; mesmos gates de describe-conflict; user_choice A VERIFICAR |
| `game/identity/unlink` | ✅ | ✅ | · | · | · | — | ✅ | · | — | metadata v29: IdentityApi.Unlink(identityId) CONFIRMADO; 2200 identity-id-required / 2340 identity-not-found (gate verdadeiro); identity_id A VERIFICAR |

### devices

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/devices/describe` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: DevicesApi.Describe(deviceId) CONFIRMADO; device_id A VERIFICAR (fallback snake); wrapper device; refresca last_access_time |
| `game/devices/list` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: DevicesApi.List() CONFIRMADO; wrapper devices (literal) com AuthorizedDevice[]; fixture server-replay 2026-08-17 |
| `game/devices/register` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: DevicesApi.Register(platform, region) CONFIRMADO; DeviceInfo{region, platform}; literais de wire device/platform/region; AuthorizedDevice{id, platform, region, authorizationTime, lastAccessTime} no wrapper device; fixture server-replay 2026-08-17 |
| `game/devices/unregister` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: DevicesApi.Unregister(deviceId) CONFIRMADO; sem Response DTO -> envelope puro; device_id A VERIFICAR |

### codes

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/codes/redeem` | ✅ | ✅ | · | · | · | — | ✅ | ✅ | — | metadata v29: CodesApi.Redeem(code) CONFIRMADO; literal code; sem *Response DTO confirmado -> wrapper resources A VERIFICAR (padrão PurchaseItemResponse); códigos em gameData.codes, 1x por jogador |

### xbox

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/xbox/claim-perk` | ✅ | ✅ | · | · | · | — | ✅ | · | — | metadata v29: XboxApi; XboxUnavailable=3127 real (extraído) |
| `game/xbox/get-game-pass` | ✅ | ✅ | · | · | · | — | ✅ | · | — | metadata v29: XboxApi; XboxUnavailable=3127 real (extraído) |
| `game/xbox/get-gamertag` | ✅ | ✅ | · | · | · | — | ✅ | · | — | metadata v29: XboxApi; XboxUnavailable=3127 real (extraído); sem payload falso |
| `game/xbox/get-perks` | ✅ | ✅ | · | · | · | — | ✅ | · | — | metadata v29: XboxApi; XboxUnavailable=3127 real (extraído) |

### bnet

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/bnet/claim-slayers-club` | ✅ | ✅ | · | · | · | — | ✅ | · | — | metadata v29: BnetApi.ClaimSlayersClub(bnetSession) CONFIRMADO; BnetUnavailable=3101 real (extraído) |

### ads

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/ads/begin-watch` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/ads/cancel-watch` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/ads/get-state` | ✅ | ✅ | ✅ | ✅ | · | — | ✅ | ✅ | — | metadata v29: AdApi.GetStateResponse{state}; AdState{allotment, rewardTokens}; AdAllotment{startEpoch, endEpoch, availableRewards}. Medido no emulador 2026-08-21: sem state o cliente estoura NullReferenceException em Ubu.Ads.AdController.ProcessAdState e o boot trava no LOADING 100%. |
| `game/ads/refresh-token` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |

### iap

| Rota | Impl | Schema | Req obs | Res obs | Cliente | Persist | Teste | Fixt | Fallback | Nota |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `game/iap/begin-purchase` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/iap/cancel-purchase` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/iap/confirm-purchase` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/iap/get-purchase-history-info` | ✅ | · | ✅ | ✅ | · | — | ✅ | ✅ | — | implementado, aguardando validação |
| `game/iap/recover-purchase` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |
| `game/iap/validate-purchase` | ✅ | · | · | · | · | — | · | · | — | implementado, aguardando validação |

## Rotas legadas do servidor (não existem no cliente)

Implementadas em `server/src` mas ausentes das 116 rotas do metadata —
provável erro de transcrição histórico. Candidatas a remoção;
nenhum cliente 1.13.1 as chama.

- nenhuma
