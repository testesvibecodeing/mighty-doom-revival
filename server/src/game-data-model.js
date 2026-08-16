import { resolveResource } from './config.js'
import {
  findById,
  findByTag,
  inventorySlots,
  resourceId,
  slayersList,
  weaponsList
} from './game-data-schema.js'

const CATEGORY_KIND = new Map([
  [1, 'currency'],
  [2, 'weapon'],
  [3, 'equipment'],
  [4, 'launcher'],
  [5, 'energy'],
  [6, 'ultimate'],
  [7, 'slayer'],
  [8, 'entitlement'],
  [9, 'cosmetic']
])

const COLLECTION_KIND = [
  ['weapons', 'weapon'],
  ['equipment', 'equipment'],
  ['launchers', 'launcher'],
  ['energies', 'energy'],
  ['ultimates', 'ultimate'],
  ['slayers', 'slayer'],
  ['entitlements', 'entitlement'],
  ['cosmetics', 'cosmetic']
]

function categoryId (definition) {
  if (!definition || typeof definition !== 'object') return null
  const candidates = [
    definition.category_id,
    definition.category,
    definition.resource_category_id,
    definition.resource_category,
    definition.type_id
  ]
  for (const candidate of candidates) {
    if (Number.isInteger(candidate)) return candidate
    if (candidate && typeof candidate === 'object') {
      if (Number.isInteger(candidate.id)) return candidate.id
      if (Number.isInteger(candidate.rid)) return candidate.rid
    }
  }
  return null
}

function inCollection (gameData, name, rid) {
  const list = gameData?.[name]
  return Array.isArray(list) && list.some(x => resourceId(x) === rid)
}

export function classifyResource (rid, runtime, explicitKind = null) {
  if (typeof explicitKind === 'string' && explicitKind.length > 0) return explicitKind

  const definition = runtime.index.byId.get(rid)
  const category = categoryId(definition)
  if (CATEGORY_KIND.has(category)) return CATEGORY_KIND.get(category)

  for (const [collection, kind] of COLLECTION_KIND) {
    if (inCollection(runtime.gameData, collection, rid)) return kind
  }

  if (inCollection(runtime.gameData, 'resources', rid)) return 'currency'
  return 'unknown'
}

function itemWire (rid, uid, entry) {
  const item = {
    uid,
    level: Number.isInteger(entry.level) ? entry.level : 1,
    cosmetic: null,
    rid
  }
  if (Number.isInteger(entry.tier)) item.tier = entry.tier
  return item
}

function energyDefinition (rid, runtime) {
  const list = runtime.gameData?.energies
  if (!Array.isArray(list)) return null
  return list.find(x => resourceId(x) === rid) || null
}

function normalizedEnergy (row, runtime) {
  const definition = energyDefinition(row.rid, runtime)
  const max = Number(definition?.max_amount ?? definition?.max ?? definition?.capacity ?? 0)
  const regenMinutes = Number(definition?.regen_minutes ?? definition?.regeneration_minutes ?? 0)
  let amount = Number(row.amount || 0)
  let regenEpoch = Number(row.regen_epoch || 0)

  if (max > 0 && regenMinutes > 0 && amount < max && regenEpoch > 0) {
    const now = Math.floor(Date.now() / 1000)
    const step = Math.max(1, Math.floor(regenMinutes * 60))
    if (now >= regenEpoch) {
      const gained = Math.floor((now - regenEpoch) / step) + 1
      amount = Math.min(max, amount + gained)
      regenEpoch = amount >= max ? 0 : regenEpoch + gained * step
    }
  }

  return { rid: row.rid, amount, regen_epoch: regenEpoch }
}

export function energyWireRows (repo, userId, runtime) {
  return repo.energies(userId).map(row => {
    const normalized = normalizedEnergy(row, runtime)
    if (normalized.amount !== row.amount || normalized.regen_epoch !== row.regen_epoch) {
      repo.setEnergy(userId, row.rid, normalized.amount, normalized.regen_epoch)
    }
    return normalized
  })
}

export function giveGameResource (repo, userId, entry, runtime) {
  const rid = resolveResource(entry.resource ?? entry.rid, runtime)
  const kind = classifyResource(rid, runtime, entry.kind)
  const amount = Number.isFinite(Number(entry.amount)) ? Math.floor(Number(entry.amount)) : 1

  if (kind === 'currency') {
    const next = repo.addCurrency(userId, rid, amount)
    return { kind, wire: { rid, amount: next } }
  }

  if (kind === 'energy') {
    const current = repo.energy(userId, rid) || { amount: 0, regen_epoch: 0 }
    const definition = energyDefinition(rid, runtime)
    const max = Number(definition?.max_amount ?? definition?.max ?? definition?.capacity ?? 0)
    const regenMinutes = Number(definition?.regen_minutes ?? definition?.regeneration_minutes ?? 0)
    let next = current.amount + amount
    if (max > 0) next = Math.min(max, next)
    const now = Math.floor(Date.now() / 1000)
    const regenEpoch = max > 0 && next < max && regenMinutes > 0
      ? (current.regen_epoch || now + Math.floor(regenMinutes * 60))
      : 0
    repo.setEnergy(userId, rid, Math.max(0, next), regenEpoch)
    return { kind, wire: { rid, amount: Math.max(0, next), regen_epoch: regenEpoch } }
  }

  if (kind === 'cosmetic') {
    repo.addCosmetic(userId, rid)
    return { kind, wire: { rid } }
  }

  if (kind === 'entitlement') {
    repo.addEntitlement(userId, rid)
    return { kind, wire: { rid } }
  }

  if (['weapon', 'equipment', 'launcher', 'ultimate', 'slayer'].includes(kind)) {
    const uid = repo.addItem(userId, {
      rid,
      kind,
      level: Number.isInteger(entry.level) ? entry.level : 1,
      tier: Number.isInteger(entry.tier) ? entry.tier : null,
      amount: Math.max(1, amount),
      metadata: entry.metadata || {}
    })
    return { kind, uid, wire: itemWire(rid, uid, entry) }
  }

  throw new Error(`Categoria de recurso desconhecida para rid=${rid}`)
}

function compatibleStarterGrant (grants, kind, definitions, slot) {
  const candidates = grants.filter(grant => grant.kind === kind && Number.isInteger(grant.uid))
  if (candidates.length === 0) return null
  if (!slot || slot.type === undefined || slot.type === null) return candidates[0]

  const compatible = candidates.find(grant => {
    const definition = findById(definitions, grant.wire?.rid)
    return definition && definition.slot === slot.type
  })

  return compatible || null
}

export function seedStarterBundle (repo, userId, runtime) {
  const gameData = runtime.gameData
  if (!gameData) return { seeded: false, reason: 'game-data-missing', grants: [] }

  const starterEnabled = Number(gameData?.server_properties?.starter_bundle ?? 1) > 0
  if (!starterEnabled) return { seeded: false, reason: 'disabled-by-game-data', grants: [] }

  const bundle = findByTag(gameData.bundles, 'starter')
  if (!bundle || !Array.isArray(bundle.resources)) {
    return { seeded: false, reason: 'starter-bundle-not-found', grants: [] }
  }

  const slots = inventorySlots(gameData)
  const primarySlot = findByTag(slots, 'slot_primary_weapon')
  const slayerSlot = findByTag(slots, 'slot_slayer')
  if (!primarySlot || !slayerSlot) {
    return { seeded: false, reason: 'required-starter-slot-missing', grants: [] }
  }

  const grants = []
  repo.tx(() => {
    for (const resource of bundle.resources) {
      grants.push(giveGameResource(repo, userId, resource, runtime))
    }

    const weapon = compatibleStarterGrant(grants, 'weapon', weaponsList(gameData), primarySlot)
    const slayer = compatibleStarterGrant(grants, 'slayer', slayersList(gameData), slayerSlot)

    if (!weapon) throw new Error(`Starter sem arma compatível com slot ${primarySlot.type ?? primarySlot.id}`)
    if (!slayer) throw new Error(`Starter sem Slayer compatível com slot ${slayerSlot.type ?? slayerSlot.id}`)

    const primarySlotId = resourceId(primarySlot)
    const slayerSlotId = resourceId(slayerSlot)
    if (!Number.isInteger(primarySlotId) || !Number.isInteger(slayerSlotId)) {
      throw new Error('Slots obrigatórios do starter não possuem id/rid válido')
    }

    if (!repo.setSlot(userId, primarySlotId, weapon.uid)) throw new Error('Falha ao equipar arma starter')
    if (!repo.setSlot(userId, slayerSlotId, slayer.uid)) throw new Error('Falha ao equipar Slayer starter')
  })

  return { seeded: true, grants }
}

export function inventoryWire (repo, userId, runtime) {
  const inventory = {
    currencies: repo.currencies(userId),
    weapons: [],
    equipment: [],
    launchers: [],
    energies: energyWireRows(repo, userId, runtime),
    ultimates: [],
    slayers: [],
    entitlements: repo.entitlements(userId).map(x => ({ rid: x.rid })),
    slots: repo.slots(userId).map(x => ({ id: x.slot_id, item: x.item_id })),
    cosmetics: repo.cosmetics(userId).map(x => ({ rid: x.rid }))
  }

  const buckets = {
    weapon: 'weapons',
    equipment: 'equipment',
    launcher: 'launchers',
    ultimate: 'ultimates',
    slayer: 'slayers'
  }

  for (const item of repo.items(userId)) {
    const target = buckets[item.kind]
    if (!target) continue
    const wire = {
      uid: item.id,
      level: item.level,
      cosmetic: null,
      rid: item.rid
    }
    if (item.tier !== null) wire.tier = item.tier
    inventory[target].push(wire)
  }

  return inventory
}
