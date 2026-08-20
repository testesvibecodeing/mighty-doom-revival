import assert from 'node:assert/strict'

import { chapterProgressionWire, handleChapterRequest } from '../src/chapters.js'
import { stripNulls } from '../src/wire.js'

// Dataset sintético — mesmos números do capture_protocol_fixtures.mjs.
const coins = { id: 100, tag: 'coins', category_id: 1 }
const runtime = {
  gameData: {
    resources: [coins],
    chapter_mode: {
      chapters: [{
        id: 101,
        vip_entitlement_id: 700,
        stage_rewards: [
          { stage: 1, resources: [{ rid: 100, amount: 10 }], vip_resources: [{ rid: 100, amount: 20 }] },
          { stage: 2, resources: [{ rid: 100, amount: 15 }], vip_resources: [{ rid: 100, amount: 25 }] },
          { stage: 3, resources: [{ rid: 100, amount: 20 }], vip_resources: [{ rid: 100, amount: 30 }] }
        ],
        challenges: [{ id: 1, completion_reward: [{ rid: 100, amount: 100 }] }]
      }]
    }
  },
  index: {
    byId: new Map([[100, coins]]),
    byTag: new Map([['coins', 100]])
  }
}
const runtimeNoConfig = {
  gameData: { resources: [coins], chapter_mode: { chapters: [{ id: 101 }] } },
  index: runtime.index
}

class FakeRepo {
  constructor () {
    this.attemptCount = 0
    this.chapterProgression = 0
    this.itemsList = [{ id: 50, rid: 900, kind: 'equipment', level: 1, tier: null, metadata_json: '{}' }]
    this.entitlementsList = [{ rid: 700 }]
    this.balances = new Map()
    this.state = new Map()
    this.nextItemId = 50
  }

  tx (fn) {
    const snapshot = JSON.parse(JSON.stringify({
      items: this.itemsList, balances: [...this.balances], state: [...this.state]
    }))
    try {
      return fn()
    } catch (error) {
      this.itemsList = snapshot.items
      this.balances = new Map(snapshot.balances)
      this.state = new Map(snapshot.state)
      throw error
    }
  }

  incrementAttemptCount () { this.attemptCount += 1; return this.attemptCount }
  setChapterProgression (_, value) { this.chapterProgression = value; return value }
  items () { return this.itemsList }
  deleteItem (_, id) {
    const index = this.itemsList.findIndex(item => item.id === id)
    if (index === -1) return false
    this.itemsList.splice(index, 1)
    return true
  }
  entitlements () { return this.entitlementsList }
  balance (_, rid) { return this.balances.get(rid) || 0 }
  addCurrency (_, rid, delta) {
    const next = this.balance(1, rid) + delta
    if (next < 0) throw new Error('funds')
    this.balances.set(rid, next)
    return next
  }
  getState (_, namespace, key, fallback = null) {
    const k = `${namespace}:${key}`
    return this.state.has(k) ? JSON.parse(JSON.stringify(this.state.get(k))) : fallback
  }
  setState (_, namespace, key, value) { this.state.set(`${namespace}:${key}`, value) }
}

const UID = 1

// StartChapter(chapterId, gear, weapons, challengeId) -> {attempt} apenas.
let repo = new FakeRepo()
let result = handleChapterRequest('/game/chapters/start', { chapter_id: 101, challenge_id: 1, gear: [], weapons: [] }, UID, repo, runtime)
assert.equal(result.data.attempt.chapter_id, 101)
assert.equal(result.data.attempt.challenge_id, 1)
assert.equal(Object.keys(result.data).length, 1, 'StartChapterResponse tem só attempt')
assert.equal(repo.attemptCount, 1)

// UpdateChapter(progress) -> {min_update_time} apenas. O campo e nullable no
// DTO e o null SOBREVIVEU ao cliente real, entao ele e preservado no wire: o
// `stripNulls` tem escopo estreito (so valor nao-finito) justamente para nao
// sumir com campo referencial que o contrato admite.
result = handleChapterRequest('/game/chapters/update', { progress: { stage: 3, state: 0 } }, UID, repo, runtime)
assert.ok('min_update_time' in result.data, 'o handler continua declarando o campo')
assert.equal(result.data.min_update_time, null)
assert.equal(Object.keys(result.data).length, 1)
assert.deepEqual(stripNulls(result.data), { min_update_time: null },
  'null explicito e preservado; quem some do wire e apenas NaN/Infinity')

// Revive() -> sem DTO dedicado: envelope puro.
result = handleChapterRequest('/game/chapters/revive', {}, UID, repo, runtime)
assert.equal(Object.keys(result.data).length, 0)
assert.equal(chapterProgressionWire(repo, UID).current_run.revives, 1)

// RedeemVoucher(voucherId): consome o item e registra na run.
result = handleChapterRequest('/game/chapters/redeem-voucher', { voucher_id: 900 }, UID, repo, runtime)
assert.equal(Object.keys(result.data).length, 0)
assert.equal(repo.itemsList.length, 0, 'voucher consumido')
const run = chapterProgressionWire(repo, UID).current_run
assert.equal(run.revives, 2)
assert.deepEqual(run.redeemed_vouchers, [900])

result = handleChapterRequest('/game/chapters/redeem-voucher', { voucher_id: 900 }, UID, repo, runtime)
assert.equal(result.error[2].reason, 'voucher-not-owned')

// AdRevive/AdAbilityReroll(rewardTokenId): token emitido pelo fluxo de ads.
const now = Math.floor(Date.now() / 1000)
repo.setState(UID, 'ads', 'reward_tokens', [
  { id: 1, reward_type: 'revive', issued_epoch: now, expire_epoch: now + 600 },
  { id: 2, reward_type: 'ability_reroll', issued_epoch: now, expire_epoch: now + 600 },
  { id: 3, reward_type: 'revive', issued_epoch: now, expire_epoch: now - 1 }
])
result = handleChapterRequest('/game/chapters/ad-revive', { reward_token_id: 999 }, UID, repo, runtime)
assert.equal(result.error[2].reason, 'reward-token-not-found')
result = handleChapterRequest('/game/chapters/ad-revive', { reward_token_id: 2 }, UID, repo, runtime)
assert.equal(result.error[2].reason, 'reward-token-type-mismatch')
result = handleChapterRequest('/game/chapters/ad-revive', { reward_token_id: 3 }, UID, repo, runtime)
assert.equal(result.error[2].reason, 'reward-token-expired')
result = handleChapterRequest('/game/chapters/ad-revive', { reward_token_id: 1 }, UID, repo, runtime)
assert.equal(Object.keys(result.data).length, 0)
assert.equal(chapterProgressionWire(repo, UID).current_run.revives, 3)
assert.equal(repo.getState(UID, 'ads', 'reward_tokens', []).length, 2, 'token consumido')

result = handleChapterRequest('/game/chapters/ad-ability-reroll', { reward_token_id: 2 }, UID, repo, runtime)
assert.equal(Object.keys(result.data).length, 0)
assert.equal(chapterProgressionWire(repo, UID).current_run.ability_rerolls, 1)

// EndChapter(progress) -> {loot} apenas; stats gravadas.
result = handleChapterRequest('/game/chapters/end', { progress: { stage: 5, state: 1, loot: [{ rid: 100, amount: 5 }] } }, UID, repo, runtime)
assert.deepEqual(result.data.loot, [{ rid: 100, amount: 5 }])
assert.equal(Object.keys(result.data).length, 1)
const ended = chapterProgressionWire(repo, UID)
assert.equal(ended.current_run, null)
const chapter101 = ended.chapters.find(row => row.chapter === 101)
assert.equal(chapter101.best_stage, 5)
assert.equal(chapter101.attempts, 1)
assert.equal(chapter101.wins, 1)
assert.equal(ended.challenges[0].wins, 1)

// ClaimStageReward/ClaimRewards(chapterId) -> {stage, resources} reais.
result = handleChapterRequest('/game/chapters/claim-stage-reward', { chapter_id: 101 }, UID, repo, runtime)
assert.equal(result.data.stage, 1)
assert.deepEqual(result.data.resources, [{ rid: 100, amount: 10 }])
result = handleChapterRequest('/game/chapters/claim-rewards', { chapter_id: 101 }, UID, repo, runtime)
assert.equal(result.data.stage, 2)
// sem config: erro explícito de estado, nunca resources vazio fingindo sucesso
result = handleChapterRequest('/game/chapters/claim-stage-reward', { chapter_id: 102 }, UID, repo, runtime)
assert.equal(result.error[1], 2200)
result = handleChapterRequest('/game/chapters/claim-stage-reward', { chapter_id: 101 }, UID, repo, runtimeNoConfig)
assert.equal(result.error[1], 2300)
assert.equal(result.error[2].reason, 'stage-rewards-config-missing')

// estágio ainda não completado
const fresh = new FakeRepo()
handleChapterRequest('/game/chapters/start', { chapter_id: 101 }, UID, fresh, runtime)
handleChapterRequest('/game/chapters/end', { progress: { stage: 1, state: 1 } }, UID, fresh, runtime)
result = handleChapterRequest('/game/chapters/claim-stage-reward', { chapter_id: 101 }, UID, fresh, runtime)
assert.equal(result.data.stage, 1)
result = handleChapterRequest('/game/chapters/claim-stage-reward', { chapter_id: 101 }, UID, fresh, runtime)
assert.equal(result.error[2].reason, 'stage-not-completed')

// ClaimVipReward(chapterId): exige entitlement + estágio completado.
result = handleChapterRequest('/game/chapters/claim-vip-reward', { chapter_id: 101 }, UID, fresh, runtime)
assert.equal(result.data.stage, 1)
// resources[].amount é o saldo pós-concessão (mesmo wire do daily-rewards)
assert.deepEqual(result.data.resources, [{ rid: 100, amount: 30 }])
const noVip = new FakeRepo()
noVip.entitlementsList = []
handleChapterRequest('/game/chapters/start', { chapter_id: 101 }, UID, noVip, runtime)
handleChapterRequest('/game/chapters/end', { progress: { stage: 2, state: 1 } }, UID, noVip, runtime)
result = handleChapterRequest('/game/chapters/claim-vip-reward', { chapter_id: 101 }, UID, noVip, runtime)
assert.equal(result.error[1], 2300)
assert.equal(result.error[2].reason, 'vip-not-entitled')

// ClaimVipRewardsChapter(chapterId): todos os estágios VIP pendentes.
// saldo 35 (10+15 dos claims normais) + 20/25/30 dos VIP = 45/70/100
result = handleChapterRequest('/game/chapters/claim-vip-rewards-chapter', { chapter_id: 101 }, UID, repo, runtime)
assert.equal(result.data.stage, 3)
assert.deepEqual(result.data.resources, [{ rid: 100, amount: 45 }, { rid: 100, amount: 70 }, { rid: 100, amount: 100 }])

// ClaimVipRewardsAll(): sem pendentes -> estado explícito.
result = handleChapterRequest('/game/chapters/claim-vip-rewards-all', {}, UID, repo, runtime)
assert.equal(result.error[1], 2300)
assert.equal(result.error[2].reason, 'vip-reward-already-claimed')
const allRepo = new FakeRepo()
handleChapterRequest('/game/chapters/start', { chapter_id: 101 }, UID, allRepo, runtime)
handleChapterRequest('/game/chapters/end', { progress: { stage: 3, state: 1 } }, UID, allRepo, runtime)
result = handleChapterRequest('/game/chapters/claim-vip-rewards-all', {}, UID, allRepo, runtime)
assert.deepEqual(result.data.stages, [{ chapter_id: 101, stage: 1 }, { chapter_id: 101, stage: 2 }, { chapter_id: 101, stage: 3 }])
assert.equal(result.data.resources.length, 3)

// ClaimChallengeReward(chapterId, challengeId).
result = handleChapterRequest('/game/chapters/claim-challenge-reward', { chapter_id: 101, challenge_id: 1 }, UID, repo, runtime)
assert.deepEqual(result.data.resources, [{ rid: 100, amount: 200 }])
result = handleChapterRequest('/game/chapters/claim-challenge-reward', { chapter_id: 101, challenge_id: 1 }, UID, repo, runtime)
assert.equal(result.error[2].reason, 'challenge-reward-already-claimed')
result = handleChapterRequest('/game/chapters/claim-challenge-reward', { chapter_id: 101, challenge_id: 7 }, UID, repo, runtime)
assert.equal(result.error[2].reason, 'challenge-config-missing')

// vitória sem desafio: nada a reivindicar
const noChallenge = new FakeRepo()
handleChapterRequest('/game/chapters/start', { chapter_id: 101 }, UID, noChallenge, runtime)
handleChapterRequest('/game/chapters/end', { progress: { stage: 1, state: 1 } }, UID, noChallenge, runtime)
result = handleChapterRequest('/game/chapters/claim-challenge-reward', { chapter_id: 101, challenge_id: 1 }, UID, noChallenge, runtime)
assert.equal(result.error[2].reason, 'challenge-not-completed')

// run ativa: estado inválido agora na faixa 2300 (ResponseCode: estado).
handleChapterRequest('/game/chapters/start', { chapter_id: 101 }, UID, repo, runtime)
result = handleChapterRequest('/game/chapters/start', { chapter_id: 101 }, UID, repo, runtime)
assert.equal(result.error[1], 2300)
result = handleChapterRequest('/game/chapters/update', {}, UID, new FakeRepo(), runtime)
assert.equal(result.error[2].reason, 'no-active-run')

console.log('chapters regression suite passed')
