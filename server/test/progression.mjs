import assert from 'node:assert/strict'

import { handleProgressionRequest, talentsWire } from '../src/progression.js'

class FakeRepo {
  constructor () {
    this.user = { id: 1, level: 10 }
    this.itemsMap = new Map([
      [7, { id: 7, rid: 200, kind: 'weapon', level: 1, tier: 1 }],
      [8, { id: 8, rid: 210, kind: 'slayer', level: 1, tier: null }]
    ])
    this.balances = new Map([[1, 1000], [2, 100]])
    this.state = new Map()
  }

  tx (fn) {
    const itemSnapshot = new Map([...this.itemsMap].map(([id, item]) => [id, { ...item }]))
    const balanceSnapshot = new Map(this.balances)
    const stateSnapshot = new Map(this.state)
    try {
      return fn()
    } catch (error) {
      this.itemsMap = itemSnapshot
      this.balances = balanceSnapshot
      this.state = stateSnapshot
      throw error
    }
  }

  userById () { return this.user }
  itemById (_, id) { return this.itemsMap.has(id) ? { ...this.itemsMap.get(id) } : null }
  updateItemLevel (_, id, level) { this.itemsMap.get(id).level = level }
  balance (_, rid) { return this.balances.get(rid) || 0 }
  addCurrency (_, rid, delta) {
    const next = this.balance(1, rid) + delta
    if (next < 0) throw new Error('funds')
    this.balances.set(rid, next)
    return next
  }
  getState (_, namespace, key, fallback) {
    const stateKey = `${namespace}:${key}`
    return this.state.has(stateKey) ? this.state.get(stateKey) : fallback
  }
  setState (_, namespace, key, value) { this.state.set(`${namespace}:${key}`, value) }
}

const runtime = {
  gameData: {
    weapons: [{
      id: 200,
      max_level: 3,
      upgrade_costs: [
        { level: 2, cost: [{ resource: 'coins', amount: 100 }] },
        { level: 3, cost: [{ resource: 'coins', amount: 200 }] }
      ]
    }],
    slayers: [{
      id: 210,
      max_level: 10,
      upgrade_costs: [{ level: 2, cost: [{ resource: 'coins', amount: 75 }, { resource: 'argent', amount: 5 }] }]
    }],
    talents: {
      talents: [
        { id: 300, cost: [{ resource: 'coins', amount: 50 }] },
        { id: 301, prerequisites: [300], cost: [{ resource: 'coins', amount: 60 }] }
      ]
    }
  },
  index: {
    byId: new Map(),
    byTag: new Map([['coins', 1], ['argent', 2]])
  }
}

const repo = new FakeRepo()

let result = handleProgressionRequest('/game/gear/upgrade', { item: 7 }, 1, repo, runtime)
assert.equal(result.data.item.level, 2)
assert.equal(repo.balance(1, 1), 900)

result = handleProgressionRequest('/game/gear/multi-upgrade', { item: 7, target_level: 3 }, 1, repo, runtime)
assert.equal(result.data.item.level, 3)
assert.equal(repo.balance(1, 1), 700)

result = handleProgressionRequest('/game/gear/upgrade', { item: 7, target_level: 4 }, 1, repo, runtime)
assert.equal(result.error[2].reason, 'level-cap')
assert.equal(repo.balance(1, 1), 700)

result = handleProgressionRequest('/game/slayers/upgrade', { slayer: 8 }, 1, repo, runtime)
assert.equal(result.data.item.level, 2)
assert.equal(repo.balance(1, 1), 625)
assert.equal(repo.balance(1, 2), 95)

result = handleProgressionRequest('/game/talents/buy', { talent: 301 }, 1, repo, runtime)
assert.equal(result.error[2].reason, 'prerequisite')
assert.equal(repo.balance(1, 1), 625)

result = handleProgressionRequest('/game/talents/buy', { talent: 300 }, 1, repo, runtime)
assert.equal(result.data.talent, 300)
assert.equal(repo.balance(1, 1), 575)
assert.deepEqual(talentsWire(repo, 1).talents, [300])

result = handleProgressionRequest('/game/talents/buy', { talent: 301 }, 1, repo, runtime)
assert.equal(result.data.talent, 301)
assert.equal(repo.balance(1, 1), 515)
assert.deepEqual(talentsWire(repo, 1).talents, [300, 301])

result = handleProgressionRequest('/game/talents/buy', { talent: 300 }, 1, repo, runtime)
assert.equal(result.error[2].reason, 'already-owned')
assert.equal(repo.balance(1, 1), 515)

console.log('progression regression suite passed')
