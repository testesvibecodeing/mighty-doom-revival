import assert from 'node:assert/strict'

import { handlePlatformRequest, platformLoginError } from '../src/platform.js'
import { RESPONSE_CODE } from '../src/response-codes.js'

// ---- Rotas platform-gated: código real de indisponibilidade (extraído do
// metadata) ou gate verdadeiro — nunca payload falso de sucesso. ----

// Logins de plataforma (pré-auth)
assert.deepEqual(platformLoginError('/game/auth/login-xbox'), {
  error: [400, RESPONSE_CODE.XboxUnavailable, { reason: 'xbox-unavailable' }]
})
assert.equal(platformLoginError('/game/auth/login-xbox').error[1], 3127)
assert.equal(platformLoginError('/game/auth/login-google-play-games').error[1], 3111)
assert.equal(platformLoginError('/game/auth/login-game-center').error[1], 3121)
assert.equal(platformLoginError('/game/auth/login-device'), null, 'login-device não é rota de plataforma')

// Xbox Live: indisponibilidade real em todas as rotas do módulo
for (const path of [
  '/game/xbox/get-gamertag', '/game/xbox/get-game-pass', '/game/xbox/get-perks',
  '/game/xbox/claim-perk', '/game/identity/link-xbox', '/game/identity/authorize-xbox'
]) {
  const response = handlePlatformRequest(path, {})
  assert.equal(response.error[1], 3127, `${path} responde XboxUnavailable`)
  assert.equal(response.error[2].reason, 'xbox-unavailable')
}

// Battle.net
assert.equal(handlePlatformRequest('/game/bnet/claim-slayers-club', {}).error[1], 3101)

// Conflitos de identidade: sem vínculo de plataforma, nenhum linkToken existe.
assert.equal(handlePlatformRequest('/game/identity/describe-conflict', {}).error[2].reason, 'link-token-required')
assert.equal(handlePlatformRequest('/game/identity/describe-conflict', { link_token: 'qualquer' }).error[1], 2340)
assert.equal(handlePlatformRequest('/game/identity/resolve-conflict', { link_token: 'x', user_choice: 1 }).error[2].reason, 'link-not-found')
assert.equal(handlePlatformRequest('/game/identity/unlink', {}).error[2].reason, 'identity-id-required')
assert.equal(handlePlatformRequest('/game/identity/unlink', { identity_id: 1 }).error[1], 2340)

// Fora do módulo não intercepta
assert.equal(handlePlatformRequest('/game/player/user-data', {}), null)

console.log('Mighty DOOM Revival platform gates test: PASS')
