import { handleBattlePassRequest } from './battle-pass.js'
import { handleProgressionRequest } from './progression.js'
import { claimDailyReward, claimIdleReward, startOfUtcDayEpoch } from './rewards.js'

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

  const progression = handleProgressionRequest(path, body, userId, repo, runtime)
  if (progression) return progression

  if (path === '/game/daily-rewards/claim') {
    const result = claimDailyReward(repo, userId, runtime)
    if (!result.ok) return { error: [400, 2000, { reason: result.reason }] }
    return { data: { resources: result.resources, claimed_day: result.claimed_day } }
  }

  if (
    path === '/game/idle-rewards/claim' ||
    path === '/game/idle-rewards/claim-rewards'
  ) {
    const result = claimIdleReward(repo, userId, runtime)
    if (!result.ok) return { error: [400, 2000, { reason: result.reason, state: result.state }] }
    return { data: { resources: result.resources, periods: result.periods } }
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
