import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'

import { Repository } from '../src/db.js'
import { claimRewardTrackTier, handleRewardTrackRequest, rewardTrackState, rewardTrackWire } from '../src/reward-tracks.js'
import { incrementPlayerStats } from '../src/stats.js'

const dir = mkdtempSync(resolve(tmpdir(), 'mighty-doom-reward-tracks-'))
const dbPath = resolve(dir, 'reward-tracks.sqlite3')
const repo = new Repository(dbPath)

const currency = { id: 1, category: 1, tag: 'coins' }
const runtime = {
  gameData: {
    resources: [currency],
    reward_tracks: {
      tracks: [
        {
          id: 700,
          stat_id: 'demons-killed',
          tiers: [
            { id: 701, target: 2, resources: [{ rid: 1, amount: 10 }] },
            { id: 702, target: 5, resources: [{ rid: 1, amount: 25 }] }
          ]
        }
      ]
    }
  },
  revival: {},
  index: {
    byId: new Map([[1, currency]]),
    byTag: new Map([['coins', currency]])
  }
}

try {
  const { user } = repo.createUser()

  let tracks = rewardTrackState(repo, user.id, runtime)
  assert.equal(tracks.length, 1)
  assert.equal(tracks[0].progress, 0)
  assert.equal(tracks[0].tiers[0].completed, false)

  incrementPlayerStats(repo, user.id, { stats: [{ tag: 'demons-killed', increment: 2 }] }, runtime)
  tracks = rewardTrackState(repo, user.id, runtime)
  assert.equal(tracks[0].progress, 2)
  assert.equal(tracks[0].tiers[0].completed, true)
  assert.equal(tracks[0].tiers[1].completed, false)

  const first = claimRewardTrackTier(repo, user.id, runtime, 700, 701)
  assert.equal(first.ok, true)
  assert.equal(repo.balance(user.id, 1), 10)
  assert.equal(claimRewardTrackTier(repo, user.id, runtime, 700, 701).reason, 'already-claimed')
  assert.equal(claimRewardTrackTier(repo, user.id, runtime, 700, 702).reason, 'tier-not-complete')

  incrementPlayerStats(repo, user.id, { increments: { 'demons-killed': 3 } }, runtime)
  const second = claimRewardTrackTier(repo, user.id, runtime, 700, 702)
  assert.equal(second.ok, true)
  assert.equal(repo.balance(user.id, 1), 35)

  // Wire RewardTrackModel (metadata v29): {id, track_id, entries_claimed,
  // entries:[{id, resources}]}; claim responde ClaimRewardTrackResponse{resources}.
  tracks = rewardTrackState(repo, user.id, runtime)
  const wire = rewardTrackWire(tracks[0])
  assert.equal(wire.id, 700)
  assert.equal(wire.track_id, 700)
  assert.deepEqual(wire.entries_claimed, [701, 702])
  assert.equal(wire.entries.length, 2)
  assert.deepEqual(wire.entries[0].resources, [{ rid: 1, amount: 10 }])
  assert.equal('next_claim_epoch' in wire, false, 'sem cooldown o campo é omitido')

  let handled = handleRewardTrackRequest('/game/reward-tracks/get-all', {}, user.id, repo, runtime)
  assert.equal(handled.data.tracks.length, 1)
  assert.deepEqual(handled.data.tracks[0].entries_claimed, [701, 702])

  handled = handleRewardTrackRequest('/game/reward-tracks/get-track', { track_id: 700 }, user.id, repo, runtime)
  assert.equal(handled.data.track.id, 700)
  assert.equal(Object.keys(handled.data).length, 1, 'GetTrackResponse só tem track')
  handled = handleRewardTrackRequest('/game/reward-tracks/get-track', { track_id: 999 }, user.id, repo, runtime)
  assert.equal(handled.error[2].reason, 'track-not-found')

  handled = handleRewardTrackRequest('/game/reward-tracks/claim', { track_id: 999, tier_id: 1 }, user.id, repo, runtime)
  assert.equal(handled.error[2].reason, 'track-not-found')

  repo.close()
  const reopened = new Repository(dbPath)
  tracks = rewardTrackState(reopened, user.id, runtime)
  assert.equal(tracks[0].progress, 5)
  assert.equal(tracks[0].tiers.every(row => row.claimed), true)
  assert.equal(reopened.balance(user.id, 1), 35)
  reopened.close()

  console.log('Mighty DOOM Revival reward tracks test: PASS')
} finally {
  try { repo.close() } catch {}
  rmSync(dir, { recursive: true, force: true })
}
