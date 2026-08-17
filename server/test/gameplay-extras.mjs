import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'

import { Repository } from '../src/db.js'
import { findAdRewardToken } from '../src/ad-tokens.js'
import { boostIdleReward } from '../src/rewards.js'
import { handleArmoryRequest } from '../src/armory.js'
import {
  activatedOfferWires,
  activateStoreOffer,
  adPurchasePack,
  storeItemsWire
} from '../src/store.js'

const coins = { id: 100, tag: 'coins', category_id: 1 }
const gems = { id: 101, tag: 'gems', category_id: 1 }
const runtime = {
  gameData: {
    resources: [coins, gems],
    idle_reward: {
      generation_period: 60,
      chapter_idle_generation: [{ chapter_progress: 0, idle_generation: [{ rid: 100, amount: 1 }] }],
      boost: { multiplier: 2, cooldown: 3600 }
    },
    armory: {
      unlock_level: 1,
      upgrades: [
        {
          id: 1,
          tag: 'damage',
          levels: [
            { cost: [{ rid: 100, amount: 25 }], chapter_progress: 0 },
            { cost: [{ rid: 100, amount: 20 }], chapter_progress: 2 }
          ]
        },
        { id: 2, tag: 'locked', availability: 0, levels: [{ cost: [] }] }
      ]
    },
    store: {
      offers: [
        { id: 5, item_id: 900100, allowed_purchases: 1, purchase_amount: 100 },
        { id: 6, item_id: 900100, targeted_offer_type: 1 }
      ]
    }
  },
  packs: [
    { id: 900100, tag: 'coin_pack', active: true, cost: [{ resource: 'coins', amount: 50 }], contents: [{ resource: 'coins', kind: 'currency', amount: 100 }] },
    { id: 900200, tag: 'ad_crate', active: true, ad: true, cost: [], contents: [{ resource: 'gems', kind: 'currency', amount: 5 }] }
  ],
  revival: {},
  index: { byId: new Map([[100, coins], [101, gems]]), byTag: new Map([['coins', 100], ['gems', 101]]) }
}

const dir = mkdtempSync(resolve(tmpdir(), 'mighty-doom-extras-'))
const dbPath = resolve(dir, 'extras.sqlite3')
const repo = new Repository(dbPath)

// Boost concede períodos pendentes × multiplicador; last_claim avança.
function advanceIdle (repo, userId, seconds) {
  const current = Number(repo.getState(userId, 'idle-rewards', 'last_claim', 0) || 0)
  repo.setState(userId, 'idle-rewards', 'last_claim', current - seconds)
}

try {
  const { user } = repo.createUser()
  const UID = user.id

  // ---- boost / ad-boost (IdleRewardApi) ----
  assert.equal(boostIdleReward(repo, UID, runtime).reason, 'not-ready', 'sem períodos não boosta')
  advanceIdle(repo, UID, 180) // 3 períodos de 60s
  let result = boostIdleReward(repo, UID, runtime)
  assert.equal(result.ok, true)
  assert.equal(result.multiplier, 2)
  assert.equal(repo.balance(UID, 100), 6, '3 períodos x 1 moeda x 2')
  assert.equal(boostIdleReward(repo, UID, runtime).reason, 'not-ready', 'last_claim avançou')
  advanceIdle(repo, UID, 120) // 2 períodos
  assert.equal(boostIdleReward(repo, UID, runtime).reason, 'boost-not-ready', 'cooldown do boost grátis')

  // ad-boost: a validação de tipo é o findAdRewardToken compartilhado (o que a
  // rota HTTP faz) e o consumo acontece dentro do tx do boost.
  repo.setState(UID, 'ads', 'reward_tokens', [
    { id: 30, reward_type: 'idle_reward_boost', issued_epoch: 1, expire_epoch: 1 },
    { id: 31, reward_type: 'idle_reward_boost', issued_epoch: 1, expire_epoch: 4102444800 },
    { id: 32, reward_type: 'revive' }
  ])
  const wrong = findAdRewardToken(repo, UID, 32, 'idle_reward_boost')
  assert.equal(wrong.error[2].reason, 'reward-token-type-mismatch')
  const expired = findAdRewardToken(repo, UID, 30, 'idle_reward_boost')
  assert.equal(expired.error[2].reason, 'reward-token-expired')
  const found = findAdRewardToken(repo, UID, 31, 'idle_reward_boost')
  assert.equal(found.token.id, 31)
  result = boostIdleReward(repo, UID, runtime, undefined, { tokenId: 31, tokens: found.tokens })
  assert.equal(result.ok, true)
  assert.equal(repo.balance(UID, 100), 10, '2 períodos x 1 x 2')
  assert.deepEqual(repo.getState(UID, 'ads', 'reward_tokens', []).map(t => t.id), [30, 32], 'só o token usado é consumido')

  // ---- armory (ArmoryApi) ----
  let response = handleArmoryRequest('/game/armory/get', {}, UID, repo, runtime)
  assert.deepEqual(response.data.upgrades, [{ id: 1, level: 0 }, { id: 2, level: 0 }])
  assert.equal(handleArmoryRequest('/game/armory/upgrade', { id: 99, level: 1 }, UID, repo, runtime).error[2].reason, 'upgrade-not-found')
  assert.equal(handleArmoryRequest('/game/armory/upgrade', { id: 2, level: 1 }, UID, repo, runtime).error[2].reason, 'upgrade-unavailable')
  assert.equal(handleArmoryRequest('/game/armory/upgrade', { id: 1, level: 3 }, UID, repo, runtime).error[2].reason, 'max-level-reached')
  assert.equal(handleArmoryRequest('/game/armory/upgrade', { id: 1, level: 1 }, UID, repo, runtime).error[2].reason, 'insufficient-currency')
  repo.addCurrency(UID, 100, 100)
  response = handleArmoryRequest('/game/armory/upgrade', { id: 1, level: 1 }, UID, repo, runtime)
  assert.equal(Object.keys(response.data).length, 0, 'Upgrade sem DTO -> envelope puro')
  assert.equal(repo.balance(UID, 100), 85)
  assert.equal(handleArmoryRequest('/game/armory/upgrade', { id: 1, level: 1 }, UID, repo, runtime).error[2].reason, 'invalid-level')
  assert.equal(handleArmoryRequest('/game/armory/upgrade', { id: 1, level: 2 }, UID, repo, runtime).error[2].reason, 'chapter-progress-required')
  response = handleArmoryRequest('/game/armory/get', {}, UID, repo, runtime)
  assert.deepEqual(response.data.upgrades[0], { id: 1, level: 1 })

  // ---- store (StoreApi) ----
  const items = storeItemsWire(runtime)
  assert.deepEqual(items.store_items.map(item => item.id), [900100])
  assert.deepEqual(items.ad_items.map(item => item.id), [900200])
  assert.deepEqual(items.iap_items, [])

  assert.equal(activateStoreOffer(repo, UID, { offer_id: 9 }, runtime).error[2].reason, 'offer-not-found')
  assert.equal(activateStoreOffer(repo, UID, { offer_id: 6 }, runtime).error[2].reason, 'gear-resource-id-required')
  response = activateStoreOffer(repo, UID, { offer_id: 5 }, runtime)
  assert.equal(Object.keys(response.data).length, 1, 'ActivateOfferResponse só tem offer')
  assert.equal(response.data.offer.id, 5)
  assert.equal(response.data.offer.item_id, 900100)
  assert.equal(response.data.offer.purchase_amount, 100)
  assert.equal(typeof response.data.offer.start_time, 'number')
  assert.deepEqual(activatedOfferWires(repo, UID, runtime).map(offer => offer.id), [5])

  // ad-purchase: só pack de anúncio, com token StoreItemCrate/Gold válido.
  assert.equal(adPurchasePack(repo, UID, { item_id: 900100 }, runtime).error[2].reason, 'not-ad-item')
  assert.equal(adPurchasePack(repo, UID, { item_id: 900200 }, runtime).error[2].reason, 'reward-token-required')
  repo.setState(UID, 'ads', 'reward_tokens', [...repo.getState(UID, 'ads', 'reward_tokens', []), { id: 33, reward_type: 'store_item_gold' }])
  response = adPurchasePack(repo, UID, { item_id: 900200, reward_token_id: 33 }, runtime)
  assert.deepEqual(response.data.resources, [{ rid: 101, amount: 5 }])
  assert.equal(repo.balance(UID, 101), 5)
  assert.equal(adPurchasePack(repo, UID, { item_id: 900200, reward_token_id: 33 }, runtime).error[2].reason, 'reward-token-not-found')

  // persistência: níveis de armory e offers ativados sobrevivem ao restart.
  repo.close()
  const reopened = new Repository(dbPath)
  const armoryAfter = handleArmoryRequest('/game/armory/get', {}, UID, reopened, runtime)
  assert.deepEqual(armoryAfter.data.upgrades[0], { id: 1, level: 1 })
  assert.deepEqual(activatedOfferWires(reopened, UID, runtime).map(offer => offer.id), [5])
  assert.equal(reopened.balance(UID, 100), 85)
  assert.equal(reopened.balance(UID, 101), 5)
  reopened.close()

  console.log('Mighty DOOM Revival gameplay extras test: PASS')
} finally {
  try { repo.close() } catch {}
  rmSync(dir, { recursive: true, force: true })
}
