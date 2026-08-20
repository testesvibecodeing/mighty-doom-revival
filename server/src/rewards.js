import { giveGameResource } from './game-data-model.js'
import { consumeAdRewardToken } from './ad-tokens.js'

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

// `0D00H05M00S` -> 300. Formato real do game-data 1.13.1 (medido em
// 2026-08-20: `idle_reward.generation_period === '0D00H05M00S'`).
const DURATION_RE = /^\s*(?:(\d+)D)?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?\s*$/i

/**
 * Segundos a partir de número OU da duração em texto do game-data.
 *
 * Existe porque `Number('0D00H05M00S')` é NaN e `JSON.stringify(NaN)` emite
 * **null** — foi exatamente assim que `generation_period: null` chegou ao wire
 * e derrubou o parse do cliente com `Malformed response payload` no restart
 * (medido no rig em 2026-08-20, request_log 326, `Network response (14)`).
 * Campo numérico não-nullable jamais pode virar null (DEAD-ENDS #3).
 *
 * Valor irreconhecível devolve `fallback` — nunca NaN, nunca null.
 */
export function durationSeconds (valor, fallback = 0) {
  if (typeof valor === 'number') return Number.isFinite(valor) ? valor : fallback
  if (typeof valor !== 'string' || !valor.trim()) return fallback
  const cru = Number(valor)
  if (Number.isFinite(cru)) return cru
  const m = DURATION_RE.exec(valor)
  if (!m || !m.slice(1).some(Boolean)) return fallback
  const [, d, h, min, s] = m.map(x => (x === undefined ? 0 : Number(x)))
  const total = d * 86400 + h * 3600 + min * 60 + s
  return Number.isFinite(total) ? total : fallback
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
    generation_period: durationSeconds(idle?.generation_period, 0),
    max_generation_periods: durationSeconds(idle?.max_generation_periods ?? idle?.max_periods, 0)
  }
}

/**
 * `300` -> `0D00H05M00S`. É o formato que o CLIENTE exige no wire.
 *
 * CONFIRMADO por bisseção no rig em 2026-08-20 (série `lab-bisect-*`): o campo
 * `generation_period` de `idle-rewards/get-state` derrubava o restart com
 * `Malformed response payload` (`Network response (14)`) enquanto era enviado
 * como INTEIRO. Removê-lo -> `flow_validated`; enviá-lo como TimeSpan .NET
 * (`00:05:00`) -> falha de novo; enviá-lo neste formato -> `flow_validated`.
 *
 * É o mesmo formato que o game-data oficial usa
 * (`idle_reward.generation_period === '0D00H05M00S'`), ou seja: o servidor
 * devolve a duração na forma em que o cliente já sabe lê-la.
 */
export function formatDuration (segundos) {
  const total = Math.max(0, Math.floor(Number(segundos) || 0))
  const pad = n => String(n).padStart(2, '0')
  return `${Math.floor(total / 86400)}D${pad(Math.floor((total % 86400) / 3600))}H` +
    `${pad(Math.floor((total % 3600) / 60))}M${pad(total % 60)}S`
}

/**
 * Segundos que faltam para o proximo claim. Nunca negativo, nunca epoch.
 *
 * Sem periodo configurado nao ha proximo claim agendado: devolve 0, que o
 * cliente trata como "sem timer" (0 ms e valido para o Timer).
 */
export function proximoClaimEmSegundos (lastClaim, period, periods, epoch) {
  if (!(period > 0)) return 0
  const alvoEpoch = lastClaim + (periods + 1) * period
  return Math.max(0, alvoEpoch - epoch)
}

/** Números crus do idle reward — o wire é montado a partir daqui. */
function computeIdle (repo, userId, runtime, epoch) {
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

  return { generation, lastClaim, period, periods }
}

export function idleRewardState (repo, userId, runtime, epoch = nowEpoch()) {
  const { generation, lastClaim, period, periods } = computeIdle(repo, userId, runtime, epoch)

  return {
    last_claim: lastClaim,
    boost_available: 0,
    // SEGUNDOS ATE o proximo claim, nao epoch absoluto.
    //
    // CONFIRMADO por bisseccao no rig em 2026-08-20 (request_log 541 x 555):
    // `Ubu.IdleRewards.IdleRewardsController.UpdateNextClaimEpoch` monta um
    // `System.Timers.Timer(next_claim * 1000)`. Com epoch absoluto o intervalo
    // vira 1.787.259.906.000 ms, muito acima do teto de int.MaxValue (~24,8
    // dias), e o cliente estoura com
    //   ArgumentException: Invalid value '1787259906000' for parameter 'interval'
    // matando o timer inteiro de idle rewards. Com a duracao (246 s -> 246.000
    // ms) o boot fica limpo: zero ArgumentException, zero Timer na stack.
    //
    // `last_claim` continua epoch absoluto — o cliente nao o usa como intervalo.
    next_claim: proximoClaimEmSegundos(lastClaim, period, periods, epoch),
    idle_generation: generation.idle_generation,
    // Duração em TEXTO — inteiro aqui derruba o parse do cliente (ver
    // formatDuration). O valor em segundos continua interno.
    generation_period: formatDuration(period),
    claimable_periods: periods
  }
}

export function claimIdleReward (repo, userId, runtime, epoch = nowEpoch()) {
  const { period } = computeIdle(repo, userId, runtime, epoch)
  const state = idleRewardState(repo, userId, runtime, epoch)
  if (state.claimable_periods <= 0) return { ok: false, reason: 'not-ready', state }

  const grants = []
  const claimedSeconds = state.claimable_periods * period
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

// ---- IdleRewardApi.Boost()/AdBoost(rewardTokenId) (metadata v29) ----
// Ambos sem Response DTO -> envelope puro: concedem os períodos pendentes
// multiplicados e o cliente relê o estado via get-state. Config em
// gameData.idle_reward.boost {multiplier, cooldown}; o AdBoost usa um
// AdRewardToken do tipo IdleRewardBoost e ignora o cooldown do boost grátis.
function boostConfig (runtime) {
  const idle = runtime?.gameData?.idle_reward || runtime?.gameData?.idle_rewards || {}
  const boost = idle?.boost || {}
  const multiplier = Number(boost.multiplier)
  const cooldown = Number(boost.cooldown)
  return {
    multiplier: Number.isFinite(multiplier) && multiplier > 1 ? multiplier : null,
    cooldown: Number.isFinite(cooldown) && cooldown > 0 ? cooldown : 0
  }
}

export function boostIdleReward (repo, userId, runtime, epoch = nowEpoch(), ad = null) {
  const config = boostConfig(runtime)
  if (config.multiplier === null) return { ok: false, reason: 'boost-config-missing' }
  // `period` em SEGUNDOS: no wire `generation_period` é texto (formatDuration),
  // então a aritmética usa o número interno, nunca o campo do wire.
  const { period } = computeIdle(repo, userId, runtime, epoch)
  const state = idleRewardState(repo, userId, runtime, epoch)
  if (state.claimable_periods <= 0) return { ok: false, reason: 'not-ready' }
  if (ad === null && config.cooldown > 0) {
    const lastBoost = Number(repo.getState(userId, IDLE_NS, 'last_boost', 0) || 0)
    if (epoch - lastBoost < config.cooldown) return { ok: false, reason: 'boost-not-ready' }
  }

  const grants = []
  repo.tx(() => {
    if (ad !== null) consumeAdRewardToken(repo, userId, ad.tokens, ad.tokenId)
    for (const reward of state.idle_generation) {
      const amount = Number(reward?.amount ?? 0)
      if (!Number.isFinite(amount) || amount <= 0) continue
      const grant = giveGameResource(repo, userId, {
        ...reward,
        amount: Math.floor(amount * state.claimable_periods * config.multiplier)
      }, runtime)
      grants.push(grant.wire)
    }
    repo.setState(userId, IDLE_NS, 'last_claim', state.last_claim + state.claimable_periods * period)
    if (ad === null && config.cooldown > 0) repo.setState(userId, IDLE_NS, 'last_boost', epoch)
  })

  return { ok: true, resources: grants, periods: state.claimable_periods, multiplier: config.multiplier }
}
