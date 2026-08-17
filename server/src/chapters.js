import { chaptersList } from './game-data-schema.js'
import { giveGameResource } from './game-data-model.js'

const NS = 'chapters'

// ---- Contrato extraído do global-metadata.dat v29 (2026-08-17) ----
// ChapterModeApi (13 métodos = 13 rotas game/chapters/* do cliente):
//   StartChapter(chapterId, gear, weapons, challengeId)    {chapter_id, gear, weapons, challenge_id}
//   UpdateChapter(progress)                                 {progress}
//   EndChapter(progress)                                   {progress}
//   Revive()                                               {}
//   AdRevive(rewardTokenId)                                {reward_token_id}
//   AdAbilityReroll(rewardTokenId)                         {reward_token_id}
//   RedeemVoucher(voucherId)                               {voucher_id}
//   ClaimStageReward(chapterId)                            {chapter_id}
//   ClaimRewards(chapterId)                                {chapter_id}
//   ClaimVipReward(chapterId)                              {chapter_id}
//   ClaimVipRewardsChapter(chapterId)                      {chapter_id}
//   ClaimVipRewardsAll()                                   {}
//   ClaimChallengeReward(chapterId, challengeId)           {chapter_id, challenge_id}
// Response DTOs (campos confirmados; snake_case do nome C#):
//   StartChapterResponse{attempt}          UpdateChapterResponse{min_update_time}
//   EndChapterResponse{loot}               ClaimStageReward/Rewards/VipReward/
//   VipRewardsChapter{stage, resources}    ClaimVipRewardsAll{stages, resources}
//   ClaimChallengeReward{resources}        Revive/AdRevive/AdAbilityReroll/
//   RedeemVoucher: sem DTO dedicado -> envelope puro {uts, code}
// Config (ChapterInfo/ChapterChallengeInfo/AdRewardToken do DataObjects):
//   chapters[].stage_rewards[{stage, resources, vip_resources}]
//   chapters[].vip_entitlement_id  chapters[].challenges[{id, completion_reward}]
// CONFIRMADO por literal: chapter_id/challenge_id/voucher_id/progress/gear/
// weapons/stage_rewards/loot. A VERIFICAR até captura do cliente:
// reward_token_id (fallback snake) e o shape do array `stages` de
// ClaimVipRewardsAll (aqui: [{chapter_id, stage}] por estágio concedido).

function asInt (value, fallback = null) {
  return Number.isInteger(value) ? value : fallback
}

function asArray (value) {
  return Array.isArray(value) ? value : []
}

function nowSeconds () {
  return Math.floor(Date.now() / 1000)
}

function progressBody (body = {}) {
  return body?.progress && typeof body.progress === 'object' ? body.progress : body
}

function runFromBody (body = {}) {
  const chapter = asInt(body.chapter_id ?? body.chapter ?? body.rid)
  if (chapter === null) return null
  return {
    chapter,
    challenge: asInt(body.challenge_id ?? body.challenge, 0),
    stage: 0,
    started_at: nowSeconds(),
    updated_at: nowSeconds(),
    revives: 0,
    weapons: Array.isArray(body.weapons) ? body.weapons : [],
    gear: Array.isArray(body.gear) ? body.gear : [],
    stats: [],
    payload: null
  }
}

function progression (repo, userId) {
  return repo.getState(userId, NS, 'progression', {
    chapters: [],
    challenges: [],
    current_run: null
  })
}

function saveProgression (repo, userId, value) {
  repo.setState(userId, NS, 'progression', value)
  return value
}

function chapterRow (state, chapterId) {
  let row = state.chapters.find(x => x?.chapter === chapterId || x?.id === chapterId)
  if (!row) {
    row = {
      chapter: chapterId,
      completed: false,
      best_stage: 0,
      attempts: 0,
      wins: 0,
      completed_at: null,
      highest_stage_reward_claimed: 0,
      highest_vip_reward_claimed: 0
    }
    state.chapters.push(row)
  }
  return row
}

function challengeRow (state, chapterId, challengeId) {
  let row = state.challenges.find(x => x?.chapter === chapterId && x?.challenge === challengeId)
  if (!row) {
    row = {
      chapter: chapterId,
      challenge: challengeId,
      attempts: 0,
      wins: 0,
      best_stage: 0,
      completion_reward_claimed: false
    }
    state.challenges.push(row)
  }
  return row
}

function mergeRun (current, body = {}) {
  const progress = progressBody(body)
  const next = { ...current, updated_at: nowSeconds() }
  const stage = asInt(progress.stage ?? progress.stage_index)
  if (stage !== null) next.stage = Math.max(next.stage ?? 0, stage)
  if (Number.isInteger(progress.state)) next.state = progress.state
  if (Array.isArray(progress.stats)) next.stats = progress.stats
  if (Array.isArray(progress.loot)) next.loot = progress.loot
  if (Array.isArray(progress.redeemed_vouchers)) next.redeemed_vouchers = progress.redeemed_vouchers
  if (Array.isArray(progress.battle_pass_points_found)) next.battle_pass_points_found = progress.battle_pass_points_found
  if (progress.checkpoint !== undefined) next.checkpoint = progress.checkpoint
  next.payload = progress
  return next
}

function completedFromProgress (body = {}) {
  const progress = progressBody(body)
  if (Number.isInteger(progress.state)) return progress.state === 1
  return body.completed !== false && body.success !== false
}

function recordCompletion (state, run, body = {}) {
  const completed = completedFromProgress(body)
  const row = chapterRow(state, run.chapter)
  row.attempts = (asInt(row.attempts) ?? 0) + 1
  row.best_stage = Math.max(asInt(row.best_stage) ?? 0, Number(run.stage || 0))
  if (completed) {
    row.completed = true
    row.wins = (asInt(row.wins) ?? 0) + 1
    row.completed_at = nowSeconds()
  }
  if (asInt(run.challenge)) {
    const challenge = challengeRow(state, run.chapter, run.challenge)
    challenge.attempts += 1
    challenge.best_stage = Math.max(challenge.best_stage, Number(run.stage || 0))
    if (completed) challenge.wins += 1
  }
  return { ...state, current_run: null }
}

function completedChapterCount (state) {
  if (!Array.isArray(state?.chapters)) return 0
  return new Set(
    state.chapters
      .filter(row => row?.completed === true)
      .map(row => row?.chapter ?? row?.id)
      .filter(value => value !== undefined && value !== null)
      .map(String)
  ).size
}

function attemptWire (run) {
  return {
    id: run.started_at,
    attempt_id: run.started_at,
    chapter_id: run.chapter,
    challenge_id: run.challenge || null,
    seed: run.started_at,
    weapons: run.weapons,
    gear: run.gear,
    stage: run.stage
  }
}

function grantResources (repo, userId, entries, runtime) {
  const grants = []
  for (const entry of entries) grants.push(giveGameResource(repo, userId, entry, runtime).wire)
  return grants
}

function chapterDefinition (chapterId, runtime) {
  return chaptersList(runtime.gameData).find(def => asInt(def?.id ?? def?.rid) === chapterId) || null
}

function stageRewardsFor (definition) {
  return Array.isArray(definition?.stage_rewards) ? definition.stage_rewards : null
}

function requireVipEntitlement (repo, userId, definition) {
  const entitlementId = asInt(definition?.vip_entitlement_id)
  if (entitlementId === null) return { error: [400, 2300, { reason: 'vip-config-missing' }] }
  if (!asArray(repo.entitlements(userId)).some(row => asInt(row?.rid) === entitlementId)) {
    return { error: [400, 2300, { reason: 'vip-not-entitled' }] }
  }
  return null
}

function vipResourcesAt (stageRewards, stage) {
  const entry = stageRewards.find(row => asInt(row?.stage) === stage)
  const resources = asArray(entry?.vip_resources)
  return resources.length > 0 ? resources : null
}

// Concede todos os estágios VIP pendentes do capítulo (robusto para as três
// rotas VIP); o chamador decide entre "um estágio" e "todos" pela resposta.
function claimVipStages (repo, userId, definition, row, runtime) {
  const stageRewards = stageRewardsFor(definition)
  const grants = []
  const stages = []
  let stage = (asInt(row.highest_vip_reward_claimed) ?? 0) + 1
  while ((asInt(row.best_stage) ?? 0) >= stage) {
    const resources = vipResourcesAt(stageRewards, stage)
    if (!resources) break
    grants.push(...grantResources(repo, userId, resources, runtime))
    stages.push(stage)
    row.highest_vip_reward_claimed = stage
    stage += 1
  }
  return { stages, grants }
}

function chapterIdFromBody (body) {
  return asInt(body?.chapter_id ?? body?.chapter)
}

function claimStageRewardRoute (repo, userId, body, runtime) {
  const chapterId = chapterIdFromBody(body)
  if (chapterId === null) return { error: [400, 2200, { reason: 'chapter-required' }] }
  const definition = chapterDefinition(chapterId, runtime)
  if (!definition) return { error: [400, 2200, { reason: 'chapter-not-found' }] }
  const stageRewards = stageRewardsFor(definition)
  if (!stageRewards) return { error: [400, 2300, { reason: 'stage-rewards-config-missing' }] }
  const state = progression(repo, userId)
  const row = chapterRow(state, chapterId)
  const nextStage = (asInt(row.highest_stage_reward_claimed) ?? 0) + 1
  const entry = stageRewards.find(item => asInt(item?.stage) === nextStage)
  if (!entry) return { error: [400, 2300, { reason: 'stage-reward-already-claimed' }] }
  if ((asInt(row.best_stage) ?? 0) < nextStage) {
    return { error: [400, 2300, { reason: 'stage-not-completed', stage: nextStage }] }
  }
  let resources
  repo.tx(() => {
    resources = grantResources(repo, userId, asArray(entry.resources), runtime)
    row.highest_stage_reward_claimed = nextStage
    saveProgression(repo, userId, state)
  })
  return { data: { stage: nextStage, resources } }
}

function claimVipRewardRoute (repo, userId, body, runtime) {
  const chapterId = chapterIdFromBody(body)
  if (chapterId === null) return { error: [400, 2200, { reason: 'chapter-required' }] }
  const definition = chapterDefinition(chapterId, runtime)
  if (!definition) return { error: [400, 2200, { reason: 'chapter-not-found' }] }
  if (!stageRewardsFor(definition)) return { error: [400, 2300, { reason: 'stage-rewards-config-missing' }] }
  const denied = requireVipEntitlement(repo, userId, definition)
  if (denied) return denied
  const state = progression(repo, userId)
  const row = chapterRow(state, chapterId)
  const nextStage = (asInt(row.highest_vip_reward_claimed) ?? 0) + 1
  if ((asInt(row.best_stage) ?? 0) < nextStage) {
    return { error: [400, 2300, { reason: 'stage-not-completed', stage: nextStage }] }
  }
  const resources = vipResourcesAt(stageRewardsFor(definition), nextStage)
  if (!resources) return { error: [400, 2300, { reason: 'vip-reward-already-claimed' }] }
  let grants
  repo.tx(() => {
    grants = grantResources(repo, userId, resources, runtime)
    row.highest_vip_reward_claimed = nextStage
    saveProgression(repo, userId, state)
  })
  return { data: { stage: nextStage, resources: grants } }
}

function claimVipRewardsChapterRoute (repo, userId, body, runtime) {
  const chapterId = chapterIdFromBody(body)
  if (chapterId === null) return { error: [400, 2200, { reason: 'chapter-required' }] }
  const definition = chapterDefinition(chapterId, runtime)
  if (!definition) return { error: [400, 2200, { reason: 'chapter-not-found' }] }
  if (!stageRewardsFor(definition)) return { error: [400, 2300, { reason: 'stage-rewards-config-missing' }] }
  const denied = requireVipEntitlement(repo, userId, definition)
  if (denied) return denied
  const state = progression(repo, userId)
  const row = chapterRow(state, chapterId)
  let claimed
  repo.tx(() => {
    claimed = claimVipStages(repo, userId, definition, row, runtime)
    saveProgression(repo, userId, state)
  })
  if (claimed.stages.length === 0) return { error: [400, 2300, { reason: 'vip-reward-already-claimed' }] }
  return { data: { stage: claimed.stages[claimed.stages.length - 1], resources: claimed.grants } }
}

function claimVipRewardsAllRoute (repo, userId, body, runtime) {
  const state = progression(repo, userId)
  const stages = []
  const grants = []
  repo.tx(() => {
    for (const definition of chaptersList(runtime.gameData)) {
      const chapterId = asInt(definition?.id ?? definition?.rid)
      if (chapterId === null || !stageRewardsFor(definition)) continue
      if (requireVipEntitlement(repo, userId, definition)) continue
      const row = chapterRow(state, chapterId)
      const claimed = claimVipStages(repo, userId, definition, row, runtime)
      for (const stage of claimed.stages) stages.push({ chapter_id: chapterId, stage })
      grants.push(...claimed.grants)
    }
    saveProgression(repo, userId, state)
  })
  if (stages.length === 0) return { error: [400, 2300, { reason: 'vip-reward-already-claimed' }] }
  return { data: { stages, resources: grants } }
}

function claimChallengeRewardRoute (repo, userId, body, runtime) {
  const chapterId = chapterIdFromBody(body)
  const challengeId = asInt(body?.challenge_id ?? body?.challenge)
  if (chapterId === null) return { error: [400, 2200, { reason: 'chapter-required' }] }
  if (challengeId === null) return { error: [400, 2200, { reason: 'challenge-required' }] }
  const definition = chapterDefinition(chapterId, runtime)
  if (!definition) return { error: [400, 2200, { reason: 'chapter-not-found' }] }
  const challenge = asArray(definition.challenges).find(row => asInt(row?.id ?? row?.rid) === challengeId)
  if (!challenge) return { error: [400, 2300, { reason: 'challenge-config-missing' }] }
  const reward = asArray(challenge.completion_reward)
  if (reward.length === 0) return { error: [400, 2300, { reason: 'challenge-reward-config-missing' }] }
  const state = progression(repo, userId)
  const row = challengeRow(state, chapterId, challengeId)
  if (row.completion_reward_claimed) return { error: [400, 2300, { reason: 'challenge-reward-already-claimed' }] }
  if (!((asInt(row.wins) ?? 0) > 0)) return { error: [400, 2300, { reason: 'challenge-not-completed' }] }
  let resources
  repo.tx(() => {
    resources = grantResources(repo, userId, reward, runtime)
    row.completion_reward_claimed = true
    saveProgression(repo, userId, state)
  })
  return { data: { resources } }
}

// RedeemVoucher(voucherId): o cliente consome um item de voucher ganho no
// capítulo para reviver. Posse = item no inventário com o rid do voucher
// (armazenamento A VERIFICAR até captura do cliente); resposta é envelope puro.
function redeemVoucherRoute (repo, userId, body) {
  const voucherId = asInt(body?.voucher_id ?? body?.voucher)
  if (voucherId === null) return { error: [400, 2200, { reason: 'voucher-required' }] }
  const state = progression(repo, userId)
  if (!state.current_run) return { error: [400, 2300, { reason: 'no-active-run' }] }
  const voucher = asArray(repo.items(userId)).find(item => asInt(item?.rid) === voucherId)
  if (!voucher) return { error: [400, 2300, { reason: 'voucher-not-owned' }] }
  let result
  try {
    repo.tx(() => {
      if (!repo.deleteItem(userId, voucher.id)) {
        throw Object.assign(new Error('voucher-not-owned'), { result: { error: [400, 2300, { reason: 'voucher-not-owned' }] } })
      }
      const run = {
        ...state.current_run,
        revives: Math.max(0, Number(state.current_run.revives || 0)) + 1,
        redeemed_vouchers: [...new Set([...asArray(state.current_run.redeemed_vouchers), voucherId])],
        updated_at: nowSeconds()
      }
      state.current_run = run
      saveProgression(repo, userId, state)
      result = { data: {} }
    })
  } catch (error) {
    return error.result || { error: [400, 2000, { reason: error.message }] }
  }
  return result
}

// AdRevive/AdAbilityReroll(rewardTokenId): consome um AdRewardToken emitido
// pelo fluxo de anúncios (game/ads/*, fora de escopo por enquanto). Sem
// emissor, o estado honesto é o erro explícito — nunca sucesso falso.
function adRewardRoute (repo, userId, body, expectedType) {
  const tokenId = asInt(body?.reward_token_id ?? body?.rewardTokenId)
  if (tokenId === null) return { error: [400, 2200, { reason: 'reward-token-required' }] }
  const tokens = asArray(repo.getState(userId, 'ads', 'reward_tokens', []))
  const token = tokens.find(row => asInt(row?.id) === tokenId)
  if (!token) return { error: [400, 2300, { reason: 'reward-token-not-found' }] }
  if ((token.reward_type ?? token.type) !== expectedType) {
    return { error: [400, 2300, { reason: 'reward-token-type-mismatch' }] }
  }
  const expireEpoch = asInt(token.expire_epoch)
  if (expireEpoch !== null && expireEpoch < nowSeconds()) {
    return { error: [400, 2300, { reason: 'reward-token-expired' }] }
  }
  const state = progression(repo, userId)
  if (!state.current_run) return { error: [400, 2300, { reason: 'no-active-run' }] }
  let result
  try {
    repo.tx(() => {
      repo.setState(userId, 'ads', 'reward_tokens', tokens.filter(row => asInt(row?.id) !== tokenId))
      const current = state.current_run
      const run = expectedType === 'revive'
        ? { ...current, revives: Math.max(0, Number(current.revives || 0)) + 1, updated_at: nowSeconds() }
        : { ...current, ability_rerolls: (asInt(current.ability_rerolls) ?? 0) + 1, updated_at: nowSeconds() }
      state.current_run = run
      saveProgression(repo, userId, state)
      result = { data: {} }
    })
  } catch (error) {
    return { error: [400, 2000, { reason: error.message }] }
  }
  return result
}

export function chapterProgressionWire (repo, userId) {
  return progression(repo, userId)
}

export function handleChapterRequest (path, body, userId, repo, runtime) {
  if (path === '/game/chapters/start') {
    const state = progression(repo, userId)
    if (state.current_run) return { error: [400, 2300, { reason: 'run-already-active' }] }
    const run = runFromBody(body)
    if (!run) return { error: [400, 2200, { reason: 'chapter-required' }] }
    repo.tx(() => {
      repo.incrementAttemptCount(userId)
      saveProgression(repo, userId, { ...state, current_run: run })
    })
    return { data: { attempt: attemptWire(run) } }
  }

  if (path === '/game/chapters/update') {
    const state = progression(repo, userId)
    if (!state.current_run) return { error: [400, 2300, { reason: 'no-active-run' }] }
    const currentRun = mergeRun(state.current_run, body)
    saveProgression(repo, userId, { ...state, current_run: currentRun })
    return { data: { min_update_time: null } }
  }

  if (path === '/game/chapters/revive') {
    const state = progression(repo, userId)
    if (!state.current_run) return { error: [400, 2300, { reason: 'no-active-run' }] }
    const currentRun = {
      ...state.current_run,
      revives: Math.max(0, Number(state.current_run.revives || 0)) + 1,
      updated_at: nowSeconds()
    }
    saveProgression(repo, userId, { ...state, current_run: currentRun })
    return { data: {} }
  }

  if (path === '/game/chapters/ad-revive') return adRewardRoute(repo, userId, body, 'revive')
  if (path === '/game/chapters/ad-ability-reroll') return adRewardRoute(repo, userId, body, 'ability_reroll')
  if (path === '/game/chapters/redeem-voucher') return redeemVoucherRoute(repo, userId, body)

  if (path === '/game/chapters/end') {
    const state = progression(repo, userId)
    if (!state.current_run) return { error: [400, 2300, { reason: 'no-active-run' }] }
    const finalRun = mergeRun(state.current_run, body)
    const next = recordCompletion(state, finalRun, body)
    repo.tx(() => {
      saveProgression(repo, userId, next)
      if (completedFromProgress(body)) {
        repo.setChapterProgression(userId, completedChapterCount(next))
      }
    })
    return { data: { loot: Array.isArray(finalRun.loot) ? finalRun.loot : [] } }
  }

  if (path === '/game/chapters/claim-stage-reward') return claimStageRewardRoute(repo, userId, body, runtime)
  if (path === '/game/chapters/claim-rewards') return claimStageRewardRoute(repo, userId, body, runtime)
  if (path === '/game/chapters/claim-vip-reward') return claimVipRewardRoute(repo, userId, body, runtime)
  if (path === '/game/chapters/claim-vip-rewards-chapter') return claimVipRewardsChapterRoute(repo, userId, body, runtime)
  if (path === '/game/chapters/claim-vip-rewards-all') return claimVipRewardsAllRoute(repo, userId, body, runtime)
  if (path === '/game/chapters/claim-challenge-reward') return claimChallengeRewardRoute(repo, userId, body, runtime)

  return null
}
