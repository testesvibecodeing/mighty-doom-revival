import { resolveResource } from './config.js'

function utcBucket (period) {
  const d = new Date()
  if (period === 'daily') return d.toISOString().slice(0, 10)
  if (period === 'weekly') {
    const x = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()))
    x.setUTCDate(x.getUTCDate() - x.getUTCDay())
    return `week:${x.toISOString().slice(0, 10)}`
  }
  return 'lifetime'
}

function wireResource (entry, runtime) {
  const rid = resolveResource(entry.resource ?? entry.rid, runtime)
  const result = { rid }
  for (const key of ['amount', 'level', 'tier']) {
    if (entry[key] !== undefined) result[key] = entry[key]
  }
  return result
}

export function activePacks (runtime) {
  return runtime.packs.filter(x => x && x.active !== false && Number.isInteger(x.id))
}

export function packToStoreItem (pack, runtime) {
  if (pack.real_money || pack.iap || pack.price) {
    throw new Error(`Pacote ${pack.id} tentou usar preço/IAP real; bloqueado pelo Revival.`)
  }
  const cost = (pack.cost || []).map(entry => ({
    rid: resolveResource(entry.resource ?? entry.rid, runtime),
    amount: Number(entry.amount || 0)
  }))
  const resources = (pack.contents || []).map(entry => wireResource(entry, runtime))

  return {
    id: pack.id,
    tag: pack.tag || `revival_pack_${pack.id}`,
    contents: {
      display_type: pack.display_type ?? 0,
      priority: pack.priority ?? 0,
      resources,
      mystery_resources: [],
      reward_track_id: 0
    },
    cost,
    quota_id: pack.quota_id ?? null,
    requirements: {
      selector_format_version: 1,
      player: {
        userId: null,
        playerLevel: null,
        chapterProgress: null,
        storeQuotas: null,
        gear: null,
        slayers: null,
        entitlements: null,
        cosmetics: null,
        lastLogin: null,
        iapPurchases: null,
        device: null,
        firstInstall: null
      }
    }
  }
}

export function purchasePack (repo, userId, itemId, runtime) {
  const pack = activePacks(runtime).find(x => x.id === itemId)
  if (!pack) return { ok: false, reason: 'unknown-pack' }
  if (pack.real_money || pack.iap || pack.price) return { ok: false, reason: 'iap-disabled' }

  const period = pack.quota?.period || 'lifetime'
  const bucket = utcBucket(period)
  const max = Number.isInteger(pack.quota?.max) ? pack.quota.max : null
  if (max !== null && repo.purchaseCount(userId, itemId, bucket) >= max) {
    return { ok: false, reason: 'quota' }
  }

  const costs = (pack.cost || []).map(x => ({
    rid: resolveResource(x.resource ?? x.rid, runtime),
    amount: Number(x.amount || 0),
    kind: x.kind || 'currency'
  }))
  if (costs.some(x => x.kind !== 'currency' || x.amount < 0)) {
    return { ok: false, reason: 'invalid-cost' }
  }
  for (const cost of costs) {
    if (repo.balance(userId, cost.rid) < cost.amount) return { ok: false, reason: 'funds' }
  }

  const grants = []
  repo.tx(() => {
    for (const cost of costs) repo.addCurrency(userId, cost.rid, -cost.amount)

    for (const reward of (pack.contents || [])) {
      const rid = resolveResource(reward.resource ?? reward.rid, runtime)
      const kind = reward.kind || 'currency'
      const wire = wireResource(reward, runtime)
      if (kind === 'currency') {
        repo.addCurrency(userId, rid, Number(reward.amount || 0))
        grants.push(wire)
      } else {
        const uid = repo.addItem(userId, { ...wire, kind })
        grants.push({ ...wire, uid })
      }
    }
    repo.incrementPurchase(userId, itemId, bucket)
  })

  return { ok: true, resources: grants }
}
