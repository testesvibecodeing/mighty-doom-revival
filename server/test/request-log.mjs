import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:net'
import { DatabaseSync } from 'node:sqlite'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

// Evidência de execução real: o request_log precisa (1) sobreviver à migração
// de um banco antigo, (2) conter register/login-device com request e response
// pareados na mesma linha, (3) expor captura incremental determinística em
// /revival/requests e (4) nunca persistir segredo em texto claro.

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const work = mkdtempSync(resolve(tmpdir(), 'mighty-doom-request-log-'))
mkdirSync(resolve(work, 'config'), { recursive: true })
writeFileSync(resolve(work, 'config/revival.json'), JSON.stringify({ client_version: '1.13.1', api_version: '24.0.0', game_data_token: 'test' }))
writeFileSync(resolve(work, 'config/packs.json'), '{"packs":[]}')
writeFileSync(resolve(work, 'config/events.json'), '{"events":[]}')
writeFileSync(resolve(work, 'config/site.json'), '{}')

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
const ADMIN = 'log-admin-token'
const child = spawn(process.execPath, ['src/index.js'], {
  cwd: root,
  env: { ...process.env, HOST: '127.0.0.1', PORT: String(port), DB_PATH: dbPath, REVIVAL_CONFIG_PATH: resolve(work, 'config/revival.json'), PACKS_CONFIG_PATH: resolve(work, 'config/packs.json'), EVENTS_CONFIG_PATH: resolve(work, 'config/events.json'), SITE_CONFIG_PATH: resolve(work, 'config/site.json'), RESEARCH_MODE: 'true', REVIVAL_ADMIN_TOKEN: ADMIN },
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

const gameHeaders = { 'content-type': 'application/json', 'x-ubu-apiversion': '24.0.0' }

async function game (path, body, headers = {}) {
  const response = await fetch(`${base}${path}`, { method: 'POST', headers: { ...gameHeaders, ...headers }, body: JSON.stringify(body || {}) })
  return { status: response.status, body: await response.json() }
}

async function adminGet (path) {
  const response = await fetch(`${base}${path}`, { headers: { authorization: `Bearer ${ADMIN}` } })
  return { status: response.status, body: await response.json() }
}

function parseJsonColumn (row, column) {
  if (!row || row[column] === null || row[column] === undefined) return null
  return JSON.parse(row[column])
}

try {
  await waitForServer()

  // ---------------------------------------------------------------- migrate
  // Um banco criado com o schema ANTIGO (sem as colunas de pairing) precisa
  // migrar preservando usuários e progresso. Simulamos: mata o servidor,
  // recria o request_log antigo por cima, reinsere progressão e sobe de novo.
  child.kill('SIGKILL')
  await new Promise(resolveDown => child.on('exit', resolveDown))
  let usersBefore
  let uuidBefore
  {
    const legacy = new DatabaseSync(dbPath)
    usersBefore = legacy.prepare('SELECT COUNT(*) AS total FROM users').get().total
    uuidBefore = legacy.prepare('SELECT uuid FROM users ORDER BY id LIMIT 1').get()?.uuid
    assert.ok(usersBefore >= 1, 'banco novo já tem o super admin')
    // Progresso gravado direto no banco antigo tem que sobreviver à migração.
    legacy.prepare('UPDATE users SET level = 7, chapter_progression = 3 WHERE id = (SELECT MIN(id) FROM users)').run()
    legacy.exec('DROP TABLE request_log')
    legacy.exec(`
      CREATE TABLE request_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        path TEXT NOT NULL,
        body_json TEXT,
        created_at INTEGER NOT NULL
      );
    `)
    legacy.prepare('INSERT INTO request_log (user_id, path, body_json, created_at) VALUES (?, ?, ?, ?)')
      .run(1, 'game/session/heartbeat', '{}', 1)
    legacy.close()
  }
  const reborn = spawn(process.execPath, ['src/index.js'], {
    cwd: root,
    env: { ...process.env, HOST: '127.0.0.1', PORT: String(port), DB_PATH: dbPath, REVIVAL_CONFIG_PATH: resolve(work, 'config/revival.json'), PACKS_CONFIG_PATH: resolve(work, 'config/packs.json'), EVENTS_CONFIG_PATH: resolve(work, 'config/events.json'), SITE_CONFIG_PATH: resolve(work, 'config/site.json'), RESEARCH_MODE: 'true', REVIVAL_ADMIN_TOKEN: ADMIN },
    stdio: ['ignore', 'pipe', 'pipe']
  })
  reborn.stdout.on('data', chunk => { logs += chunk.toString() })
  reborn.stderr.on('data', chunk => { logs += chunk.toString() })
  for (let attempt = 0; attempt < 50; attempt++) {
    try { if ((await fetch(`${base}/revival/health`)).ok) break } catch {}
    await new Promise(resolveWait => setTimeout(resolveWait, 100))
  }
  {
    const after = new DatabaseSync(dbPath)
    const usersAfter = after.prepare('SELECT COUNT(*) AS total FROM users').get().total
    const first = after.prepare('SELECT uuid, level, chapter_progression FROM users ORDER BY id LIMIT 1').get()
    assert.equal(usersAfter, usersBefore, 'migração não perde usuários')
    assert.equal(first.uuid, uuidBefore, 'identidade preservada')
    assert.equal(first.level, 7, 'progresso (level) preservado')
    assert.equal(first.chapter_progression, 3, 'progresso (chapter) preservado')
    const columns = after.prepare('PRAGMA table_info(request_log)').all().map(row => row.name)
    for (const column of ['method', 'status', 'code', 'response_json', 'note']) {
      assert.ok(columns.includes(column), `coluna ${column} criada pela migração`)
    }
    const legacyRow = after.prepare('SELECT * FROM request_log ORDER BY id LIMIT 1').get()
    assert.equal(legacyRow.path, 'game/session/heartbeat', 'linha legada do request_log preservada')
    assert.equal(legacyRow.response_json, null, 'linha legada sem response não ganha payload inventado')
    after.close()
  }

  // ------------------------------------------------------- baseline + fluxo
  const baseline = await adminGet('/revival/requests?limit=1')
  assert.equal(baseline.status, 200)
  assert.equal(typeof baseline.body.last_id, 'number', 'last_id é o cursor do baseline')
  const cursor = baseline.body.last_id
  // A linha legada (pré-migração) existe e não tem response — não pode sumir.
  assert.ok(baseline.body.requests.length >= 1, 'linha legada visível no modo DESC')

  const registered = await game('/game/auth/register', { client_version: '1.13.1', device_id: 'device-abc-123' })
  assert.equal(registered.status, 200)
  const login = await game('/game/auth/login-device', { client_version: '1.13.1', user_id: registered.body.user_id, password: registered.body.password })
  assert.equal(login.status, 200)

  const incremental = await adminGet(`/revival/requests?since_id=${cursor}&limit=1000`)
  assert.equal(incremental.status, 200)
  const rows = incremental.body.requests
  assert.ok(rows.length >= 2, 'register e login-device entram no delta')
  // Ordem crescente por id = sequência temporal real da execução.
  for (let i = 1; i < rows.length; i++) assert.ok(rows[i - 1].id < rows[i].id, `ordem crescente por id: ${rows[i - 1].id} !< ${rows[i].id}`)
  assert.ok(rows.every(row => row.id > cursor), 'nenhum request anterior ao baseline vaza no delta')

  const registerRow = rows.find(row => row.path === '/game/auth/register')
  assert.ok(registerRow, 'register registrado mesmo sem autenticação prévia')
  assert.equal(registerRow.method, 'POST')
  assert.equal(registerRow.status, 200)
  assert.equal(registerRow.code, 1000)
  assert.equal(registerRow.user_id, registered.body.user_id, 'user_id da conta criada associado ao request')
  const registerRequest = parseJsonColumn(registerRow, 'body_json')
  const registerResponse = parseJsonColumn(registerRow, 'response_json')
  assert.equal(registerRequest.device_id, '<device_id>', 'device_id redigido no request persistido')
  assert.equal(registerResponse.token, '<token>', 'token JWT redigido no response persistido')
  assert.equal(registerResponse.password, '<password>', 'password redigido no response persistido')
  assert.equal(registerResponse.recovery_code, '<recovery_code>', 'recovery code redigido no response persistido')
  assert.ok(registerResponse.uts, 'shape do response preservado além dos redigidos')
  assert.equal(registerResponse.puuid, '<puuid>', 'puuid redigido: identificador estável de conta')

  // ---------------------------------------------------------------------
  // TIPO do wire preservado: `device_id` e credencial (UUID string) em
  // game/auth/*, mas id NUMERICO da linha de dispositivo em game/devices/*.
  // Redigir o inteiro trocaria numero por string no log e em toda fixture
  // derivada — tipo errado no wire e o que derruba o parse do cliente.
  // Este bloco vai do request_log ATE a fixture sanitizada.
  // ---------------------------------------------------------------------
  const tokenAuth = { 'x-ubu-token': registered.body.token }
  await game('/game/devices/register', { device_id: 'device-abc-123', platform_id: 4 }, tokenAuth)
  await game('/game/devices/describe', { device_id: 1 }, tokenAuth)
  await game('/game/devices/unregister', { device_id: 1 }, tokenAuth)

  const aposDevices = await adminGet(`/revival/requests?since_id=${cursor}&limit=200`)
  const linhasDevices = aposDevices.body.requests.filter(row => row.path.startsWith('/game/devices/'))
  assert.ok(linhasDevices.length >= 2, 'as rotas de devices entraram no request_log')

  for (const linha of linhasDevices.filter(l => l.path !== '/game/devices/register')) {
    const corpo = parseJsonColumn(linha, 'body_json')
    assert.equal(typeof corpo.device_id, 'number',
      `${linha.path}: device_id numerico tem que continuar numero no log`)
    assert.equal(corpo.device_id, 1)
  }
  const linhaRegister = linhasDevices.find(l => l.path === '/game/devices/register')
  if (linhaRegister) {
    assert.equal(parseJsonColumn(linhaRegister, 'body_json').device_id, '<device_id>',
      'device_id STRING de autenticacao continua redigido')
  }

  // E a fixture derivada (sanitizador do harness) tem que chegar na mesma
  // conclusao: numero permanece numero, credencial vira placeholder.
  {
    const { sanitize } = await import('../../scripts/fixture_sanitize.mjs')
    const numerico = sanitize({ device_id: 1, user_id: 8 })
    assert.equal(numerico.device_id, 1, 'fixture preserva o device_id numerico')
    assert.equal(typeof numerico.device_id, 'number')
    const credencial = sanitize({ device_id: '3f2504e0-4f89-11d3-9a0c-0305e82c3301' })
    assert.equal(credencial.device_id, '<device-id>', 'fixture redige a credencial')
    for (const chave of ['password', 'token', 'recovery_code', 'puuid']) {
      const saida = sanitize({ [chave]: 'valor-real-que-nao-pode-vazar' })
      assert.match(String(saida[chave]), /^<[a-z-]+>$/, `${chave} continua redigido na fixture`)
    }
  }

  const loginRow = rows.find(row => row.path === '/game/auth/login-device')
  assert.ok(loginRow, 'login-device registrado')
  assert.equal(loginRow.status, 200)
  assert.equal(parseJsonColumn(loginRow, 'response_json').code, 1000)
  assert.equal(parseJsonColumn(loginRow, 'body_json').password, '<password>', 'password do login redigido')

  // Requests autenticados continuam pareados na mesma linha.
  const authHeaders = { 'x-ubu-token': login.body.token }
  const userData = await game('/game/player/user-data', {}, authHeaders)
  assert.equal(userData.status, 200)
  const after = await adminGet(`/revival/requests?since_id=${incremental.body.last_id}&limit=1000`)
  const userDataRow = after.body.requests.find(row => row.path === '/game/player/user-data')
  assert.ok(userDataRow, 'rota autenticada no log')
  assert.equal(userDataRow.status, 200)
  assert.ok(parseJsonColumn(userDataRow, 'response_json').user_data, 'response pareado na mesma linha do request')

  // Endpoint desconhecido (fora das 116 do cliente) em research mode marca o
  // fallback na própria linha do log — é o sinal de "não implementado" para o
  // delta do harness.
  await game('/game/test/unknown-endpoint', { probe: 1 }, authHeaders)
  const research = await (await fetch(`${base}/revival/research`)).json()
  assert.ok(research.fallback_endpoints.some(entry => entry.path === '/game/test/unknown-endpoint'), 'fallback registrado em /revival/research')
  const tail = await adminGet(`/revival/requests?since_id=${after.body.last_id}&limit=1000`)
  const fallbackRow = tail.body.requests.find(row => row.path === '/game/test/unknown-endpoint')
  assert.equal(fallbackRow.note, 'research-fallback', 'linha do fallback marcada com note')
  assert.equal(fallbackRow.status, 200, 'fallback responde 200 vazio (research)')

  // Guards rejeitados também viram evidência (405/403/401).
  await fetch(`${base}/game/session/heartbeat`, { method: 'GET' })
  const guardTail = await adminGet(`/revival/requests?since_id=${tail.body.last_id}&limit=1000`)
  const guardRow = guardTail.body.requests.find(row => row.path === '/game/session/heartbeat')
  assert.ok(guardRow, 'request rejeitado por guard também é logado')
  assert.equal(guardRow.status, 405)

  // Sem token admin a captura é negada.
  const unauthorized = await fetch(`${base}/revival/requests?since_id=0`)
  assert.equal(unauthorized.status, 401, '/revival/requests exige admin')

  // since_id inválido não explode: trata como 0.
  const invalid = await adminGet('/revival/requests?since_id=notanumber')
  assert.equal(invalid.status, 200)

  reborn.kill('SIGKILL')
  console.log('request-log.mjs: OK')
  process.exit(0)
} catch (error) {
  console.error('request-log.mjs FALHOU:', error)
  child.kill('SIGKILL')
  process.exit(1)
} finally {
  rmSync(work, { recursive: true, force: true })
}
