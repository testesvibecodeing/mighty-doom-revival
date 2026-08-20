// A regra do wire que mais derruba o boot, em um módulo puro.
//
// Vive fora do index.js de propósito: importar o index sobe o servidor como
// efeito colateral, e esta regra precisa ser testável isolada
// (server/test/wire.mjs).

/**
 * Impede que valor NÃO-FINITO (`NaN`, `Infinity`) chegue ao wire como `null`.
 *
 * Escopo ESTREITO de propósito. A versão anterior removia todo `null` de todo
 * payload, o que passava por cima de contrato em vez de conhecê-lo: a regra do
 * projeto proíbe `null` em campo numérico NÃO-nullable (AGENTS.md regra 6,
 * DEAD-ENDS #3) — ela não autoriza sumir com todo campo referencial nullable
 * dos 116 contratos.
 *
 * Auditoria dos `null` que o servidor realmente emite (medida no request_log do
 * rig em 2026-08-20). Todos apareceram em boots que COMPLETARAM antes desta
 * função existir, ou seja, o cliente os aceita:
 *
 *   playfab_session_ticket   auth/register, auth/login-device   string nullable
 *   cosmetic, current_run,
 *   player_settings          player/user-data                   referência nullable
 *   quota_id, device, gear,
 *   slayers, cosmetics,
 *   entitlements             store/get (seletor de requisitos)  referência nullable
 *
 * O único que quebrava era `generation_period`, e ele foi corrigido NA ORIGEM
 * (`rewards.js`: o game-data traz `'0D00H05M00S'`, `Number(...)` disso é NaN, e
 * `JSON.stringify(NaN)` emite `null`). É exatamente esse caso — valor numérico
 * que vira `null` sem ninguém ter escrito `null` — que esta função continua
 * cobrindo, para toda rota, inclusive as que ainda não existem.
 *
 * ARRAY preserva posição: elemento não-finito vira `null` em vez de sumir,
 * porque removê-lo deslocaria o índice de todos os seguintes.
 */
export function stripNulls (valor) {
  if (Array.isArray(valor)) return valor.map(item => {
    const limpo = stripNulls(item)
    return limpo === undefined ? null : limpo
  })
  if (valor === null || valor === undefined) return valor
  if (typeof valor === 'number') return Number.isFinite(valor) ? valor : undefined
  if (typeof valor !== 'object') return valor
  if (valor instanceof Date) return valor
  const saida = {}
  for (const [chave, item] of Object.entries(valor)) {
    const limpo = stripNulls(item)
    // Só valor NÃO-FINITO some. `null` explícito é preservado: onde o contrato
    // não admite null, quem corrige é a origem, não uma limpeza cega aqui.
    if (limpo === undefined && item !== undefined) continue
    if (limpo === undefined) continue
    saida[chave] = limpo
  }
  return saida
}
