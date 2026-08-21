// Painel do Slayer (/slayer): visão do jogador + administração do servidor.
// Sem sessão -> volta para /account. O menu principal fica embaixo (estilo app).
const $ = selector => document.querySelector(selector)
const $$ = selector => [...document.querySelectorAll(selector)]

let me = null

function formData (form) { return Object.fromEntries(new FormData(form).entries()) }
function escapeHtml (value) { return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]) }
function formatNumber (value) { return Number(value || 0).toLocaleString('pt-BR') }
function formatDate (epoch) { return epoch ? new Date(epoch * 1000).toLocaleDateString('pt-BR') : '--' }
function formatDateTime (epoch) { return epoch ? new Date(epoch * 1000).toLocaleString('pt-BR') : '--' }
function toast (message) {
  const el = $('#toast')
  el.textContent = message
  el.classList.add('show')
  setTimeout(() => el.classList.remove('show'), 3600)
}
async function api (path, options = {}) {
  const response = await fetch(path, { credentials: 'same-origin', headers: { 'content-type': 'application/json', ...(options.headers || {}) }, ...options })
  if (response.status === 401 && path !== '/account/me') window.location.href = '/account'
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.error || 'Não foi possível concluir a operação.')
  return body
}
function status (id, message, ok = false) {
  const el = $(`#${id}`)
  if (!el) return
  el.textContent = message || ''
  el.className = `form-status ${ok ? 'ok' : message ? 'error' : ''}`
}

/* ============ boot ============ */
async function boot () {
  try {
    me = await api('/account/me')
  } catch {
    window.location.href = '/account'
    return
  }
  renderPlayer()
  loadNotices().catch(() => {})
  loadStore().catch(() => {})
  if (me.account.is_admin) {
    $('#tabAdmin').hidden = false
    $('#panel-admin').hidden = false
    $('#adminBadge').hidden = false
  }
  showPasswordHint()
  loadClaimable().catch(() => {})
}

/* ============ ícones do jogo ============ */
const KIND_LABELS = {
  weapon: 'Arma', equipment: 'Equipamento', launcher: 'Launcher',
  ultimate: 'Ultimate', slayer: 'Slayer', cosmetic: 'Cosmético',
  entitlement: 'Benefício', currency: 'Moeda', energy: 'Energia', crate: 'Caixa'
}

function iconImg (resource, cls = '') {
  const src = escapeHtml(resource.icon || '')
  const fallback = escapeHtml(resource.fallback || '/assets/img/kinds/pack.svg')
  const alt = escapeHtml(resource.name || '')
  return `<img class="game-icon ${cls}" src="${src}" data-fallback="${fallback}" alt="${alt}" loading="lazy" onerror="if(this.dataset.fallback&&this.src!==this.dataset.fallback)this.src=this.dataset.fallback;else this.style.visibility='hidden'">`
}

// A capa do pacote é apenas uma composição visual do conteúdo que o cliente
// já recebe. Assim o site mostra os mesmos itens/ícones do jogo, sem inventar
// um campo de imagem no wire da Store API.
function packVisual (entries, cls = '') {
  const visible = (entries || []).slice(0, 4)
  if (!visible.length) return iconImg({}, cls)
  return `<div class="pack-visual ${escapeHtml(cls)}">${visible.map(entry => iconImg(entry, 'pack-visual-icon')).join('')}${entries.length > visible.length ? `<span class="pack-visual-more">+${entries.length - visible.length}</span>` : ''}</div>`
}

/* ============ inventário ============ */
const SLOT_LABELS = {
  slot_primary_weapon: 'Arma primária', slot_secondary_weapon: 'Arma secundária',
  slot_slayer: 'Slayer', slot_launcher: 'Launcher', slot_ultimate: 'Ultimate',
  slot_helmet: 'Capacete', slot_chestplate: 'Peitoral', slot_gauntlets: 'Luvas',
  slot_boots: 'Botas'
}

let inventoryFilter = 'all'

function renderInventory () {
  const { snapshot } = me
  const items = snapshot.items || []
  const equipped = new Set((snapshot.equipped || []).map(slot => slot.item_id))
  const equippedSlots = new Map((snapshot.equipped || []).map(slot => [slot.item_id, slot.slot_id]))

  const byKind = new Map()
  for (const item of items) {
    const kind = item.kind || 'other'
    if (!byKind.has(kind)) byKind.set(kind, [])
    byKind.get(kind).push(item)
  }

  const chips = [['all', `Tudo (${items.length})`]]
  for (const [kind, list] of byKind) chips.push([kind, `${KIND_LABELS[kind] || kind} (${list.length})`])
  $('#inventoryFilters').innerHTML = chips.map(([key, label]) =>
    `<button class="chip ${inventoryFilter === key ? 'active' : ''}" data-filter="${escapeHtml(key)}">${escapeHtml(label)}</button>`).join('')

  const visible = inventoryFilter === 'all' ? items : items.filter(item => (item.kind || 'other') === inventoryFilter)
  $('#inventoryCount').textContent = `${items.length} itens`
  $('#inventoryGrid').innerHTML = visible.length
    ? visible.map(item => {
      const isEquipped = equipped.has(item.id)
      const slotLabel = isEquipped ? SLOT_LABELS[equippedSlots.get(item.id)] || 'Equipado' : null
      return `<article class="item-card ${isEquipped ? 'equipped' : ''}">
        <div class="item-art">${iconImg(item)}${isEquipped ? `<span class="equip-badge"><i class="fa-solid fa-check"></i> ${escapeHtml(slotLabel)}</span>` : ''}</div>
        <span class="item-kind">${escapeHtml(KIND_LABELS[item.kind] || item.kind)}</span>
        <h3>${escapeHtml(item.name)}</h3>
        <div class="item-meta">
          ${item.tier ? `<span>T${item.tier}</span>` : ''}
          ${item.level > 1 ? `<span>Nv ${item.level}</span>` : ''}
          ${item.amount > 1 ? `<span>x${formatNumber(item.amount)}</span>` : ''}
          ${!item.tier && item.level <= 1 && item.amount <= 1 ? '<span>Base</span>' : ''}
        </div>
      </article>`
    }).join('')
    : `<p class="empty">${items.length ? 'Nenhum item nesta categoria.' : 'Seu inventário ainda está vazio — compre na loja ou jogue para receber itens.'}</p>`

  renderCollectionGrid('#cosmeticGrid', snapshot.cosmetics, 'Nenhum cosmético desbloqueado ainda.')
  renderCollectionGrid('#entitlementGrid', snapshot.entitlements, 'Nenhum benefício liberado ainda.')
}

function renderCollectionGrid (selector, rows, emptyText) {
  const list = rows || []
  $(selector).innerHTML = list.length
    ? list.map(row => `<article class="collection-card">${iconImg(row)}<span>${escapeHtml(row.name)}</span></article>`).join('')
    : `<p class="empty">${emptyText}</p>`
}

$('#inventoryFilters').addEventListener('click', event => {
  const chip = event.target.closest('[data-filter]')
  if (!chip) return
  inventoryFilter = chip.dataset.filter
  renderInventory()
})

function renderPlayer () {
  const { account, snapshot } = me
  $('#heroName').textContent = account.display_name || `Slayer #${account.id}`
  $('#heroId').textContent = account.id
  $('#heroCreated').textContent = formatDate(account.created_at)
  const progression = snapshot.progression || {}
  $('#metricLevel').textContent = progression.level || 1
  $('#metricChapters').textContent = `${progression.chapters || 0} capítulos concluídos`
  $('#metricItems').textContent = formatNumber(snapshot.items?.length)
  $('#metricAttempts').textContent = formatNumber(progression.attempts)
  const coins = snapshot.currencies?.[0]
  $('#metricCoins').textContent = formatNumber(coins?.amount)
  const resources = [...(snapshot.currencies || []), ...(snapshot.energies || [])]
  $('#resourceList').innerHTML = resources.length
    ? resources.map(row => `<div class="resource-row">${iconImg(row, 'inline')}<span style="flex:1">${escapeHtml(row.name)}</span><strong>${formatNumber(row.amount)}</strong></div>`).join('')
    : '<p class="empty">Nenhum recurso registrado ainda.</p>'
  const stats = progression.stats || []
  $('#statsList').innerHTML = stats.length
    ? stats.slice(0, 10).map(row => `<div class="stat-row"><span>${escapeHtml(row.tag || row.id || 'Estatística')}</span><strong>${formatNumber(row.value)}</strong></div>`).join('')
    : '<p class="empty">Jogue uma partida para gerar estatísticas.</p>'
  renderInventory()
  $('#profileName').value = account.display_name || ''
  $('#profileEmail').value = account.email || ''
}

// Quem entrou com senha temporária deve trocá-la depois do primeiro acesso.
function showPasswordHint () {
  let hint = false
  try { hint = sessionStorage.getItem('revival_temporary_password') === '1' } catch {}
  if (!hint) return
  sessionStorage.removeItem('revival_temporary_password')
  toast('Você entrou com uma senha temporária. Troque-a agora em Minha conta → Segurança.')
}

/* ============ avisos ============ */
const NOTICE_ICONS = { info: 'fa-circle-info', update: 'fa-circle-arrow-up', event: 'fa-calendar-days', warning: 'fa-triangle-exclamation' }
const NOTICE_LABELS = { info: 'Informação', update: 'Atualização', event: 'Evento', warning: 'Aviso' }

async function loadNotices () {
  const { notifications } = await api('/account/notifications')
  $('#noticeList').innerHTML = notifications.length
    ? notifications.map(renderNotice).join('')
    : '<p class="empty">Nenhum aviso do servidor por enquanto.</p>'
}

function renderNotice (notice) {
  const admin = me?.account?.is_admin
    ? `<button class="mini-action notice-admin" data-del-notice="${notice.id}" title="Excluir aviso"><i class="fa-solid fa-trash"></i></button>` : ''
  return `<article class="notice-item ${escapeHtml(notice.kind)}" data-kind="${escapeHtml(notice.kind)}">
    <i class="fa-solid ${NOTICE_ICONS[notice.kind] || NOTICE_ICONS.info} n-icon"></i>
    <div style="flex:1;min-width:0"><b>${escapeHtml(notice.title)}</b>${notice.body ? `<p>${escapeHtml(notice.body)}</p>` : ''}<small>${NOTICE_LABELS[notice.kind] || notice.kind} · ${formatDateTime(notice.created_at)}</small></div>
    ${admin}
  </article>`
}

document.addEventListener('click', async event => {
  const button = event.target.closest('[data-del-notice]')
  if (!button) return
  try {
    await api(`/account/admin/notifications/${button.dataset.delNotice}`, { method: 'DELETE' })
    toast('Aviso excluído.')
    loadNotices().catch(() => {})
    if (adminLoaded.notices) loadAdminNotices().catch(() => {})
  } catch (error) { toast(error.message) }
})

/* ============ loja (visão do jogador) ============ */
async function loadStore () {
  const { packs } = await api('/account/store')
  $('#storeCount').textContent = `${packs.length} pacotes`
  $('#storeList').innerHTML = packs.length ? packs.map(pack => {
    const costEntries = pack.preview?.cost || []
    const contentEntries = pack.preview?.contents || []
    const cost = costEntries.map(entry => `<span class="cost-pill">${iconImg(entry, 'inline')} ${escapeHtml(entry.name)} · ${formatNumber(entry.amount)}</span>`).join('') || '<span class="cost-pill"><i class="fa-solid fa-gift"></i> Grátis</span>'
    const contents = contentEntries.map(entry => `<span>${iconImg(entry, 'inline thumb')}<b style="flex:1">${escapeHtml(entry.name)}</b><strong>x${formatNumber(entry.amount)}</strong></span>`).join('')
    const quota = pack.quota ? `<span class="tag">Limite: ${pack.quota.max}x ${pack.quota.period === 'daily' ? 'por dia' : pack.quota.period === 'weekly' ? 'por semana' : 'total'}</span>` : ''
    const coverEntries = contentEntries.length ? contentEntries : costEntries
    return `<article class="store-card">
      <div class="store-cover">${packVisual(coverEntries)}</div>
      <div class="store-body">
        <div class="store-head"><h3>${escapeHtml(pack.tag)}</h3>${quota}</div>
        <div class="store-cost">${cost}</div>
        ${contents ? `<div class="store-contents">${contents}</div>` : ''}
      </div>
    </article>`
  }).join('') : '<p class="empty">Nenhum pacote ativo na loja desta instância.</p>'
}

/* ============ abas ============ */
$$('.tab').forEach(tab => tab.addEventListener('click', () => {
  $$('.tab').forEach(x => x.classList.toggle('active', x === tab))
  $$('.tab-panel').forEach(panel => {
    const active = panel.id === `panel-${tab.dataset.tab}`
    panel.classList.toggle('active', active)
    panel.hidden = !active
  })
  window.scrollTo({ top: 0 })
  if (tab.dataset.tab === 'admin') loadAdminSection('overview')
}))

/* ============ conta ============ */
$('#profileForm').addEventListener('submit', async event => {
  event.preventDefault()
  status('profileStatus', 'Salvando…')
  try {
    const result = await api('/account/profile', { method: 'PATCH', body: JSON.stringify(formData(event.target)) })
    me.account = result.account
    renderPlayer()
    status('profileStatus', 'Dados atualizados.', true)
  } catch (error) { status('profileStatus', error.message) }
})

$('#passwordForm').addEventListener('submit', async event => {
  event.preventDefault()
  status('passwordStatus', 'Atualizando…')
  try {
    const result = await api('/account/password', { method: 'POST', body: JSON.stringify(formData(event.target)) })
    event.target.reset()
    status('passwordStatus', result.message || 'Senha alterada.', true)
  } catch (error) { status('passwordStatus', error.message) }
})

async function logout () {
  try { await api('/account/logout', { method: 'POST', body: '{}' }) } catch {}
  window.location.href = '/account'
}
$('#logoutButton').addEventListener('click', logout)
$('#logoutTop').addEventListener('click', logout)
/* ============ modais ============ */
function showResult ({ title, text = '', code = '', copyable = false }) {
  $('#resultTitle').textContent = title
  $('#resultText').textContent = text
  const codeEl = $('#resultCode')
  codeEl.hidden = !code
  codeEl.textContent = code
  $('#resultCopy').hidden = !copyable
  $('#resultModal').hidden = false
}
$('#resultClose').addEventListener('click', () => { $('#resultModal').hidden = true })
$('#resultCopy').addEventListener('click', () => navigator.clipboard?.writeText($('#resultCode').textContent).then(() => toast('Copiado.')))
$('#resultModal').addEventListener('click', event => { if (event.target === $('#resultModal')) $('#resultModal').hidden = true })

let confirmAction = null
function showConfirm (title, text, onYes) {
  $('#resultTitle').textContent = title
  $('#resultText').textContent = text
  $('#resultCode').hidden = true
  $('#resultCopy').hidden = true
  const yes = $('#resultConfirm')
  yes.hidden = false
  confirmAction = onYes
  $('#resultModal').hidden = false
}
$('#resultConfirm')?.addEventListener('click', () => {
  $('#resultModal').hidden = true
  $('#resultConfirm').hidden = true
  confirmAction?.()
})

/* ============ admin ============ */
$$('#adminSubnav .chip').forEach(chip => chip.addEventListener('click', () => {
  $$('#adminSubnav .chip').forEach(x => x.classList.toggle('active', x === chip))
  $$('.admin-sub').forEach(sub => {
    const active = sub.id === `admin-${chip.dataset.sub}`
    sub.classList.toggle('active', active)
    // [hidden] has precedence over .admin-sub.active in the stylesheet.
    // Keep the attribute in sync so the panel is actually visible after a
    // navigation click, including browsers with native hidden handling.
    sub.hidden = !active
  })
  loadAdminSection(chip.dataset.sub)
}))

function loadAdminSection (name) {
  if (!me?.account?.is_admin) return
  if (name === 'overview') return loadAdminOverview().catch(error => toast(error.message))
  if (name === 'users') return loadAdminUsers().catch(error => toast(error.message))
  if (name === 'packs') return loadAdminPacks().catch(error => toast(error.message))
  if (name === 'events') return loadAdminEvents().catch(error => toast(error.message))
  if (name === 'notices') return loadAdminNotices().catch(error => toast(error.message))
  if (name === 'site') return loadAdminSite().catch(error => toast(error.message))
  if (name === 'smtp') return loadAdminSmtp().catch(error => toast(error.message))
  if (name === 'routes') return loadAdminRoutes().catch(error => toast(error.message))
}

async function loadAdminOverview () {
  const { overview } = await api('/account/admin/overview')
  const tiles = [
    ['PLAYERS', formatNumber(overview.players), `${overview.admins} admin(s)`],
    ['PACOTES', `${overview.packs_active}/${overview.packs_total}`, 'ativos na loja'],
    ['EVENTOS', `${overview.events_active}/${overview.events_total}`, 'rodando agora'],
    ['AVISOS', formatNumber(overview.notifications), 'publicados'],
    ['UPTIME', `${Math.floor(overview.uptime_seconds / 3600)}h ${Math.floor((overview.uptime_seconds % 3600) / 60)}m`, overview.server_name],
    ['GAME DATA', overview.game_data_loaded ? 'OK' : '--', 'carregado']
  ]
  $('#adminTiles').innerHTML = tiles.map(([label, value, hint]) => `<article class="metric-card"><small>${label}</small><strong>${escapeHtml(value)}</strong><span>${escapeHtml(hint)}</span></article>`).join('')
  const apk = overview.apk || {}
  $('#apkInfo').innerHTML = `
    <div class="kv-row"><span>Publicado</span><strong>${apk.available ? 'Sim' : 'Não'}</strong></div>
    <div class="kv-row"><span>Tamanho</span><strong>${apk.size ? `${(apk.size / 1048576).toFixed(1)} MB` : '--'}</strong></div>
    <div class="kv-row"><span>Enviado em</span><strong>${formatDate(apk.uploaded_at)}</strong></div>`
  const compatibility = overview.compatibility || {}
  const healthPill = $('#adminHealthPill')
  healthPill.className = `health-pill ${overview.game_data_loaded ? 'healthy' : 'warning'}`
  healthPill.innerHTML = `<i class="fa-solid ${overview.game_data_loaded ? 'fa-circle-check' : 'fa-triangle-exclamation'}"></i> ${overview.game_data_loaded ? 'instância saudável' : 'game-data ausente'}`
  $('#adminCommandMeta').innerHTML = `<span><i class="fa-solid fa-server"></i> ${escapeHtml(overview.server_name || 'Revival')}</span><span><i class="fa-solid fa-users"></i> ${formatNumber(overview.players)} jogadores</span><span><i class="fa-solid fa-clock"></i> ${Math.floor((overview.uptime_seconds || 0) / 3600)}h uptime</span>`
  $('#adminHealthGrid').innerHTML = [
    ['Game data', overview.game_data_loaded ? 'Carregado' : 'Ausente', overview.game_data_loaded ? 'healthy' : 'warning'],
    ['Loja', `${overview.packs_active}/${overview.packs_total} ativos`, overview.packs_total ? 'healthy' : 'warning'],
    ['Eventos', `${overview.events_active}/${overview.events_total} ativos`, overview.events_total ? 'healthy' : 'neutral'],
    ['APK', apk.available ? 'Publicado' : 'Não publicado', apk.available ? 'healthy' : 'warning']
  ].map(([label, value, tone]) => `<div class="health-cell ${tone}"><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`).join('')
  $('#adminCoverageSummary').innerHTML = `<div class="coverage-meter"><div class="coverage-meter-head"><span>Implementação</span><strong>${compatibility.implemented || 0}/${compatibility.route_count || 0}</strong></div><div class="progress-track"><i style="width:${compatibility.route_count ? Math.round((compatibility.implemented || 0) / compatibility.route_count * 100) : 0}%"></i></div><small>${compatibility.validated || 0} validadas no cliente · ${compatibility.regression_test || 0} com regressão</small></div><button class="mini-action wide" type="button" data-open-admin="routes"><i class="fa-solid fa-diagram-project"></i> Abrir mapa de rotas</button>`
  $('#adminCoverageSummary').querySelector('[data-open-admin]')?.addEventListener('click', () => {
    const chip = $('#adminSubnav .chip[data-sub="routes"]')
    chip?.click()
  })
}
$('#adminRefresh').addEventListener('click', async () => {
  const active = $('#adminSubnav .chip.active')?.dataset.sub || 'overview'
  try { await loadAdminSection(active); toast('Painel atualizado.') } catch (error) { toast(error.message) }
})

async function loadAdminUsers (query = '') {
  const { users } = await api(`/account/admin/users?query=${encodeURIComponent(query)}`)
  $('#userList').innerHTML = users.length ? users.map(user => `
    <article class="admin-card" data-user="${user.id}">
      <div class="admin-card-head">
        <h3>#${user.id} ${escapeHtml(user.display_name || 'Sem nome')}</h3>
        <div class="user-tags">
          ${user.is_admin ? '<span class="tag admin"><i class="fa-solid fa-shield-halved"></i> ADMIN</span>' : ''}
          <span class="tag">Nv ${user.level}</span>
          <span class="tag">${user.chapter_progression} caps</span>
        </div>
      </div>
      <div class="user-meta">
        <span>E-mail: <strong>${escapeHtml(user.email || '--')}</strong></span>
        <span>${formatNumber(user.attempt_count)} runs · desde ${formatDate(user.created_at)}</span>
      </div>
      <div class="action-row">
        <button class="mini-action" data-act="profile"><i class="fa-solid fa-id-card"></i> Ver perfil</button>
        <button class="mini-action" data-act="reset"><i class="fa-solid fa-key"></i> Nova senha</button>
        <button class="mini-action" data-act="grant"><i class="fa-solid fa-gift"></i> Conceder</button>
        <button class="mini-action" data-act="admin"><i class="fa-solid fa-shield-halved"></i> ${user.is_admin ? 'Remover admin' : 'Tornar admin'}</button>
        <button class="mini-action danger" data-act="delete"><i class="fa-solid fa-trash"></i> Excluir</button>
      </div>
    </article>`).join('') : '<p class="empty">Nenhum usuário encontrado.</p>'
}

function profileResourceRows (rows, empty = 'Nenhum registro') {
  return rows?.length ? rows.map(row => `<div class="profile-resource"><img class="game-icon inline thumb" src="${escapeHtml(row.icon || row.fallback || '/assets/img/kinds/pack.svg')}" alt=""><span>${escapeHtml(row.name || `Recurso ${row.rid}`)}</span><strong>${formatNumber(row.amount ?? row.rid ?? 0)}</strong></div>`).join('') : `<p class="empty">${empty}</p>`
}

async function loadAdminUserProfile (userId) {
  const { profile } = await api(`/account/admin/users/${userId}/profile`)
  const account = profile.account
  const profileEl = $('#userProfile')
  const groups = [
    ['Armas', profile.items.filter(row => row.kind === 'weapon')],
    ['Armaduras / equipamentos', profile.items.filter(row => row.kind === 'equipment')],
    ['Launchers', profile.items.filter(row => row.kind === 'launcher')],
    ['Ultimates', profile.items.filter(row => row.kind === 'ultimate')],
    ['Slayers', profile.items.filter(row => row.kind === 'slayer')],
    ['Cosméticos', profile.cosmetics],
    ['Benefícios', profile.entitlements]
  ]
  const sections = groups.map(([title, rows]) => `<div class="profile-section"><h4>${title}</h4><div class="profile-resource-list">${profileResourceRows(rows, 'Nenhum')}</div></div>`).join('')
  const equipped = profile.equipped?.length ? profile.equipped.map(row => `<span class="tag"><i class="fa-solid fa-shield-halved"></i> slot ${row.slot_id} → item ${row.item_id}</span>`).join('') : '<span class="empty">Nenhum item equipado</span>'
  const stats = profile.stats?.length ? profile.stats.map(row => `<div class="profile-resource"><span>${escapeHtml(String(row.id))}</span><strong>${formatNumber(row.value)}</strong></div>`).join('') : '<p class="empty">Nenhuma estatística registrada</p>'
  profileEl.innerHTML = `<div class="modal admin-profile-modal" role="dialog" aria-modal="true" aria-labelledby="adminProfileTitle"><div class="profile-head"><div><span class="eyebrow">// PLAYER PROFILE</span><h3 id="adminProfileTitle">#${account.id} ${escapeHtml(account.display_name || 'Sem nome')}</h3><p class="hint">${escapeHtml(account.email || 'Sem e-mail')} · UUID ${escapeHtml(account.uuid)}</p></div><button class="secondary-action" data-close-profile>Fechar</button></div><div class="metric-grid"><article class="metric-card"><small>NÍVEL</small><strong>${account.level}</strong><span>${account.chapter_progression} capítulos</span></article><article class="metric-card"><small>RUNS</small><strong>${formatNumber(account.attempt_count)}</strong><span>tentativas</span></article><article class="metric-card"><small>ITENS</small><strong>${profile.items.length}</strong><span>no inventário</span></article><article class="metric-card"><small>ADMIN</small><strong>${account.is_admin ? 'SIM' : 'NÃO'}</strong><span>${account.password_set ? 'senha definida' : 'sem senha'}</span></article></div><div class="profile-section"><h4>Dinheiro e energia</h4><div class="profile-resource-list">${profileResourceRows([...(profile.currencies || []), ...(profile.energies || [])], 'Nenhuma moeda ou energia')}</div></div><div class="profile-columns">${sections}</div><div class="profile-section"><h4>Equipados</h4><div class="user-tags">${equipped}</div></div><div class="profile-section"><h4>Estatísticas</h4><div class="profile-resource-list">${stats}</div></div><div class="profile-actions"><button class="primary-action" data-profile-grant="${account.id}"><i class="fa-solid fa-gift"></i> Dar item / dinheiro</button><button class="secondary-action" data-profile-refresh="${account.id}"><i class="fa-solid fa-rotate"></i> Atualizar</button></div></div>`
  profileEl.hidden = false
  document.body.classList.add('profile-open')
}

$('#userSearchButton').addEventListener('click', () => loadAdminUsers($('#userSearch').value).catch(error => toast(error.message)))
$('#userSearch').addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); loadAdminUsers(event.target.value).catch(error => toast(error.message)) } })

$('#userList').addEventListener('click', async event => {
  const button = event.target.closest('[data-act]')
  if (!button) return
  const card = button.closest('[data-user]')
  const userId = Number(card.dataset.user)
  const isAdmin = card.querySelector('.tag.admin') !== null
  const act = button.dataset.act
  try {
    if (act === 'profile') {
      await loadAdminUserProfile(userId)
      return
    }
    if (act === 'reset') {
      const result = await api(`/account/admin/users/${userId}/reset-password`, { method: 'POST', body: '{}' })
      showResult({ title: 'Senha redefinida', text: `Nova senha do usuário #${userId}. As sessões ativas dele foram encerradas.`, code: result.password, copyable: true })
    }
    if (act === 'grant') openGrantModal(userId)
    if (act === 'admin') {
      await api(`/account/admin/users/${userId}/admin`, { method: 'POST', body: JSON.stringify({ is_admin: !isAdmin }) })
      toast('Permissão atualizada.')
      loadAdminUsers($('#userSearch').value).catch(() => {})
    }
    if (act === 'delete') {
      showConfirm('Excluir usuário', `Remover definitivamente o usuário #${userId} e todo o progresso dele? Não dá para desfazer.`, async () => {
        try {
          await api(`/account/admin/users/${userId}`, { method: 'DELETE' })
          toast('Usuário excluído.')
          loadAdminUsers($('#userSearch').value).catch(() => {})
        } catch (error) { toast(error.message) }
      })
    }
  } catch (error) { toast(error.message) }
})

$('#userProfile').addEventListener('click', event => {
  if (event.target === $('#userProfile') || event.target.closest('[data-close-profile]')) {
    $('#userProfile').hidden = true
    document.body.classList.remove('profile-open')
  }
  const grant = event.target.closest('[data-profile-grant]')
  if (grant) openGrantModal(Number(grant.dataset.profileGrant))
  const refresh = event.target.closest('[data-profile-refresh]')
  if (refresh) loadAdminUserProfile(Number(refresh.dataset.profileRefresh)).catch(error => toast(error.message))
})

/* --- conceder recurso --- */
let grantUserId = null
function openGrantModal (userId) {
  grantUserId = userId
  $('#grantTarget').textContent = `Para: jogador #${userId}`
  $('#grantStatus').textContent = ''
  $('#grantForm').reset()
  $('#grantForm').querySelector('[name="kind"]').value = 'currency'
  grantSelected = null
  $('#grantSelectedLabel').textContent = 'Nenhum item selecionado'
  $('#resourcePicker').innerHTML = '<p class="empty">Carregando catálogo…</p>'
  $('#grantModal').hidden = false
  searchResources('')
}
$('#grantCancel').addEventListener('click', () => { $('#grantModal').hidden = true })
$('#grantModal').addEventListener('click', event => { if (event.target === $('#grantModal')) $('#grantModal').hidden = true })

let resourceSearchTimer = null
let grantSelected = null
$('#grantResourceSearch').addEventListener('input', () => {
  clearTimeout(resourceSearchTimer)
  resourceSearchTimer = setTimeout(() => searchResources($('#grantResourceSearch').value), 250)
})
async function searchResources (query) {
  try {
    const { resources } = await api(`/account/admin/resources?query=${encodeURIComponent(query)}`)
    $('#resourcePicker').innerHTML = resources.length ? resources.map(row => `<button type="button" class="resource-choice ${grantSelected?.rid === row.rid ? 'selected' : ''}" data-resource-rid="${row.rid}" data-resource="${escapeHtml(row.tag || row.rid)}" data-resource-name="${escapeHtml(row.name)}" data-resource-kind="${escapeHtml(row.kind)}"><img src="${escapeHtml(row.icon || row.fallback || '/assets/img/kinds/pack.svg')}" alt=""><span><strong>${escapeHtml(row.name)}</strong><small>${escapeHtml(row.kind)} · #${row.rid}</small></span></button>`).join('') : '<p class="empty">Nenhum item encontrado. Verifique se o game-data está carregado.</p>'
  } catch { $('#resourcePicker').innerHTML = '<p class="empty">Não foi possível carregar o catálogo.</p>' }
}
$('#resourcePicker').addEventListener('click', event => {
  const choice = event.target.closest('[data-resource-rid]')
  if (!choice) return
  grantSelected = { rid: Number(choice.dataset.resourceRid), resource: choice.dataset.resource, name: choice.dataset.resourceName, kind: choice.dataset.resourceKind }
  $('#grantResource').value = grantSelected.resource
  $('#grantSelectedLabel').textContent = `${grantSelected.name} · ${grantSelected.kind}`
  $$('#resourcePicker .resource-choice').forEach(row => row.classList.toggle('selected', row === choice))
})
$('#grantForm').addEventListener('submit', async event => {
  event.preventDefault()
  const data = formData(event.target)
  if (!grantSelected) { status('grantStatus', 'Selecione um item no catálogo antes de conceder.'); return }
  status('grantStatus', 'Concedendo…')
  try {
    const grant = { resource: data.resource, amount: Number(data.amount), kind: data.kind }
    if (data.level) grant.level = Number(data.level)
    if (data.tier) grant.tier = Number(data.tier)
    await api(`/account/admin/users/${grantUserId}/grant`, { method: 'POST', body: JSON.stringify(grant) })
    status('grantStatus', 'Recurso concedido!', true)
    toast('Recurso concedido ao jogador.')
    setTimeout(() => { $('#grantModal').hidden = true }, 700)
  } catch (error) { status('grantStatus', error.message) }
})

/* --- pacotes da loja (preços e itens, inclusive itens de evento) --- */
async function loadAdminPacks () {
  const { packs } = await api('/account/admin/packs')
  $('#packList').innerHTML = packs.length ? packs.map(renderPackEditor).join('') : '<p class="empty">Nenhum pacote configurado. Crie o primeiro!</p>'
}

function rowEditor (label, rows, fields) {
  return `<label class="editor-label">${label}</label>
    <div class="editor-grid" data-rows="${rows.key}">
      ${rows.value.map((row, index) => `<div class="editor-row ${fields.length > 2 ? 'wide-row' : ''}" data-index="${index}">${fields.map(field => `<input data-field="${field.name}" value="${escapeHtml(String(row[field.name] ?? ''))}" placeholder="${field.placeholder}" ${field.type ? `type="${field.type}"` : ''}>`).join('')}<button type="button" data-remove-row><i class="fa-solid fa-xmark"></i></button></div>`).join('')}
    </div>
    <button type="button" class="mini-action" data-add-row="${rows.key}" style="margin-top:8px"><i class="fa-solid fa-plus"></i> Adicionar</button>`
}

function renderPackEditor (pack) {
  const costRows = { key: 'cost', value: (pack.cost || []).map(entry => ({ resource: entry.resource ?? entry.rid ?? '', amount: entry.amount ?? 0 })) }
  const contentRows = { key: 'contents', value: (pack.contents || []).map(entry => ({ resource: entry.resource ?? entry.rid ?? '', amount: entry.amount ?? 1, level: entry.level ?? '' })) }
  return `<article class="admin-card" data-pack="${pack.id}">
    <div class="admin-card-head">
      <h3>#${pack.id}</h3>
      <label class="switch-row" style="border:0;padding:0">Ativo na loja <input type="checkbox" class="switch" data-field="active" ${pack.active !== false ? 'checked' : ''}></label>
    </div>
    <div class="pack-admin-preview"><span class="editor-label">PREVIEW DOS ITENS</span>${packVisual(pack.preview?.contents || [], 'pack-visual-admin')}</div>
    <div class="editor-grid">
      <label>Tag do pacote<input data-field="tag" value="${escapeHtml(pack.tag || '')}" placeholder="revival_pack_x"></label>
    </div>
    ${rowEditor('PREÇO (MOEDAS DO JOGO)', costRows, [{ name: 'resource', placeholder: 'moeda (tag ou ID)' }, { name: 'amount', placeholder: 'valor', type: 'number' }])}
    ${rowEditor('CONTEÚDO (ITENS / MOEDAS / EVENTOS)', contentRows, [{ name: 'resource', placeholder: 'recurso (tag ou ID)' }, { name: 'amount', placeholder: 'qtd', type: 'number' }, { name: 'level', placeholder: 'nível (opc.)', type: 'number' }])}
    <div class="quota-row" style="margin-top:12px">
      <label>Cota<select data-field="quota-period">
        <option value="lifetime" ${!pack.quota ? 'selected' : ''}>Ilimitada</option>
        <option value="daily" ${pack.quota?.period === 'daily' ? 'selected' : ''}>Diária</option>
        <option value="weekly" ${pack.quota?.period === 'weekly' ? 'selected' : ''}>Semanal</option>
      </select></label>
      <label>Máximo por período<input data-field="quota-max" type="number" min="1" value="${pack.quota?.max ?? 1}"></label>
    </div>
    <div class="action-row">
      <button class="mini-action" data-act="save"><i class="fa-solid fa-floppy-disk"></i> Salvar pacote</button>
      <button class="mini-action danger" data-act="delete"><i class="fa-solid fa-trash"></i> Excluir</button>
    </div>
    ${pack.preview === null ? '<p class="form-status error">Este pacote tem recursos inválidos e não aparece no jogo.</p>' : ''}
  </article>`
}

$('#newPackButton').addEventListener('click', async () => {
  try {
    await api('/account/admin/packs', { method: 'POST', body: JSON.stringify({ tag: 'revival_novo_pacote', active: false, cost: [], contents: [] }) })
    toast('Pacote criado (inativo). Configure e ative.')
    loadAdminPacks().catch(() => {})
  } catch (error) { toast(error.message) }
})

$('#packList').addEventListener('click', async event => {
  if (event.target.closest('[data-add-row]')) {
    const key = event.target.closest('[data-add-row]').dataset.addRow
    const grid = event.target.closest('.admin-card').querySelector(`[data-rows="${key}"]`)
    grid.insertAdjacentHTML('beforeend', '<div class="editor-row"><input data-field="resource" placeholder="recurso"><input data-field="amount" type="number" placeholder="qtd" value="1"><button type="button" data-remove-row><i class="fa-solid fa-xmark"></i></button></div>')
    return
  }
  if (event.target.closest('[data-remove-row]')) {
    event.target.closest('.editor-row').remove()
    return
  }
  const button = event.target.closest('[data-act]')
  if (!button) return
  const card = button.closest('[data-pack]')
  const packId = card.dataset.pack
  if (button.dataset.act === 'delete') {
    showConfirm('Excluir pacote', `Remover o pacote #${packId} da loja?`, async () => {
      try {
        await api(`/account/admin/packs/${packId}`, { method: 'DELETE' })
        toast('Pacote excluído.')
        loadAdminPacks().catch(() => {})
        loadStore().catch(() => {})
      } catch (error) { toast(error.message) }
    })
    return
  }
  const collectRows = (key, fields) => [...card.querySelectorAll(`[data-rows="${key}"] .editor-row`)].map(row => {
    const entry = {}
    for (const field of fields) {
      const input = row.querySelector(`[data-field="${field}"]`)
      if (!input) continue
      const value = input.value.trim()
      if (value === '') continue
      entry[field] = field === 'resource' ? value : Number(value)
    }
    return entry
  }).filter(entry => entry.resource)
  const payload = {
    tag: card.querySelector('[data-field="tag"]').value.trim(),
    active: card.querySelector('[data-field="active"]').checked,
    cost: collectRows('cost', ['resource', 'amount']),
    contents: collectRows('contents', ['resource', 'amount', 'level'])
  }
  const period = card.querySelector('[data-field="quota-period"]').value
  const max = Number(card.querySelector('[data-field="quota-max"]').value) || 1
  payload.quota = period === 'lifetime' ? null : { period, max }
  try {
    await api(`/account/admin/packs/${packId}`, { method: 'PATCH', body: JSON.stringify(payload) })
    toast('Pacote salvo.')
    loadAdminPacks().catch(() => {})
    loadStore().catch(() => {})
  } catch (error) { toast(error.message) }
})

/* --- eventos: editor completo do contrato + filtros operacionais --- */
const STATUS_LABELS = { running: 'Rodando agora', always: 'Sempre ativo', scheduled: 'Agendado', ended: 'Encerrado', inactive: 'Inativo' }
const EVENT_TYPE_LABELS = { 0: 'None', 1: 'Game mode', 2: 'Store offer', 3: 'Battle pass' }
let adminEvents = []

function toLocalInput (value) {
  if (!value) return ''
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(Date.parse(value))
  if (Number.isNaN(date.getTime())) return ''
  const pad = n => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}
function eventDateLabel (value) {
  if (!value) return 'sem data'
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(Date.parse(value))
  return Number.isNaN(date.getTime()) ? 'data inválida' : date.toLocaleString('pt-BR', { dateStyle: 'medium', timeStyle: 'short' })
}
function jsonPretty (value, fallback = {}) { return JSON.stringify(value && typeof value === 'object' ? value : fallback, null, 2) }
function eventMatchesFilters (event) {
  const query = ($('#eventSearch')?.value || '').trim().toLowerCase()
  const statusFilter = $('#eventStatusFilter')?.value || 'all'
  const channelFilter = $('#eventChannelFilter')?.value || 'all'
  const haystack = `${event.id} ${event.tag || ''} ${event.channel || ''} ${EVENT_TYPE_LABELS[event.event_type] || ''}`.toLowerCase()
  return (!query || haystack.includes(query)) && (statusFilter === 'all' || event.status === statusFilter) && (channelFilter === 'all' || event.channel === channelFilter)
}
function renderEventCard (event) {
  const active = event.active !== false
  const argCount = Object.keys(event.args || {}).length
  const progressCount = Object.keys(event.progress_template || {}).length
  return `<article class="event-command-card ${active ? 'is-active' : 'is-muted'}" data-event="${event.id}">
    <div class="event-card-rail"><span class="event-id">#${event.id}</span><span class="status-chip ${event.status}"><i class="fa-solid ${event.status === 'running' || event.status === 'always' ? 'fa-circle-play' : event.status === 'scheduled' ? 'fa-clock' : 'fa-circle'}"></i> ${STATUS_LABELS[event.status] || event.status}</span></div>
    <div class="event-card-main"><div class="event-card-head"><div><span class="event-kicker">${escapeHtml(event.channel || 'game_mode')} · ${escapeHtml(EVENT_TYPE_LABELS[event.event_type] || 'None')}</span><h3>${escapeHtml(event.tag || `Evento ${event.id}`)}</h3></div><span class="event-live-dot ${active ? 'on' : ''}"></span></div>
      <div class="event-card-meta"><span><i class="fa-regular fa-calendar"></i> ${event.always ? 'Disponível sem janela' : `${eventDateLabel(event.start_time)} → ${eventDateLabel(event.end_time)}`}</span><span><i class="fa-solid fa-code"></i> ${argCount} args</span><span><i class="fa-solid fa-chart-line"></i> ${progressCount} campos de progresso</span></div>
      <div class="event-card-footer"><span class="tag ${active ? 'success' : ''}">${active ? 'publicação habilitada' : 'rascunho desativado'}</span><div class="action-row"><button class="mini-action" data-act="edit"><i class="fa-solid fa-pen-to-square"></i> Editar</button><button class="mini-action" data-act="duplicate"><i class="fa-solid fa-copy"></i> Duplicar</button><button class="mini-action danger" data-act="delete"><i class="fa-solid fa-trash"></i> Excluir</button></div></div>
    </div>
  </article>`
}
function renderEventMetrics () {
  const counts = { total: adminEvents.length, running: 0, scheduled: 0, drafts: 0 }
  for (const event of adminEvents) { if (event.status === 'running' || event.status === 'always') counts.running += 1; if (event.status === 'scheduled') counts.scheduled += 1; if (event.active === false) counts.drafts += 1 }
  $('#eventMetrics').innerHTML = [['TOTAL', counts.total, 'configurados'], ['AO VIVO', counts.running, 'disponíveis agora'], ['AGENDA', counts.scheduled, 'próximos eventos'], ['RASCUNHOS', counts.drafts, 'fora do ar']].map(([label, value, hint]) => `<div class="event-metric"><span>${label}</span><strong>${value}</strong><small>${hint}</small></div>`).join('')
}
function renderAdminEvents () {
  renderEventMetrics()
  const rows = adminEvents.filter(eventMatchesFilters)
  $('#eventList').innerHTML = rows.length ? rows.map(renderEventCard).join('') : '<div class="empty-state-large"><i class="fa-solid fa-calendar-xmark"></i><strong>Nenhum evento neste filtro</strong><span>Crie um evento ou ajuste a busca para continuar.</span></div>'
}
async function loadAdminEvents () {
  const result = await api('/account/admin/events')
  adminEvents = Array.isArray(result.events) ? result.events : []
  renderAdminEvents()
}
function setEventFormValue (form, name, value) { const field = form.elements[name]; if (field) field.value = value ?? '' }
function openEventEditor (event = null) {
  const modal = $('#eventEditorModal'); const form = $('#eventEditorForm')
  form.reset()
  setEventFormValue(form, 'id', event?.id || '')
  setEventFormValue(form, 'tag', event?.tag || `revival_event_${Date.now()}`)
  setEventFormValue(form, 'event_definition_id', event?.event_definition_id || event?.id || 990001)
  setEventFormValue(form, 'channel', event?.channel || 'game_mode')
  setEventFormValue(form, 'event_type', event?.event_type ?? 0)
  setEventFormValue(form, 'availability', event?.availability ?? 1)
  setEventFormValue(form, 'start_time', toLocalInput(event?.start_time))
  setEventFormValue(form, 'end_time', toLocalInput(event?.end_time))
  setEventFormValue(form, 'min_api_version', event?.min_api_version || '')
  setEventFormValue(form, 'max_api_version', event?.max_api_version || '')
  form.elements.active.checked = event ? event.active !== false : false
  form.elements.always.checked = event?.always === true
  setEventFormValue(form, 'args', jsonPretty(event?.args, { event_id: Number(event?.event_definition_id || event?.id || 990001) }))
  setEventFormValue(form, 'progress_template', jsonPretty(event?.progress_template, { event_id: Number(event?.event_definition_id || event?.id || 990001) }))
  $('#eventEditorTitle').textContent = event ? `Editar evento #${event.id}` : 'Novo evento'
  $('#eventEditorHint').textContent = event ? 'Alterações são gravadas no runtime e entram no próximo reload do servidor.' : 'O evento nasce inativo até você revisar e publicar.'
  status('eventEditorStatus', '')
  modal.hidden = false
  updateEventPreview()
  form.elements.tag.focus()
}
function closeEventEditor () { $('#eventEditorModal').hidden = true }
function eventFormPayload (form) {
  const parseObject = name => { const raw = String(form.elements[name].value || '').trim(); if (!raw) return {}; try { const value = JSON.parse(raw); if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('precisa ser um objeto JSON'); return value } catch (error) { throw new Error(`${name === 'args' ? 'Args' : 'Progress template'} inválido: ${error.message}`) } }
  return { tag: form.elements.tag.value.trim(), event_definition_id: Number(form.elements.event_definition_id.value), active: form.elements.active.checked, always: form.elements.always.checked, channel: form.elements.channel.value, event_type: Number(form.elements.event_type.value), availability: Number(form.elements.availability.value), start_time: form.elements.start_time.value || null, end_time: form.elements.end_time.value || null, min_api_version: form.elements.min_api_version.value.trim() || null, max_api_version: form.elements.max_api_version.value.trim() || null, args: parseObject('args'), progress_template: parseObject('progress_template') }
}
function updateEventPreview () {
  const preview = $('#eventEditorPreview code'); if (!preview) return
  try { preview.textContent = JSON.stringify(eventFormPayload($('#eventEditorForm')), null, 2) } catch (error) { preview.textContent = error.message }
}
$('#newEventButton').addEventListener('click', () => openEventEditor())
$('#eventEditorClose').addEventListener('click', closeEventEditor)
$('#eventEditorCancel').addEventListener('click', closeEventEditor)
$('#eventEditorModal').addEventListener('click', event => { if (event.target === $('#eventEditorModal')) closeEventEditor() })
$('#eventEditorForm').addEventListener('input', updateEventPreview)
$('#eventEditorForm').addEventListener('submit', async event => {
  event.preventDefault(); const form = event.target
  try {
    const payload = eventFormPayload(form); status('eventEditorStatus', 'Salvando…')
    const id = Number(form.elements.id.value)
    const result = await api(id ? `/account/admin/events/${id}` : '/account/admin/events', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) })
    closeEventEditor(); toast(id ? 'Evento atualizado.' : 'Evento criado como rascunho.')
    if (result.event) adminEvents = id ? adminEvents.map(row => row.id === id ? { ...result.event, status: row.status } : row) : [...adminEvents, { ...result.event, status: 'inactive' }]
    await loadAdminEvents()
  } catch (error) { status('eventEditorStatus', error.message) }
})
for (const selector of ['#eventSearch', '#eventStatusFilter', '#eventChannelFilter']) { $(selector).addEventListener('input', renderAdminEvents); $(selector).addEventListener('change', renderAdminEvents) }
$('#eventList').addEventListener('click', async event => {
  const button = event.target.closest('[data-act]'); if (!button) return
  const eventId = Number(button.closest('[data-event]').dataset.event); const current = adminEvents.find(row => row.id === eventId)
  if (!current) return
  if (button.dataset.act === 'edit') { openEventEditor(current); return }
  if (button.dataset.act === 'duplicate') {
    try { const copy = { ...current, id: undefined, tag: `${current.tag || 'revival_event'}_copy`, active: false }; delete copy.status; await api('/account/admin/events', { method: 'POST', body: JSON.stringify(copy) }); toast('Evento duplicado como rascunho.'); await loadAdminEvents() } catch (error) { toast(error.message) }
    return
  }
  showConfirm('Excluir evento', `Remover definitivamente o evento #${eventId}?`, async () => { try { await api(`/account/admin/events/${eventId}`, { method: 'DELETE' }); toast('Evento excluído.'); await loadAdminEvents() } catch (error) { toast(error.message) } })
})

/* --- mapa completo das rotas extraídas do APK --- */
let routeCatalog = null
function routeGateBadges (row) {
  const gates = [['schema_extracted', 'schema'], ['implemented', 'impl'], ['request_observed', 'req'], ['response_observed', 'res'], ['client_validated', 'cliente'], ['persistence_validated', 'persist'], ['regression_test', 'teste']]
  return gates.map(([field, label]) => `<span class="route-gate ${row[field] ? 'pass' : ''}" title="${field}">${row[field] ? '<i class="fa-solid fa-check"></i>' : '<i class="fa-solid fa-minus"></i>'} ${label}</span>`).join('')
}
function renderRouteCatalog () {
  if (!routeCatalog) return
  const query = ($('#routeSearch')?.value || '').trim().toLowerCase(); const module = $('#routeModuleFilter')?.value || 'all'; const gate = $('#routeGateFilter')?.value || 'all'
  const rows = routeCatalog.endpoints.filter(row => {
    const haystack = `${row.path} ${row.module} ${row.evidence || ''}`.toLowerCase()
    const gateOk = gate === 'all' || (gate === 'missing' && !row.client_validated) || (gate === 'validated' && row.client_validated) || (gate === 'implemented' && row.implemented)
    return (!query || haystack.includes(query)) && (module === 'all' || row.module === module) && gateOk
  })
  $('#routeList').innerHTML = rows.length ? rows.map(row => `<article class="route-row ${row.client_validated ? 'validated' : ''}"><div class="route-row-main"><span class="route-method">POST</span><div><code>${escapeHtml(row.path)}</code><small>${escapeHtml(row.module)}${row.uses_fallback ? ' · fallback ativo' : ''}</small></div></div><div class="route-gates">${routeGateBadges(row)}</div></article>`).join('') : '<div class="empty-state-large"><i class="fa-solid fa-filter-circle-xmark"></i><strong>Nenhuma rota neste filtro</strong><span>Refine a busca ou selecione outro módulo.</span></div>'
}
function renderRouteSummary () {
  const totals = routeCatalog.gate_totals || {}; const total = routeCatalog.route_count || routeCatalog.endpoints.length
  $('#routeSummary').innerHTML = [['ROTAS EXTRAÍDAS', total, 'contrato do APK', 'accent'], ['IMPLEMENTADAS', totals.implemented || 0, 'handlers no servidor', ''], ['OBSERVADAS', totals.request_observed || 0, 'requests reais', ''], ['VALIDADAS', totals.client_validated || 0, 'cliente confirmou', 'success']].map(([label, value, hint, tone]) => `<div class="route-summary-card ${tone}"><span>${label}</span><strong>${value}</strong><small>${hint}</small></div>`).join('')
}
async function loadAdminRoutes () {
  const result = await api('/account/admin/routes'); routeCatalog = result.compatibility || { endpoints: [], modules: [], gate_totals: {} }
  const moduleSelect = $('#routeModuleFilter'); const current = moduleSelect.value
  moduleSelect.innerHTML = '<option value="all">Todos os módulos</option>' + (routeCatalog.modules || []).map(row => `<option value="${escapeHtml(row.module)}">${escapeHtml(row.module)} (${row.total})</option>`).join(''); moduleSelect.value = current || 'all'
  renderRouteSummary(); renderRouteCatalog()
}
$('#routesRefresh').addEventListener('click', () => loadAdminRoutes().then(() => toast('Mapa de rotas atualizado.')).catch(error => toast(error.message)))
for (const selector of ['#routeSearch', '#routeModuleFilter', '#routeGateFilter']) { $(selector).addEventListener('input', renderRouteCatalog); $(selector).addEventListener('change', renderRouteCatalog) }

/* --- avisos --- */
async function loadAdminNotices () {
  const { notifications } = await api('/account/admin/notifications')
  $('#noticeAdminList').innerHTML = notifications.length
    ? notifications.map(renderNotice).join('')
    : '<p class="empty">Nenhum aviso publicado ainda.</p>'
}

$('#noticeForm').addEventListener('submit', async event => {
  event.preventDefault()
  const data = formData(event.target)
  status('noticeStatus', 'Publicando…')
  try {
    await api('/account/admin/notifications', { method: 'POST', body: JSON.stringify(data) })
    event.target.reset()
    status('noticeStatus', 'Aviso publicado para todos os jogadores.', true)
    toast('Aviso publicado.')
    loadAdminNotices().catch(() => {})
    loadNotices().catch(() => {})
  } catch (error) { status('noticeStatus', error.message) }
})

$('#notifyApk').addEventListener('click', () => {
  $$('#adminSubnav .chip').forEach(x => x.classList.toggle('active', x.dataset.sub === 'notices'))
  $$('.admin-sub').forEach(sub => {
    const active = sub.id === 'admin-notices'
    sub.classList.toggle('active', active)
    sub.hidden = !active
  })
  $('#noticeForm').querySelector('[name="title"]').value = 'Novo APK disponível para download'
  $('#noticeForm').querySelector('[name="kind"]').value = 'update'
  $('#noticeForm').querySelector('[name="body"]').focus()
  loadAdminNotices().catch(() => {})
})

/* --- vínculo com a conta do jogo (login-device) --- */
async function loadClaimable () {
  const list = $('#claimableList')
  if (!list) return
  const { accounts } = await api('/account/claimable')
  if (!accounts.length) {
    list.innerHTML = '<p class="empty">Nenhuma conta do jogo sem dono agora.</p>'
    return
  }
  list.innerHTML = accounts.map(account => `
    <article class="admin-card">
      <div class="admin-card-head">
        <h3>#${account.id} ${escapeHtml(account.display_name || 'Sem nome')}</h3>
        <div class="user-tags">
          <span class="tag">Nv ${account.level ?? 1}</span>
          <span class="tag">${formatNumber(account.attempt_count ?? 0)} runs</span>
        </div>
      </div>
      <div class="user-meta"><span>Desde ${formatDate(account.created_at)} · sem e-mail vinculado</span></div>
      <div class="action-row">
        <button class="mini-action" data-claim="${account.id}"><i class="fa-solid fa-link"></i> Vincular ao meu e-mail</button>
      </div>
    </article>`).join('')
  list.querySelectorAll('[data-claim]').forEach(button => button.addEventListener('click', async () => {
    if (!window.confirm(`Vincular a conta do jogo #${button.dataset.claim} a este e-mail? Ela passa a usar seu login atual.`)) return
    status('claimStatus', 'Vinculando…')
    try {
      await api('/account/claim-game', { method: 'POST', body: JSON.stringify({ game_user_id: Number(button.dataset.claim) }) })
      toast('Conta do jogo vinculada! Recarregando…')
      setTimeout(() => window.location.reload(), 900)
    } catch (error) { status('claimStatus', error.message) }
  }))
}

/* --- SMTP: recuperação por senha temporária --- */
async function loadAdminSmtp () {
  const { smtp } = await api('/account/admin/smtp')
  const form = $('#smtpForm')
  form.querySelector('[name="host"]').value = smtp.host || ''
  form.querySelector('[name="port"]').value = smtp.port || 587
  form.querySelector('[name="user"]').value = smtp.user || ''
  form.querySelector('[name="pass"]').value = ''
  form.querySelector('[name="from"]').value = smtp.from || ''
  form.querySelector('[name="from_name"]').value = smtp.from_name || ''
  form.querySelector('[name="secure"]').checked = Boolean(smtp.secure)
  form.querySelector('[name="allow_invalid_cert"]').checked = Boolean(smtp.allow_invalid_cert)
  renderSmtpPill(smtp)
  status('smtpStatus', smtp.configured ? 'Configurado. A recuperação por e-mail está ativa.' : 'Sem configuração: “Esqueci minha senha” fica indisponível (503).', smtp.configured)
}

// Estado visível sem revelar segredo: só o fato de haver ou não senha salva.
function renderSmtpPill (smtp) {
  const pill = $('#smtpStatePill')
  if (!pill) return
  pill.className = `health-pill ${smtp.configured ? 'healthy' : 'warning'}`
  const cert = smtp.allow_invalid_cert ? ' · certificado não validado' : ''
  pill.innerHTML = `<i class="fa-solid ${smtp.configured ? 'fa-circle-check' : 'fa-triangle-exclamation'}"></i> ${smtp.configured ? 'configurado' : 'não configurado'}${cert}`
}

$('#smtpForm').addEventListener('submit', async event => {
  event.preventDefault()
  const form = event.target
  const payload = {
    host: form.querySelector('[name="host"]').value.trim(),
    port: Number(form.querySelector('[name="port"]').value) || 587,
    user: form.querySelector('[name="user"]').value.trim(),
    from: form.querySelector('[name="from"]').value.trim(),
    from_name: form.querySelector('[name="from_name"]').value.trim(),
    secure: form.querySelector('[name="secure"]').checked,
    allow_invalid_cert: form.querySelector('[name="allow_invalid_cert"]').checked
  }
  const pass = form.querySelector('[name="pass"]').value
  if (pass) payload.pass = pass
  status('smtpStatus', 'Salvando…')
  try {
    const { smtp } = await api('/account/admin/smtp', { method: 'PATCH', body: JSON.stringify(payload) })
    form.querySelector('[name="pass"]').value = ''
    renderSmtpPill(smtp)
    status('smtpStatus', smtp.configured ? 'Salvo. Recuperação por senha temporária ativa.' : 'Salvo, mas incompleto: falta servidor ou remetente.', smtp.configured)
    toast('Configuração de e-mail salva.')
  } catch (error) { status('smtpStatus', error.message) }
})

/* --- personalização do site público --- */
const SITE_FLAGS = ['show_github', 'show_status', 'show_features', 'show_download', 'show_faq']

async function loadAdminSite () {
  const { site } = await api('/account/admin/site')
  const form = $('#siteForm')
  form.querySelector('[name="hero_title"]').value = site.hero_title || ''
  form.querySelector('[name="hero_description"]').value = site.hero_description || ''
  form.querySelector('[name="github_url"]').value = site.github_url || ''
  for (const flag of SITE_FLAGS) form.querySelector(`[name="${flag}"]`).checked = site[flag] !== false
}

$('#siteForm').addEventListener('submit', async event => {
  event.preventDefault()
  const form = event.target
  const payload = {
    hero_title: form.querySelector('[name="hero_title"]').value,
    hero_description: form.querySelector('[name="hero_description"]').value,
    github_url: form.querySelector('[name="github_url"]').value
  }
  for (const flag of SITE_FLAGS) payload[flag] = form.querySelector(`[name="${flag}"]`).checked
  status('siteStatus', 'Aplicando…')
  try {
    await api('/account/admin/site', { method: 'PATCH', body: JSON.stringify(payload) })
    status('siteStatus', 'Site atualizado! Recarregue a página principal para ver.', true)
    toast('Personalização do site aplicada.')
  } catch (error) { status('siteStatus', error.message) }
})

boot()
