// Captura fixtures de protocolo request/response em tests/fixtures/protocol/.
//
// Sobe um servidor temporário (mesmo padrão do server/test/smoke.mjs), executa
// o fluxo de gameplay implementado por HTTP real e grava cada par
// request/response sanitizado, um arquivo por endpoint:
//
//   tests/fixtures/protocol/<modulo>/<rota com / -> __>.json
//
// provenance "server-replay": contrato observado contra o servidor Revival
// com o jogo dos dados sintéticos de teste. Quando o harness ADB
// (scripts/client_harness.py) capturar o MESMO par vindo do cliente real, ele
// reescreve o arquivo com provenance "client" — só então
// request_observed/response_observed viram true no compatibility.json.
//
// Uso: node scripts/capture_protocol_fixtures.mjs [--out tests/fixtures/protocol]
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const serverRoot = resolve(repoRoot, 'server')
const outDir = resolve(process.argv[2] || resolve(repoRoot, 'tests/fixtures/protocol'), 'server-replay')

const work = mkdtempSync(resolve(tmpdir(), 'mighty-doom-revival-fixtures-'))
mkdirSync(resolve(work, 'config'), { recursive: true })
mkdirSync(resolve(work, 'data'), { recursive: true })
mkdirSync(resolve(work, 'runtime'), { recursive: true })

// Mesmo dataset sintético do smoke.mjs: determinístico, sem material proprietário.
const revival = {
  server_name: 'Mighty DOOM Revival Fixtures',
  api_version: '24.0.0',
  client_version: '1.13.1',
  game_data_token: 'fixtures-game-data',
  game_data_version_id: 'fixtures-v1',
  auto_starter_bundle: true,
  initial_resources: []
}
const gameData = {
  server_properties: { starter_bundle: 1 },
  resources: [{ id: 100, tag: 'coins', category_id: 1 }],
  weapons: [{ id: 200, tag: 'heavy_cannon', category_id: 2, max_level: 3, upgrade_costs: [{ level: 2, cost: [{ resource: 'coins', amount: 100 }] }, { level: 3, cost: [{ resource: 'coins', amount: 100 }] }] }],
  slayers: [{ id: 300, tag: 'mini_slayer', category_id: 7, max_level: 5, upgrade_costs: [{ level: 2, cost: [{ resource: 'coins', amount: 50 }] }] }],
  cosmetics: [{ id: 800, tag: 'skin_revival', category_id: 9 }],
  energies: [{ id: 400, tag: 'energy', category_id: 5, max_amount: 20, regen_minutes: 1 }],
  talents: { talents: [{ id: 500, cost: [{ resource: 'coins', amount: 50 }] }] },
  gear_fusion: { input_count: 2, tier_gain: 1 },
  dismantle: { tiers: { 1: [{ resource: 'coins', amount: 25 }] } },
  chapter_mode: {
    chapters: [{
      id: 101,
      vip_entitlement_id: 700,
      stage_rewards: [
        { stage: 1, resources: [{ rid: 100, amount: 10 }], vip_resources: [{ rid: 100, amount: 20 }] },
        { stage: 2, resources: [{ rid: 100, amount: 15 }], vip_resources: [{ rid: 100, amount: 25 }] },
        { stage: 3, resources: [{ rid: 100, amount: 20 }], vip_resources: [{ rid: 100, amount: 30 }] },
        { stage: 4, vip_resources: [{ rid: 100, amount: 35 }] }
      ],
      challenges: [{ id: 1, completion_reward: [{ rid: 100, amount: 100 }] }]
    }, {
      id: 102,
      vip_entitlement_id: 700,
      stage_rewards: [
        { stage: 1, vip_resources: [{ rid: 100, amount: 12 }] },
        { stage: 2, vip_resources: [{ rid: 100, amount: 14 }] },
        { stage: 3, vip_resources: [{ rid: 100, amount: 16 }] }
      ]
    }]
  },
  messages: [
    { id: 1, title: 'Welcome to the Revival', body: 'Good hunting, slayer.', resources: [{ rid: 100, amount: 50 }] },
    { id: 2, title: 'Server notice', body: 'Research mode counts unknown endpoints.' }
  ],
  reward_tracks: {
    tracks: [{ id: 600, progress: 1, tiers: [{ id: 601, target: 1, resources: [{ rid: 100, amount: 30 }] }] }]
  },
  bundles: [{
    id: 1,
    tag: 'starter',
    resources: [
      { resource: { id: 100 }, kind: 'currency', amount: 2000 },
      { resource: { id: 200 }, kind: 'weapon', level: 1, tier: 1 },
      { resource: { id: 200 }, kind: 'weapon', level: 1, tier: 1 },
      { resource: { id: 200 }, kind: 'weapon', level: 1, tier: 1 },
      { resource: { id: 300 }, kind: 'slayer', level: 1, tier: 1 },
      { resource: { id: 700 }, kind: 'entitlement' },
      { resource: { id: 800 }, kind: 'cosmetic' },
      { resource: { id: 900 }, kind: 'equipment' },
      { resource: { id: 400 }, kind: 'energy', amount: 10 }
    ]
  }],
  inventory: { slots: [{ id: 10, tag: 'slot_primary_weapon' }, { id: 11, tag: 'slot_slayer' }] },
  daily_rewards: { days: [{ resources: [{ resource: 'coins', amount: 25 }] }] },
  idle_reward: { generation_period: 60, chapter_idle_generation: [{ chapter_progress: 0, idle_generation: [{ rid: 100, amount: 1 }] }] }
}
const packs = { packs: [] }
const events = { events: [] }

const writeJson = (path, value) => writeFileSync(path, JSON.stringify(value, null, 2))
writeJson(resolve(work, 'config/revival.json'), revival)
writeJson(resolve(work, 'config/packs.json'), packs)
writeJson(resolve(work, 'config/events.json'), events)
writeJson(resolve(work, 'data/game-data.json'), gameData)

async function freePort () {
  return await new Promise((resolvePort, reject) => {
    const socket = createServer()
    socket.once('error', reject)
    socket.listen(0, '127.0.0.1', () => {
      const port = socket.address().port
      socket.close(error => error ? reject(error) : resolvePort(port))
    })
  })
}

const port = await freePort()
const base = `http://127.0.0.1:${port}`
const child = spawn(process.execPath, ['src/index.js'], {
  cwd: serverRoot,
  env: {
    ...process.env,
    HOST: '127.0.0.1',
    PORT: String(port),
    DB_PATH: resolve(work, 'runtime/revival.sqlite3'),
    GAME_DATA_PATH: resolve(work, 'data/game-data.json'),
    REVIVAL_CONFIG_PATH: resolve(work, 'config/revival.json'),
    PACKS_CONFIG_PATH: resolve(work, 'config/packs.json'),
    EVENTS_CONFIG_PATH: resolve(work, 'config/events.json'),
    RESEARCH_MODE: 'true'
  },
  stdio: ['ignore', 'pipe', 'pipe']
})
let logs = ''
child.stdout.on('data', chunk => { logs += chunk.toString() })
child.stderr.on('data', chunk => { logs += chunk.toString() })

async function waitForHealth () {
  for (let i = 0; i < 50; i++) {
    try {
      const response = await fetch(`${base}/revival/health`)
      if (response.ok) return
    } catch {}
    await new Promise(wait => setTimeout(wait, 100))
  }
  throw new Error(`Servidor não ficou saudável. Logs:\n${logs}`)
}

const captured = []

async function call (label, path, body, token = null) {
  const headers = { 'content-type': 'application/json', 'x-ubu-apiversion': '24.0.0' }
  if (token) headers['x-ubu-token'] = token
  const response = await fetch(`${base}${path}`, { method: 'POST', headers, body: JSON.stringify(body ?? {}) })
  const data = await response.json()
  if (response.status !== 200) throw new Error(`${path} -> ${response.status}: ${JSON.stringify(data)}`)
  captured.push({ label, path, body, status: response.status, data })
  return data
}

function sanitize (value) {
  if (Array.isArray(value)) return value.map(sanitize)
  if (value && typeof value === 'object') {
    const out = {}
    for (const [key, inner] of Object.entries(value)) {
      if (key === 'uts') out[key] = '<uts>'
      else if (key === 'token') out[key] = '<token>'
      else if (key === 'password') out[key] = '<password>'
      else if (key === 'recovery_code') out[key] = '<recovery-code>'
      else if (key === 'url') out[key] = String(inner).replace(/^https?:\/\/[^/]+/, '<base>')
      else if (key === 'account_age' || key === 'last_login') out[key] = 0
      else out[key] = sanitize(inner)
    }
    return out
  }
  return value
}

try {
  await waitForHealth()

  // Fluxo na ordem em que o cliente 1.13.1 chama (bootstrap do RELATORIO-STATUS).
  const registration = await call('register', '/game/auth/register', { client_version: '1.13.1', device_id: 'fixtures-device' })
  const token = registration.token
  await call('login-device', '/game/auth/login-device', { client_version: '1.13.1', user_id: registration.user_id, password: registration.password })
  await call('game-data-token', '/game/player/game-data-token', {}, token)
  const userData = await call('user-data', '/game/player/user-data', {}, token)
  await call('armory-get', '/game/armory/get', {}, token)
  await call('events-get-schedule', '/game/events/get-schedule', {}, token)
  await call('events-get-progress', '/game/events/get-progress', {}, token)
  await call('session-refresh', '/game/session/refresh', {}, token)
  await call('session-heartbeat', '/game/session/heartbeat', {}, token)
  await call('identity-list', '/game/identity/list', {}, token)
  await call('inbox-get-messages', '/game/inbox/get-messages', {}, token)
  await call('reward-tracks-get-all', '/game/reward-tracks/get-all', {}, token)
  await call('quests-get-daily-quests', '/game/quests/get-daily-quests', {}, token)
  await call('idle-rewards-get-state', '/game/idle-rewards/get-state', {}, token)
  await call('daily-rewards-get-state', '/game/daily-rewards/get-state', {}, token)
  await call('daily-rewards-claim', '/game/daily-rewards/claim', {}, token)
  await call('inventory-get-equip-sequence-id', '/game/inventory/get-equip-sequence-id', {}, token)
  await call('talents-buy', '/game/talents/buy', { talent_id: 500 }, token)

  // Módulo gear/slayers — contrato extraído do metadata v29:
  // Upgrade(gearUid) / MultiUpgrade(gearUid, levelsToUpgrade) / Fuse(inputUids)
  // / Dismantle(gearUid) / ApplyCosmetic(gearUid|slayerUid, cosmeticId).
  const weapons = userData.user_data.inventory.weapons
  const slayers = userData.user_data.inventory.slayers
  const keep = weapons[0].uid
  const fuseA = weapons[1].uid
  const fuseB = weapons[2].uid
  await call('gear-upgrade', '/game/gear/upgrade', { gear_uid: keep }, token)
  await call('gear-multi-upgrade', '/game/gear/multi-upgrade', { gear_uid: keep, levels_to_upgrade: 1 }, token)
  await call('slayers-upgrade', '/game/slayers/upgrade', { slayer_uid: slayers[0].uid }, token)
  await call('gear-apply-cosmetic', '/game/gear/apply-cosmetic', { gear_uid: keep, cosmetic_id: 800 }, token)
  await call('slayers-apply-cosmetic', '/game/slayers/apply-cosmetic', { slayer_uid: slayers[0].uid, cosmetic_id: 800 }, token)
  await call('gear-fuse', '/game/gear/fuse', { input_uids: [fuseA, fuseB] }, token)
  await call('gear-dismantle', '/game/gear/dismantle', { gear_uid: keep }, token)

  // Módulo chapters — ChapterModeApi (metadata v29): 13 métodos = 13 rotas.
  // VIP em estágios distintos para capturar as três rotas VIP sem esgotar:
  // claim-vip-reward(1) → claim-vip-rewards-chapter(2,3) → all(4).
  await call('chapters-start', '/game/chapters/start', { chapter_id: 101, challenge_id: 1, gear: [], weapons: [] }, token)
  await call('chapters-update', '/game/chapters/update', { progress: { stage: 3, state: 0 } }, token)
  await call('chapters-revive', '/game/chapters/revive', {}, token)
  await call('chapters-redeem-voucher', '/game/chapters/redeem-voucher', { voucher_id: 900 }, token)
  await call('chapters-end', '/game/chapters/end', { progress: { stage: 5, state: 1 } }, token)
  await call('chapters-claim-stage-reward', '/game/chapters/claim-stage-reward', { chapter_id: 101 }, token)
  await call('chapters-claim-rewards', '/game/chapters/claim-rewards', { chapter_id: 101 }, token)
  await call('chapters-claim-vip-reward', '/game/chapters/claim-vip-reward', { chapter_id: 101 }, token)
  await call('chapters-claim-vip-rewards-chapter', '/game/chapters/claim-vip-rewards-chapter', { chapter_id: 101 }, token)
  // Segunda run (capítulo 102) deixa pendentes VIP para a rota "all", que
  // varre todos os capítulos — sem isso ela responderia 2300 vazia.
  await call('chapters-start-102', '/game/chapters/start', { chapter_id: 102, gear: [], weapons: [] }, token)
  await call('chapters-end-102', '/game/chapters/end', { progress: { stage: 3, state: 1 } }, token)
  await call('chapters-claim-vip-reward-102', '/game/chapters/claim-vip-reward', { chapter_id: 102 }, token)
  await call('chapters-claim-vip-rewards-all', '/game/chapters/claim-vip-rewards-all', {}, token)
  await call('chapters-claim-challenge-reward', '/game/chapters/claim-challenge-reward', { chapter_id: 101, challenge_id: 1 }, token)
  // Inbox/reward-tracks — InboxApi/RewardTracksApi (metadata v29).
  await call('inbox-read', '/game/inbox/read', { message_id: 2 }, token)
  await call('inbox-claim', '/game/inbox/claim', { message_id: 1 }, token)
  await call('inbox-delete', '/game/inbox/delete', { message_id: 2 }, token)
  await call('reward-tracks-get-track', '/game/reward-tracks/get-track', { track_id: 600 }, token)
  await call('reward-tracks-claim', '/game/reward-tracks/claim', { track_id: 600, tier_id: 601 }, token)
  await call('store-get', '/game/store/get', {}, token)
  await call('player-stats', '/game/player/stats', {}, token)
} finally {
  child.kill('SIGTERM')
  await new Promise(exit => child.once('exit', exit))
  rmSync(work, { recursive: true, force: true })
}

mkdirSync(outDir, { recursive: true })
const seenRoutes = new Set()
for (const capture of captured) {
  const route = capture.path.replace(/^\//, '')
  if (seenRoutes.has(route)) continue // primeira chamada por rota é a canônica
  seenRoutes.add(route)
  const module = route.split('/')[1] || 'raiz'
  const file = resolve(outDir, module, `${route.replaceAll('/', '__')}.json`)
  mkdirSync(dirname(file), { recursive: true })
  const fixture = {
    endpoint: route,
    provenance: 'server-replay',
    captured_at: new Date().toISOString().replace(/:\d{2}\.\d{3}Z$/, ':00Z'),
    sanitized: true,
    note: 'Capturado contra o servidor Revival com dataset sintético; substitua por provenance=client via scripts/client_harness.py',
    request: {
      method: 'POST',
      path: capture.path,
      headers: { 'content-type': 'application/json', 'x-ubu-apiversion': '24.0.0', 'x-ubu-token': '<token>' },
      body: sanitize(capture.body)
    },
    response: { status: capture.status, body: sanitize(capture.data) }
  }
  writeFileSync(file, JSON.stringify(fixture, null, 2) + '\n')
  console.log(`[fixture] ${route}`)
}
console.log(`\n${seenRoutes.size} fixtures server-replay em ${outDir}`)
