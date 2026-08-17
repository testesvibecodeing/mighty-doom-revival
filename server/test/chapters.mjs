import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'

import { chapterProgressionWire, handleChapterRequest } from '../src/chapters.js'
import { Repository } from '../src/db.js'

const dir = mkdtempSync(resolve(tmpdir(), 'mighty-doom-chapters-'))
const dbPath = resolve(dir, 'chapters.sqlite3')
const repo = new Repository(dbPath)

try {
  const { user } = repo.createUser()
  assert.equal(repo.userById(user.id).attempt_count, 0)
  assert.equal(repo.userById(user.id).chapter_progression, 0)

  let response = handleChapterRequest('/game/chapters/start', { chapter: 101 }, user.id, repo)
  assert.ok(response?.data?.current_run)
  assert.equal(repo.userById(user.id).attempt_count, 1)

  response = handleChapterRequest('/game/chapters/update', { stage: 5 }, user.id, repo)
  assert.equal(response.data.current_run.stage, 5)

  response = handleChapterRequest('/game/chapters/end', { state: 1, stage: 5 }, user.id, repo)
  assert.equal(response.data.chapter_progression.chapters.length, 1)
  assert.equal(repo.userById(user.id).chapter_progression, 1)
  assert.equal(chapterProgressionWire(repo, user.id).chapters[0].best_stage, 5)

  // Replay do mesmo capítulo conta como tentativa, mas não infla o progresso
  // global nem reduz o melhor estágio já persistido.
  handleChapterRequest('/game/chapters/start', { chapter: 101 }, user.id, repo)
  handleChapterRequest('/game/chapters/update', { stage: 3 }, user.id, repo)
  handleChapterRequest('/game/chapters/end', { state: 1, stage: 3 }, user.id, repo)
  assert.equal(repo.userById(user.id).attempt_count, 2)
  assert.equal(repo.userById(user.id).chapter_progression, 1)
  assert.equal(chapterProgressionWire(repo, user.id).chapters[0].best_stage, 5)

  // Tentativa perdida deve incrementar total_attempt_count, mas não o número
  // de capítulos concluídos usado pelo idle-reward/progresso global.
  handleChapterRequest('/game/chapters/start', { chapter: 102 }, user.id, repo)
  handleChapterRequest('/game/chapters/end', { state: 0, stage: 2 }, user.id, repo)
  assert.equal(repo.userById(user.id).attempt_count, 3)
  assert.equal(repo.userById(user.id).chapter_progression, 1)

  handleChapterRequest('/game/chapters/start', { chapter: 102 }, user.id, repo)
  handleChapterRequest('/game/chapters/end', { state: 1, stage: 4 }, user.id, repo)
  assert.equal(repo.userById(user.id).attempt_count, 4)
  assert.equal(repo.userById(user.id).chapter_progression, 2)

  repo.close()
  const reopened = new Repository(dbPath)
  assert.equal(reopened.userById(user.id).attempt_count, 4)
  assert.equal(reopened.userById(user.id).chapter_progression, 2)
  assert.equal(chapterProgressionWire(reopened, user.id).chapters.length, 2)
  reopened.close()

  console.log('Mighty DOOM Revival chapters test: PASS')
} finally {
  try { repo.close() } catch {}
  rmSync(dir, { recursive: true, force: true })
}
