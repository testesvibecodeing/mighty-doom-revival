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
  showRecoveryBanner()
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

function showRecoveryBanner () {
  let code = ''
  try { code = sessionStorage.getItem('revival_recovery_code') || '' } catch {}
  if (!code) return
  sessionStorage.removeItem('revival_recovery_code')
  $('#recoveryCode').textContent = code
  $('#recoveryBanner').hidden = false
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
    const cover = contentEntries[0] || costEntries[0] || null
    return `<article class="store-card">
      <div class="store-cover">${iconImg(cover || {}, '')}</div>
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
  $$('.tab-panel').forEach(panel => panel.classList.toggle('active', panel.id === `panel-${tab.dataset.tab}`))
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
$('#copyRecovery').addEventListener('click', () => {
  navigator.clipboard?.writeText($('#recoveryCode').textContent).then(() => toast('Código copiado.'))
})

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
  $$('.admin-sub').forEach(sub => sub.classList.toggle('active', sub.id === `admin-${chip.dataset.sub}`))
  loadAdminSection(chip.dataset.sub)
}))

function loadAdminSection (name) {
  if (!me?.account?.is_admin) return
  if (name === 'overview') loadAdminOverview().catch(error => toast(error.message))
  if (name === 'users') loadAdminUsers().catch(error => toast(error.message))
  if (name === 'packs') loadAdminPacks().catch(error => toast(error.message))
  if (name === 'events') loadAdminEvents().catch(error => toast(error.message))
  if (name === 'notices') loadAdminNotices().catch(error => toast(error.message))
  if (name === 'site') loadAdminSite().catch(error => toast(error.message))
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
}

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
        <button class="mini-action" data-act="reset"><i class="fa-solid fa-key"></i> Nova senha</button>
        <button class="mini-action" data-act="recovery"><i class="fa-solid fa-rotate"></i> Recovery</button>
        <button class="mini-action" data-act="grant"><i class="fa-solid fa-gift"></i> Conceder</button>
        <button class="mini-action" data-act="admin"><i class="fa-solid fa-shield-halved"></i> ${user.is_admin ? 'Remover admin' : 'Tornar admin'}</button>
        <button class="mini-action danger" data-act="delete"><i class="fa-solid fa-trash"></i> Excluir</button>
      </div>
    </article>`).join('') : '<p class="empty">Nenhum usuário encontrado.</p>'
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
    if (act === 'reset') {
      const result = await api(`/account/admin/users/${userId}/reset-password`, { method: 'POST', body: '{}' })
      showResult({ title: 'Senha redefinida', text: `Nova senha do usuário #${userId}. As sessões ativas dele foram encerradas.`, code: result.password, copyable: true })
    }
    if (act === 'recovery') {
      const result = await api(`/account/admin/users/${userId}/recovery-code`, { method: 'POST', body: '{}' })
      showResult({ title: 'Novo código de recuperação', text: `Entregue este código ao jogador #${userId} com segurança.`, code: result.recovery_code, copyable: true })
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

/* --- conceder recurso --- */
let grantUserId = null
function openGrantModal (userId) {
  grantUserId = userId
  $('#grantTarget').textContent = `Para: jogador #${userId}`
  $('#grantStatus').textContent = ''
  $('#grantForm').reset()
  $('#grantModal').hidden = false
  searchResources('')
}
$('#grantCancel').addEventListener('click', () => { $('#grantModal').hidden = true })
$('#grantModal').addEventListener('click', event => { if (event.target === $('#grantModal')) $('#grantModal').hidden = true })

let resourceSearchTimer = null
$('#grantResource').addEventListener('input', () => {
  clearTimeout(resourceSearchTimer)
  resourceSearchTimer = setTimeout(() => searchResources($('#grantResource').value), 300)
})
async function searchResources (query) {
  try {
    const { resources } = await api(`/account/admin/resources?query=${encodeURIComponent(query)}`)
    $('#resourceOptions').innerHTML = resources.map(row => `<option value="${escapeHtml(row.tag || row.rid)}">${escapeHtml(row.name)} (${row.kind})</option>`).join('')
  } catch {}
}
$('#grantForm').addEventListener('submit', async event => {
  event.preventDefault()
  const data = formData(event.target)
  status('grantStatus', 'Concedendo…')
  try {
    await api(`/account/admin/users/${grantUserId}/grant`, { method: 'POST', body: JSON.stringify({ resource: data.resource, amount: Number(data.amount) }) })
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

/* --- eventos --- */
const STATUS_LABELS = { running: 'Rodando', always: 'Sempre ativo', scheduled: 'Agendado', ended: 'Encerrado', inactive: 'Inativo' }

function toLocalInput (value) {
  if (!value) return ''
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(Date.parse(value))
  if (Number.isNaN(date.getTime())) return ''
  const pad = n => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

async function loadAdminEvents () {
  const { events } = await api('/account/admin/events')
  $('#eventList').innerHTML = events.length ? events.map(event => `
    <article class="admin-card" data-event="${event.id}">
      <div class="admin-card-head">
        <h3>#${event.id} ${escapeHtml(event.tag || '')}</h3>
        <span class="status-chip ${event.status}">${STATUS_LABELS[event.status] || event.status}</span>
      </div>
      <div class="switch-row"><span>Ativo</span><input type="checkbox" class="switch" data-field="active" ${event.active !== false ? 'checked' : ''}></div>
      <div class="switch-row"><span>Sempre disponível (ignora datas)</span><input type="checkbox" class="switch" data-field="always" ${event.always === true ? 'checked' : ''}></div>
      <div class="quota-row" style="margin-top:10px">
        <label>Início<input data-field="start_time" type="datetime-local" value="${toLocalInput(event.start_time)}"></label>
        <label>Fim<input data-field="end_time" type="datetime-local" value="${toLocalInput(event.end_time)}"></label>
      </div>
      <div class="action-row">
        <button class="mini-action" data-act="save"><i class="fa-solid fa-floppy-disk"></i> Salvar evento</button>
        <button class="mini-action danger" data-act="delete"><i class="fa-solid fa-trash"></i> Excluir</button>
      </div>
    </article>`).join('') : '<p class="empty">Nenhum evento configurado.</p>'
}

$('#newEventButton').addEventListener('click', async () => {
  try {
    await api('/account/admin/events', { method: 'POST', body: JSON.stringify({ tag: 'revival_novo_evento', active: false, always: false }) })
    toast('Evento criado (inativo). Configure as datas e ative.')
    loadAdminEvents().catch(() => {})
  } catch (error) { toast(error.message) }
})

$('#eventList').addEventListener('click', async event => {
  const button = event.target.closest('[data-act]')
  if (!button) return
  const card = button.closest('[data-event]')
  const eventId = card.dataset.event
  if (button.dataset.act === 'delete') {
    showConfirm('Excluir evento', `Remover o evento #${eventId}?`, async () => {
      try {
        await api(`/account/admin/events/${eventId}`, { method: 'DELETE' })
        toast('Evento excluído.')
        loadAdminEvents().catch(() => {})
      } catch (error) { toast(error.message) }
    })
    return
  }
  const payload = {
    active: card.querySelector('[data-field="active"]').checked,
    always: card.querySelector('[data-field="always"]').checked,
    start_time: card.querySelector('[data-field="start_time"]').value || null,
    end_time: card.querySelector('[data-field="end_time"]').value || null
  }
  try {
    await api(`/account/admin/events/${eventId}`, { method: 'PATCH', body: JSON.stringify(payload) })
    toast('Evento salvo.')
    loadAdminEvents().catch(() => {})
  } catch (error) { toast(error.message) }
})

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
  $$('.admin-sub').forEach(sub => sub.classList.toggle('active', sub.id === 'admin-notices'))
  $('#noticeForm').querySelector('[name="title"]').value = 'Novo APK disponível para download'
  $('#noticeForm').querySelector('[name="kind"]').value = 'update'
  $('#noticeForm').querySelector('[name="body"]').focus()
  loadAdminNotices().catch(() => {})
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
