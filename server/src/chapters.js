import { fail, ok } from './protocol.js'

const NS = 'chapters'

function asInt (value, fallback = null) {
  return Number.isInteger(value) ? value : fallback
}

function runFromBody (body = {}) {
  const chapter = asInt(body.chapter ?? body.chapter_id ?? body.rid)
  if (chapter === null) return null
  return {
    chapter,
    challenge: asInt(body.challenge ?? body.challenge_id, 0),
    stage: asInt(body.stage ?? body.stage_index, 0),
    started_at: Math.floor(Date.now() / 1000),
    updated_at: Math.floor(Date.now() / 1000),
    revives: 0,
    stats: Array.isArray(body.stats) ? body.stats : [],
    payload: body.run && typeof body.run === 'object' ? body.run : null
  }
}

function progression (repo, userId) {
  return repo.getState(userId, NS, 'progression', {
    chapters: [],
    challenges: [],
    current_run: null
  })
}

function saveProgression (repo, userId, value) {
  repo.setState(userId, NS, 'progression', value)
  return value
}

function mergeRun (current, body = {}) {
  const next = { ...current, updated_at: Math.floor(Date.now() / 1000) }
  const stage = asInt(body.stage ?? body.stage_index)
  if (stage !== null) next.stage = Math.max(next.stage ?? 0, stage)
  if (Array.isArray(body.stats)) next.stats = body.stats
  if (body.run && typeof body.run === 'object') next.payload = body.run
  if (body.checkpoint !== undefined) next.checkpoint = body.checkpoint
  return next
}

function recordCompletion (state, run, body = {}) {
  const completed = body.completed !== false && body.success !== false
  const chapters = Array.isArray(state.chapters) ? [...state.chapters] : []
  if (completed) {
    const existing = chapters.find(x => x?.chapter === run.chapter || x?.id === run.chapter)
    const row = {
      chapter: run.chapter,
      completed: true,
      best_stage: Math.max(run.stage ?? 0, asInt(body.stage ?? body.stage_index, 0)),
      completed_at: Math.floor(Date.now() / 1000)
    }
    if (existing) Object.assign(existing, row)
    else chapters.push(row)
  }
  return { ...state, chapters, current_run: null }
}

export function chapterProgressionWire (repo, userId) {
  return progression(repo, userId)
}

export function installChapterRoutes (router, repo) {
  router.post('/chapters/start', ctx => {
    const userId = ctx.state.user.id
    const state = progression(repo, userId)
    if (state.current_run) return fail(ctx, 409, 2000, { reason: 'run-already-active' })

    const run = runFromBody(ctx.request.body)
    if (!run) return fail(ctx, 400, 2200, { reason: 'chapter-required' })

    saveProgression(repo, userId, { ...state, current_run: run })
    ok(ctx, { current_run: run })
  })

  router.post('/chapters/update', ctx => {
    const userId = ctx.state.user.id
    const state = progression(repo, userId)
    if (!state.current_run) return fail(ctx, 409, 2000, { reason: 'no-active-run' })

    const currentRun = mergeRun(state.current_run, ctx.request.body)
    saveProgression(repo, userId, { ...state, current_run: currentRun })
    ok(ctx, { current_run: currentRun })
  })

  router.post('/chapters/revive', ctx => {
    const userId = ctx.state.user.id
    const state = progression(repo, userId)
    if (!state.current_run) return fail(ctx, 409, 2000, { reason: 'no-active-run' })

    const currentRun = {
      ...state.current_run,
      revives: Math.max(0, Number(state.current_run.revives || 0)) + 1,
      updated_at: Math.floor(Date.now() / 1000)
    }
    saveProgression(repo, userId, { ...state, current_run: currentRun })
    ok(ctx, { current_run: currentRun })
  })

  router.post('/chapters/end', ctx => {
    const userId = ctx.state.user.id
    const state = progression(repo, userId)
    if (!state.current_run) return fail(ctx, 409, 2000, { reason: 'no-active-run' })

    const finalRun = mergeRun(state.current_run, ctx.request.body)
    const next = recordCompletion(state, finalRun, ctx.request.body)
    saveProgression(repo, userId, next)
    ok(ctx, { chapter_progression: next, rewards: [] })
  })

  // The client may request stage rewards separately. Until the exact reward
  // table is validated, return an explicit empty grant instead of allowing the
  // research fallback to pretend that a reward was delivered.
  router.post('/chapters/stage-rewards', ctx => ok(ctx, { rewards: [] }))
  router.post('/chapters/claim-stage-rewards', ctx => ok(ctx, { rewards: [] }))
}
