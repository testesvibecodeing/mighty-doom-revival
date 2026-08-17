import assert from 'node:assert/strict'

import { handleProgressionRequest, talentsWire } from '../src/progression.js'

class FakeRepo {
  constructor () {
    this.user = { id: 1, level: 10 }
    this.itemsMap = new Map([
      [7, { id: 7, rid: 200, kind: 'weapon', level: 1, tier: 1, metadata_json: '{}' }],
      [8, { id: 8, rid: 210, kind: 'slayer', level: 1, tier: null, metadata_json: '{}' }],
      [9, { id: 9, rid: 200, kind: 'weapon', level: 1, tier: 1, metadata_json: '{}' }],
      [10, { id: 10, rid: 200, kind: 'weapon', level: 1, tier: 1, metadata_json: '{}' }]
    ])
    this.balances = new Map([[1, 1000], [2, 100]])
    this.state = new Map()
    this.cosmeticsList = [{ rid: 800 }]
    this.nextItemId = Math.max(...this.itemsMap.keys())
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
  addItem (_, resource) {
    // AUTOINCREMENT monotônico como o SQLite real: nunca reusa id deletado.
    const id = ++this.nextItemId
    this.itemsMap.set(id, {
      id, rid: resource.rid, kind: resource.kind || 'item',
      level: resource.level ?? 1, tier: resource.tier ?? null, metadata_json: '{}'
    })
    return id
  }
  deleteItem (_, id) { return this.itemsMap.delete(id) }
  updateItemMetadata (_, id, metadata) {
    const item = this.itemsMap.get(id)
    if (!item) return false
    item.metadata_json = JSON.stringify(metadata)
    return true
  }
  cosmetics () { return this.cosmeticsList }
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

// Contrato extraído do global-metadata.dat v29: GearApi.Upgrade(gearUid) ->
// POST game/gear/upgrade {gear_uid}; resposta {gear, gear_upgrade_sequence_id}.
let result = handleProgressionRequest('/game/gear/upgrade', { gear_uid: 7 }, 1, repo, runtime)
assert.equal(result.data.gear.level, 2)
assert.equal(result.data.gear.uid, 7)
assert.equal(result.data.gear_upgrade_sequence_id, 1)
assert.equal(repo.balance(1, 1), 900)

// MultiUpgrade(gearUid, levelsToUpgrade) -> {gear_uid, levels_to_upgrade}
result = handleProgressionRequest('/game/gear/multi-upgrade', { gear_uid: 7, levels_to_upgrade: 1 }, 1, repo, runtime)
assert.equal(result.data.gear.level, 3)
assert.equal(result.data.gear_upgrade_sequence_id, 2)
assert.equal(repo.balance(1, 1), 700)

result = handleProgressionRequest('/game/gear/upgrade', { gear_uid: 7 }, 1, repo, runtime)
assert.equal(result.error[2].reason, 'level-cap')
assert.equal(repo.balance(1, 1), 700)

// SlayerApi.Upgrade(slayerUid) -> {slayer_uid}; resposta {slayer}
result = handleProgressionRequest('/game/slayers/upgrade', { slayer_uid: 8 }, 1, repo, runtime)
assert.equal(result.data.slayer.level, 2)
assert.equal(repo.balance(1, 1), 625)
assert.equal(repo.balance(1, 2), 95)

// Fuse(inputUids) -> {input_uids}; exige gear_fusion no game-data (erro
// explícito de estado, nunca payload vazio fingindo sucesso).
const fusionRuntime = {
  ...runtime,
  gameData: { ...runtime.gameData, gear_fusion: { input_count: 2, tier_gain: 1 } }
}
result = handleProgressionRequest('/game/gear/fuse', { input_uids: [9, 10] }, 1, repo, runtime)
assert.equal(result.error[1], 2300)
assert.equal(result.error[2].reason, 'fusion-config-missing')
assert.ok(repo.itemById(1, 9) && repo.itemById(1, 10), 'sem config os itens permanecem')

result = handleProgressionRequest('/game/gear/fuse', { input_uids: [9, 10] }, 1, repo, fusionRuntime)
assert.equal(result.data.gear.tier, 2)
assert.equal(result.data.gear.rid, 200)
assert.equal(repo.itemById(1, 9), null)
assert.equal(repo.itemById(1, 10), null)

result = handleProgressionRequest('/game/gear/fuse', { input_uids: [7] }, 1, repo, fusionRuntime)
assert.equal(result.error[2].reason, 'insufficient-inputs')

// Dismantle(gearUid) -> {gear_uid}; refund vem de dismantle.tiers no game-data.
const dismantleRuntime = {
  ...runtime,
  gameData: { ...runtime.gameData, dismantle: { tiers: { 1: [{ resource: 'coins', amount: 50 }] } } }
}
result = handleProgressionRequest('/game/gear/dismantle', { gear_uid: 7 }, 1, repo, runtime)
assert.equal(result.error[1], 2300)
assert.equal(result.error[2].reason, 'dismantle-config-missing')
assert.ok(repo.itemById(1, 7), 'sem config o item permanece')

result = handleProgressionRequest('/game/gear/dismantle', { gear_uid: 7 }, 1, repo, dismantleRuntime)
assert.equal(result.data.gear.uid, 7)
assert.deepEqual(result.data.resources, [{ rid: 1, amount: 50 }])
assert.equal(repo.itemById(1, 7), null)
assert.equal(repo.balance(1, 1), 675)

// ApplyCosmetic(gearUid|slayerUid, cosmeticId) -> {gear_uid|slayer_uid, cosmetic_id}
const cosmeticRepo = new FakeRepo()
result = handleProgressionRequest('/game/gear/apply-cosmetic', { gear_uid: 7, cosmetic_id: 800 }, 1, cosmeticRepo, runtime)
assert.equal(result.data.gear.cosmetic_id, 800)
assert.equal(result.data.gear.uid, 7)

result = handleProgressionRequest('/game/gear/apply-cosmetic', { gear_uid: 7, cosmetic_id: 999 }, 1, cosmeticRepo, runtime)
assert.equal(result.error[2].reason, 'cosmetic-not-owned')

result = handleProgressionRequest('/game/slayers/apply-cosmetic', { slayer_uid: 8, cosmetic_id: 800 }, 1, cosmeticRepo, runtime)
assert.equal(result.data.slayer.cosmetic_id, 800)

result = handleProgressionRequest('/game/slayers/apply-cosmetic', { slayer_uid: 7, cosmetic_id: 800 }, 1, cosmeticRepo, runtime)
assert.equal(result.error[2].reason, 'not-slayer')

result = handleProgressionRequest('/game/talents/buy', { talent_id: 301 }, 1, repo, runtime)
assert.equal(result.error[2].reason, 'prerequisite')
assert.equal(repo.balance(1, 1), 675)

result = handleProgressionRequest('/game/talents/buy', { talent_id: 300 }, 1, repo, runtime)
assert.equal(result.data.talent, 300)
assert.equal(repo.balance(1, 1), 625)
assert.deepEqual(talentsWire(repo, 1).talents, [300])

result = handleProgressionRequest('/game/talents/buy', { talent_id: 301 }, 1, repo, runtime)
assert.equal(result.data.talent, 301)
assert.equal(repo.balance(1, 1), 565)
assert.deepEqual(talentsWire(repo, 1).talents, [300, 301])

result = handleProgressionRequest('/game/talents/buy', { talent_id: 300 }, 1, repo, runtime)
assert.equal(result.error[2].reason, 'already-owned')
assert.equal(repo.balance(1, 1), 565)

console.log('progression regression suite passed')
