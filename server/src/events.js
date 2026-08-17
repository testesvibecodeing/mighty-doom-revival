import { activeBattlePassStates } from './battle-pass.js'
import { archiveMode, storyBattlePasses } from './game-data-schema.js'
import { giveGameResource } from './game-data-model.js'

// ---- Contrato extraído do global-metadata.dat v29 (2026-08-17) ----
// EventsApi (11 métodos = 11 rotas game/events/* do cliente):
//   GetSchedule()                                            {}
//   GetProgress()                                            {}
//   GetInstance(instanceId)                                  {instance_id}
//   StartGameModeEvent(scheduledEventId)                     {scheduled_event_id}
//   UpdateGameModeEventProgress(scheduledEventId, progress)  {scheduled_event_id, progress}
//   EndGameModeEvent(scheduledEventId, progress)             {scheduled_event_id, progress}
//   GameModeEventRevive(scheduledEventId)                    {scheduled_event_id}
//   GameModeEventAdRevive(rewardTokenId, scheduledEventId)   {reward_token_id, scheduled_event_id}
//   GameModeEventAdAbilityReroll(rewardTokenId, scheduledEventId) {reward_token_id, scheduled_event_id}
//   GameModeEventRedeemVoucher(voucherId)                    {voucher_id}
//   ActivateStoreOfferEvent(scheduledEventId)                {scheduled_event_id}
// Response DTOs (campos confirmados; snake_case do nome C#):
//   GetInstanceResponse{eventInstance}
//   StartGameModeEventResponse{attempt}
//   EndGameModeEventResponse{resources, stageRewards}
//   UpdateGameModeEventProgressResponse{minUpdateTime}
//   ActivateStoreOfferEventResponse{offer}
//   Revive/AdRevive/AdAbilityReroll/RedeemVoucher: sem DTO -> envelope puro.
// DataObjects de estado (campos confirmados, snake fallback):
//   GameModeEventState{attempts, scheduledEventId, run, highestStage,
//                      bestCompletionTimeMilliseconds}
//   GameModeEventRun{scheduledEventId, seed, startTime, slots, maxLoot,
//                    battlePassPointsLoot, gameModeEventProgress, lootPools}
//   StoreOfferEventState{scheduledEventId}          (estado inteiro do offer)
//   StoreOfferEventDefinition{id, tag, itemId, allowedPurchases}
//   PlayerOfferModel{id, offerDefinitionId, itemId, allowedPurchases,
//                    purchaseAmount, startTime, endTime, altResources,
//                    targetedOfferType, offerGroup, apiVersion}
//   EventStageReward{stage, resources, lootRolls, display}
// CONFIRMADO por literal: progress, voucher_id, stage_rewards. A VERIFICAR
// até captura do cliente: scheduled_event_id/instance_id/reward_token_id
// (fallback snake), o shape de `attempt` (aqui: GameModeEventRun), o de
// `eventInstance` (aqui: o mesmo wire do schedule, que o cliente já parseia
// em get-schedule) e os tipos de purchaseAmount/startTime.

const NS = 'events'
const GME_KEY = 'game_mode'

function asEpoch (value) {
  if (value === null || value === undefined) return null
  if (typeof value === 'number') return value
  const n = Date.parse(value)
  if (Number.isNaN(n)) throw new Error(`Data de evento inválida: ${value}`)
  return Math.floor(n / 1000)
}

function asInt (value, fallback = null) {
  return Number.isInteger(value) ? value : fallback
}

function asArray (value) {
  return Array.isArray(value) ? value : []
}

function nowSeconds () {
  return Math.floor(Date.now() / 1000)
}

function active (event, now) {
  if (event.active === false) return false
  if (event.always === true) return true
  const start = asEpoch(event.start_time)
  const end = asEpoch(event.end_time)
  if (start !== null && now < start) return false
  if (end !== null && now > end) return false
  return true
}

function channelOf (event) {
  return event.channel || 'game_mode'
}

function wireEvent (event, archive = false) {
  // O cliente 1.13.1 desserializa cada evento do schedule com parse estrito.
  // O cluster do DTO no global-metadata é exatamente: id, event_definition_id,
  // start_time, end_time, availability, min_api_version, max_api_version,
  // stop_time, args — sem "event_type". Campos numéricos não-nullable que
  // chegam como null explícito derrubam o parse ("Malformed response payload"),
  // então campos sem valor são omitidos, nunca enviados como null.
  const wire = {
    id: event.id,
    event_definition_id: event.event_definition_id ?? event.id,
    start_time: archive ? null : asEpoch(event.start_time),
    end_time: archive ? null : asEpoch(event.end_time),
    availability: event.availability ?? 1,
    args: Buffer.from(JSON.stringify(event.args || {}), 'utf8').toString('base64')
  }
  if (event.min_api_version != null) wire.min_api_version = event.min_api_version
  if (event.max_api_version != null) wire.max_api_version = event.max_api_version
  return wire
}

export function eventSchedule (runtime) {
  const now = Math.floor(Date.now() / 1000)
  const schedule = []
  const ids = new Set()

  for (const event of runtime.events.filter(x => active(x, now))) {
    const wire = wireEvent(event, false)
    schedule.push(wire)
    ids.add(String(wire.id))
  }

  const archive = archiveMode(runtime.gameData)
  for (const pass of storyBattlePasses(runtime.gameData)) {
    if (Number(pass?.availability ?? 1) < 1) continue
    if (!archive && !active(pass, now)) continue
    if (ids.has(String(pass.id))) continue
    schedule.push(wireEvent(pass, archive))
    ids.add(String(pass.id))
  }

  return schedule
}

// ---- Estado do ciclo game-mode-event (espelha chapters.js) ----

function gameModeLifecycle (repo, userId) {
  return repo.getState(userId, NS, GME_KEY, { runs: {}, meta: {} })
}

function saveGameModeLifecycle (repo, userId, value) {
  repo.setState(userId, NS, GME_KEY, value)
  return value
}

function eventDefinition (scheduledEventId, runtime) {
  return runtime.events.find(event => asInt(event?.id) === scheduledEventId) || null
}

function runWire (run) {
  const wire = {
    scheduled_event_id: run.scheduled_event_id,
    seed: run.seed,
    start_time: run.start_time
  }
  if (Array.isArray(run.slots) && run.slots.length > 0) wire.slots = run.slots
  if (asInt(run.max_loot) !== null) wire.max_loot = run.max_loot
  if (asInt(run.battle_pass_points_loot) !== null) wire.battle_pass_points_loot = run.battle_pass_points_loot
  if (run.game_mode_event_progress !== null && run.game_mode_event_progress !== undefined) {
    wire.game_mode_event_progress = run.game_mode_event_progress
  }
  if (Array.isArray(run.loot_pools) && run.loot_pools.length > 0) wire.loot_pools = run.loot_pools
  return wire
}

function gameModeEventStateWire (event, lifecycle) {
  const id = asInt(event?.id)
  const meta = lifecycle?.meta?.[String(id)] || {}
  const wire = {
    attempts: asInt(meta.attempts) ?? 0,
    scheduled_event_id: id,
    highest_stage: asInt(meta.highest_stage) ?? 0,
    best_completion_time_milliseconds: asInt(meta.best_completion_time_milliseconds) ?? 0
  }
  const run = lifecycle?.runs?.[String(id)]
  if (run) wire.run = runWire(run)
  return wire
}

function storeOfferStateWire (event) {
  // StoreOfferEventState tem um único campo: scheduledEventId.
  return { scheduled_event_id: asInt(event?.id) }
}

function offerWire (event, activatedAt) {
  const definitionId = asInt(event?.offer_definition_id) ?? asInt(event?.id)
  const wire = {
    id: asInt(event?.id),
    offer_definition_id: definitionId,
    item_id: asInt(event?.item_id),
    allowed_purchases: asInt(event?.allowed_purchases) ?? 1,
    start_time: activatedAt
  }
  const endTime = asEpoch(event?.end_time)
  if (endTime !== null) wire.end_time = endTime
  const purchaseAmount = asInt(event?.purchase_amount)
  if (purchaseAmount !== null) wire.purchase_amount = purchaseAmount
  if (Array.isArray(event?.alt_resources) && event.alt_resources.length > 0) wire.alt_resources = event.alt_resources
  if (event?.targeted_offer_type != null) wire.targeted_offer_type = event.targeted_offer_type
  if (event?.offer_group != null) wire.offer_group = event.offer_group
  if (event?.api_version != null) wire.api_version = event.api_version
  return wire
}

function eventStageRewardWire (entry) {
  const wire = { stage: asInt(entry?.stage) ?? 0, resources: asArray(entry?.resources) }
  const lootRolls = asInt(entry?.loot_rolls)
  if (lootRolls !== null) wire.loot_rolls = lootRolls
  return wire
}

export function eventProgress (repo, userId, runtime) {
  const now = Math.floor(Date.now() / 1000)
  const lifecycle = gameModeLifecycle(repo, userId)
  const result = {
    game_mode_events_progress: [],
    store_offer_events_states: [],
    battle_pass_events_states: []
  }

  for (const event of runtime.events.filter(x => active(x, now))) {
    const channel = channelOf(event)
    if (channel === 'battle_pass') {
      const fallback = event.progress_template || { event_id: event.id }
      result.battle_pass_events_states.push(repo.getState(userId, 'event', String(event.id), fallback))
    } else if (channel === 'store_offer') {
      result.store_offer_events_states.push(storeOfferStateWire(event))
    } else {
      const id = asInt(event.id)
      const meta = lifecycle?.meta?.[String(id)]
      if (meta) {
        result.game_mode_events_progress.push(gameModeEventStateWire(event, lifecycle))
      } else {
        // Config legado com progress_template continua funcionando.
        const legacy = repo.getState(userId, 'event', String(event.id), null)
        result.game_mode_events_progress.push(legacy || { event_id: event.id })
      }
    }
  }

  const existing = new Set(result.battle_pass_events_states.map(state => String(state?.season_id ?? state?.event_id ?? '')))
  for (const state of activeBattlePassStates(repo, userId, runtime)) {
    if (existing.has(String(state.season_id))) continue
    result.battle_pass_events_states.push(state)
  }

  return result
}

function scheduledEventIdFromBody (body) {
  return asInt(body?.scheduled_event_id ?? body?.scheduledEventId)
}

function requireActiveEvent (scheduledEventId, runtime, expectedChannel) {
  if (scheduledEventId === null) return { error: [400, 2200, { reason: 'scheduled-event-required' }] }
  const definition = eventDefinition(scheduledEventId, runtime)
  if (!definition || !active(definition, nowSeconds())) {
    return { error: [400, 2200, { reason: 'event-not-found' }] }
  }
  if (channelOf(definition) !== expectedChannel) {
    return { error: [400, 2200, { reason: 'event-not-found' }] }
  }
  return { definition }
}

function progressBody (body = {}) {
  return body?.progress && typeof body.progress === 'object' ? body.progress : body
}

function mergeRunProgress (run, body = {}) {
  const progress = progressBody(body)
  const next = { ...run, updated_at: nowSeconds() }
  const stage = asInt(progress.stage ?? progress.stage_index)
  if (stage !== null) next.stage = Math.max(asInt(next.stage) ?? 0, stage)
  next.game_mode_event_progress = progress
  return next
}

function grantResources (repo, userId, entries, runtime) {
  const grants = []
  for (const entry of entries) grants.push(giveGameResource(repo, userId, entry, runtime).wire)
  return grants
}

// AdRewardToken: emitido pelo fluxo de anúncios (game/ads/*, fora de escopo).
// Sem emissor o estado honesto é o erro explícito — nunca sucesso falso.
function adRewardRoute (repo, userId, body, expectedType) {
  const tokenId = asInt(body?.reward_token_id ?? body?.rewardTokenId)
  if (tokenId === null) return { error: [400, 2200, { reason: 'reward-token-required' }] }
  const scheduledEventId = scheduledEventIdFromBody(body)
  if (scheduledEventId === null) return { error: [400, 2200, { reason: 'scheduled-event-required' }] }
  const tokens = asArray(repo.getState(userId, 'ads', 'reward_tokens', []))
  const token = tokens.find(row => asInt(row?.id) === tokenId)
  if (!token) return { error: [400, 2300, { reason: 'reward-token-not-found' }] }
  if ((token.reward_type ?? token.type) !== expectedType) {
    return { error: [400, 2300, { reason: 'reward-token-type-mismatch' }] }
  }
  const expireEpoch = asInt(token.expire_epoch)
  if (expireEpoch !== null && expireEpoch < nowSeconds()) {
    return { error: [400, 2300, { reason: 'reward-token-expired' }] }
  }
  const lifecycle = gameModeLifecycle(repo, userId)
  const run = lifecycle.runs[String(scheduledEventId)]
  if (!run) return { error: [400, 2300, { reason: 'no-active-run' }] }
  let result
  repo.tx(() => {
    repo.setState(userId, 'ads', 'reward_tokens', tokens.filter(row => asInt(row?.id) !== tokenId))
    const nextRun = expectedType === 'revive'
      ? { ...run, revives: Math.max(0, Number(run.revives || 0)) + 1, updated_at: nowSeconds() }
      : { ...run, ability_rerolls: (asInt(run.ability_rerolls) ?? 0) + 1, updated_at: nowSeconds() }
    lifecycle.runs[String(scheduledEventId)] = nextRun
    saveGameModeLifecycle(repo, userId, lifecycle)
    result = { data: {} }
  })
  return result
}

export function handleEventRequest (path, body, userId, repo, runtime) {
  if (path === '/game/events/get-schedule') {
    return { data: { scheduled_events: eventSchedule(runtime) } }
  }

  if (path === '/game/events/get-progress') {
    return { data: eventProgress(repo, userId, runtime) }
  }

  if (path === '/game/events/get-instance') {
    const instanceId = asInt(body?.instance_id ?? body?.instanceId)
    if (instanceId === null) return { error: [400, 2200, { reason: 'instance-required' }] }
    const now = nowSeconds()
    const row = runtime.events.find(event => asInt(event?.id) === instanceId && active(event, now))
      || storyBattlePasses(runtime.gameData).find(pass => asInt(pass?.id) === instanceId)
      || null
    if (!row) return { error: [400, 2200, { reason: 'event-not-found' }] }
    return { data: { event_instance: wireEvent(row) } }
  }

  if (path === '/game/events/start-game-mode-event') {
    const scheduledEventId = scheduledEventIdFromBody(body)
    const check = requireActiveEvent(scheduledEventId, runtime, 'game_mode')
    if (check.error) return { error: check.error }
    const lifecycle = gameModeLifecycle(repo, userId)
    if (lifecycle.runs[String(scheduledEventId)]) return { error: [400, 2300, { reason: 'run-already-active' }] }
    const definition = check.definition
    const startedAt = nowSeconds()
    const run = {
      scheduled_event_id: scheduledEventId,
      seed: (startedAt * 1000 + (Date.now() % 1000)) % 2147483647,
      start_time: startedAt,
      started_at_ms: Date.now(),
      slots: Array.isArray(definition.slots) ? definition.slots : [],
      max_loot: asInt(definition.max_loot),
      battle_pass_points_loot: asInt(definition.battle_pass_points_loot),
      loot_pools: Array.isArray(definition.loot_pools) ? definition.loot_pools : [],
      game_mode_event_progress: null,
      stage: 0,
      revives: 0,
      ability_rerolls: 0,
      redeemed_vouchers: [],
      updated_at: startedAt
    }
    repo.tx(() => {
      repo.incrementAttemptCount(userId)
      const meta = lifecycle.meta[String(scheduledEventId)] || {}
      lifecycle.meta[String(scheduledEventId)] = {
        ...meta,
        attempts: (asInt(meta.attempts) ?? 0) + 1
      }
      lifecycle.runs[String(scheduledEventId)] = run
      saveGameModeLifecycle(repo, userId, lifecycle)
    })
    return { data: { attempt: runWire(run) } }
  }

  if (path === '/game/events/update-game-mode-event-progress') {
    const scheduledEventId = scheduledEventIdFromBody(body)
    if (scheduledEventId === null) return { error: [400, 2200, { reason: 'scheduled-event-required' }] }
    const lifecycle = gameModeLifecycle(repo, userId)
    const run = lifecycle.runs[String(scheduledEventId)]
    if (!run) return { error: [400, 2300, { reason: 'no-active-run' }] }
    lifecycle.runs[String(scheduledEventId)] = mergeRunProgress(run, body)
    saveGameModeLifecycle(repo, userId, lifecycle)
    return { data: { min_update_time: null } }
  }

  if (path === '/game/events/game-mode-event-revive') {
    const scheduledEventId = scheduledEventIdFromBody(body)
    if (scheduledEventId === null) return { error: [400, 2200, { reason: 'scheduled-event-required' }] }
    const lifecycle = gameModeLifecycle(repo, userId)
    const run = lifecycle.runs[String(scheduledEventId)]
    if (!run) return { error: [400, 2300, { reason: 'no-active-run' }] }
    lifecycle.runs[String(scheduledEventId)] = {
      ...run,
      revives: Math.max(0, Number(run.revives || 0)) + 1,
      updated_at: nowSeconds()
    }
    saveGameModeLifecycle(repo, userId, lifecycle)
    return { data: {} }
  }

  if (path === '/game/events/game-mode-event-ad-revive') {
    return adRewardRoute(repo, userId, body, 'revive')
  }
  if (path === '/game/events/game-mode-event-ad-ability-reroll') {
    return adRewardRoute(repo, userId, body, 'ability_reroll')
  }

  // GameModeEventRedeemVoucher(voucherId): sem scheduledEventId no contrato —
  // aplica ao run ativo que houver (espelha o RedeemVoucher de chapters).
  if (path === '/game/events/game-mode-event-redeem-voucher') {
    const voucherId = asInt(body?.voucher_id ?? body?.voucher)
    if (voucherId === null) return { error: [400, 2200, { reason: 'voucher-required' }] }
    const lifecycle = gameModeLifecycle(repo, userId)
    const entry = Object.entries(lifecycle.runs).find(([, run]) => run) || null
    if (!entry) return { error: [400, 2300, { reason: 'no-active-run' }] }
    const voucher = asArray(repo.items(userId)).find(item => asInt(item?.rid) === voucherId)
    if (!voucher) return { error: [400, 2300, { reason: 'voucher-not-owned' }] }
    let result
    try {
      repo.tx(() => {
        if (!repo.deleteItem(userId, voucher.id)) {
          throw Object.assign(new Error('voucher-not-owned'), { result: { error: [400, 2300, { reason: 'voucher-not-owned' }] } })
        }
        const [key, run] = entry
        lifecycle.runs[key] = {
          ...run,
          revives: Math.max(0, Number(run.revives || 0)) + 1,
          redeemed_vouchers: [...new Set([...asArray(run.redeemed_vouchers), voucherId])],
          updated_at: nowSeconds()
        }
        saveGameModeLifecycle(repo, userId, lifecycle)
        result = { data: {} }
      })
    } catch (error) {
      return error.result || { error: [400, 2000, { reason: error.message }] }
    }
    return result
  }

  if (path === '/game/events/end-game-mode-event') {
    const scheduledEventId = scheduledEventIdFromBody(body)
    if (scheduledEventId === null) return { error: [400, 2200, { reason: 'scheduled-event-required' }] }
    const lifecycle = gameModeLifecycle(repo, userId)
    const run = lifecycle.runs[String(scheduledEventId)]
    if (!run) return { error: [400, 2300, { reason: 'no-active-run' }] }
    const definition = eventDefinition(scheduledEventId, runtime)
    const finalRun = mergeRunProgress(run, body)
    const progress = progressBody(body)
    const completed = Number.isInteger(progress.state) ? progress.state === 1 : body?.completed !== false
    const stage = asInt(finalRun.stage) ?? 0
    const stageRewards = asArray(definition?.stage_rewards)
    const entry = stageRewards.find(row => asInt(row?.stage) === stage)
    const completionMs = completed
      ? asInt(progress.completion_time_milliseconds) ?? Math.max(0, Date.now() - Number(finalRun.started_at_ms || finalRun.start_time * 1000))
      : null
    let resources
    let stageRewardWire
    repo.tx(() => {
      resources = entry ? grantResources(repo, userId, asArray(entry.resources), runtime) : []
      stageRewardWire = entry ? eventStageRewardWire(entry) : null
      const meta = lifecycle.meta[String(scheduledEventId)] || {}
      const previousBest = asInt(meta.best_completion_time_milliseconds) ?? 0
      lifecycle.meta[String(scheduledEventId)] = {
        ...meta,
        attempts: asInt(meta.attempts) ?? 0,
        highest_stage: Math.max(asInt(meta.highest_stage) ?? 0, stage),
        best_completion_time_milliseconds: completionMs !== null
          ? (previousBest > 0 ? Math.min(previousBest, completionMs) : completionMs)
          : previousBest
      }
      delete lifecycle.runs[String(scheduledEventId)]
      saveGameModeLifecycle(repo, userId, lifecycle)
    })
    return { data: { resources, stage_rewards: stageRewardWire ? [stageRewardWire] : [] } }
  }

  if (path === '/game/events/activate-store-offer-event') {
    const scheduledEventId = scheduledEventIdFromBody(body)
    const check = requireActiveEvent(scheduledEventId, runtime, 'store_offer')
    if (check.error) return { error: check.error }
    const definition = check.definition
    if (asInt(definition.item_id) === null) return { error: [400, 2300, { reason: 'store-offer-config-missing' }] }
    const activatedAt = nowSeconds()
    // StoreOfferEventState{scheduledEventId} + PlayerOfferModel no wire.
    repo.setState(userId, NS, `store_offer:${scheduledEventId}`, {
      scheduled_event_id: scheduledEventId,
      activated_at: activatedAt
    })
    return { data: { offer: offerWire(definition, activatedAt) } }
  }

  return null
}
