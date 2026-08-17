import { resolveResource } from './config.js'

// ---- Contrato extraído do global-metadata.dat v29 (2026-08-17) ----
// ArmoryApi: Get() e Upgrade(id, level) — 2 rotas game/armory/*.
// Upgrade sem Response DTO -> envelope puro. Config (DataObjects.Armory):
//   ArmoryConfig{unlockLevel, availability, upgrades}
//   ArmoryUpgrade{id, tag, availability, requiredRids, requiresAllRids,
//                levels: [ArmoryUpgradeLevel]}
//   ArmoryUpgradeLevel{cost, playerLevel, chapterProgress, effects}
// Wire do estado: ArmoryUpgradeModel{id, level}.
// CONFIRMADO por literal: nenhum override aqui — id/level são fallback snake
// do parâmetro C#. A VERIFICAR até captura do cliente: semântica exata do
// `level` do request (aqui: nível alvo 1-based, sequencial).

const NS = 'armory'

function asInt (value, fallback = null) {
  return Number.isInteger(value) ? value : fallback
}

function armoryConfig (runtime) {
  const config = runtime?.gameData?.armory
  return config && typeof config === 'object' ? config : {}
}

function upgradeRows (runtime) {
  return Array.isArray(armoryConfig(runtime).upgrades) ? armoryConfig(runtime).upgrades : []
}

function armoryLevels (repo, userId) {
  const saved = repo.getState(userId, NS, 'levels', {})
  return saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {}
}

// O cliente 1.13.1 faz foreach em ArmoryController.Init(upgrades); sem o
// array no wire a desserialização deixa null e a iteração NRE-derruba o boot
// da sessão logo após o registro/login — por isso sempre um array (vazio
// quando não há config, nunca ausente).
export function armoryUpgradesWire (repo, userId, runtime) {
  const levels = armoryLevels(repo, userId)
  return upgradeRows(runtime)
    .map(row => asInt(row?.id))
    .filter(id => id !== null)
    .map(id => ({ id, level: asInt(levels[String(id)]) ?? 0 }))
}

export function handleArmoryRequest (path, body, userId, repo, runtime) {
  if (path === '/game/armory/get') {
    return { data: { upgrades: armoryUpgradesWire(repo, userId, runtime) } }
  }

  if (path === '/game/armory/upgrade') {
    const upgradeId = asInt(body?.id)
    const targetLevel = asInt(body?.level)
    if (upgradeId === null) return { error: [400, 2200, { reason: 'upgrade-id-required' }] }
    if (targetLevel === null || targetLevel < 1) return { error: [400, 2200, { reason: 'level-required' }] }
    const definition = upgradeRows(runtime).find(row => asInt(row?.id) === upgradeId)
    if (!definition) return { error: [400, 2200, { reason: 'upgrade-not-found' }] }
    if (definition.availability !== undefined && Number(definition.availability) < 1) {
      return { error: [400, 2300, { reason: 'upgrade-unavailable' }] }
    }
    const levels = Array.isArray(definition.levels) ? definition.levels : []
    const levelConfig = levels[targetLevel - 1]
    if (!levelConfig) return { error: [400, 2300, { reason: 'max-level-reached' }] }
    const state = armoryLevels(repo, userId)
    const currentLevel = asInt(state[String(upgradeId)]) ?? 0
    if (targetLevel !== currentLevel + 1) return { error: [400, 2300, { reason: 'invalid-level' }] }

    const requiredProgress = asInt(levelConfig.chapter_progress)
    if (requiredProgress !== null) {
      const user = repo.userById(userId)
      if ((asInt(user?.chapter_progression) ?? 0) < requiredProgress) {
        return { error: [400, 2300, { reason: 'chapter-progress-required', required: requiredProgress }] }
      }
    }

    const costs = Array.isArray(levelConfig.cost) ? levelConfig.cost : []
    const resolved = []
    for (const cost of costs) {
      const rid = asInt(cost?.rid) ?? asInt(cost?.resource?.id) ?? resolveResource(cost?.resource, runtime)
      const amount = Number(cost?.amount)
      if (rid === null || !Number.isFinite(amount) || amount < 0) {
        return { error: [400, 2300, { reason: 'cost-config-invalid' }] }
      }
      if (repo.balance(userId, rid) < amount) return { error: [400, 2300, { reason: 'insufficient-currency' }] }
      resolved.push({ rid, amount })
    }

    repo.tx(() => {
      for (const cost of resolved) repo.addCurrency(userId, cost.rid, -cost.amount)
      state[String(upgradeId)] = targetLevel
      repo.setState(userId, NS, 'levels', state)
    })
    return { data: {} }
  }

  return null
}
