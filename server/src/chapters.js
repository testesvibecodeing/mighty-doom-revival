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

export function handleChapterRequest (path, body, userId, repo) {
  if (path === '/game/chapters/start') {
    const state = progression(repo, userId)
    if (state.current_run) return { error: [409, 2000, { reason: 'run-already-active' }] }
    const run = runFromBody(body)
    if (!run) return { error: [400, 2200, { reason: 'chapter-required' }] }
    saveProgression(repo, userId, { ...state, current_run: run })
    return { data: { current_run: run } }
  }

  if (path === '/game/chapters/update') {
    const state = progression(repo, userId)
    if (!state.current_run) return { error: [409, 2000, { reason: 'no-active-run' }] }
    const currentRun = mergeRun(state.current_run, body)
    saveProgression(repo, userId, { ...state, current_run: currentRun })
    return { data: { current_run: currentRun } }
  }

  if (path === '/game/chapters/revive') {
    const state = progression(repo, userId)
    if (!state.current_run) return { error: [409, 2000, { reason: 'no-active-run' }] }
    const currentRun = {
      ...state.current_run,
      revives: Math.max(0, Number(state.current_run.revives || 0)) + 1,
      updated_at: Math.floor(Date.now() / 1000)
    }
    saveProgression(repo, userId, { ...state, current_run: currentRun })
    return { data: { current_run: currentRun } }
  }

  if (path === '/game/chapters/end') {
    const state = progression(repo, userId)
    if (!state.current_run) return { error: [409, 2000, { reason: 'no-active-run' }] }
    const finalRun = mergeRun(state.current_run, body)
    const next = recordCompletion(state, finalRun, body)
    saveProgression(repo, userId, next)
    return { data: { chapter_progression: next, rewards: [] } }
  }

  if (path === '/game/chapters/stage-rewards' || path === '/game/chapters/claim-stage-rewards') {
    return { data: { rewards: [] } }
  }

  return null
}
