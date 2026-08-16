import { giveGameResource } from './game-data-model.js'
import { archiveMode, storyBattlePasses } from './game-data-schema.js'

const NS = 'battle-pass'

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
    premium_state: runtime.revival.unlock_premium_battle_pass === false ? 0 : 1,
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
  for (const pass of storyBattlePasses(runtime.gameData)) {
    if (!available(runtime, pass)) continue
    const state = battlePassState(repo, userId, runtime, pass.id)
    if (state) result.push(state)
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

function alreadyClaimed (state, tierId, rewardId) {
  return state.reward_claims.some(claim => claim?.tier_id === tierId && claim?.reward_id === rewardId)
}

export function handleBattlePassRequest (path, body, userId, repo, runtime) {
  if (path === '/game/battle-pass/start-season') {
    const seasonId = body?.season_id
    if (typeof seasonId !== 'string') return { error: [400, 2200] }
    const pass = battlePassById(runtime, seasonId)
    if (!available(runtime, pass)) return { error: [400, 2000, { reason: 'season-unavailable' }] }
    if (battlePassState(repo, userId, runtime, seasonId)) return { error: [400, 2000, { reason: 'season-already-started' }] }
    const state = battlePassDefaultState(runtime, pass)
    repo.setState(userId, NS, stateKey(seasonId), state)
    return { data: { state } }
  }

  if (path === '/game/battle-pass/claim-mission') {
    const seasonId = body?.season_id
    const requestedMissionId = body?.mission_id
    if (typeof seasonId !== 'string' || !Number.isInteger(requestedMissionId)) return { error: [400, 2200] }
    const pass = battlePassById(runtime, seasonId)
    if (!available(runtime, pass)) return { error: [400, 2000] }
    const definition = missionDefinitions(pass).find(entry => missionId(entry) === requestedMissionId)
    if (!definition) return { error: [400, 2000] }
    const state = battlePassState(repo, userId, runtime, seasonId)
    if (!state) return { error: [400, 2000, { reason: 'season-not-started' }] }
    const mission = state.mission_progress.find(entry => entry.mission_id === requestedMissionId)
    if (!mission || !mission.completed || mission.claimed) return { error: [400, 2000, { reason: 'mission-not-claimable' }] }
    mission.claimed = true
    mission.claim_state = 2
    state.points += missionPoints(definition)
    repo.setState(userId, NS, stateKey(seasonId), state)
    return { data: { resources: [] } }
  }

  if (path === '/game/battle-pass/claim-track-tier') {
    const seasonId = body?.season_id
    const tierId = body?.tier_id
    if (typeof seasonId !== 'string' || !Number.isInteger(tierId)) return { error: [400, 2200] }
    const pass = battlePassById(runtime, seasonId)
    if (!available(runtime, pass)) return { error: [400, 2000] }
    const tier = tierDefinitions(pass).find(entry => entry?.id === tierId)
    if (!tier) return { error: [400, 2000] }
    const state = battlePassState(repo, userId, runtime, seasonId)
    if (!state) return { error: [400, 2000, { reason: 'season-not-started' }] }
    const threshold = Math.max(0, Number(tier.point_threshold) || 0)
    if (state.points < threshold) return { error: [400, 2000, { reason: 'insufficient-points' }] }

    const grants = []
    repo.tx(() => {
      const rewards = Array.isArray(tier.rewards) ? tier.rewards : []
      for (const reward of rewards) {
        const rewardId = reward?.id
        if (!Number.isInteger(rewardId)) continue
        if (alreadyClaimed(state, tierId, rewardId)) continue
        if (reward.requires_premium && state.premium_state < 1) continue
        const resources = reward?.reward_items?.resources
        if (Array.isArray(resources)) {
          for (const resource of resources) {
            grants.push(giveGameResource(repo, userId, resource, runtime).wire)
          }
        }
        state.reward_claims.push({ tier_id: tierId, reward_id: rewardId })
      }
      repo.setState(userId, NS, stateKey(seasonId), state)
    })

    return { data: { resources: grants } }
  }

  return null
}
