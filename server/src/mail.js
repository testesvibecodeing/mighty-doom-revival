// Envio de e-mail em Node puro (net + tls) para senhas temporárias do painel:
// EHLO, STARTTLS quando o servidor oferece, AUTH LOGIN, DATA com dot-stuffing.
// Zero dependências — o servidor é builtin-only por projeto.
// Config: server/config/smtp.json (runtime, gitignored; exemplo em smtp.example.json).
import net from 'node:net'
import tls from 'node:tls'
import { randomBytes } from 'node:crypto'
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const CONFIG_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', 'config')
const CONFIG_PATH = process.env.SMTP_CONFIG_PATH || join(CONFIG_DIR, 'smtp.json')

const DEFAULTS = {
  host: '',
  port: 587,
  secure: false,
  user: '',
  pass: '',
  from: '',
  from_name: '',
  timeout_ms: 15000,
  // Certificado TLS do SMTP é VALIDADO por padrão. As duas chaves abaixo são
  // escapes explícitos, gravados no config por quem assume o risco — nunca
  // ligadas sozinhas, nunca ligadas por falha de handshake.
  allow_invalid_cert: false,
  allow_plaintext_auth: false
}

export function readSmtpConfig () {
  try {
    const raw = JSON.parse(readFileSync(CONFIG_PATH, 'utf8'))
    return { ...DEFAULTS, ...raw }
  } catch (error) {
    if (error.code !== 'ENOENT') console.warn(`[mail] smtp.json ilegível: ${error.message}`)
    return null
  }
}

// patch.pass vazio/ausente preserva a senha salva (o painel a máscara no form).
export function writeSmtpConfig (patch = {}) {
  const next = { ...(readSmtpConfig() || DEFAULTS) }
  for (const key of ['host', 'user', 'from', 'from_name']) {
    if (typeof patch[key] === 'string') next[key] = patch[key].trim()
  }
  if (typeof patch.pass === 'string' && patch.pass.trim()) next.pass = patch.pass.trim()
  if (patch.pass === null) next.pass = ''
  if (patch.port !== undefined) next.port = Math.floor(Number(patch.port)) || 587
  if (patch.timeout_ms !== undefined) next.timeout_ms = Math.max(3000, Math.floor(Number(patch.timeout_ms)) || 15000)
  if (patch.secure !== undefined) next.secure = patch.secure === true
  if (patch.allow_invalid_cert !== undefined) next.allow_invalid_cert = patch.allow_invalid_cert === true
  if (patch.allow_plaintext_auth !== undefined) next.allow_plaintext_auth = patch.allow_plaintext_auth === true
  mkdirSync(dirname(CONFIG_PATH), { recursive: true })
  writeFileSync(CONFIG_PATH, JSON.stringify(next, null, 2) + '\n')
  return next
}

export function smtpConfigured (config) {
  return Boolean(config && config.host && Number(config.port) > 0 && String(config.from).includes('@'))
}

// Resposta para o painel: nunca devolve a senha.
export function smtpPublic (config) {
  if (!config) return { configured: false }
  return {
    configured: smtpConfigured(config),
    host: config.host,
    port: config.port,
    secure: Boolean(config.secure),
    user: config.user,
    from: config.from,
    from_name: config.from_name,
    has_pass: Boolean(config.pass),
    allow_invalid_cert: Boolean(config.allow_invalid_cert),
    allow_plaintext_auth: Boolean(config.allow_plaintext_auth)
  }
}

// Ponto UNICO onde a politica de TLS e decidida — exportado para o teste
// poder afirmar `rejectUnauthorized` sem precisar de um certificado no repo
// (AGENTS.md regra 1: nada de *.pem versionado).
export function tlsOptionsFor (config, extra = {}) {
  return {
    ...extra,
    servername: config.host,
    minVersion: 'TLSv1.2',
    rejectUnauthorized: config.allow_invalid_cert !== true
  }
}

// Loopback nunca sai desta maquina: AUTH em texto claro ali nao expoe
// credencial a ninguem. Exportado pelo mesmo motivo acima.
export function plaintextAuthAllowed (config, secured) {
  return Boolean(secured) || isLoopback(config.host) || config.allow_plaintext_auth === true
}

class SmtpSession {
  constructor (config) {
    this.config = config
    this.socket = null
    this.buffer = ''
    this.reply = null
    this.replyLines = []
    this.error = null
  }

  attach (socket) {
    this.socket = socket
    socket.setTimeout(Number(this.config.timeout_ms) || 15000)
    socket.on('data', chunk => {
      this.buffer += chunk.toString('utf8')
      let index
      while ((index = this.buffer.indexOf('\n')) >= 0) {
        const line = this.buffer.slice(0, index).replace(/\r$/, '')
        this.buffer = this.buffer.slice(index + 1)
        this.handleLine(line)
      }
    })
    socket.on('timeout', () => this.fail(new Error('timeout de SMTP')))
    socket.on('error', err => this.fail(err))
  }

  handleLine (line) {
    if (!this.reply) return
    this.replyLines.push(line)
    // Resposta completa: linha final "NNN texto" (as intermediárias são "NNN-traço").
    if (/^\d{3} /.test(line) || /^\d{3}$/.test(line)) {
      const { resolve } = this.reply
      this.reply = null
      resolve({ code: Number(line.slice(0, 3)), lines: this.replyLines })
    }
  }

  fail (error) {
    if (!this.error) this.error = error
    this.socket?.destroy()
    if (this.reply) {
      const { reject } = this.reply
      this.reply = null
      reject(this.error)
    }
  }

  readReply () {
    if (this.error) return Promise.reject(this.error)
    if (this.reply) return this.reply.promise
    this.replyLines = []
    let resolve
    let reject
    const promise = new Promise((res, rej) => { resolve = res; reject = rej })
    this.reply = { promise, resolve, reject }
    return promise
  }

  // `label` existe para NUNCA ecoar o texto enviado: as linhas de AUTH LOGIN
  // sao o usuario e a senha em base64, e a mensagem de erro daqui termina em
  // console.warn no servidor. Rotulo fixo em vez do payload.
  command (text, expected, label = text.split(' ')[0]) {
    const pending = this.readReply()
    this.socket.write(text + '\r\n')
    return pending.then(reply => {
      if (expected && !expected.includes(reply.code)) {
        throw new Error(`SMTP ${label}: esperado ${expected.join('/')}, recebido ${reply.lines.join(' | ')}`)
      }
      return reply
    })
  }

  // Validacao do certificado LIGADA por padrao. Antes era `rejectUnauthorized:
  // false` fixo, o que aceitava em silencio qualquer certificado — inclusive o
  // de um man-in-the-middle entre este servidor e o provedor de e-mail, que
  // veria a senha de aplicativo do AUTH LOGIN. So desliga com
  // `allow_invalid_cert` gravado no config, e o painel mostra o aviso.
  tlsOptions (extra) {
    return tlsOptionsFor(this.config, extra)
  }

  connect () {
    const { config } = this
    return new Promise((resolveConnect, rejectConnect) => {
      const base = { host: config.host, port: Number(config.port) || 587 }
      const socket = config.secure
        ? tls.connect(this.tlsOptions(base))
        : net.connect(base)
      socket.once('error', rejectConnect)
      socket.once(config.secure ? 'secureConnect' : 'connect', () => resolveConnect(socket))
    })
  }

  starttls () {
    const raw = this.socket
    raw.removeAllListeners('data')
    return new Promise((resolveTls, rejectTls) => {
      const secure = tls.connect(this.tlsOptions({ socket: raw }))
      secure.once('secureConnect', () => {
        this.attach(secure)
        resolveTls(secure)
      })
      secure.once('error', rejectTls)
    })
  }
}

function rfc2047 (value) {
  return /^[\x20-\x7e]*$/.test(value) ? value : `=?UTF-8?B?${Buffer.from(value, 'utf8').toString('base64')}?=`
}

// Loopback: a conexao nunca deixa a maquina, entao AUTH em texto claro aqui
// nao expoe credencial a ninguem. E o caso do SMTP falso da suite de testes.
function isLoopback (host) {
  const value = String(host || '').trim().toLowerCase().replace(/^\[|\]$/g, '')
  return value === 'localhost' || value === '::1' || /^127\./.test(value)
}

function envelopeFrom (config) {
  return String(config.from).replace(/[<>\r\n]/g, '')
}

function buildMessage (config, { to, subject, text }) {
  const from = envelopeFrom(config)
  const headers = [
    config.from_name ? `From: ${rfc2047(config.from_name)} <${from}>` : `From: <${from}>`,
    `To: <${to}>`,
    `Subject: ${rfc2047(subject)}`,
    `Date: ${new Date().toUTCString()}`,
    `Message-ID: <${randomBytes(12).toString('hex')}@revival.local>`,
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset=UTF-8',
    'Content-Transfer-Encoding: 8bit'
  ]
  const body = String(text || '').replace(/\r?\n/g, '\r\n').split('\r\n')
    .map(line => (line.startsWith('.') ? `.${line}` : line))
    .join('\r\n')
  return `${headers.join('\r\n')}\r\n\r\n${body}\r\n.\r\n`
}

export async function sendMail (config, message) {
  if (!smtpConfigured(config)) throw new Error('SMTP não configurado')
  if (!message?.to || !String(message.to).includes('@')) throw new Error('destinatário inválido')
  const session = new SmtpSession(config)
  const ehloName = 'revival.local'
  let socket = await session.connect()
  session.attach(socket)
  try {
    const greeting = await session.readReply()
    if (greeting.code !== 220) throw new Error(`saudação SMTP inesperada: ${greeting.lines.join(' | ')}`)
    let ehlo = await session.command(`EHLO ${ehloName}`, [250])
    let secured = Boolean(config.secure)
    if (!config.secure && ehlo.lines.some(line => /^250[- ]STARTTLS\b/i.test(line))) {
      await session.command('STARTTLS', [220])
      socket = await session.starttls()
      secured = true
      ehlo = await session.command(`EHLO ${ehloName}`, [250])
    }
    if (config.user) {
      // AUTH LOGIN manda usuario e senha em base64 — que e codificacao, nao
      // cifra. Sem TLS a credencial trafega legivel. Loopback nunca sai desta
      // maquina e continua liberado; qualquer outro host exige TLS ou o
      // opt-in explicito `allow_plaintext_auth`.
      if (!plaintextAuthAllowed(config, secured)) {
        throw new Error('o servidor SMTP nao ofereceu STARTTLS: enviar AUTH LOGIN em texto claro exporia a senha de aplicativo')
      }
      await session.command('AUTH LOGIN', [334])
      await session.command(Buffer.from(String(config.user), 'utf8').toString('base64'), [334], 'AUTH usuario')
      await session.command(Buffer.from(String(config.pass || ''), 'utf8').toString('base64'), [235], 'AUTH senha')
    }
    await session.command(`MAIL FROM:<${envelopeFrom(config)}>`, [250])
    await session.command(`RCPT TO:<${message.to}>`, [250, 251])
    await session.command('DATA', [354])
    await new Promise((resolveWrite, rejectWrite) => {
      socket.write(buildMessage(config, message), error => (error ? rejectWrite(error) : resolveWrite()))
    })
    const accepted = await session.readReply()
    if (accepted.code !== 250) throw new Error(`mensagem rejeitada: ${accepted.lines.join(' | ')}`)
    try { await session.command('QUIT', [221]) } catch { /* servidor pode fechar antes */ }
    return true
  } finally {
    socket.destroy()
  }
}
