import { applyBattlePassStatTotals } from './battle-pass.js'

const NS = 'player-stats'
const KEY = 'totals'

function statKey (value) {
  if (Number.isInteger(value)) return String(value)
  if (typeof value === 'string' && value.trim()) return value.trim()
  return null
}

function numericIncrement (value) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return null
  return parsed
}

export function normalizeStatIncrements (body) {
  const increments = new Map()
  const add = (keyValue, amountValue) => {
    const key = statKey(keyValue)
    const amount = numericIncrement(amountValue)
    if (key === null || amount === null) return
    increments.set(key, (increments.get(key) || 0) + amount)
  }

  const stats = body?.stats ?? body?.increments ?? body
  if (Array.isArray(stats)) {
    for (const row of stats) {
      if (!row || typeof row !== 'object') continue
      add(
        row.stat_id ?? row.stat?.id ?? row.id ?? row.tag ?? row.name,
        row.increment ?? row.amount ?? row.value ?? row.count
      )
    }
  } else if (stats && typeof stats === 'object') {
    for (const [key, value] of Object.entries(stats)) {
      if (value && typeof value === 'object') {
        add(
          value.stat_id ?? value.stat?.id ?? value.id ?? value.tag ?? key,
          value.increment ?? value.amount ?? value.value ?? value.count
        )
      } else {
        add(key, value)
      }
    }
  }

  return Object.fromEntries(increments)
}

export function playerStatTotals (repo, userId) {
  const saved = repo.getState(userId, NS, KEY, {})
  if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return {}

  const result = {}
  for (const [key, value] of Object.entries(saved)) {
    const parsed = Number(value)
    if (Number.isFinite(parsed) && parsed >= 0) result[key] = parsed
  }
  return result
}

export function playerStatsWire (repo, userId) {
  return Object.entries(playerStatTotals(repo, userId)).map(([id, value]) => {
    const numericId = Number(id)
    return {
      id: Number.isInteger(numericId) && String(numericId) === id ? numericId : id,
      value
    }
  })
}

export function incrementPlayerStats (repo, userId, body, runtime) {
  const increments = normalizeStatIncrements(body)
  const entries = Object.entries(increments)
  if (entries.length === 0) {
    return { totals: playerStatTotals(repo, userId), battle_pass_updates: [] }
  }

  const totals = playerStatTotals(repo, userId)
  for (const [key, amount] of entries) totals[key] = (Number(totals[key]) || 0) + amount

  repo.setState(userId, NS, KEY, totals)
  const battlePassUpdates = applyBattlePassStatTotals(repo, userId, runtime, totals)
  return { totals, battle_pass_updates: battlePassUpdates }
}
