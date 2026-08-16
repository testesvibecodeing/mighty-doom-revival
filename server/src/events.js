import { activeBattlePassStates } from './battle-pass.js'
import { archiveMode, storyBattlePasses } from './game-data-schema.js'

function asEpoch (value) {
  if (value === null || value === undefined) return null
  if (typeof value === 'number') return value
  const n = Date.parse(value)
  if (Number.isNaN(n)) throw new Error(`Data de evento inválida: ${value}`)
  return Math.floor(n / 1000)
}

function active (event, now) {
  if (event.active === false) return false
  if (event.always === true) return true
  const start = asEpoch(event.start_time)
  const end = asEpoch(event.end_time)
  if (start !== null && now < start) return false
  if (end !== null && now > end) return false
  return true
}

function wireEvent (event, archive = false) {
  // O cliente 1.13.1 desserializa cada evento do schedule com parse estrito.
  // O cluster do DTO no global-metadata é exatamente: id, event_definition_id,
  // start_time, end_time, availability, min_api_version, max_api_version,
  // stop_time, args — sem "event_type". Campos numéricos não-nullable que
  // chegam como null explícito derrubam o parse ("Malformed response payload"),
  // então campos sem valor são omitidos, nunca enviados como null.
  const wire = {
    id: event.id,
    event_definition_id: event.event_definition_id ?? event.id,
    start_time: archive ? null : asEpoch(event.start_time),
    end_time: archive ? null : asEpoch(event.end_time),
    availability: event.availability ?? 1,
    args: Buffer.from(JSON.stringify(event.args || {}), 'utf8').toString('base64')
  }
  if (event.min_api_version != null) wire.min_api_version = event.min_api_version
  if (event.max_api_version != null) wire.max_api_version = event.max_api_version
  return wire
}

export function eventSchedule (runtime) {
  const now = Math.floor(Date.now() / 1000)
  const schedule = []
  const ids = new Set()

  for (const event of runtime.events.filter(x => active(x, now))) {
    const wire = wireEvent(event, false)
    schedule.push(wire)
    ids.add(String(wire.id))
  }

  const archive = archiveMode(runtime)
  for (const pass of storyBattlePasses(runtime.gameData)) {
    if (Number(pass?.availability ?? 1) < 1) continue
    if (!archive && !active(pass, now)) continue
    if (ids.has(String(pass.id))) continue
    schedule.push(wireEvent(pass, archive))
    ids.add(String(pass.id))
  }

  return schedule
}

export function eventProgress (repo, userId, runtime) {
  const now = Math.floor(Date.now() / 1000)
  const result = {
    game_mode_events_progress: [],
    store_offer_events_states: [],
    battle_pass_events_states: []
  }

  for (const event of runtime.events.filter(x => active(x, now))) {
    const channel = event.channel || 'game_mode'
    const fallback = event.progress_template || { event_id: event.id }
    const state = repo.getState(userId, 'event', String(event.id), fallback)
    if (channel === 'battle_pass') result.battle_pass_events_states.push(state)
    else if (channel === 'store_offer') result.store_offer_events_states.push(state)
    else result.game_mode_events_progress.push(state)
  }

  const existing = new Set(result.battle_pass_events_states.map(state => String(state?.season_id ?? state?.event_id ?? '')))
  for (const state of activeBattlePassStates(repo, userId, runtime)) {
    if (existing.has(String(state.season_id))) continue
    result.battle_pass_events_states.push(state)
  }

  return result
}
