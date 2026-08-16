import { chapterProgressionWire } from './chapters.js'
import { inventoryWire } from './game-data-model.js'
import { talentsWire } from './progression.js'
import { playerStatsWire } from './stats.js'
import { tutorialProgressionWire } from './tutorial.js'

function nowSeconds () {
  return Math.floor(Date.now() / 1000)
}

export function playerUserDataWire (repo, user, runtime) {
  const settings = repo.settings(user.id)

  return {
    user_data: {
      inventory: inventoryWire(repo, user.id, runtime),
      chapter_progression: chapterProgressionWire(repo, user.id),
      talent_progression: talentsWire(repo, user.id),
      tutorial_progression: tutorialProgressionWire(repo, user.id),
      account_age: Math.max(0, nowSeconds() - user.created_at),
      player: {
        level: {
          current: user.level,
          max: user.level,
          details_current: {},
          details_next: {}
        },
        chapter_progression: user.chapter_progression,
        stats: playerStatsWire(repo, user.id)
      },
      total_attempt_count: user.attempt_count,
      player_settings: settings
        ? {
            blood_built_in: settings.blood_built_in,
            blood_cosmetic: settings.blood_cosmetic,
            confirm_gem_spend: Boolean(settings.confirm_gem_spend),
            skin_randomization: settings.skin_randomization
          }
        : null,
      last_login: nowSeconds()
    }
  }
}
