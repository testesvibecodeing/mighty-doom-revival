import assert from 'node:assert/strict'

import { stripNulls } from '../src/wire.js'

// Escopo ESTREITO por decisao auditada: o que nunca pode chegar ao wire e um
// valor NAO-FINITO, porque `JSON.stringify(NaN)` emite `null` sem que ninguem
// tenha escrito `null`. `null` EXPLICITO e preservado — onde o contrato nao o
// admite, quem corrige e a origem (ver rewards.js), nao uma limpeza cega aqui.

// --- o caso que motivou tudo: NaN vira null no JSON ------------------------
{
  assert.equal(JSON.stringify({ x: NaN }), '{"x":null}', 'a armadilha existe mesmo')
  const out = stripNulls({ periodo: NaN, ok: 300 })
  assert.deepEqual(out, { ok: 300 })
  assert.ok(!JSON.stringify(out).includes('null'))
  assert.equal(stripNulls({ inf: Infinity }).inf, undefined, 'Infinity tambem sai')
  assert.equal(stripNulls({ neg: -Infinity }).neg, undefined)
}

// --- null EXPLICITO e preservado -------------------------------------------
// Auditoria de 2026-08-20: estes campos aparecem como null em boots que
// COMPLETARAM antes desta funcao existir, ou seja, o cliente os aceita.
{
  const reais = {
    playfab_session_ticket: null,          // auth/register, auth/login-device
    cosmetic: null,                        // player/user-data
    current_run: null,
    player_settings: null,
    quota_id: null                         // store/get
  }
  const out = stripNulls({ ...reais, code: 1000 })
  for (const chave of Object.keys(reais)) {
    assert.ok(chave in out, `${chave} nao pode sumir: o cliente aceita null nele`)
    assert.equal(out[chave], null)
  }
  assert.equal(out.code, 1000)
}

// --- undefined nao e valor de wire -----------------------------------------
{
  const out = stripNulls({ a: 1, b: undefined })
  assert.deepEqual(out, { a: 1 }, 'undefined nao vira null nem chave vazia')
}

// --- valores falsy LEGITIMOS ficam -----------------------------------------
{
  const out = stripNulls({ zero: 0, falso: false, vazio: '', lista: [], objeto: {} })
  assert.deepEqual(out, { zero: 0, falso: false, vazio: '', lista: [], objeto: {} })
}

// --- profundidade -----------------------------------------------------------
{
  const out = stripNulls({ state: { last_claim: 10, periodo: NaN, nested: { a: null, b: 2 } } })
  assert.deepEqual(out, { state: { last_claim: 10, nested: { a: null, b: 2 } } })
}

// --- ARRAY preserva posicao -------------------------------------------------
{
  const out = stripNulls({ itens: [1, NaN, 3] })
  assert.deepEqual(out.itens, [1, null, 3], 'remover deslocaria o indice dos seguintes')
  assert.equal(out.itens.length, 3)
  assert.deepEqual(stripNulls({ i: [1, null, 3] }).i, [1, null, 3])
}

// --- objetos DENTRO de array --------------------------------------------
{
  const out = stripNulls({ itens: [{ x: NaN, y: 1 }, { z: 2 }] })
  assert.deepEqual(out.itens, [{ y: 1 }, { z: 2 }])
}

// --- caso real medido: idle-rewards/get-state ------------------------------
{
  const out = stripNulls({
    state: {
      last_claim: 1787254065,
      boost_available: 0,
      next_claim: 246,
      idle_generation: [{ rid: 1, amount: 32 }],
      generation_period: Number('0D00H05M00S'),   // NaN de verdade
      claimable_periods: 0
    }
  })
  assert.ok(!('generation_period' in out.state), 'NaN sai do wire')
  assert.equal(out.state.next_claim, 246, 'duracao em segundos permanece')
  assert.equal(out.state.boost_available, 0, 'zero legitimo permanece')
  assert.ok(!JSON.stringify(out).includes('null'))
}

// --- escalares e tipos especiais -------------------------------------------
{
  assert.equal(stripNulls('texto'), 'texto')
  assert.equal(stripNulls(7), 7)
  assert.equal(stripNulls(true), true)
  assert.equal(stripNulls(null), null, 'raiz null continua null: quem decide e o chamador')
  assert.equal(stripNulls(NaN), undefined, 'NaN na raiz nao vira null')
  const d = new Date(0)
  assert.equal(stripNulls({ d }).d, d, 'Date nao e desmontado')
}

console.log('wire.mjs: OK')
