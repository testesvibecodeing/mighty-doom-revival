// Revival public site — interface institucional/self-hosted.
import { startNetworkScene } from './network-scene.js'

const cfg = window.REVIVAL_CONFIG || {}
const $ = (selector, root = document) => root.querySelector(selector)
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)]

const ORIGIN = (cfg.serverUrl || '').replace(/\/+$/, '') || location.origin
const HEALTH_URL = cfg.healthUrl || `${ORIGIN}/revival/health`
const APK_INFO_URL = cfg.apkInfoUrl || `${ORIGIN}/revival/apk`
const GITHUB = (cfg.githubUrl || 'https://github.com/testesvibecodeing/mighty-doom-revival').replace(/\/+$/, '')

const state = {
  health: null,
  apk: null,
  latencyMs: null,
  online: false,
  lastHealthAt: null,
  polling: false
}

function toast (message) {
  const el = $('#toast')
  if (!el) return
  $('#toastMsg').textContent = message
  el.classList.add('show')
  clearTimeout(window.__revivalToast)
  window.__revivalToast = setTimeout(() => el.classList.remove('show'), 2800)
}

function fmtBytes (bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '--'
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
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const pad = n => String(n).padStart(2, '0')
  return days > 0 ? `${days}d ${pad(hours)}:${pad(minutes)}` : `${pad(hours)}:${pad(minutes)}`
}

function fmtDate (epochSeconds) {
  if (!Number.isFinite(epochSeconds) || epochSeconds <= 0) return '--'
  return new Date(epochSeconds * 1000).toLocaleString('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'short'
  })
}

function currentUptime () {
  if (!state.health || !Number.isFinite(state.health.uptime_seconds)) return null
  const extra = state.lastHealthAt ? Math.floor((Date.now() - state.lastHealthAt) / 1000) : 0
  return state.health.uptime_seconds + extra
}

function setText (selector, value) {
  const el = $(selector)
  if (el) el.textContent = value
}

function setClassText (selector, value, className = '') {
  const el = $(selector)
  if (!el) return
  el.textContent = value
  el.className = className
}

function repoUrl (path = '') {
  return path ? `${GITHUB}/${path.replace(/^\/+/, '')}` : GITHUB
}

function applyStaticLinks () {
  const links = {
    '#githubHero': repoUrl(),
    '#githubClosing': repoUrl(),
    '#footerGithub': repoUrl(),
    '#patchDocsBtn': repoUrl('blob/main/docs/APK-PATCH.md'),
    '#patchSourceBtn': repoUrl('tree/main/scripts'),
    '#docServer': repoUrl('blob/main/docs/SERVER.md'),
    '#docPatch': repoUrl('blob/main/docs/APK-PATCH.md'),
    '#docLegal': repoUrl('blob/main/docs/LEGAL-PRESERVATION.md'),
    '#docMatrix': repoUrl('blob/main/docs/ENDPOINT-MATRIX.md'),
    '#footerLegal': repoUrl('blob/main/docs/LEGAL-PRESERVATION.md')
  }
  for (const [selector, href] of Object.entries(links)) {
    const el = $(selector)
    if (el) el.href = href
  }
  setText('#serverUrl', ORIGIN)
  setText('#healthUrlLabel', HEALTH_URL.replace(ORIGIN, '') || HEALTH_URL)
}

function updateClock () {
  const uptime = currentUptime()
  if (uptime === null) return
  setText('#statusUptime', fmtUptime(uptime))
  setText('#tileUptime', fmtUptime(uptime))
}

function renderHealth () {
  const dot = $('#statusDot')
  const liveDot = $('#liveDot')
  const status = $('#statusText')

  if (state.online && state.health) {
    const h = state.health
    if (dot) dot.className = 'instance-dot online'
    if (liveDot) liveDot.className = 'live-dot online'
    if (status) status.textContent = 'ONLINE'

    setClassText('#tileState', 'ONLINE', 'ok')
    setText('#tileLatency', `${state.latencyMs ?? '--'} ms`)
    setText('#tilePlayers', Number.isFinite(h.players) ? String(h.players) : '--')
    setClassText('#tileGameData', h.game_data_loaded ? 'CARREGADO' : 'PENDENTE', h.game_data_loaded ? 'ok' : 'warn')
    setText('#tileApi', `${h.api_version || '--'} / ${h.client_version || '--'}`)
    setText('#tilePacks', String(h.packs ?? '--'))
    setText('#tileEvents', String(h.events ?? '--'))
    updateClock()
    document.dispatchEvent(new CustomEvent('revival:online'))
    return
  }

  if (dot) dot.className = 'instance-dot offline'
  if (liveDot) liveDot.className = 'live-dot offline'
  if (status) status.textContent = 'OFFLINE'
  setText('#statusUptime', '--')
  setClassText('#tileState', 'OFFLINE', 'bad')
  setText('#tileLatency', '--')
}

function renderApk () {
  const apk = state.apk
  const btn = $('#instanceApkBtn')
  const availability = $('#apkAvailability')

  if (apk?.available) {
    if (availability) {
      availability.textContent = 'disponível nesta instância'
      availability.className = 'availability available'
    }
    setText('#apkStatus', 'PUBLICADO')
    setText('#apkSize', fmtBytes(apk.size))
    setText('#apkHash', apk.sha256 || '--')
    setText('#apkDate', fmtDate(apk.uploaded_at))

    if (btn) {
      btn.href = apk.url
      btn.classList.remove('disabled')
      btn.removeAttribute('aria-disabled')
      const strong = btn.querySelector('strong')
      const small = btn.querySelector('small')
      if (strong) strong.textContent = `Baixar pacote desta instância · ${fmtBytes(apk.size)}`
      if (small) small.textContent = 'fornecido pelo administrador desta instância'
      btn.onclick = null
    }
    return
  }

  if (availability) {
    availability.textContent = 'não publicado'
    availability.className = 'availability unavailable'
  }
  setText('#apkStatus', 'NÃO PUBLICADO')
  setText('#apkSize', '--')
  setText('#apkHash', '--')
  setText('#apkDate', '--')

  if (btn) {
    btn.removeAttribute('href')
    btn.classList.add('disabled')
    btn.setAttribute('aria-disabled', 'true')
    const strong = btn.querySelector('strong')
    const small = btn.querySelector('small')
    if (strong) strong.textContent = 'Nenhum pacote publicado'
    if (small) small.textContent = 'endpoint desta instância: /revival/apk'
    btn.onclick = event => {
      event.preventDefault()
      toast('Esta instância não publicou um pacote configurado.')
    }
  }
}

async function poll () {
  if (state.polling) return
  state.polling = true
  try {
    const started = performance.now()
    const [healthResponse, apkResponse] = await Promise.all([
      fetch(HEALTH_URL, { cache: 'no-store' }),
      fetch(APK_INFO_URL, { cache: 'no-store' }).catch(() => null)
    ])

    if (!healthResponse.ok) throw new Error(`health HTTP ${healthResponse.status}`)
    state.health = await healthResponse.json()
    state.latencyMs = Math.round(performance.now() - started)
    state.lastHealthAt = Date.now()
    state.online = true

    if (apkResponse?.ok) {
      state.apk = await apkResponse.json()
    } else if (apkResponse && !apkResponse.ok) {
      state.apk = { available: false }
    }
  } catch {
    state.online = false
    if (!state.health) state.latencyMs = null
  } finally {
    state.polling = false
    renderHealth()
    renderApk()
  }
}

function setupCopy () {
  const btn = $('#copyBtn')
  if (!btn) return
  btn.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(ORIGIN)
      toast('Endereço da instância copiado.')
    } catch {
      toast(ORIGIN)
    }
  })
}

function setupNavigation () {
  const topbar = $('#topbar')
  const menuButton = $('#menuToggle')
  const nav = $('#nav')

  addEventListener('scroll', () => {
    topbar?.classList.toggle('scrolled', scrollY > 20)
  }, { passive: true })

  if (menuButton && nav) {
    menuButton.addEventListener('click', () => {
      const open = nav.classList.toggle('open')
      menuButton.setAttribute('aria-expanded', String(open))
    })
    $$('#nav a').forEach(link => link.addEventListener('click', () => {
      nav.classList.remove('open')
      menuButton.setAttribute('aria-expanded', 'false')
    }))
  }

  const sections = $$('main section[id]')
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        $$('#nav a').forEach(link => {
          link.classList.toggle('active', link.getAttribute('href') === `#${entry.target.id}`)
        })
      }
    }, { rootMargin: '-38% 0px -55% 0px' })
    sections.forEach(section => observer.observe(section))
  }
}

function setupReveal () {
  if (!('IntersectionObserver' in window)) {
    $$('.reveal').forEach(el => el.classList.add('visible'))
    return
  }
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue
      entry.target.classList.add('visible')
      observer.unobserve(entry.target)
    }
  }, { threshold: 0.12, rootMargin: '0px 0px -30px' })
  $$('.reveal').forEach(el => observer.observe(el))
}

function setupCodeTabs () {
  $$('.code-tabs button').forEach(button => {
    button.addEventListener('click', () => {
      const tab = button.dataset.tab
      $$('.code-tabs button').forEach(item => item.classList.toggle('active', item === button))
      $$('[data-code]').forEach(code => {
        code.hidden = code.dataset.code !== tab
      })
    })
  })
}

function setupRefresh () {
  $('#refreshHealth')?.addEventListener('click', () => {
    poll()
    toast('Atualizando telemetria da instância…')
  })
}

applyStaticLinks()
setupCopy()
setupNavigation()
setupReveal()
setupCodeTabs()
setupRefresh()

try {
  startNetworkScene($('#networkCanvas'))
} catch {
  // Sem WebGL: o gradiente e a grade CSS continuam suficientes.
}

poll()
setInterval(poll, 30000)
setInterval(updateClock, 1000)
