import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import Koa from 'koa'
import Router from '@koa/router'
import { bodyParser } from '@koa/bodyparser'

import { loadRuntimeConfig, researchMode, resolveResource } from './config.js'
import { Repository } from './db.js'
import { eventProgress, eventSchedule } from './events.js'
import { fail, gameGuard, ok, requireUser } from './protocol.js'
import { activePacks, packToStoreItem, purchasePack } from './store.js'

let runtime = loadRuntimeConfig()
const dbPath = process.env.DB_PATH || 'server/runtime/revival.sqlite3'
const repo = new Repository(dbPath)
const app = new Koa({ proxy: String(process.env.TRUST_PROXY || 'true').toLowerCase() !== 'false' })
const root = new Router()
const game = new Router({ prefix: '/game' })

function currentRuntime () { return runtime }
function reloadRuntime () { runtime = loadRuntimeConfig(); return runtime }

app.use(async (ctx, next) => {
  try {
    await next()
  } catch (error) {
    console.error(error)
    if (!ctx.headerSent) fail(ctx, 500, 2000)
  }
})
app.use(bodyParser({ enableTypes: ['json'], jsonLimit: '2mb' }))

root.get('/revival/health', ctx => {
  const r = currentRuntime()
  ctx.body = {
    ok: true,
    server: r.revival.server_name,
    client_version: r.revival.client_version,
    api_version: r.revival.api_version,
    game_data_loaded: Boolean(r.gameData),
    packs: activePacks(r).length,
    events: r.events.filter(x => x.active !== false).length,
    research_mode: researchMode()
  }
})

root.post('/revival/reload', ctx => {
  const expected = process.env.REVIVAL_ADMIN_TOKEN
  if (!expected || ctx.get('authorization') !== `Bearer ${expected}`) {
    ctx.status = 401
    ctx.body = { ok: false }
    return
  }
  const r = reloadRuntime()
  ctx.body = { ok: true, packs: activePacks(r).length, events: r.events.length, game_data_loaded: Boolean(r.gameData) }
})

root.get('/data', ctx => {
  const r = currentRuntime()
  const token = ctx.get('authorization')
  if (!token || !token.endsWith(r.revival.game_data_token)) {
    ctx.status = 403
    return
  }
  if (!r.gameData || !existsSync(r.paths.gameDataPath)) {
    ctx.status = 503
    ctx.type = 'application/json'
    ctx.body = { error: 'game-data.json ainda não foi importado', path: r.paths.gameDataPath }
    return
  }
  ctx.type = 'application/json'
  ctx.body = readFileSync(r.paths.gameDataPath, 'utf8')
})

app.use(root.routes()).use(root.allowedMethods())

game.use(gameGuard(currentRuntime))

game.post('/auth/register', ctx => {
  const r = currentRuntime()
  if (ctx.request.body?.client_version !== r.revival.client_version) return fail(ctx, 400, 2200)
  if (ctx.get('x-ubu-token')) return fail(ctx, 403, 2200)

  const { user, password } = repo.createUser()
  for (const entry of (r.revival.initial_resources || [])) {
    try {
      const rid = resolveResource(entry.resource ?? entry.rid, r)
      if ((entry.kind || 'currency') === 'currency') repo.addCurrency(user.id, rid, Number(entry.amount || 0))
      else repo.addItem(user.id, { rid, kind: entry.kind, amount: entry.amount, level: entry.level, tier: entry.tier })
    } catch (error) {
      console.warn(`Starter resource ignorado: ${error.message}`)
    }
  }

  ok(ctx, {
    user_id: user.id,
    device_id: '00000000-0000-0000-0000-000000000000',
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
  })
})

game.post('/auth/login-device', ctx => {
  const r = currentRuntime()
  const userId = Number.parseInt(ctx.request.body?.user_id)
  const password = ctx.request.body?.password
  if (ctx.request.body?.client_version !== r.revival.client_version || !Number.isInteger(userId) || typeof password !== 'string') {
    return fail(ctx, 400, 2200)
  }
  const user = repo.login(userId, password)
  if (!user) return fail(ctx, 403, 2101)
  ok(ctx, {
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
  })
})

game.post('/auth/login-google-play-games', ctx => fail(ctx, 400, 2000))
game.post('/auth/login-game-center', ctx => fail(ctx, 400, 2000))

const authed = new Router()
authed.use(requireUser(repo))
authed.use(async (ctx, next) => {
  repo.logRequest(ctx.state.user.id, ctx.path, ctx.request.body)
  await next()
})

authed.post('/player/game-data-token', ctx => {
  const r = currentRuntime()
  ok(ctx, {
    url: `${ctx.protocol}://${ctx.host}/data`,
    token: r.revival.game_data_token,
    version_id: r.revival.game_data_version_id || 'revival-local'
  })
})

authed.post('/player/update-settings', ctx => {
  repo.saveSettings(ctx.state.user.id, ctx.request.body?.settings || {})
  ok(ctx)
})

authed.post('/player/user-data', ctx => {
  const user = repo.userById(ctx.state.user.id)
  const items = repo.items(user.id)
  const inventory = {
    currencies: repo.currencies(user.id),
    weapons: [],
    equipment: [],
    launchers: [],
    energies: [],
    ultimates: [],
    slayers: [],
    entitlements: [],
    slots: repo.slots(user.id).map(x => ({ slot: x.slot_id, item: x.item_id })),
    cosmetics: []
  }
  const bucket = {
    weapon: 'weapons',
    equipment: 'equipment',
    launcher: 'launchers',
    energy: 'energies',
    ultimate: 'ultimates',
    slayer: 'slayers',
    cosmetic: 'cosmetics'
  }
  for (const item of items) {
    const target = bucket[item.kind] || 'equipment'
    const wireItem = { rid: item.rid, uid: item.id, level: item.level }
    if (item.tier !== null) wireItem.tier = item.tier
    inventory[target].push(wireItem)
  }
  const settings = repo.settings(user.id)
  ok(ctx, {
    user_data: {
      inventory,
      chapter_progression: { chapters: [], challenges: [], current_run: null },
      talent_progression: { talents: [] },
      tutorial_progression: { sequences: [] },
      account_age: Math.max(0, Math.floor(Date.now() / 1000) - user.created_at),
      player: {
        level: { current: user.level, max: user.level, details_current: {}, details_next: {} },
        chapter_progression: user.chapter_progression,
        stats: []
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
      last_login: Math.floor(Date.now() / 1000)
    }
  })
})

authed.post('/store/get', ctx => {
  const r = currentRuntime()
  const day = new Date(); day.setUTCHours(0, 0, 0, 0)
  const dayStart = Math.floor(day.getTime() / 1000)
  const week = new Date(day); week.setUTCDate(week.getUTCDate() - week.getUTCDay())
  const weekStart = Math.floor(week.getTime() / 1000)
  let storeItems
  try {
    storeItems = activePacks(r).map(x => packToStoreItem(x, r))
  } catch (error) {
    console.error(error)
    return fail(ctx, 500, 2000)
  }
  ok(ctx, {
    day_start_epoch: dayStart,
    day_end_epoch: dayStart + 86400,
    week_start_epoch: weekStart,
    week_end_epoch: weekStart + 604800,
    store_quota_purchases: [],
    store_items: storeItems,
    iap_items: [],
    ad_items: []
  })
})

authed.post('/store/get-offers', ctx => ok(ctx, { store_items: [], iap_items: [], ad_items: [], offers: [] }))
authed.post('/store/get-daily-offers', ctx => ok(ctx, { daily_offers: [] }))
authed.post('/store/activate-daily-offers', ctx => ok(ctx, { daily_offers: [] }))

authed.post('/store/purchase', ctx => {
  const itemId = ctx.request.body?.item
  if (!Number.isInteger(itemId)) return fail(ctx, 400, 2200)
  try {
    const result = purchasePack(repo, ctx.state.user.id, itemId, currentRuntime())
    if (!result.ok) return fail(ctx, 400, 2000, { reason: result.reason })
    ok(ctx, { resources: result.resources })
  } catch (error) {
    console.error(error)
    fail(ctx, 400, 2000)
  }
})

authed.post('/events/get-schedule', ctx => ok(ctx, { scheduled_events: eventSchedule(currentRuntime()) }))
authed.post('/events/get-progress', ctx => ok(ctx, eventProgress(repo, ctx.state.user.id, currentRuntime())))

// Real-money functionality is deliberately disabled. Revival packages are
// exposed through /store and always cost game resources.
authed.post('/iap/:action', ctx => fail(ctx, 400, 2000, { iap_disabled: true }))
authed.post('/ads/:action', ctx => ok(ctx, { ads_disabled: true }))

// Safe baseline responses while the APK call graph is being mapped. Every
// unknown POST is recorded in request_log so we can implement it precisely.
authed.post(/.*/, ctx => {
  if (!researchMode()) return fail(ctx, 404, 2000)
  console.warn(`[research] endpoint ainda não implementado: ${ctx.path}`)
  ok(ctx)
})

game.use(authed.routes())
app.use(game.routes()).use(game.allowedMethods())

const host = process.env.HOST || '0.0.0.0'
const port = Number.parseInt(process.env.PORT || '8080')
app.listen(port, host, () => {
  console.log(`${currentRuntime().revival.server_name} ouvindo em http://${host}:${port}`)
  if (!currentRuntime().gameData) {
    console.warn(`ATENÇÃO: game-data.json ausente em ${resolve(currentRuntime().paths.gameDataPath)}`)
  }
})
