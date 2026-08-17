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
writeFileSync(resolve(work, 'config/site.json'), '{}')

const ADMIN_EMAIL = 'admin@revival.local'
const ADMIN_PASSWORD = 'super-admin-senha-123'

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
  env: { ...process.env, HOST: '127.0.0.1', PORT: String(port), DB_PATH: resolve(work, 'runtime/db.sqlite3'), REVIVAL_CONFIG_PATH: resolve(work, 'config/revival.json'), PACKS_CONFIG_PATH: resolve(work, 'config/packs.json'), EVENTS_CONFIG_PATH: resolve(work, 'config/events.json'), SITE_CONFIG_PATH: resolve(work, 'config/site.json'), RESEARCH_MODE: 'true', REVIVAL_ADMIN_EMAIL: ADMIN_EMAIL, REVIVAL_ADMIN_PASSWORD: ADMIN_PASSWORD },
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
  assert.equal(me.body.account.is_admin, false)
  assert.equal(me.body.snapshot.progression.level, 1)
  await request('/account/profile', { method: 'PATCH', headers: { cookie }, body: JSON.stringify({ display_name: 'Updated Slayer', email: 'updated@example.com' }) })
  await request('/account/password', { method: 'POST', headers: { cookie }, body: JSON.stringify({ current_password: 'password-123', new_password: 'password-456' }) })
  await request('/account/logout', { method: 'POST', headers: { cookie }, body: '{}' })
  await request('/account/login', { method: 'POST', body: JSON.stringify({ login: 'updated@example.com', password: 'password-456' }) })

  // --- Super Admin: semeado no boot com a senha do env ---
  const adminLogin = await request('/account/login', { method: 'POST', body: JSON.stringify({ login: ADMIN_EMAIL, password: ADMIN_PASSWORD }) })
  const adminCookie = adminLogin.response.headers.get('set-cookie').split(';')[0]
  assert.equal(adminLogin.body.account.is_admin, true)

  const overview = await request('/account/admin/overview', { headers: { cookie: adminCookie } })
  assert.equal(overview.body.overview.players, 2)
  assert.equal(overview.body.overview.admins, 1)

  // jogador comum não entra na área admin
  const second = await request('/account/register', { method: 'POST', body: JSON.stringify({ display_name: 'Plain Slayer', email: 'plain@example.com', password: 'password-789' }) }, 201)
  let plainCookie = second.response.headers.get('set-cookie').split(';')[0]
  await request('/account/admin/overview', { headers: { cookie: plainCookie } }, 403)

  // --- admin reseta a senha de quem esqueceu (e derruba as sessões) ---
  const plainId = second.body.account.id
  const reset = await request(`/account/admin/users/${plainId}/reset-password`, { method: 'POST', headers: { cookie: adminCookie }, body: '{}' })
  assert.ok(reset.body.password.length >= 8)
  await request('/account/notifications', { headers: { cookie: plainCookie } }, 401)
  const relogin = await request('/account/login', { method: 'POST', body: JSON.stringify({ login: 'plain@example.com', password: reset.body.password }) })
  plainCookie = relogin.response.headers.get('set-cookie').split(';')[0]

  // --- novo código de recuperação emitido pelo admin ---
  const recovery = await request(`/account/admin/users/${plainId}/recovery-code`, { method: 'POST', headers: { cookie: adminCookie }, body: '{}' })
  assert.match(recovery.body.recovery_code, /^RV-/)

  // --- conceder recurso a um jogador ---
  const grant = await request(`/account/admin/users/${plainId}/grant`, { method: 'POST', headers: { cookie: adminCookie }, body: JSON.stringify({ resource: 7, amount: 5 }) })
  assert.equal(grant.body.ok, true)

  // --- avisos: admin publica, jogador vê, admin remove ---
  const notice = await request('/account/admin/notifications', { method: 'POST', headers: { cookie: adminCookie }, body: JSON.stringify({ title: 'Novo APK disponível', body: 'Atualize o cliente', kind: 'update' }) }, 201)
  const playerNotices = await request('/account/notifications', { headers: { cookie: plainCookie } })
  assert.equal(playerNotices.body.notifications[0].title, 'Novo APK disponível')
  await request(`/account/admin/notifications/${notice.body.notification.id}`, { method: 'DELETE', headers: { cookie: adminCookie } })

  // --- loja: pacote com preço em moeda, ativa/desativa, aparece na visão do jogador ---
  const pack = await request('/account/admin/packs', { method: 'POST', headers: { cookie: adminCookie }, body: JSON.stringify({ tag: 'revival_test_pack', active: true, cost: [{ resource: 1, amount: 10 }], contents: [{ resource: 2, amount: 3 }] }) }, 201)
  assert.equal(pack.body.pack.active, true)
  const storeVisible = await request('/account/store', { headers: { cookie: plainCookie } })
  assert.equal(storeVisible.body.packs.length, 1)
  await request(`/account/admin/packs/${pack.body.pack.id}`, { method: 'PATCH', headers: { cookie: adminCookie }, body: JSON.stringify({ active: false }) })
  const storeHidden = await request('/account/store', { headers: { cookie: plainCookie } })
  assert.equal(storeHidden.body.packs.length, 0)
  await request(`/account/admin/packs/${pack.body.pack.id}`, { method: 'DELETE', headers: { cookie: adminCookie } })

  // --- pacote com preço real continua bloqueado ---
  await request('/account/admin/packs', { method: 'POST', headers: { cookie: adminCookie }, body: JSON.stringify({ tag: 'bad_pack', price: 9.99 }) }, 400)

  // --- eventos: criar, desativar, excluir ---
  const event = await request('/account/admin/events', { method: 'POST', headers: { cookie: adminCookie }, body: JSON.stringify({ tag: 'revival_test_event', active: true, always: true }) }, 201)
  assert.equal(event.body.event.always, true)
  await request(`/account/admin/events/${event.body.event.id}`, { method: 'PATCH', headers: { cookie: adminCookie }, body: JSON.stringify({ active: false }) })
  await request(`/account/admin/events/${event.body.event.id}`, { method: 'DELETE', headers: { cookie: adminCookie } })

  // --- personalização do site público ---
  const sitePatch = await request('/account/admin/site', { method: 'PATCH', headers: { cookie: adminCookie }, body: JSON.stringify({ show_faq: false, github_url: 'https://github.com/example/revival', hero_title: 'Meu servidor.<br>Minhas regras.' }) })
  assert.equal(sitePatch.body.site.show_faq, false)
  assert.equal(sitePatch.body.site.show_github, true)
  const publicSite = await request('/revival/site')
  assert.equal(publicSite.body.site.github_url, 'https://github.com/example/revival')
  assert.equal(publicSite.body.site.show_faq, false)
  // URL inválida é rejeitada; conteúdo de script é limpo do título.
  await request('/account/admin/site', { method: 'PATCH', headers: { cookie: adminCookie }, body: JSON.stringify({ github_url: 'javascript:alert(1)' }) }, 400)
  const xss = await request('/account/admin/site', { method: 'PATCH', headers: { cookie: adminCookie }, body: JSON.stringify({ hero_title: 'ok<script>alert(1)</script>' }) })
  assert.ok(!xss.body.site.hero_title.includes('script'))

  console.log('Mighty DOOM Revival account test: PASS')
} finally {
  child.kill('SIGTERM')
  await new Promise(resolveExit => child.once('exit', resolveExit))
  rmSync(work, { recursive: true, force: true })
}
