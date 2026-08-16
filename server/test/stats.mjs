import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'

import { handleBattlePassRequest, battlePassState } from '../src/battle-pass.js'
import { Repository } from '../src/db.js'
import { incrementPlayerStats, normalizeStatIncrements, playerStatsWire } from '../src/stats.js'

const dir = mkdtempSync(resolve(tmpdir(), 'mighty-doom-stats-'))
const repo = new Repository(resolve(dir, 'stats.sqlite3'))

const season = {
  id: 'season-stats-test',
  availability: 1,
  start_time: 1,
  end_time: 2,
  args: {
    missions: {
      seasonal_missions: [
        { mission: { id: 501, points: 75, stat_id: 42, target: 3 } },
        { mission: { id: 502, points: 25, stat: { id: 'demons-killed' }, amount: 5 } }
      ]
    },
    reward_track: { tiers: [] }
  }
}

const runtime = {
  gameData: { story_battle_passes: [season] },
  revival: { archive_mode: true, unlock_premium_battle_pass: true },
  index: { byId: new Map(), byTag: new Map() }
}

try {
  assert.deepEqual(normalizeStatIncrements({
    stats: [
      { stat_id: 42, increment: 1 },
      { id: 42, amount: 1 },
      { tag: 'demons-killed', value: 2 },
      { stat_id: 99, increment: -100 },
      { stat_id: 100, increment: 0 }
    ]
  }), { '42': 2, 'demons-killed': 2 })

  const { user } = repo.createUser()
  const started = handleBattlePassRequest(
    '/game/battle-pass/start-season',
    { season_id: season.id },
    user.id,
    repo,
    runtime
  )
  assert.equal(started.data.state.mission_progress.length, 2)

  let result = incrementPlayerStats(repo, user.id, {
    stats: [
      { stat_id: 42, increment: 2 },
      { tag: 'demons-killed', increment: 2 }
    ]
  }, runtime)
  assert.deepEqual(result.totals, { '42': 2, 'demons-killed': 2 })
  assert.equal(result.battle_pass_updates.length, 2)

  let state = battlePassState(repo, user.id, runtime, season.id)
  assert.equal(state.mission_progress[0].progress, 2)
  assert.equal(state.mission_progress[0].completed, false)
  assert.equal(state.mission_progress[1].progress, 2)

  result = incrementPlayerStats(repo, user.id, {
    increments: {
      42: 1,
      'demons-killed': 10
    }
  }, runtime)
  assert.deepEqual(result.totals, { '42': 3, 'demons-killed': 12 })

  state = battlePassState(repo, user.id, runtime, season.id)
  assert.equal(state.mission_progress[0].progress, 3)
  assert.equal(state.mission_progress[0].completed, true)
  assert.equal(state.mission_progress[0].claim_state, 2)
  assert.equal(state.mission_progress[1].progress, 5)
  assert.equal(state.mission_progress[1].completed, true)

  const claimed = handleBattlePassRequest(
    '/game/battle-pass/claim-mission',
    { season_id: season.id, mission_id: 501 },
    user.id,
    repo,
    runtime
  )
  assert.deepEqual(claimed.data.resources, [])
  assert.equal(battlePassState(repo, user.id, runtime, season.id).points, 75)

  assert.deepEqual(playerStatsWire(repo, user.id), [
    { id: 42, value: 3 },
    { id: 'demons-killed', value: 12 }
  ])

  repo.close()
  const reopened = new Repository(resolve(dir, 'stats.sqlite3'))
  assert.deepEqual(playerStatsWire(reopened, user.id), [
    { id: 42, value: 3 },
    { id: 'demons-killed', value: 12 }
  ])
  reopened.close()

  console.log('Mighty DOOM Revival player stats test: PASS')
} finally {
  try { repo.close() } catch {}
  rmSync(dir, { recursive: true, force: true })
}
