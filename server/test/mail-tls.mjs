// Política de TLS e de credencial do SMTP — o que este teste protege:
//
//   1. o certificado do servidor SMTP é VALIDADO por padrão. A versão anterior
//      passava `rejectUnauthorized: false` fixo, ou seja, aceitava em silêncio
//      qualquer certificado — inclusive o de um interceptador entre o servidor
//      e o provedor, que veria a senha de aplicativo do AUTH LOGIN;
//   2. AUTH LOGIN não sai em texto claro para fora da máquina. `base64` é
//      codificação, não cifra: sem TLS a credencial vai legível no fio;
//   3. nenhuma mensagem de erro ecoa usuário ou senha, nem em base64.
//
// O certificado real não é testável aqui de propósito: AGENTS.md proíbe
// versionar `*.pem`. Por isso a decisão de TLS vive num ponto único exportado
// (`tlsOptionsFor`), e é ele que este teste afirma.
import assert from 'node:assert/strict'
import { createServer } from 'node:net'
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { networkInterfaces, tmpdir } from 'node:os'
import { resolve } from 'node:path'

const work = mkdtempSync(resolve(tmpdir(), 'mighty-doom-mailtls-'))
process.env.SMTP_CONFIG_PATH = resolve(work, 'smtp.json')

const { sendMail, tlsOptionsFor, plaintextAuthAllowed, readSmtpConfig, writeSmtpConfig, smtpPublic } =
  await import('../src/mail.js')

const USER = 'tester'
const PASS = 'segredo-do-app-nao-vaza'
const USER_B64 = Buffer.from(USER).toString('base64')
const PASS_B64 = Buffer.from(PASS).toString('base64')

// --- 1. política de certificado -------------------------------------------
assert.equal(tlsOptionsFor({ host: 'smtp.exemplo.com' }).rejectUnauthorized, true,
  'sem opt-in explícito o certificado TEM que ser validado')
assert.equal(tlsOptionsFor({ host: 'smtp.exemplo.com' }).minVersion, 'TLSv1.2')
assert.equal(tlsOptionsFor({ host: 'smtp.exemplo.com' }).servername, 'smtp.exemplo.com',
  'sem servername o SNI/hostname check não acontece')
assert.equal(tlsOptionsFor({ host: 'smtp.exemplo.com', allow_invalid_cert: true }).rejectUnauthorized, false,
  'o escape existe, mas só quando alguém o liga explicitamente')

// --- 2. AUTH em texto claro -----------------------------------------------
for (const host of ['127.0.0.1', 'localhost', '::1', '127.0.0.53']) {
  assert.equal(plaintextAuthAllowed({ host }, false), true, `loopback liberado: ${host}`)
}
for (const host of ['smtp.gmail.com', '192.168.0.10', '10.0.2.2', '8.8.8.8']) {
  assert.equal(plaintextAuthAllowed({ host }, false), false, `fora da máquina exige TLS: ${host}`)
  assert.equal(plaintextAuthAllowed({ host }, true), true, `com TLS o AUTH pode ir: ${host}`)
  assert.equal(plaintextAuthAllowed({ host, allow_plaintext_auth: true }, false), true,
    `opt-in explícito continua possível: ${host}`)
}

// --- 3. defaults gravados e nunca revelar a senha --------------------------
writeFileSync(process.env.SMTP_CONFIG_PATH, JSON.stringify({
  host: 'smtp.exemplo.com', port: 587, user: USER, pass: PASS, from: 'nao-responda@exemplo.com'
}))
const carregado = readSmtpConfig()
assert.equal(carregado.allow_invalid_cert, false, 'config antigo sem a chave = validação LIGADA')
assert.equal(carregado.allow_plaintext_auth, false)
const publico = smtpPublic(carregado)
assert.equal('pass' in publico, false, 'a senha do SMTP nunca volta na API do painel')
assert.equal(publico.has_pass, true)
assert.equal(publico.allow_invalid_cert, false)
const salvo = writeSmtpConfig({ pass: '', allow_invalid_cert: true })
assert.equal(salvo.pass, PASS, 'senha vazia preserva a salva')
assert.equal(salvo.allow_invalid_cert, true)
assert.equal(writeSmtpConfig({ allow_invalid_cert: false }).allow_invalid_cert, false)

// --- SMTP falso: EHLO sem STARTTLS, AUTH sempre recusado ------------------
let ultimoAuth = null
const fake = createServer(socket => {
  let buffer = ''
  let authStep = 0
  socket.write('220 fake.revival ESMTP\r\n')
  socket.on('data', chunk => {
    buffer += chunk.toString('utf8')
    let index
    while ((index = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, index).replace(/\r$/, '')
      buffer = buffer.slice(index + 1)
      if (authStep === 1) { authStep = 2; socket.write('334 UGFzc3dvcmQ6\r\n'); continue }
      if (authStep === 2) {
        authStep = 0
        ultimoAuth = line
        socket.write('535 5.7.8 credencial recusada\r\n')
        continue
      }
      const verb = line.split(' ')[0].toUpperCase()
      if (verb === 'EHLO') socket.write('250-fake.revival\r\n250 AUTH LOGIN\r\n')
      else if (verb === 'AUTH') { authStep = 1; socket.write('334 VXNlcm5hbWU6\r\n') }
      else if (verb === 'QUIT') { socket.write('221 tchau\r\n'); socket.end() }
      else socket.write('250 ok\r\n')
    }
  })
})
// 0.0.0.0 para conseguir alcançar o MESMO servidor por um endereço que NÃO é
// loopback — é o único jeito de exercitar a recusa de verdade, sem simular.
const port = await new Promise((ok, erro) => {
  fake.once('error', erro)
  fake.listen(0, '0.0.0.0', () => ok(fake.address().port))
})

const mensagem = { to: 'jogador@exemplo.com', subject: 'teste', text: 'corpo' }
const base = { port, secure: false, user: USER, pass: PASS, from: 'painel@revival.local' }

try {
  // --- 4. loopback: AUTH pode ir sem TLS, e o erro do 535 não vaza segredo --
  let erro = await sendMail({ ...base, host: '127.0.0.1' }, mensagem).then(() => null, e => e)
  assert.ok(erro, 'o fake recusa o AUTH: sendMail tem que falhar')
  assert.equal(ultimoAuth, PASS_B64, 'o AUTH realmente chegou ao servidor (loopback liberado)')
  for (const segredo of [PASS, PASS_B64, USER_B64]) {
    assert.equal(erro.message.includes(segredo), false,
      `mensagem de erro vazou segredo: ${erro.message}`)
  }
  assert.match(erro.message, /AUTH senha/, 'o erro identifica a etapa por rótulo, não pelo payload')

  // --- 5. fora do loopback sem TLS: nem chega a mandar a credencial --------
  const externo = Object.values(networkInterfaces()).flat()
    .find(nic => nic && nic.family === 'IPv4' && !nic.internal)
  if (externo) {
    ultimoAuth = null
    erro = await sendMail({ ...base, host: externo.address }, mensagem).then(() => null, e => e)
    assert.ok(erro, 'AUTH em texto claro fora da máquina tem que ser recusado')
    assert.match(erro.message, /STARTTLS/)
    assert.equal(ultimoAuth, null, 'a credencial não pode nem ter sido enviada')
    for (const segredo of [PASS, PASS_B64, USER_B64]) {
      assert.equal(erro.message.includes(segredo), false, 'recusa não pode ecoar segredo')
    }

    // opt-in explícito volta a permitir — o escape existe e é consciente
    erro = await sendMail({ ...base, host: externo.address, allow_plaintext_auth: true }, mensagem)
      .then(() => null, e => e)
    assert.equal(ultimoAuth, PASS_B64, 'com allow_plaintext_auth a credencial vai (e o fake recusa)')
    assert.ok(erro)
  } else {
    console.log('mail-tls: sem IPv4 não-loopback nesta máquina; recusa fora do loopback não exercitada')
  }

  console.log('mail-tls: todos os testes passaram')
} finally {
  fake.close()
  rmSync(work, { recursive: true, force: true })
}
