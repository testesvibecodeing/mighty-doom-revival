import { existsSync, readFileSync, writeFileSync, mkdirSync, unlinkSync } from 'node:fs'
import { randomBytes } from 'node:crypto'
import { dirname } from 'node:path'

import { classifyResource, giveGameResource } from './game-data-model.js'
import { resolveResource } from './config.js'
import { panelResourceByRef, panelResourceInfo } from './assets.js'

// Kinds aceitos numa concessão explícita de recurso (giveGameResource).
const GRANT_KINDS = new Set(['currency', 'energy', 'cosmetic', 'entitlement', 'weapon', 'equipment', 'launcher', 'ultimate', 'slayer'])

// Super Admin do painel web (/slayer) e API de administração em
// /account/admin/*.
//
// Fluxo das credenciais: scripts/install.sh gera e-mail + senha e grava
// runtime/admin-credentials.json; o servidor consome esse arquivo no boot
// (aplica uma única vez e apaga, para não sobrescrever senhas trocadas
// depois pelo painel). Sem arquivo, gera uma senha e imprime no console.
// REVIVAL_ADMIN_EMAIL/REVIVAL_ADMIN_PASSWORD no env sempre têm prioridade
// e são reaplicados a cada boot (override explícito do operador).
//
// Recuperação de acesso: install.sh também grava
// runtime/admin-recover-token.json com 10 minutos de validade e imprime o
// link /admin-recover/<token>. A página permite trocar e-mail e senha do
// Super Admin; ao concluir a troca o token é revogado na hora (arquivo
// apagado) — link de uso único.

const DEFAULT_ADMIN_EMAIL = 'admin@revival.local'
const RECOVER_TOKEN_TTL = 600 // 10 minutos

function nowSeconds () {
  return Math.floor(Date.now() / 1000)
}

function json (res, status, payload) {
  const body = JSON.stringify(payload)
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(body),
    'cache-control': 'no-store'
  })
  res.end(body)
  return true
}

export function ensureSuperAdmin ({ repo, credentialsFile }) {
  const envEmail = String(process.env.REVIVAL_ADMIN_EMAIL || '').trim().toLowerCase()
  const envPassword = typeof process.env.REVIVAL_ADMIN_PASSWORD === 'string' && process.env.REVIVAL_ADMIN_PASSWORD
    ? process.env.REVIVAL_ADMIN_PASSWORD
    : null

  // Credenciais geradas pelo instalador: aplicadas uma única vez.
  let installerEmail = null
  let installerPassword = null
  if (existsSync(credentialsFile)) {
    try {
      const stored = JSON.parse(readFileSync(credentialsFile, 'utf8'))
      if (typeof stored?.email === 'string' && stored.email) installerEmail = stored.email.trim().toLowerCase()
      if (typeof stored?.password === 'string' && stored.password) installerPassword = stored.password
    } catch {}
  }

  const email = envEmail || installerEmail || DEFAULT_ADMIN_EMAIL
  const existing = repo.userByLogin(email)

  if (!existing) {
    const password = envPassword || installerPassword || randomBytes(12).toString('base64url')
    const generated = !envPassword && !installerPassword
    repo.createUser({ email, displayName: 'Super Admin', password, isAdmin: true })
    console.log(`[SUPER ADMIN] criado: ${email}`)
    if (generated) console.log(`[SUPER ADMIN] senha gerada: ${password}`)
  } else {
    if (!existing.is_admin) repo.setAdminFlag(existing.id, true)
    if (envPassword) {
      repo.updatePassword(existing.id, envPassword)
      repo.revokeUserSessions(existing.id)
      console.log(`[SUPER ADMIN] senha reaplicada do env REVIVAL_ADMIN_PASSWORD (${email})`)
    } else if (installerPassword) {
      repo.updatePassword(existing.id, installerPassword)
      repo.revokeUserSessions(existing.id)
      console.log(`[SUPER ADMIN] senha atualizada com as credenciais do instalador (${email})`)
    }
  }

  if (installerEmail || installerPassword) {
    try {
      unlinkSync(credentialsFile)
    } catch {}
  }

  return { email }
}

// --- link temporário de recuperação do acesso do Super Admin ---

function readRecoverToken (tokenFile) {
  try {
    const stored = JSON.parse(readFileSync(tokenFile, 'utf8'))
    if (typeof stored?.token !== 'string' || !stored.token) return null
    if (!Number.isFinite(stored?.expires_at) || stored.expires_at <= 0) return null
    return { token: stored.token, expiresAt: Math.floor(stored.expires_at) }
  } catch {
    return null
  }
}

function revokeRecoverToken (tokenFile) {
  try {
    unlinkSync(tokenFile)
  } catch {}
}

function recoverPageHtml (token, expiresAt) {
  const expiresJson = JSON.stringify(expiresAt)
  return `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Recuperar acesso - Mighty DOOM Revival</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;background:radial-gradient(circle at 50% -20%,#2a0c04 0%,#0b0403 55%,#050201 100%);color:#f1e8db;font:16px/1.6 Rajdhani,system-ui,sans-serif}
.card{width:min(560px,100%);padding:32px 28px;border:1px solid rgba(255,93,21,.4);background:linear-gradient(160deg,rgba(30,16,10,.96),rgba(9,6,5,.97));box-shadow:0 30px 80px rgba(0,0,0,.55);clip-path:polygon(3% 0,97% 0,100% 12%,100% 88%,97% 100%,3% 100%,0 88%,0 12%)}
h1{margin:0 0 6px;font:400 clamp(22px,4.5vw,30px)/1.15 'Black Ops One',Rajdhani,sans-serif;letter-spacing:.02em;color:#ff8414;text-transform:uppercase}
.sub{margin:0 0 20px;color:#a59688;text-transform:uppercase;letter-spacing:.18em;font-size:12px;font-weight:700}
label{display:grid;gap:6px;margin-bottom:14px;color:#cbbdb0;font-size:14px;font-weight:600}
input{width:100%;border:1px solid rgba(255,255,255,.13);background:rgba(0,0,0,.28);color:#f1e8db;padding:13px 14px;outline:none;font:inherit}
input:focus{border-color:#ff791c;box-shadow:0 0 0 3px rgba(255,100,30,.1)}
button{width:100%;margin-top:8px;padding:13px 17px;border:1px solid #ff791c;background:linear-gradient(180deg,#c43a16,#711308);color:#fff;font:700 16px Rajdhani,sans-serif;cursor:pointer}
button:hover{filter:brightness(1.15)}
.status{min-height:22px;margin:14px 0 0;color:#ff9b59;font-weight:600}
.status.ok{color:#55e878}
.meta{margin:14px 0 0;color:#8f867c;font-size:13px}
a{color:#ffb12a}
</style>
</head>
<body>
<main class="card">
<h1>Recuperar acesso</h1>
<p class="sub">Super Admin // link tempor&aacute;rio</p>
<form id="form">
<label>Novo e-mail<input name="email" type="email" autocomplete="username" required placeholder="admin@seudominio.com"></label>
<label>Nova senha<input name="password" type="password" minlength="8" autocomplete="new-password" required placeholder="M&iacute;nimo de 8 caracteres"></label>
<label>Repetir a senha<input name="confirm" type="password" minlength="8" autocomplete="new-password" required></label>
<button type="submit">Trocar dados de acesso</button>
<p class="status" id="status" role="status"></p>
</form>
<p class="meta">Expira em <b id="countdown">--</b>. Ap&oacute;s a troca este link &eacute; revogado na hora e todas as sess&otilde;es do painel s&atilde;o encerradas.</p>
<p class="meta"><a href="/account">Ir para o login</a></p>
</main>
<script>
(function(){
var expires=${expiresJson};
var cd=document.getElementById('countdown'),form=document.getElementById('form'),status=document.getElementById('status');
function tick(){var s=expires-Math.floor(Date.now()/1000);
if(s<=0){cd.textContent='expirado';form.style.display='none';status.textContent='Link expirado. Rode novamente ./scripts/install.sh na VPS para gerar um novo.';status.className='status';return}
var m=Math.floor(s/60),x=s%60;cd.textContent=(m<10?'0':'')+m+':'+(x<10?'0':'')+x;setTimeout(tick,1000)}
tick();
form.addEventListener('submit',function(ev){
ev.preventDefault();
var data=Object.fromEntries(new FormData(form).entries());
if(data.password!==data.confirm){status.textContent='As senhas n\\u00e3o conferem.';status.className='status';return}
status.textContent='Trocando...';
fetch('/admin-recover/${token}',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({email:data.email,password:data.password})})
.then(function(r){return r.json().then(function(b){return {ok:r.ok,body:b}})})
.then(function(r){
if(r.ok){status.textContent='Acesso atualizado! Fa\\u00e7a login com os novos dados.';status.className='status ok';form.style.display='none';setTimeout(function(){location.href='/account'},1600)}
else{status.textContent=r.body.error||'N\\u00e3o foi poss\\u00edvel concluir.';status.className='status'}
})
.catch(function(){status.textContent='Erro de rede.';status.className='status'});
});
})();
</script>
</body>
</html>`
}

// GET serve a página; POST troca e-mail/senha do Super Admin e revoga o
// link. Token errado responde igual a inexistente (não confirma existência).
export async function handleAdminRecover (req, res, path, { repo, tokenFile }) {
  const match = /^\/admin-recover\/([A-Za-z0-9]+)$/.exec(path)
  if (!match) return false

  const stored = readRecoverToken(tokenFile)
  if (!stored || stored.token !== match[1]) {
    res.writeHead(410, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store', 'x-robots-tag': 'noindex, nofollow' })
    res.end('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Link indispon&iacute;vel</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0403;color:#f1e8db;font:16px/1.6 Rajdhani,system-ui,sans-serif;text-align:center;padding:24px}b{color:#ff8414}</style></head><body><p>Link de recupera&ccedil;&atilde;o <b>inv&aacute;lido ou j&aacute; usado</b>.<br>Rode <b>sudo ./scripts/install.sh</b> na VPS para gerar um novo.</p></body></html>')
    return true
  }
  if (nowSeconds() >= stored.expiresAt) {
    revokeRecoverToken(tokenFile)
    res.writeHead(410, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store', 'x-robots-tag': 'noindex, nofollow' })
    res.end('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Link expirado</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0403;color:#f1e8db;font:16px/1.6 Rajdhani,system-ui,sans-serif;text-align:center;padding:24px}b{color:#ff8414}</style></head><body><p>Link de recupera&ccedil;&atilde;o <b>expirou</b> (validade de 10 minutos).<br>Rode <b>sudo ./scripts/install.sh</b> na VPS para gerar um novo.</p></body></html>')
    return true
  }

  if (req.method === 'GET' || req.method === 'HEAD') {
    const body = recoverPageHtml(match[1], stored.expiresAt)
    res.writeHead(200, {
      'content-type': 'text/html; charset=utf-8',
      'content-length': Buffer.byteLength(body),
      'cache-control': 'no-store',
      'x-robots-tag': 'noindex, nofollow'
    })
    res.end(req.method === 'HEAD' ? undefined : body)
    return true
  }

  if (req.method !== 'POST') return json(res, 405, { ok: false, error: 'method-not-allowed' })

  let body = {}
  try {
    const chunks = []
    for await (const chunk of req) chunks.push(chunk)
    body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : {}
  } catch {
    return json(res, 400, { ok: false, error: 'invalid-json' })
  }

  const email = String(body.email || '').trim().toLowerCase()
  const password = body.password
  if (!email.includes('@') || typeof password !== 'string' || password.length < 8 || password.length > 128) {
    return json(res, 400, { ok: false, error: 'E-mail ou senha inválidos (senha mínima de 8 caracteres).' })
  }

  const current = repo.listUsers('', 500).find(x => x.is_admin)
  const collision = repo.userByLogin(email)
  if (collision && (!current || collision.id !== current.id)) {
    return json(res, 409, { ok: false, error: 'Já existe uma conta com este e-mail.' })
  }

  if (current) {
    repo.updateProfile(current.id, { email, displayName: 'Super Admin' })
    repo.updatePassword(current.id, password)
    repo.revokeUserSessions(current.id)
  } else {
    repo.createUser({ email, displayName: 'Super Admin', password, isAdmin: true })
  }

  revokeRecoverToken(tokenFile)
  console.log(`[SUPER ADMIN] dados de acesso trocados via link de recuperação: ${email}`)
  return json(res, 200, { ok: true, message: 'Acesso atualizado. Faça login com os novos dados.' })
}

// --- API de administração (requer sessão de um admin) ---

function eventStatus (event, now) {
  if (event.active === false) return 'inactive'
  if (event.always === true) return 'always'
  const start = event.start_time ? Date.parse(event.start_time) / 1000 : null
  const end = event.end_time ? Date.parse(event.end_time) / 1000 : null
  if (start && now < start) return 'scheduled'
  if (end && now > end) return 'ended'
  return 'running'
}

export function publicPack (pack, runtime) {
  // Preview por entrada: um recurso que ainda não resolve para rid (game-data
  // ausente nesta instância) continua exibindo nome/ícone via tag canônica,
  // em vez de derrubar o preview do pacote inteiro.
  const entryView = (entry, kindHint) => {
    const ref = entry.resource ?? entry.rid
    let rid = null
    try {
      rid = resolveResource(ref, runtime)
    } catch {
      rid = null
    }
    const info = rid !== null
      ? panelResourceInfo(rid, runtime, kindHint)
      : panelResourceByRef(String(ref), runtime, kindHint)
    return { rid, name: info.name, icon: info.icon, kind: info.kind, amount: Number(entry.amount || 0) }
  }
  const preview = {
    cost: (pack.cost || []).map(entry => entryView(entry, 'currency')),
    contents: (pack.contents || []).map(entry => entryView(entry, null))
  }
  return { ...pack, preview }
}

// Referência de recurso válida para config de pack: número (rid) ou string
// (tag). Sem game-data a tag fica pendente de resolução — o jogo resolve
// quando o game-data estiver carregado; o painel já exibe nome/ícone dela.
function packRef (entry) {
  const ref = entry.resource ?? entry.rid
  if (Number.isInteger(ref)) return ref
  if (typeof ref === 'string' && ref.trim()) return ref.trim().slice(0, 96)
  if (ref && typeof ref === 'object' && (Number.isInteger(ref.rid) || Number.isInteger(ref.id))) return Number(ref.rid ?? ref.id)
  throw new Error('Recurso inválido no pacote')
}

function refRid (ref, runtime) {
  try {
    return resolveResource(ref, runtime)
  } catch {
    return null
  }
}

function sanitizeCost (input, runtime) {
  if (!Array.isArray(input)) return []
  return input.map(entry => {
    const ref = packRef(entry)
    const rid = refRid(ref, runtime)
    const amount = Math.floor(Number(entry.amount))
    if (!Number.isFinite(amount) || amount < 0) throw new Error('Valor de custo inválido')
    // 'unknown' = sem game-data para classificar (tag pendente); só bloqueia
    // quando sabe com certeza que o recurso não é uma moeda.
    const kind = rid !== null ? classifyResource(rid, runtime, entry.kind) : 'unknown'
    if (kind !== 'currency' && kind !== 'unknown') throw new Error(`O recurso não é uma moeda (rid=${rid})`)
    return { resource: ref, kind: 'currency', amount }
  })
}

function sanitizeContents (input, runtime) {
  if (!Array.isArray(input)) return []
  return input.map(entry => {
    const ref = packRef(entry)
    const rid = refRid(ref, runtime)
    const amount = Math.floor(Number(entry.amount ?? 1))
    if (!Number.isFinite(amount) || amount <= 0) throw new Error('Quantidade inválida')
    const kind = entry.kind || (rid !== null ? classifyResource(rid, runtime) : 'unknown')
    const row = { resource: ref, kind, amount }
    if (entry.level !== undefined) row.level = Math.max(1, Math.floor(Number(entry.level) || 1))
    if (entry.tier !== undefined) row.tier = Math.floor(Number(entry.tier) || 0)
    return row
  })
}

// Monta o pacote final a partir do que veio do painel. Preço real/IAP
// continua bloqueado: o Revival só negocia com moedas do jogo.
function sanitizePack (input, base = {}) {
  if (input.real_money || input.iap || input.price) throw new Error('Pacote com preço real é bloqueado pelo Revival')
  return {
    id: Math.floor(Number(input.id ?? base.id)),
    tag: String(input.tag ?? base.tag ?? `revival_pack_${input.id ?? base.id}`).slice(0, 64),
    active: input.active !== undefined ? input.active !== false : base.active !== false,
    display_type: Math.floor(Number(input.display_type ?? base.display_type ?? 0)) || 0,
    priority: Math.floor(Number(input.priority ?? base.priority ?? 0)) || 0,
    cost: input.cost !== undefined ? input.cost : (base.cost || []),
    contents: input.contents !== undefined ? input.contents : (base.contents || []),
    quota: base.quota ?? null
  }
}

function sanitizeEvent (input, base = {}) {
  const id = Math.floor(Number(input.id ?? base.id))
  const event = {
    id,
    event_definition_id: Math.floor(Number(input.event_definition_id ?? base.event_definition_id ?? id)),
    active: input.active !== undefined ? input.active !== false : base.active !== false,
    always: input.always !== undefined ? input.always === true : base.always === true,
    availability: Math.max(0, Math.floor(Number(input.availability ?? base.availability ?? 1)) || 1),
    channel: input.channel ?? base.channel ?? 'game_mode',
    args: base.args && input.args === undefined ? base.args : (input.args && typeof input.args === 'object' && !Array.isArray(input.args) ? input.args : {}),
    progress_template: base.progress_template || { event_id: id }
  }
  if (input.tag !== undefined || base.tag !== undefined) event.tag = String(input.tag ?? base.tag).slice(0, 64)
  for (const field of ['start_time', 'end_time']) {
    if (input[field] !== undefined) {
      if (input[field] === null || input[field] === '') continue
      const parsed = Date.parse(String(input[field]))
      if (Number.isNaN(parsed)) throw new Error(`Data inválida: ${input[field]}`)
      event[field] = input[field]
    } else if (base[field] !== undefined) {
      event[field] = base[field]
    }
  }
  event.progress_template.event_id = event.id
  return event
}

function saveConfig (path, key, value) {
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, JSON.stringify({ [key]: value }, null, 2))
}

// Whitelist do que o painel pode mudar no site público. O título aceita
// <br>, então removemos script/on* para não virar vetor de XSS por acidente.
const SITE_TEXTS = { hero_title: 200, hero_description: 800, github_url: 300 }
const SITE_FLAGS = ['show_github', 'show_status', 'show_features', 'show_download', 'show_faq']

function sanitizeSite (input, base) {
  const next = { ...base }
  for (const [key, limit] of Object.entries(SITE_TEXTS)) {
    if (typeof input?.[key] === 'string') {
      next[key] = input[key].replace(/<\s*\/?\s*script[^>]*>/gi, '').replace(/\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '').trim().slice(0, limit)
    }
  }
  for (const flag of SITE_FLAGS) {
    if (typeof input?.[flag] === 'boolean') next[flag] = input[flag]
  }
  if (typeof next.github_url === 'string' && next.github_url && !/^https?:\/\//i.test(next.github_url)) {
    throw new Error('A URL do GitHub precisa começar com http:// ou https://')
  }
  return next
}

export function handleAdminApi (req, res, path, body, { repo, runtime, reloadRuntime, site, user }) {
  const route = path.replace(/^\/account\/admin\/?/, '')

  // --- visão geral do servidor ---
  if (route === 'overview') {
    const now = nowSeconds()
    const users = repo.listUsers('', 500)
    return json(res, 200, {
      ok: true,
      overview: {
        server_name: runtime.revival.server_name,
        players: repo.countUsers(),
        admins: users.filter(x => x.is_admin).length,
        packs_total: runtime.packs.length,
        packs_active: runtime.packs.filter(x => x.active !== false).length,
        events_total: runtime.events.length,
        events_active: runtime.events.filter(x => ['running', 'always'].includes(eventStatus(x, now))).length,
        notifications: repo.listNotifications(100).length,
        game_data_loaded: Boolean(runtime.gameData),
        uptime_seconds: Math.floor(process.uptime()),
        apk: site.apkInfo()
      }
    })
  }

  // --- usuários: buscar, resetar senha, recovery, promover, conceder item ---
  let match = /^users\/(\d+)\/([a-z-]+)$/.exec(route)
  if (match) {
    const userId = Number(match[1])
    const target = repo.userById(userId)
    if (!target) return json(res, 404, { ok: false, error: 'user-not-found' })

    if (match[2] === 'reset-password') {
      const password = passwordIsValid(body.new_password) ? body.new_password : randomBytes(9).toString('base64url')
      repo.updatePassword(userId, password)
      repo.revokeUserSessions(userId)
      return json(res, 200, { ok: true, password, message: 'Senha redefinida; sessões ativas foram encerradas.' })
    }
    if (match[2] === 'recovery-code') {
      return json(res, 200, { ok: true, recovery_code: repo.resetRecoveryCode(userId) })
    }
    if (match[2] === 'grant') {
      try {
        // Sem game-data o catálogo não classifica o rid: kind explícito da lista,
        // ou fallback para carteira (moeda) — a concessão mais comum do painel.
        const explicitKind = GRANT_KINDS.has(body.kind) ? body.kind : null
        const rid = resolveResource(body.resource ?? body.rid, runtime)
        const kind = explicitKind || (classifyResource(rid, runtime) === 'unknown' ? 'currency' : null)
        const grant = giveGameResource(repo, userId, { resource: rid, amount: body.amount, level: body.level, kind }, runtime)
        return json(res, 200, { ok: true, grant })
      } catch (error) {
        return json(res, 400, { ok: false, error: error.message })
      }
    }
    if (match[2] === 'admin') {
      if (target.id === user.id) return json(res, 400, { ok: false, error: 'cannot-change-own-role' })
      repo.setAdminFlag(userId, body.is_admin === true)
      return json(res, 200, { ok: true, account: { id: userId, is_admin: body.is_admin === true } })
    }
    return json(res, 404, { ok: false, error: 'unknown-action' })
  }

  match = /^users\/(\d+)$/.exec(route)
  if (match) {
    const userId = Number(match[1])
    if (req.method !== 'DELETE') return json(res, 405, { ok: false, error: 'method-not-allowed' })
    if (userId === user.id) return json(res, 400, { ok: false, error: 'cannot-delete-self' })
    if (!repo.deleteUser(userId)) return json(res, 400, { ok: false, error: 'admin-cannot-be-deleted' })
    return json(res, 200, { ok: true })
  }

  if (route === 'users' || route === 'users/') {
    const url = new URL(req.url || '/', 'http://localhost')
    const query = String(url.searchParams.get('query') || body?.query || '')
    return json(res, 200, { ok: true, users: repo.listUsers(query) })
  }

  // --- catálogo de recursos (inclui itens exclusivos de evento) ---
  if (route === 'resources' || route === 'resources/') {
    const url = new URL(req.url || '/', 'http://localhost')
    const query = String(url.searchParams.get('query') || body?.query || '').toLowerCase()
    const results = []
    for (const [rid, definition] of runtime.index.byId) {
      const tag = typeof definition.tag === 'string' ? definition.tag : ''
      const name = String(definition.display_name || definition.name || definition.key || '')
      if (query && !tag.toLowerCase().includes(query) && !name.toLowerCase().includes(query) && String(rid) !== query) continue
      results.push({ rid, tag, name, kind: classifyResource(rid, runtime) })
      if (results.length >= 60) break
    }
    results.sort((a, b) => a.rid - b.rid)
    return json(res, 200, { ok: true, resources: results })
  }

  // --- pacotes da loja: preços, conteúdos, ativação ---
  match = /^packs(\/(\d+))?$/.exec(route)
  if (match) {
    const packs = runtime.packs
    if (!match[2]) {
      if (req.method === 'POST') {
        const nextId = packs.reduce((max, x) => Math.max(max, Number(x.id) || 0), 900000) + 1
        let pack
        try {
          pack = sanitizePack({ ...body, id: nextId }, {})
          if (body.cost !== undefined) pack.cost = sanitizeCost(body.cost, runtime)
          if (body.contents !== undefined) pack.contents = sanitizeContents(body.contents, runtime)
        } catch (error) {
          return json(res, 400, { ok: false, error: error.message })
        }
        const next = [...packs, pack]
        saveConfig(runtime.paths.packsPath, 'packs', next)
        reloadRuntime()
        return json(res, 201, { ok: true, pack: publicPack(pack, runtime) })
      }
      return json(res, 200, { ok: true, packs: packs.map(x => publicPack(x, runtime)) })
    }

    const packId = Number(match[2])
    const index = packs.findIndex(x => Number(x.id) === packId)
    if (index === -1) return json(res, 404, { ok: false, error: 'pack-not-found' })

    if (req.method === 'DELETE') {
      saveConfig(runtime.paths.packsPath, 'packs', packs.filter((_, i) => i !== index))
      reloadRuntime()
      return json(res, 200, { ok: true })
    }

    let pack
    try {
      pack = sanitizePack(body, packs[index])
      if (body.cost !== undefined) pack.cost = sanitizeCost(body.cost, runtime)
      if (body.contents !== undefined) pack.contents = sanitizeContents(body.contents, runtime)
    } catch (error) {
      return json(res, 400, { ok: false, error: error.message })
    }
    const next = [...packs]
    next[index] = pack
    saveConfig(runtime.paths.packsPath, 'packs', next)
    reloadRuntime()
    return json(res, 200, { ok: true, pack: publicPack(pack, runtime) })
  }

  // --- eventos: ativar, reagendar, criar ---
  match = /^events(\/(\d+))?$/.exec(route)
  if (match) {
    const events = runtime.events
    if (!match[2]) {
      if (req.method === 'POST') {
        const nextId = events.reduce((max, x) => Math.max(max, Number(x.id) || 0), 990000) + 1
        let event
        try {
          event = sanitizeEvent({ ...body, id: nextId }, {})
        } catch (error) {
          return json(res, 400, { ok: false, error: error.message })
        }
        saveConfig(runtime.paths.eventsPath, 'events', [...events, event])
        reloadRuntime()
        return json(res, 201, { ok: true, event })
      }
      const now = nowSeconds()
      return json(res, 200, { ok: true, events: events.map(x => ({ ...x, status: eventStatus(x, now) })) })
    }

    const eventId = Number(match[2])
    const index = events.findIndex(x => Number(x.id) === eventId)
    if (index === -1) return json(res, 404, { ok: false, error: 'event-not-found' })

    if (req.method === 'DELETE') {
      saveConfig(runtime.paths.eventsPath, 'events', events.filter((_, i) => i !== index))
      reloadRuntime()
      return json(res, 200, { ok: true })
    }

    let event
    try {
      event = sanitizeEvent(body, events[index])
    } catch (error) {
      return json(res, 400, { ok: false, error: error.message })
    }
    const next = [...events]
    next[index] = event
    saveConfig(runtime.paths.eventsPath, 'events', next)
    reloadRuntime()
    return json(res, 200, { ok: true, event })
  }

  // --- personalização do site público (textos, GitHub, seções) ---
  if (route === 'site' || route === 'site/') {
    if (req.method === 'PATCH' || req.method === 'POST') {
      let next
      try {
        next = sanitizeSite(body, runtime.site)
      } catch (error) {
        return json(res, 400, { ok: false, error: error.message })
      }
      mkdirSync(dirname(runtime.paths.sitePath), { recursive: true })
      writeFileSync(runtime.paths.sitePath, JSON.stringify(next, null, 2))
      reloadRuntime()
      return json(res, 200, { ok: true, site: reloadRuntime().site })
    }
    return json(res, 200, { ok: true, site: runtime.site })
  }

  // --- avisos/notificações (ex.: novo APK para atualizar) ---
  match = /^notifications(\/(\d+))?$/.exec(route)
  if (match) {
    if (!match[2]) {
      if (req.method === 'POST') {
        const title = String(body.title || '').trim()
        if (!title) return json(res, 400, { ok: false, error: 'title-required' })
        const kind = ['info', 'update', 'event', 'warning'].includes(body.kind) ? body.kind : 'info'
        return json(res, 201, { ok: true, notification: repo.createNotification({ title, body: String(body.body || ''), kind, createdBy: user.id }) })
      }
      return json(res, 200, { ok: true, notifications: repo.listNotifications(100) })
    }
    if (req.method === 'DELETE') {
      if (!repo.deleteNotification(Number(match[2]))) return json(res, 404, { ok: false, error: 'not-found' })
      return json(res, 200, { ok: true })
    }
  }

  return json(res, 404, { ok: false, error: 'not-found' })
}

function passwordIsValid (value) {
  return typeof value === 'string' && value.length >= 8 && value.length <= 128
}
