import { createServer } from 'node:http'
import { existsSync, readFileSync } from 'node:fs'
import { isAbsolute, join, resolve } from 'node:path'
import { loadEnvFile } from 'node:process'

import { ensureSuperAdmin, handleAdminApi, handleAdminRecover, publicPack } from './admin.js'
import { chapterProgressionWire, handleChapterRequest } from './chapters.js'
import { handleInboxRequest } from './inbox.js'
import { handleCompatRequest } from './compat.js'
import { loadRuntimeConfig, researchMode } from './config.js'
import { Repository } from './db.js'
import { handleEventRequest } from './events.js'
import { handleArmoryRequest } from './armory.js'
import { findAdRewardToken } from './ad-tokens.js'
import { boostIdleReward, idleRewardState } from './rewards.js'
import { handleDevicesRequest } from './devices.js'
import { redeemCode } from './codes.js'
import { handlePlatformRequest, platformLoginError } from './platform.js'
import { activatedOfferWires, activateStoreOffer, adPurchasePack, storeItemsWire } from './store.js'
import { inventoryWire, seedStarterBundle, giveGameResource } from './game-data-model.js'
import { playerStatsWire, incrementPlayerStats } from './stats.js'
import { activePacks, packToStoreItem, purchasePack } from './store.js'
import { handleTutorialRequest, tutorialProgressionWire } from './tutorial.js'
import { createSiteRouter } from './site.js'
import { panelResourceInfo } from './assets.js'
import { readSmtpConfig, sendMail, smtpConfigured } from './mail.js'
import { instanceIdentity } from './instance.js'
import { stripNulls } from './wire.js'
import { createSessionToken, sessionSecret, verifySessionToken } from './jwt.js'

const serverRoot = resolve(import.meta.dirname, '..')
const envPath = resolve(serverRoot, '.env')
if (existsSync(envPath)) loadEnvFile(envPath)

let runtime = loadRuntimeConfig()
const defaultDbPath = resolve(serverRoot, 'runtime', 'revival.sqlite3')
const configuredDb = process.env.DB_PATH
const dbPath = configuredDb
  ? (isAbsolute(configuredDb) ? configuredDb : resolve(serverRoot, configuredDb))
  : defaultDbPath
const repo = new Repository(dbPath)

// Site estático (server/public) + upload de APK por link temporário. Os
// diretórios são overridáveis por env para testes/Docker.
const publicDir = process.env.PUBLIC_DIR
  ? resolve(serverRoot, process.env.PUBLIC_DIR)
  : resolve(serverRoot, 'public')
const uploadDir = process.env.UPLOAD_DIR
  ? resolve(serverRoot, process.env.UPLOAD_DIR)
  : resolve(serverRoot, 'runtime')
const site = createSiteRouter({ publicDir, uploadDir })

// Super Admin do painel /slayer: credenciais geradas pelo scripts/install.sh
// (runtime/admin-credentials.json, consumidas uma única vez no boot) ou env
// REVIVAL_ADMIN_EMAIL/REVIVAL_ADMIN_PASSWORD. O link temporário de 10 min
// para trocar o acesso do admin vive em runtime/admin-recover-token.json.
const adminCredentialsFile = join(uploadDir, 'admin-credentials.json')
const adminRecoverTokenFile = join(uploadDir, 'admin-recover-token.json')
ensureSuperAdmin({ repo, credentialsFile: adminCredentialsFile })

function nowSeconds () {
  return Math.floor(Date.now() / 1000)
}

// Contador de fallbacks do RESEARCH_MODE por rota. O gate de convergência
// (scripts/verify_everything.py e o harness ADB) lê /revival/research e
// FALHA se um fluxo já validado no cliente ainda depender de resposta vazia
// de pesquisa. Enquanto um endpoint vive de fallback, ele não está done.
const researchFallbacks = new Map()

function recordResearchFallback (path) {
  const entry = researchFallbacks.get(path) || { count: 0, first_seen: nowSeconds(), last_seen: nowSeconds() }
  entry.count += 1
  entry.last_seen = nowSeconds()
  researchFallbacks.set(path, entry)
}

function wire (data = {}, code = 1000) {
  // O cliente 1.13.1 faz parse estrito do timestamp do servidor em
  // Ubu.GameController.ParseServerTimestamp (StartSession). Bisseção no
  // emulador confirmou: a chave do wire é "uts" sozinha, no formato
  // "yyyy-MM-ddTHH:mm:ss" UTC (unix epoch, ISO com espaço e chaves
  // timestamp/utc_timestamp são ignoradas ou rejeitadas).
  const uts = formatServerTimestamp(new Date())
  return stripNulls({ uts, code, ...data })
}

// Chaves cujo VALOR nunca deve ficar em texto claro no request_log (corpo
// persistido = mínimo necessário ao contrato; a fixture final é sanitizada
// de novo pelo harness). Headers não são persistidos — nada de Authorization.
const SECRET_LOG_KEYS = new Set(['token', 'password', 'recovery_code', 'push_token', 'device_id'])

function redactForLog (value, depth = 0) {
  if (value === null || typeof value !== 'object' || depth > 8) return value
  if (Array.isArray(value)) return value.map(item => redactForLog(item, depth + 1))
  const out = {}
  for (const [key, item] of Object.entries(value)) {
    // Nullabilidade/shape preservados: só valores truthy são redigidos.
    out[key] = SECRET_LOG_KEYS.has(key) && item ? `<${key}>` : redactForLog(item, depth + 1)
  }
  return out
}

function formatServerTimestamp (date) {
  const pad = (n, w = 2) => String(n).padStart(w, '0')
  return (
    `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}` +
    `T${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())}`
  )
}

function json (res, status, payload) {
  const body = JSON.stringify(payload)
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(body),
    'cache-control': 'no-store'
  })
  res.end(body)
  persistGameLog(res, status, payload)
  // handleAccount() usa `return json(...)` como sinal de "rota respondida";
  // sem o true o handle() prossegue até o 404 catch-all e responde duas
  // vezes (ERR_HTTP_HEADERS_SENT). O json() de site.js já faz o mesmo.
  return true
}

// Ponto único de pairing: toda resposta JSON de rota /game/* anexa um ctx em
// `res.revivalGameLog` (criado no handle()); quando a resposta efetivamente
// sai, gravamos request+response na MESMA linha do request_log — inclusive
// register/login-device, que não passam pela autenticação. Falha no log não
// pode derrubar a resposta já enviada ao cliente.
function persistGameLog (res, status, payload) {
  const ctx = res.revivalGameLog
  if (!ctx || ctx.logged) return
  ctx.logged = true
  try {
    ctx.id = repo.logRequest(ctx.userId ?? null, ctx.path, redactForLog(ctx.body), {
      method: ctx.method,
      status,
      code: typeof payload?.code === 'number' ? payload.code : null,
      response: redactForLog(payload),
      note: ctx.note || null
    })
  } catch (error) {
    console.error('[request-log] falha ao persistir:', error.message)
  }
}

function ok (res, data = {}) {
  json(res, 200, wire(data))
}

function fail (res, status = 400, code = 2000, data = {}) {
  json(res, status, wire(data, code))
}

function adminAuthorized (req) {
  const expected = process.env.REVIVAL_ADMIN_TOKEN
  return Boolean(expected) && req.headers.authorization === `Bearer ${expected}`
}

function extractToken (req) {
  const ubu = req.headers['x-ubu-token']
  if (typeof ubu === 'string' && ubu) return ubu
  const auth = req.headers.authorization
  if (typeof auth !== 'string' || !auth) return null
  return auth.toLowerCase().startsWith('bearer ') ? auth.slice(7).trim() : auth
}

function cookieValue (req, name) {
  const cookies = String(req.headers.cookie || '').split(';')
  for (const part of cookies) {
    const [key, ...rest] = part.trim().split('=')
    if (key === name) return decodeURIComponent(rest.join('='))
  }
  return null
}

function accountToken (req) {
  const cookie = cookieValue(req, 'revival_session')
  if (cookie) return cookie
  const auth = req.headers.authorization
  return typeof auth === 'string' && auth.toLowerCase().startsWith('bearer ')
    ? auth.slice(7).trim()
    : null
}

function accountCookie (res, token, maxAge = 30 * 24 * 3600) {
  res.setHeader('set-cookie', `revival_session=${encodeURIComponent(token)}; HttpOnly; Path=/; SameSite=Lax; Max-Age=${maxAge}`)
}

function publicAccount (user) {
  return {
    id: user.id,
    uuid: user.uuid,
    email: user.email || '',
    display_name: user.display_name || '',
    is_admin: Boolean(user.is_admin),
    password_set: user.password_set !== 0,
    level: user.level,
    chapter_progression: user.chapter_progression,
    attempt_count: user.attempt_count,
    created_at: user.created_at
  }
}

function accountSnapshot (user) {
  const items = repo.items(user.id).map(item => {
    let metadata = {}
    try { metadata = JSON.parse(item.metadata_json || '{}') } catch {}
    const info = panelResourceInfo(item.rid, runtime, item.kind)
    return {
      id: item.id,
      rid: item.rid,
      name: info.name,
      icon: info.icon,
      tag: info.tag,
      kind: info.kind,
      level: item.level,
      tier: item.tier,
      amount: item.amount,
      metadata
    }
  })
  return {
    currencies: repo.currencies(user.id).map(row => ({ ...row, ...panelResourceInfo(row.rid, runtime, 'currency') })),
    energies: repo.energies(user.id).map(row => ({ ...row, ...panelResourceInfo(row.rid, runtime, 'energy') })),
    items,
    equipped: repo.slots(user.id),
    cosmetics: repo.cosmetics(user.id).map(row => ({ ...row, ...panelResourceInfo(row.rid, runtime, 'cosmetic') })),
    entitlements: repo.entitlements(user.id).map(row => ({ ...row, ...panelResourceInfo(row.rid, runtime, 'entitlement') })),
    progression: {
      level: user.level,
      chapters: user.chapter_progression,
      attempts: user.attempt_count,
      stats: playerStatsWire(repo, user.id)
    }
  }
}

function passwordIsValid (value) {
  return typeof value === 'string' && value.length >= 8 && value.length <= 128
}

function emailIsValid (value) {
  return typeof value === 'string' && value.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
}

// Envia o código de acesso por e-mail. `create: true` cadastra a conta no
// primeiro pedido (login sem senha); `create: false` é o fluxo "esqueci a
// senha", que responde ok mesmo para e-mail inexistente (anti-enumerção).
async function dispatchLoginCode (email, { create }) {
  const smtp = readSmtpConfig()
  if (!smtpConfigured(smtp)) {
    return { status: 503, payload: { ok: false, error: 'smtp-not-configured', message: 'O administrador precisa configurar o SMTP no painel.' } }
  }
  let user = repo.userByLogin(email)
  let created = false
  if (!user) {
    if (!create) return { status: 200, payload: { ok: true, code_sent: true } }
    try {
      user = repo.createUser({ email, passwordSet: false }).user
      created = true
    } catch (error) {
      if (String(error.message).includes('UNIQUE')) return { status: 409, payload: { ok: false, error: 'email-already-used' } }
      throw error
    }
  }
  const code = repo.createLoginCode(email)
  if (!code) {
    return { status: 429, payload: { ok: false, error: 'code-rate-limited', message: 'Aguarde um minuto antes de pedir outro código.' } }
  }
  try {
    await sendMail(smtp, {
      to: email,
      subject: 'Seu código de acesso',
      text: `Olá!\n\nSeu código de acesso é: ${code}\nEle é válido por 10 minutos.\n\nSe você não pediu este código, ignore este e-mail.`
    })
  } catch (error) {
    console.warn(`[mail] falha ao enviar para ${email}: ${error.message}`)
    return { status: 502, payload: { ok: false, error: 'mail-send-failed' } }
  }
  return { status: 200, payload: { ok: true, code_sent: true, account_created: created } }
}

async function handleAccount (req, res, path) {
  if (!path.startsWith('/account/')) return false
  if (req.method === 'GET' && path === '/account/me') {
    const user = repo.userByWebSession(accountToken(req))
    if (!user) return json(res, 401, { ok: false, error: 'session-expired' })
    return json(res, 200, { ok: true, account: publicAccount(user), snapshot: accountSnapshot(user) })
  }

  if (req.method === 'GET' && path === '/account/notifications') {
    const user = repo.userByWebSession(accountToken(req))
    if (!user) return json(res, 401, { ok: false, error: 'session-expired' })
    return json(res, 200, { ok: true, notifications: repo.listNotifications(30) })
  }

  // Contas do jogo (login-device) sem dono no site — para a tela de vínculo.
  if (req.method === 'GET' && path === '/account/claimable') {
    const user = repo.userByWebSession(accountToken(req))
    if (!user) return json(res, 401, { ok: false, error: 'session-expired' })
    const accounts = repo.listClaimableAccounts(50).filter(account => account.id !== user.id)
    return json(res, 200, { ok: true, accounts })
  }

  // Loja como o jogador vê no painel: só pacotes ativos, preços em moedas.
  if (req.method === 'GET' && path === '/account/store') {
    const user = repo.userByWebSession(accountToken(req))
    if (!user) return json(res, 401, { ok: false, error: 'session-expired' })
    return json(res, 200, { ok: true, packs: activePacks(runtime).map(pack => publicPack(pack, runtime)) })
  }

  if (path.startsWith('/account/admin')) {
    const user = repo.userByWebSession(accountToken(req))
    if (!user) return json(res, 401, { ok: false, error: 'session-expired' })
    if (!user.is_admin) return json(res, 403, { ok: false, error: 'forbidden' })
    let body = {}
    if (['POST', 'PATCH', 'PUT'].includes(req.method)) {
      try { body = await readJsonBody(req) } catch { return json(res, 400, { ok: false, error: 'invalid-json' }) }
    }
    return handleAdminApi(req, res, path, body, { repo, runtime, reloadRuntime, site, user })
  }

  let body = {}
  if (req.method !== 'POST' && req.method !== 'PATCH') return json(res, 405, { ok: false, error: 'method-not-allowed' })
  try { body = await readJsonBody(req) } catch { return json(res, 400, { ok: false, error: 'invalid-json' }) }

  if (path === '/account/email-code/request') {
    const email = String(body.email || '').trim().toLowerCase()
    if (!emailIsValid(email)) return json(res, 400, { ok: false, error: 'email-invalid' })
    const outcome = await dispatchLoginCode(email, { create: true })
    return json(res, outcome.status, outcome.payload)
  }

  if (path === '/account/email-code/login') {
    const email = String(body.email || '').trim().toLowerCase()
    const user = repo.userByLogin(email)
    if (!user || !repo.consumeLoginCode(email, body.code)) return json(res, 401, { ok: false, error: 'code-invalid' })
    const session = repo.createWebSession(user.id)
    accountCookie(res, session.token)
    const fresh = repo.userById(user.id)
    return json(res, 200, {
      ok: true,
      account: publicAccount(fresh),
      snapshot: accountSnapshot(fresh),
      password_set: Boolean(fresh.password_set)
    })
  }

  if (path === '/account/register') {
    const email = String(body.email || '').trim().toLowerCase()
    const displayName = String(body.display_name || '').trim().slice(0, 48)
    if (!emailIsValid(email) || !passwordIsValid(body.password)) return json(res, 400, { ok: false, error: 'email-and-password-invalid' })
    if (repo.userByLogin(email)) return json(res, 409, { ok: false, error: 'email-already-used' })
    try {
      const created = bootstrapUser({}, { password: body.password, email, displayName })
      const session = repo.createWebSession(created.user_id)
      accountCookie(res, session.token)
      return json(res, 201, {
        ok: true,
        account: publicAccount(repo.userById(created.user_id)),
        recovery_code: created.recovery_code,
        message: 'Guarde o código de recuperação em local seguro.'
      })
    } catch (error) {
      if (String(error.message).includes('UNIQUE')) return json(res, 409, { ok: false, error: 'email-already-used' })
      throw error
    }
  }

  if (path === '/account/login') {
    const user = repo.loginAccount(body.login, body.password)
    if (!user) return json(res, 401, { ok: false, error: 'invalid-login' })
    const session = repo.createWebSession(user.id)
    accountCookie(res, session.token)
    return json(res, 200, { ok: true, account: publicAccount(repo.userById(user.id)), snapshot: accountSnapshot(repo.userById(user.id)) })
  }

  if (path === '/account/logout') {
    repo.revokeWebSession(accountToken(req))
    accountCookie(res, '', 0)
    return json(res, 200, { ok: true })
  }

  if (path === '/account/forgot-password') {
    const email = String(body.email || '').trim().toLowerCase()
    if (emailIsValid(email)) {
      const outcome = await dispatchLoginCode(email, { create: false })
      if (outcome.payload?.code_sent) {
        return json(res, 200, { ok: true, code_sent: true, message: 'Se a conta existir, um código de acesso foi enviado ao e-mail.' })
      }
      if (outcome.status === 429 || outcome.status === 502) return json(res, outcome.status, outcome.payload)
    }
    return json(res, 200, { ok: true, recovery_required: true, message: 'Sem SMTP configurado, use o código de recuperação criado junto com a conta.' })
  }

  if (path === '/account/reset-password') {
    // Via nova: e-mail + código recebido. Via antiga: código de recuperação RV-.
    const email = String(body.email || '').trim().toLowerCase()
    if (email && body.code) {
      const user = repo.userByLogin(email)
      if (!user || !passwordIsValid(body.new_password) || !repo.consumeLoginCode(email, body.code)) {
        return json(res, 400, { ok: false, error: 'recovery-data-invalid' })
      }
      repo.updatePassword(user.id, body.new_password)
      return json(res, 200, { ok: true, message: 'Senha redefinida. Faça login com e-mail e senha.' })
    }
    const user = repo.userByLogin(body.login)
    if (!user || !passwordIsValid(body.new_password) || !repo.verifyRecoveryCode(user.id, body.recovery_code)) {
      return json(res, 400, { ok: false, error: 'recovery-data-invalid' })
    }
    repo.updatePassword(user.id, body.new_password)
    return json(res, 200, { ok: true, message: 'Senha redefinida. Faça login novamente.' })
  }

  const user = repo.userByWebSession(accountToken(req))
  if (!user) return json(res, 401, { ok: false, error: 'session-expired' })

  if (path === '/account/profile') {
    const email = String(body.email || '').trim().toLowerCase()
    const displayName = String(body.display_name || '').trim().slice(0, 48)
    if (email && !emailIsValid(email)) return json(res, 400, { ok: false, error: 'email-invalid' })
    const owner = email ? repo.userByLogin(email) : null
    if (owner && owner.id !== user.id) return json(res, 409, { ok: false, error: 'email-already-used' })
    repo.updateProfile(user.id, { email, displayName })
    return json(res, 200, { ok: true, account: publicAccount(repo.userById(user.id)) })
  }

  if (path === '/account/password') {
    // Conta nascida por código de e-mail (password_set=0) define a primeira
    // senha sem precisar de current_password — a sessão web já é a prova.
    const firstPassword = user.password_set === 0
    if ((!firstPassword && !repo.login(user.id, body.current_password)) || !passwordIsValid(body.new_password)) {
      return json(res, 400, { ok: false, error: 'password-data-invalid' })
    }
    repo.updatePassword(user.id, body.new_password)
    return json(res, 200, { ok: true, message: firstPassword ? 'Senha criada com sucesso.' : 'Senha alterada com sucesso.' })
  }

  // Vínculo: adota a conta do jogo (progresso do login-device) passando a
  // identidade de e-mail dela a pertencer a esta sessão.
  if (path === '/account/claim-game') {
    const gameId = Number.parseInt(body.game_user_id)
    if (!Number.isInteger(gameId)) return json(res, 400, { ok: false, error: 'game-user-id-invalid' })
    const result = repo.claimGameAccount(user.id, gameId)
    const statusByError = { 'not-found': 404, 'already-claimed': 409, 'site-account-has-progress': 409 }
    if (result.error) {
      const status2 = statusByError[result.error] || 400
      return json(res, status2, { ok: false, error: result.error })
    }
    const session = repo.createWebSession(result.account.id)
    accountCookie(res, session.token)
    return json(res, 200, { ok: true, account: publicAccount(result.account), message: 'Conta do jogo vinculada a este e-mail.' })
  }

  return json(res, 404, { ok: false, error: 'not-found' })
}

function requestProtocol (req) {
  if (String(process.env.TRUST_PROXY || 'true').toLowerCase() !== 'false') {
    const forwarded = req.headers['x-forwarded-proto']
    if (typeof forwarded === 'string' && forwarded) return forwarded.split(',')[0].trim()
  }
  return req.socket.encrypted ? 'https' : 'http'
}

function requestHost (req) {
  if (String(process.env.TRUST_PROXY || 'true').toLowerCase() !== 'false') {
    const forwarded = req.headers['x-forwarded-host']
    if (typeof forwarded === 'string' && forwarded) return forwarded.split(',')[0].trim()
  }
  return req.headers.host || '127.0.0.1:8080'
}

async function readJsonBody (req, limit = 2 * 1024 * 1024) {
  const contentType = String(req.headers['content-type'] || '').toLowerCase()
  if (!contentType.startsWith('application/json')) {
    const error = new Error('content-type')
    error.httpStatus = 400
    error.gameCode = 2200
    throw error
  }

  const chunks = []
  let size = 0
  for await (const chunk of req) {
    size += chunk.length
    if (size > limit) {
      const error = new Error('body-too-large')
      error.httpStatus = 413
      error.gameCode = 2200
      throw error
    }
    chunks.push(chunk)
  }
  if (size === 0) return {}
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'))
  } catch {
    const error = new Error('invalid-json')
    error.httpStatus = 400
    error.gameCode = 2200
    throw error
  }
}

function reloadRuntime () {
  runtime = loadRuntimeConfig()
  return runtime
}

function startOfUtcDayEpoch () {
  const now = new Date()
  return Math.floor(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()) / 1000)
}

function playerUserData (user) {
  const settings = repo.settings(user.id)
  return {
    user_data: {
      inventory: inventoryWire(repo, user.id, runtime),
      chapter_progression: chapterProgressionWire(repo, user.id),
      talent_progression: { talents: [] },
      tutorial_progression: tutorialProgressionWire(repo, user.id),
      account_age: Math.max(0, nowSeconds() - user.created_at),
      player: {
        level: { current: user.level, max: user.level, details_current: {}, details_next: {} },
        chapter_progression: user.chapter_progression,
        stats: playerStatsWire(repo, user.id)
      },
      total_attempt_count: user.attempt_count,
      player_settings: settings
        ? {
            blood_built_in: settings.blood_built_in,
            blood_cosmetic: settings.blood_cosmetic,
            confirm_gem_spend: Boolean(settings.confirm_gem_spend),
            skin_randomization: settings.skin_randomization
          }
        : null,
      last_login: nowSeconds()
    }
  }
}

function storePayload () {
  const day = new Date()
  day.setUTCHours(0, 0, 0, 0)
  const dayStart = Math.floor(day.getTime() / 1000)
  const week = new Date(day)
  week.setUTCDate(week.getUTCDate() - week.getUTCDay())
  const weekStart = Math.floor(week.getTime() / 1000)
  return {
    day_start_epoch: dayStart,
    day_end_epoch: dayStart + 86400,
    week_start_epoch: weekStart,
    week_end_epoch: weekStart + 604800,
    store_quota_purchases: [],
    store_items: activePacks(runtime).map(x => packToStoreItem(x, runtime)),
    iap_items: [],
    ad_items: []
  }
}

// Token de sessão JWT (ver jwt.js): o cliente real exige JWT bem formado no
// register/login/refresh — o token opaco da coluna users.token continua como
// fallback legado na autenticação.
function issueSessionToken (userId) {
  return createSessionToken(userId, { secret: sessionSecret(runtime.revival) })
}

function bootstrapUser (body, accountOptions = {}) {
  const { user, password, recoveryCode } = repo.createUser(accountOptions)

  if (runtime.gameData && runtime.revival.auto_starter_bundle !== false) {
    try {
      const starter = seedStarterBundle(repo, user.id, runtime)
      if (!starter.seeded) console.warn(`[starter] ${starter.reason}`)
    } catch (error) {
      console.warn(`[starter] falha ao aplicar bundle: ${error.message}`)
    }
  }

  for (const entry of (runtime.revival.initial_resources || [])) {
    try {
      giveGameResource(repo, user.id, entry, runtime)
    } catch (error) {
      console.warn(`Starter resource custom ignorado: ${error.message}`)
    }
  }

  return {
    user_id: user.id,
    device_id: typeof body.device_id === 'string' && body.device_id ? body.device_id : user.uuid,
    password,
    recovery_code: recoveryCode,
    token: issueSessionToken(user.id),
    session_id: 1,
    puuid: user.uuid,
    legal: {
      tos_version: 1,
      pp_version: 1,
      eula_version: 1,
      allow_personalization: false,
      allow_sharing: false
    },
    playfab_session_ticket: null
  }
}

function loginUser (body) {
  const userId = Number.parseInt(body?.user_id)
  if (body?.client_version !== runtime.revival.client_version || !Number.isInteger(userId) || typeof body?.password !== 'string') {
    return { error: [400, 2200] }
  }
  const user = repo.login(userId, body.password)
  if (!user) return { error: [403, 2101] }
  return {
    userId: user.id,
    data: {
      token: issueSessionToken(user.id),
      session_id: 1,
      puuid: user.uuid,
      legal: {
        tos_version: 1,
        pp_version: 1,
        eula_version: 1,
        allow_personalization: false,
        allow_sharing: false
      },
      playfab_session_ticket: null
    }
  }
}

function handleBaseline (path, body, user) {
  if (path === '/game/session/heartbeat') return { data: {} }
  if (path === '/game/session/refresh') return { data: { token: issueSessionToken(user.id) } }
  if (path === '/game/identity/list') return { data: { identities: [] } }
  if (path === '/game/identity/link-game-center' || path === '/game/identity/link-google-play-games') return { error: [400, 2000] }

  if (path === '/game/daily-rewards/get-state') {
    const dayStart = startOfUtcDayEpoch()
    const state = repo.getState(user.id, 'daily-rewards', 'state', {
      day: 1,
      last_claim: 0,
      pending: [],
      claimed: []
    })
    return {
      data: {
        state: {
          day_start: dayStart,
          day_end: dayStart + 86400,
          day: state.day ?? 1,
          last_claim: state.last_claim ?? 0,
          pending: Array.isArray(state.pending) ? state.pending : [],
          claimed: Array.isArray(state.claimed) ? state.claimed : []
        }
      }
    }
  }

  if (path === '/game/idle-rewards/get-state') {
    // Mesma projeção de estado do claim/boost: inicializa last_claim na
    // primeira leitura e deriva next_claim do período configurado (o cliente
    // usa next_claim para habilitar o resgate; 0 fixo mentia sobre o estado).
    return { data: { state: idleRewardState(repo, user.id, runtime) } }
  }

  // IdleRewardApi.Boost()/AdBoost(rewardTokenId): sem DTO -> envelope puro;
  // os períodos pendentes são concedidos multiplicados e o cliente relê o
  // get-state. Sem config de boost o erro é explícito (2300).
  if (path === '/game/idle-rewards/boost') {
    const result = boostIdleReward(repo, user.id, runtime)
    if (!result.ok) return { error: [400, 2300, { reason: result.reason }] }
    return { data: {} }
  }

  if (path === '/game/idle-rewards/ad-boost') {
    const tokenId = Number.isInteger(body?.reward_token_id) ? body.reward_token_id : null
    const found = findAdRewardToken(repo, user.id, tokenId, 'idle_reward_boost')
    if (found.error) return { error: found.error }
    const result = boostIdleReward(repo, user.id, runtime, undefined, { tokenId, tokens: found.tokens })
    if (!result.ok) return { error: [400, 2300, { reason: result.reason }] }
    return { data: {} }
  }

  // InventoryApi.ExchangeCurrency(inputCurrencyId, outputCurrencyId,
  // outputCurrencyAmount) -> ExchangeCurrencyResponse sem campos (envelope).
  // Taxa em gameData.currency_exchange [{input_rid, output_rid, rate}] onde
  // rate = unidades de input por 1 de output.
  if (path === '/game/inventory/exchange-currency') {
    const inputRid = body?.input_currency_id
    const outputRid = body?.output_currency_id
    const outputAmount = body?.output_currency_amount
    if (!Number.isInteger(inputRid) || !Number.isInteger(outputRid)) {
      return { error: [400, 2200, { reason: 'currency-required' }] }
    }
    if (!Number.isInteger(outputAmount) || outputAmount <= 0) {
      return { error: [400, 2200, { reason: 'amount-required' }] }
    }
    const rows = Array.isArray(runtime.gameData?.currency_exchange) ? runtime.gameData.currency_exchange : []
    const row = rows.find(entry => entry?.input_rid === inputRid && entry?.output_rid === outputRid)
    if (!row || !Number.isFinite(Number(row.rate)) || Number(row.rate) <= 0) {
      return { error: [400, 2300, { reason: 'exchange-not-configured' }] }
    }
    const inputCost = Math.ceil(outputAmount * Number(row.rate))
    if (repo.balance(user.id, inputRid) < inputCost) {
      return { error: [400, 2300, { reason: 'insufficient-currency' }] }
    }
    repo.tx(() => {
      repo.addCurrency(user.id, inputRid, -inputCost)
      // Saída via giveGameResource: respeita a categoria do recurso
      // (energia tem regeneração/teto próprios, não é currency simples).
      giveGameResource(repo, user.id, { rid: outputRid, amount: outputAmount }, runtime)
    })
    return { data: {} }
  }

  // SessionApi.UpdateLegal(tosVersion, ppVersion, eulaVersion,
  // allowPersonalization, allowThirdPartySharing) -> envelope puro.
  if (path === '/game/session/update-legal') {
    const legal = {
      tos_version: body?.tos_version ?? null,
      pp_version: body?.pp_version ?? null,
      eula_version: body?.eula_version ?? null,
      allow_personalization: body?.allow_personalization === true,
      allow_third_party_sharing: body?.allow_third_party_sharing === true,
      updated_at: Math.floor(Date.now() / 1000)
    }
    repo.setState(user.id, 'session', 'legal', legal)
    return { data: {} }
  }

  // PlayerApi.SetPushToken(pushToken) -> SetPushTokenResponse sem campos.
  if (path === '/game/player/set-push-token') {
    if (typeof body?.push_token !== 'string' || body.push_token.length === 0) {
      return { error: [400, 2200, { reason: 'push-token-required' }] }
    }
    repo.setState(user.id, 'player', 'push_token', body.push_token)
    return { data: {} }
  }

  // DevicesApi: Register/Unregister/List/Describe — AuthorizedDevice no wire.
  if (path.startsWith('/game/devices/')) {
    const handled = handleDevicesRequest(path, body, user.id, repo)
    if (handled) return handled
  }

  // CodesApi.Redeem(code): códigos de gameData.codes, resgate 1x por jogador.
  if (path === '/game/codes/redeem') return redeemCode(repo, user.id, body, runtime)

  // Rotas platform-gated (xbox/bnet/identity de plataforma): indisponibilidade
  // real ou gate verdadeiro — ver src/platform.js.
  {
    const handled = handlePlatformRequest(path, body)
    if (handled) return handled
  }

  if (path === '/game/inventory/get-equip-sequence-id') {
    return { data: { sequence_id: repo.getState(user.id, 'inventory', 'equip_sequence_id', 0) } }
  }

  if (path === '/game/inventory/equip') {
    const slotId = body?.slot
    const itemId = body?.item
    if (!Number.isInteger(slotId) || !Number.isInteger(itemId)) return { error: [400, 2200] }
    const success = repo.tx(() => {
      if (!repo.setSlot(user.id, slotId, itemId)) return false
      const previous = repo.getState(user.id, 'inventory', 'equip_sequence_id', 0)
      repo.setState(user.id, 'inventory', 'equip_sequence_id', previous + 1)
      return true
    })
    if (!success) return { error: [400, 2000] }
    return { data: { sequence_id: repo.getState(user.id, 'inventory', 'equip_sequence_id', 0) } }
  }

  if (path === '/game/player/increment-stats') {
    incrementPlayerStats(repo, user.id, body, runtime)
    return { data: {} }
  }

  // PlayerApi.GetStats() -> StatsResponse{stats} de StatModel{id, value}
  if (path === '/game/player/stats') {
    return { data: { stats: playerStatsWire(repo, user.id) } }
  }
  return null
}

function handleAuthed (path, body, user, req) {
  const baseline = handleBaseline(path, body, user)
  if (baseline) return baseline

  const compat = handleCompatRequest(path, body, user.id, repo, runtime)
  if (compat) return compat

  const chapter = handleChapterRequest(path, body, user.id, repo, runtime)
  if (chapter) return chapter

  const inbox = handleInboxRequest(path, body, user.id, repo, runtime)
  if (inbox) return inbox

  const tutorial = handleTutorialRequest(path, body, user.id, repo, runtime)
  if (tutorial) return tutorial

  if (path === '/game/player/game-data-token') {
    return {
      data: {
        url: `${requestProtocol(req)}://${requestHost(req)}/data`,
        token: runtime.revival.game_data_token,
        version_id: runtime.revival.game_data_version_id || 'revival-local'
      }
    }
  }

  if (path === '/game/player/update-settings') {
    repo.saveSettings(user.id, body?.settings || {})
    return { data: {} }
  }

  if (path === '/game/player/user-data') return { data: playerUserData(repo.userById(user.id)) }

  // O cliente 1.13.1 faz foreach em ArmoryController.Init(upgrades); sem o
  // array no wire a desserialização deixa null e a iteração NRE-derruba o
  // boot da sessão — o handler devolve array (vazio sem config, nunca null).
  if (path.startsWith('/game/armory/')) {
    const handled = handleArmoryRequest(path, body, user.id, repo, runtime)
    if (handled) return handled
  }

  if (path === '/game/store/get') return { data: storePayload() }
  if (path === '/game/store/get-offers') return { data: { store_items: [], iap_items: [], ad_items: [], offers: [] } }
  if (path === '/game/store/get-daily-offers' || path === '/game/store/activate-daily-offers') return { data: { daily_offers: [] } }
  if (path === '/game/store/purchase') {
    const itemId = body?.item
    if (!Number.isInteger(itemId)) return { error: [400, 2200] }
    const result = purchasePack(repo, user.id, itemId, runtime)
    if (!result.ok) return { error: [400, 2000, { reason: result.reason }] }
    return { data: { resources: result.resources } }
  }

  // StoreApi (metadata v29): GetItems/GetOfferItems -> {storeItems, iapItems,
  // adItems}; GetPlayerOffers -> {offers}; ActivateOffer(offerId,
  // gearResourceId) -> {offer}; AdPurchaseItem(itemId, rewardTokenId) ->
  // AdPurchaseResponse{resources} consumindo token StoreItemCrate/Gold.
  if (path === '/game/store/get-items' || path === '/game/store/get-offer-items') {
    return { data: storeItemsWire(runtime) }
  }
  if (path === '/game/store/get-player-offers') {
    return { data: { offers: activatedOfferWires(repo, user.id, runtime) } }
  }
  if (path === '/game/store/activate-offer') return activateStoreOffer(repo, user.id, body, runtime)
  if (path === '/game/store/ad-purchase') return adPurchasePack(repo, user.id, body, runtime)

  if (path.startsWith('/game/events/')) {
    const handled = handleEventRequest(path, body, user.id, repo, runtime)
    if (handled) return handled
  }

  // Consulta READ-ONLY do histórico de compras. Não reativa IAP: comprar
  // continua desligado logo abaixo. Medido no rig em 2026-08-20 (request_log
  // 323): o cliente chama esta rota no boot e o 400/2000 derrubou o parse com
  // `Malformed response payload`, abortando o restart.
  //
  // Contrato extraído do metadata v29 (IapApi.GetIapPurchaseHistory ->
  // IapHistoryPurchaseResponse): campos `timeSinceLastPurchase` e
  // `totalLifetimePurchase`. Sem nenhuma compra, `total_lifetime_purchase` é 0
  // e `time_since_last_purchase` é OMITIDO — numérico sem valor nunca vai como
  // null (DEAD-ENDS #3), e omitir deixa o default do tipo concreto valer.
  if (path === '/game/iap/get-purchase-history-info') {
    return { data: { total_lifetime_purchase: 0 } }
  }
  if (path.startsWith('/game/iap/')) return { error: [400, 2000, { iap_disabled: true }] }
  if (path.startsWith('/game/ads/')) return { data: { ads_disabled: true } }

  return null
}

// O cliente oficial monta as URLs a partir da base da API Gear
// ("https://international.gear.bethesda.net/collections/doom"). O patch de
// hostname preserva o path do literal, então as chamadas do APK chegam como
// "/collections/doom/game/...". Normalizamos removendo esse prefixo antes de
// rotear; as rotas internas continuam sendo apenas "/game/*".
const GEAR_COLLECTION_PREFIX = /^\/collections\/[A-Za-z0-9._-]+(?=\/|$)/

function normalizePath (pathname) {
  if (!GEAR_COLLECTION_PREFIX.test(pathname)) return pathname
  return pathname.replace(GEAR_COLLECTION_PREFIX, '') || '/'
}

async function handle (req, res) {
  const url = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`)
  const path = normalizePath(url.pathname)

  if (req.method === 'GET' && path === '/revival/health') {
    return json(res, 200, {
      ok: true,
      // Identidade da instância que respondeu (instance.js). Sem isto,
      // client_version/api_version eram idênticos entre local e VPS e não
      // distinguiam as duas instâncias. Nada aqui é segredo e nada toca `game/*`.
      ...instanceIdentity(),
      server: runtime.revival.server_name,
      client_version: runtime.revival.client_version,
      api_version: runtime.revival.api_version,
      game_data_loaded: Boolean(runtime.gameData),
      packs: activePacks(runtime).length,
      events: runtime.events.filter(x => x.active !== false).length,
      players: repo.countUsers(),
      uptime_seconds: Math.floor(process.uptime()),
      apk_available: site.apkInfo().available,
      research_mode: researchMode(),
      runtime: 'node-builtin-http+sqlite'
    })
  }

  // Personalização do site público (editada pelo Super Admin em /slayer).
  if (req.method === 'GET' && path === '/revival/site') {
    return json(res, 200, { ok: true, site: runtime.site })
  }

  if (req.method === 'POST' && path === '/revival/reload') {
    if (!adminAuthorized(req)) return json(res, 401, { ok: false })
    const r = reloadRuntime()
    return json(res, 200, {
      ok: true,
      packs: activePacks(r).length,
      events: r.events.length,
      game_data_loaded: Boolean(r.gameData)
    })
  }

  if (await handleAccount(req, res, path)) return

  // Link temporário (10 min) para trocar os dados de acesso do Super Admin.
  if (await handleAdminRecover(req, res, path, { repo, tokenFile: adminRecoverTokenFile })) return

  // Estado do RESEARCH_MODE para o gate de convergência: quantos fallbacks
  // (endpoint desconhecido respondido com ok() vazio) aconteceram desde o
  // boot deste processo, por rota. Só expõe contagens — nenhum dado de
  // jogador. verify_everything.py/client_harness.py falham se houver
  // fallback em fluxo validado.
  if (req.method === 'GET' && path === '/revival/research') {
    const fallbacks = [...researchFallbacks.entries()]
      .map(([fallbackPath, entry]) => ({ path: fallbackPath, ...entry }))
      .sort((a, b) => b.count - a.count)
    return json(res, 200, {
      ok: true,
      research_mode: researchMode(),
      fallback_total: fallbacks.reduce((sum, entry) => sum + entry.count, 0),
      fallback_endpoints: fallbacks
    })
  }

  // Captura de evidência para o harness. Modo legacy (sem since_id): as
  // `limit` mais recentes, DESC. Modo incremental (?since_id=N&limit=M): só
  // linhas de id > N em ordem ASC — a sequência temporal real de UMA execução,
  // sem herdar requests antigos. `last_id` é o cursor do baseline.
  if (req.method === 'GET' && path === '/revival/requests') {
    if (!adminAuthorized(req)) return json(res, 401, { ok: false })
    const since = url.searchParams.get('since_id')
    const limit = Number(url.searchParams.get('limit') || 100)
    if (since !== null) {
      const rows = repo.requestsSince(since, limit)
      return json(res, 200, {
        ok: true,
        since_id: Math.max(0, Math.floor(Number(since) || 0)),
        last_id: rows.length ? rows[rows.length - 1].id : repo.requestLogCursor(),
        count: rows.length,
        requests: rows
      })
    }
    return json(res, 200, { ok: true, last_id: repo.requestLogCursor(), requests: repo.requestLog(limit) })
  }

  // Site público (/), assets, download do APK e links temporários de upload.
  // Retorna false para rotas que não são dele, caindo no /data e /game/*.
  if (site.handle(req, res, path)) return

  if (req.method === 'GET' && path === '/data') {
    const token = req.headers.authorization
    if (typeof token !== 'string' || !token.endsWith(runtime.revival.game_data_token)) {
      res.writeHead(403)
      return res.end()
    }
    if (!runtime.gameData || !existsSync(runtime.paths.gameDataPath)) {
      return json(res, 503, { error: 'game-data.json ainda não foi importado', path: runtime.paths.gameDataPath })
    }
    const raw = readFileSync(runtime.paths.gameDataPath)
    res.writeHead(200, {
      'content-type': 'application/json; charset=utf-8',
      'content-length': raw.length,
      'cache-control': 'no-store'
    })
    return res.end(raw)
  }

  if (!path.startsWith('/game/')) return json(res, 404, { ok: false, error: 'not-found' })
  // Evidência de execução: TODA rota /game/* (register e login incluídos,
  // mesmo rejeitados pelos guards) vira uma linha com request e response
  // pareados quando a resposta sai — ver persistGameLog().
  res.revivalGameLog = { path, method: req.method, body: null, userId: null }
  const gameLog = res.revivalGameLog
  if (req.method !== 'POST') return fail(res, 405, 2200)
  if (req.headers['x-ubu-apiversion'] !== runtime.revival.api_version) return fail(res, 403, 2200)

  let body
  try {
    body = await readJsonBody(req)
  } catch (error) {
    return fail(res, error.httpStatus || 400, error.gameCode || 2200)
  }
  gameLog.body = body

  if (path === '/game/auth/register') {
    if (body?.client_version !== runtime.revival.client_version) return fail(res, 400, 2200)
    if (req.headers['x-ubu-token']) return fail(res, 403, 2200)
    const created = bootstrapUser(body)
    gameLog.userId = created.user_id
    return ok(res, created)
  }

  if (path === '/game/auth/login-device') {
    const result = loginUser(body)
    if (result.error) return fail(res, ...result.error)
    gameLog.userId = result.userId
    return ok(res, result.data)
  }

  if (path === '/game/auth/login-xbox' || path === '/game/auth/login-google-play-games' || path === '/game/auth/login-game-center') {
    // Logins de plataforma: código REAL de indisponibilidade do ResponseCode
    // (extraído do metadata) — o Revival não fala com Xbox/Google/Game Center.
    const platformError = platformLoginError(path)
    return fail(res, ...platformError.error)
  }

  const token = extractToken(req)
  // JWT assinado primeiro; token opaco legado (users.token) como fallback.
  const session = token ? verifySessionToken(token, sessionSecret(runtime.revival)) : null
  const user = session ? repo.userById(session.userId) : (token ? repo.userByToken(token) : null)
  if (!user) return fail(res, 401, 2101)
  gameLog.userId = user.id

  try {
    const result = handleAuthed(path, body, user, req)
    if (result?.error) return fail(res, ...result.error)
    if (result) return ok(res, result.data)
  } catch (error) {
    console.error(`[${path}]`, error)
    return fail(res, 400, 2000)
  }

  if (researchMode()) {
    console.warn(`[research] endpoint ainda não implementado: ${path}`)
    recordResearchFallback(path)
    gameLog.note = 'research-fallback'
    return ok(res)
  }
  return fail(res, 404, 2000)
}

const host = process.env.HOST || '0.0.0.0'
const port = Number.parseInt(process.env.PORT || '8080')
const server = createServer((req, res) => {
  const startedAt = Date.now()
  res.on('finish', () => {
    if (req.url?.startsWith('/game') || req.url === '/data' || (req.url || '').startsWith('/collections')) {
      console.log(`[req] ${req.method} ${req.url} -> ${res.statusCode} ${res.getHeader('content-length') || '?'}B ${Date.now() - startedAt}ms`)
    }
  })
  handle(req, res).catch(error => {
    console.error(error)
    if (!res.headersSent) fail(res, 500, 2000)
    else res.destroy()
  })
})

server.on('error', error => {
  if (error?.code === 'EADDRINUSE') {
    console.error(`[ERRO] Porta ${port} já está em uso em ${host}. Altere PORT no server/.env ou encerre o processo que ocupa a porta.`)
  } else if (error?.code === 'EACCES') {
    console.error(`[ERRO] Sem permissão para abrir ${host}:${port}.`)
  } else {
    console.error('[ERRO] Falha ao iniciar servidor:', error)
  }
  try { repo.close() } catch {}
  process.exitCode = 2
})

server.listen(port, host, () => {
  console.log(`${runtime.revival.server_name} ouvindo em http://${host}:${port}`)
  console.log(`SQLite: ${dbPath}`)
  console.log(`Site público: ${publicDir}`)
  if (!runtime.gameData) console.warn(`ATENÇÃO: game-data.json ausente em ${runtime.paths.gameDataPath}`)
})

function shutdown (signal) {
  console.log(`Recebido ${signal}; encerrando...`)
  server.close(() => {
    try { repo.close() } catch {}
    process.exit(0)
  })
  setTimeout(() => process.exit(1), 5000).unref()
}

process.on('SIGINT', () => shutdown('SIGINT'))
process.on('SIGTERM', () => shutdown('SIGTERM'))
