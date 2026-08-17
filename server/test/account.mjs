import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const work = mkdtempSync(resolve(tmpdir(), 'mighty-doom-account-'))
mkdirSync(resolve(work, 'config'), { recursive: true })
writeFileSync(resolve(work, 'config/revival.json'), JSON.stringify({ client_version: '1.13.1', api_version: '24.0.0', game_data_token: 'test' }))
writeFileSync(resolve(work, 'config/packs.json'), '{"packs":[]}')
writeFileSync(resolve(work, 'config/events.json'), '{"events":[]}')

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
const child = spawn(process.execPath, ['src/index.js'], {
  cwd: root,
  env: { ...process.env, HOST: '127.0.0.1', PORT: String(port), DB_PATH: resolve(work, 'runtime/db.sqlite3'), REVIVAL_CONFIG_PATH: resolve(work, 'config/revival.json'), PACKS_CONFIG_PATH: resolve(work, 'config/packs.json'), EVENTS_CONFIG_PATH: resolve(work, 'config/events.json'), RESEARCH_MODE: 'true' },
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
  const response = await fetch(`${base}${path}`, { ...options, headers: { 'content-type': 'application/json', ...(options.headers || {}) } })
  const body = await response.json()
  assert.equal(response.status, expected, JSON.stringify(body))
  return { body, response }
}

try {
  await waitForServer()
  const created = await request('/account/register', { method: 'POST', body: JSON.stringify({ display_name: 'Test Slayer', email: 'test@example.com', password: 'password-123' }) }, 201)
  const cookie = created.response.headers.get('set-cookie').split(';')[0]
  assert.match(created.body.recovery_code, /^RV-/)
  assert.equal(created.body.account.email, 'test@example.com')
  const me = await request('/account/me', { headers: { cookie } })
  assert.equal(me.body.account.display_name, 'Test Slayer')
  assert.equal(me.body.snapshot.progression.level, 1)
  await request('/account/profile', { method: 'PATCH', headers: { cookie }, body: JSON.stringify({ display_name: 'Updated Slayer', email: 'updated@example.com' }) })
  await request('/account/password', { method: 'POST', headers: { cookie }, body: JSON.stringify({ current_password: 'password-123', new_password: 'password-456' }) })
  await request('/account/logout', { method: 'POST', headers: { cookie }, body: '{}' })
  await request('/account/login', { method: 'POST', body: JSON.stringify({ login: 'updated@example.com', password: 'password-456' }) })
  console.log('Mighty DOOM Revival account test: PASS')
} finally {
  child.kill('SIGTERM')
  await new Promise(resolveExit => child.once('exit', resolveExit))
  rmSync(work, { recursive: true, force: true })
}
