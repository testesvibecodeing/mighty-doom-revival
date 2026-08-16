import { fail, ok } from './protocol.js'
import { dailyRewardState, idleRewardState } from './rewards.js'

/**
 * Endpoints whose wire shape is known and whose implementation is safe even
 * before the full game-data/progression layer has been reconstructed.
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
    const runtime = runtimeProvider()
    const current = dailyRewardState(repo, ctx.state.user.id, runtime)
    ok(ctx, {
      state: {
        day_start: current.dayStart,
        day_end: current.dayStart + 86400,
        day: current.state.day,
        last_claim: current.state.last_claim,
        pending: current.state.pending,
        claimed: current.state.claimed,
        claimable: current.claimable
      }
    })
  })

  router.post('/idle-rewards/get-state', ctx => {
    const runtime = runtimeProvider()
    ok(ctx, { state: idleRewardState(repo, ctx.state.user.id, runtime) })
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
