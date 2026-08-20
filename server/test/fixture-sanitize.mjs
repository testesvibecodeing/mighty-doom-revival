import assert from 'node:assert/strict'

// Sanitizador das fixtures de protocolo, testado ISOLADO — importar
// scripts/capture_protocol_fixtures.mjs subiria um servidor temporário e
// executaria a captura inteira como efeito colateral. Por isso a regra vive em
// scripts/fixture_sanitize.mjs, um módulo puro.
import { sanitize, SECRET_KEYS, VOLATILE_KEYS } from '../../scripts/fixture_sanitize.mjs'

// --- redação de credencial -------------------------------------------------
{
  const wire = {
    uts: '2026-08-19T22:26:18',
    code: 1000,
    user_id: 8,
    token: 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiI4In0.assinatura',
    password: 'senha-de-32-caracteres-exatamente',
    recovery_code: 'RV-ABCDEF123456',
    device_id: '3f2504e0-4f89-11d3-9a0c-0305e82c3301',
    puuid: '00000000-0000-4000-8000-000000000000',
    push_token: 'token-de-push-do-firebase'
  }
  const out = sanitize(wire)
  assert.equal(out.uts, '<uts>')
  assert.equal(out.token, '<token>')
  assert.equal(out.password, '<password>')
  assert.equal(out.recovery_code, '<recovery-code>')
  assert.equal(out.device_id, '<device-id>')
  assert.equal(out.puuid, '<puuid>', 'puuid: identificador estável de conta, redigido')
  assert.equal(out.push_token, '<push-token>')
  assert.equal(out.code, 1000, 'code do envelope preservado')
  assert.equal(out.user_id, 8, 'identificador numérico do contrato não é credencial')
  assert.deepEqual(Object.keys(out), Object.keys(wire), 'nenhuma chave criada nem removida')
}

// --- o defeito medido: device_id NUMÉRICO de game/devices/* ----------------
// tests/fixtures/protocol/server-replay/devices/game__devices__{describe,unregister}.json
// trazem `"device_id": 1` — o id da LINHA de dispositivo, não a credencial.
// Trocar o inteiro por "<device-id>" mudaria o TIPO do wire na fixture, e tipo
// errado é o que derruba o parse do cliente (DEAD-ENDS #3).
{
  const out = sanitize({ device_id: 1, user_id: 8 })
  assert.equal(out.device_id, 1, 'device_id numérico NÃO pode virar string')
  assert.equal(typeof out.device_id, 'number', 'o tipo do wire é preservado')
}

// --- nullabilidade e omissão ----------------------------------------------
{
  const out = sanitize({ push_token: null, token: '', device_id: 1, puuid: null })
  assert.equal(out.push_token, null, 'null continua null (nullabilidade do wire)')
  assert.equal(out.token, '', 'string vazia não vira placeholder')
  assert.equal(out.puuid, null)
  assert.ok(!('recovery_code' in out), 'chave ausente não é inventada')
}

// --- estrutura: arrays e aninhamento --------------------------------------
{
  const out = sanitize({
    itens: [{ id: 1, token: 'abc' }, { id: 2, token: 'def' }],
    legal: { tos_version: 1, allow_sharing: false },
    vazio: []
  })
  assert.equal(out.itens[0].token, '<token>')
  assert.equal(out.itens[1].token, '<token>')
  assert.equal(out.itens[0].id, 1)
  assert.equal(out.legal.tos_version, 1)
  assert.equal(out.legal.allow_sharing, false, 'false não é tratado como ausente')
  assert.deepEqual(out.vazio, [], 'array vazio preservado (não vira null nem some)')
  assert.ok(Array.isArray(out.itens))
}

// --- url perde o host, guarda o path --------------------------------------
{
  const out = sanitize({ url: 'https://doom.exemplo.br/data?v=1' })
  assert.equal(out.url, '<base>/data?v=1')
  assert.equal(sanitize({ url: 'http://127.0.0.1:8080/data' }).url, '<base>/data',
    'host privado/loopback nunca fica na fixture')
}

// --- voláteis e zerados ---------------------------------------------------
{
  const out = sanitize({ account_age: 42, last_login: 1787180192, last_claim: 1787180192, next_claim: 1787183792 })
  assert.equal(out.account_age, 0)
  assert.equal(out.last_login, 0)
  assert.equal(out.last_claim, '<epoch>')
  assert.equal(out.next_claim, '<epoch>')
}

// --- idempotência: sanitizar de novo não muda nada -------------------------
{
  const uma = sanitize({ token: 'abc', device_id: 1, uts: '2026-08-19T00:00:00', legal: { v: 1 } })
  assert.deepEqual(sanitize(uma), uma, 'sanitize(sanitize(x)) === sanitize(x)')
}

// --- contrato dos placeholders com o gate Python ---------------------------
// scripts/verify_everything.py::SECRET_IN_FIXTURE_RES exige valor no formato
// <...>; scripts/client_harness.py usa os MESMOS placeholders no lado Python.
{
  for (const [chave, placeholder] of Object.entries(SECRET_KEYS)) {
    assert.match(placeholder, /^<[a-z0-9-]+>$/, `placeholder de ${chave} fora do formato do gate`)
  }
  for (const placeholder of Object.values(VOLATILE_KEYS)) {
    assert.match(placeholder, /^<[a-z0-9-]+>$/)
  }
  assert.ok('puuid' in SECRET_KEYS, 'puuid tem que estar na tabela (regressão da Fase 1)')
}

// --- escalares crus --------------------------------------------------------
{
  assert.equal(sanitize('texto'), 'texto')
  assert.equal(sanitize(7), 7)
  assert.equal(sanitize(null), null)
  assert.equal(sanitize(false), false)
}

console.log('fixture-sanitize.mjs: OK')
