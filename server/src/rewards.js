import { giveGameResource } from './game-data-model.js'

const DAILY_NS = 'daily-rewards'
const IDLE_NS = 'idle-rewards'

function nowEpoch () {
  return Math.floor(Date.now() / 1000)
}

export function startOfUtcDayEpoch (epoch = nowEpoch()) {
  const now = new Date(epoch * 1000)
  return Math.floor(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()) / 1000)
}

function arrayOrEmpty (value) {
  return Array.isArray(value) ? value : []
}

function dailyRewardRows (runtime) {
  const gameData = runtime?.gameData
  const candidates = [
    gameData?.daily_rewards?.rewards,
    gameData?.daily_rewards?.days,
    gameData?.daily_reward?.rewards,
    gameData?.daily_reward?.days,
    Array.isArray(gameData?.daily_rewards) ? gameData.daily_rewards : null,
    runtime?.revival?.daily_rewards
  ]
  return candidates.find(Array.isArray) || []
}

function rowResources (row) {
  if (!row || typeof row !== 'object') return []
  for (const value of [row.resources, row.rewards, row.contents, row.items]) {
    if (Array.isArray(value)) return value
  }
  if (row.resource !== undefined || row.rid !== undefined) return [row]
  return []
}

function normalizeDailyState (value) {
  return {
    day: Number.isInteger(value?.day) && value.day > 0 ? value.day : 1,
    last_claim: Number.isInteger(value?.last_claim) ? value.last_claim : 0,
    pending: arrayOrEmpty(value?.pending),
    claimed: arrayOrEmpty(value?.claimed)
  }
}

export function dailyRewardState (repo, userId, runtime, epoch = nowEpoch()) {
  const state = normalizeDailyState(repo.getState(userId, DAILY_NS, 'state', null))
  const dayStart = startOfUtcDayEpoch(epoch)
  const rows = dailyRewardRows(runtime)
  const alreadyClaimedToday = state.last_claim >= dayStart && state.last_claim < dayStart + 86400
  const index = rows.length > 0 ? (state.day - 1) % rows.length : 0

  return {
    state,
    rows,
    row: rows[index] || null,
    claimable: !alreadyClaimedToday,
    dayStart
  }
}

export function claimDailyReward (repo, userId, runtime, epoch = nowEpoch()) {
  const current = dailyRewardState(repo, userId, runtime, epoch)
  if (!current.claimable) return { ok: false, reason: 'already-claimed' }

  const grants = []
  repo.tx(() => {
    for (const reward of rowResources(current.row)) {
      const grant = giveGameResource(repo, userId, reward, runtime)
      grants.push(grant.wire)
    }

    const claimed = [...current.state.claimed, { day: current.state.day, claimed_at: epoch }].slice(-90)
    const nextDay = current.rows.length > 0
      ? (current.state.day % current.rows.length) + 1
      : current.state.day + 1
    repo.setState(userId, DAILY_NS, 'state', {
      ...current.state,
      day: nextDay,
      last_claim: epoch,
      pending: [],
      claimed
    })
  })

  return { ok: true, resources: grants, claimed_day: current.state.day }
}

function chooseIdleGeneration (gameData, chapterProgression) {
  const idle = gameData?.idle_reward || gameData?.idle_rewards || {}
  const table = Array.isArray(idle?.chapter_idle_generation) ? idle.chapter_idle_generation : []
  let chosen = null
  for (const row of table) {
    if (typeof row?.chapter_progress !== 'number') continue
    if (row.chapter_progress > chapterProgression) continue
    if (chosen === null || row.chapter_progress >= chosen.chapter_progress) chosen = row
  }
  return {
    idle_generation: arrayOrEmpty(chosen?.idle_generation),
    generation_period: Number(idle?.generation_period || 0),
    max_generation_periods: Number(idle?.max_generation_periods ?? idle?.max_periods ?? 0)
  }
}

export function idleRewardState (repo, userId, runtime, epoch = nowEpoch()) {
  const user = repo.userById(userId)
  const generation = chooseIdleGeneration(runtime?.gameData, user?.chapter_progression || 0)
  let lastClaim = Number(repo.getState(userId, IDLE_NS, 'last_claim', 0) || 0)
  if (lastClaim <= 0) {
    lastClaim = epoch
    repo.setState(userId, IDLE_NS, 'last_claim', lastClaim)
  }

  const period = Math.max(0, generation.generation_period)
  let periods = period > 0 ? Math.floor(Math.max(0, epoch - lastClaim) / period) : 0
  if (generation.max_generation_periods > 0) periods = Math.min(periods, generation.max_generation_periods)

  return {
    last_claim: lastClaim,
    boost_available: 0,
    next_claim: period > 0 ? lastClaim + (periods + 1) * period : 0,
    idle_generation: generation.idle_generation,
    generation_period: period,
    claimable_periods: periods
  }
}

export function claimIdleReward (repo, userId, runtime, epoch = nowEpoch()) {
  const state = idleRewardState(repo, userId, runtime, epoch)
  if (state.claimable_periods <= 0) return { ok: false, reason: 'not-ready', state }

  const grants = []
  const claimedSeconds = state.claimable_periods * state.generation_period
  repo.tx(() => {
    for (const reward of state.idle_generation) {
      const amount = Number(reward?.amount ?? 0)
      if (!Number.isFinite(amount) || amount <= 0) continue
      const grant = giveGameResource(repo, userId, {
        ...reward,
        amount: Math.floor(amount * state.claimable_periods)
      }, runtime)
      grants.push(grant.wire)
    }
    repo.setState(userId, IDLE_NS, 'last_claim', state.last_claim + claimedSeconds)
  })

  return { ok: true, resources: grants, periods: state.claimable_periods }
}
