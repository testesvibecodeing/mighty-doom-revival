const NS = 'chapters'

function asInt (value, fallback = null) {
  return Number.isInteger(value) ? value : fallback
}

function progressBody (body = {}) {
  return body?.progress && typeof body.progress === 'object' ? body.progress : body
}

function runFromBody (body = {}) {
  const chapter = asInt(body.chapter ?? body.chapter_id ?? body.rid)
  if (chapter === null) return null
  return {
    chapter,
    challenge: asInt(body.challenge ?? body.challenge_id, 0),
    stage: 0,
    started_at: Math.floor(Date.now() / 1000),
    updated_at: Math.floor(Date.now() / 1000),
    revives: 0,
    weapons: Array.isArray(body.weapons) ? body.weapons : [],
    gear: Array.isArray(body.gear) ? body.gear : [],
    stats: [],
    payload: null
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
  const progress = progressBody(body)
  const next = { ...current, updated_at: Math.floor(Date.now() / 1000) }
  const stage = asInt(progress.stage ?? progress.stage_index)
  if (stage !== null) next.stage = Math.max(next.stage ?? 0, stage)
  if (Number.isInteger(progress.state)) next.state = progress.state
  if (Array.isArray(progress.stats)) next.stats = progress.stats
  if (Array.isArray(progress.loot)) next.loot = progress.loot
  if (Array.isArray(progress.battle_pass_points_found)) next.battle_pass_points_found = progress.battle_pass_points_found
  if (progress.checkpoint !== undefined) next.checkpoint = progress.checkpoint
  next.payload = progress
  return next
}

function completedFromProgress (body = {}) {
  const progress = progressBody(body)
  if (Number.isInteger(progress.state)) return progress.state === 1
  return body.completed !== false && body.success !== false
}

function recordCompletion (state, run, body = {}) {
  const completed = completedFromProgress(body)
  const chapters = Array.isArray(state.chapters) ? [...state.chapters] : []
  if (completed) {
    const existing = chapters.find(x => x?.chapter === run.chapter || x?.id === run.chapter)
    const row = {
      chapter: run.chapter,
      completed: true,
      best_stage: run.stage ?? 0,
      completed_at: Math.floor(Date.now() / 1000)
    }
    if (existing) Object.assign(existing, row)
    else chapters.push(row)
  }
  return { ...state, chapters, current_run: null }
}

function attemptWire (run) {
  return {
    id: run.started_at,
    attempt_id: run.started_at,
    chapter_id: run.chapter,
    challenge_id: run.challenge || null,
    seed: run.started_at,
    weapons: run.weapons,
    gear: run.gear,
    stage: run.stage
  }
}

export function chapterProgressionWire (repo, userId) {
  return progression(repo, userId)
}

export function handleChapterRequest (path, body, userId, repo) {
  if (path === '/game/chapters/start') {
    const state = progression(repo, userId)
    if (state.current_run) return { error: [400, 2000, { reason: 'run-already-active' }] }
    const run = runFromBody(body)
    if (!run) return { error: [400, 2200, { reason: 'chapter-required' }] }
    saveProgression(repo, userId, { ...state, current_run: run })
    return { data: { attempt: attemptWire(run), current_run: run } }
  }

  if (path === '/game/chapters/update') {
    const state = progression(repo, userId)
    if (!state.current_run) return { error: [400, 2000, { reason: 'no-active-run' }] }
    const currentRun = mergeRun(state.current_run, body)
    saveProgression(repo, userId, { ...state, current_run: currentRun })
    return { data: { min_update_time: null, current_run: currentRun } }
  }

  if (path === '/game/chapters/revive') {
    const state = progression(repo, userId)
    if (!state.current_run) return { error: [400, 2000, { reason: 'no-active-run' }] }
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
    if (!state.current_run) return { error: [400, 2000, { reason: 'no-active-run' }] }
    const finalRun = mergeRun(state.current_run, body)
    const next = recordCompletion(state, finalRun, body)
    saveProgression(repo, userId, next)
    return {
      data: {
        loot: Array.isArray(finalRun.loot) ? finalRun.loot : [],
        chapter_progression: next,
        rewards: []
      }
    }
  }

  if (
    path === '/game/chapters/claim-stage-reward' ||
    path === '/game/chapters/stage-rewards' ||
    path === '/game/chapters/claim-stage-rewards'
  ) {
    const state = progression(repo, userId)
    const chapterId = asInt(body?.chapter_id ?? body?.chapter)
    const row = state.chapters.find(x => x?.chapter === chapterId || x?.id === chapterId)
    return { data: { stage: row?.best_stage ?? 0, resources: [], rewards: [] } }
  }

  return null
}
