import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const serverRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const work = mkdtempSync(resolve(tmpdir(), 'mighty-doom-revival-smoke-'))
mkdirSync(resolve(work, 'config'), { recursive: true })
mkdirSync(resolve(work, 'data'), { recursive: true })
mkdirSync(resolve(work, 'runtime'), { recursive: true })

const revival = {
  server_name: 'Mighty DOOM Revival Smoke',
  api_version: '24.0.0',
  client_version: '1.13.1',
  game_data_token: 'smoke-game-data',
  game_data_version_id: 'smoke-v1',
  auto_starter_bundle: true,
  initial_resources: []
}

const gameData = {
  server_properties: { starter_bundle: 1 },
  resources: [
    { id: 100, tag: 'coins', category_id: 1 },
    { id: 101, tag: 'gems', category_id: 1 }
  ],
  weapons: [{ id: 200, tag: 'heavy_cannon', category_id: 2 }],
  slayers: [{ id: 300, tag: 'mini_slayer', category_id: 7 }],
  energies: [{ id: 400, tag: 'energy', category_id: 5, max_amount: 20, regen_minutes: 1 }],
  talents: {
    talents: [{ id: 500, cost: [{ resource: 'coins', amount: 50 }] }]
  },
  bundles: [{
    id: 1,
    tag: 'starter',
    resources: [
      { resource: { id: 100 }, kind: 'currency', amount: 2000 },
      { resource: { id: 200 }, kind: 'weapon', level: 1, tier: 1 },
      { resource: { id: 300 }, kind: 'slayer', level: 1, tier: 1 },
      { resource: { id: 400 }, kind: 'energy', amount: 10 }
    ]
  }],
  inventory: { slots: [{ id: 10, tag: 'slot_primary_weapon' }, { id: 11, tag: 'slot_slayer' }] },
  daily_rewards: {
    days: [{ resources: [{ resource: 'coins', amount: 25 }] }]
  },
  idle_reward: {
    generation_period: 1,
    chapter_idle_generation: [{ chapter_progress: 0, idle_generation: [{ rid: 100, amount: 1 }] }],
    boost: { multiplier: 2, cooldown: 3600 }
  },
  currency_exchange: [{ input_rid: 100, output_rid: 101, rate: 10 }],
  armory: {
    upgrades: [{
      id: 1,
      levels: [
        { cost: [{ rid: 100, amount: 25 }], chapter_progress: 0 },
        { cost: [{ rid: 100, amount: 20 }], chapter_progress: 2 }
      ]
    }]
  },
  store: {
    offers: [{ id: 5, item_id: 900100, allowed_purchases: 1, purchase_amount: 100 }]
  },
  codes: [{ code: 'REVIVAL', resources: [{ resource: 'coins', amount: 150 }] }],
  chapter_mode: {
    chapters: [{
      id: 101,
      stage_rewards: [{ stage: 1, resources: [{ rid: 100, amount: 5 }] }],
      challenges: [{ id: 1, completion_reward: [{ rid: 100, amount: 7 }] }]
    }]
  }
}

const packs = {
  packs: [{
    id: 900100,
    tag: 'revival_weapon_pack',
    active: true,
    cost: [{ resource: 'coins', kind: 'currency', amount: 500 }],
    contents: [{ resource: 'heavy_cannon', kind: 'weapon', level: 2, tier: 1 }],
    quota: { period: 'daily', max: 2 }
  }, {
    id: 900200,
    tag: 'revival_ad_crate',
    active: true,
    ad: true,
    cost: [],
    contents: [{ resource: 'gems', kind: 'currency', amount: 5 }]
  }]
}

const events = {
  events: [{
    id: 7001,
    event_definition_id: 7001,
    active: true,
    always: true,
    channel: 'game_mode',
    event_type: 1,
    args: { mode: 'smoke' },
    progress_template: { event_id: 7001, score: 0 }
  }]
}

function writeJson (path, value) {
  writeFileSync(path, JSON.stringify(value, null, 2))
}

writeJson(resolve(work, 'config/revival.json'), revival)
writeJson(resolve(work, 'config/packs.json'), packs)
writeJson(resolve(work, 'config/events.json'), events)
writeJson(resolve(work, 'data/game-data.json'), gameData)

async function freePort () {
  return await new Promise((resolvePort, reject) => {
    const socket = createServer()
    socket.once('error', reject)
    socket.listen(0, '127.0.0.1', () => {
      const address = socket.address()
      const port = address.port
      socket.close(error => error ? reject(error) : resolvePort(port))
    })
  })
}

const port = await freePort()
const base = `http://127.0.0.1:${port}`
const env = {
  ...process.env,
  HOST: '127.0.0.1',
  PORT: String(port),
  DB_PATH: resolve(work, 'runtime/revival.sqlite3'),
  GAME_DATA_PATH: resolve(work, 'data/game-data.json'),
  REVIVAL_CONFIG_PATH: resolve(work, 'config/revival.json'),
  PACKS_CONFIG_PATH: resolve(work, 'config/packs.json'),
  EVENTS_CONFIG_PATH: resolve(work, 'config/events.json'),
  REVIVAL_ADMIN_TOKEN: 'smoke-admin',
  RESEARCH_MODE: 'true'
}

const child = spawn(process.execPath, ['src/index.js'], {
  cwd: serverRoot,
  env,
  stdio: ['ignore', 'pipe', 'pipe']
})

let logs = ''
child.stdout.on('data', chunk => { logs += chunk.toString() })
child.stderr.on('data', chunk => { logs += chunk.toString() })

async function waitForHealth () {
  for (let i = 0; i < 50; i++) {
    try {
      const response = await fetch(`${base}/revival/health`)
      if (response.ok) return await response.json()
    } catch {}
    await new Promise(resolveWait => setTimeout(resolveWait, 100))
  }
  throw new Error(`Servidor não ficou saudável. Logs:\n${logs}`)
}

async function post (path, body, token = null, expected = 200, extraHeaders = {}) {
  const headers = {
    'content-type': 'application/json',
    'x-ubu-apiversion': '24.0.0',
    ...extraHeaders
  }
  if (token) headers['x-ubu-token'] = token
  const response = await fetch(`${base}${path}`, { method: 'POST', headers, body: JSON.stringify(body ?? {}) })
  const data = await response.json()
  assert.equal(response.status, expected, `${path}: ${JSON.stringify(data)}`)
  return data
}

try {
  const health = await waitForHealth()
  assert.equal(health.game_data_loaded, true)
  assert.equal(health.packs, 2)
  assert.equal(health.events, 1)

  const registration = await post('/game/auth/register', { client_version: '1.13.1', device_id: 'smoke-device' })
  assert.equal(registration.code, 1000)
  assert.equal(registration.device_id, 'smoke-device')
  const userId = registration.user_id
  const password = registration.password
  const token = registration.token

  const login = await post('/game/auth/login-device', { client_version: '1.13.1', user_id: userId, password })
  assert.equal(login.token, token)

  // O APK real chama a API com o path completo da base Gear:
  // https://<host>/collections/doom/game/...
  const gearLogin = await post('/collections/doom/game/auth/login-device', { client_version: '1.13.1', user_id: userId, password })
  assert.equal(gearLogin.token, token)

  const userData = await post('/game/player/user-data', {}, token)
  const inventory = userData.user_data.inventory
  assert.deepEqual(inventory.currencies, [{ rid: 100, amount: 2000 }])
  assert.equal(inventory.weapons[0].rid, 200)
  assert.equal(inventory.slayers[0].rid, 300)
  assert.equal(inventory.energies[0].amount, 10)
  assert.deepEqual(inventory.slots.map(row => row.id).sort((a, b) => a - b), [10, 11])
  assert.deepEqual(userData.user_data.talent_progression.talents, [])

  const dataToken = await post('/game/player/game-data-token', {}, token)
  const dataResponse = await fetch(dataToken.url, { headers: { authorization: `Bearer ${dataToken.token}` } })
  assert.equal(dataResponse.status, 200)
  assert.equal((await dataResponse.json()).bundles[0].tag, 'starter')

  const dailyBefore = await post('/game/daily-rewards/get-state', {}, token)
  assert.equal(dailyBefore.state.claimable ?? true, true)
  await post('/game/daily-rewards/claim', {}, token)
  const dailyDuplicate = await post('/game/daily-rewards/claim', {}, token, 400)
  assert.equal(dailyDuplicate.reason, 'already-claimed')
  const afterDaily = await post('/game/player/user-data', {}, token)
  assert.equal(afterDaily.user_data.inventory.currencies[0].amount, 2025)

  const talentBuy = await post('/game/talents/buy', { talent: 500 }, token)
  assert.equal(talentBuy.talent, 500)
  // TalentsApi só tem Buy no cliente 1.13.1; a leitura é o talent_progression
  // do user-data (a rota talents/get legada foi removida do servidor).
  const afterTalent = await post('/game/player/user-data', {}, token)
  assert.deepEqual(afterTalent.user_data.talent_progression.talents, [500])
  assert.equal(afterTalent.user_data.inventory.currencies[0].amount, 1975)

  const store = await post('/game/store/get', {}, token)
  assert.equal(store.store_items[0].id, 900100)
  await post('/game/store/purchase', { item: 900100 }, token)
  await post('/game/store/purchase', { item: 900100 }, token)
  const quota = await post('/game/store/purchase', { item: 900100 }, token, 400)
  assert.equal(quota.reason, 'quota')

  const afterPurchases = await post('/game/player/user-data', {}, token)
  assert.equal(afterPurchases.user_data.inventory.currencies[0].amount, 975)
  assert.deepEqual(afterPurchases.user_data.talent_progression.talents, [500])

  // IdleRewardApi.Boost(): multiplica os períodos pendentes (período de 1s no
  // game-data do smoke) e responde envelope puro — o cliente relê get-state.
  // O número exato de períodos acumulados varia com o timing da máquina; o
  // que é determinístico: >=1 período concedido ×2 e estado zerado após.
  await post('/game/idle-rewards/get-state', {}, token)
  await new Promise(wait => setTimeout(wait, 1200))
  await post('/game/idle-rewards/boost', {}, token)
  const afterBoost = await post('/game/player/user-data', {}, token)
  const boostBalance = afterBoost.user_data.inventory.currencies.find(row => row.rid === 100).amount
  assert.ok(boostBalance >= 977 && boostBalance <= 981, `boost concede períodos ×2 (saldo ${boostBalance})`)
  const idleAfterBoost = await post('/game/idle-rewards/get-state', {}, token)
  assert.equal(idleAfterBoost.state.claimable_periods, 0, 'boost consome os períodos pendentes')

  // InventoryApi.ExchangeCurrency(): taxa configurada input 100 -> output 101
  // (rate 10 = 10 moedas por 1 gema). Saída via giveGameResource.
  await post('/game/inventory/exchange-currency', {
    input_currency_id: 100, output_currency_id: 101, output_currency_amount: 3
  }, token)
  const afterExchange = await post('/game/player/user-data', {}, token)
  assert.equal(afterExchange.user_data.inventory.currencies.find(row => row.rid === 100).amount, boostBalance - 30, 'exchange debita ceil(3 × rate 10)')
  assert.equal(afterExchange.user_data.inventory.currencies.find(row => row.rid === 101).amount, 3)
  const exchangeMissing = await post('/game/inventory/exchange-currency', { input_currency_id: 100 }, token, 400)
  assert.equal(exchangeMissing.reason, 'currency-required')

  // SessionApi.UpdateLegal()/PlayerApi.SetPushToken(): envelope puro, estado
  // persistido em namespaces próprios.
  await post('/game/session/update-legal', { tos_version: 1, allow_personalization: true }, token)
  const pushMissing = await post('/game/player/set-push-token', {}, token, 400)
  assert.equal(pushMissing.reason, 'push-token-required')
  await post('/game/player/set-push-token', { push_token: 'smoke-push' }, token)

  // ArmoryApi.Get()/Upgrade(id, level): estado {id, level}, custo debitado.
  const armoryBefore = await post('/game/armory/get', {}, token)
  assert.deepEqual(armoryBefore.upgrades, [{ id: 1, level: 0 }])
  await post('/game/armory/upgrade', { id: 1, level: 1 }, token)
  const armoryAfter = await post('/game/armory/get', {}, token)
  assert.deepEqual(armoryAfter.upgrades, [{ id: 1, level: 1 }])
  const afterArmory = await post('/game/player/user-data', {}, token)
  assert.equal(afterArmory.user_data.inventory.currencies.find(row => row.rid === 100).amount, boostBalance - 55, 'armory debita o custo do nível 1')

  // StoreApi.GetItems()/GetOfferItems()/ActivateOffer()/GetPlayerOffers()/
  // AdPurchaseItem(): packs de anúncio separados em ad_items; ad-purchase sem
  // token (emissor game/ads/* fora de escopo) é erro explícito.
  const items = await post('/game/store/get-items', {}, token)
  assert.deepEqual(items.store_items.map(item => item.id), [900100])
  assert.deepEqual(items.ad_items.map(item => item.id), [900200])
  assert.deepEqual(items.iap_items, [], 'IAP desligado por design no Revival')
  const offerItems = await post('/game/store/get-offer-items', {}, token)
  assert.deepEqual(offerItems.ad_items.map(item => item.id), [900200])
  const activatedOffer = await post('/game/store/activate-offer', { offer_id: 5 }, token)
  assert.equal(activatedOffer.offer.item_id, 900100)
  assert.equal(typeof activatedOffer.offer.start_time, 'number')
  const playerOffers = await post('/game/store/get-player-offers', {}, token)
  assert.deepEqual(playerOffers.offers.map(offer => offer.id), [5])
  const adNoToken = await post('/game/store/ad-purchase', { item_id: 900200 }, token, 400)
  assert.equal(adNoToken.reason, 'reward-token-required')

  // DevicesApi: AuthorizedDevice{id, platform, region, authorization_time,
  // last_access_time} no wire; unregister responde envelope puro.
  const device = await post('/game/devices/register', { platform: 'android', region: 'US' }, token)
  assert.equal(device.device.id, 1)
  assert.equal(device.device.platform, 'android')
  const deviceList = await post('/game/devices/list', {}, token)
  assert.equal(deviceList.devices.length, 1)
  await post('/game/devices/describe', { device_id: 1 }, token)
  await post('/game/devices/unregister', { device_id: 1 }, token)
  const deviceGone = await post('/game/devices/list', {}, token)
  assert.deepEqual(deviceGone.devices, [])

  // CodesApi.Redeem(code): concessão única por jogador. O wire de resources
  // reporta o saldo pós-concessão (semântica do giveGameResource), não o delta.
  const redeemed = await post('/game/codes/redeem', { code: 'REVIVAL' }, token)
  assert.deepEqual(redeemed.resources, [{ rid: 100, amount: boostBalance - 55 + 150 }])
  const redeemedAgain = await post('/game/codes/redeem', { code: 'REVIVAL' }, token, 400)
  assert.equal(redeemedAgain.reason, 'code-already-redeemed')

  // Rotas platform-gated: código REAL de indisponibilidade do ResponseCode
  // (extraído do metadata: XboxUnavailable=3127, BnetUnavailable=3101,
  // GooglePlayGamesUnavailable=3111, GameCenterUnavailable=3121) e gates
  // verdadeiros nos fluxos de conflito/unlink — nunca payload falso.
  const loginXbox = await post('/game/auth/login-xbox', { client_version: '1.13.1' }, null, 400)
  assert.equal(loginXbox.code, 3127)
  assert.equal(loginXbox.reason, 'xbox-unavailable')
  const loginGpg = await post('/game/auth/login-google-play-games', {}, null, 400)
  assert.equal(loginGpg.code, 3111)
  const gamertag = await post('/game/xbox/get-gamertag', {}, token, 400)
  assert.equal(gamertag.code, 3127)
  const slayersClub = await post('/game/bnet/claim-slayers-club', {}, token, 400)
  assert.equal(slayersClub.code, 3101)
  const conflictMissing = await post('/game/identity/describe-conflict', {}, token, 400)
  assert.equal(conflictMissing.code, 2200)
  const conflictUnknown = await post('/game/identity/describe-conflict', { link_token: 'x' }, token, 400)
  assert.equal(conflictUnknown.code, 2340)
  const unlinkUnknown = await post('/game/identity/unlink', { identity_id: 1 }, token, 400)
  assert.equal(unlinkUnknown.code, 2340)

  const schedule = await post('/game/events/get-schedule', {}, token)
  assert.equal(schedule.scheduled_events[0].id, 7001)
  // Contrato do cliente 1.13.1: o DTO do schedule (cluster do global-metadata)
  // é id, event_definition_id, start_time, end_time, availability,
  // min_api_version, max_api_version, stop_time, args. Campos numéricos
  // não-nullable enviados como null explícito derrubam o parse do cliente
  // ("Malformed response payload" após get-schedule, boot aborta após 3
  // tentativas), então valores ausentes são omitidos e "event_type" (que não
  // existe no DTO) nunca é enviado.
  for (const event of schedule.scheduled_events) {
    assert.equal(event.event_type, undefined, 'event_type não faz parte do DTO do cliente')
    for (const field of ['min_api_version', 'max_api_version', 'stop_time']) {
      assert.notEqual(event[field], null, `${field} não pode ir como null para o cliente 1.13.1`)
    }
  }
  const eventState = await post('/game/events/get-progress', {}, token)
  assert.equal(eventState.game_mode_events_progress[0].event_id, 7001)

  // Contrato do ChapterModeApi (metadata v29): StartChapterResponse{attempt},
  // UpdateChapterResponse{min_update_time}, Revive/RedeemVoucher sem DTO
  // (envelope puro), EndChapterResponse{loot}, ClaimStageReward{stage,
  // resources}, ClaimChallengeReward{resources}.
  const attempt = await post('/game/chapters/start', { chapter_id: 101, challenge_id: 1 }, token)
  assert.equal(attempt.attempt.chapter_id, 101)
  assert.equal(attempt.current_run, undefined, 'StartChapterResponse só tem attempt')
  const updated = await post('/game/chapters/update', { progress: { stage: 3, state: 0 } }, token)
  assert.ok('min_update_time' in updated, 'UpdateChapterResponse tem min_update_time')
  const revived = await post('/game/chapters/revive', {}, token)
  assert.equal(revived.current_run, undefined, 'Revive responde envelope puro')
  const ended = await post('/game/chapters/end', { progress: { stage: 5, state: 1 } }, token)
  assert.deepEqual(ended.loot, [])
  assert.equal(ended.chapter_progression, undefined, 'EndChapterResponse só tem loot')
  const stageReward = await post('/game/chapters/claim-stage-reward', { chapter_id: 101 }, token)
  assert.equal(stageReward.stage, 1)
  assert.equal(stageReward.resources[0].rid, 100)
  const challengeReward = await post('/game/chapters/claim-challenge-reward', { chapter_id: 101, challenge_id: 1 }, token)
  assert.equal(challengeReward.resources.length, 1)

  const persisted = await post('/game/player/user-data', {}, token)
  assert.equal(persisted.user_data.chapter_progression.chapters[0].chapter, 101)
  assert.deepEqual(persisted.user_data.talent_progression.talents, [500])

  const dailyAfter = await post('/game/daily-rewards/get-state', {}, token)
  assert.equal(dailyAfter.state.claimable ?? false, false)
  await post('/game/idle-rewards/get-state', {}, token)
  await post('/game/session/heartbeat', {}, token)

  const iap = await post('/game/iap/purchase', {}, token, 400)
  assert.equal(iap.iap_disabled, true)

  await post('/game/future/unknown-endpoint', { probe: 1 }, token)

  // Gate de convergência: o contador de fallbacks do RESEARCH_MODE precisa
  // registrar exatamente o endpoint desconhecido chamado acima — e NENHUMA
  // rota do fluxo já implementado pode aparecer como fallback. Se uma rota
  // conhecida cair aqui, ela respondeu ok() vazio em vez do contrato real.
  const research = await fetch(`${base}/revival/research`)
  assert.equal(research.status, 200)
  const researchState = await research.json()
  assert.equal(researchState.research_mode, true)
  const probed = researchState.fallback_endpoints.find(row => row.path === '/game/future/unknown-endpoint')
  assert.ok(probed, 'fallback do endpoint desconhecido deve ser contado')
  assert.equal(probed.count, 1)
  const implementedPaths = new Set([
    '/game/auth/register', '/game/auth/login-device', '/game/player/user-data',
    '/game/player/game-data-token', '/game/daily-rewards/get-state', '/game/daily-rewards/claim',
    '/game/talents/buy', '/game/store/get', '/game/store/purchase',
    '/game/events/get-schedule', '/game/events/get-progress', '/game/chapters/start',
    '/game/chapters/update', '/game/chapters/revive', '/game/chapters/end',
    '/game/idle-rewards/get-state', '/game/session/heartbeat',
    '/game/idle-rewards/boost', '/game/inventory/exchange-currency',
    '/game/session/update-legal', '/game/player/set-push-token',
    '/game/armory/get', '/game/armory/upgrade',
    '/game/store/get-items', '/game/store/get-offer-items',
    '/game/store/get-player-offers', '/game/store/activate-offer', '/game/store/ad-purchase',
    '/game/devices/register', '/game/devices/list', '/game/devices/describe',
    '/game/devices/unregister', '/game/codes/redeem',
    '/game/auth/login-xbox', '/game/auth/login-google-play-games',
    '/game/xbox/get-gamertag', '/game/bnet/claim-slayers-club',
    '/game/identity/describe-conflict', '/game/identity/unlink'
  ])
  const leaked = researchState.fallback_endpoints.filter(row => implementedPaths.has(row.path))
  assert.deepEqual(leaked, [], 'rota implementada não pode depender de fallback de pesquisa')

  const requests = await fetch(`${base}/revival/requests?limit=20`, {
    headers: { authorization: 'Bearer smoke-admin' }
  })
  assert.equal(requests.status, 200)
  const requestLog = await requests.json()
  assert.ok(requestLog.requests.some(row => row.path === '/game/future/unknown-endpoint'))

  const wrongApi = await post('/game/auth/register', { client_version: '1.13.1' }, null, 403, { 'x-ubu-apiversion': 'wrong' })
  assert.equal(wrongApi.code, 2200)

  console.log('Mighty DOOM Revival smoke test: PASS')
} finally {
  child.kill('SIGTERM')
  await new Promise(resolveExit => child.once('exit', resolveExit))
  rmSync(work, { recursive: true, force: true })
}
