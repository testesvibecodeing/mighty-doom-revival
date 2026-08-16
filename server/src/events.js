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

export function eventSchedule (runtime) {
  const now = Math.floor(Date.now() / 1000)
  return runtime.events.filter(x => active(x, now)).map(x => ({
    id: x.id,
    event_definition_id: x.event_definition_id ?? x.id,
    start_time: asEpoch(x.start_time),
    end_time: asEpoch(x.end_time),
    availability: x.availability ?? 1,
    min_api_version: x.min_api_version ?? null,
    max_api_version: x.max_api_version ?? null,
    stop_time: null,
    event_type: x.event_type ?? 0,
    args: Buffer.from(JSON.stringify(x.args || {}), 'utf8').toString('base64')
  }))
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
  return result
}
