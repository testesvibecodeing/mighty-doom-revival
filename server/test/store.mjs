import assert from 'node:assert/strict'
import { activePacks, packToStoreItem, purchasePack } from '../src/store.js'

const runtime = {
  packs: [],
  index: {
    byTag: new Map([
      ['currency_coins', 101],
      ['currency_crystals', 102],
      ['reward_tokens', 201]
    ]),
    byId: new Map()
  }
}

function makeRepo (balances = {}) {
  const state = new Map(Object.entries(balances).map(([rid, amount]) => [Number(rid), amount]))
  const purchases = new Map()
  return {
    tx (fn) { return fn() },
    balance (_userId, rid) { return state.get(rid) || 0 },
    addCurrency (_userId, rid, amount) { state.set(rid, (state.get(rid) || 0) + amount) },
    purchaseCount (userId, itemId, bucket) { return purchases.get(`${userId}:${itemId}:${bucket}`) || 0 },
    incrementPurchase (userId, itemId, bucket) {
      const key = `${userId}:${itemId}:${bucket}`
      purchases.set(key, (purchases.get(key) || 0) + 1)
    },
    getBalance (rid) { return state.get(rid) || 0 }
  }
}

runtime.packs = [
  {
    id: 900001,
    tag: 'revival_daily_tokens',
    active: true,
    cost: [{ resource: 'currency_coins', kind: 'currency', amount: 250 }],
    contents: [{ resource: 'reward_tokens', kind: 'currency', amount: 10 }],
    quota: { period: 'daily', max: 1 }
  },
  { id: 900002, tag: 'disabled', active: false, cost: [], contents: [] }
]

assert.deepEqual(activePacks(runtime).map(x => x.id), [900001])
const wire = packToStoreItem(runtime.packs[0], runtime)
assert.equal(wire.cost[0].rid, 101)
assert.equal(wire.cost[0].amount, 250)
assert.equal(wire.contents.resources[0].rid, 201)

for (const forbidden of [
  { price: 1 },
  { iap: true },
  { real_money: true }
]) {
  assert.throws(() => packToStoreItem({ id: 1, cost: [], contents: [], ...forbidden }, runtime), /preço\/IAP real/)
}

const repo = makeRepo({ 101: 500 })
let result = purchasePack(repo, 'player-1', 900001, runtime)
assert.equal(result.ok, true)
assert.equal(repo.getBalance(101), 250)
assert.equal(repo.getBalance(201), 10)

result = purchasePack(repo, 'player-1', 900001, runtime)
assert.deepEqual(result, { ok: false, reason: 'quota' })
assert.equal(repo.getBalance(101), 250)

const poorRepo = makeRepo({ 101: 249 })
result = purchasePack(poorRepo, 'player-2', 900001, runtime)
assert.deepEqual(result, { ok: false, reason: 'funds' })
assert.equal(poorRepo.getBalance(101), 249)

runtime.packs.push({
  id: 900003,
  tag: 'invalid_non_currency_cost',
  active: true,
  cost: [{ resource: 'currency_coins', kind: 'iap', amount: 1 }],
  contents: []
})
result = purchasePack(makeRepo({ 101: 999 }), 'player-3', 900003, runtime)
assert.deepEqual(result, { ok: false, reason: 'invalid-cost' })

console.log('store tests: ok')
