// Autenticação do Revival: login, registro e recuperação por código.
// O painel em si vive em /slayer; aqui só preparamos a sessão e redirecionamos.
const $ = selector => document.querySelector(selector)
const $$ = selector => [...document.querySelectorAll(selector)]

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

// Alternância login/registro pelos tabs; a recuperação é uma "terceira
// aba" escondida, alcançada pelo botão "Esqueci minha senha".
function showAuth (name) {
  $$('.auth-tab').forEach(tab => tab.classList.toggle('active', tab.dataset.auth === name))
  $$('.auth-form').forEach(form => form.classList.toggle('active', form.id === `${name}Form`))
}

$$('.auth-tab').forEach(tab => tab.addEventListener('click', () => showAuth(tab.dataset.auth)))
$('#forgotButton').addEventListener('click', () => showAuth('reset'))
$('#backToLogin').addEventListener('click', () => showAuth('login'))
$$('[data-toggle-password]').forEach(button => button.addEventListener('click', () => { const input = button.parentElement.querySelector('input'); input.type = input.type === 'password' ? 'text' : 'password' }))

function goToPanel () { window.location.href = '/slayer' }

$('#loginForm').addEventListener('submit', async event => {
  event.preventDefault()
  status('loginStatus', 'Entrando…')
  try {
    await api('/account/login', { method: 'POST', body: JSON.stringify(formData(event.target)) })
    goToPanel()
  } catch (error) { status('loginStatus', error.message) }
})

$('#registerForm').addEventListener('submit', async event => {
  event.preventDefault()
  status('registerStatus', 'Criando sua conta…')
  try {
    const result = await api('/account/register', { method: 'POST', body: JSON.stringify(formData(event.target)) })
    // O código de recuperação só é exibido uma vez: guarda para o painel
    // mostrar em destaque logo após o redirect.
    try { sessionStorage.setItem('revival_recovery_code', result.recovery_code || '') } catch {}
    toast('Conta criada! Abrindo seu painel…')
    setTimeout(goToPanel, 600)
  } catch (error) { status('registerStatus', error.message) }
})

$('#resetForm').addEventListener('submit', async event => {
  event.preventDefault()
  status('resetStatus', 'Validando código…')
  try {
    const result = await api('/account/reset-password', { method: 'POST', body: JSON.stringify(formData(event.target)) })
    status('resetStatus', result.message || 'Senha redefinida. Faça login novamente.', true)
    event.target.reset()
    setTimeout(() => showAuth('login'), 1400)
  } catch (error) { status('resetStatus', error.message) }
})

// Já tem sessão ativa? Vai direto para o painel.
api('/account/me').then(goToPanel).catch(() => {})
