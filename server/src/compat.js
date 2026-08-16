import { handleBattlePassRequest } from './battle-pass.js'

function startOfUtcDayEpoch () {
  const now = new Date()
  return Math.floor(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()) / 1000)
}

function playerLevelWire (user) {
  return {
    current: user.level,
    max: user.level,
    details_current: {},
    details_next: {}
  }
}

export function handleCompatRequest (path, body, userId, repo, runtime) {
  const battlePass = handleBattlePassRequest(path, body, userId, repo, runtime)
  if (battlePass) return battlePass

  if (path === '/game/daily-rewards/claim') {
    // The preserved public backend also leaves claim reward calculation as a
    // TODO. Keep an explicit persistent claim marker instead of letting this
    // fall through research mode; actual rewards will be filled from GameData.
    const state = repo.getState(userId, 'daily-rewards', 'state', {
      day: 1,
      last_claim: 0,
      pending: [],
      claimed: []
    })
    const now = Math.floor(Date.now() / 1000)
    repo.setState(userId, 'daily-rewards', 'state', { ...state, last_claim: now })
    return { data: { resources: [] } }
  }

  if (path === '/game/quests/get-daily-quests') {
    const dayStart = startOfUtcDayEpoch()
    return {
      data: {
        day_start_epoch: dayStart,
        day_end_epoch: dayStart + 86400,
        milestones: [],
        quests: []
      }
    }
  }

  if (path === '/game/player/level-up') {
    const user = repo.userById(userId)
    if (!user) return { error: [401, 2101] }

    return { data: { level: playerLevelWire(user), pending_game_data_logic: true } }
  }

  return null
}
