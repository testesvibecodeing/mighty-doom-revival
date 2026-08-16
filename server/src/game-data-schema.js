function arrayOrEmpty (value) {
  return Array.isArray(value) ? value : []
}

export function resourcesList (gameData) {
  return arrayOrEmpty(gameData?.resources)
}

export function weaponsList (gameData) {
  return arrayOrEmpty(gameData?.weapons)
}

export function equipmentList (gameData) {
  return arrayOrEmpty(gameData?.equipment)
}

export function launchersList (gameData) {
  return arrayOrEmpty(gameData?.launchers)
}

export function energiesList (gameData) {
  return arrayOrEmpty(gameData?.energies)
}

export function ultimatesList (gameData) {
  return arrayOrEmpty(gameData?.ultimates)
}

export function slayersList (gameData) {
  return arrayOrEmpty(gameData?.slayers)
}

export function cosmeticsList (gameData) {
  return arrayOrEmpty(gameData?.cosmetics)
}

export function entitlementsList (gameData) {
  return arrayOrEmpty(gameData?.entitlements)
}

export function bundlesList (gameData) {
  return arrayOrEmpty(gameData?.bundles)
}

export function inventorySlots (gameData) {
  return arrayOrEmpty(gameData?.inventory?.slots)
}

export function tutorialSequences (gameData) {
  if (Array.isArray(gameData?.tutorial?.sequences)) return gameData.tutorial.sequences
  return arrayOrEmpty(gameData?.tutorial_sequences)
}

export function chaptersList (gameData) {
  if (Array.isArray(gameData?.chapter_mode?.chapters)) return gameData.chapter_mode.chapters
  return arrayOrEmpty(gameData?.chapters)
}

export function talentsList (gameData) {
  if (Array.isArray(gameData?.talents?.talents)) return gameData.talents.talents
  return arrayOrEmpty(gameData?.talents)
}

export function storeCatalogs (gameData) {
  if (Array.isArray(gameData?.store?.catalogs)) return gameData.store.catalogs
  return arrayOrEmpty(gameData?.store_catalogs)
}

export function storyBattlePasses (gameData) {
  if (Array.isArray(gameData?.story_battle_passes)) return gameData.story_battle_passes
  if (Array.isArray(gameData?.battle_pass_season_events)) return gameData.battle_pass_season_events
  return []
}

export function findById (list, id) {
  return arrayOrEmpty(list).find(value => value?.id === id || value?.rid === id) || null
}

export function findByTag (list, tag) {
  return arrayOrEmpty(list).find(value => value?.tag === tag) || null
}

export function resourceId (value) {
  if (Number.isInteger(value)) return value
  if (!value || typeof value !== 'object') return null
  if (Number.isInteger(value.rid)) return value.rid
  if (Number.isInteger(value.id)) return value.id
  if (value.resource !== undefined) return resourceId(value.resource)
  return null
}

export function archiveMode (runtime) {
  return runtime?.revival?.archive_mode !== false
}
