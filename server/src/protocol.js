export function nowSeconds () {
  return Math.floor(Date.now() / 1000)
}

export function formatServerTimestamp (date = new Date()) {
  const pad = (n, w = 2) => String(n).padStart(w, '0')
  return (
    `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}` +
    `T${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())}`
  )
}

export function wire (data = {}, code = 1000) {
  // O cliente 1.13.1 faz parse estrito do uts em ParseServerTimestamp; a chave
  // do wire é "uts" sozinha no formato "yyyy-MM-ddTHH:mm:ss" UTC (confirmado
  // por bisseção no emulador; unix epoch e "yyyy-MM-dd HH:mm:ss" falham).
  return { uts: formatServerTimestamp(), code, ...data }
}

export function ok (ctx, data = {}) {
  ctx.status = 200
  ctx.type = 'application/json'
  ctx.body = wire(data)
}

export function fail (ctx, httpStatus = 400, code = 2000, data = {}) {
  ctx.status = httpStatus
  ctx.type = 'application/json'
  ctx.body = wire(data, code)
}

export function extractToken (ctx) {
  const ubu = ctx.get('x-ubu-token')
  if (ubu) return ubu
  const auth = ctx.get('authorization')
  if (auth.toLowerCase().startsWith('bearer ')) return auth.slice(7).trim()
  return auth || null
}

export function gameGuard (runtimeProvider) {
  return async (ctx, next) => {
    const runtime = runtimeProvider()
    if (ctx.method !== 'POST') return fail(ctx, 405, 2200)
    if (ctx.get('x-ubu-apiversion') !== runtime.revival.api_version) {
      return fail(ctx, 403, 2200)
    }
    if (!ctx.is('application/json')) return fail(ctx, 400, 2200)
    await next()
  }
}

export function requireUser (repo) {
  return async (ctx, next) => {
    const token = extractToken(ctx)
    const user = token ? repo.userByToken(token) : null
    if (!user) return fail(ctx, 401, 2101)
    ctx.state.user = user
    await next()
  }
}
