import { existsSync, readFileSync } from 'node:fs'
import { isAbsolute, resolve } from 'node:path'

const ROOT = resolve(import.meta.dirname, '..')

function pathFromEnv (name, fallback) {
  const configured = process.env[name]
  if (!configured) return resolve(ROOT, fallback)
  return isAbsolute(configured) ? configured : resolve(ROOT, configured)
}

function readJson (path, fallback) {
  if (!existsSync(path)) return fallback
  return JSON.parse(readFileSync(path, 'utf8'))
}

function indexGameData (root) {
  const byTag = new Map()
  const byId = new Map()
  const seen = new Set()

  function walk (value) {
    if (!value || typeof value !== 'object' || seen.has(value)) return
    seen.add(value)

    if (!Array.isArray(value)) {
      const id = Number.isInteger(value.rid)
        ? value.rid
        : (Number.isInteger(value.id) ? value.id : null)
      if (id !== null) {
        if (!byId.has(id)) byId.set(id, value)
        if (typeof value.tag === 'string' && !byTag.has(value.tag)) {
          byTag.set(value.tag, id)
        }
      }
    }

    for (const child of Array.isArray(value) ? value : Object.values(value)) walk(child)
  }

  walk(root)
  return { byTag, byId }
}

export function loadRuntimeConfig () {
  const gameDataPath = pathFromEnv('GAME_DATA_PATH', 'data/game-data.json')
  const revivalPath = pathFromEnv('REVIVAL_CONFIG_PATH', 'config/revival.json')
  const packsPath = pathFromEnv('PACKS_CONFIG_PATH', 'config/packs.json')
  const eventsPath = pathFromEnv('EVENTS_CONFIG_PATH', 'config/events.json')
  const sitePath = pathFromEnv('SITE_CONFIG_PATH', 'config/site.json')

  const gameData = readJson(gameDataPath, null)
  const revival = readJson(revivalPath, {
    server_name: 'Mighty DOOM Revival',
    api_version: '24.0.0',
    client_version: '1.13.1',
    game_data_token: 'revival-local-game-data',
    auto_starter_bundle: true,
    initial_resources: []
  })
  const packs = readJson(packsPath, { packs: [] })
  const events = readJson(eventsPath, { events: [] })
  // Personalização do site público editada pelo Super Admin no painel
  // (/slayer). O site lê em /revival/site e aplica em tempo real.
  const siteStored = readJson(sitePath, {})
  const site = {
    hero_title: text(siteStored.hero_title, 'O clássico ressuscitou.<br>100% offline. 100% seu.', 200),
    hero_description: text(siteStored.hero_description, 'Reviva toda a ação, progressão, eventos e recompensas do Mighty DOOM em um servidor controlado por você. Sem pay-to-win e sem depender dos serviços oficiais encerrados.', 800),
    github_url: text(siteStored.github_url, 'https://github.com/testesvibecodeing/mighty-doom-revival', 300),
    show_github: bool(siteStored.show_github, true),
    show_status: bool(siteStored.show_status, true),
    show_features: bool(siteStored.show_features, true),
    show_download: bool(siteStored.show_download, true),
    show_faq: bool(siteStored.show_faq, true)
  }
  const index = gameData ? indexGameData(gameData) : { byTag: new Map(), byId: new Map() }

  return {
    root: ROOT,
    paths: { gameDataPath, revivalPath, packsPath, eventsPath, sitePath },
    gameData,
    revival,
    packs: Array.isArray(packs.packs) ? packs.packs : [],
    events: Array.isArray(events.events) ? events.events : [],
    site,
    index
  }
}

function text (value, fallback, limit) {
  return typeof value === 'string' && value.trim() ? value.trim().slice(0, limit) : fallback
}

function bool (value, fallback) {
  return typeof value === 'boolean' ? value : fallback
}

export function resolveResource (ref, runtime) {
  if (Number.isInteger(ref)) return ref

  if (typeof ref === 'string') {
    const id = runtime.index.byTag.get(ref)
    if (Number.isInteger(id)) return id
  }

  if (ref && typeof ref === 'object') {
    if (Number.isInteger(ref.rid)) return ref.rid
    if (Number.isInteger(ref.id)) return ref.id
    if (typeof ref.tag === 'string') {
      const id = runtime.index.byTag.get(ref.tag)
      if (Number.isInteger(id)) return id
    }
    if (ref.resource !== undefined) return resolveResource(ref.resource, runtime)
  }

  throw new Error(`Resource não resolvido: ${JSON.stringify(ref)}`)
}

export function resourceDefinition (rid, runtime) {
  return runtime.index.byId.get(rid) || null
}

export function researchMode () {
  return String(process.env.RESEARCH_MODE || 'true').toLowerCase() !== 'false'
}
