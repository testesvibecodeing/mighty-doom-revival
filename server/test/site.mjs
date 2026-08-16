import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

// Testa o site estático (server/public) e o upload de APK por link
// temporário: token válido por 24h, expiração, cancelamento imediato,
// validação de assinatura ZIP, metadados públicos e download com Range.

const serverRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const work = mkdtempSync(resolve(tmpdir(), 'mighty-doom-revival-site-'))
const publicDir = resolve(work, 'public')
const uploadDir = resolve(work, 'runtime-uploads')
mkdirSync(resolve(publicDir, 'assets/js'), { recursive: true })
mkdirSync(resolve(work, 'config'), { recursive: true })
mkdirSync(uploadDir, { recursive: true })

writeFileSync(resolve(publicDir, 'index.html'),
  '<!doctype html><html lang="pt-BR"><title>Mighty DOOM Revival</title><canvas id="hell-canvas"></canvas></html>')
writeFileSync(resolve(publicDir, 'assets/js/config.js'), 'window.MD_CONFIG = { serverUrl: "" };')

writeFileSync(resolve(work, 'config/revival.json'), JSON.stringify({
  server_name: 'Mighty DOOM Revival Site Test',
  api_version: '24.0.0',
  client_version: '1.13.1',
  game_data_token: 'site-game-data',
  game_data_version_id: 'site-v1',
  auto_starter_bundle: false,
  initial_resources: []
}, null, 2))
writeFileSync(resolve(work, 'config/packs.json'), JSON.stringify({ packs: [] }, null, 2))
writeFileSync(resolve(work, 'config/events.json'), JSON.stringify({ events: [] }, null, 2))

const TOKEN = 'a'.repeat(64)
const tokenFile = resolve(uploadDir, 'upload-token.json')
const writeToken = (expiresAt) => {
  writeFileSync(tokenFile, JSON.stringify({ token: TOKEN, expires_at: expiresAt, created_at: Math.floor(Date.now() / 1000) - 5 }))
}

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
  REVIVAL_CONFIG_PATH: resolve(work, 'config/revival.json'),
  PACKS_CONFIG_PATH: resolve(work, 'config/packs.json'),
  EVENTS_CONFIG_PATH: resolve(work, 'config/events.json'),
  PUBLIC_DIR: publicDir,
  UPLOAD_DIR: uploadDir,
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

async function postRaw (path, body, headers = {}, expected = 200) {
  const response = await fetch(`${base}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/octet-stream', ...headers },
    body
  })
  const data = await response.json().catch(() => ({}))
  assert.equal(response.status, expected, `${path}: ${JSON.stringify(data)}`)
  return data
}

try {
  // --- site estático ---
  const health = await waitForHealth()
  assert.equal(health.ok, true)
  assert.equal(health.players, 0)
  assert.equal(Number.isFinite(health.uptime_seconds), true)

  const home = await fetch(`${base}/`)
  assert.equal(home.status, 200)
  assert.equal(home.headers.get('content-type'), 'text/html; charset=utf-8')
  const homeHtml = await home.text()
  assert.ok(homeHtml.includes('Mighty DOOM Revival'))
  assert.ok(homeHtml.includes('hell-canvas'))

  const asset = await fetch(`${base}/assets/js/config.js`)
  assert.equal(asset.status, 200)
  assert.equal(asset.headers.get('content-type'), 'text/javascript; charset=utf-8')
  assert.ok((await asset.text()).includes('MD_CONFIG'))

  // Path traversal codificado não pode escapar do root público.
  const traversal = await fetch(`${base}/assets/%2e%2e/%2e%2e/src/index.js`)
  assert.equal(traversal.status, 404)

  // --- APK antes de qualquer upload ---
  const before = await (await fetch(`${base}/revival/apk`)).json()
  assert.equal(before.available, false)
  assert.equal(before.url, '/download/mighty-doom-revival.apk')

  // --- sem token, nada é aceito ---
  assert.equal((await fetch(`${base}/upload/${'b'.repeat(64)}`)).status, 410)
  assert.equal((await fetch(`${base}/upload/short`)).status, 410)

  // --- link de upload válido ---
  writeToken(Math.floor(Date.now() / 1000) + 3600)
  const page = await fetch(`${base}/upload/${TOKEN}`)
  assert.equal(page.status, 200)
  const pageHtml = await page.text()
  assert.ok(pageHtml.includes('Enviar APK'))
  assert.ok(pageHtml.includes(TOKEN))

  // --- upload de algo que não é ZIP é rejeitado ---
  const rejected = await postRaw(`/upload/${TOKEN}`, Buffer.from('GARBAGE-NO-ZIP!!'), {}, 400)
  assert.ok(rejected.error.includes('APK'))

  // --- upload real (mágica ZIP + payload) ---
  const apkBytes = Buffer.concat([Buffer.from([0x50, 0x4b, 0x03, 0x04]), Buffer.alloc(2048, 7)])
  const expectedSha = createHash('sha256').update(apkBytes).digest('hex')
  const uploaded = await postRaw(`/upload/${TOKEN}`, apkBytes)
  assert.equal(uploaded.ok, true)
  assert.equal(uploaded.size, apkBytes.length)
  assert.equal(uploaded.sha256, expectedSha)
  assert.equal(uploaded.url, '/download/mighty-doom-revival.apk')

  const meta = await (await fetch(`${base}/revival/apk`)).json()
  assert.equal(meta.available, true)
  assert.equal(meta.size, apkBytes.length)
  assert.equal(meta.sha256, expectedSha)

  // --- download com e sem Range ---
  const full = await fetch(`${base}/download/mighty-doom-revival.apk`)
  assert.equal(full.status, 200)
  assert.equal(full.headers.get('content-type'), 'application/vnd.android.package-archive')
  assert.equal((await full.arrayBuffer()).byteLength, apkBytes.length)

  const partial = await fetch(`${base}/download/mighty-doom-revival.apk`, { headers: { range: 'bytes=0-3' } })
  assert.equal(partial.status, 206)
  assert.equal(partial.headers.get('content-range'), `bytes 0-3/${apkBytes.length}`)
  assert.equal(Buffer.from(await partial.arrayBuffer()).toString('latin1'), 'PK')

  // --- health reflete o APK publicado ---
  const healthAfter = await (await fetch(`${base}/revival/health`)).json()
  assert.equal(healthAfter.apk_available, true)

  // --- token expirado (mesmo correto) vira 410 ---
  writeToken(Math.floor(Date.now() / 1000) - 10)
  assert.equal((await fetch(`${base}/upload/${TOKEN}`)).status, 410)

  // --- cancelamento imediato mata o link, mas não o APK publicado ---
  writeToken(Math.floor(Date.now() / 1000) + 3600)
  const cancel = await fetch(`${base}/upload-cancel/${TOKEN}`)
  assert.equal(cancel.status, 200)
  assert.ok((await cancel.text()).includes('desativado'))
  assert.equal((await fetch(`${base}/upload/${TOKEN}`)).status, 410)
  await postRaw(`/upload/${TOKEN}`, apkBytes, {}, 410)
  const metaAfter = await (await fetch(`${base}/revival/apk`)).json()
  assert.equal(metaAfter.available, true)
  const stillDown = await fetch(`${base}/download/mighty-doom-revival.apk`)
  assert.equal(stillDown.status, 200)

  // --- cancelar de novo não vira erro ---
  assert.equal((await fetch(`${base}/upload-cancel/${TOKEN}`)).status, 200)

  // --- jogadores reais aparecem no health ---
  const register = await fetch(`${base}/game/auth/register`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-ubu-apiversion': '24.0.0' },
    body: JSON.stringify({ client_version: '1.13.1' })
  })
  assert.equal(register.status, 200)
  const healthFinal = await (await fetch(`${base}/revival/health`)).json()
  assert.equal(healthFinal.players, 1)

  console.log('Mighty DOOM Revival site/upload test: PASS')
} finally {
  child.kill('SIGTERM')
  await new Promise(resolveExit => child.once('exit', resolveExit))
  rmSync(work, { recursive: true, force: true })
}
