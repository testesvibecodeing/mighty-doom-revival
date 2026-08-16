import { equipmentList, findById, slayersList, talentsList, weaponsList, launchersList, ultimatesList } from './game-data-schema.js'
import { resolveResource } from './config.js'

function asArray (value) { return Array.isArray(value) ? value : [] }
function int (value) { return Number.isInteger(value) ? value : null }

function itemDefinition (item, runtime) {
  const collections = item.kind === 'weapon' ? [weaponsList(runtime.gameData)]
    : item.kind === 'equipment' ? [equipmentList(runtime.gameData)]
      : item.kind === 'launcher' ? [launchersList(runtime.gameData)]
        : item.kind === 'ultimate' ? [ultimatesList(runtime.gameData)]
          : item.kind === 'slayer' ? [slayersList(runtime.gameData)]
            : [weaponsList(runtime.gameData), equipmentList(runtime.gameData), launchersList(runtime.gameData), ultimatesList(runtime.gameData), slayersList(runtime.gameData)]
  for (const list of collections) {
    const found = findById(list, item.rid)
    if (found) return found
  }
  return runtime.index?.byId?.get(item.rid) || null
}

function maxLevel (definition, item, user) {
  const candidates = [definition?.max_level, definition?.level_cap, definition?.maxLevel, definition?.levels?.length]
  for (const value of candidates) if (Number.isInteger(value) && value > 0) return value
  if (item.kind === 'slayer' && Number.isInteger(user?.level) && user.level > 0) return user.level
  return null
}

function normalizeCostEntries (value) {
  if (!value) return []
  if (Array.isArray(value)) return value
  if (typeof value === 'object') return Object.entries(value).map(([resource, amount]) => ({ resource, amount }))
  return []
}

function costForLevel (definition, targetLevel) {
  const arrays = [definition?.upgrade_costs, definition?.level_costs, definition?.levels, definition?.upgrades]
  for (const list of arrays) {
    if (!Array.isArray(list) || list.length === 0) continue
    let entry = list.find(x => x && typeof x === 'object' && (x.level === targetLevel || x.target_level === targetLevel))
    if (!entry) entry = list[targetLevel - 2] ?? list[targetLevel - 1]
    if (!entry) continue
    const raw = entry.cost ?? entry.costs ?? entry.resources ?? entry.requirements ?? entry.upgrade_cost
    const costs = normalizeCostEntries(raw)
    if (costs.length > 0) return costs
  }
  const direct = definition?.upgrade_cost ?? definition?.cost
  const costs = normalizeCostEntries(direct)
  return costs.length > 0 ? costs : null
}

function normalizedCosts (costs, runtime) {
  return costs.map(entry => ({
    rid: resolveResource(entry.resource ?? entry.rid ?? entry.id, runtime),
    amount: Math.max(0, Math.floor(Number(entry.amount ?? entry.value ?? entry.count ?? 0)))
  })).filter(entry => entry.amount > 0)
}

function debitCosts (repo, userId, costs) {
  for (const cost of costs) if (repo.balance(userId, cost.rid) < cost.amount) return false
  for (const cost of costs) repo.addCurrency(userId, cost.rid, -cost.amount)
  return true
}

function wireItem (item) {
  const result = { uid: item.id, rid: item.rid, level: item.level }
  if (item.tier !== null && item.tier !== undefined) result.tier = item.tier
  return result
}

function upgradeItemTo (repo, userId, itemId, targetLevel, runtime) {
  const item = repo.itemById(userId, itemId)
  if (!item) return { ok: false, reason: 'item-not-found' }
  if (!['weapon', 'equipment', 'launcher', 'ultimate', 'slayer'].includes(item.kind)) return { ok: false, reason: 'not-upgradeable' }
  if (!Number.isInteger(targetLevel) || targetLevel <= item.level) return { ok: false, reason: 'invalid-target-level' }
  const definition = itemDefinition(item, runtime)
  if (!definition) return { ok: false, reason: 'definition-not-found' }
  const user = repo.userById(userId)
  const cap = maxLevel(definition, item, user)
  if (cap !== null && targetLevel > cap) return { ok: false, reason: 'level-cap' }

  const spent = []
  for (let level = item.level + 1; level <= targetLevel; level++) {
    const rawCosts = costForLevel(definition, level)
    if (!rawCosts) return { ok: false, reason: 'upgrade-cost-missing', level }
    const costs = normalizedCosts(rawCosts, runtime)
    if (costs.length === 0) return { ok: false, reason: 'upgrade-cost-empty', level }
    if (!debitCosts(repo, userId, costs)) return { ok: false, reason: 'funds', level }
    spent.push(...costs)
    repo.updateItemLevel(userId, itemId, level)
  }
  return { ok: true, item: wireItem(repo.itemById(userId, itemId)), spent }
}

function talentIdFromBody (body) {
  return int(body?.talent) ?? int(body?.talent_id) ?? int(body?.id)
}

function talentCosts (talent, runtime) {
  const raw = talent?.cost ?? talent?.costs ?? talent?.resources ?? talent?.requirements
  const entries = normalizeCostEntries(raw)
  return entries.length > 0 ? normalizedCosts(entries, runtime) : null
}

function buyTalent (repo, userId, body, runtime) {
  const talentId = talentIdFromBody(body)
  if (!Number.isInteger(talentId)) return { ok: false, reason: 'invalid-talent' }
  const talent = findById(talentsList(runtime.gameData), talentId)
  if (!talent) return { ok: false, reason: 'talent-not-found' }
  const owned = asArray(repo.getState(userId, 'talents', 'owned', []))
  if (owned.includes(talentId)) return { ok: false, reason: 'already-owned' }
  const prerequisites = asArray(talent.requires ?? talent.prerequisites ?? talent.dependencies)
    .map(x => int(x?.id ?? x?.rid ?? x))
    .filter(Number.isInteger)
  if (prerequisites.some(id => !owned.includes(id))) return { ok: false, reason: 'prerequisite' }
  const costs = talentCosts(talent, runtime)
  if (!costs) return { ok: false, reason: 'talent-cost-missing' }
  if (!debitCosts(repo, userId, costs)) return { ok: false, reason: 'funds' }
  const next = [...owned, talentId]
  repo.setState(userId, 'talents', 'owned', next)
  return { ok: true, talent: talentId, talents: next, spent: costs }
}

export function talentsWire (repo, userId) {
  return { talents: asArray(repo.getState(userId, 'talents', 'owned', [])) }
}

export function handleProgressionRequest (path, body, userId, repo, runtime) {
  if (path === '/game/talents/get') return { data: talentsWire(repo, userId) }
  if (path === '/game/talents/buy') {
    let result
    try {
      repo.tx(() => {
        result = buyTalent(repo, userId, body, runtime)
        if (!result.ok) throw Object.assign(new Error(result.reason), { result })
      })
    } catch (error) {
      const failure = error.result || { reason: error.message }
      return { error: [400, 2000, failure] }
    }
    return { data: result }
  }

  const isGear = path === '/game/gear/upgrade' || path === '/game/gear/multi-upgrade'
  const isSlayer = path === '/game/slayers/upgrade'
  if (!isGear && !isSlayer) return null
  const itemId = int(body?.item) ?? int(body?.item_id) ?? int(body?.uid) ?? int(body?.slayer)
  if (!Number.isInteger(itemId)) return { error: [400, 2200, { reason: 'invalid-item' }] }
  const current = repo.itemById(userId, itemId)
  if (!current) return { error: [400, 2000, { reason: 'item-not-found' }] }
  if (isSlayer && current.kind !== 'slayer') return { error: [400, 2000, { reason: 'not-slayer' }] }
  const requestedTarget = int(body?.target_level) ?? int(body?.level)
  const levels = int(body?.levels) ?? int(body?.amount) ?? 1
  const target = requestedTarget ?? (current.level + Math.max(1, levels))
  let result
  try {
    repo.tx(() => {
      result = upgradeItemTo(repo, userId, itemId, target, runtime)
      if (!result.ok) throw Object.assign(new Error(result.reason), { result })
    })
  } catch (error) {
    const failure = error.result || { reason: error.message }
    return { error: [400, 2000, failure] }
  }
  return { data: { item: result.item, spent: result.spent } }
}
