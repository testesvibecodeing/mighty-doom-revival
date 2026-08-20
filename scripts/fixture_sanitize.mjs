// Sanitizador das fixtures de protocolo — módulo puro, SEM efeito colateral.
//
// Vive fora do capture_protocol_fixtures.mjs de propósito: aquele arquivo é um
// CLI de topo que sobe um servidor temporário ao ser importado, então testar a
// função de dentro dele exigiria executar a captura inteira. Aqui a regra de
// redação é importável e testável isoladamente (server/test/fixture-sanitize.mjs).
//
// Contrato: preserva chaves, tipos, arrays, omissões e nullabilidade do wire —
// só o VALOR sensível/volátil muda. O par Python equivalente é
// scripts/client_harness.py::sanitize_value; os dois produzem fixture
// versionada e o gate (scripts/verify_everything.py::check_fixtures) cobra os
// mesmos placeholders de ambos.

// chave do wire -> placeholder na fixture.
export const SECRET_KEYS = Object.freeze({
  token: '<token>',
  password: '<password>',
  recovery_code: '<recovery-code>',
  device_id: '<device-id>',
  push_token: '<push-token>',
  // puuid NÃO é credencial: é o identificador estável da conta no wire, que
  // sozinho não dá acesso a nada. É redigido porque correlaciona execuções e
  // sobrevive a restart — a fixture só precisa provar a chave e o tipo.
  puuid: '<puuid>'
})

// Volátil por execução: o valor muda a cada captura e poluiria o diff.
export const VOLATILE_KEYS = Object.freeze({ uts: '<uts>' })

// Épocas derivadas do relógio no momento da captura (idle/offer/run). O
// start_time de evento agendado NÃO entra aqui: vem da config, é determinístico.
export const EPOCH_KEYS = Object.freeze([
  'last_claim', 'next_claim', 'started_at_ms', 'best_completion_time_milliseconds',
  'authorization_time', 'last_access_time'
])

// Zerados: contadores relativos ao instante da captura.
export const ZEROED_KEYS = Object.freeze(['account_age', 'last_login'])

// Só STRING não vazia é redigida. Medido em 2026-08-19: `device_id` é a
// credencial (UUID string) em game/auth/*, mas é o id NUMÉRICO da linha de
// dispositivo em game/devices/describe e game/devices/unregister. Trocar o
// inteiro por "<device-id>" mudaria o TIPO do wire na fixture — e tipo errado
// é exatamente o que derruba o parse do cliente (DEAD-ENDS #3). Número não é
// credencial: fica como está.
function redigivel (valor) {
  return typeof valor === 'string' && valor.length > 0
}

export function sanitize (value) {
  if (Array.isArray(value)) return value.map(sanitize)
  if (value && typeof value === 'object') {
    const out = {}
    for (const [key, inner] of Object.entries(value)) {
      if (key in VOLATILE_KEYS) out[key] = redigivel(inner) ? VOLATILE_KEYS[key] : inner
      else if (key in SECRET_KEYS) out[key] = redigivel(inner) ? SECRET_KEYS[key] : inner
      else if (key === 'url') out[key] = String(inner).replace(/^https?:\/\/[^/]+/, '<base>')
      else if (ZEROED_KEYS.includes(key)) out[key] = 0
      else if (EPOCH_KEYS.includes(key)) out[key] = '<epoch>'
      else out[key] = sanitize(inner)
    }
    return out
  }
  return value
}
