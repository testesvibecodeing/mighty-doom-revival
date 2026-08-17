import assert from 'node:assert/strict'
import { createHmac } from 'node:crypto'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:net'
import { DatabaseSync } from 'node:sqlite'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const work = mkdtempSync(resolve(tmpdir(), 'mighty-doom-session-jwt-'))
mkdirSync(resolve(work, 'config'), { recursive: true })
writeFileSync(resolve(work, 'config/revival.json'), JSON.stringify({ client_version: '1.13.1', api_version: '24.0.0', game_data_token: 'test' }))
writeFileSync(resolve(work, 'config/packs.json'), '{"packs":[]}')
writeFileSync(resolve(work, 'config/events.json'), '{"events":[]}')
writeFileSync(resolve(work, 'config/site.json'), '{}')

const SECRET = 'test-session-secret-jwt'

const freePort = () => new Promise((resolvePort, reject) => {
  const socket = createServer()
  socket.once('error', reject)
  socket.listen(0, '127.0.0.1', () => {
    const port = socket.address().port
    socket.close(error => error ? reject(error) : resolvePort(port))
  })
})

const port = await freePort()
const base = `http://127.0.0.1:${port}`
const dbPath = resolve(work, 'runtime/db.sqlite3')
const child = spawn(process.execPath, ['src/index.js'], {
  cwd: root,
  env: { ...process.env, HOST: '127.0.0.1', PORT: String(port), DB_PATH: dbPath, REVIVAL_CONFIG_PATH: resolve(work, 'config/revival.json'), PACKS_CONFIG_PATH: resolve(work, 'config/packs.json'), EVENTS_CONFIG_PATH: resolve(work, 'config/events.json'), SITE_CONFIG_PATH: resolve(work, 'config/site.json'), RESEARCH_MODE: 'true', REVIVAL_SESSION_SECRET: SECRET },
  stdio: ['ignore', 'pipe', 'pipe']
})
let logs = ''
child.stdout.on('data', chunk => { logs += chunk.toString() })
child.stderr.on('data', chunk => { logs += chunk.toString() })

async function waitForServer () {
  for (let attempt = 0; attempt < 50; attempt++) {
    try { if ((await fetch(`${base}/revival/health`)).ok) return } catch {}
    await new Promise(resolveWait => setTimeout(resolveWait, 100))
  }
  throw new Error(`server did not start: ${logs}`)
}

async function request (path, options = {}, expected = 200) {
  const response = await fetch(`${base}${path}`, { ...options, headers: { 'content-type': 'application/json', 'x-ubu-apiversion': '24.0.0', ...(options.headers || {}) } })
  const body = await response.json()
  assert.equal(response.status, expected, JSON.stringify(body))
  return { body, response }
}

const decodeSegment = segment => JSON.parse(Buffer.from(segment, 'base64url').toString('utf8'))

try {
  await waitForServer()

  // register devolve JWT bem formado com os claims que o cliente lê
  const registered = await request('/game/auth/register', { method: 'POST', body: JSON.stringify({ client_version: '1.13.1', device_id: 'device-jwt-test' }) })
  const token = registered.body.token
  const segments = token.split('.')
  assert.equal(segments.length, 3, 'token deve ter 3 segmentos')
  const header = decodeSegment(segments[0])
  assert.equal(header.alg, 'HS256')
  assert.equal(header.typ, 'JWT')
  const payload = decodeSegment(segments[1])
  assert.equal(payload.ubu_user_id, registered.body.user_id)
  assert.equal(payload.sub, String(registered.body.user_id))
  assert.equal(payload.ubu_session_id, 1)
  assert.equal(payload.session_id, 1)
  assert.equal(payload.iss, payload.issuer)
  assert.equal(payload.aud, payload.audience)
  assert.ok(Number.isInteger(payload.iat))
  assert.ok(payload.exp > Math.floor(Date.now() / 1000), 'exp deve estar no futuro')
  assert.ok(typeof payload.sessionNonce === 'string' && payload.sessionNonce.length > 0)

  // o JWT autentica as chamadas seguintes
  await request('/game/session/heartbeat', { method: 'POST', headers: { 'x-ubu-token': token }, body: '{}' })

  // refresh emite novo JWT válido
  const refreshed = await request('/game/session/refresh', { method: 'POST', headers: { 'x-ubu-token': token }, body: '{}' })
  assert.equal(refreshed.body.token.split('.').length, 3)
  assert.notEqual(refreshed.body.token, token)

  // login-device também devolve JWT do mesmo usuário
  const loggedIn = await request('/game/auth/login-device', { method: 'POST', body: JSON.stringify({ client_version: '1.13.1', user_id: registered.body.user_id, password: registered.body.password }) })
  assert.equal(decodeSegment(loggedIn.body.token.split('.')[1]).ubu_user_id, registered.body.user_id)

  // assinatura adulterada → 401
  await request('/game/session/heartbeat', { method: 'POST', headers: { 'x-ubu-token': `${segments[0]}.${segments[1]}.deadbeef` }, body: '{}' }, 401)

  // payload com payload forjado (outro user_id) → assinatura não bate → 401
  const forgedBody = Buffer.from(JSON.stringify({ ...payload, ubu_user_id: registered.body.user_id + 1, sub: String(registered.body.user_id + 1) }), 'utf8').toString('base64url')
  const forged = `${segments[0]}.${forgedBody}.${segments[2]}`
  await request('/game/session/heartbeat', { method: 'POST', headers: { 'x-ubu-token': forged }, body: '{}' }, 401)

  // token expirado assinado com o segredo certo → 401
  const now = Math.floor(Date.now() / 1000)
  const expiredHeader = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' }), 'utf8').toString('base64url')
  const expiredBody = Buffer.from(JSON.stringify({ ubu_user_id: registered.body.user_id, sub: String(registered.body.user_id), ubu_session_id: 1, expiresTimestamp: now - 10, exp: now - 10 }), 'utf8').toString('base64url')
  const expiredSig = createHmac('sha256', SECRET).update(`${expiredHeader}.${expiredBody}`).digest('base64url')
  await request('/game/session/heartbeat', { method: 'POST', headers: { 'x-ubu-token': `${expiredHeader}.${expiredBody}.${expiredSig}` }, body: '{}' }, 401)

  // token opaco legado (coluna users.token) continua autenticando
  const db = new DatabaseSync(dbPath, { readOnly: true })
  const legacy = db.prepare('SELECT token FROM users WHERE id = ?').get(registered.body.user_id)
  db.close()
  assert.ok(typeof legacy.token === 'string' && !legacy.token.includes('.'))
  await request('/game/session/heartbeat', { method: 'POST', headers: { 'x-ubu-token': legacy.token }, body: '{}' })

  console.log('Mighty DOOM Revival session JWT test: PASS')
} finally {
  child.kill('SIGTERM')
  await new Promise(resolveExit => {
    const timer = setTimeout(resolveExit, 3000)
    child.once('exit', () => { clearTimeout(timer); resolveExit() })
  })
  try { rmSync(work, { recursive: true, force: true }) } catch {}
}
