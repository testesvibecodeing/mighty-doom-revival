import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'

import { Repository } from '../src/db.js'
import { claimDailyQuest, claimDailyQuestMilestone, dailyQuestState } from '../src/quests.js'
import { incrementPlayerStats } from '../src/stats.js'

const dir = mkdtempSync(resolve(tmpdir(), 'mighty-doom-quests-'))
const dbPath = resolve(dir, 'quests.sqlite3')
const repo = new Repository(dbPath)

const currency = { id: 1, category: 1, tag: 'coins' }
const runtime = {
  gameData: {
    resources: [currency],
    quests: {
      daily_quests: [
        { id: 101, stat_id: 42, target: 3, rewards: [{ rid: 1, amount: 10 }] },
        { id: 102, stat: { id: 'demons-killed' }, amount: 2, rewards: [{ rid: 1, amount: 5 }] }
      ],
      daily_milestones: [
        { id: 201, target: 2, rewards: [{ rid: 1, amount: 25 }] }
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
  const epoch = 1_787_000_000

  let state = dailyQuestState(repo, user.id, runtime, epoch)
  assert.equal(state.quests.length, 2)
  assert.equal(state.quests[0].progress, 0)
  assert.equal(state.quests[0].completed, false)
  assert.equal(state.milestones[0].progress, 0)

  incrementPlayerStats(repo, user.id, {
    stats: [
      { stat_id: 42, increment: 3 },
      { tag: 'demons-killed', increment: 2 }
    ]
  }, runtime)

  state = dailyQuestState(repo, user.id, runtime, epoch)
  assert.equal(state.quests[0].progress, 3)
  assert.equal(state.quests[0].completed, true)
  assert.equal(state.quests[1].progress, 2)
  assert.equal(state.quests[1].completed, true)
  assert.equal(state.milestones[0].progress, 2)
  assert.equal(state.milestones[0].completed, true)

  const first = claimDailyQuest(repo, user.id, runtime, 101, epoch)
  assert.equal(first.ok, true)
  assert.equal(repo.balance(user.id, 1), 10)
  assert.equal(claimDailyQuest(repo, user.id, runtime, 101, epoch).reason, 'already-claimed')

  const second = claimDailyQuest(repo, user.id, runtime, 102, epoch)
  assert.equal(second.ok, true)
  assert.equal(repo.balance(user.id, 1), 15)

  const milestone = claimDailyQuestMilestone(repo, user.id, runtime, 201, epoch)
  assert.equal(milestone.ok, true)
  assert.equal(repo.balance(user.id, 1), 40)
  assert.equal(claimDailyQuestMilestone(repo, user.id, runtime, 201, epoch).reason, 'already-claimed')

  repo.close()
  const reopened = new Repository(dbPath)
  state = dailyQuestState(reopened, user.id, runtime, epoch)
  assert.equal(state.quests.every(row => row.claimed), true)
  assert.equal(state.milestones[0].claimed, true)
  assert.equal(reopened.balance(user.id, 1), 40)
  reopened.close()

  console.log('Mighty DOOM Revival daily quests test: PASS')
} finally {
  try { repo.close() } catch {}
  rmSync(dir, { recursive: true, force: true })
}
