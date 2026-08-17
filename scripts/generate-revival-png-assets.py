#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import shutil
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
REVIVAL = ROOT / 'server' / 'public' / 'assets' / 'img' / 'revival'
GAME = ROOT / 'server' / 'public' / 'assets' / 'img' / 'game'
W = H = 512

for folder in ['resources', 'crates', 'weapons', 'gear', 'cosmetics', 'frames']:
    (REVIVAL / folder).mkdir(parents=True, exist_ok=True)
GAME.mkdir(parents=True, exist_ok=True)

for stale in ['.keep', 'NOTICE.txt', '_integration-plan.md', '_why-no-preview.txt', '_staging-complete.txt', '_binary-upload-needed.txt']:
    target = REVIVAL / stale
    if target.exists():
        target.unlink()


def canvas():
    return Image.new('RGBA', (W, H), (0, 0, 0, 0))


def glow(draw, center, radius, color, alpha=80):
    x, y = center
    for factor, a in [(1.0, alpha), (.72, int(alpha * .55)), (.44, int(alpha * .3))]:
        r = int(radius * factor)
        draw.ellipse((x-r, y-r, x+r, y+r), fill=color + (a,))


def save(img, category, name):
    path = REVIVAL / category / f'{name}.png'
    img.save(path, 'PNG', optimize=True)
    return path


def weapon(name, kind):
    img = canvas(); d = ImageDraw.Draw(img, 'RGBA')
    glow(d, (260, 245), 150, (255, 80, 25), 48)
    fill = (25, 25, 30, 255); hot = (255, 100, 40, 255); gold = (255, 210, 120, 255)
    if kind == 'mg':
        d.polygon([(90,280),(280,220),(380,225),(432,200),(450,220),(400,250),(388,290),(300,300),(220,330),(95,315)], fill=fill, outline=hot)
        d.rectangle((150,300,190,380), fill=fill, outline=hot, width=6); d.rectangle((370,245,470,270), fill=(220,50,30,255), outline=gold, width=5)
    elif kind == 'shotgun':
        d.polygon([(85,280),(255,250),(420,240),(440,255),(320,290),(100,320)], fill=fill, outline=hot)
        d.rectangle((190,290,230,375), fill=fill, outline=hot, width=6); d.rectangle((350,246,470,270), fill=(235,80,35,255), outline=gold, width=5)
    elif kind == 'plasma':
        d.polygon([(100,290),(235,240),(390,220),(445,238),(425,280),(270,310),(120,320)], fill=fill, outline=(130,120,255,255))
        d.rectangle((150,300,185,370), fill=fill, outline=(130,120,255,255), width=6)
        for x in [285,315,345]: d.ellipse((x,238,x+22,260), fill=(95,220,255,255))
    elif kind == 'rocket':
        d.polygon([(80,295),(175,255),(360,225),(450,245),(420,285),(220,320),(95,320)], fill=fill, outline=hot)
        d.rectangle((150,305,190,380), fill=fill, outline=hot, width=6); d.rectangle((365,238,472,272), fill=(235,80,35,255), outline=gold, width=5)
    elif kind == 'sniper':
        d.polygon([(70,290),(245,255),(425,245),(455,255),(450,275),(240,300),(80,310)], fill=fill, outline=(120,170,255,255))
        d.rectangle((180,300,210,365), fill=fill, outline=(120,170,255,255), width=6); d.rectangle((250,220,310,245), fill=(30,30,30,255), outline=(120,170,255,255), width=5)
    else:
        d.rounded_rectangle((110,215,370,320), radius=26, fill=fill, outline=hot, width=6)
        d.rectangle((330,235,465,290), fill=(50,50,55,255), outline=hot, width=6)
        for r in [0,12,24]: d.ellipse((400-r,215-r,510+r,325+r), outline=(255,120,40,255), width=6)
        d.rectangle((180,310,225,395), fill=fill, outline=hot, width=6)
    return save(img, 'weapons', name)

img=canvas(); d=ImageDraw.Draw(img,'RGBA'); glow(d,(256,250),150,(255,70,20),85)
d.polygon([(256,50),(360,170),(320,410),(190,435),(115,220)], fill=(180,20,15,255), outline=(255,190,70,255))
d.line((256,50,256,430), fill=(255,130,80,220), width=7); d.line((140,220,256,160,350,175), fill=(255,130,80,220), width=6); d.line((190,435,256,330,320,410), fill=(255,130,80,220), width=6)
save(img,'resources','revival_crystal')

img=canvas(); d=ImageDraw.Draw(img,'RGBA'); glow(d,(256,256),140,(255,160,20),65)
d.ellipse((90,90,422,422), fill=(120,72,10,255), outline=(255,205,90,255), width=18); d.ellipse((120,120,392,392), fill=(185,110,20,255), outline=(255,230,120,255), width=10)
d.line([(220,170),(190,230),(220,300),(256,320),(292,300),(322,230),(292,170)], fill=(90,40,5,255), width=18, joint='curve'); d.ellipse((222,220,246,244), fill=(240,190,70,255)); d.ellipse((266,220,290,244), fill=(240,190,70,255)); d.rectangle((232,270,280,292), fill=(90,40,5,255))
save(img,'resources','slayer_coin')

img=canvas(); d=ImageDraw.Draw(img,'RGBA'); glow(d,(256,256),150,(40,120,255),65)
d.polygon([(180,180),(330,180),(330,330),(180,330)], fill=(30,70,180,180), outline=(120,220,255,255)); d.polygon([(330,180),(390,140),(390,290),(330,330)], fill=(25,55,140,160), outline=(120,220,255,255)); d.polygon([(180,180),(240,140),(390,140),(330,180)], fill=(60,100,220,140), outline=(120,220,255,255))
d.line((255,140,255,330), fill=(180,240,255,220), width=6); d.line((180,255,330,255), fill=(180,240,255,220), width=6)
save(img,'resources','energy_cell')

img=canvas(); d=ImageDraw.Draw(img,'RGBA'); glow(d,(256,256),140,(160,70,255),70)
d.polygon([(256,80),(390,350),(122,350)], fill=(90,30,150,180), outline=(220,160,255,255)); d.polygon([(256,125),(342,320),(170,320)], fill=(170,70,255,120), outline=(245,210,255,180)); d.line((256,125,256,320), fill=(245,210,255,180), width=5)
save(img,'resources','void_token')

img=canvas(); d=ImageDraw.Draw(img,'RGBA'); glow(d,(256,256),140,(255,140,30),50)
d.rounded_rectangle((110,220,320,290), radius=25, fill=(210,120,20,255), outline=(255,220,140,255), width=8); d.ellipse((75,190,175,320), outline=(255,220,140,255), width=18); d.rectangle((310,220,390,250), fill=(210,120,20,255), outline=(255,220,140,255), width=8); d.rectangle((350,245,390,275), fill=(210,120,20,255), outline=(255,220,140,255), width=8); d.rectangle((330,255,360,300), fill=(210,120,20,255), outline=(255,220,140,255), width=8)
save(img,'resources','ember_key')

for name, base in [('standard_crate',(90,90,90)),('epic_crate',(120,40,180)),('legendary_crate',(190,110,20))]:
    img=canvas(); d=ImageDraw.Draw(img,'RGBA'); glow(d,(256,256),150,(min(base[0]+40,255),min(base[1]+60,255),min(base[2]+40,255)),55)
    d.polygon([(145,180),(367,180),(367,360),(145,360)], fill=base+(255,), outline=(255,220,120,220)); d.polygon([(145,180),(195,130),(417,130),(367,180)], fill=tuple(min(c+30,255) for c in base)+(255,), outline=(255,220,120,220)); d.polygon([(367,180),(417,130),(417,310),(367,360)], fill=tuple(max(c-20,0) for c in base)+(255,), outline=(255,220,120,220)); d.rectangle((220,230,290,295), fill=(25,20,15,255), outline=(255,140,40,255), width=8); d.line((256,180,256,360), fill=(20,20,20,120), width=8)
    save(img,'crates',name)

rarities={'common':(160,160,160),'uncommon':(85,216,121),'rare':(74,165,255),'epic':(165,108,255),'legendary':(255,173,40),'mythic':(255,76,53)}
for name,col in rarities.items():
    img=canvas(); d=ImageDraw.Draw(img,'RGBA'); d.rounded_rectangle((40,40,472,472), radius=34, outline=col+(255,), width=18); d.rounded_rectangle((58,58,454,454), radius=28, outline=col+(120,), width=4); save(img,'frames',f'frame_{name}')

weapon('weapon_hellfire_mg','mg'); weapon('weapon_bone_crusher','shotgun'); weapon('weapon_void_plasma','plasma'); weapon('weapon_inferno_launcher','rocket'); weapon('weapon_soul_piercer','sniper'); weapon('weapon_doom_cannon','cannon')

img=canvas(); d=ImageDraw.Draw(img,'RGBA'); glow(d,(256,256),130,(255,70,20),45); d.rounded_rectangle((150,150,360,360), radius=60, fill=(28,28,34,255), outline=(255,110,35,255), width=10); d.rectangle((220,110,290,160), fill=(60,60,70,255), outline=(255,110,35,255), width=8); d.line((190,190,322,322), fill=(255,100,40,255), width=10); d.line((322,190,190,322), fill=(255,100,40,255), width=10); save(img,'weapons','launcher_frag_grenade')

img=canvas(); d=ImageDraw.Draw(img,'RGBA'); glow(d,(256,256),150,(255,90,25),50); d.polygon([(270,60),(315,160),(282,415),(228,415),(205,160)], fill=(180,35,20,255), outline=(255,210,120,255)); d.rectangle((220,415,295,445), fill=(55,35,20,255), outline=(255,170,90,255), width=6); d.rectangle((170,445,345,470), fill=(95,55,25,255), outline=(255,170,90,255), width=6); save(img,'weapons','ultimate_crucible')

img=canvas(); d=ImageDraw.Draw(img,'RGBA'); glow(d,(256,245),150,(255,80,20),48); d.rounded_rectangle((150,120,360,380), radius=80, fill=(35,35,40,255), outline=(255,90,30,255), width=10); d.polygon([(170,215),(250,185),(340,215),(310,280),(200,280)], fill=(20,20,24,255), outline=(255,90,30,255)); d.ellipse((205,220,238,248), fill=(255,120,30,255)); d.ellipse((272,220,305,248), fill=(255,120,30,255)); d.rectangle((220,300,290,330), fill=(18,18,22,255), outline=(255,90,30,255), width=6); save(img,'gear','slayer_helm')

img=canvas(); d=ImageDraw.Draw(img,'RGBA'); glow(d,(256,256),145,(255,75,20),48); d.polygon([(170,120),(342,120),(395,220),(350,400),(160,400),(120,220)], fill=(38,36,42,255), outline=(255,90,30,255)); d.polygon([(215,150),(295,150),(320,220),(300,330),(210,330),(190,220)], fill=(22,22,26,255), outline=(255,130,40,255)); d.ellipse((235,240,277,282), fill=(255,110,30,255)); save(img,'gear','slayer_armor')

img=canvas(); d=ImageDraw.Draw(img,'RGBA'); glow(d,(256,256),140,(255,70,20),45); d.polygon([(150,210),(245,180),(370,210),(355,330),(280,380),(170,340)], fill=(35,35,40,255), outline=(255,95,35,255))
for x in [175,220,265,310]: d.rectangle((x,145,x+35,220), fill=(45,45,50,255), outline=(255,95,35,255), width=6)
save(img,'gear','rage_gauntlet')

img=canvas(); d=ImageDraw.Draw(img,'RGBA'); glow(d,(256,256),140,(255,70,20),45); d.polygon([(210,110),(315,120),(330,260),(410,300),(420,360),(120,360),(115,300),(190,260)], fill=(36,36,40,255), outline=(255,95,35,255)); d.rectangle((115,300,420,335), fill=(60,28,20,255), outline=(255,140,40,255), width=6); save(img,'gear','hell_boot')

img=canvas(); d=ImageDraw.Draw(img,'RGBA'); glow(d,(256,230),170,(255,90,10),70); d.polygon([(256,80),(310,130),(350,210),(344,320),(300,400),(210,400),(168,320),(160,220),(202,135)], fill=(50,20,14,255), outline=(255,120,40,255)); d.ellipse((240,170,272,210), fill=(255,90,20,255)); d.ellipse((280,170,312,210), fill=(255,90,20,255)); d.polygon([(256,130),(280,175),(260,210),(245,175)], fill=(255,140,50,180)); save(img,'cosmetics','skin_infernal_slayer')

img=canvas(); d=ImageDraw.Draw(img,'RGBA'); glow(d,(256,256),150,(255,150,20),45); d.ellipse((130,120,382,372), fill=(60,35,18,255), outline=(255,190,90,255), width=10); d.polygon([(256,160),(284,225),(354,230),(300,275),(320,345),(256,305),(192,345),(212,275),(158,230),(228,225)], fill=(255,180,50,255), outline=(255,220,140,255)); save(img,'cosmetics','entitlement_benefit')

assets = {
    'revival_crystal': ('resources','resource','Revival Crystal'), 'slayer_coin': ('resources','resource','Slayer Coin'), 'energy_cell': ('resources','resource','Energy Cell'), 'void_token': ('resources','resource','Void Token'), 'ember_key': ('resources','resource','Ember Key'),
    'standard_crate': ('crates','crate','Standard Crate'), 'epic_crate': ('crates','crate','Epic Crate'), 'legendary_crate': ('crates','crate','Legendary Crate'),
    'weapon_hellfire_mg': ('weapons','weapon','Hellfire MG'), 'weapon_bone_crusher': ('weapons','weapon','Bone Crusher'), 'weapon_void_plasma': ('weapons','weapon','Void Plasma'), 'weapon_inferno_launcher': ('weapons','weapon','Inferno Launcher'), 'weapon_soul_piercer': ('weapons','weapon','Soul Piercer'), 'weapon_doom_cannon': ('weapons','weapon','Revival Heavy Cannon'), 'launcher_frag_grenade': ('weapons','launcher','Frag Grenade'), 'ultimate_crucible': ('weapons','ultimate','Energy Blade'),
    'slayer_helm': ('gear','equipment','Slayer Helm'), 'slayer_armor': ('gear','equipment','Slayer Armor'), 'rage_gauntlet': ('gear','equipment','Rage Gauntlet'), 'hell_boot': ('gear','equipment','Hell Boot'),
    'skin_infernal_slayer': ('cosmetics','cosmetic','Infernal Slayer Skin'), 'entitlement_benefit': ('cosmetics','entitlement','Benefit'),
    **{f'frame_{k}': ('frames','frame',k.title()) for k in rarities}
}
manifest = {'version': 1, 'license_note': 'Original Revival artwork. No official game assets included.', 'base_url': '/assets/img/revival', 'assets': {k: {'file': f'{folder}/{k}.png', 'category': cat, 'label': label} for k,(folder,cat,label) in assets.items()}}
(REVIVAL / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
(REVIVAL / 'README.md').write_text('# Revival original PNG artwork\n\nGenerated original artwork for the Revival project. No extracted game sprites, screenshots, logos or official art are included.\n', encoding='utf-8')

aliases = {
    'store_crystalsingle_01': 'resources/revival_crystal.png', 'store_coinssingle_01': 'resources/slayer_coin.png', 'store_slayerorbssingle_01': 'resources/void_token.png', 'store_tech_single_01': 'resources/void_token.png',
    'store_equipmentcrate_key_single_01': 'resources/ember_key.png', 'store_weaponcrate_key_single_01': 'resources/ember_key.png', 'store_specialcrate_key_single_01': 'resources/ember_key.png', 'store_token_allrandom_tier_01': 'resources/void_token.png',
    'store_tokensingle_helmet_01': 'resources/void_token.png', 'store_tokensingle_chestplate_01': 'resources/void_token.png', 'store_tokensingle_boots_01': 'resources/void_token.png', 'store_tokensingle_gloves_01': 'resources/void_token.png', 'store_tokensingle_launcher_01': 'resources/void_token.png', 'store_tokensingle_ultimate_01': 'resources/void_token.png', 'icon_ability_xp_up_major': 'resources/energy_cell.png',
    'wpn_icon_heavycannon_01': 'weapons/weapon_doom_cannon.png', 'wpn_icon_combatshotgun_01': 'weapons/weapon_bone_crusher.png', 'wpn_icon_supershotgun_01': 'weapons/weapon_bone_crusher.png', 'wpn_icon_plasmarifle_01': 'weapons/weapon_void_plasma.png', 'wpn_icon_chaingun_01': 'weapons/weapon_hellfire_mg.png', 'wpn_icon_rocketlauncher_01': 'weapons/weapon_inferno_launcher.png', 'wpn_icon_ballista_01': 'weapons/weapon_soul_piercer.png', 'wpn_icon_gausscannon_01': 'weapons/weapon_soul_piercer.png', 'wpn_icon_burstrifle_01': 'weapons/weapon_hellfire_mg.png', 'wpn_icon_sentinelhammer_01': 'weapons/ultimate_crucible.png',
    'store_tokensingle_heavycannon_01': 'resources/void_token.png', 'store_tokensingle_combatshotgun_01': 'resources/void_token.png', 'store_tokensingle_supershotgun_01': 'resources/void_token.png', 'store_tokensingle_plasmarifle_01': 'resources/void_token.png', 'store_tokensingle_chaingun_01': 'resources/void_token.png', 'store_tokensingle_rocketlauncher_01': 'resources/void_token.png', 'store_tokensingle_ballista_01': 'resources/void_token.png', 'store_tokensingle_gausscannon_01': 'resources/void_token.png',
    'lch_icon_explosive_fraggrenade_01': 'weapons/launcher_frag_grenade.png', 'lch_icon_fire_flamebelch_01': 'weapons/weapon_inferno_launcher.png', 'lch_icon_ice_icebomb_01': 'weapons/launcher_frag_grenade.png', 'lch_icon_plasma_arcgrenade_01': 'weapons/launcher_frag_grenade.png', 'lch_icon_toxic_acidspit_01': 'weapons/launcher_frag_grenade.png',
    'ult_icon_bfg_01': 'weapons/ultimate_crucible.png', 'ult_icon_chainsaw_01': 'weapons/ultimate_crucible.png', 'ult_icon_crucible_01': 'weapons/ultimate_crucible.png', 'ult_icon_unmaykr_01': 'weapons/ultimate_crucible.png', 'ult_icon_samuraisword_01': 'weapons/ultimate_crucible.png',
    'crt_icon_weaponcrate_01': 'crates/standard_crate.png', 'crt_icon_equipmentcrate_01': 'crates/epic_crate.png', 'crt_icon_specialcrate_01': 'crates/legendary_crate.png', 'crt_icon_prizetrackcrate_01': 'crates/epic_crate.png', 'crt_icon_fireelementalcrate_01': 'crates/legendary_crate.png', 'crt_icon_iceelementalcrate_01': 'crates/epic_crate.png', 'crt_icon_toxicelementalcrate_01': 'crates/epic_crate.png', 'crt_icon_plasmaelementalcrate_01': 'crates/epic_crate.png', 'crt_icon_explosiveelementalcrate_01': 'crates/legendary_crate.png', 'crt_icon_adcrate_01': 'crates/standard_crate.png'
}

slayer_icons = ['slayerdefault','slayergold','slayercrimson','slayerclassicmarine','slayerzombie','slayerhailfire','slayerdoomicorn','slayerronin','slayerhoppingmad','slayerslaytriot','slayermarauder','slayergibbo','slayerdemonic','slayerjackoslayer','slayerpioneer','slayersanta','slayersurvivalist','slayerwintherin']
for icon in slayer_icons:
    aliases[f'slay_icon_events_{icon}_01'] = 'cosmetics/skin_infernal_slayer.png'

gear_sets = ['cultist','uac','demonic','exultian','hellfire','cryo','cyro','barrage','charged','radioactive','arc']
for set_name in gear_sets:
    aliases[f'gear_icon_{set_name}_helmet_01'] = 'gear/slayer_helm.png'
    aliases[f'gear_icon_{set_name}_torso_01'] = 'gear/slayer_armor.png'
    aliases[f'gear_icon_{set_name}_boots_01'] = 'gear/hell_boot.png'
    aliases[f'gear_icon_{set_name}_gloves_01'] = 'gear/rage_gauntlet.png'
aliases['gear_icon_allresist_gloves_01'] = 'gear/rage_gauntlet.png'

for alias_name, source_rel in aliases.items():
    shutil.copyfile(REVIVAL / source_rel, GAME / f'{alias_name}.png')

game_manifest = {'generated_by': 'scripts/generate-revival-png-assets.py', 'origin': 'Revival original artwork; technical alias filenames only', 'files': {name: {'file': f'{name}.png', 'source': source} for name, source in sorted(aliases.items())}}
(GAME / 'manifest.json').write_text(json.dumps(game_manifest, indent=2), encoding='utf-8')
(GAME / 'README.md').write_text('# Revival compatibility artwork\n\nTracked PNGs in this directory are original Revival artwork copied under technical catalog aliases so the existing asset resolver can use them. They are not extracted game assets. Running the local APK extractor may overwrite them on an operator machine.\n', encoding='utf-8')
print(f'Generated {len(assets)} original PNG assets and {len(aliases)} compatibility aliases.')
