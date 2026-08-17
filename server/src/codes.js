import { giveGameResource } from './game-data-model.js'

// ---- Contrato extraído do global-metadata.dat v29 (2026-08-17) ----
// CodesApi: Redeem(code) — 1 rota game/codes/redeem.
// Literal de wire no cliente (Nível 1): 'code'. Nenhum *Response DTO foi
// encontrado por nome nem campo de resposta confirmado -> wrapper
// A VERIFICAR; o padrão das concessões do jogo (PurchaseItemResponse/
// AdPurchaseResponse{resources}) é o candidato usado aqui.
// Códigos são configuráveis em gameData.codes [{code, resources}] com o
// mesmo shape de reward das daily rewards; resgate é 1x por jogador.

const NS = 'codes'
const KEY = 'redeemed'

function codeRows (runtime) {
  const rows = runtime?.gameData?.codes
  return Array.isArray(rows) ? rows : []
}

export function redeemCode (repo, userId, body, runtime) {
  const code = typeof body?.code === 'string' ? body.code.trim() : ''
  if (code.length === 0) return { error: [400, 2200, { reason: 'code-required' }] }

  const row = codeRows(runtime).find(entry => String(entry?.code ?? '').trim() === code)
  if (!row) return { error: [400, 2300, { reason: 'code-not-found' }] }

  const redeemed = repo.getState(userId, NS, KEY, [])
  if (Array.isArray(redeemed) && redeemed.includes(code)) {
    return { error: [400, 2300, { reason: 'code-already-redeemed' }] }
  }

  const grants = []
  repo.tx(() => {
    for (const reward of (Array.isArray(row.resources) ? row.resources : [])) {
      const grant = giveGameResource(repo, userId, reward, runtime)
      grants.push(grant.wire)
    }
    repo.setState(userId, NS, KEY, [...(Array.isArray(redeemed) ? redeemed : []), code])
  })
  return { data: { resources: grants } }
}
