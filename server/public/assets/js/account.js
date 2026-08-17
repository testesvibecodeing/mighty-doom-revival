const $ = selector => document.querySelector(selector)
const $$ = selector => [...document.querySelectorAll(selector)]
const authView = $('#authView')
const dashboardView = $('#dashboardView')
let accountState = null

function formData (form) { return Object.fromEntries(new FormData(form).entries()) }
function status (id, message, ok = false) {
  const el = $(`#${id}`)
  if (!el) return
  el.textContent = message || ''
  el.className = `form-status ${ok ? 'ok' : message ? 'error' : ''}`
}
function toast (message) {
  const el = $('#toast')
  el.textContent = message
  el.classList.add('show')
  setTimeout(() => el.classList.remove('show'), 3600)
}
async function api (path, options = {}) {
  const response = await fetch(path, { credentials: 'same-origin', headers: { 'content-type': 'application/json', ...(options.headers || {}) }, ...options })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.error || 'Não foi possível concluir a operação.')
  return body
}
function showAuth (name) {
  $$('.auth-tab').forEach(tab => tab.classList.toggle('active', tab.dataset.auth === name))
  $$('.auth-form').forEach(form => form.classList.toggle('active', form.id === `${name}Form`))
}
function formatNumber (value) { return Number(value || 0).toLocaleString('pt-BR') }
function formatDate (epoch) { return epoch ? new Date(epoch * 1000).toLocaleDateString('pt-BR') : '--' }
function renderDashboard () {
  const { account, snapshot } = accountState
  $('#dashName').textContent = account.display_name || `Slayer #${account.id}`
  $('#dashId').textContent = account.id
  $('#dashCreated').textContent = formatDate(account.created_at)
  const progression = snapshot.progression || {}
  $('#metricLevel').textContent = progression.level || 1
  $('#metricChapters').textContent = `${progression.chapters || 0} capítulos concluídos`
  $('#metricItems').textContent = formatNumber(snapshot.items?.length)
  $('#metricAttempts').textContent = formatNumber(progression.attempts)
  const resources = [...(snapshot.currencies || []), ...(snapshot.energies || [])]
  $('#metricCoins').textContent = formatNumber(snapshot.currencies?.[0]?.amount)
  $('#resourceList').innerHTML = resources.length ? resources.map(row => `<div class="resource-row"><span>${escapeHtml(row.name)}</span><strong>${formatNumber(row.amount)}</strong></div>`).join('') : '<p class="empty">Nenhum recurso registrado ainda.</p>'
  const stats = progression.stats || []
  $('#statsList').innerHTML = stats.length ? stats.slice(0, 8).map(row => `<div class="stat-row"><span>${escapeHtml(row.tag || row.id || 'Estatística')}</span><strong>${formatNumber(row.value)}</strong></div>`).join('') : '<p class="empty">Jogue uma partida para gerar estatísticas.</p>'
  $('#inventoryCount').textContent = `${snapshot.items?.length || 0} itens`
  $('#inventoryGrid').innerHTML = snapshot.items?.length ? snapshot.items.map(item => `<article class="item-card"><span class="item-kind">${escapeHtml(item.kind)}</span><h3>${escapeHtml(item.name)}</h3><div class="item-meta"><span>Nível ${item.level || 1}</span><span>x${item.amount || 1}</span></div></article>`).join('') : '<p class="empty">Seu inventário ainda está vazio.</p>'
  $('#profileName').value = account.display_name || ''
  $('#profileEmail').value = account.email || ''
}
function escapeHtml (value) { return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]) }
function openDashboard (payload) { accountState = payload; authView.hidden = true; dashboardView.hidden = false; renderDashboard() }
async function refresh () { openDashboard(await api('/account/me', { method: 'GET', headers: {} })) }

$$('.auth-tab').forEach(tab => tab.addEventListener('click', () => showAuth(tab.dataset.auth)))
$$('[data-toggle-password]').forEach(button => button.addEventListener('click', () => { const input = button.parentElement.querySelector('input'); input.type = input.type === 'password' ? 'text' : 'password' }))
$('#loginForm').addEventListener('submit', async event => { event.preventDefault(); status('loginStatus', 'Entrando…'); try { openDashboard(await api('/account/login', { method: 'POST', body: JSON.stringify(formData(event.target)) })) } catch (error) { status('loginStatus', error.message) } })
$('#registerForm').addEventListener('submit', async event => { event.preventDefault(); status('registerStatus', 'Criando sua conta…'); try { const result = await api('/account/register', { method: 'POST', body: JSON.stringify(formData(event.target)) }); await refresh(); toast(`Código de recuperação: ${result.recovery_code}`) } catch (error) { status('registerStatus', error.message) } })
$('#resetForm').addEventListener('submit', async event => { event.preventDefault(); status('resetStatus', 'Validando código…'); try { const result = await api('/account/reset-password', { method: 'POST', body: JSON.stringify(formData(event.target)) }); status('resetStatus', result.message, true); event.target.reset(); setTimeout(() => showAuth('login'), 1200) } catch (error) { status('resetStatus', error.message) } })
$('#logoutButton').addEventListener('click', async () => { await api('/account/logout', { method: 'POST', body: '{}' }); dashboardView.hidden = true; authView.hidden = false; showAuth('login') })
$$('.dashboard-tab').forEach(tab => tab.addEventListener('click', () => { $$('.dashboard-tab').forEach(x => x.classList.toggle('active', x === tab)); $$('.dashboard-panel').forEach(panel => panel.classList.toggle('active', panel.id === `panel-${tab.dataset.panel}`)) }))
$('#profileForm').addEventListener('submit', async event => { event.preventDefault(); status('profileStatus', 'Salvando…'); try { const result = await api('/account/profile', { method: 'PATCH', body: JSON.stringify(formData(event.target)) }); accountState.account = result.account; renderDashboard(); status('profileStatus', 'Dados atualizados.', true) } catch (error) { status('profileStatus', error.message) } })
$('#passwordForm').addEventListener('submit', async event => { event.preventDefault(); status('passwordStatus', 'Atualizando…'); try { const result = await api('/account/password', { method: 'POST', body: JSON.stringify(formData(event.target)) }); event.target.reset(); status('passwordStatus', result.message, true) } catch (error) { status('passwordStatus', error.message) } })
refresh().catch(() => {})
