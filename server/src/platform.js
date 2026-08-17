import { RESPONSE_CODE } from './response-codes.js'

// ---- Contrato extraído do global-metadata.dat v29 (2026-08-17) ----
// IdentityApi: LinkXbox(xboxAuth), AuthorizeXbox(xboxAuth),
// DescribeConflict(linkToken), ResolveConflict(linkToken, userChoice),
// Unlink(identityId). XboxApi/BnetApi.ClaimSlayersClub(bnetSession) — os
// métodos de plataforma dependem de Xbox Live/Battle.net, com quem o Revival
// não fala. A resposta honesta é o código REAL de indisponibilidade do enum
// ResponseCode (extraído, ver response-codes.js) — nunca um payload falso de
// sucesso. As rotas de conflito/unlink têm gates verdadeiros: sem vínculo de
// plataforma nenhum linkToken/identityId pode existir, então o 2340
// (ObjectDoesNotExist) é fato, não invenção.

const XBOX_ROUTES = new Set([
  '/game/xbox/get-gamertag',
  '/game/xbox/get-game-pass',
  '/game/xbox/get-perks',
  '/game/xbox/claim-perk',
  '/game/identity/link-xbox',
  '/game/identity/authorize-xbox'
])

function xboxUnavailable () {
  return { error: [400, RESPONSE_CODE.XboxUnavailable, { reason: 'xbox-unavailable' }] }
}

function bnetUnavailable () {
  return { error: [400, RESPONSE_CODE.BnetUnavailable, { reason: 'bnet-unavailable' }] }
}

// Login de plataforma (pré-auth): mesmo contrato de indisponibilidade real.
export function platformLoginError (path) {
  if (path === '/game/auth/login-xbox') return xboxUnavailable()
  if (path === '/game/auth/login-google-play-games') {
    return { error: [400, RESPONSE_CODE.GooglePlayGamesUnavailable, { reason: 'google-play-games-unavailable' }] }
  }
  if (path === '/game/auth/login-game-center') {
    return { error: [400, RESPONSE_CODE.GameCenterUnavailable, { reason: 'game-center-unavailable' }] }
  }
  return null
}

export function handlePlatformRequest (path, body) {
  if (XBOX_ROUTES.has(path)) return xboxUnavailable()
  if (path === '/game/bnet/claim-slayers-club') return bnetUnavailable()

  if (path === '/game/identity/describe-conflict' || path === '/game/identity/resolve-conflict') {
    const linkToken = typeof body?.link_token === 'string' && body.link_token.length > 0
      ? body.link_token
      : null
    if (linkToken === null) return { error: [400, RESPONSE_CODE.ParameterError, { reason: 'link-token-required' }] }
    return { error: [400, RESPONSE_CODE.ObjectDoesNotExist, { reason: 'link-not-found' }] }
  }

  if (path === '/game/identity/unlink') {
    if (!Number.isInteger(body?.identity_id)) {
      return { error: [400, RESPONSE_CODE.ParameterError, { reason: 'identity-id-required' }] }
    }
    return { error: [400, RESPONSE_CODE.ObjectDoesNotExist, { reason: 'identity-not-found' }] }
  }

  return null
}
