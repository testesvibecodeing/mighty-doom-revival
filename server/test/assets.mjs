import assert from 'node:assert/strict'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { panelResourceByRef, panelResourceInfo, resetGameIcons, useGameIconsFrom } from '../src/assets.js'
import { publicPack } from '../src/admin.js'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const work = mkdtempSync(resolve(tmpdir(), 'mighty-doom-assets-'))

// Manifest mínimo simulando a extração do APK (scripts/extract-game-icons.py)
writeFileSync(resolve(work, 'manifest.json'), JSON.stringify({
  source: { file: 'test.apk', sha256: '0'.repeat(64) },
  count: 6,
  files: {
    store_coinssingle_01: { w: 256, h: 256 },
    wpn_icon_heavycannon_01: { w: 197, h: 146 },
    slay_icon_events_slayergold_01: { w: 152, h: 175 },
    gear_icon_barrage_helmet_01: { w: 128, h: 128 },
    lch_icon_explosive_fraggrenade_01: { w: 130, h: 130 },
    skin_icon_plasmarifleastro_01: { w: 160, h: 160 }
  }
}))
// PNG no diretório fora do manifest (artwork versionada pelo CI convivendo
// com a extração local) também precisa resolver.
writeFileSync(resolve(work, 'ult_icon_bfg_01.png'), 'png')

// Runtime sem game-data: o caso de instância que ainda não tem snapshot.
const runtime = { gameData: null, index: { byId: new Map(), byTag: new Map() } }

try {
  useGameIconsFrom(work)

  // --- tag canônica resolve nome + ícone do jogo mesmo sem game-data ---
  const coins = panelResourceByRef('coins', runtime, 'currency')
  assert.equal(coins.name, 'Coins')
  assert.equal(coins.icon, '/assets/img/game/store_coinssingle_01.png')
  assert.equal(coins.kind, 'currency')

  const cannon = panelResourceByRef('heavy_cannon', runtime, 'weapon')
  assert.equal(cannon.name, 'Heavy Cannon')
  assert.equal(cannon.icon, '/assets/img/game/wpn_icon_heavycannon_01.png')

  // PNG presente no diretório mas fora do manifest resolve pelo scan
  const bfg = panelResourceByRef('bfg', runtime, 'ultimate')
  assert.equal(bfg.icon, '/assets/img/game/ult_icon_bfg_01.png')

  // --- tags reais do game-data 1.13.1 (<nome>_slayer, launcher_, key_) ---
  const gold = panelResourceByRef('gold_slayer', runtime, null)
  assert.equal(gold.name, 'Gold Slayer')
  assert.equal(gold.icon, '/assets/img/game/slay_icon_events_slayergold_01.png')
  assert.equal(gold.kind, 'slayer')

  const grenade = panelResourceByRef('launcher_frag_grenade', runtime, 'launcher')
  assert.equal(grenade.name, 'Frag Grenade')
  assert.equal(grenade.icon, '/assets/img/game/lch_icon_explosive_fraggrenade_01.png')

  const weaponKey = panelResourceByRef('key_weapon_crate', runtime, 'currency')
  assert.equal(weaponKey.name, 'Chave de caixa de arma')
  assert.equal(weaponKey.icon, '/assets/img/kinds/currency.svg')

  const gearHelmet = panelResourceByRef('helmet_barrage', runtime, 'equipment')
  assert.equal(gearHelmet.name, 'Barrage Capacete')
  assert.equal(gearHelmet.icon, '/assets/img/game/gear_icon_barrage_helmet_01.png')

  // grafia legada <set>_<peça> continua funcionando
  const legacyHelmet = panelResourceByRef('barrage_helmet', runtime, 'equipment')
  assert.equal(legacyHelmet.name, 'Barrage Capacete')
  assert.equal(legacyHelmet.icon, '/assets/img/game/gear_icon_barrage_helmet_01.png')

  // shards de slayer: nome resolve, arte cai no fallback da categoria
  const shards = panelResourceByRef('shard_gold', runtime, 'currency')
  assert.equal(shards.name, 'Shards Gold Slayer')
  assert.equal(shards.icon, '/assets/img/kinds/currency.svg')

  // cosmético de arma: cosmetic_<arma>_<skin> -> skin_icon_<arma-junto>_<skin>_01
  const skin = panelResourceByRef('cosmetic_plasma_rifle_astro', runtime, 'cosmetic')
  assert.equal(skin.name, 'Plasma Rifle — skin Astro')
  assert.equal(skin.icon, '/assets/img/game/skin_icon_plasmarifleastro_01.png')

  // cosmético de slayer: reusa a arte do slayer base
  const slayerSkin = panelResourceByRef('cosmetic_gold_slayer_platinum', runtime, 'cosmetic')
  assert.equal(slayerSkin.icon, '/assets/img/game/slay_icon_events_slayergold_01.png')

  // --- tag desconhecida cai no ícone da categoria, sem quebrar ---
  const unknown = panelResourceByRef('moeda_secreta_x', runtime, 'currency')
  assert.equal(unknown.icon, '/assets/img/kinds/currency.svg')
  assert.equal(unknown.fallback, '/assets/img/kinds/currency.svg')

  // --- rid sem game-data: nome genérico + ícone da categoria ---
  const ridInfo = panelResourceInfo(200, runtime, 'weapon')
  assert.equal(ridInfo.name, 'Recurso 200')
  assert.equal(ridInfo.icon, '/assets/img/kinds/weapon.svg')

  // --- preview do pack de exemplo exibe ícones com tag pendente ---
  const pack = {
    id: 900001,
    tag: 'revival_starter_weapon_pack',
    active: true,
    cost: [{ resource: 'coins', kind: 'currency', amount: 2500 }],
    contents: [
      { resource: 'heavy_cannon', kind: 'weapon', amount: 1, level: 2, tier: 1 },
      { resource: 'launcher_frag_grenade', kind: 'launcher', amount: 1 }
    ]
  }
  const preview = publicPack(pack, runtime)
  assert.equal(preview.preview.cost[0].name, 'Coins')
  assert.equal(preview.preview.cost[0].icon, '/assets/img/game/store_coinssingle_01.png')
  assert.equal(preview.preview.cost[0].rid, null)
  assert.equal(preview.preview.contents[0].name, 'Heavy Cannon')
  assert.equal(preview.preview.contents[0].amount, 1)
  assert.equal(preview.preview.contents[1].name, 'Frag Grenade')
  assert.equal(preview.preview.contents[1].icon, '/assets/img/game/lch_icon_explosive_fraggrenade_01.png')

  // --- sem extração nenhuma, tudo cai no fallback e nada quebra ---
  useGameIconsFrom(resolve(work, 'nao-existe'))
  const bare = publicPack(pack, runtime)
  assert.equal(bare.preview.cost[0].icon, '/assets/img/kinds/currency.svg')
  assert.equal(bare.preview.contents[0].icon, '/assets/img/kinds/weapon.svg')

  console.log('Mighty DOOM Revival assets test: PASS')
} finally {
  resetGameIcons()
  rmSync(work, { recursive: true, force: true })
}
