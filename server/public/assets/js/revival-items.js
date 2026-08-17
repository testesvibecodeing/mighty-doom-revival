/* Revival Visual System — artwork original do projeto.
 * Carregado depois de slayer.js. Não usa sprites extraídos nem arte oficial.
 */
(() => {
  const HOT = '#ff7b1c'
  const RED = '#ff4322'
  const GOLD = '#ffc34e'
  const DARK = '#0b0705'
  const METAL = '#241813'

  const css = `
  :root{--rv-common:#8c817a;--rv-uncommon:#55d879;--rv-rare:#4aa5ff;--rv-epic:#a56cff;--rv-legendary:#ffad28;--rv-mythic:#ff4c35}
  .inventory-grid{grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px}
  .item-card,.store-card,.collection-card{position:relative;overflow:hidden;isolation:isolate}
  .item-card{min-height:284px;padding:0;background:linear-gradient(165deg,rgba(43,20,10,.95),rgba(12,8,7,.98));clip-path:polygon(8px 0,calc(100% - 8px) 0,100% 8px,100% calc(100% - 8px),calc(100% - 8px) 100%,8px 100%,0 calc(100% - 8px),0 8px);transition:.18s;cursor:pointer}
  .item-card:hover,.store-card:hover{transform:translateY(-3px);border-color:rgba(255,171,57,.58);box-shadow:0 18px 38px rgba(0,0,0,.34)}
  .item-card::before{content:"";position:absolute;z-index:3;inset:0 0 auto;height:3px;background:var(--rv-common)}
  .item-card.r1::before{background:var(--rv-uncommon)}.item-card.r2::before{background:var(--rv-rare)}.item-card.r3::before{background:var(--rv-epic)}.item-card.r4::before{background:var(--rv-legendary)}.item-card.r5::before,.item-card.r6::before{background:var(--rv-mythic)}
  .item-art{min-height:164px;margin:0;padding:16px 12px 24px;background:radial-gradient(circle at 50% 42%,rgba(255,128,28,.19),transparent 35%),linear-gradient(180deg,rgba(255,117,20,.045),rgba(0,0,0,.3));border-bottom:1px solid rgba(255,130,30,.1)}
  .item-art .game-icon{max-width:140px;max-height:132px;filter:drop-shadow(0 12px 15px rgba(0,0,0,.62))}
  .item-card>.item-kind,.item-card>h3,.item-card>.item-meta{margin-left:14px;margin-right:14px}.item-card>.item-kind{margin-top:13px}.item-card>h3{font-size:17px}.item-card>.item-meta{margin-bottom:14px}
  .item-meta span{padding:3px 7px;border:1px solid rgba(255,255,255,.09);background:rgba(0,0,0,.2)}
  .rv-rarity{position:absolute;z-index:4;top:9px;right:9px;padding:4px 7px;border:1px solid currentColor;background:rgba(8,4,3,.86);color:var(--rv-common);font-size:9px;font-weight:800;letter-spacing:.08em;text-transform:uppercase}
  .r1 .rv-rarity{color:var(--rv-uncommon)}.r2 .rv-rarity{color:var(--rv-rare)}.r3 .rv-rarity{color:var(--rv-epic)}.r4 .rv-rarity{color:var(--rv-legendary)}.r5 .rv-rarity,.r6 .rv-rarity{color:var(--rv-mythic)}
  .equip-badge{z-index:4;background:linear-gradient(90deg,rgba(7,27,12,.96),rgba(11,51,21,.94))}
  .collection-card{min-height:154px;background:linear-gradient(160deg,rgba(35,17,10,.94),rgba(13,9,8,.98))}
  .collection-card .game-icon{max-width:86px;max-height:86px}
  .store-list{grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
  .store-card{display:flex;flex-direction:column;gap:0;padding:0;background:linear-gradient(165deg,rgba(48,21,10,.95),rgba(12,8,7,.98));clip-path:polygon(10px 0,calc(100% - 10px) 0,100% 10px,100% calc(100% - 10px),calc(100% - 10px) 100%,10px 100%,0 calc(100% - 10px),0 10px);cursor:pointer;transition:.18s}
  .store-cover{width:100%;height:188px;min-height:188px;border:0;border-bottom:1px solid rgba(255,109,24,.15);background:radial-gradient(circle at 50% 48%,rgba(255,132,31,.22),transparent 34%),linear-gradient(180deg,rgba(255,91,16,.055),rgba(0,0,0,.36))}
  .store-cover .game-icon{max-width:156px;max-height:150px}.store-body{padding:16px}.store-head h3{font-size:18px;line-height:1.25}.cost-pill{font-size:13px;padding:7px 10px}.store-contents span{padding:6px 0}
  .rv-own{margin-left:auto;padding:2px 6px;border:1px solid rgba(85,232,120,.25);color:var(--green);font-size:10px;font-style:normal;font-weight:700}
  .rv-store-action{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:14px;padding-top:12px;border-top:1px solid rgba(255,255,255,.07)}.rv-store-action small{color:var(--muted)}
  .rv-view{border:1px solid rgba(255,122,28,.42);background:rgba(255,91,14,.08);color:#ffc56c;padding:7px 10px;font-weight:700;cursor:pointer}
  .game-icon{filter:drop-shadow(0 7px 12px rgba(0,0,0,.58))}
  .rv-modal{position:fixed;inset:0;z-index:90;display:none;place-items:center;padding:20px;background:rgba(4,2,1,.84);backdrop-filter:blur(9px)}.rv-modal.open{display:grid}
  .rv-dialog{width:min(620px,100%);max-height:92vh;overflow:auto;border:1px solid rgba(255,129,31,.5);background:linear-gradient(165deg,#281208,#0d0806 62%);box-shadow:0 34px 90px rgba(0,0,0,.7);clip-path:polygon(12px 0,calc(100% - 12px) 0,100% 12px,100% calc(100% - 12px),calc(100% - 12px) 100%,12px 100%,0 calc(100% - 12px),0 12px)}
  .rv-hero{position:relative;display:grid;place-items:center;min-height:280px;background:radial-gradient(circle at 50% 48%,rgba(255,122,25,.25),transparent 34%),linear-gradient(180deg,rgba(255,88,17,.08),rgba(0,0,0,.36));border-bottom:1px solid rgba(255,129,31,.17)}
  .rv-hero img{max-width:240px;max-height:220px;filter:drop-shadow(0 20px 24px rgba(0,0,0,.66))}.rv-close{position:absolute;right:12px;top:12px;width:40px;height:40px;border:1px solid rgba(255,255,255,.13);background:rgba(8,4,3,.84);color:#ffe1bd;cursor:pointer}
  .rv-info{padding:22px}.rv-info h3{margin:5px 0 0;font:400 27px/1.15 'Black Ops One';color:#fff0dc}.rv-meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}.rv-meta span{padding:6px 9px;border:1px solid rgba(255,255,255,.1);background:rgba(0,0,0,.25);color:#cbb9a9;font-size:12px}.rv-body{margin-top:16px;color:#b8a89b;line-height:1.65}
  @media(max-width:620px){.inventory-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.item-card{min-height:248px}.item-art{min-height:136px}.store-list{grid-template-columns:1fr}.store-cover{height:180px}}
  @media(max-width:390px){.inventory-grid{grid-template-columns:1fr}}
  `
  const style = document.createElement('style')
  style.dataset.revivalVisuals = '1'
  style.textContent = css
  document.head.appendChild(style)

  const clean = v => String(v || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[_-]+/g, ' ')
  const typeFor = (r = {}) => {
    const s = clean(`${r.tag || ''} ${r.name || ''}`), k = clean(r.kind)
    if (/(crystal|gem)/.test(s)) return 'crystal'
    if (/(coin|gold)/.test(s)) return 'coin'
    if (/(key|chave)/.test(s)) return 'key'
    if (/(token|tech|shard)/.test(s)) return 'token'
    if (/(energy|energia|argent)/.test(s) || k === 'energy') return 'energy'
    if (/(crate|box|caixa|shipment)/.test(s) || /crate|pack/.test(k)) return 'crate'
    if (/(helmet|capacete)/.test(s)) return 'helmet'
    if (/(chest|torso|peitoral|armor|armadura)/.test(s)) return 'armor'
    if (/(gauntlet|glove|luva)/.test(s)) return 'gauntlets'
    if (/(boot|bota)/.test(s)) return 'boots'
    if (/(shotgun)/.test(s)) return 'shotgun'
    if (/(plasma)/.test(s)) return 'plasma'
    if (/(rocket|launcher|grenade|flame belch|ice bomb|acid spit)/.test(s) || k === 'launcher') return 'launcher'
    if (/(ballista|gauss|burst|sniper)/.test(s)) return 'precision'
    if (/(chainsaw|crucible|hammer|sword|samurai)/.test(s)) return 'melee'
    if (/(bfg|unmaykr|ultimate)/.test(s) || k === 'ultimate') return 'ultimate'
    if (/(slayer|marine)/.test(s) || k === 'slayer') return 'slayer'
    if (/(cosmetic|skin)/.test(s) || k === 'cosmetic') return 'cosmetic'
    if (/(entitlement|beneficio|benefit)/.test(s) || k === 'entitlement') return 'badge'
    if (k === 'equipment') return 'armor'
    if (k === 'currency') return 'coin'
    return 'weapon'
  }

  function svg (type) {
    const common = `<defs><linearGradient id="h" x1="0" y1="0" x2="1" y2="1"><stop stop-color="${GOLD}"/><stop offset=".55" stop-color="${HOT}"/><stop offset="1" stop-color="${RED}"/></linearGradient><linearGradient id="m" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#3b2a22"/><stop offset=".5" stop-color="${DARK}"/><stop offset="1" stop-color="${METAL}"/></linearGradient></defs><circle cx="80" cy="80" r="63" fill="#070504" stroke="#3b1b13" stroke-width="2"/><circle cx="80" cy="80" r="52" fill="none" stroke="${HOT}" stroke-opacity=".16"/>`
    const shapes = {
      crystal:`<path d="M80 22 113 61 99 124 80 138 58 123 47 61Z" fill="url(#h)" stroke="#ffd56c" stroke-width="3"/><path d="M80 22v116M47 61l33 16 33-16M58 123l22-46 19 47" fill="none" stroke="#fff1b6" stroke-opacity=".7" stroke-width="2"/>`,
      coin:`<circle cx="80" cy="80" r="42" fill="url(#h)" stroke="#ffe28a" stroke-width="5"/><circle cx="80" cy="80" r="30" fill="#6b2508"/><path d="M62 105V55h20q25 0 25 20 0 13-12 18l14 12H91L79 95v10Zm16-25h5q10 0 10-7 0-6-10-6h-5Z" fill="#ffd65b"/>`,
      energy:`<rect x="52" y="31" width="56" height="98" rx="13" fill="url(#m)" stroke="#58d8ff" stroke-width="3"/><path d="M87 46 63 82h18l-7 32 26-43H82Z" fill="#58d8ff" stroke="#d8f8ff" stroke-width="2"/>`,
      key:`<circle cx="59" cy="64" r="23" fill="url(#m)" stroke="${GOLD}" stroke-width="5"/><circle cx="59" cy="64" r="10" fill="#080605"/><path d="m76 80 49 46M101 103l13-13M112 114l13-13" fill="none" stroke="url(#h)" stroke-width="12"/>`,
      token:`<path d="M80 25 124 104 36 104Z" fill="url(#m)" stroke="#9d6cff" stroke-width="4"/><path d="M80 46 104 93H56Z" fill="none" stroke="#d0b5ff" stroke-width="4"/><circle cx="80" cy="81" r="8" fill="#9d6cff"/>`,
      crate:`<path d="M37 48 80 29l43 19v65l-43 21-43-21Z" fill="url(#m)" stroke="${HOT}" stroke-width="3"/><path d="m37 48 43 22 43-22M80 70v64" fill="none" stroke="${GOLD}" stroke-width="3"/><rect x="67" y="76" width="26" height="28" rx="4" fill="#5d220c" stroke="#ffca58" stroke-width="3"/>`,
      slayer:`<path d="M45 56 61 36h38l17 20-4 50-20 23H67l-20-23Z" fill="url(#m)" stroke="${HOT}" stroke-width="3"/><path d="M55 68 68 58h25l13 10-8 26H63Z" fill="#10241b" stroke="#70ff9b" stroke-width="3"/><path d="M62 98h37l-10 18H72Z" fill="#080605" stroke="${HOT}" stroke-width="2"/>`,
      helmet:`<path d="M43 65 57 39h46l15 26-6 48-20 16H67l-20-16Z" fill="url(#m)" stroke="${HOT}" stroke-width="3"/><path d="M57 72 70 62h23l12 10-7 24H63Z" fill="#28100b" stroke="${GOLD}" stroke-width="3"/>`,
      armor:`<path d="m48 45 24-14h16l24 14 17 33-13 48-31 12-41-12-13-48Z" fill="url(#m)" stroke="${HOT}" stroke-width="3"/><path d="M57 59h46l9 21-15 13H63L48 80Z" fill="#2c120c" stroke="${GOLD}" stroke-width="3"/>`,
      gauntlets:`<path d="M38 52h28l13 31-10 48H45L31 91Z" fill="url(#m)" stroke="${HOT}" stroke-width="3"/><path d="M94 52h28l7 39-14 40H91l-10-48Z" fill="url(#m)" stroke="${HOT}" stroke-width="3"/>`,
      boots:`<path d="M47 35h27l3 66-17 31H33l6-35Z" fill="url(#m)" stroke="${HOT}" stroke-width="3"/><path d="M86 35h27l8 62 6 35H99l-17-31Z" fill="url(#m)" stroke="${HOT}" stroke-width="3"/>`,
      shotgun:`<path d="M28 78 50 64h65l18 9v16l-18 8H52l-24-10Z" fill="url(#m)" stroke="${HOT}" stroke-width="3"/><path d="M43 71h72v8H43M43 84h72v8H43" fill="none" stroke="${GOLD}" stroke-width="4"/><path d="m68 97 8 28h25l7-28" fill="url(#m)" stroke="${HOT}" stroke-width="3"/>`,
      plasma:`<path d="M26 88 48 65h61l13 12 13 2v18l-21 5-11 9H51L26 98Z" fill="url(#m)" stroke="#4bd7ff" stroke-width="3"/><path d="M52 77h57l9 11-14 11H51Z" fill="#12384a" stroke="#70e6ff" stroke-width="2"/>`,
      launcher:`<path d="M27 75 46 57h66l19 13v29l-21 10H48L27 94Z" fill="url(#m)" stroke="${HOT}" stroke-width="3"/><ellipse cx="112" cy="83" rx="25" ry="24" fill="#19100c" stroke="${GOLD}" stroke-width="5"/><ellipse cx="112" cy="83" rx="13" ry="12" fill="#080605"/>`,
      precision:`<path d="M20 83 49 72h56l19 8h19v14h-25l-18 9H48L20 94Z" fill="url(#m)" stroke="${HOT}" stroke-width="3"/><rect x="58" y="55" width="41" height="12" rx="6" fill="#111" stroke="${GOLD}" stroke-width="2"/><circle cx="79" cy="61" r="7" fill="${RED}"/>`,
      melee:`<path d="m51 124 16-16 42-76 12 8-42 78-8 22Z" fill="url(#h)" stroke="#ffd066" stroke-width="3"/><path d="m50 108 28 16M58 99l30 17" stroke="#3b160c" stroke-width="5"/>`,
      ultimate:`<path d="M31 88 54 59h54l22 25-20 28H53L31 99Z" fill="url(#m)" stroke="${RED}" stroke-width="3"/><circle cx="84" cy="86" r="24" fill="url(#h)"/>`,
      cosmetic:`<path d="M80 24 109 38l17 27-8 37-38 34-38-34-8-37 17-27Z" fill="url(#m)" stroke="#a56cff" stroke-width="3"/><path d="m80 45 11 23 25 3-18 17 5 25-23-12-23 12 5-25-18-17 25-3Z" fill="#7c3aed" stroke="#d5b9ff" stroke-width="2"/>`,
      badge:`<path d="M80 24 119 45v35c0 28-17 46-39 56-22-10-39-28-39-56V45Z" fill="url(#m)" stroke="${GOLD}" stroke-width="3"/><path d="m58 81 14 14 30-34" fill="none" stroke="#ffd768" stroke-width="7"/>`,
      weapon:`<path d="M28 89 47 69h55l16 11h19v20h-24l-11 11H48l-20-10Z" fill="url(#m)" stroke="${HOT}" stroke-width="3"/><rect x="45" y="84" width="62" height="9" rx="4" fill="url(#h)"/><path d="M58 70 68 53h29l12 17M53 111l8 18h22l5-18" fill="url(#m)" stroke="${HOT}" stroke-width="3"/>`
    }
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160">${common}${shapes[type] || shapes.weapon}</svg>`
  }

  const cache = new Map()
  const artUrl = r => {
    const type = typeFor(r)
    if (!cache.has(type)) cache.set(type, `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg(type))}`)
    return cache.get(type)
  }

  if (typeof iconImg === 'function') {
    iconImg = function (resource = {}, cls = '') {
      return `<img class="game-icon revival-art ${cls}" src="${escapeHtml(artUrl(resource))}" alt="${escapeHtml(resource.name || resource.tag || resource.kind || 'Item Revival')}" loading="lazy">`
    }
  }

  const rarity = ['Base','Aprimorado','Raro','Épico','Lendário','Mítico','Mítico']
  function tierOf (card) {
    const t = [...card.querySelectorAll('.item-meta span')].map(x => x.textContent.trim()).find(x => /^T\d+$/i.test(x))
    return Math.max(0, Math.min(6, t ? Number(t.slice(1)) || 0 : 0))
  }
  function humanPack (s) {
    return String(s || '').replace(/^(revival|historical)_/i,'').split('_').filter(Boolean).map(x => /^\d+$/.test(x) ? x : x[0].toUpperCase()+x.slice(1)).join(' ')
  }
  function owned (name) {
    if (typeof me === 'undefined' || !me?.snapshot) return 0
    const n = clean(name), rows = [...(me.snapshot.items||[]),...(me.snapshot.cosmetics||[]),...(me.snapshot.entitlements||[])]
    const hit = rows.find(r => clean(r.name) === n)
    return Number(hit?.amount || (hit ? 1 : 0))
  }
  function enhance () {
    document.querySelectorAll('#inventoryGrid .item-card').forEach(card => {
      const t = tierOf(card)
      card.classList.add(`r${t}`); card.dataset.rvDetail='inventory'; card.tabIndex=0
      const art = card.querySelector('.item-art')
      if (art && !art.querySelector('.rv-rarity')) { const b=document.createElement('span');b.className='rv-rarity';b.textContent=rarity[t];art.appendChild(b) }
    })
    document.querySelectorAll('#storeList .store-card').forEach(card => {
      card.dataset.rvDetail='store'; card.tabIndex=0
      const h=card.querySelector('.store-head h3')
      if(h&&!h.dataset.pretty){h.textContent=humanPack(h.textContent);h.dataset.pretty='1'}
      card.querySelectorAll('.store-contents > span').forEach(row => {
        if(row.querySelector('.rv-own')) return
        const a=owned(row.querySelector('b')?.textContent||'')
        if(a>0){const e=document.createElement('em');e.className='rv-own';e.textContent=`Possui x${a.toLocaleString('pt-BR')}`;row.appendChild(e)}
      })
      const body=card.querySelector('.store-body')
      if(body&&!body.querySelector('.rv-store-action')){const d=document.createElement('div');d.className='rv-store-action';d.innerHTML='<small>Preço em recursos do jogo</small><button type="button" class="rv-view">Detalhes</button>';body.appendChild(d)}
    })
  }
  function modal () {
    let m=document.querySelector('#rvModal'); if(m)return m
    m=document.createElement('div');m.id='rvModal';m.className='rv-modal'
    m.innerHTML='<article class="rv-dialog"><div class="rv-hero"><button class="rv-close" type="button">×</button><img id="rvImg" alt=""></div><div class="rv-info"><span class="eyebrow" id="rvKind">// ITEM</span><h3 id="rvTitle">Item</h3><div class="rv-meta" id="rvMeta"></div><div class="rv-body" id="rvBody"></div></div></article>'
    document.body.appendChild(m);m.querySelector('.rv-close').onclick=()=>m.classList.remove('open');m.onclick=e=>{if(e.target===m)m.classList.remove('open')};return m
  }
  function openCard(card){
    const m=modal(),store=card.dataset.rvDetail==='store',img=card.querySelector('.game-icon'),title=card.querySelector(store?'.store-head h3':'h3')?.textContent?.trim()||'Item'
    const kind=card.querySelector('.item-kind')?.textContent?.trim()||(store?'Pacote da instância':'Item')
    const meta=[...card.querySelectorAll(store?'.cost-pill,.tag':'.item-meta span,.rv-rarity,.equip-badge')].map(x=>x.textContent.replace(/\s+/g,' ').trim()).filter(Boolean)
    m.querySelector('#rvImg').src=img?.src||artUrl({kind:'reward'});m.querySelector('#rvImg').alt=title;m.querySelector('#rvKind').textContent=`// ${kind.toUpperCase()}`;m.querySelector('#rvTitle').textContent=title;m.querySelector('#rvMeta').innerHTML=meta.map(v=>`<span>${escapeHtml(v)}</span>`).join('')
    m.querySelector('#rvBody').innerHTML=store?(card.querySelector('.store-contents')?.outerHTML||'<p>Pacote configurado nesta instância.</p>'):'<p>Este painel reflete o item persistido no inventário real desta conta. Nível, tier, quantidade e estado equipado vêm do snapshot do jogador.</p>';m.classList.add('open')
  }
  document.addEventListener('click',e=>{const c=e.target.closest('[data-rv-detail]');if(!c)return;if(e.target.closest('button,a,input,select,textarea')&&!e.target.closest('.rv-view'))return;openCard(c)})
  document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelector('#rvModal')?.classList.remove('open');if(!['Enter',' '].includes(e.key))return;const c=e.target.closest?.('[data-rv-detail]');if(c){e.preventDefault();openCard(c)}})
  const obs=new MutationObserver(()=>queueMicrotask(enhance))
  for(const s of ['#inventoryGrid','#storeList','#cosmeticGrid','#entitlementGrid','#resourceList']){const n=document.querySelector(s);if(n)obs.observe(n,{childList:true,subtree:true})}
  enhance()
})()
