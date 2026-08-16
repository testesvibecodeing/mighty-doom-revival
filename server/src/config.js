import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const ROOT = resolve(import.meta.dirname, '..')

function pathFromEnv (name, fallback) {
  return resolve(process.cwd(), process.env[name] || fallback)
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
  const gameDataPath = pathFromEnv('GAME_DATA_PATH', 'server/data/game-data.json')
  const revivalPath = pathFromEnv('REVIVAL_CONFIG_PATH', 'server/config/revival.json')
  const packsPath = pathFromEnv('PACKS_CONFIG_PATH', 'server/config/packs.json')
  const eventsPath = pathFromEnv('EVENTS_CONFIG_PATH', 'server/config/events.json')

  const gameData = readJson(gameDataPath, null)
  const revival = readJson(revivalPath, {
    server_name: 'Mighty DOOM Revival',
    api_version: '24.0.0',
    client_version: '1.13.1',
    game_data_token: 'revival-local-game-data',
    initial_resources: []
  })
  const packs = readJson(packsPath, { packs: [] })
  const events = readJson(eventsPath, { events: [] })
  const index = gameData ? indexGameData(gameData) : { byTag: new Map(), byId: new Map() }

  return {
    root: ROOT,
    paths: { gameDataPath, revivalPath, packsPath, eventsPath },
    gameData,
    revival,
    packs: Array.isArray(packs.packs) ? packs.packs : [],
    events: Array.isArray(events.events) ? events.events : [],
    index
  }
}

export function resolveResource (ref, runtime) {
  if (Number.isInteger(ref)) return ref
  if (typeof ref === 'string') {
    const id = runtime.index.byTag.get(ref)
    if (Number.isInteger(id)) return id
  }
  throw new Error(`Resource não resolvido: ${JSON.stringify(ref)}`)
}

export function resourceDefinition (rid, runtime) {
  return runtime.index.byId.get(rid) || null
}

export function researchMode () {
  return String(process.env.RESEARCH_MODE || 'true').toLowerCase() !== 'false'
}
