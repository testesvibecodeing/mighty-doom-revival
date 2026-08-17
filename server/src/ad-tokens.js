// ---- Contrato extraído do global-metadata.dat v29 (2026-08-17) ----
// AdRewardToken{id, rewardType, issuedEpoch, expireEpoch} em
// Ubu.GameApi.DataObjects.Ads; AdRewardType:
//   None, Revive, IdleRewardBoost, StoreItemCrate, StoreItemGold,
//   AbilityReroll, StoreDailyOffer
// O emissor é o fluxo de anúncios (game/ads/*, fora de escopo); os
// consumidores (chapters, events, idle-rewards, store) validam e consomem
// via este helper. Estado em repo.getState(userId, 'ads', 'reward_tokens')
// como array de tokens no wire do AdRewardToken (snake_case).
//
// Sem emissor ativo o estado honesto é o erro explícito — nunca sucesso falso.

const NS = 'ads'
const KEY = 'reward_tokens'

function nowSeconds () {
  return Math.floor(Date.now() / 1000)
}

// Valida existência/tipo/validade sem consumir; o consumo (consumeAdRewardToken)
// fica a cargo do chamador dentro da própria transação.
export function findAdRewardToken (repo, userId, tokenId, expectedType) {
  if (!Number.isInteger(tokenId)) return { error: [400, 2200, { reason: 'reward-token-required' }] }
  const saved = repo.getState(userId, NS, KEY, [])
  const tokens = Array.isArray(saved) ? saved : []
  const token = tokens.find(row => Number.isInteger(row?.id) && row.id === tokenId)
  if (!token) return { error: [400, 2300, { reason: 'reward-token-not-found' }] }
  if ((token.reward_type ?? token.type) !== expectedType) {
    return { error: [400, 2300, { reason: 'reward-token-type-mismatch' }] }
  }
  if (Number.isInteger(token.expire_epoch) && token.expire_epoch < nowSeconds()) {
    return { error: [400, 2300, { reason: 'reward-token-expired' }] }
  }
  return { token, tokens }
}

export function consumeAdRewardToken (repo, userId, tokens, tokenId) {
  repo.setState(userId, NS, KEY, tokens.filter(row => row?.id !== tokenId))
}
