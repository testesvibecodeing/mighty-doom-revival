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
  resources: [{ id: 100, tag: 'coins', category_id: 1 }],
  weapons: [{ id: 200, tag: 'heavy_cannon', category_id: 2 }],
  slayers: [{ id: 300, tag: 'mini_slayer', category_id: 7 }],
  energies: [{ id: 400, tag: 'energy', category_id: 5, max_amount: 20, regen_minutes: 1 }],
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
  idle_reward: { generation_period: 60, chapter_idle_generation: [{ chapter_progress: 0, idle_generation: [{ rid: 100, amount: 1 }] }] }
}

const packs = {
  packs: [{
    id: 900100,
    tag: 'revival_weapon_pack',
    active: true,
    cost: [{ resource: 'coins', kind: 'currency', amount: 500 }],
    contents: [{ resource: 'heavy_cannon', kind: 'weapon', level: 2, tier: 1 }],
    quota: { period: 'daily', max: 2 }
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
  assert.equal(health.packs, 1)
  assert.equal(health.events, 1)

  const registration = await post('/game/auth/register', { client_version: '1.13.1', device_id: 'smoke-device' })
  assert.equal(registration.code, 1000)
  assert.equal(registration.device_id, 'smoke-device')
  const userId = registration.user_id
  const password = registration.password
  const token = registration.token

  const login = await post('/game/auth/login-device', { client_version: '1.13.1', user_id: userId, password })
  assert.equal(login.token, token)

  const userData = await post('/game/player/user-data', {}, token)
  const inventory = userData.user_data.inventory
  assert.deepEqual(inventory.currencies, [{ rid: 100, amount: 2000 }])
  assert.equal(inventory.weapons[0].rid, 200)
  assert.equal(inventory.slayers[0].rid, 300)
  assert.equal(inventory.energies[0].amount, 10)
  assert.deepEqual(inventory.slots.map(row => row.id).sort((a, b) => a - b), [10, 11])

  const dataToken = await post('/game/player/game-data-token', {}, token)
  const dataResponse = await fetch(dataToken.url, { headers: { authorization: `Bearer ${dataToken.token}` } })
  assert.equal(dataResponse.status, 200)
  assert.equal((await dataResponse.json()).bundles[0].tag, 'starter')

  const dailyBefore = await post('/game/daily-rewards/get-state', {}, token)
  assert.equal(dailyBefore.state.claimable, true)
  await post('/game/daily-rewards/claim', {}, token)
  const dailyDuplicate = await post('/game/daily-rewards/claim', {}, token, 400)
  assert.equal(dailyDuplicate.reason, 'already-claimed')
  const afterDaily = await post('/game/player/user-data', {}, token)
  assert.equal(afterDaily.user_data.inventory.currencies[0].amount, 2025)

  const store = await post('/game/store/get', {}, token)
  assert.equal(store.store_items[0].id, 900100)
  await post('/game/store/purchase', { item: 900100 }, token)
  await post('/game/store/purchase', { item: 900100 }, token)
  const quota = await post('/game/store/purchase', { item: 900100 }, token, 400)
  assert.equal(quota.reason, 'quota')

  const afterPurchases = await post('/game/player/user-data', {}, token)
  assert.equal(afterPurchases.user_data.inventory.currencies[0].amount, 1025)

  const schedule = await post('/game/events/get-schedule', {}, token)
  assert.equal(schedule.scheduled_events[0].id, 7001)
  const eventState = await post('/game/events/get-progress', {}, token)
  assert.equal(eventState.game_mode_events_progress[0].event_id, 7001)

  await post('/game/chapters/start', { chapter: 101, stage: 0 }, token)
  await post('/game/chapters/update', { stage: 3, checkpoint: 'c3' }, token)
  const revived = await post('/game/chapters/revive', {}, token)
  assert.equal(revived.current_run.revives, 1)
  const ended = await post('/game/chapters/end', { stage: 5, success: true }, token)
  assert.equal(ended.chapter_progression.chapters[0].best_stage, 5)

  const persisted = await post('/game/player/user-data', {}, token)
  assert.equal(persisted.user_data.chapter_progression.chapters[0].chapter, 101)

  const dailyAfter = await post('/game/daily-rewards/get-state', {}, token)
  assert.equal(dailyAfter.state.claimable, false)
  await post('/game/idle-rewards/get-state', {}, token)
  await post('/game/session/heartbeat', {}, token)

  const iap = await post('/game/iap/purchase', {}, token, 400)
  assert.equal(iap.iap_disabled, true)

  await post('/game/future/unknown-endpoint', { probe: 1 }, token)
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
