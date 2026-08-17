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

function setItemLevel (repo, userId, itemId, level) {
  if (typeof repo.updateItemLevel === 'function') return repo.updateItemLevel(userId, itemId, level)
  const result = repo.db.prepare('UPDATE items SET level = ? WHERE user_id = ? AND id = ?').run(level, userId, itemId)
  if (result.changes !== 1) throw new Error('item-update-failed')
}

function itemMetadata (item) {
  try { return JSON.parse(item.metadata_json || '{}') } catch { return {} }
}

function wireItem (item) {
  const result = { uid: item.id, rid: item.rid, level: item.level }
  if (item.tier !== null && item.tier !== undefined) result.tier = item.tier
  const cosmeticId = int(itemMetadata(item).cosmetic_id)
  if (cosmeticId !== null) result.cosmetic_id = cosmeticId
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
    setItemLevel(repo, userId, itemId, level)
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

// ---- Contrato extraído do global-metadata.dat v29 (2026-08-17) ----
// GearApi.Upgrade(gearUid)                        -> game/gear/upgrade         {gear_uid}
// GearApi.MultiUpgrade(gearUid, levelsToUpgrade)  -> game/gear/multi-upgrade   {gear_uid, levels_to_upgrade}
// GearApi.Fuse(inputUids)                         -> game/gear/fuse           {input_uids}
// GearApi.Dismantle(gearUid)                      -> game/gear/dismantle      {gear_uid}
// GearApi.ApplyCosmetic(gearUid, cosmeticId)      -> game/gear/apply-cosmetic {gear_uid, cosmetic_id}
// SlayerApi.Upgrade(slayerUid)                    -> game/slayers/upgrade     {slayer_uid}
// SlayerApi.ApplyCosmetic(slayerUid, cosmeticId)  -> game/slayers/apply-cosmetic {slayer_uid, cosmetic_id}
// Nomes de wire: levels_to_upgrade/cosmetic_id/talent_id são literais do
// metadata (overrides [JsonProperty] confirmados); gear_uid/slayer_uid/
// input_uids vêm do fallback SnakeCaseNamingStrategy (A VERIFICAR até a
// captura do request real no cliente — aliases legados continuam aceitos).
const GEAR_KINDS = ['weapon', 'equipment', 'launcher', 'ultimate']

function gearUidFromBody (body) {
  return int(body?.gear_uid) ?? int(body?.gearUid) ?? int(body?.uid) ?? int(body?.item)
}

function slayerUidFromBody (body) {
  return int(body?.slayer_uid) ?? int(body?.slayerUid) ?? int(body?.uid) ?? int(body?.slayer)
}

function nextGearUpgradeSequence (repo, userId) {
  const previous = repo.getState(userId, 'gear', 'upgrade_sequence_id', 0)
  repo.setState(userId, 'gear', 'upgrade_sequence_id', previous + 1)
  return previous + 1
}

// game-data opcional: gear_fusion = { input_count: N, tier_gain: N, cost: [...] }
function fusionConfig (runtime) {
  const raw = runtime.gameData?.gear_fusion ?? runtime.gameData?.fusion
  if (!raw || typeof raw !== 'object') return null
  const inputCount = int(raw.input_count ?? raw.count) ?? 2
  const tierGain = int(raw.tier_gain ?? raw.tier) ?? 1
  if (inputCount < 2 || tierGain < 1) return null
  return { inputCount, tierGain, cost: normalizeCostEntries(raw.cost) }
}

// game-data opcional: dismantle = { tiers: { "<tier>": [{resource, amount}] } }
function dismantleRefunds (runtime, tier) {
  const raw = runtime.gameData?.dismantle ?? runtime.gameData?.gear_dismantle
  const table = raw?.tiers ?? raw
  if (!table || typeof table !== 'object') return null
  const entry = table[String(tier)] ?? table.default
  const entries = normalizeCostEntries(entry)
  return entries.length > 0 ? normalizedCosts(entries, runtime) : null
}

function fuseGear (repo, userId, body, runtime) {
  const config = fusionConfig(runtime)
  if (!config) return { ok: false, code: 2300, reason: 'fusion-config-missing' }
  const uids = Array.isArray(body?.input_uids) ? body.input_uids : (Array.isArray(body?.inputUids) ? body.inputUids : null)
  if (!uids) return { ok: false, code: 2200, reason: 'invalid-input-uids' }
  const items = uids.map(uid => repo.itemById(userId, int(uid)))
  if (items.some(item => !item)) return { ok: false, code: 2000, reason: 'item-not-found' }
  if (items.some(item => !GEAR_KINDS.includes(item.kind))) return { ok: false, code: 2000, reason: 'not-gear' }
  if (items.length < config.inputCount) return { ok: false, code: 2200, reason: 'insufficient-inputs' }
  const reference = items[0]
  if (items.some(item => item.rid !== reference.rid || item.level !== reference.level || item.tier !== reference.tier)) {
    return { ok: false, code: 2200, reason: 'inputs-mismatched' }
  }
  const costs = normalizedCosts(config.cost, runtime)
  if (costs.length > 0 && !debitCosts(repo, userId, costs)) return { ok: false, code: 2000, reason: 'funds' }
  for (const item of items) {
    if (!repo.deleteItem(userId, item.id)) return { ok: false, code: 2000, reason: 'item-delete-failed' }
  }
  const fusedId = repo.addItem(userId, {
    rid: reference.rid,
    kind: reference.kind,
    level: reference.level,
    tier: (reference.tier ?? 0) + config.tierGain
  })
  return { ok: true, gear: wireItem(repo.itemById(userId, fusedId)) }
}

function dismantleGear (repo, userId, body, runtime) {
  const uid = gearUidFromBody(body)
  if (!Number.isInteger(uid)) return { ok: false, code: 2200, reason: 'invalid-item' }
  const item = repo.itemById(userId, uid)
  if (!item) return { ok: false, code: 2000, reason: 'item-not-found' }
  if (!GEAR_KINDS.includes(item.kind)) return { ok: false, code: 2000, reason: 'not-gear' }
  const refunds = dismantleRefunds(runtime, item.tier ?? 0)
  if (refunds === null) return { ok: false, code: 2300, reason: 'dismantle-config-missing' }
  if (!repo.deleteItem(userId, uid)) return { ok: false, code: 2000, reason: 'item-delete-failed' }
  for (const refund of refunds) repo.addCurrency(userId, refund.rid, refund.amount)
  return { ok: true, gear: wireItem(item), resources: refunds }
}

function applyCosmetic (repo, userId, body, isSlayer) {
  const uid = isSlayer ? slayerUidFromBody(body) : gearUidFromBody(body)
  const cosmeticId = int(body?.cosmetic_id) ?? int(body?.cosmeticId)
  if (!Number.isInteger(uid)) return { ok: false, code: 2200, reason: 'invalid-item' }
  if (!Number.isInteger(cosmeticId)) return { ok: false, code: 2200, reason: 'invalid-cosmetic' }
  const item = repo.itemById(userId, uid)
  if (!item) return { ok: false, code: 2000, reason: 'item-not-found' }
  if (isSlayer ? item.kind !== 'slayer' : !GEAR_KINDS.includes(item.kind)) {
    return { ok: false, code: 2000, reason: isSlayer ? 'not-slayer' : 'not-gear' }
  }
  if (!asArray(repo.cosmetics(userId)).some(row => int(row.rid) === cosmeticId)) {
    return { ok: false, code: 2000, reason: 'cosmetic-not-owned' }
  }
  const metadata = itemMetadata(item)
  metadata.cosmetic_id = cosmeticId
  if (typeof repo.updateItemMetadata !== 'function' || !repo.updateItemMetadata(userId, uid, metadata)) {
    return { ok: false, code: 2000, reason: 'item-update-failed' }
  }
  const key = isSlayer ? 'slayer' : 'gear'
  return { ok: true, [key]: wireItem(repo.itemById(userId, uid)) }
}

export function handleProgressionRequest (path, body, userId, repo, runtime) {
  // TalentsApi só tem Buy no cliente 1.13.1: a leitura vem do
  // talent_progression do user-data (user-data.js usa talentsWire daqui).
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

  if (path === '/game/gear/fuse' || path === '/game/gear/dismantle' ||
      path === '/game/gear/apply-cosmetic' || path === '/game/slayers/apply-cosmetic') {
    let operation
    if (path === '/game/gear/fuse') operation = fuseGear(repo, userId, body, runtime)
    else if (path === '/game/gear/dismantle') operation = dismantleGear(repo, userId, body, runtime)
    else operation = applyCosmetic(repo, userId, body, path === '/game/slayers/apply-cosmetic')
    if (!operation.ok) return { error: [400, operation.code ?? 2000, { reason: operation.reason }] }
    const { ok, code, reason, ...wire } = operation
    return { data: wire }
  }

  const isGearUpgrade = path === '/game/gear/upgrade' || path === '/game/gear/multi-upgrade'
  const isSlayerUpgrade = path === '/game/slayers/upgrade'
  if (!isGearUpgrade && !isSlayerUpgrade) return null
  const itemId = isSlayerUpgrade ? slayerUidFromBody(body) : gearUidFromBody(body)
  if (!Number.isInteger(itemId)) return { error: [400, 2200, { reason: 'invalid-item' }] }
  const current = repo.itemById(userId, itemId)
  if (!current) return { error: [400, 2000, { reason: 'item-not-found' }] }
  if (isSlayerUpgrade && current.kind !== 'slayer') return { error: [400, 2000, { reason: 'not-slayer' }] }
  // Upgrade sobe exatamente 1 nível; MultiUpgrade sobe levels_to_upgrade.
  const levels = int(body?.levels_to_upgrade) ?? int(body?.levelsToUpgrade) ?? int(body?.levels) ?? int(body?.amount) ?? 1
  const requestedTarget = int(body?.target_level) ?? int(body?.level)
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
  if (isSlayerUpgrade) return { data: { slayer: result.item } }
  return { data: { gear: result.item, gear_upgrade_sequence_id: nextGearUpgradeSequence(repo, userId) } }
}
