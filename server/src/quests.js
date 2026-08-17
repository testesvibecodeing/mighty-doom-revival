import { giveGameResource } from './game-data-model.js'
import { playerStatTotals } from './stats.js'
import { startOfUtcDayEpoch } from './rewards.js'

const NS = 'daily-quests'

function arrayOrEmpty (value) {
  return Array.isArray(value) ? value : []
}

function questRows (runtime) {
  const gameData = runtime?.gameData || {}
  const candidates = [
    gameData?.quests?.daily_quests,
    gameData?.quests?.daily,
    gameData?.daily_quests?.quests,
    Array.isArray(gameData?.daily_quests) ? gameData.daily_quests : null,
    runtime?.revival?.daily_quests
  ]
  return candidates.find(Array.isArray) || []
}

function milestoneRows (runtime) {
  const gameData = runtime?.gameData || {}
  const candidates = [
    gameData?.quests?.daily_milestones,
    gameData?.quests?.milestones,
    gameData?.daily_quests?.milestones,
    runtime?.revival?.daily_quest_milestones
  ]
  return candidates.find(Array.isArray) || []
}

function questId (row, index) {
  const value = row?.id ?? row?.rid ?? row?.quest_id ?? row?.tag
  return value ?? `daily-${index + 1}`
}

function statId (row) {
  const value = row?.stat_id ?? row?.stat?.id ?? row?.stat ?? row?.progress_stat_id ?? row?.objective?.stat_id
  if (Number.isInteger(value)) return String(value)
  if (typeof value === 'string' && value.trim()) return value.trim()
  return null
}

function targetAmount (row) {
  for (const value of [row?.target, row?.amount, row?.required, row?.count, row?.objective?.target, row?.objective?.amount]) {
    const number = Number(value)
    if (Number.isFinite(number) && number > 0) return number
  }
  return 1
}

function rewardRows (row) {
  if (!row || typeof row !== 'object') return []
  for (const value of [row.rewards, row.resources, row.contents, row.items]) {
    if (Array.isArray(value)) return value
  }
  return []
}

function milestoneTarget (row) {
  for (const value of [row?.target, row?.required, row?.points, row?.count]) {
    const number = Number(value)
    if (Number.isFinite(number) && number > 0) return number
  }
  return 1
}

function normalizeState (value, dayStart, totals) {
  if (!value || typeof value !== 'object' || value.day_start !== dayStart) {
    return {
      day_start: dayStart,
      baseline_stats: { ...totals },
      claimed_quests: [],
      claimed_milestones: []
    }
  }
  return {
    day_start: dayStart,
    baseline_stats: value.baseline_stats && typeof value.baseline_stats === 'object' ? value.baseline_stats : { ...totals },
    claimed_quests: arrayOrEmpty(value.claimed_quests),
    claimed_milestones: arrayOrEmpty(value.claimed_milestones)
  }
}

function questProgress (row, state, totals) {
  const stat = statId(row)
  if (stat === null) return Number(row?.progress ?? 0) || 0
  const current = Number(totals[stat] || 0)
  const baseline = Number(state.baseline_stats?.[stat] || 0)
  return Math.max(0, current - baseline)
}

function completedQuestCount (rows, state, totals) {
  let count = 0
  rows.forEach(row => {
    if (questProgress(row, state, totals) >= targetAmount(row)) count += 1
  })
  return count
}

export function dailyQuestState (repo, userId, runtime, epoch = Math.floor(Date.now() / 1000)) {
  const dayStart = startOfUtcDayEpoch(epoch)
  const totals = playerStatTotals(repo, userId)
  const rows = questRows(runtime)
  const milestones = milestoneRows(runtime)
  const state = normalizeState(repo.getState(userId, NS, 'state', null), dayStart, totals)

  if (repo.getState(userId, NS, 'state', null)?.day_start !== dayStart) {
    repo.setState(userId, NS, 'state', state)
  }

  const quests = rows.map((row, index) => {
    const id = questId(row, index)
    const target = targetAmount(row)
    const progress = Math.min(target, questProgress(row, state, totals))
    // DailyQuestModel: {id, quest_id, progress, claimed, points, go_to};
    // target/completed são extras que o cliente ignora.
    return {
      ...row,
      id,
      quest_id: id,
      progress,
      claimed: state.claimed_quests.includes(id),
      go_to: row?.go_to ?? row?.go_to_hint,
      target,
      completed: progress >= target
    }
  })

  const completed = completedQuestCount(rows, state, totals)
  const milestoneWire = milestones.map((row, index) => {
    const id = questId(row, index)
    const target = milestoneTarget(row)
    // DailyQuestMilestoneModel: {id, milestone_id, points_required, claimed, rewards}
    return {
      ...row,
      id,
      milestone_id: id,
      points_required: target,
      claimed: state.claimed_milestones.includes(id),
      progress: Math.min(target, completed),
      target,
      completed: completed >= target
    }
  })

  return {
    day_start_epoch: dayStart,
    day_end_epoch: dayStart + 86400,
    quests,
    milestones: milestoneWire
  }
}

export function claimDailyQuest (repo, userId, runtime, requestedId, epoch = Math.floor(Date.now() / 1000)) {
  const current = dailyQuestState(repo, userId, runtime, epoch)
  const quest = current.quests.find(row => String(row.id) === String(requestedId))
  if (!quest) return { ok: false, reason: 'quest-not-found' }
  if (!quest.completed) return { ok: false, reason: 'quest-not-complete' }
  if (quest.claimed) return { ok: false, reason: 'already-claimed' }

  const grants = []
  repo.tx(() => {
    for (const reward of rewardRows(quest)) {
      grants.push(giveGameResource(repo, userId, reward, runtime).wire)
    }
    const state = normalizeState(repo.getState(userId, NS, 'state', null), current.day_start_epoch, playerStatTotals(repo, userId))
    state.claimed_quests = [...new Set([...state.claimed_quests, quest.id])]
    repo.setState(userId, NS, 'state', state)
  })
  return { ok: true, resources: grants, quest_id: quest.id }
}

export function claimDailyQuestMilestone (repo, userId, runtime, requestedId, epoch = Math.floor(Date.now() / 1000)) {
  const current = dailyQuestState(repo, userId, runtime, epoch)
  const milestone = current.milestones.find(row => String(row.id) === String(requestedId))
  if (!milestone) return { ok: false, reason: 'milestone-not-found' }
  if (!milestone.completed) return { ok: false, reason: 'milestone-not-complete' }
  if (milestone.claimed) return { ok: false, reason: 'already-claimed' }

  const grants = []
  repo.tx(() => {
    for (const reward of rewardRows(milestone)) {
      grants.push(giveGameResource(repo, userId, reward, runtime).wire)
    }
    const state = normalizeState(repo.getState(userId, NS, 'state', null), current.day_start_epoch, playerStatTotals(repo, userId))
    state.claimed_milestones = [...new Set([...state.claimed_milestones, milestone.id])]
    repo.setState(userId, NS, 'state', state)
  })
  return { ok: true, resources: grants, milestone_id: milestone.id }
}

function requestedQuestId (body) {
  return body?.quest_id ?? body?.quest ?? body?.id ?? body?.rid
}

function requestedMilestoneId (body) {
  return body?.milestone_id ?? body?.milestone ?? body?.id ?? body?.rid
}

export function handleQuestRequest (path, body, userId, repo, runtime) {
  if (path === '/game/quests/get-daily-quests') {
    return { data: dailyQuestState(repo, userId, runtime) }
  }

  if (path === '/game/quests/claim-daily-quest' || path === '/game/quests/claim') {
    const id = requestedQuestId(body)
    if (id === undefined || id === null) return { error: [400, 2200] }
    const result = claimDailyQuest(repo, userId, runtime, id)
    if (!result.ok) return { error: [400, 2000, { reason: result.reason }] }
    // Response de claim declara apenas {resources} (ClaimMilestoneResponse);
    // quest_id/milestone_id não estão no DTO do cliente.
    return { data: { resources: result.resources } }
  }

  if (path === '/game/quests/claim-daily-milestone' || path === '/game/quests/claim-milestone') {
    const id = requestedMilestoneId(body)
    if (id === undefined || id === null) return { error: [400, 2200] }
    const result = claimDailyQuestMilestone(repo, userId, runtime, id)
    if (!result.ok) return { error: [400, 2000, { reason: result.reason }] }
    return { data: { resources: result.resources } }
  }

  return null
}
