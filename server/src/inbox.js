import { giveGameResource } from './game-data-model.js'

// ---- Contrato extraído do global-metadata.dat v29 (2026-08-17) ----
// InboxApi (rotas game/inbox/*): get-messages, read, claim, delete
// GetMessagesResponse{messages} de InboxMessage:
//   {id, display_type, interaction_state, title, body, publish_epoch,
//    expire_epoch, resources, image_id, conditions}
// ClaimMessageResponse{resources}; read/delete sem DTO -> envelope puro.
// MessageInteraction: Unread=0, Read=1, Claimed=2, Archived=3 (enum serializa
// como número no Newtonsoft sem StringEnumConverter — A VERIFICAR na captura).
// Config em gameData.messages[] (ou gameData.inbox.messages[]): mesmos campos
// do InboxMessage; expire_epoch/resources/image_id/conditions opcionais
// (omitidos no wire quando ausentes — campo sem valor é omitido, nunca null).

const NS = 'inbox'

const INTERACTION = { unread: 0, read: 1, claimed: 2, archived: 3 }

function arrayOrEmpty (value) {
  return Array.isArray(value) ? value : []
}

function nowSeconds () {
  return Math.floor(Date.now() / 1000)
}

function asInt (value) {
  return Number.isInteger(value) ? value : null
}

function messageRows (runtime) {
  const gameData = runtime?.gameData || {}
  const candidates = [
    gameData?.messages,
    gameData?.inbox?.messages,
    Array.isArray(gameData?.inbox) ? gameData.inbox : null
  ]
  return candidates.find(Array.isArray) || []
}

function messageId (row, index) {
  return asInt(row?.id) ?? row?.tag ?? index + 1
}

function inboxState (repo, userId) {
  const saved = repo.getState(userId, NS, 'state', null)
  if (!saved || typeof saved !== 'object' || Array.isArray(saved)) {
    return { read: [], claimed: [], deleted: [] }
  }
  return {
    read: arrayOrEmpty(saved.read),
    claimed: arrayOrEmpty(saved.claimed),
    deleted: arrayOrEmpty(saved.deleted)
  }
}

function saveInboxState (repo, userId, state) {
  repo.setState(userId, NS, 'state', state)
  return state
}

function visibleMessages (repo, userId, runtime, epoch = nowSeconds()) {
  const state = inboxState(repo, userId)
  return messageRows(runtime)
    .map((row, index) => ({ row, id: messageId(row, index) }))
    .filter(({ row, id }) => {
      if (state.deleted.includes(id)) return false
      const publish = asInt(row?.publish_epoch)
      if (publish !== null && publish > epoch) return false
      const expire = asInt(row?.expire_epoch)
      if (expire !== null && expire <= epoch) return false
      return true
    })
}

function messageWire ({ row, id }, state) {
  const wire = {
    id,
    display_type: row?.display_type ?? 'inbox',
    interaction_state: state.claimed.includes(id) ? INTERACTION.claimed
      : state.read.includes(id) ? INTERACTION.read
        : INTERACTION.unread,
    title: row?.title ?? '',
    body: row?.body ?? ''
  }
  const publish = asInt(row?.publish_epoch)
  if (publish !== null) wire.publish_epoch = publish
  const expire = asInt(row?.expire_epoch)
  if (expire !== null) wire.expire_epoch = expire
  const resources = arrayOrEmpty(row?.resources)
  if (resources.length > 0) wire.resources = resources
  const imageId = asInt(row?.image_id)
  if (imageId !== null) wire.image_id = imageId
  const conditions = arrayOrEmpty(row?.conditions)
  if (conditions.length > 0) wire.conditions = conditions
  return wire
}

function requestedMessageId (body) {
  return body?.message_id ?? body?.id ?? body?.message
}

export function handleInboxRequest (path, body, userId, repo, runtime) {
  if (path === '/game/inbox/get-messages') {
    const state = inboxState(repo, userId)
    const messages = visibleMessages(repo, userId, runtime).map(entry => messageWire(entry, state))
    return { data: { messages } }
  }

  if (path === '/game/inbox/read') {
    const id = requestedMessageId(body)
    if (id === undefined || id === null) return { error: [400, 2200, { reason: 'message-required' }] }
    const visible = visibleMessages(repo, userId, runtime)
    if (!visible.some(entry => String(entry.id) === String(id))) {
      return { error: [400, 2300, { reason: 'message-not-found' }] }
    }
    const state = inboxState(repo, userId)
    if (!state.read.includes(id)) saveInboxState(repo, userId, {
      ...state,
      read: [...new Set([...state.read, id])]
    })
    return { data: {} }
  }

  if (path === '/game/inbox/claim') {
    const id = requestedMessageId(body)
    if (id === undefined || id === null) return { error: [400, 2200, { reason: 'message-required' }] }
    const entry = visibleMessages(repo, userId, runtime).find(item => String(item.id) === String(id))
    if (!entry) return { error: [400, 2300, { reason: 'message-not-found' }] }
    const state = inboxState(repo, userId)
    if (state.claimed.includes(id)) return { error: [400, 2300, { reason: 'already-claimed' }] }
    const rewards = arrayOrEmpty(entry.row?.resources)
    if (rewards.length === 0) return { error: [400, 2300, { reason: 'message-without-resources' }] }
    let resources
    repo.tx(() => {
      resources = rewards.map(reward => giveGameResource(repo, userId, reward, runtime).wire)
      saveInboxState(repo, userId, {
        ...inboxState(repo, userId),
        claimed: [...new Set([...inboxState(repo, userId).claimed, id])],
        read: [...new Set([...inboxState(repo, userId).read, id])]
      })
    })
    return { data: { resources } }
  }

  if (path === '/game/inbox/delete') {
    const id = requestedMessageId(body)
    if (id === undefined || id === null) return { error: [400, 2200, { reason: 'message-required' }] }
    const visible = visibleMessages(repo, userId, runtime)
    if (!visible.some(entry => String(entry.id) === String(id))) {
      return { error: [400, 2300, { reason: 'message-not-found' }] }
    }
    const state = inboxState(repo, userId)
    if (!state.deleted.includes(id)) saveInboxState(repo, userId, {
      ...state,
      deleted: [...new Set([...state.deleted, id])]
    })
    return { data: {} }
  }

  return null
}
