import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'

import {
  handleBattlePassRequest,
  setBattlePassMissionProgress
} from '../src/battle-pass.js'
import { Repository } from '../src/db.js'
import { eventProgress, eventSchedule } from '../src/events.js'

const dir = mkdtempSync(resolve(tmpdir(), 'mighty-doom-battle-pass-'))
const dbPath = resolve(dir, 'battle-pass.sqlite3')
const repo = new Repository(dbPath)

const coin = { id: 100, tag: 'coins', category: 1 }
const season = {
  id: 'season-archive-test',
  event_definition_id: 9000,
  event_type: 3,
  availability: 1,
  start_time: 1,
  end_time: 2,
  min_api_version: '24.0.0',
  max_api_version: null,
  args: {
    missions: {
      seasonal_missions: [
        { mission: { id: 500, points: 100 } }
      ]
    },
    reward_track: {
      tiers: [
        {
          id: 1,
          point_threshold: 100,
          rewards: [
            {
              id: 10,
              requires_premium: true,
              reward_items: {
                resources: [
                  { resource: { id: 100 }, amount: 25 }
                ]
              }
            }
          ]
        },
        {
          id: 2,
          point_threshold: 150,
          rewards: [
            {
              id: 11,
              reward_items: {
                resources: [
                  { resource: { id: 100 }, amount: 15 }
                ]
              }
            },
            {
              id: 12,
              requires_premium: true,
              reward_items: {
                resources: [
                  { resource: { id: 100 }, amount: 40 }
                ]
              }
            }
          ]
        }
      ],
      prestige_point_start: 10,
      prestige_point_increment: 5,
      prestige_requires_premium: false,
      prestige_reward_pool: [
        { reward_items: { resources: [{ resource: { id: 100 }, amount: 50 }] } }
      ]
    },
    points_exchange_rate: { in_currency: 'coins', in_amount: 30, out_points: 25 }
  }
}

// Temporada separada para o gate de premium com unlock desligado.
const premiumSeason = {
  id: 'season-premium-test',
  availability: 1,
  start_time: 1,
  end_time: 2,
  args: {
    premium_entitlement_id: 700,
    reward_track: {
      tiers: [
        {
          id: 1,
          point_threshold: 0,
          rewards: [
            {
              id: 20,
              requires_premium: true,
              reward_items: { resources: [{ resource: { id: 100 }, amount: 7 }] }
            }
          ]
        }
      ]
    }
  }
}

const runtime = {
  gameData: {
    resources: [coin],
    story_battle_passes: [season, premiumSeason]
  },
  revival: {
    archive_mode: true,
    unlock_premium_battle_pass: true
  },
  events: [],
  index: {
    byId: new Map([[100, coin]]),
    byTag: new Map([['coins', 100]])
  }
}
const runtimeLocked = { ...runtime, revival: { ...runtime.revival, unlock_premium_battle_pass: false } }

try {
  const { user } = repo.createUser()
  const UID = user.id
  const H = (path, body, rt = runtime) => handleBattlePassRequest(path, body, UID, repo, rt)

  // Battle passes de história ficam FORA do schedule: o cliente 1.13.1
  // processa todo evento agendado como game-mode no EventModeController e
  // NRE com o FTUE_BattlePass na lista (provado no emulador 2026-08-19).
  // O season segue visível via get-progress (preview de archive abaixo) e
  // operável via start/end-season.
  const schedule = eventSchedule(runtime)
  assert.equal(schedule.length, 0)

  // Archive mode must advertise preserved seasons before the client explicitly
  // starts one, but the preview must not persist and block /start-season.
  const preview = eventProgress(repo, UID, runtime)
  assert.equal(preview.battle_pass_events_states.length, 2)
  assert.equal(preview.battle_pass_events_states[0].season_id, season.id)
  assert.equal(preview.battle_pass_events_states[0].points, 0)
  // PremiumState: None=0, Free=1, Premium=2 — liberado por padrão no revival.
  assert.equal(preview.battle_pass_events_states[0].premium_state, 2)
  assert.equal(preview.battle_pass_events_states[0].mission_progress[0].mission_id, 500)
  assert.equal(repo.getState(UID, 'battle-pass', season.id, null), null)

  const started = H('/game/battle-pass/start-season', { season_id: season.id })
  assert.equal(started.data.state.season_id, season.id)
  assert.equal(started.data.state.premium_state, 2)
  assert.equal(started.data.state.points, 0)
  assert.equal(started.data.state.mission_progress[0].mission_id, 500)
  assert.equal(Object.keys(started.data).length, 1, 'StartSeasonResponse só tem state')

  const duplicateStart = H('/game/battle-pass/start-season', { season_id: season.id })
  assert.equal(duplicateStart.error[2].reason, 'season-already-started')

  const tooEarly = H('/game/battle-pass/claim-mission', { season_id: season.id, mission_id: 500 })
  assert.equal(tooEarly.error[2].reason, 'mission-not-claimable')

  assert.equal(
    setBattlePassMissionProgress(repo, UID, runtime, season.id, 500, 1, true),
    true
  )

  const missionClaim = H('/game/battle-pass/claim-mission', { season_id: season.id, mission_id: 500 })
  assert.deepEqual(missionClaim.data.resources, [])

  const tierClaim = H('/game/battle-pass/claim-track-tier', { season_id: season.id, tier_id: 1 })
  assert.equal(tierClaim.data.resources.length, 1)
  assert.equal(repo.balance(UID, 100), 25)

  const secondTierClaim = H('/game/battle-pass/claim-track-tier', { season_id: season.id, tier_id: 1 })
  assert.deepEqual(secondTierClaim.data.resources, [])
  assert.equal(repo.balance(UID, 100), 25)

  // claim-track-reward: reward único do tier; gates de pontos/claim/premium.
  let result = H('/game/battle-pass/claim-track-reward', { season_id: season.id, tier_id: 2, reward_id: 11 })
  assert.equal(result.error[1], 2300)
  assert.equal(result.error[2].reason, 'insufficient-points')
  assert.equal(H('/game/battle-pass/claim-track-reward', { season_id: season.id, tier_id: 2, reward_id: 99 }).error[2].reason, 'reward-not-found')
  assert.equal(H('/game/battle-pass/claim-track-reward', { season_id: season.id, tier_id: 1, reward_id: 10 }).error[2].reason, 'reward-already-claimed')

  // buy-next-track-tier: custo = ceil(pontos faltantes/out_points)*in_amount.
  result = H('/game/battle-pass/buy-next-track-tier', { season_id: season.id })
  assert.equal(result.error[2].reason, 'insufficient-currency')
  repo.addCurrency(UID, 100, 100)
  result = H('/game/battle-pass/buy-next-track-tier', { season_id: season.id })
  assert.equal(Object.keys(result.data).length, 0, 'BuyNextTrackTierResponse sem campos -> envelope puro')
  assert.equal(repo.balance(UID, 100), 65)

  result = H('/game/battle-pass/claim-track-reward', { season_id: season.id, tier_id: 2, reward_id: 11 })
  assert.deepEqual(result.data.resources, [{ rid: 100, amount: 80 }])
  assert.equal(repo.balance(UID, 100), 80)

  // claim-track-all: varre tudo conquistado e não reivindicado.
  result = H('/game/battle-pass/claim-track-all', { season_id: season.id })
  assert.deepEqual(result.data.resources, [{ rid: 100, amount: 120 }])
  assert.equal(repo.balance(UID, 100), 120)
  assert.equal(H('/game/battle-pass/claim-track-all', { season_id: season.id }).error[2].reason, 'nothing-to-claim')

  const progress = eventProgress(repo, UID, runtime)
  assert.equal(progress.battle_pass_events_states[0].season_id, season.id)
  assert.equal(progress.battle_pass_events_states[0].points, 150)
  assert.deepEqual(progress.battle_pass_events_states[0].reward_claims, [
    { tier_id: 1, reward_id: 10 },
    { tier_id: 2, reward_id: 11 },
    { tier_id: 2, reward_id: 12 }
  ])

  // prestige: exige o último tier; reseta pontos/claims e concede o pool.
  result = H('/game/battle-pass/prestige', { season_id: season.id })
  assert.deepEqual(result.data.resources, [{ rid: 100, amount: 170 }])
  assert.equal(repo.balance(UID, 100), 170)
  result = eventProgress(repo, UID, runtime)
  assert.equal(result.battle_pass_events_states[0].prestige, 1)
  assert.equal(result.battle_pass_events_states[0].points, 10)
  assert.deepEqual(result.battle_pass_events_states[0].reward_claims, [])
  assert.equal(H('/game/battle-pass/prestige', { season_id: season.id }).error[2].reason, 'prestige-not-available')

  // end-season: concede o que faltar e marca Ended (ActiveState=2).
  result = H('/game/battle-pass/end-season', { season_id: season.id })
  assert.deepEqual(result.data.resources, [])
  assert.equal(H('/game/battle-pass/end-season', { season_id: season.id }).error[2].reason, 'season-ended')
  assert.equal(H('/game/battle-pass/claim-track-tier', { season_id: season.id, tier_id: 1 }).error[2].reason, 'season-ended')

  // redeem-premium-entitlement com unlock desligado: None -> Premium via
  // posse do entitlement configurado no args da temporada.
  const second = repo.createUser().user
  const L = (path, body) => handleBattlePassRequest(path, body, second.id, repo, runtimeLocked)
  result = L('/game/battle-pass/start-season', { season_id: premiumSeason.id })
  assert.equal(result.data.state.premium_state, 0)
  result = L('/game/battle-pass/claim-track-reward', { season_id: premiumSeason.id, tier_id: 1, reward_id: 20 })
  assert.equal(result.error[2].reason, 'premium-required')
  result = L('/game/battle-pass/redeem-premium-entitlement', { season_id: premiumSeason.id })
  assert.equal(result.error[2].reason, 'premium-not-entitled')
  repo.addEntitlement(second.id, 700)
  result = L('/game/battle-pass/redeem-premium-entitlement', { season_id: premiumSeason.id })
  assert.equal(Object.keys(result.data).length, 0, 'RedeemPremiumEntitlementResponse sem campos')
  result = L('/game/battle-pass/claim-track-reward', { season_id: premiumSeason.id, tier_id: 1, reward_id: 20 })
  assert.deepEqual(result.data.resources, [{ rid: 100, amount: 7 }])
  assert.equal(L('/game/battle-pass/redeem-premium-entitlement', { season_id: premiumSeason.id }).error[2].reason, 'already-premium')

  // persistência: pontos/prestige/ended e o premium resgatado sobrevivem.
  repo.close()
  const reopened = new Repository(dbPath)
  const state = reopened.getState(UID, 'battle-pass', season.id, null)
  assert.equal(state.points, 10)
  assert.equal(state.prestige, 1)
  assert.equal(state.active_state, 2)
  assert.equal(reopened.balance(UID, 100), 170)
  const premiumState = reopened.getState(second.id, 'battle-pass', premiumSeason.id, null)
  assert.equal(premiumState.premium_state, 2)
  assert.equal(reopened.balance(second.id, 100), 7)
  reopened.close()

  // FTUE real (rig local 2026-08-19, request_log 250→251): o cliente chama
  // end-season e start-season da MESMA season no mesmo boot. Estado Ended
  // não pode devolver season-already-started — o cliente cai em "playing
  // offline". Restart recomeça com o state default (Active, zerado).
  const third = new Repository(dbPath)
  const restart = handleBattlePassRequest('/game/battle-pass/start-season', { season_id: season.id }, UID, third, runtime)
  assert.equal(restart.data.state.season_id, season.id)
  assert.equal(restart.data.state.active_state, 1, 'restart volta a Active')
  assert.equal(restart.data.state.points, 0, 'restart zera pontos (state default)')
  third.close()

  console.log('Mighty DOOM Revival battle pass test: PASS')
} finally {
  try { repo.close() } catch {}
  rmSync(dir, { recursive: true, force: true })
}
