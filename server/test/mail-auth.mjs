import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync, unlinkSync } from 'node:fs'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const work = mkdtempSync(resolve(tmpdir(), 'mighty-doom-mail-'))
mkdirSync(resolve(work, 'config'), { recursive: true })
writeFileSync(resolve(work, 'config/revival.json'), JSON.stringify({ client_version: '1.13.1', api_version: '24.0.0', game_data_token: 'test' }))
writeFileSync(resolve(work, 'config/packs.json'), '{"packs":[]}')
writeFileSync(resolve(work, 'config/events.json'), '{"events":[]}')
writeFileSync(resolve(work, 'config/site.json'), '{}')
const smtpPath = resolve(work, 'config/smtp.json')

const SMTP_USER = 'tester'
const SMTP_PASS = 'segredo-do-app'
const ADMIN_EMAIL = 'admin@revival.local'
const ADMIN_PASSWORD = 'super-admin-senha-123'

// --- SMTP fake: saudação, EHLO com AUTH LOGIN, DATA capturado -------------
const captured = []
const fakeSmtp = createServer(socket => {
  let buffer = ''
  let inData = false
  let authStep = 0
  let mail = { commands: [], data: '' }
  socket.write('220 fake.revival ESMTP pronto\r\n')
  socket.on('data', chunk => {
    buffer += chunk.toString('utf8')
    let index
    while ((index = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, index).replace(/\r$/, '')
      buffer = buffer.slice(index + 1)
      if (inData) {
        mail.data += line + '\r\n'
        if (line === '.') {
          inData = false
          captured.push(mail)
          mail = { commands: [], data: '' }
          socket.write('250 ok: fila fake\r\n')
        }
        continue
      }
      const verb = line.split(' ')[0].toUpperCase()
      mail.commands.push(line)
      if (authStep === 1) { authStep = 2; socket.write('334 UGFzc3dvcmQ6\r\n'); continue }
      if (authStep === 2) {
        authStep = 0
        assert.equal(line, Buffer.from(SMTP_PASS).toString('base64'), 'senha SMTP não bateu')
        socket.write('235 autenticado\r\n')
        continue
      }
      if (verb === 'EHLO') socket.write('250-fake.revival\r\n250 AUTH LOGIN\r\n')
      else if (verb === 'AUTH') { assert.equal(line, 'AUTH LOGIN'); authStep = 1; socket.write('334 VXNlcm5hbWU6\r\n') }
      else if (verb === 'STARTTLS') socket.write('454 TLS indisponível no fake\r\n')
      else if (verb === 'MAIL' || verb === 'RCPT') socket.write('250 ok\r\n')
      else if (verb === 'DATA') { inData = true; socket.write('354 manda\r\n') }
      else if (verb === 'QUIT') { socket.write('221 tchau\r\n'); socket.end() }
      else socket.write('250 ok\r\n')
    }
  })
})
const smtpPort = await new Promise((resolvePort, rejectPort) => {
  fakeSmtp.once('error', rejectPort)
  fakeSmtp.listen(0, '127.0.0.1', () => resolvePort(fakeSmtp.address().port))
})

writeFileSync(smtpPath, JSON.stringify({ host: '127.0.0.1', port: smtpPort, secure: false, user: SMTP_USER, pass: SMTP_PASS, from: 'painel@revival.local', from_name: 'Revival' }))

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
  env: { ...process.env, HOST: '127.0.0.1', PORT: String(port), DB_PATH: resolve(work, 'runtime/db.sqlite3'), REVIVAL_CONFIG_PATH: resolve(work, 'config/revival.json'), PACKS_CONFIG_PATH: resolve(work, 'config/packs.json'), EVENTS_CONFIG_PATH: resolve(work, 'config/events.json'), SITE_CONFIG_PATH: resolve(work, 'config/site.json'), SMTP_CONFIG_PATH: smtpPath, RESEARCH_MODE: 'true', REVIVAL_ADMIN_EMAIL: ADMIN_EMAIL, REVIVAL_ADMIN_PASSWORD: ADMIN_PASSWORD },
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

function codeFromLastMail () {
  const mail = captured[captured.length - 1]
  assert.ok(mail, 'nenhum e-mail capturado')
  // subject tem acento e vai codificado RFC 2047; corpo é 8bit UTF-8
  assert.match(mail.data, /^Subject: /m)
  const match = /acesso [eé]: (\d{6})/.exec(mail.data)
  assert.ok(match, `código não encontrado em: ${mail.data.slice(0, 400)}`)
  return match[1]
}

try {
  await waitForServer()

  // --- 1º acesso por e-mail: conta criada + código enviado ---------------
  const email = 'jogador@exemplo.com'
  const first = await request('/account/email-code/request', { method: 'POST', body: JSON.stringify({ email }) })
  assert.equal(first.body.code_sent, true)
  assert.equal(first.body.account_created, true)
  const code = codeFromLastMail()
  const sent = captured[captured.length - 1]
  assert.ok(sent.data.includes('To: <jogador@exemplo.com>'), sent.data.slice(0, 200))
  assert.ok(sent.data.includes('From: Revival <painel@revival.local>'), sent.data.slice(0, 200))
  assert.ok(sent.commands.includes(Buffer.from(SMTP_USER).toString('base64')), 'usuário SMTP não enviado')

  // código errado não loga; código certo loga sem senha
  await request('/account/email-code/login', { method: 'POST', body: JSON.stringify({ email, code: '000000' }) }, 401)
  const login = await request('/account/email-code/login', { method: 'POST', body: JSON.stringify({ email, code }) })
  const cookie = login.response.headers.get('set-cookie').split(';')[0]
  assert.equal(login.body.password_set, false)
  assert.equal(login.body.account.email, email)
  const me = await request('/account/me', { headers: { cookie } })
  assert.equal(me.body.account.email, email)

  // pedido imediato de outro código: rate limit
  await request('/account/email-code/request', { method: 'POST', body: JSON.stringify({ email }) }, 429)

  // primeira senha sem current_password (conta sem senha)
  await request('/account/password', { method: 'POST', headers: { cookie }, body: JSON.stringify({ new_password: 'senha-nova-123' }) })
  await request('/account/logout', { method: 'POST', headers: { cookie }, body: '{}' })
  const byPassword = await request('/account/login', { method: 'POST', body: JSON.stringify({ login: email, password: 'senha-nova-123' }) })
  assert.equal(byPassword.body.account.email, email)

  // --- esqueci a senha via código de e-mail ------------------------------
  const second = await request('/account/register', { method: 'POST', body: JSON.stringify({ display_name: 'Segundo', email: 'segundo@exemplo.com', password: 'senha-antiga-123' }) }, 201)
  await request('/account/forgot-password', { method: 'POST', body: JSON.stringify({ email: 'segundo@exemplo.com' }) })
  const resetCode = codeFromLastMail()
  await request('/account/reset-password', { method: 'POST', body: JSON.stringify({ email: 'segundo@exemplo.com', code: '000000', new_password: 'senha-troca-456' }) }, 400)
  await request('/account/reset-password', { method: 'POST', body: JSON.stringify({ email: 'segundo@exemplo.com', code: resetCode, new_password: 'senha-troca-456' }) })
  await request('/account/login', { method: 'POST', body: JSON.stringify({ login: 'segundo@exemplo.com', password: 'senha-antiga-123' }) }, 401)
  await request('/account/login', { method: 'POST', body: JSON.stringify({ login: 'segundo@exemplo.com', password: 'senha-troca-456' }) })

  // e-mail inexistente no esqueci: resposta neutra (anti-enumerção)
  const ghost = await request('/account/forgot-password', { method: 'POST', body: JSON.stringify({ email: 'ninguem@exemplo.com' }) })
  assert.equal(ghost.body.code_sent, true)
  assert.equal(captured.filter(m => m.data.includes('ninguem@exemplo.com')).length, 0)

  // --- admin: SMTP settings mascarados ------------------------------------
  const playerCookie = second.response.headers.get('set-cookie').split(';')[0]
  await request('/account/admin/smtp', { headers: { cookie: playerCookie } }, 403)
  const adminLogin = await request('/account/login', { method: 'POST', body: JSON.stringify({ login: ADMIN_EMAIL, password: ADMIN_PASSWORD }) })
  const adminCookie = adminLogin.response.headers.get('set-cookie').split(';')[0]
  const smtpView = await request('/account/admin/smtp', { headers: { cookie: adminCookie } })
  assert.equal(smtpView.body.smtp.configured, true)
  assert.equal(smtpView.body.smtp.has_pass, true)
  assert.equal('pass' in smtpView.body.smtp, false, 'resposta vazou a senha')
  // salvar sem digitar a senha de novo preserva a salva
  const patched = await request('/account/admin/smtp', { method: 'PATCH', headers: { cookie: adminCookie }, body: JSON.stringify({ host: '127.0.0.1', port: smtpPort, user: SMTP_USER, pass: '', from: 'painel@revival.local' }) })
  assert.equal(patched.body.smtp.has_pass, true)

  // PATCH com senha em branco preservou a salva? o próximo envio (e-mail
  // novo, sem rate limit) só chega ao 250 se o AUTH LOGIN continuar válido.
  const afterPatch = await request('/account/email-code/request', { method: 'POST', body: JSON.stringify({ email: ADMIN_EMAIL }) })
  assert.equal(afterPatch.body.code_sent, true)
  assert.ok(captured[captured.length - 1].data.includes(`To: <${ADMIN_EMAIL}>`))

  // --- sem SMTP configurado: 503 claro + fallback de recovery ------------
  unlinkSync(smtpPath)
  const noSmtp = await request('/account/email-code/request', { method: 'POST', body: JSON.stringify({ email: 'outra@exemplo.com' }) }, 503)
  assert.equal(noSmtp.body.error, 'smtp-not-configured')
  const legacy = await request('/account/forgot-password', { method: 'POST', body: JSON.stringify({ email: 'segundo@exemplo.com' }) })
  assert.equal(legacy.body.recovery_required, true)

  console.log('mail-auth: todos os testes passaram')
} finally {
  child.kill()
  await new Promise(resolveExit => {
    if (child.exitCode !== null) return resolveExit()
    child.once('exit', resolveExit)
    setTimeout(resolveExit, 3000)
  })
  fakeSmtp.close()
  try { rmSync(work, { recursive: true, force: true }) } catch { /* Windows pode segurar o sqlite por um instante */ }
}
