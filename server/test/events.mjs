import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'

import { Repository } from '../src/db.js'
import { handleEventRequest } from '../src/events.js'
import { stripNulls } from '../src/wire.js'

// Dataset sintético — mesmo padrão dos demais testes de módulo.
const coins = { id: 100, tag: 'coins', category_id: 1 }
const runtime = {
  gameData: { resources: [coins] },
  revival: {},
  events: [
    {
      id: 501,
      start_time: '2026-01-01T00:00:00Z',
      end_time: '2030-01-01T00:00:00Z',
      stage_rewards: [
        { stage: 1, resources: [{ rid: 100, amount: 5 }] },
        { stage: 2, resources: [{ rid: 100, amount: 10 }], loot_rolls: 2 }
      ]
    },
    {
      id: 502,
      channel: 'store_offer',
      item_id: 250,
      allowed_purchases: 2,
      purchase_amount: 100,
      start_time: '2026-01-01T00:00:00Z',
      end_time: '2030-01-01T00:00:00Z'
    },
    { id: 503, channel: 'store_offer', start_time: '2026-01-01T00:00:00Z' },
    { id: 504, channel: 'battle_pass', progress_template: { season_id: 504, points: 0 } }
  ],
  index: { byId: new Map([[100, coins]]), byTag: new Map([['coins', coins]]) }
}

const dir = mkdtempSync(resolve(tmpdir(), 'mighty-doom-events-'))
const dbPath = resolve(dir, 'events.sqlite3')
const repo = new Repository(dbPath)

try {
  const { user } = repo.createUser()
  const UID = user.id
  const H = (path, body) => handleEventRequest(path, body, UID, repo, runtime)

  // get-schedule: eventos ativos dos três canais aparecem com o wire validado.
  let result = H('/game/events/get-schedule', {})
  assert.deepEqual(result.data.scheduled_events.map(row => row.id).sort(), [501, 502, 503, 504])

  // get-progress sem estado: game_mode legado, store_offer com o wire
  // StoreOfferEventState{scheduledEventId}, battle_pass com o template.
  result = H('/game/events/get-progress', {})
  assert.deepEqual(result.data.game_mode_events_progress, [{ event_id: 501 }])
  assert.deepEqual(result.data.store_offer_events_states, [
    { scheduled_event_id: 502 },
    { scheduled_event_id: 503 }
  ])
  assert.deepEqual(result.data.battle_pass_events_states, [{ season_id: 504, points: 0 }])

  // get-instance: wire do schedule para o id pedido; desconhecido -> 2200.
  result = H('/game/events/get-instance', { instance_id: 501 })
  assert.equal(result.data.event_instance.id, 501)
  assert.equal(result.data.event_instance.event_definition_id, 501)
  assert.equal('args' in result.data.event_instance, true)
  assert.equal(Object.keys(result.data).length, 1, 'GetInstanceResponse só tem event_instance')
  assert.equal(H('/game/events/get-instance', { instance_id: 999 }).error[2].reason, 'event-not-found')
  assert.equal(H('/game/events/get-instance', {}).error[2].reason, 'instance-required')

  // start: parâmetro obrigatório, evento inexistente/canal errado, happy path.
  assert.equal(H('/game/events/start-game-mode-event', {}).error[2].reason, 'scheduled-event-required')
  assert.equal(H('/game/events/start-game-mode-event', { scheduled_event_id: 999 }).error[2].reason, 'event-not-found')
  assert.equal(H('/game/events/start-game-mode-event', { scheduled_event_id: 502 }).error[2].reason, 'event-not-found')
  result = H('/game/events/start-game-mode-event', { scheduled_event_id: 501 })
  const attempt = result.data.attempt
  assert.equal(Object.keys(result.data).length, 1, 'StartGameModeEventResponse só tem attempt')
  assert.equal(attempt.scheduled_event_id, 501)
  assert.equal(typeof attempt.seed, 'number')
  assert.equal(typeof attempt.start_time, 'number')
  assert.equal(H('/game/events/start-game-mode-event', { scheduled_event_id: 501 }).error[2].reason, 'run-already-active')

  // get-progress agora com GameModeEventState{attempts, run, ...}.
  result = H('/game/events/get-progress', {})
  const state = result.data.game_mode_events_progress[0]
  assert.equal(state.attempts, 1)
  assert.equal(state.scheduled_event_id, 501)
  assert.equal(state.highest_stage, 0)
  assert.equal(state.best_completion_time_milliseconds, 0)
  assert.equal(state.run.scheduled_event_id, 501)

  // update-progress: sem run -> 2300; com run -> min_update_time nullable.
  assert.equal(H('/game/events/update-game-mode-event-progress', { scheduled_event_id: 503, progress: { stage: 1 } }).error[2].reason, 'no-active-run')
  result = H('/game/events/update-game-mode-event-progress', { scheduled_event_id: 501, progress: { stage: 2, state: 0 } })
  assert.deepEqual(result.data, { min_update_time: null })
  // No wire a chave é omitida: campo sem valor nunca sai como null
  // (AGENTS.md regra 6). Equivalente para nullable, obrigatório para os demais.
  assert.deepEqual(stripNulls(result.data), {})

  // revive: envelope puro; exige run do evento.
  assert.equal(H('/game/events/game-mode-event-revive', { scheduled_event_id: 503 }).error[2].reason, 'no-active-run')
  result = H('/game/events/game-mode-event-revive', { scheduled_event_id: 501 })
  assert.equal(Object.keys(result.data).length, 0)

  // ad-revive/ad-ability-reroll: token emitido pelo módulo de ads (fora de
  // escopo) — valida, confere tipo, consome e aplica ao run.
  repo.setState(UID, 'ads', 'reward_tokens', [
    { id: 77, reward_type: 'revive' },
    { id: 78, reward_type: 'ability_reroll' },
    { id: 79, reward_type: 'ability_reroll', expire_epoch: 1 }
  ])
  assert.equal(H('/game/events/game-mode-event-ad-revive', { reward_token_id: 99, scheduled_event_id: 501 }).error[2].reason, 'reward-token-not-found')
  assert.equal(H('/game/events/game-mode-event-ad-revive', { reward_token_id: 78, scheduled_event_id: 501 }).error[2].reason, 'reward-token-type-mismatch')
  assert.equal(H('/game/events/game-mode-event-ad-ability-reroll', { reward_token_id: 79, scheduled_event_id: 501 }).error[2].reason, 'reward-token-expired')
  result = H('/game/events/game-mode-event-ad-revive', { reward_token_id: 77, scheduled_event_id: 501 })
  assert.equal(Object.keys(result.data).length, 0)
  assert.equal(H('/game/events/game-mode-event-ad-revive', { reward_token_id: 77, scheduled_event_id: 501 }).error[2].reason, 'reward-token-not-found')
  result = H('/game/events/game-mode-event-ad-ability-reroll', { reward_token_id: 78, scheduled_event_id: 501 })
  assert.equal(Object.keys(result.data).length, 0)

  // redeem-voucher: consome item do inventário, aplica ao run ativo.
  assert.equal(H('/game/events/game-mode-event-redeem-voucher', { voucher_id: 900 }).error[2].reason, 'voucher-not-owned')
  repo.addItem(UID, { rid: 900, kind: 'equipment', level: 1, tier: null, amount: 1, metadata: {} })
  result = H('/game/events/game-mode-event-redeem-voucher', { voucher_id: 900 })
  assert.equal(Object.keys(result.data).length, 0)
  assert.equal(repo.items(UID).some(item => item.rid === 900), false)

  // end: concede o reward do estágio alcançado (saldo pós-grant no wire da
  // moeda) e reporta o EventStageReward; meta registra highest_stage/best time.
  result = H('/game/events/end-game-mode-event', { scheduled_event_id: 501, progress: { stage: 2, state: 1 } })
  assert.equal(Object.keys(result.data).length, 2, 'EndGameModeEventResponse: resources + stage_rewards')
  assert.deepEqual(result.data.resources, [{ rid: 100, amount: 10 }])
  assert.deepEqual(result.data.stage_rewards, [{ stage: 2, resources: [{ rid: 100, amount: 10 }], loot_rolls: 2 }])
  assert.equal(repo.balance(UID, 100), 10)
  result = H('/game/events/get-progress', {})
  const done = result.data.game_mode_events_progress[0]
  assert.equal(done.highest_stage, 2)
  assert.equal(done.best_completion_time_milliseconds > 0, true)
  assert.equal('run' in done, false, 'run encerrado não vai no wire')
  assert.equal(H('/game/events/end-game-mode-event', { scheduled_event_id: 501, progress: { stage: 2, state: 1 } }).error[2].reason, 'no-active-run')

  // end em estágio sem config: fields do DTO presentes, arrays vazios.
  H('/game/events/start-game-mode-event', { scheduled_event_id: 501 })
  result = H('/game/events/end-game-mode-event', { scheduled_event_id: 501, progress: { stage: 9, state: 1 } })
  assert.deepEqual(result.data, { resources: [], stage_rewards: [] })
  result = H('/game/events/get-progress', {})
  assert.equal(result.data.game_mode_events_progress[0].highest_stage, 9)
  assert.equal(result.data.game_mode_events_progress[0].attempts, 2)

  // activate-store-offer-event: canal errado, config sem item_id, happy path.
  assert.equal(H('/game/events/activate-store-offer-event', { scheduled_event_id: 501 }).error[2].reason, 'event-not-found')
  assert.equal(H('/game/events/activate-store-offer-event', { scheduled_event_id: 503 }).error[2].reason, 'store-offer-config-missing')
  result = H('/game/events/activate-store-offer-event', { scheduled_event_id: 502 })
  const offer = result.data.offer
  assert.equal(Object.keys(result.data).length, 1, 'ActivateStoreOfferEventResponse só tem offer')
  assert.equal(offer.id, 502)
  assert.equal(offer.offer_definition_id, 502)
  assert.equal(offer.item_id, 250)
  assert.equal(offer.allowed_purchases, 2)
  assert.equal(offer.purchase_amount, 100)
  assert.equal(typeof offer.start_time, 'number')
  assert.equal(typeof offer.end_time, 'number')
  assert.equal('alt_resources' in offer, false, 'campo ausente é omitido')

  // persistência: meta do evento e ativação do offer sobrevivem ao restart.
  repo.close()
  const reopened = new Repository(dbPath)
  const R = (path, body) => handleEventRequest(path, body, UID, reopened, runtime)
  result = R('/game/events/get-progress', {})
  assert.equal(result.data.game_mode_events_progress[0].attempts, 2)
  assert.equal(result.data.game_mode_events_progress[0].highest_stage, 9)
  assert.deepEqual(result.data.store_offer_events_states, [
    { scheduled_event_id: 502 },
    { scheduled_event_id: 503 }
  ])
  assert.equal(reopened.balance(UID, 100), 10)
  const saved = reopened.getState(UID, 'events', 'store_offer:502', null)
  assert.equal(saved.scheduled_event_id, 502)
  reopened.close()

  console.log('Mighty DOOM Revival events test: PASS')
} finally {
  try { repo.close() } catch {}
  rmSync(dir, { recursive: true, force: true })
}
