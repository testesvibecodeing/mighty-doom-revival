import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'

import { Repository } from '../src/db.js'
import { handleTutorialRequest, tutorialProgressionWire } from '../src/tutorial.js'

const dir = mkdtempSync(resolve(tmpdir(), 'mighty-doom-tutorial-'))
const repo = new Repository(resolve(dir, 'tutorial.sqlite3'))

const gameData = {
  resources: [{ id: 100, tag: 'coins', category_id: 1 }],
  tutorial_sequences: [
    {
      id: 1,
      dependencies: [],
      resources: [{ resource: { id: 100 }, kind: 'currency', amount: 50 }]
    },
    {
      id: 2,
      dependencies: [1],
      resources: [{ resource: { id: 100 }, kind: 'currency', amount: 75 }]
    }
  ]
}

const runtime = {
  gameData,
  index: {
    byId: new Map([[100, gameData.resources[0]]]),
    byTag: new Map([['coins', 100]])
  }
}

try {
  const { user } = repo.createUser()

  const blocked = handleTutorialRequest(
    '/game/tutorial/complete-sequence',
    { sequence: 2 },
    user.id,
    repo,
    runtime
  )
  assert.equal(blocked.error[0], 400)
  assert.equal(blocked.error[2].reason, 'missing-dependencies')
  assert.equal(repo.balance(user.id, 100), 0)

  const first = handleTutorialRequest(
    '/game/tutorial/complete-sequence',
    { sequence: 1 },
    user.id,
    repo,
    runtime
  )
  assert.equal(first.data.resources[0].rid, 100)
  assert.equal(repo.balance(user.id, 100), 50)

  const second = handleTutorialRequest(
    '/game/tutorial/complete-sequence',
    { sequence: 2 },
    user.id,
    repo,
    runtime
  )
  assert.equal(second.data.resources[0].rid, 100)
  assert.equal(repo.balance(user.id, 100), 125)

  const duplicate = handleTutorialRequest(
    '/game/tutorial/complete-sequence',
    { sequence: 2 },
    user.id,
    repo,
    runtime
  )
  assert.equal(duplicate.error[2].reason, 'sequence-already-complete')
  assert.equal(repo.balance(user.id, 100), 125)

  const progression = tutorialProgressionWire(repo, user.id)
  assert.deepEqual(progression.sequences.map(row => row.sequence), [1, 2])

  const malformed = handleTutorialRequest(
    '/game/tutorial/complete-sequence',
    { sequence: '2' },
    user.id,
    repo,
    runtime
  )
  assert.equal(malformed.error[1], 2200)

  console.log('Mighty DOOM Revival tutorial test: PASS')
} finally {
  repo.close()
  rmSync(dir, { recursive: true, force: true })
}
