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
  const form = event.target
  const data = formData(form)
  // Com código do e-mail em mãos vai pela via nova; sem ele, cai no RV-.
  const payload = data.code
    ? { email: data.email, code: data.code, new_password: data.new_password }
    : { login: data.email, recovery_code: (data.recovery_code || '').trim(), new_password: data.new_password }
  status('resetStatus', 'Validando…')
  try {
    const result = await api('/account/reset-password', { method: 'POST', body: JSON.stringify(payload) })
    status('resetStatus', result.message || 'Senha redefinida. Faça login novamente.', true)
    form.reset()
    setTimeout(() => showAuth('login'), 1400)
  } catch (error) { status('resetStatus', error.message) }
})

$('#sendResetCode').addEventListener('click', async () => {
  const email = $('#resetForm').querySelector('[name="email"]').value.trim()
  if (!email) return status('resetStatus', 'Digite o e-mail da conta acima.')
  status('resetStatus', 'Enviando código…')
  try {
    const result = await api('/account/forgot-password', { method: 'POST', body: JSON.stringify({ email }) })
    if (result.code_sent) status('resetStatus', 'Código enviado! Confira sua caixa de entrada (e o spam).', true)
    else status('resetStatus', 'Este servidor não tem SMTP: use o código de recuperação RV- abaixo.')
  } catch (error) { status('resetStatus', error.message) }
})

/* --- entrada por código de e-mail: 1º acesso cria a conta --- */
let codeCooldown = 0

function startCodeCooldown () {
  const button = $('#requestCode')
  codeCooldown = 60
  button.disabled = true
  const tick = setInterval(() => {
    codeCooldown -= 1
    if (codeCooldown <= 0) {
      clearInterval(tick)
      button.disabled = false
      button.innerHTML = 'Receber código <i class="fa-solid fa-envelope-open-text"></i>'
    } else {
      button.textContent = `Reenviar em ${codeCooldown}s`
    }
  }, 1000)
}

$('#requestCode').addEventListener('click', async () => {
  const form = $('#emailForm')
  const email = form.querySelector('[name="email"]').value.trim()
  if (!email) return status('emailStatus', 'Digite seu e-mail primeiro.')
  status('emailStatus', 'Enviando código…')
  try {
    const result = await api('/account/email-code/request', { method: 'POST', body: JSON.stringify({ email }) })
    const input = form.querySelector('[name="code"]')
    input.disabled = false
    $('#emailLogin').disabled = false
    input.focus()
    startCodeCooldown()
    status('emailStatus', result.account_created
      ? 'Conta criada! Código enviado ao seu e-mail (válido por 10 minutos).'
      : 'Código enviado (válido por 10 minutos).', true)
  } catch (error) { status('emailStatus', error.message) }
})

$('#emailForm').addEventListener('submit', async event => {
  event.preventDefault()
  status('emailStatus', 'Entrando…')
  try {
    const result = await api('/account/email-code/login', { method: 'POST', body: JSON.stringify(formData(event.target)) })
    if (result.password_set === false) {
      try { sessionStorage.setItem('revival_password_hint', '1') } catch {}
    }
    goToPanel()
  } catch (error) { status('emailStatus', error.message) }
})

// Já tem sessão ativa? Vai direto para o painel.
api('/account/me').then(goToPanel).catch(() => {})
