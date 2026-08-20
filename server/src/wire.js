// A regra do wire que mais derruba o boot, em um módulo puro.
//
// Vive fora do index.js de propósito: importar o index sobe o servidor como
// efeito colateral, e esta regra precisa ser testável isolada
// (server/test/wire.mjs).

/**
 * Remove chaves com valor `null`/`undefined`/`NaN` de todo o payload.
 *
 * É a regra do projeto aplicada no ÚNICO lugar por onde toda resposta `/game/*`
 * passa (o `wire()` do index.js): **campo sem valor é omitido, nunca `null`**
 * (AGENTS.md regra 6, DEAD-ENDS #3). O parse do cliente é IL2CPP com tipos
 * concretos; um numérico não-nullable que chega como `null` derruba a
 * desserialização inteira e o boot morre com `Malformed response payload`.
 *
 * Aplicar aqui e não caso a caso é deliberado: cada rota nova herda a regra em
 * vez de precisar lembrar dela. Omitir também é seguro para tipo de referência
 * — Newtonsoft deixa o campo ausente como null de qualquer forma.
 *
 * ARRAY preserva posição: um elemento null continua `null`, porque removê-lo
 * mudaria o índice de todos os seguintes. Array com buraco é bug de quem montou
 * o payload, não algo para mascarar aqui.
 *
 * `NaN` recebe atenção especial porque `JSON.stringify(NaN)` emite **null** —
 * foi assim que `generation_period: null` chegou ao wire (medido no rig em
 * 2026-08-20: o game-data traz `'0D00H05M00S'`, e `Number(...)` disso é NaN).
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
    if (item === null || item === undefined) continue
    const limpo = stripNulls(item)
    if (limpo === undefined) continue          // NaN vira omissão, nunca null
    saida[chave] = limpo
  }
  return saida
}
