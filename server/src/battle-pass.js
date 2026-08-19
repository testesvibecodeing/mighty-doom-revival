import { giveGameResource } from './game-data-model.js'
import { archiveMode, storyBattlePasses } from './game-data-schema.js'

const NS = 'battle-pass'

// ---- Contrato extraído do global-metadata.dat v29 (2026-08-17) ----
// BattlePassApi (9 métodos = 9 rotas game/battle-pass/*):
//   StartSeason(seasonId)                       {season_id}
//   EndSeason(seasonId)                         {season_id}
//   RedeemPremiumEntitlement(seasonId)          {season_id}
//   ClaimTrackReward(seasonId, tierId, rewardId) {season_id, tier_id, reward_id}
//   ClaimTrackTier(seasonId, tierId)            {season_id, tier_id}
//   ClaimTrackAll(seasonId)                     {season_id}
//   Prestige(seasonId)                          {season_id}
//   BuyNextTrackTier(seasonId)                  {season_id}
//   ClaimMission(seasonId, missionId)           {season_id, mission_id}
// Response DTOs (campos confirmados; snake_case do nome C#):
//   StartSeasonResponse{state}   EndSeasonResponse{resources}
//   ClaimTrackReward/Tier/All/Mission/Prestige: {resources}
//   RedeemPremiumEntitlement/BuyNextTrackTier: sem campos -> envelope puro.
// DataObjects de estado/config (campos confirmados):
//   BattlePassEventState{seasonId, activeState, premiumState, points,
//     prestige, rewardClaims, missionProgress}
//   BattlePassRewardClaim{tierId, rewardId}
//   BattlePassRewardTier{id, pointThreshold, rewards}
//   BattlePassReward{id, requiresPremium, rewardItems}
//   BattlePassRewardItems{resources, dropTableRolls, display}
//   BattlePassRewardTrack{tiers, prestigePointStart, prestigePointIncrement,
//     prestigeRequiresPremium, prestigeRewardPool}
//   BattlePassPointsExchangeRate{inCurrency, outPoints}
//   ScheduledBattlePassEventArgs{..., premiumEntitlementId, pointsExchangeRate,
//     rewardTrack, missions, ...}
// Enums: ActiveState None=0/Active=1/Ended=2; PremiumState None=0/Free=1/
// Premium=2; MissionClaimState None=0/Unclaimed=1/Claimed=2.
// CONFIRMADO por literal: season_rewards não; progress/tracks não são daqui.
// A VERIFICAR até captura do cliente: season_id/tier_id/reward_id/mission_id
// (fallback snake), custo do BuyNextTrackTier (aqui: exchange rate
// ceil(pontos_faltantes/out_points) * in_amount) e o reset de pontos do
// Prestige (aqui: prestige_point_start + (prestige-1) * incremento).

function battlePassById (runtime, seasonId) {
  return storyBattlePasses(runtime.gameData).find(pass => pass?.id === seasonId) || null
}

function available (runtime, pass) {
  if (!pass || Number(pass.availability ?? 1) < 1) return false
  if (archiveMode(runtime)) return true
  const now = Math.floor(Date.now() / 1000)
  if (pass.start_time !== null && pass.start_time !== undefined && now < Number(pass.start_time)) return false
  if (pass.end_time !== null && pass.end_time !== undefined && now > Number(pass.end_time)) return false
  return true
}

function missionDefinitions (pass) {
  const list = pass?.args?.missions?.seasonal_missions
  return Array.isArray(list) ? list : []
}

function tierDefinitions (pass) {
  const list = pass?.args?.reward_track?.tiers
  return Array.isArray(list) ? list : []
}

function missionId (entry) {
  if (Number.isInteger(entry?.mission?.id)) return entry.mission.id
  if (Number.isInteger(entry?.id)) return entry.id
  return null
}

function missionPoints (entry) {
  const value = entry?.mission?.points ?? entry?.points ?? 0
  return Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : 0
}

function missionStatId (entry) {
  const mission = entry?.mission ?? entry
  const candidates = [
    mission?.stat_id,
    mission?.stat?.id,
    mission?.objective?.stat_id,
    mission?.objective?.stat?.id,
    entry?.stat_id
  ]
  for (const value of candidates) {
    if (Number.isInteger(value)) return value
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return null
}

function missionTarget (entry) {
  const mission = entry?.mission ?? entry
  const candidates = [
    mission?.target,
    mission?.amount,
    mission?.required,
    mission?.count,
    mission?.objective?.target,
    mission?.objective?.amount,
    mission?.objective?.required,
    mission?.objective?.count,
    entry?.target
  ]
  for (const value of candidates) {
    const parsed = Number(value)
    if (Number.isFinite(parsed) && parsed > 0) return parsed
  }
  return null
}

function defaultMissionProgress (pass) {
  return missionDefinitions(pass)
    .map(entry => missionId(entry))
    .filter(Number.isInteger)
    .map(id => ({ mission_id: id, progress: 0, claim_state: 1 }))
}

function stateKey (seasonId) {
  return String(seasonId)
}

export function battlePassDefaultState (runtime, pass) {
  return {
    season_id: pass.id,
    active_state: 1,
    // PremiumState: None=0, Free=1, Premium=2. Servidor particular libera o
    // premium por padrão (2); com unlock desligado parte de None (0) e só
    // sobe via /redeem-premium-entitlement.
    premium_state: runtime.revival.unlock_premium_battle_pass === false ? 0 : 2,
    points: 0,
    prestige: 0,
    reward_claims: [],
    mission_progress: defaultMissionProgress(pass)
  }
}

export function battlePassState (repo, userId, runtime, seasonId) {
  const saved = repo.getState(userId, NS, stateKey(seasonId), null)
  if (!saved) return null
  const pass = battlePassById(runtime, seasonId)
  if (!pass) return null
  return {
    ...battlePassDefaultState(runtime, pass),
    ...saved,
    reward_claims: Array.isArray(saved.reward_claims) ? saved.reward_claims : [],
    mission_progress: Array.isArray(saved.mission_progress) ? saved.mission_progress : defaultMissionProgress(pass)
  }
}

export function activeBattlePassStates (repo, userId, runtime) {
  const result = []
  const archive = archiveMode(runtime)
  for (const pass of storyBattlePasses(runtime.gameData)) {
    if (!available(runtime, pass)) continue
    const state = battlePassState(repo, userId, runtime, pass.id)
    if (state) {
      result.push(state)
      continue
    }

    // Archived seasons need to be visible in the client's event progress before
    // the player explicitly starts one. Return a non-persisted default preview
    // so /start-season can still create the real state when the client asks.
    if (archive) result.push(battlePassDefaultState(runtime, pass))
  }
  return result
}

export function setBattlePassMissionProgress (repo, userId, runtime, seasonId, missionIdValue, progress, completed = false) {
  const pass = battlePassById(runtime, seasonId)
  if (!available(runtime, pass)) return false
  const state = battlePassState(repo, userId, runtime, seasonId)
  if (!state) return false
  const row = state.mission_progress.find(item => item.mission_id === missionIdValue)
  if (!row) return false
  row.progress = Math.max(0, Number(progress) || 0)
  row.claim_state = completed ? 2 : 1
  if (completed) row.completed = true
  repo.setState(userId, NS, stateKey(seasonId), state)
  return true
}

export function applyBattlePassStatTotals (repo, userId, runtime, totals) {
  if (!totals || typeof totals !== 'object') return []
  const updates = []

  for (const pass of storyBattlePasses(runtime.gameData)) {
    if (!available(runtime, pass)) continue
    const state = battlePassState(repo, userId, runtime, pass.id)
    if (!state) continue

    let changed = false
    for (const definition of missionDefinitions(pass)) {
      const id = missionId(definition)
      const statId = missionStatId(definition)
      const target = missionTarget(definition)
      if (!Number.isInteger(id) || statId === null || target === null) continue

      const raw = totals[String(statId)] ?? totals[statId]
      const total = Number(raw)
      if (!Number.isFinite(total) || total < 0) continue

      const row = state.mission_progress.find(item => item.mission_id === id)
      if (!row || row.claimed) continue

      const next = Math.min(target, total)
      const completed = next >= target
      if (Number(row.progress || 0) === next && Boolean(row.completed) === completed) continue

      row.progress = next
      row.completed = completed
      row.claim_state = completed ? 2 : 1
      changed = true
      updates.push({ season_id: pass.id, mission_id: id, progress: next, target, completed })
    }

    if (changed) repo.setState(userId, NS, stateKey(pass.id), state)
  }

  return updates
}

function alreadyClaimed (state, tierId, rewardId) {
  return state.reward_claims.some(claim => claim?.tier_id === tierId && claim?.reward_id === rewardId)
}

function sortedTiers (pass) {
  return tierDefinitions(pass)
    .slice()
    .sort((a, b) => Number(a?.point_threshold) - Number(b?.point_threshold))
}

function rewardResources (reward) {
  const resources = reward?.reward_items?.resources ?? reward?.resources
  return Array.isArray(resources) ? resources : []
}

function grantReward (grants, repo, userId, state, tierId, reward, runtime) {
  const rewardId = reward?.id
  if (!Number.isInteger(rewardId)) return
  if (alreadyClaimed(state, tierId, rewardId)) return
  if (reward.requires_premium && state.premium_state < 2) return
  for (const resource of rewardResources(reward)) {
    grants.push(giveGameResource(repo, userId, resource, runtime).wire)
  }
  state.reward_claims.push({ tier_id: tierId, reward_id: rewardId })
}

// Concede todos os rewards já conquistados (pontos >= threshold, premium ok,
// ainda não reivindicados) — compartilhado por claim-track-all e end-season.
function grantEarnedRewards (repo, userId, state, pass, runtime) {
  const grants = []
  for (const tier of sortedTiers(pass)) {
    const threshold = Math.max(0, Number(tier.point_threshold) || 0)
    if (state.points < threshold) continue
    for (const reward of Array.isArray(tier.rewards) ? tier.rewards : []) {
      grantReward(grants, repo, userId, state, tier.id, reward, runtime)
    }
  }
  return grants
}

function currencyRidFor (value, runtime) {
  if (Number.isInteger(value)) return value
  if (typeof value === 'string') {
    const row = runtime?.index?.byTag?.get(value)
    if (Number.isInteger(row)) return row
    if (row) return Number.isInteger(row.id) ? row.id : Number.isInteger(row.rid) ? row.rid : null
  }
  return null
}

// season iniciada + não encerrada; devolve o estado pronto para operar.
function activeSeasonState (repo, userId, runtime, seasonId) {
  if (typeof seasonId !== 'string') return { error: [400, 2200, { reason: 'season-required' }] }
  const pass = battlePassById(runtime, seasonId)
  if (!pass) return { error: [400, 2200, { reason: 'season-not-found' }] }
  if (!available(runtime, pass)) return { error: [400, 2300, { reason: 'season-unavailable' }] }
  let state = battlePassState(repo, userId, runtime, seasonId)
  if (!state) {
    // O preview de archive do get-progress não persiste estado; o cliente
    // do FTUE chama end-season direto, sem start-season (provado no
    // emulador 2026-08-19: end-season -> 400 season-not-started em loop e
    // diálogo de ERRO). Materializa o estado default aqui e segue.
    state = battlePassDefaultState(runtime, pass)
    repo.setState(userId, NS, stateKey(seasonId), state)
  }
  if (state.active_state === 2) return { error: [400, 2300, { reason: 'season-ended' }] }
  return { pass, state }
}

export function handleBattlePassRequest (path, body, userId, repo, runtime) {
  if (path === '/game/battle-pass/start-season') {
    const seasonId = body?.season_id
    if (typeof seasonId !== 'string') return { error: [400, 2200, { reason: 'season-required' }] }
    const pass = battlePassById(runtime, seasonId)
    if (!available(runtime, pass)) return { error: [400, 2200, { reason: 'season-not-found' }] }
    if (battlePassState(repo, userId, runtime, seasonId)) return { error: [400, 2300, { reason: 'season-already-started' }] }
    const state = battlePassDefaultState(runtime, pass)
    repo.setState(userId, NS, stateKey(seasonId), state)
    return { data: { state } }
  }

  if (path === '/game/battle-pass/end-season') {
    const check = activeSeasonState(repo, userId, runtime, body?.season_id)
    if (check.error) return { error: check.error }
    const { pass, state } = check
    let resources
    repo.tx(() => {
      resources = grantEarnedRewards(repo, userId, state, pass, runtime)
      state.active_state = 2
      repo.setState(userId, NS, stateKey(state.season_id), state)
    })
    return { data: { resources } }
  }

  if (path === '/game/battle-pass/redeem-premium-entitlement') {
    const check = activeSeasonState(repo, userId, runtime, body?.season_id)
    if (check.error) return { error: check.error }
    const { pass, state } = check
    const entitlementId = pass?.args?.premium_entitlement_id
    if (entitlementId === undefined || entitlementId === null) {
      return { error: [400, 2300, { reason: 'premium-entitlement-config-missing' }] }
    }
    if (state.premium_state >= 2) return { error: [400, 2300, { reason: 'already-premium' }] }
    const owned = (repo.entitlements(userId) || []).some(row =>
      row?.rid === entitlementId || row?.tag === entitlementId
    )
    if (!owned) return { error: [400, 2300, { reason: 'premium-not-entitled' }] }
    state.premium_state = 2
    repo.setState(userId, NS, stateKey(state.season_id), state)
    return { data: {} }
  }

  if (path === '/game/battle-pass/claim-mission') {
    const requestedMissionId = body?.mission_id
    if (!Number.isInteger(requestedMissionId)) return { error: [400, 2200, { reason: 'mission-id-required' }] }
    const check = activeSeasonState(repo, userId, runtime, body?.season_id)
    if (check.error) return { error: check.error }
    const { pass, state } = check
    const definition = missionDefinitions(pass).find(entry => missionId(entry) === requestedMissionId)
    if (!definition) return { error: [400, 2200, { reason: 'mission-not-found' }] }
    const mission = state.mission_progress.find(entry => entry.mission_id === requestedMissionId)
    if (!mission || !mission.completed || mission.claimed) return { error: [400, 2300, { reason: 'mission-not-claimable' }] }
    mission.claimed = true
    mission.claim_state = 2
    state.points += missionPoints(definition)
    repo.setState(userId, NS, stateKey(state.season_id), state)
    return { data: { resources: [] } }
  }

  if (path === '/game/battle-pass/claim-track-tier') {
    const tierId = body?.tier_id
    if (!Number.isInteger(tierId)) return { error: [400, 2200, { reason: 'tier-required' }] }
    const check = activeSeasonState(repo, userId, runtime, body?.season_id)
    if (check.error) return { error: check.error }
    const { pass, state } = check
    const tier = tierDefinitions(pass).find(entry => entry?.id === tierId)
    if (!tier) return { error: [400, 2200, { reason: 'tier-not-found' }] }
    const threshold = Math.max(0, Number(tier.point_threshold) || 0)
    if (state.points < threshold) return { error: [400, 2300, { reason: 'insufficient-points' }] }

    const grants = []
    repo.tx(() => {
      for (const reward of Array.isArray(tier.rewards) ? tier.rewards : []) {
        grantReward(grants, repo, userId, state, tierId, reward, runtime)
      }
      repo.setState(userId, NS, stateKey(state.season_id), state)
    })
    return { data: { resources: grants } }
  }

  if (path === '/game/battle-pass/claim-track-reward') {
    const tierId = body?.tier_id
    const rewardId = body?.reward_id
    if (!Number.isInteger(tierId)) return { error: [400, 2200, { reason: 'tier-required' }] }
    if (!Number.isInteger(rewardId)) return { error: [400, 2200, { reason: 'reward-required' }] }
    const check = activeSeasonState(repo, userId, runtime, body?.season_id)
    if (check.error) return { error: check.error }
    const { pass, state } = check
    const tier = tierDefinitions(pass).find(entry => entry?.id === tierId)
    if (!tier) return { error: [400, 2200, { reason: 'tier-not-found' }] }
    const reward = (Array.isArray(tier.rewards) ? tier.rewards : []).find(entry => entry?.id === rewardId)
    if (!reward) return { error: [400, 2200, { reason: 'reward-not-found' }] }
    if (state.points < Math.max(0, Number(tier.point_threshold) || 0)) {
      return { error: [400, 2300, { reason: 'insufficient-points' }] }
    }
    if (alreadyClaimed(state, tierId, rewardId)) return { error: [400, 2300, { reason: 'reward-already-claimed' }] }
    if (reward.requires_premium && state.premium_state < 2) {
      return { error: [400, 2300, { reason: 'premium-required' }] }
    }
    const grants = []
    repo.tx(() => {
      grantReward(grants, repo, userId, state, tierId, reward, runtime)
      repo.setState(userId, NS, stateKey(state.season_id), state)
    })
    return { data: { resources: grants } }
  }

  if (path === '/game/battle-pass/claim-track-all') {
    const check = activeSeasonState(repo, userId, runtime, body?.season_id)
    if (check.error) return { error: check.error }
    const { pass, state } = check
    let resources
    repo.tx(() => {
      resources = grantEarnedRewards(repo, userId, state, pass, runtime)
      repo.setState(userId, NS, stateKey(state.season_id), state)
    })
    if (resources.length === 0) return { error: [400, 2300, { reason: 'nothing-to-claim' }] }
    return { data: { resources } }
  }

  if (path === '/game/battle-pass/prestige') {
    const check = activeSeasonState(repo, userId, runtime, body?.season_id)
    if (check.error) return { error: check.error }
    const { pass, state } = check
    const track = pass?.args?.reward_track || {}
    const tiers = sortedTiers(pass)
    const maxThreshold = tiers.length > 0 ? Math.max(0, Number(tiers[tiers.length - 1].point_threshold) || 0) : null
    if (maxThreshold === null || state.points < maxThreshold) {
      return { error: [400, 2300, { reason: 'prestige-not-available' }] }
    }
    if (track.prestige_requires_premium && state.premium_state < 2) {
      return { error: [400, 2300, { reason: 'premium-required' }] }
    }
    const pointStart = Number(track.prestige_point_start)
    const increment = Number(track.prestige_point_increment)
    if (!Number.isFinite(pointStart) || !Number.isFinite(increment)) {
      return { error: [400, 2300, { reason: 'prestige-config-missing' }] }
    }
    const pool = Array.isArray(track.prestige_reward_pool) ? track.prestige_reward_pool : []
    const grants = []
    repo.tx(() => {
      for (const reward of pool) {
        for (const resource of rewardResources(reward)) {
          grants.push(giveGameResource(repo, userId, resource, runtime).wire)
        }
      }
      state.prestige = (Number(state.prestige) || 0) + 1
      // Novo ciclo: pontos voltam ao base do prestige; claims zeram porque os
      // tiers podem ser conquistados de novo (A VERIFICAR na captura).
      state.points = pointStart + (state.prestige - 1) * increment
      state.reward_claims = []
      repo.setState(userId, NS, stateKey(state.season_id), state)
    })
    return { data: { resources: grants } }
  }

  if (path === '/game/battle-pass/buy-next-track-tier') {
    const check = activeSeasonState(repo, userId, runtime, body?.season_id)
    if (check.error) return { error: check.error }
    const { pass, state } = check
    const tiers = sortedTiers(pass)
    const next = tiers.find(entry => Number(entry?.point_threshold) > state.points)
    if (!next) return { error: [400, 2300, { reason: 'no-next-tier' }] }
    const rate = pass?.args?.points_exchange_rate
    const outPoints = Number(rate?.out_points)
    const inAmount = Math.max(1, Number(rate?.in_amount) || 1)
    const rid = currencyRidFor(rate?.in_currency ?? rate?.inCurrency, runtime)
    if (!Number.isFinite(outPoints) || outPoints <= 0 || rid === null) {
      return { error: [400, 2300, { reason: 'point-exchange-rate-missing' }] }
    }
    const needed = Number(next.point_threshold) - state.points
    const cost = Math.ceil(needed / outPoints) * inAmount
    if (repo.balance(userId, rid) < cost) return { error: [400, 2300, { reason: 'insufficient-currency' }] }
    repo.tx(() => {
      repo.addCurrency(userId, rid, -cost)
      state.points = Number(next.point_threshold)
      repo.setState(userId, NS, stateKey(state.season_id), state)
    })
    return { data: {} }
  }

  return null
}
