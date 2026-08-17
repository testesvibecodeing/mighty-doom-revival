// app.js - dados reais do Revival Server + interações do site.
//
// Busca /revival/health e /revival/apk no mesmo domínio (configurável via
// window.MD_CONFIG) a cada 30s e povoa: chip de status do topo, conexão do
// hero, fichas de dados ao vivo, terminal com valores reais e o estado do
// botão de download do APK. Cada resposta online dispara "revival:online",
// que faz o fundo three.js respirar mais forte.

import { startHellScene } from './hell-scene.js'

const cfg = window.MD_CONFIG || {}
const $ = s => document.querySelector(s)
const $$ = s => [...document.querySelectorAll(s)]

const ORIGIN = (cfg.serverUrl || '').replace(/\/+$/, '') || location.origin
const HEALTH_URL = cfg.healthUrl || `${ORIGIN}/revival/health`
const APK_INFO_URL = cfg.apkInfoUrl || `${ORIGIN}/revival/apk`

const state = { health: null, apk: null, latencyMs: null, online: false, lastTick: null }

function toast (msg) {
  $('#toastMsg').textContent = msg
  $('#toast').classList.add('show')
  clearTimeout(window.__toastTimer)
  window.__toastTimer = setTimeout(() => $('#toast').classList.remove('show'), 3200)
}

function fmtBytes (bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(value >= 100 || unit === 0 ? 0 : 1)} ${units[unit]}`
}

function fmtUptime (seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '--'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  const pad = n => String(n).padStart(2, '0')
  return d > 0 ? `${d}d ${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(h)}:${pad(m)}:${pad(s)}`
}

function fmtDate (epochSeconds) {
  if (!Number.isFinite(epochSeconds) || epochSeconds <= 0) return '--'
  return new Date(epochSeconds * 1000).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
}

function uptimeBase () {
  if (!state.health || !Number.isFinite(state.health.uptime_seconds)) return null
  const elapsed = state.lastTick ? Math.floor((Date.now() - state.lastTick) / 1000) : 0
  return state.health.uptime_seconds + elapsed
}

// Relógio local de uptime/latência (atualiza 1x/s sem refazer o fetch).
function tickClock () {
  const up = uptimeBase()
  if (up !== null) {
    const el = $('#statusUptime')
    if (el) el.textContent = `up ${fmtUptime(up)}`
    const tile = $('#tileUptime')
    if (tile) tile.textContent = fmtUptime(up)
  }
}

function setStatsTile (id, value, cls = '') {
  const el = $(`#${id}`)
  if (!el) return
  el.textContent = value
  el.className = `stat-value${cls ? ` ${cls}` : ''}`
}

function renderTerminal () {
  const log = $('#terminalLog')
  if (!log) return
  if (!state.online || !state.health) {
    log.textContent = [
      '[BOOT] Revival frontend iniciado',
      `[SERVER] ${HEALTH_URL}`,
      state.health ? `[STATUS] OFFLINE (última resposta válida registrada)` : '[STATUS] AGUARDANDO RESPOSTA',
      '[ERROR] sem contato com o servidor - o jogo não conectaria agora'
    ].join('\n')
    return
  }
  const h = state.health
  const apk = state.apk
  const lines = [
    '[BOOT] Revival frontend iniciado',
    `[SERVER] ${h.server || 'Revival Server'}`,
    `[STATUS] ONLINE (${state.latencyMs ?? '--'}ms) · up ${fmtUptime(uptimeBase())}`,
    `[CLIENT] client_version=${h.client_version || '--'} · api_version=${h.api_version || '--'}`,
    `[GAMEDATA] ${h.game_data_loaded ? 'loaded' : 'PENDENTE (server/data/game-data.json)'}`,
    `[PLAYERS] ${Number.isFinite(h.players) ? h.players : '--'} Slayer(s) registrados`,
    `[PACKS] ${h.packs ?? '--'} pacotes ativos · [EVENTS] ${h.events ?? '--'} eventos ativos`,
    `[APK] ${apk?.available ? `publicado (${fmtBytes(apk.size)} · sha256 ${(apk.sha256 || '').slice(0, 16)}…)` : 'aguardando upload pelo link temporário do install.sh'}`,
    `[STORE] real-money: disabled · iap: disabled`,
    `[MODE] ${h.research_mode ? 'research' : 'preservation'} / self-hosted`
  ]
  log.textContent = lines.join('\n')
}

function renderApkButtons () {
  const apk = state.apk
  const btn = $('#downloadBtn')
  const top = $('#apkTop')
  const specSize = $('#specSize')
  const apkSub = $('#apkSubLabel')

  if (apk && apk.available) {
    const label = `Baixar APK (${fmtBytes(apk.size)})`
    for (const b of [btn, top]) {
      if (!b) continue
      b.href = apk.url
      b.classList.remove('disabled')
      b.onclick = null
    }
    if (btn) btn.querySelector('strong').textContent = label
    if (top) top.innerHTML = `<i class="fa-solid fa-download"></i><span>${label}</span>`
    if (apkSub) apkSub.textContent = `sha256 ${(apk.sha256 || '').slice(0, 24) || '--'} · enviado ${fmtDate(apk.uploaded_at)}`
    if (specSize) specSize.innerHTML = `<i class="fa-solid fa-hard-drive"></i> ${fmtBytes(apk.size)}`
  } else {
    for (const b of [btn, top]) {
      if (!b) continue
      b.removeAttribute('href')
      b.classList.add('disabled')
      b.onclick = e => {
        e.preventDefault()
        toast('APK ainda não publicado. Use o link temporário impresso pelo install.sh na VPS.')
        $('#download').scrollIntoView({ behavior: 'smooth' })
      }
    }
    if (btn) btn.querySelector('strong').textContent = 'APK ainda não publicado'
    if (top) top.innerHTML = '<i class="fa-solid fa-download"></i><span>Baixar APK</span>'
    if (apkSub) apkSub.textContent = 'aguardando o upload via link temporário do install.sh'
  }
}

function renderStatus () {
  const dot = $('#statusDot')
  const txt = $('#statusText')
  const chipState = $('#connectState')
  if (!dot || !txt) return

  if (state.online && state.health) {
    const h = state.health
    dot.className = 'status-dot online'
    txt.textContent = 'ONLINE'
    if (chipState) {
      chipState.className = 'connect-state online'
      chipState.querySelector('span').textContent = `CONECTADO ${state.latencyMs ?? '--'}ms`
    }
    setStatsTile('tilePlayers', Number.isFinite(h.players) ? String(h.players) : '--')
    setStatsTile('tilePacks', String(h.packs ?? '--'))
    setStatsTile('tileEvents', String(h.events ?? '--'))
    setStatsTile('tileLatency', `${state.latencyMs ?? '--'} ms`)
    setStatsTile('tileGameData', h.game_data_loaded ? 'CARREGADO' : 'PENDENTE', h.game_data_loaded ? 'ok' : 'warn')
    setStatsTile('tileApk', state.apk?.available ? fmtBytes(state.apk.size) : 'AGUARDANDO', state.apk?.available ? 'ok' : 'warn')
    setStatsTile('tileApi', `${h.api_version || '--'} / ${h.client_version || '--'}`)
    const specVersion = $('#specVersion')
    if (specVersion && h.client_version) specVersion.innerHTML = `<i class="fa-solid fa-code-branch"></i> v${h.client_version}`
    document.dispatchEvent(new CustomEvent('revival:online'))
  } else {
    dot.className = 'status-dot offline'
    txt.textContent = 'OFFLINE'
    if ($('#statusUptime')) $('#statusUptime').textContent = '--'
    if (chipState) {
      chipState.className = 'connect-state offline'
      chipState.querySelector('span').textContent = 'SEM RESPOSTA'
    }
    setStatsTile('tileLatency', '--')
  }
  renderTerminal()
  renderApkButtons()
  tickClock()
}

async function poll () {
  try {
    const t0 = performance.now()
    const [healthRes, apkRes] = await Promise.all([
      fetch(HEALTH_URL, { cache: 'no-store' }),
      fetch(APK_INFO_URL, { cache: 'no-store' }).catch(() => null)
    ])
    if (!healthRes.ok) throw new Error(`HTTP ${healthRes.status}`)
    state.health = await healthRes.json()
    state.apk = apkRes && apkRes.ok ? await apkRes.json() : state.apk
    state.latencyMs = Math.round(performance.now() - t0)
    state.online = true
    state.lastTick = Date.now()
  } catch (error) {
    state.online = false
    if (!state.health) state.latencyMs = null
  }
  renderStatus()
}

function applyConfig () {
  $('#serverUrl').textContent = ORIGIN
  for (const id of ['#githubBtn', '#footerGithub']) {
    const el = $(id)
    if (el) el.href = cfg.githubUrl || '#'
  }
  $('#copyBtn').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(ORIGIN)
      toast('Endereço do servidor copiado.')
    } catch {
      toast(ORIGIN)
    }
  })
}

// Personalização vinda do painel do Super Admin (/slayer): textos do hero,
// GitHub e quais seções do site aparecem. Sem config salva, o site fica
// exatamente como está no HTML.
async function applySiteCustomization () {
  try {
    const response = await fetch(`${ORIGIN}/revival/site`, { cache: 'no-store' })
    if (!response.ok) return
    const { site } = await response.json()
    if (!site) return
    if (site.hero_title) $('#heroTitle').innerHTML = site.hero_title
    if (site.hero_description) $('#heroDescription').textContent = site.hero_description
    for (const id of ['#githubBtn', '#footerGithub']) {
      const el = $(id)
      if (!el) continue
      if (site.show_github === false) el.style.display = 'none'
      else if (site.github_url) el.href = site.github_url
    }
    for (const [flag, section] of [
      ['show_status', 'status'],
      ['show_features', 'recursos'],
      ['show_download', 'download'],
      ['show_faq', 'faq']
    ]) {
      if (site[flag] !== false) continue
      $(`#${section}`)?.style.setProperty('display', 'none')
      $(`#nav a[href="#${section}"]`)?.style.setProperty('display', 'none')
    }
  } catch {
    // Sem contato com o servidor: o site estático permanece como está.
  }
}

function setupUi () {
  const menu = $('#mobileMenu')
  const nav = $('#nav')
  if (menu && nav) {
    menu.addEventListener('click', () => nav.classList.toggle('open'))
    $$('#nav a').forEach(a => a.addEventListener('click', () => nav.classList.remove('open')))
  }

  addEventListener('scroll', () => {
    $('#topbar').style.boxShadow = scrollY > 30 ? '0 18px 45px rgba(0,0,0,.45)' : 'none'
  }, { passive: true })

  const revealObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible')
        revealObserver.unobserve(entry.target)
      }
    })
  }, { threshold: 0.12 })
  $$('.reveal').forEach(el => revealObserver.observe(el))

  // Link ativo da nav conforme a seção visível.
  const sections = $$('main section[id]')
  if (sections.length && 'IntersectionObserver' in window) {
    const navObserver = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return
        $$('#nav a').forEach(a => a.classList.toggle('active', a.getAttribute('href') === `#${entry.target.id}`))
      })
    }, { rootMargin: '-40% 0px -55% 0px' })
    sections.forEach(s => navObserver.observe(s))
  }
}

applyConfig()
applySiteCustomization()
setupUi()
try {
  startHellScene($('#hell-canvas'))
} catch {
  // Sem WebGL: o fundo CSS escuro permanece.
}
poll()
setInterval(poll, 30000)
setInterval(tickClock, 1000)
