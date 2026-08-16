import assert from 'node:assert/strict'
import { claimDailyReward, claimIdleReward, dailyRewardState, idleRewardState } from '../src/rewards.js'

class MemoryRepo {
  constructor () {
    this.states = new Map()
    this.balances = new Map()
    this.user = { id: 1, chapter_progression: 0 }
  }

  tx (fn) { return fn() }
  userById () { return this.user }

  stateKey (userId, namespace, key) { return `${userId}:${namespace}:${key}` }
  getState (userId, namespace, key, fallback = null) {
    return this.states.has(this.stateKey(userId, namespace, key))
      ? this.states.get(this.stateKey(userId, namespace, key))
      : fallback
  }
  setState (userId, namespace, key, value) {
    this.states.set(this.stateKey(userId, namespace, key), structuredClone(value))
  }

  balance (userId, rid) { return this.balances.get(`${userId}:${rid}`) || 0 }
  addCurrency (userId, rid, delta) {
    const key = `${userId}:${rid}`
    const next = this.balance(userId, rid) + delta
    if (next < 0) throw new Error('negative balance')
    this.balances.set(key, next)
    return next
  }

  energy () { return null }
  setEnergy () { throw new Error('not expected') }
  addCosmetic () { throw new Error('not expected') }
  addEntitlement () { throw new Error('not expected') }
  addItem () { throw new Error('not expected') }
}

const coins = { id: 100, rid: 100, tag: 'coins', category_id: 1 }
const runtime = {
  revival: {},
  gameData: {
    resources: [coins],
    daily_rewards: {
      days: [
        { resources: [{ resource: 'coins', amount: 25 }] },
        { resources: [{ resource: 'coins', amount: 50 }] }
      ]
    },
    idle_reward: {
      generation_period: 60,
      max_generation_periods: 10,
      chapter_idle_generation: [
        { chapter_progress: 0, idle_generation: [{ resource: 'coins', amount: 3 }] }
      ]
    }
  },
  index: {
    byTag: new Map([['coins', 100]]),
    byId: new Map([[100, coins]])
  }
}

const repo = new MemoryRepo()
const dayOne = 2_000_000_000

const before = dailyRewardState(repo, 1, runtime, dayOne)
assert.equal(before.claimable, true)
assert.equal(before.state.day, 1)

const first = claimDailyReward(repo, 1, runtime, dayOne)
assert.equal(first.ok, true)
assert.equal(first.claimed_day, 1)
assert.deepEqual(first.resources, [{ rid: 100, amount: 25 }])
assert.equal(repo.balance(1, 100), 25)

const duplicate = claimDailyReward(repo, 1, runtime, dayOne + 30)
assert.deepEqual(duplicate, { ok: false, reason: 'already-claimed' })
assert.equal(repo.balance(1, 100), 25)

const second = claimDailyReward(repo, 1, runtime, dayOne + 86400)
assert.equal(second.ok, true)
assert.equal(second.claimed_day, 2)
assert.equal(repo.balance(1, 100), 75)
assert.equal(dailyRewardState(repo, 1, runtime, dayOne + 86401).state.day, 1)

const idleInitial = idleRewardState(repo, 1, runtime, dayOne)
assert.equal(idleInitial.claimable_periods, 0)

const idle = claimIdleReward(repo, 1, runtime, dayOne + 305)
assert.equal(idle.ok, true)
assert.equal(idle.periods, 5)
assert.equal(repo.balance(1, 100), 90)

const idleAfter = idleRewardState(repo, 1, runtime, dayOne + 305)
assert.equal(idleAfter.claimable_periods, 0)

const capped = claimIdleReward(repo, 1, runtime, dayOne + 60 * 30)
assert.equal(capped.ok, true)
assert.equal(capped.periods, 10)
assert.equal(repo.balance(1, 100), 120)

console.log('Mighty DOOM Revival rewards test: PASS')
