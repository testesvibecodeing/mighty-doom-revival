import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { classifyResource } from './game-data-model.js'

// Ícones de conteúdo do painel (/slayer e site).
//
// Duas camadas:
// 1. PNGs extraídos da cópia local do APK pelo scripts/extract-game-icons.py
//    em public/assets/img/game/ (gitignored — assets do jogo não entram no
//    Git), indexados pelo manifest.json gerado junto.
// 2. Fallback por categoria em public/assets/img/kinds/ (SVGs originais
//    deste projeto, sempre commitados).
//
// A resolução casa tag/nome do game-data (quando carregado) com o slug do
// ícone; sem game-data, a alias table abaixo ainda entrega nome e ícone
// corretos para o conteúdo canônico do jogo.

const SERVER_ROOT = resolve(import.meta.dirname, '..')
const GAME_ICONS_DIR = join(SERVER_ROOT, 'public', 'assets', 'img', 'game')
const GAME_ICONS_URL = '/assets/img/game'
const KIND_ICONS_URL = '/assets/img/kinds'

const KIND_ICONS = {
  currency: 'currency.svg',
  weapon: 'weapon.svg',
  equipment: 'equipment.svg',
  launcher: 'launcher.svg',
  energy: 'energy.svg',
  ultimate: 'ultimate.svg',
  slayer: 'slayer.svg',
  entitlement: 'entitlement.svg',
  cosmetic: 'cosmetic.svg',
  crate: 'pack.svg',
  pack: 'pack.svg'
}

export function kindIcon (kind) {
  const file = KIND_ICONS[kind] || 'pack.svg'
  return `${KIND_ICONS_URL}/${file}`
}

// Índice do manifest com cache simples: muda só quando o operador roda o
// script de extração de novo (e reinicia o servidor junto).
let gameIconsCache = null
let overrideDir = null

export function loadGameIcons (dir = null) {
  const target = dir || overrideDir || GAME_ICONS_DIR
  if (gameIconsCache && gameIconsCache.dir === target) return gameIconsCache
  const files = new Set()
  try {
    const manifest = JSON.parse(readFileSync(join(target, 'manifest.json'), 'utf8'))
    for (const name of Object.keys(manifest.files || {})) files.add(name)
  } catch {
    // sem manifest — o scan do diretório abaixo resolve o que houver
  }
  // O manifest nem sempre cobre o diretório: os PNGs originais versionados
  // (aliases técnicos gerados pelo CI) e a extração local do APK convivem
  // aqui. Quem estiver no disco resolve.
  try {
    for (const entry of readdirSync(target)) {
      if (entry.endsWith('.png')) files.add(entry.slice(0, -'.png'.length))
    }
  } catch {
    // diretório ausente — o painel cai no fallback por categoria
  }
  gameIconsCache = { dir: target, files }
  return gameIconsCache
}

// Para os testes: aponta a fonte de ícones para um diretório com manifest
// próprio e limpa o cache.
export function useGameIconsFrom (dir) {
  overrideDir = dir
  gameIconsCache = null
}

export function resetGameIcons () {
  overrideDir = null
  gameIconsCache = null
}

function slugKey (value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/['\s-]+/g, '_')
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '')
}

// Conteúdo canônico do jogo: nome exibido + slug do ícone extraído. As
// chaves são tags/nomes slugados ("heavy_cannon", "heavy cannon").
const ALIASES = {}
function alias (keys, display, icon, kind = null) {
  for (const key of keys) ALIASES[slugKey(key)] = { display, icon, kind }
}

// --- moedas e recursos da loja ---
alias(['coins', 'coin', 'gold'], 'Coins', 'store_coinssingle_01', 'currency')
alias(['crystals', 'crystal', 'gems', 'gem'], 'Crystals', 'store_crystalsingle_01', 'currency')
alias(['slayer_orbs', 'orbs', 'slayer_orb'], 'Slayer Orbs', 'store_slayerorbssingle_01', 'currency')
alias(['tech', 'science', 'research'], 'Tech', 'store_tech_single_01', 'currency')
alias(['keys', 'key', 'equipment_crate_key', 'equipment_key', 'key_equipment_crate'], 'Chave de caixa de equipamento', 'store_equipmentcrate_key_single_01', 'currency')
alias(['weapon_crate_key', 'weapon_key', 'key_weapon_crate'], 'Chave de caixa de arma', 'store_weaponcrate_key_single_01', 'currency')
alias(['special_crate_key', 'special_key', 'key_special_crate'], 'Chave de caixa especial', 'store_specialcrate_key_single_01', 'currency')
alias(['tokens', 'token', 'weapon_tokens'], 'Tokens de arma', 'store_token_allrandom_tier_01', 'currency')
alias(['skin_shards', 'shards', 'skin_unlock_shards'], 'Shards de skin', 'store_skinshards_01', 'currency')
alias(['xp_player', 'xp'], 'XP', 'icon_ability_xp_up_major', 'currency')
alias(['argent_energy', 'argent', 'token_slayer_argent-energy'], 'Argent Energy', 'store_argentenergy_01', 'energy')

// Tokens por peça de gear / launcher / ultimate (tags reais do game-data).
alias(['token_helmet'], 'Tokens de capacete', 'store_tokensingle_helmet_01', 'currency')
alias(['token_torso'], 'Tokens de peitoral', 'store_tokensingle_chestplate_01', 'currency')
alias(['token_boots'], 'Tokens de botas', 'store_tokensingle_boots_01', 'currency')
alias(['token_gloves'], 'Tokens de luvas', 'store_tokensingle_gloves_01', 'currency')
alias(['token_launcher'], 'Tokens de launcher', 'store_tokensingle_launcher_01', 'currency')
alias(['token_ultimate'], 'Tokens de ultimate', 'store_tokensingle_ultimate_01', 'currency')

// --- armas ---
alias(['heavy_cannon'], 'Heavy Cannon', 'wpn_icon_heavycannon_01', 'weapon')
alias(['combat_shotgun'], 'Combat Shotgun', 'wpn_icon_combatshotgun_01', 'weapon')
alias(['super_shotgun'], 'Super Shotgun', 'wpn_icon_supershotgun_01', 'weapon')
alias(['plasma_rifle'], 'Plasma Rifle', 'wpn_icon_plasmarifle_01', 'weapon')
alias(['chaingun'], 'Chaingun', 'wpn_icon_chaingun_01', 'weapon')
alias(['rocket_launcher'], 'Rocket Launcher', 'wpn_icon_rocketlauncher_01', 'weapon')
alias(['ballista'], 'Ballista', 'wpn_icon_ballista_01', 'weapon')
alias(['gauss_cannon'], 'Gauss Cannon', 'wpn_icon_gausscannon_01', 'weapon')
alias(['burst_rifle'], 'Burst Rifle', 'wpn_icon_burstrifle_01', 'weapon')
alias(['sentinel_hammer'], 'Sentinel Hammer', 'wpn_icon_sentinelhammer_01', 'weapon')

// --- launchers ---
alias(['frag_grenade', 'launcher_frag_grenade', 'grenade'], 'Frag Grenade', 'lch_icon_explosive_fraggrenade_01', 'launcher')
alias(['flame_belch', 'launcher_flame_belch'], 'Flame Belch', 'lch_icon_fire_flamebelch_01', 'launcher')
alias(['ice_bomb', 'launcher_ice_bomb'], 'Ice Bomb', 'lch_icon_ice_icebomb_01', 'launcher')
alias(['arc_grenade', 'launcher_arc_grenade'], 'Arc Grenade', 'lch_icon_plasma_arcgrenade_01', 'launcher')
alias(['acid_spit', 'launcher_acid_spit'], 'Acid Spit', 'lch_icon_toxic_acidspit_01', 'launcher')

// --- ultimates ---
alias(['bfg'], 'BFG', 'ult_icon_bfg_01', 'ultimate')
alias(['chainsaw'], 'Chainsaw', 'ult_icon_chainsaw_01', 'ultimate')
alias(['crucible'], 'Crucible', 'ult_icon_crucible_01', 'ultimate')
alias(['unmaykr'], 'Unmaykr', 'ult_icon_unmaykr_01', 'ultimate')
alias(['samurai_sword'], 'Samurai Sword', 'ult_icon_samuraisword_01', 'ultimate')

// --- slayers (tags reais do game-data 1.13.1: <nome>_slayer) ---
const SLAYERS = {
  mini_slayer_default: ['Slayer', 'slayerdefault'],
  gold_slayer: ['Gold Slayer', 'slayergold'],
  crimson_slayer: ['Crimson Slayer', 'slayercrimson'],
  classic_doom_marine: ['Classic Doom Marine', 'slayerclassicmarine'],
  zombie_slayer: ['Zombie Slayer', 'slayerzombie'],
  hailfire_slayer: ['Hailfire Slayer', 'slayerhailfire'],
  doomicorn_slayer: ['DOOMicorn Slayer', 'slayerdoomicorn'],
  samurai_slayer: ['Samurai Slayer', 'slayerronin'],
  hopping_mad_slayer: ['Hopping Mad Slayer', 'slayerhoppingmad'],
  slaytriot: ['Slaytriot Slayer', 'slayerslaytriot'],
  marauder_slayer: ['Marauder Slayer', 'slayermarauder'],
  gibbo_slayer: ['Gibbo Slayer', 'slayergibbo'],
  demonic_slayer: ['Demonic Slayer', 'slayerdemonic'],
  jackoslayer: ['Jack-O-Slayer', 'slayerjackoslayer'],
  pioneer_slayer: ['Pioneer Slayer', 'slayerpioneer'],
  santa_slayer: ['Santa Slayer', 'slayersanta'],
  survivalist_slayer: ['Survivalist Slayer', 'slayersurvivalist'],
  wintherin_slayer: ['Wintherin Slayer', 'slayerwintherin'],
  // grafias alternativas que operadores costumam digitar nos packs
  slayer_default: ['Slayer', 'slayerdefault'],
  slayer_gold: ['Gold Slayer', 'slayergold'],
  slayer_doomicorn: ['DOOMicorn Slayer', 'slayerdoomicorn'],
  slayer_santa: ['Santa Slayer', 'slayersanta'],
  slayer_jack_o_slayer: ['Jack-O-Slayer', 'slayerjackoslayer']
}
// Qualquer grafia de slayer -> sufixo do sprite (para skins de slayer).
const SLAYER_SPRITES = {}
for (const [tag, [display, icon]] of Object.entries(SLAYERS)) {
  const keys = [tag, display]
  if (tag === 'mini_slayer_default') keys.push('slayer_default', 'default_slayer')
  if (tag === 'classic_doom_marine') keys.push('slayer_classic_marine', 'classic_marine')
  for (const key of keys) SLAYER_SPRITES[slugKey(key)] = icon
  alias(keys, display, `slay_icon_events_${icon}_01`, 'slayer')
  // shards de skin de slayer (tags reais shard_<slayer>): mesmo nome, sem
  // arte própria na extração — cai no ícone da categoria.
  alias([`shard_${tag}`, `shard_${tag.replace(/_?slayer$/, '')}`], `Shards ${display}`, `store_shard_${icon}_01`, 'currency')
}

// Tokens por arma (tags reais token_<arma>): store_tokensingle_<arma>_01.
const WEAPON_TOKENS = {
  heavy_cannon: 'heavycannon', combat_shotgun: 'combatshotgun', shotgun: 'combatshotgun',
  super_shotgun: 'supershotgun', plasma_rifle: 'plasmarifle', chaingun: 'chaingun',
  rocket_launcher: 'rocketlauncher', ballista: 'ballista', gauss_cannon: 'gausscannon',
  burst_rifle: 'burstrifle', sentinel_hammer: 'sentinelhammer'
}
for (const [tag, tight] of Object.entries(WEAPON_TOKENS)) {
  alias([`token_${tag}`], `Tokens ${tag.replace(/_/g, ' ')}`, tight ? `store_tokensingle_${tight}_01` : 'store_token_allrandom_tier_01', 'currency')
}

// --- equipamento (tags reais: <peça>_<conjunto>) ---
const GEAR_SETS = {
  cultist: 'Cultist', uac: 'UAC', demonic: 'Demonic', exultian: 'Exultian',
  hellfire: 'Hellfire', cryo: 'Cryo', cyro: 'Cryo', barrage: 'Barrage',
  charged: 'Charged', radioactive: 'Radioactive', arc: 'Arc'
}
// peça na tag -> [rótulo, peça no nome do sprite]
const GEAR_PIECES = {
  helmet: ['Capacete', 'helmet'], chest: ['Peitoral', 'torso'],
  boots: ['Botas', 'boots'], gauntlets: ['Luvas', 'gloves'],
  gloves: ['Luvas', 'gloves'], torso: ['Peitoral', 'torso']
}
for (const [setKey, setName] of Object.entries(GEAR_SETS)) {
  for (const [pieceKey, [pieceName, spritePiece]] of Object.entries(GEAR_PIECES)) {
    alias([`${pieceKey}_${setKey}`, `${setKey}_${pieceKey}`, `${setName} ${pieceName}`], `${setName} ${pieceName}`, `gear_icon_${setKey}_${spritePiece}_01`, 'equipment')
  }
}
alias(['all_resist_gloves'], 'Luvas All Resist', 'gear_icon_allresist_gloves_01', 'equipment')

// --- crates / caixas ---
alias(['weapon_crate', 'weapon_box'], 'Caixa de arma', 'crt_icon_weaponcrate_01', 'crate')
alias(['equipment_crate', 'gear_crate'], 'Caixa de equipamento', 'crt_icon_equipmentcrate_01', 'crate')
alias(['special_crate'], 'Caixa especial', 'crt_icon_specialcrate_01', 'crate')
alias(['prize_track_crate'], 'Caixa de prize track', 'crt_icon_prizetrackcrate_01', 'crate')
alias(['fire_crate', 'fire_elemental_crate'], 'Caixa elemental de fogo', 'crt_icon_fireelementalcrate_01', 'crate')
alias(['ice_crate', 'ice_elemental_crate'], 'Caixa elemental de gelo', 'crt_icon_iceelementalcrate_01', 'crate')
alias(['toxic_crate', 'toxic_elemental_crate'], 'Caixa elemental de tóxico', 'crt_icon_toxicelementalcrate_01', 'crate')
alias(['plasma_crate', 'plasma_elemental_crate'], 'Caixa elemental de plasma', 'crt_icon_plasmaelementalcrate_01', 'crate')
alias(['explosive_crate', 'explosive_elemental_crate'], 'Caixa elemental explosiva', 'crt_icon_explosiveelementalcrate_01', 'crate')
alias(['ad_crate'], 'Caixa de anúncio', 'crt_icon_adcrate_01', 'crate')

// Prefixos de busca difusa por categoria: tentados quando a alias table e o
// índice direto não casam (ex.: skin de arma "bfg_astro" -> skin_icon_bfg_astro_01).
const KIND_PREFIXES = {
  weapon: ['wpn_icon_', 'wpn_icon_events_'],
  slayer: ['slay_icon_events_slayer', 'slay_icon_events_'],
  launcher: ['lch_icon_'],
  ultimate: ['ult_icon_', 'ult_icon_events_'],
  equipment: ['gear_icon_'],
  cosmetic: ['skin_icon_', 'slay_icon_events_'],
  crate: ['crt_icon_', 'offers_crate_']
}

function gameIconUrl (slug) {
  return `${GAME_ICONS_URL}/${slug}.png`
}

function findGameIcon (keys, kind) {
  const { files } = loadGameIcons()
  if (files.size === 0) return null

  const candidates = [...new Set(keys.filter(Boolean).map(slugKey))]
  // 1. alias table
  for (const key of candidates) {
    const hit = ALIASES[key]
    if (hit?.icon && files.has(hit.icon)) return gameIconUrl(hit.icon)
  }
  // 2. slug direto no índice (com sufixo _01 dos sprites)
  for (const key of candidates) {
    if (files.has(key)) return gameIconUrl(key)
    if (files.has(`${key}_01`)) return gameIconUrl(`${key}_01`)
  }
  // 3. difuso por categoria
  const prefixes = KIND_PREFIXES[kind] || []
  for (const key of candidates) {
    const tight = key.replace(/_/g, '')
    for (const prefix of prefixes) {
      const base = prefix + key
      const loose = prefix + tight
      for (const name of [base, `${base}_01`, loose, `${loose}_01`]) {
        if (files.has(name)) return gameIconUrl(name)
      }
    }
    // skin de arma/cosmético: "cosmetic_<arma>_<skin>" (ou "S02_<arma>_<skin>")
    // casa skin_icon_<arma-junto>_<skin>_01 (ex.: plasma_rifle_astro ->
    // skin_icon_plasmarifle_astro_01; bfg_white_rabbit -> skin_icon_bfg_whiterabbit_01,
    // com a skin grudada). Skin de slayer tem arte própria
    // (skin_icon_slayer<slayer>_<skin>_01) e cai na arte do slayer como último
    // recurso.
    if (kind === 'cosmetic' || kind === 'weapon') {
      const stripped = key.replace(/^cosmetic_/, '').replace(/^s\d+_/, '')
      const candidates = [`skin_icon_${stripped}`, `skin_icon_${stripped.replace(/_/g, '')}`]
      const parts = stripped.split('_')
      for (let cut = 1; cut < parts.length; cut++) {
        const w = parts.slice(0, cut).join('')
        const skin = parts.slice(cut).join('_')
        const skinTight = skin.replace(/_/g, '')
        candidates.push(`skin_icon_${w}_${skin}`, `skin_icon_${w}_${skinTight}`)
        const suffix = SLAYER_SPRITES[parts.slice(0, cut).join('_')]
        if (suffix) {
          candidates.push(`skin_icon_${suffix}_${skin}`, `skin_icon_${suffix}_${skinTight}`)
        }
      }
      for (const base of candidates) {
        if (files.has(base)) return gameIconUrl(base)
        if (files.has(`${base}_01`)) return gameIconUrl(`${base}_01`)
      }
      for (let cut = 1; cut < parts.length; cut++) {
        const suffix = SLAYER_SPRITES[parts.slice(0, cut).join('_')]
        if (suffix) {
          const own = `slay_icon_events_${suffix}_01`
          if (files.has(own)) return gameIconUrl(own)
        }
      }
    }
  }
  return null
}

// Resolve o que o painel mostra para um recurso: nome, ícone e categoria.
// Prioriza o game-data (tag/display_name); a alias table cobre o conteúdo
// canônico quando o game-data não está carregado.
function titleCase (value) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

// cosmetic_heavy_cannon_praetor -> "Heavy Cannon — skin Praetor"
function prettyCosmeticName (value) {
  const stripped = slugKey(value).replace(/^cosmetic_/, '').replace(/^s\d+_/, '')
  if (!stripped) return null
  for (const weaponTag of Object.keys(WEAPON_TOKENS)) {
    if (stripped.startsWith(`${weaponTag}_`)) {
      const base = ALIASES[weaponTag]?.display || titleCase(weaponTag)
      return `${base} — skin ${titleCase(stripped.slice(weaponTag.length + 1))}`
    }
  }
  for (const slayerTag of Object.keys(SLAYER_SPRITES)) {
    if (stripped.startsWith(`${slayerTag}_`)) {
      const base = ALIASES[slayerTag]?.display || titleCase(slayerTag)
      return `${base} — skin ${titleCase(stripped.slice(slayerTag.length + 1))}`
    }
  }
  return titleCase(stripped)
}

function displayName (raw) {
  const name = String(raw || '')
  if (/^cosmetic_/i.test(name) || /^s\d+_/i.test(name)) {
    return prettyCosmeticName(name) || name
  }
  return name
}

export function panelResourceInfo (rid, runtime, kindHint = null) {
  const definition = runtime.index.byId.get(Number(rid)) || null
  const tag = typeof definition?.tag === 'string' ? definition.tag : null
  const defName = String(definition?.display_name || definition?.name || definition?.key || '') || null
  const kind = kindHint || classifyResource(rid, runtime)

  const aliasHit = ALIASES[slugKey(tag)] || ALIASES[slugKey(defName)] || null
  const name = displayName(defName || aliasHit?.display || tag || `Recurso ${rid}`)
  const keys = [tag, defName].filter(Boolean)
  if (aliasHit?.display) keys.push(aliasHit.display)

  const fallback = kindIcon(kind)
  const icon = findGameIcon(keys, kind) || fallback
  return { name, icon, kind, tag, fallback }
}

// Mesma coisa para uma referência string (tag de pack que ainda não resolve
// para rid porque o game-data não está carregado nesta instância).
export function panelResourceByRef (ref, runtime, kindHint = null) {
  const aliasHit = ALIASES[slugKey(ref)] || null
  const aliasKind = aliasHit?.kind || kindHint || 'currency'
  const name = displayName(aliasHit?.display || String(ref))
  const fallback = kindIcon(aliasKind)
  const icon = findGameIcon([String(ref)], aliasKind) || fallback
  return { name, icon, kind: aliasKind, tag: String(ref), fallback }
}
