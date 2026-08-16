import { createServer } from 'node:http'
import { existsSync, readFileSync } from 'node:fs'
import { isAbsolute, resolve } from 'node:path'
import { loadEnvFile } from 'node:process'

import { chapterProgressionWire, handleChapterRequest } from './chapters.js'
import { handleCompatRequest } from './compat.js'
import { loadRuntimeConfig, researchMode } from './config.js'
import { Repository } from './db.js'
import { eventProgress, eventSchedule } from './events.js'
import { inventoryWire, seedStarterBundle, giveGameResource } from './game-data-model.js'
import { playerStatsWire, incrementPlayerStats } from './stats.js'
import { activePacks, packToStoreItem, purchasePack } from './store.js'
import { handleTutorialRequest, tutorialProgressionWire } from './tutorial.js'

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

function nowSeconds () {
  return Math.floor(Date.now() / 1000)
}

function wire (data = {}, code = 1000) {
  return { uts: nowSeconds(), code, ...data }
}

function json (res, status, payload) {
  const body = JSON.stringify(payload)
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(body),
    'cache-control': 'no-store'
  })
  res.end(body)
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

function chooseIdleGeneration (gameData, chapterProgression) {
  const idle = gameData?.idle_reward
  const table = Array.isArray(idle?.chapter_idle_generation) ? idle.chapter_idle_generation : []
  let chosen = null
  for (const row of table) {
    if (typeof row?.chapter_progress !== 'number') continue
    if (row.chapter_progress > chapterProgression) continue
    if (chosen === null || row.chapter_progress >= chosen.chapter_progress) chosen = row
  }
  return {
    idle_generation: chosen?.idle_generation ?? [],
    generation_period: idle?.generation_period ?? 0
  }
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

function bootstrapUser (body) {
  const { user, password } = repo.createUser()

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
    token: user.token,
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
    data: {
      token: user.token,
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
  if (path === '/game/session/refresh') return { data: { token: user.token } }
  if (path === '/game/identity/list') return { data: { identities: [] } }
  if (path === '/game/identity/link-game-center' || path === '/game/identity/link-google-play-games') return { error: [400, 2000] }
  if (path === '/game/inbox/get-messages') return { data: { messages: [] } }
  if (path === '/game/reward-tracks/get-all') return { data: { tracks: [] } }

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
    const current = repo.userById(user.id)
    return {
      data: {
        state: {
          last_claim: repo.getState(user.id, 'idle-rewards', 'last_claim', 0),
          boost_available: 0,
          next_claim: 0,
          ...chooseIdleGeneration(runtime.gameData, current.chapter_progression)
        }
      }
    }
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
  return null
}

function handleAuthed (path, body, user, req) {
  const baseline = handleBaseline(path, body, user)
  if (baseline) return baseline

  const compat = handleCompatRequest(path, body, user.id, repo, runtime)
  if (compat) return compat

  const chapter = handleChapterRequest(path, body, user.id, repo)
  if (chapter) return chapter

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

  if (path === '/game/events/get-schedule') return { data: { scheduled_events: eventSchedule(runtime) } }
  if (path === '/game/events/get-progress') return { data: eventProgress(repo, user.id, runtime) }

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
      server: runtime.revival.server_name,
      client_version: runtime.revival.client_version,
      api_version: runtime.revival.api_version,
      game_data_loaded: Boolean(runtime.gameData),
      packs: activePacks(runtime).length,
      events: runtime.events.filter(x => x.active !== false).length,
      research_mode: researchMode(),
      runtime: 'node-builtin-http+sqlite'
    })
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

  if (req.method === 'GET' && path === '/revival/requests') {
    if (!adminAuthorized(req)) return json(res, 401, { ok: false })
    return json(res, 200, { ok: true, requests: repo.requestLog(Number(url.searchParams.get('limit') || 100)) })
  }

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
  if (req.method !== 'POST') return fail(res, 405, 2200)
  if (req.headers['x-ubu-apiversion'] !== runtime.revival.api_version) return fail(res, 403, 2200)

  let body
  try {
    body = await readJsonBody(req)
  } catch (error) {
    return fail(res, error.httpStatus || 400, error.gameCode || 2200)
  }

  if (path === '/game/auth/register') {
    if (body?.client_version !== runtime.revival.client_version) return fail(res, 400, 2200)
    if (req.headers['x-ubu-token']) return fail(res, 403, 2200)
    return ok(res, bootstrapUser(body))
  }

  if (path === '/game/auth/login-device') {
    const result = loginUser(body)
    if (result.error) return fail(res, ...result.error)
    return ok(res, result.data)
  }

  if (path === '/game/auth/login-google-play-games' || path === '/game/auth/login-game-center') return fail(res, 400, 2000)

  const token = extractToken(req)
  const user = token ? repo.userByToken(token) : null
  if (!user) return fail(res, 401, 2101)

  repo.logRequest(user.id, path, body)

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
    return ok(res)
  }
  return fail(res, 404, 2000)
}

const host = process.env.HOST || '0.0.0.0'
const port = Number.parseInt(process.env.PORT || '8080')
const server = createServer((req, res) => {
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
