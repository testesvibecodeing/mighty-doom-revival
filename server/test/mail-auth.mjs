import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, rmSync, writeFileSync, unlinkSync } from 'node:fs'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'
import { DatabaseSync } from 'node:sqlite'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const work = mkdtempSync(resolve(tmpdir(), 'mighty-doom-mail-'))
mkdirSync(resolve(work, 'config'), { recursive: true })
writeFileSync(resolve(work, 'config/revival.json'), JSON.stringify({ client_version: '1.13.1', api_version: '24.0.0', game_data_token: 'test' }))
writeFileSync(resolve(work, 'config/packs.json'), '{"packs":[]}')
writeFileSync(resolve(work, 'config/events.json'), '{"events":[]}')
writeFileSync(resolve(work, 'config/site.json'), '{}')
const smtpPath = resolve(work, 'config/smtp.json')
const dbPath = resolve(work, 'runtime/db.sqlite3')

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
  env: { ...process.env, HOST: '127.0.0.1', PORT: String(port), DB_PATH: dbPath, REVIVAL_CONFIG_PATH: resolve(work, 'config/revival.json'), PACKS_CONFIG_PATH: resolve(work, 'config/packs.json'), EVENTS_CONFIG_PATH: resolve(work, 'config/events.json'), SITE_CONFIG_PATH: resolve(work, 'config/site.json'), SMTP_CONFIG_PATH: smtpPath, RESEARCH_MODE: 'true', REVIVAL_ADMIN_EMAIL: ADMIN_EMAIL, REVIVAL_ADMIN_PASSWORD: ADMIN_PASSWORD },
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

// Guard de toda rota /game/*: POST + x-ubu-apiversion + content-type JSON.
async function gameRequest (path, payload) {
  const response = await fetch(`${base}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-ubu-apiversion': '24.0.0' },
    body: JSON.stringify(payload)
  })
  return { status: response.status, body: await response.json() }
}

function temporaryPasswordFromLastMail () {
  const mail = captured[captured.length - 1]
  assert.ok(mail, 'nenhum e-mail capturado')
  // subject tem acento e vai codificado RFC 2047; corpo é 8bit UTF-8
  assert.match(mail.data, /^Subject: /m)
  const match = /senha temporária [eé]: (RV-[A-Za-z0-9_-]{12})/.exec(mail.data)
  assert.ok(match, `senha temporária não encontrada em: ${mail.data.slice(0, 400)}`)
  return match[1]
}

try {
  await waitForServer()

  // --- cadastro/login exigem e-mail + senha -------------------------------
  const email = 'jogador@exemplo.com'
  const originalPassword = 'senha-original-123'
  const first = await request('/account/register', { method: 'POST', body: JSON.stringify({ display_name: 'Jogador', email, password: originalPassword }) }, 201)
  assert.equal(first.body.account.email, email)
  assert.equal('recovery_code' in first.body, false, 'cadastro público não deve criar atalho sem SMTP')
  assert.equal(captured.length, 0, 'cadastro normal não envia código nem senha')

  const db = new DatabaseSync(dbPath, { readOnly: true })
  const stored = db.prepare('SELECT password_hash FROM users WHERE lower(email) = ?').get(email)
  db.close()
  assert.match(stored.password_hash, /^scrypt\$[0-9a-f]{32}\$[0-9a-f]{64}$/)
  assert.equal(stored.password_hash.includes(originalPassword), false, 'banco não pode guardar senha em claro')

  await request('/account/login', { method: 'POST', body: JSON.stringify({ email, password: 'errada-123' }) }, 401)
  const byPassword = await request('/account/login', { method: 'POST', body: JSON.stringify({ email, password: originalPassword }) })
  assert.equal(byPassword.body.account.email, email)
  assert.equal(byPassword.body.temporary_password_used, false)

  // Rotas antigas de login sem senha permanecem explicitamente aposentadas.
  await request('/account/email-code/request', { method: 'POST', body: JSON.stringify({ email }) }, 410)
  await request('/account/email-code/login', { method: 'POST', body: JSON.stringify({ email, code: '000000' }) }, 410)

  // --- esqueci a senha: temporária por SMTP, hash e uso único ------------
  const second = await request('/account/register', { method: 'POST', body: JSON.stringify({ display_name: 'Segundo', email: 'segundo@exemplo.com', password: 'senha-antiga-123' }) }, 201)
  const forgot = await request('/account/forgot-password', { method: 'POST', body: JSON.stringify({ email: 'segundo@exemplo.com' }) })
  assert.equal(forgot.body.temporary_password_sent, true)
  const temporary = temporaryPasswordFromLastMail()
  const sent = captured[captured.length - 1]
  assert.ok(sent.data.includes('To: <segundo@exemplo.com>'), sent.data.slice(0, 200))
  assert.ok(sent.data.includes('From: Revival <painel@revival.local>'), sent.data.slice(0, 200))
  assert.ok(sent.commands.includes(Buffer.from(SMTP_USER).toString('base64')), 'usuário SMTP não enviado')

  // Pedir recuperação não derruba a senha atual; a troca ocorre ao usar a
  // temporária corretamente. Depois disso, a anterior deixa de valer.
  await request('/account/login', { method: 'POST', body: JSON.stringify({ email: 'segundo@exemplo.com', password: 'senha-antiga-123' }) })
  await request('/account/login', { method: 'POST', body: JSON.stringify({ email: 'segundo@exemplo.com', password: 'RV-invalida000' }) }, 401)
  const temporaryLogin = await request('/account/login', { method: 'POST', body: JSON.stringify({ email: 'segundo@exemplo.com', password: temporary }) })
  assert.equal(temporaryLogin.body.temporary_password_used, true)
  await request('/account/login', { method: 'POST', body: JSON.stringify({ email: 'segundo@exemplo.com', password: 'senha-antiga-123' }) }, 401)
  const promoted = await request('/account/login', { method: 'POST', body: JSON.stringify({ email: 'segundo@exemplo.com', password: temporary }) })
  assert.equal(promoted.body.temporary_password_used, false, 'depois do uso vira a senha ativa, não reutiliza o reset')

  const dbAfterReset = new DatabaseSync(dbPath, { readOnly: true })
  const resetRows = dbAfterReset.prepare('SELECT password_hash, used_at FROM password_resets WHERE user_id = ?').all(second.body.account.id)
  dbAfterReset.close()
  assert.equal(resetRows.length, 1)
  assert.ok(resetRows[0].used_at > 0)
  assert.equal(resetRows[0].password_hash.includes(temporary), false, 'senha temporária não pode ficar em claro')

  // O endpoint antigo de redefinição/fallback local não contorna o SMTP.
  await request('/account/reset-password', { method: 'POST', body: JSON.stringify({ email: 'segundo@exemplo.com', recovery_code: 'RV-QUALQUER', new_password: 'senha-troca-456' }) }, 410)

  // --- credencial obsoleta no APK: o contrato que a Activity depende ------
  //
  // O `credentials.json` do cliente guarda user_id + SENHA, e é com ela que a
  // Unity chama `game/auth/login-device`. Se a senha muda no site, o arquivo
  // local fica velho. Aqui provamos o que a Activity mede no preflight: a
  // senha antiga passa a ser REJEITADA de forma determinística (403/2101) e a
  // nova funciona — não existe estado em que as duas valham, e não existe
  // estado em que o servidor aceite silenciosamente a credencial morta.
  const gameId = second.body.account.id
  const comTemporaria = await gameRequest('/game/auth/login-device', { client_version: '1.13.1', user_id: gameId, password: temporary })
  assert.equal(comTemporaria.status, 200)
  assert.equal(comTemporaria.body.code, 1000, 'a temporária promovida é a senha ativa do jogo')

  // A troca para a permanente é exatamente a chamada que a Activity faz com o
  // cookie da sessão recém-criada, usando a temporária como current_password.
  const sessaoTemporaria = promoted.response.headers.get('set-cookie').split(';')[0]
  const permanente = 'senha-permanente-789'
  await request('/account/password', { method: 'POST', headers: { cookie: sessaoTemporaria }, body: JSON.stringify({ current_password: temporary, new_password: permanente }) })

  const credencialVelha = await gameRequest('/game/auth/login-device', { client_version: '1.13.1', user_id: gameId, password: temporary })
  assert.equal(credencialVelha.status, 403, 'credencial obsoleta não pode continuar entrando')
  assert.equal(credencialVelha.body.code, 2101)
  const credencialNova = await gameRequest('/game/auth/login-device', { client_version: '1.13.1', user_id: gameId, password: permanente })
  assert.equal(credencialNova.status, 200)
  assert.equal(credencialNova.body.code, 1000)
  assert.equal('password' in credencialNova.body, false, 'login-device nunca devolve senha')

  // Depois da permanente, o login do site também só aceita a nova.
  await request('/account/login', { method: 'POST', body: JSON.stringify({ email: 'segundo@exemplo.com', password: temporary }) }, 401)
  const comPermanente = await request('/account/login', { method: 'POST', body: JSON.stringify({ email: 'segundo@exemplo.com', password: permanente }) })
  assert.equal(comPermanente.body.temporary_password_used, false)

  // e-mail inexistente no esqueci: resposta neutra (anti-enumerção)
  const ghost = await request('/account/forgot-password', { method: 'POST', body: JSON.stringify({ email: 'ninguem@exemplo.com' }) })
  assert.equal(ghost.body.temporary_password_sent, true)
  assert.equal(captured.filter(m => m.data.includes('ninguem@exemplo.com')).length, 0)

  // --- admin: SMTP settings mascarados ------------------------------------
  const playerCookie = comPermanente.response.headers.get('set-cookie').split(';')[0]
  await request('/account/admin/smtp', { headers: { cookie: playerCookie } }, 403)
  const adminLogin = await request('/account/login', { method: 'POST', body: JSON.stringify({ email: ADMIN_EMAIL, password: ADMIN_PASSWORD }) })
  const adminCookie = adminLogin.response.headers.get('set-cookie').split(';')[0]
  const smtpView = await request('/account/admin/smtp', { headers: { cookie: adminCookie } })
  assert.equal(smtpView.body.smtp.configured, true)
  assert.equal(smtpView.body.smtp.has_pass, true)
  assert.equal('pass' in smtpView.body.smtp, false, 'resposta vazou a senha')
  // salvar sem digitar a senha de novo preserva a salva
  const patched = await request('/account/admin/smtp', { method: 'PATCH', headers: { cookie: adminCookie }, body: JSON.stringify({ host: '127.0.0.1', port: smtpPort, user: SMTP_USER, pass: '', from: 'painel@revival.local' }) })
  assert.equal(patched.body.smtp.has_pass, true)

  // PATCH com senha em branco preservou a salva? o próximo e-mail só chega ao
  // 250 se o AUTH LOGIN do SMTP continuar válido.
  const afterPatch = await request('/account/forgot-password', { method: 'POST', body: JSON.stringify({ email: ADMIN_EMAIL }) })
  assert.equal(afterPatch.body.temporary_password_sent, true)
  assert.ok(captured[captured.length - 1].data.includes(`To: <${ADMIN_EMAIL}>`))

  // --- sem SMTP configurado: 503 claro e nenhum fallback local -----------
  unlinkSync(smtpPath)
  const noSmtp = await request('/account/forgot-password', { method: 'POST', body: JSON.stringify({ email: 'segundo@exemplo.com' }) }, 503)
  assert.equal(noSmtp.body.error, 'smtp-not-configured')

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
