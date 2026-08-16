import { giveGameResource } from './game-data-model.js'

const NS = 'tutorial'
const STATE_KEY = 'sequences'

function sequenceId (value) {
  if (!value || typeof value !== 'object') return null
  if (Number.isInteger(value.id)) return value.id
  if (Number.isInteger(value.rid)) return value.rid
  if (Number.isInteger(value.sequence)) return value.sequence
  if (Number.isInteger(value.sequence_id)) return value.sequence_id
  return null
}

function definitions (runtime) {
  return Array.isArray(runtime.gameData?.tutorial_sequences)
    ? runtime.gameData.tutorial_sequences
    : []
}

function definitionById (runtime, id) {
  return definitions(runtime).find(value => sequenceId(value) === id) || null
}

function completedRows (repo, userId) {
  const saved = repo.getState(userId, NS, STATE_KEY, [])
  return Array.isArray(saved) ? saved : []
}

function completedIds (rows) {
  return new Set(rows.map(row => Number.isInteger(row) ? row : sequenceId(row)).filter(Number.isInteger))
}

function dependencies (definition) {
  const values = Array.isArray(definition?.dependencies) ? definition.dependencies : []
  return values
    .map(value => Number.isInteger(value) ? value : sequenceId(value))
    .filter(Number.isInteger)
}

function rewards (definition) {
  if (Array.isArray(definition?.resources)) return definition.resources
  if (Array.isArray(definition?.rewards)) return definition.rewards
  return []
}

export function tutorialProgressionWire (repo, userId) {
  return { sequences: completedRows(repo, userId) }
}

export function handleTutorialRequest (path, body, userId, repo, runtime) {
  if (path !== '/game/tutorial/complete-sequence') return null

  const id = body?.sequence
  if (!Number.isInteger(id)) {
    return { error: [400, 2200, { reason: 'sequence-required' }] }
  }

  const definition = definitionById(runtime, id)
  if (!definition) {
    return { error: [400, 2000, { reason: 'unknown-sequence' }] }
  }

  const rows = completedRows(repo, userId)
  const ids = completedIds(rows)
  if (ids.has(id)) {
    return { error: [400, 2000, { reason: 'sequence-already-complete' }] }
  }

  const missing = dependencies(definition).filter(dependencyId => !ids.has(dependencyId))
  if (missing.length > 0) {
    return { error: [400, 2000, { reason: 'missing-dependencies', dependencies: missing }] }
  }

  const granted = []
  repo.tx(() => {
    for (const resource of rewards(definition)) {
      const result = giveGameResource(repo, userId, resource, runtime)
      granted.push(result.wire)
    }

    rows.push({
      sequence: id,
      complete_epoch: Math.floor(Date.now() / 1000)
    })
    repo.setState(userId, NS, STATE_KEY, rows)
  })

  return { data: { resources: granted } }
}
