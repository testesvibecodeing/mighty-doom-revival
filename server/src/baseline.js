import { fail, ok } from './protocol.js'

function startOfUtcDayEpoch () {
  const now = new Date()
  return Math.floor(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()) / 1000)
}

function chooseIdleGeneration (gameData, chapterProgression) {
  const idle = gameData?.idle_reward
  const table = Array.isArray(idle?.chapter_idle_generation) ? idle.chapter_idle_generation : []
  let chosen = null
  for (const row of table) {
    if (typeof row?.chapter_progress !== 'number') continue
    if (row.chapter_progress > chapterProgression) continue
    if (chosen === null || row.chapter_progress >= chosen.chapter_progress) chosen = row
  }
  return {
    idle_generation: chosen?.idle_generation ?? [],
    generation_period: idle?.generation_period ?? 0
  }
}

/**
 * Endpoints whose wire shape is known and whose implementation is safe even
 * before the full game-data/progression layer has been reconstructed.
 *
 * More complex systems (chapters, upgrades, quests, battle pass claims) stay
 * in Research Mode until their invariants can be validated against the client.
 */
export function installBaselineRoutes (router, repo, runtimeProvider) {
  router.post('/session/heartbeat', ctx => ok(ctx))
  router.post('/session/refresh', ctx => ok(ctx, { token: ctx.state.user.token }))

  router.post('/identity/list', ctx => ok(ctx, { identities: [] }))
  router.post('/identity/link-game-center', ctx => fail(ctx, 400, 2000))
  router.post('/identity/link-google-play-games', ctx => fail(ctx, 400, 2000))

  router.post('/inbox/get-messages', ctx => ok(ctx, { messages: [] }))
  router.post('/reward-tracks/get-all', ctx => ok(ctx, { tracks: [] }))

  router.post('/daily-rewards/get-state', ctx => {
    const dayStart = startOfUtcDayEpoch()
    const state = repo.getState(ctx.state.user.id, 'daily-rewards', 'state', {
      day: 1,
      last_claim: 0,
      pending: [],
      claimed: []
    })
    ok(ctx, {
      state: {
        day_start: dayStart,
        day_end: dayStart + 86400,
        day: state.day ?? 1,
        last_claim: state.last_claim ?? 0,
        pending: Array.isArray(state.pending) ? state.pending : [],
        claimed: Array.isArray(state.claimed) ? state.claimed : []
      }
    })
  })

  router.post('/idle-rewards/get-state', ctx => {
    const runtime = runtimeProvider()
    const user = repo.userById(ctx.state.user.id)
    const generation = chooseIdleGeneration(runtime.gameData, user.chapter_progression)
    ok(ctx, {
      state: {
        last_claim: repo.getState(user.id, 'idle-rewards', 'last_claim', 0),
        boost_available: 0,
        next_claim: 0,
        ...generation
      }
    })
  })

  router.post('/inventory/get-equip-sequence-id', ctx => {
    const sequenceId = repo.getState(ctx.state.user.id, 'inventory', 'equip_sequence_id', 0)
    ok(ctx, { sequence_id: sequenceId })
  })

  router.post('/inventory/equip', ctx => {
    const slotId = ctx.request.body?.slot
    const itemId = ctx.request.body?.item
    if (!Number.isInteger(slotId) || !Number.isInteger(itemId)) return fail(ctx, 400, 2200)

    const success = repo.tx(() => {
      if (!repo.setSlot(ctx.state.user.id, slotId, itemId)) return false
      const previous = repo.getState(ctx.state.user.id, 'inventory', 'equip_sequence_id', 0)
      repo.setState(ctx.state.user.id, 'inventory', 'equip_sequence_id', previous + 1)
      return true
    })
    if (!success) return fail(ctx, 400, 2000)
    const sequenceId = repo.getState(ctx.state.user.id, 'inventory', 'equip_sequence_id', 0)
    ok(ctx, { sequence_id: sequenceId })
  })

  // The client can submit generic stat increments during boot/menu flows.
  // Until the stat registry is imported from game-data we acknowledge them and
  // retain the request in request_log rather than inventing stat semantics.
  router.post('/player/increment-stats', ctx => ok(ctx))
}
