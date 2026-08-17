import { resolveResource } from './config.js'
import { giveGameResource } from './game-data-model.js'
import { consumeAdRewardToken, findAdRewardToken } from './ad-tokens.js'

// ---- Contrato extraído do global-metadata.dat v29 (2026-08-17) ----
// StoreApi: GetItems(), Get(), PurchaseItem(itemId), AdPurchaseItem(itemId,
// rewardTokenId), GetPlayerOffers(), GetOfferItems(), GetOffers(),
// ActivateOffer(offerId, gearResourceId), GetDailyOffers(),
// ActivateDailyOffers().
// Response DTOs (campos confirmados; snake fallback):
//   GetItemsResponse/GetOfferItemsResponse{storeItems, iapItems, adItems}
//   GetOffersResponse{idem + offers}
//   PurchaseItemResponse/AdPurchaseResponse{resources}
//   GetPlayerOffersResponse{offers}
//   ActivateOfferResponse{offer} — offer = PlayerOfferModel{id,
//     offerDefinitionId, itemId, allowedPurchases, purchaseAmount, startTime,
//     endTime, altResources, targetedOfferType, offerGroup, apiVersion}
// AdRewardType extraído: StoreItemCrate/StoreItemGold são os tipos de token
// do ad-purchase. A VERIFICAR até captura do cliente: nomes request
// (item_id/reward_token_id/offer_id/gear_resource_id).

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
  if (costs.some(x => x.kind !== 'currency' || !Number.isFinite(x.amount) || x.amount < 0)) {
    return { ok: false, reason: 'invalid-cost' }
  }
  for (const cost of costs) {
    if (repo.balance(userId, cost.rid) < cost.amount) return { ok: false, reason: 'funds' }
  }

  const grants = []
  repo.tx(() => {
    for (const cost of costs) repo.addCurrency(userId, cost.rid, -cost.amount)

    for (const reward of (pack.contents || [])) {
      const grant = giveGameResource(repo, userId, reward, runtime)
      grants.push(grant.wire)
    }
    repo.incrementPurchase(userId, itemId, bucket)
  })

  return { ok: true, resources: grants }
}

// ---- Rotas GetItems/GetOfferItems/GetPlayerOffers/ActivateOffer/AdPurchase ----

function adPacks (runtime) {
  return activePacks(runtime).filter(pack => pack.ad === true)
}

function currencyPacks (runtime) {
  return activePacks(runtime).filter(pack => pack.ad !== true)
}

export function storeItemsWire (runtime) {
  // GetItemsResponse/GetOfferItemsResponse{storeItems, iapItems, adItems};
  // IAP desligado por design no Revival — iap_items sempre vazio. Pacote cuja
  // tag ainda não resolve para rid (game-data ausente) fica de fora do wire
  // até o game-data carregar — o painel continua exibindo via preview.
  const wireable = packs => packs
    .map(pack => {
      try {
        return packToStoreItem(pack, runtime)
      } catch {
        return null
      }
    })
    .filter(Boolean)
  return {
    store_items: wireable(currencyPacks(runtime)),
    iap_items: [],
    ad_items: wireable(adPacks(runtime))
  }
}

function offerRows (runtime) {
  const offers = runtime?.gameData?.store?.offers ?? runtime?.gameData?.offers
  return Array.isArray(offers) ? offers : []
}

function asInt (value) {
  return Number.isInteger(value) ? value : null
}

function nowSeconds () {
  return Math.floor(Date.now() / 1000)
}

function asEpoch (value) {
  if (value === null || value === undefined) return null
  if (typeof value === 'number') return value
  const n = Date.parse(value)
  if (Number.isNaN(n)) return null
  return Math.floor(n / 1000)
}

// PlayerOfferModel no wire (mesmo shape do ActivateStoreOfferEventResponse).
export function storeOfferWire (row, activatedAt) {
  const definitionId = asInt(row?.offer_definition_id) ?? asInt(row?.id)
  const wire = {
    id: asInt(row?.id),
    offer_definition_id: definitionId,
    item_id: asInt(row?.item_id),
    allowed_purchases: asInt(row?.allowed_purchases) ?? 1,
    start_time: activatedAt
  }
  const endTime = asEpoch(row?.end_time)
  if (endTime !== null) wire.end_time = endTime
  const purchaseAmount = asInt(row?.purchase_amount)
  if (purchaseAmount !== null) wire.purchase_amount = purchaseAmount
  if (Array.isArray(row?.alt_resources) && row.alt_resources.length > 0) wire.alt_resources = row.alt_resources
  if (row?.targeted_offer_type != null) wire.targeted_offer_type = row.targeted_offer_type
  if (row?.offer_group != null) wire.offer_group = row.offer_group
  if (row?.api_version != null) wire.api_version = row.api_version
  return wire
}

export function activatedOfferWires (repo, userId, runtime) {
  const saved = repo.getState(userId, 'store', 'activated_offers', {})
  const rows = saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {}
  return Object.entries(rows)
    .map(([id, activation]) => {
      const row = offerRows(runtime).find(offer => String(asInt(offer?.id)) === id)
      if (!row) return null
      return storeOfferWire(row, asInt(activation?.activated_at) ?? 0)
    })
    .filter(Boolean)
}

export function activateStoreOffer (repo, userId, body, runtime) {
  const offerId = asInt(body?.offer_id ?? body?.offerId)
  const gearResourceId = asInt(body?.gear_resource_id ?? body?.gearResourceId)
  if (offerId === null) return { error: [400, 2200, { reason: 'offer-id-required' }] }
  const row = offerRows(runtime).find(offer => asInt(offer?.id) === offerId)
  if (!row) return { error: [400, 2200, { reason: 'offer-not-found' }] }
  if (asInt(row.item_id) === null) return { error: [400, 2300, { reason: 'offer-config-missing' }] }
  // ActivateOffer(offerId, gearResourceId): offers direcionados (Fusion)
  // exigem o gear; sem targeted_offer_type o campo é opcional no servidor.
  if (row.targeted_offer_type != null && gearResourceId === null) {
    return { error: [400, 2200, { reason: 'gear-resource-id-required' }] }
  }
  const activatedAt = nowSeconds()
  const saved = repo.getState(userId, 'store', 'activated_offers', {})
  const rows = saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {}
  rows[String(offerId)] = { activated_at: activatedAt, gear_resource_id: gearResourceId }
  repo.setState(userId, 'store', 'activated_offers', rows)
  return { data: { offer: storeOfferWire(row, activatedAt) } }
}

// AdPurchaseItem(itemId, rewardTokenId): compra de item de anúncio — consome
// um AdRewardToken StoreItemCrate/StoreItemGold em vez de moeda.
export function adPurchasePack (repo, userId, body, runtime) {
  const itemId = asInt(body?.item_id ?? body?.itemId)
  const tokenId = asInt(body?.reward_token_id ?? body?.rewardTokenId)
  if (itemId === null) return { error: [400, 2200, { reason: 'item-id-required' }] }
  const pack = activePacks(runtime).find(x => x.id === itemId)
  if (!pack) return { error: [400, 2200, { reason: 'unknown-pack' }] }
  if (pack.ad !== true) return { error: [400, 2300, { reason: 'not-ad-item' }] }

  let found = findAdRewardToken(repo, userId, tokenId, 'store_item_crate')
  if (found.error) found = findAdRewardToken(repo, userId, tokenId, 'store_item_gold')
  if (found.error) return { error: found.error }

  const grants = []
  repo.tx(() => {
    consumeAdRewardToken(repo, userId, found.tokens, tokenId)
    for (const reward of (pack.contents || [])) {
      const grant = giveGameResource(repo, userId, reward, runtime)
      grants.push(grant.wire)
    }
    repo.incrementPurchase(userId, itemId, utcBucket(pack.quota?.period || 'lifetime'))
  })
  return { data: { resources: grants } }
}
