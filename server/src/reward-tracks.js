import { giveGameResource } from './game-data-model.js'
import { playerStatTotals } from './stats.js'

// ---- Contrato extraído do global-metadata.dat v29 (2026-08-17) ----
// RewardTracksApi: GetAll() -> game/reward-tracks/get-all   GetAllResponse{tracks}
//   get-track -> GetTrackResponse{track}   claim -> ClaimRewardTrackResponse{resources}
// Wire por RewardTrackModel/RewardTrackEntryModel (snake_case do nome C#):
//   {id, track_id, entries_claimed, next_claim_epoch, entries: [{resources}]}
// VERIFICADO no cliente em 2026-08-21 (bisseção no emulador, 8 execuções):
// `entries_claimed` como ARRAY de ids é aceito; `entries` aceita SOMENTE
// `{resources}` — o `id` extra dentro do EntryModel derruba o parse com
// `Malformed response payload`. Campo desconhecido na RAIZ do envelope é
// tolerado (uts/code convivem com os campos da rota); dentro de DTO aninhado,
// não é.

const NS = 'reward-tracks'

function arrayOrEmpty (value) {
  return Array.isArray(value) ? value : []
}

function trackRows (runtime) {
  const gameData = runtime?.gameData || {}
  const candidates = [
    gameData?.reward_tracks?.tracks,
    gameData?.reward_tracks,
    gameData?.reward_track?.tracks,
    gameData?.reward_track,
    runtime?.revival?.reward_tracks
  ]
  return candidates.find(Array.isArray) || []
}

function trackId (row, index) {
  return row?.id ?? row?.rid ?? row?.track_id ?? row?.tag ?? `reward-track-${index + 1}`
}

function statId (row) {
  const value = row?.stat_id ?? row?.stat?.id ?? row?.progress_stat_id ?? row?.progress?.stat_id
  if (Number.isInteger(value)) return String(value)
  if (typeof value === 'string' && value.trim()) return value.trim()
  return null
}

function tierRows (row) {
  if (!row || typeof row !== 'object') return []
  for (const value of [row.tiers, row.rewards, row.levels, row.entries]) {
    if (Array.isArray(value)) return value
  }
  return []
}

function tierId (row, index) {
  return row?.id ?? row?.rid ?? row?.tier_id ?? row?.level ?? row?.tag ?? index + 1
}

function tierTarget (row, index) {
  for (const value of [row?.target, row?.required, row?.points, row?.progress, row?.threshold, row?.level]) {
    const parsed = Number(value)
    if (Number.isFinite(parsed) && parsed >= 0) return parsed
  }
  return index + 1
}

function rewardRows (row) {
  if (!row || typeof row !== 'object') return []
  for (const value of [row.resources, row.contents, row.items, row.grants, row.rewards]) {
    if (Array.isArray(value)) return value
  }
  return []
}

function stateFor (repo, userId, id) {
  const saved = repo.getState(userId, NS, String(id), {})
  if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return { claimed: [] }
  return {
    claimed: arrayOrEmpty(saved.claimed),
    progress: Number.isFinite(Number(saved.progress)) ? Math.max(0, Number(saved.progress)) : null
  }
}

function progressFor (track, state, totals) {
  const stat = statId(track)
  if (stat !== null) return Math.max(0, Number(totals[stat] || 0))
  if (state.progress !== null) return state.progress
  const explicit = Number(track?.progress ?? 0)
  return Number.isFinite(explicit) && explicit >= 0 ? explicit : 0
}

export function rewardTrackState (repo, userId, runtime) {
  const totals = playerStatTotals(repo, userId)
  return trackRows(runtime).map((track, trackIndex) => {
    const id = trackId(track, trackIndex)
    const state = stateFor(repo, userId, id)
    const progress = progressFor(track, state, totals)
    const tiers = tierRows(track).map((tier, tierIndex) => {
      const idValue = tierId(tier, tierIndex)
      const target = tierTarget(tier, tierIndex)
      return {
        ...tier,
        id: idValue,
        target,
        progress: Math.min(progress, target),
        completed: progress >= target,
        claimed: state.claimed.some(value => String(value) === String(idValue))
      }
    })
    return {
      ...track,
      id,
      progress,
      tiers
    }
  })
}

export function claimRewardTrackTier (repo, userId, runtime, requestedTrackId, requestedTierId) {
  const tracks = rewardTrackState(repo, userId, runtime)
  const track = tracks.find(row => String(row.id) === String(requestedTrackId))
  if (!track) return { ok: false, reason: 'track-not-found' }

  const tier = track.tiers.find(row => String(row.id) === String(requestedTierId))
  if (!tier) return { ok: false, reason: 'tier-not-found' }
  if (!tier.completed) return { ok: false, reason: 'tier-not-complete' }
  if (tier.claimed) return { ok: false, reason: 'already-claimed' }

  const grants = []
  repo.tx(() => {
    for (const reward of rewardRows(tier)) {
      grants.push(giveGameResource(repo, userId, reward, runtime).wire)
    }
    const saved = stateFor(repo, userId, track.id)
    saved.claimed = [...new Set([...saved.claimed, tier.id])]
    repo.setState(userId, NS, String(track.id), saved)
  })

  return {
    ok: true,
    track_id: track.id,
    tier_id: tier.id,
    resources: grants
  }
}

function requestTrackId (body) {
  return body?.track_id ?? body?.track ?? body?.reward_track_id
}

function requestTierId (body) {
  return body?.tier_id ?? body?.tier ?? body?.reward_id ?? body?.id ?? body?.rid
}

// rewardTrackState mantém o formato interno rico (tiers com progress/
// completed/claimed); este é o mapeamento para o wire do RewardTrackModel.
export function rewardTrackWire (track) {
  const wire = {
    id: track.id,
    track_id: track.id,
    entries_claimed: track.tiers.filter(tier => tier.claimed).map(tier => tier.id),
    // RewardTrackEntryModel declara SOMENTE `resources`. O `id` que ficava
    // aqui era suposição ("extra tolerado como unknown field") e a bisseção no
    // emulador em 2026-08-21 a derrubou: com `{id, resources}` o cliente
    // respondeu `Malformed response payload`; com `{resources}` o boot passou.
    entries: track.tiers.map(tier => ({ resources: rewardRows(tier) }))
  }
  if (Number.isFinite(Number(track.next_claim_epoch)) && Number(track.next_claim_epoch) > 0) {
    wire.next_claim_epoch = Math.floor(Number(track.next_claim_epoch))
  }
  return wire
}

export function handleRewardTrackRequest (path, body, userId, repo, runtime) {
  if (path === '/game/reward-tracks/get-all') {
    return { data: { tracks: rewardTrackState(repo, userId, runtime).map(rewardTrackWire) } }
  }

  if (path === '/game/reward-tracks/get-track') {
    const trackId = requestTrackId(body)
    if (trackId === undefined || trackId === null) return { error: [400, 2200, { reason: 'track-required' }] }
    const track = rewardTrackState(repo, userId, runtime).find(row => String(row.id) === String(trackId))
    if (!track) return { error: [400, 2200, { reason: 'track-not-found' }] }
    return { data: { track: rewardTrackWire(track) } }
  }

  if (path === '/game/reward-tracks/claim') {
    const trackId = requestTrackId(body)
    const tierId = requestTierId(body)
    if (trackId === undefined || trackId === null || tierId === undefined || tierId === null) {
      return { error: [400, 2200] }
    }
    const result = claimRewardTrackTier(repo, userId, runtime, trackId, tierId)
    if (!result.ok) return { error: [400, 2000, { reason: result.reason }] }
    // ClaimRewardTrackResponse declara apenas {resources}
    return { data: { resources: result.resources } }
  }

  return null
}
