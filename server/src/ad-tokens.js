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

// ---- game/ads/get-state -------------------------------------------------
// Medido no rig em 2026-08-21 (request_log 629): a resposta antiga
// `{ ads_disabled: true }` NAO tem o campo obrigatorio e o cliente estourou
//
//   NullReferenceException
//     at Ubu.Ads.AdController.ProcessAdState (AdState adState, bool suppressEvent)
//     at Ubu.Ads.AdController+<>c__DisplayClass44_0.<UpdateAdState>b__0 (AdApi+GetStateResponse response)
//
// travando o boot na tela de LOADING 100% — os 16 requests do boot voltavam
// 200/1000 e mesmo assim o menu nunca carregava.
//
// Contrato do global-metadata.dat v29 (nada aqui foi inventado):
//   AdApi.GetStateResponse { state }
//   AdState              { allotment, rewardTokens }
//   AdAllotment          { startEpoch, endEpoch, availableRewards }
//   AdRewardAmount       { rewardType, amount }
//   AdRewardToken        { id, rewardType, issuedEpoch, expireEpoch }
//
// Sem emissor de anuncios o estado honesto e uma janela diaria SEM recompensa
// disponivel e SEM token — nao e "sucesso falso": e dizer, no formato que o
// cliente sabe ler, que nao ha anuncio para assistir.
const DIA_EM_SEGUNDOS = 86400

export function adState (repo, userId, agora = nowSeconds()) {
  const inicio = Math.floor(agora / DIA_EM_SEGUNDOS) * DIA_EM_SEGUNDOS
  const salvos = repo.getState(userId, NS, KEY, [])
  const tokens = Array.isArray(salvos) ? salvos : []
  return {
    state: {
      allotment: {
        start_epoch: inicio,
        end_epoch: inicio + DIA_EM_SEGUNDOS
      },
      reward_tokens: tokens
    }
  }
}
