// Token de sessão em formato JWT para o cliente real (1.13.1).
//
// O cliente exige "Session token is not a well formed JWT as expected"
// (Ubu.GameController:UpdateSessionToken) — token opaco derruba o StartSession e
// o boot morre em "FALHA AO CARREGAR INFORMAÇÕES DO PERFIL". Do
// global-metadata.dat v29 (extraído nesta base):
//   - literais de claim: "ubu_session_id" e "ubu_user_id";
//   - DTO Ubu.GameApi.DataObjects.GameSessionToken com campos audience,
//     issuedTimestamp, expiresTimestamp, sessionNonce (+ issuer/subject).
//
// O parse do cliente é manual (split em '.') e não valida assinatura; a
// assinatura HS256 aqui vale para o lado do servidor autenticar as chamadas
// seguintes (x-ubu-token). Claims são emitidos em grafia redundante
// (camelCase C#, snake_case da estratégia Newtonsoft e padrão JWT) porque a
// grafia exata lida pelo cliente não foi confirmada — campos extras são
// ignorados pelo parser do cliente.
import { createHmac, randomBytes } from 'node:crypto'

const DEFAULT_TTL_SECONDS = 30 * 24 * 3600

const b64urlJson = value => Buffer.from(JSON.stringify(value), 'utf8').toString('base64url')

export function sessionSecret (revival = {}) {
  if (typeof process.env.REVIVAL_SESSION_SECRET === 'string' && process.env.REVIVAL_SESSION_SECRET) {
    return process.env.REVIVAL_SESSION_SECRET
  }
  if (typeof revival.session_secret === 'string' && revival.session_secret) return revival.session_secret
  // Derivação estável do game_data_token: sem config nova o token continua
  // válido entre restarts do servidor.
  return createHmac('sha256', 'revival-session-secret').update(String(revival.game_data_token || 'revival')).digest('hex')
}

export function createSessionToken (userId, options = {}) {
  if (!options.secret) throw new Error('session secret is required')
  if (!Number.isInteger(userId)) throw new Error('user id must be an integer')
  const now = Math.floor(Date.now() / 1000)
  const ttl = Number.isInteger(options.ttlSeconds) && options.ttlSeconds > 0 ? options.ttlSeconds : DEFAULT_TTL_SECONDS
  const sessionId = Number.isInteger(options.sessionId) ? options.sessionId : 1
  const nonce = typeof options.nonce === 'string' && options.nonce ? options.nonce : randomBytes(8).toString('hex')
  const payload = {
    issuer: 'revival',
    iss: 'revival',
    // JWT canônico: "aud" aceita string OU array, mas o cliente tipa
    // audience como String[] — string crua aqui derruba o parse do
    // UpdateSessionToken com "Could not cast or convert from System.String
    // to System.String[]" (provado no emulador 2026-08-19: com aud string o
    // cliente crashou em register/login/refresh; com array, não).
    audience: ['mighty-doom'],
    aud: ['mighty-doom'],
    subject: String(userId),
    sub: String(userId),
    issuedTimestamp: now,
    issued_timestamp: now,
    iat: now,
    expiresTimestamp: now + ttl,
    expires_timestamp: now + ttl,
    exp: now + ttl,
    sessionId,
    session_id: sessionId,
    ubu_session_id: sessionId,
    sessionNonce: nonce,
    session_nonce: nonce,
    ubu_user_id: userId
  }
  const header = b64urlJson({ alg: 'HS256', typ: 'JWT' })
  const body = b64urlJson(payload)
  const signature = createHmac('sha256', options.secret).update(`${header}.${body}`).digest('base64url')
  return `${header}.${body}.${signature}`
}

export function verifySessionToken (token, secret) {
  if (typeof token !== 'string' || typeof secret !== 'string' || !secret) return null
  const parts = token.split('.')
  if (parts.length !== 3 || parts.some(part => !part)) return null
  const [header, body, signature] = parts
  const expected = createHmac('sha256', secret).update(`${header}.${body}`).digest()
  const received = Buffer.from(signature, 'base64url')
  if (expected.length !== received.length || !expected.equals(received)) return null
  let payload
  try {
    payload = JSON.parse(Buffer.from(body, 'base64url').toString('utf8'))
  } catch {
    return null
  }
  if (!payload || typeof payload !== 'object') return null
  const userId = Number.parseInt(payload.ubu_user_id ?? payload.sub, 10)
  if (!Number.isInteger(userId) || userId <= 0) return null
  const exp = Number(payload.expiresTimestamp ?? payload.expires_timestamp ?? payload.exp)
  if (Number.isInteger(exp) && exp * 1000 <= Date.now()) return null
  return { userId, sessionId: Number(payload.ubu_session_id ?? payload.session_id ?? payload.sessionId) || 1 }
}
