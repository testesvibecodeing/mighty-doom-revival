import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'

import { Repository } from '../src/db.js'
import { handleInboxRequest } from '../src/inbox.js'

// Dataset sintético — mesmos números do capture_protocol_fixtures.mjs.
const coins = { id: 100, tag: 'coins', category_id: 1 }
const runtime = {
  gameData: {
    resources: [coins],
    messages: [
      { id: 1, title: 'Bem-vindo', body: 'Boa caçada', resources: [{ rid: 100, amount: 50 }] },
      { id: 2, title: 'Aviso', body: 'Evento termina semana que vem' },
      { id: 3, title: 'Expirado', body: 'já era', expire_epoch: 1 },
      { id: 4, title: 'Agendado', body: 'ainda não', publish_epoch: 4102444800 }
    ]
  },
  index: { byId: new Map([[100, coins]]), byTag: new Map([['coins', 100]]) }
}

const dir = mkdtempSync(resolve(tmpdir(), 'mighty-doom-inbox-'))
const dbPath = resolve(dir, 'inbox.sqlite3')
const repo = new Repository(dbPath)

try {
  const { user } = repo.createUser()
  const UID = user.id

  // GetMessagesResponse{messages}: só o que está publicado, não expirado e
  // não deletado; interaction_state numérico (MessageInteraction).
  let result = handleInboxRequest('/game/inbox/get-messages', {}, UID, repo, runtime)
  assert.deepEqual(result.data.messages.map(m => m.id), [1, 2])
  const first = result.data.messages[0]
  assert.equal(first.interaction_state, 0)
  assert.equal(first.display_type, 'inbox')
  assert.deepEqual(first.resources, [{ rid: 100, amount: 50 }])
  assert.equal('expire_epoch' in first, false, 'campo ausente é omitido, nunca null')
  assert.equal(result.data.messages[1].resources, undefined)

  // read: envelope puro e muda o interaction_state.
  result = handleInboxRequest('/game/inbox/read', { message_id: 1 }, UID, repo, runtime)
  assert.equal(Object.keys(result.data).length, 0)
  result = handleInboxRequest('/game/inbox/get-messages', {}, UID, repo, runtime)
  assert.equal(result.data.messages[0].interaction_state, 1)

  // claim: concede recursos e marca Claimed.
  result = handleInboxRequest('/game/inbox/claim', { message_id: 1 }, UID, repo, runtime)
  assert.deepEqual(result.data.resources, [{ rid: 100, amount: 50 }])
  assert.equal(repo.balance(UID, 100), 50)
  result = handleInboxRequest('/game/inbox/get-messages', {}, UID, repo, runtime)
  assert.equal(result.data.messages[0].interaction_state, 2)
  result = handleInboxRequest('/game/inbox/claim', { message_id: 1 }, UID, repo, runtime)
  assert.equal(result.error[2].reason, 'already-claimed')

  // mensagem sem recursos não é claimable — erro de estado explícito.
  result = handleInboxRequest('/game/inbox/claim', { message_id: 2 }, UID, repo, runtime)
  assert.equal(result.error[1], 2300)
  assert.equal(result.error[2].reason, 'message-without-resources')

  // delete: some da lista; read/claim em deletada -> message-not-found.
  result = handleInboxRequest('/game/inbox/delete', { message_id: 2 }, UID, repo, runtime)
  assert.equal(Object.keys(result.data).length, 0)
  result = handleInboxRequest('/game/inbox/get-messages', {}, UID, repo, runtime)
  assert.deepEqual(result.data.messages.map(m => m.id), [1])
  result = handleInboxRequest('/game/inbox/read', { message_id: 2 }, UID, repo, runtime)
  assert.equal(result.error[2].reason, 'message-not-found')

  // persistência: estado sobrevive ao restart do processo.
  repo.close()
  const reopened = new Repository(dbPath)
  result = handleInboxRequest('/game/inbox/get-messages', {}, UID, reopened, runtime)
  assert.deepEqual(result.data.messages.map(m => m.id), [1])
  assert.equal(result.data.messages[0].interaction_state, 2)
  assert.equal(reopened.balance(UID, 100), 50)
  reopened.close()

  console.log('Mighty DOOM Revival inbox test: PASS')
} finally {
  try { repo.close() } catch {}
  rmSync(dir, { recursive: true, force: true })
}
