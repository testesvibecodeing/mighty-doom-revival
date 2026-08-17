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
const repo = new Repository(resolve(dir, 'battle-pass.sqlite3'))

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
        }
      ]
    }
  }
}

const runtime = {
  gameData: {
    resources: [coin],
    story_battle_passes: [season]
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

try {
  const { user } = repo.createUser()

  const schedule = eventSchedule(runtime)
  assert.equal(schedule.length, 1)
  assert.equal(schedule[0].id, season.id)
  assert.equal(schedule[0].start_time, null)
  assert.equal(schedule[0].end_time, null)
  assert.deepEqual(
    JSON.parse(Buffer.from(schedule[0].args, 'base64').toString('utf8')),
    season.args
  )

  // Archive mode must advertise preserved seasons before the client explicitly
  // starts one, but the preview must not persist and block /start-season.
  const preview = eventProgress(repo, user.id, runtime)
  assert.equal(preview.battle_pass_events_states.length, 1)
  assert.equal(preview.battle_pass_events_states[0].season_id, season.id)
  assert.equal(preview.battle_pass_events_states[0].points, 0)
  assert.equal(preview.battle_pass_events_states[0].premium_state, 1)
  assert.equal(preview.battle_pass_events_states[0].mission_progress[0].mission_id, 500)
  assert.equal(repo.getState(user.id, 'battle-pass', season.id, null), null)

  const started = handleBattlePassRequest(
    '/game/battle-pass/start-season',
    { season_id: season.id },
    user.id,
    repo,
    runtime
  )
  assert.equal(started.data.state.season_id, season.id)
  assert.equal(started.data.state.premium_state, 1)
  assert.equal(started.data.state.points, 0)
  assert.equal(started.data.state.mission_progress[0].mission_id, 500)

  const duplicateStart = handleBattlePassRequest(
    '/game/battle-pass/start-season',
    { season_id: season.id },
    user.id,
    repo,
    runtime
  )
  assert.equal(duplicateStart.error[2].reason, 'season-already-started')

  const tooEarly = handleBattlePassRequest(
    '/game/battle-pass/claim-mission',
    { season_id: season.id, mission_id: 500 },
    user.id,
    repo,
    runtime
  )
  assert.equal(tooEarly.error[2].reason, 'mission-not-claimable')

  assert.equal(
    setBattlePassMissionProgress(repo, user.id, runtime, season.id, 500, 1, true),
    true
  )

  const missionClaim = handleBattlePassRequest(
    '/game/battle-pass/claim-mission',
    { season_id: season.id, mission_id: 500 },
    user.id,
    repo,
    runtime
  )
  assert.deepEqual(missionClaim.data.resources, [])

  const tierClaim = handleBattlePassRequest(
    '/game/battle-pass/claim-track-tier',
    { season_id: season.id, tier_id: 1 },
    user.id,
    repo,
    runtime
  )
  assert.equal(tierClaim.data.resources.length, 1)
  assert.equal(repo.balance(user.id, 100), 25)

  const secondTierClaim = handleBattlePassRequest(
    '/game/battle-pass/claim-track-tier',
    { season_id: season.id, tier_id: 1 },
    user.id,
    repo,
    runtime
  )
  assert.deepEqual(secondTierClaim.data.resources, [])
  assert.equal(repo.balance(user.id, 100), 25)

  const progress = eventProgress(repo, user.id, runtime)
  assert.equal(progress.battle_pass_events_states.length, 1)
  assert.equal(progress.battle_pass_events_states[0].season_id, season.id)
  assert.equal(progress.battle_pass_events_states[0].points, 100)
  assert.deepEqual(progress.battle_pass_events_states[0].reward_claims, [
    { tier_id: 1, reward_id: 10 }
  ])

  console.log('Mighty DOOM Revival archived battle pass test: PASS')
} finally {
  repo.close()
  rmSync(dir, { recursive: true, force: true })
}
