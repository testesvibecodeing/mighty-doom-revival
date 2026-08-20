import { giveGameResource } from './game-data-model.js'
import { tutorialSequences } from './game-data-schema.js'

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

function definitionById (runtime, id) {
  return tutorialSequences(runtime.gameData).find(value => sequenceId(value) === id) || null
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
    // Idempotente de propósito. Medido no rig em 2026-08-20 (request_log 287):
    // no RESTART o cliente reenvia complete-sequence para uma sequência que já
    // consta em tutorialProgressionWire, e o 400/2000 que existia aqui derrubou
    // o parse com `Malformed response payload` — o cliente trata esta rota como
    // sucesso e não sabe desserializar o envelope de erro.
    //
    // Repetir não pode reconceder recompensa: `resources` volta vazio, que é o
    // mesmo shape (array) do caminho de sucesso.
    return { data: { resources: [] } }
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
