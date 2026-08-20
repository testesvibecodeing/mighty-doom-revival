import assert from 'node:assert/strict'

import { stripNulls } from '../src/wire.js'

// A regra que mais derruba o boot: campo sem valor é OMITIDO, nunca null
// (AGENTS.md regra 6, DEAD-ENDS #3). Aqui ela é testada isolada, porque
// importar o index.js subiria o servidor como efeito colateral.

// --- omissão de null/undefined --------------------------------------------
{
  const out = stripNulls({ a: 1, b: null, c: 'x', d: undefined })
  assert.deepEqual(out, { a: 1, c: 'x' })
  assert.ok(!('b' in out), 'null é omitido, não convertido')
  assert.ok(!('d' in out), 'undefined é omitido')
  assert.ok(!JSON.stringify(out).includes('null'))
}

// --- NaN: o caso que passou despercebido -----------------------------------
// `JSON.stringify(NaN)` emite **null**. Foi assim que `generation_period: null`
// chegou ao wire (game-data traz '0D00H05M00S'; `Number(...)` disso é NaN).
{
  assert.equal(JSON.stringify({ x: NaN }), '{"x":null}', 'a armadilha existe mesmo')
  const out = stripNulls({ periodo: NaN, ok: 300 })
  assert.deepEqual(out, { ok: 300 })
  assert.ok(!JSON.stringify(out).includes('null'))
  assert.equal(stripNulls({ inf: Infinity }).inf, undefined, 'Infinity também é omitido')
}

// --- valores falsy LEGÍTIMOS são preservados -------------------------------
{
  const out = stripNulls({ zero: 0, falso: false, vazio: '', lista: [], objeto: {} })
  assert.deepEqual(out, { zero: 0, falso: false, vazio: '', lista: [], objeto: {} })
  assert.equal(out.zero, 0, '0 é valor, não ausência')
  assert.equal(out.falso, false, 'false é valor, não ausência')
}

// --- profundidade ----------------------------------------------------------
{
  const out = stripNulls({
    state: { last_claim: 10, generation_period: null, nested: { a: null, b: 2 } }
  })
  assert.deepEqual(out, { state: { last_claim: 10, nested: { b: 2 } } })
}

// --- ARRAY preserva posição ------------------------------------------------
// Remover um elemento mudaria o índice de todos os seguintes.
{
  const out = stripNulls({ itens: [1, null, 3] })
  assert.deepEqual(out.itens, [1, null, 3], 'buraco de array não é fechado')
  assert.equal(out.itens.length, 3)
}

// --- objetos DENTRO de array são limpos ------------------------------------
{
  const out = stripNulls({ itens: [{ x: null, y: 1 }, { z: 2 }] })
  assert.deepEqual(out.itens, [{ y: 1 }, { z: 2 }])
}

// --- caso real medido: store/get -------------------------------------------
{
  const real = {
    store_items: [{
      id: 900001,
      quota_id: null,
      requirements: {
        selector_format_version: 1,
        player: { userId: null, playerLevel: null, chapterProgress: null }
      },
      cost: [{ rid: 1, amount: 2500 }]
    }]
  }
  const out = stripNulls(real)
  const texto = JSON.stringify(out)
  assert.ok(!texto.includes('null'), `nenhum null sobrevive: ${texto}`)
  assert.equal(out.store_items[0].id, 900001, 'o que tem valor continua')
  assert.deepEqual(out.store_items[0].cost, [{ rid: 1, amount: 2500 }])
  assert.deepEqual(out.store_items[0].requirements.player, {}, 'objeto vazio, não null')
  assert.equal(out.store_items[0].requirements.selector_format_version, 1)
}

// --- caso real medido: idle-rewards/get-state ------------------------------
{
  const out = stripNulls({
    state: {
      last_claim: 1787254065, boost_available: 0, next_claim: 0,
      idle_generation: [{ rid: 1, amount: 32 }],
      generation_period: Number('0D00H05M00S'),   // NaN de verdade
      claimable_periods: 0
    }
  })
  assert.ok(!('generation_period' in out.state), 'NaN sai do wire')
  assert.equal(out.state.boost_available, 0, 'zero legítimo permanece')
  assert.ok(!JSON.stringify(out).includes('null'))
}

// --- escalares e tipos especiais -------------------------------------------
{
  assert.equal(stripNulls('texto'), 'texto')
  assert.equal(stripNulls(7), 7)
  assert.equal(stripNulls(true), true)
  assert.equal(stripNulls(null), null, 'raiz null continua null: quem decide é o chamador')
  const d = new Date(0)
  assert.equal(stripNulls({ d }).d, d, 'Date não é desmontado')
}

console.log('wire.mjs: OK')
