// ---- Contrato extraído do global-metadata.dat v29 (2026-08-17) ----
// DevicesApi: Register(platform, region), Unregister(deviceId), List(),
// Describe(deviceId) — 4 rotas game/devices/*.
// DataObjects CONFIRMADOS: AuthorizedDevice{id, platform, region,
// authorizationTime, lastAccessTime}; DeviceInfo{region, platform}.
// Literais de wire no cliente (Nível 1): 'device', 'devices', 'platform',
// 'region'. A VERIFICAR até captura do cliente: nome do parâmetro deviceId
// no request (aqui device_id, fallback snake), wrapper exato do Describe e
// se Describe refresca lastAccessTime (aqui sim — semântica do campo).

const NS = 'devices'
const KEY = 'devices'

function nowSeconds () {
  return Math.floor(Date.now() / 1000)
}

function deviceRows (repo, userId) {
  const saved = repo.getState(userId, NS, KEY, [])
  return Array.isArray(saved) ? saved : []
}

// AuthorizedDevice no wire (fallback snake dos campos C# confirmados).
function deviceWire (row) {
  return {
    id: Number(row.id),
    platform: row.platform,
    region: row.region ?? null,
    authorization_time: Number(row.authorization_time) || 0,
    last_access_time: Number(row.last_access_time) || 0
  }
}

export function handleDevicesRequest (path, body, userId, repo) {
  if (path === '/game/devices/register') {
    const platform = typeof body?.platform === 'string' ? body.platform.trim() : ''
    if (platform.length === 0) return { error: [400, 2200, { reason: 'platform-required' }] }
    const region = typeof body?.region === 'string' && body.region.trim().length > 0
      ? body.region.trim()
      : null
    const rows = deviceRows(repo, userId)
    const id = rows.reduce((max, row) => Math.max(max, Number(row.id) || 0), 0) + 1
    const row = {
      id,
      platform,
      region,
      authorization_time: nowSeconds(),
      last_access_time: nowSeconds()
    }
    repo.setState(userId, NS, KEY, [...rows, row])
    return { data: { device: deviceWire(row) } }
  }

  if (path === '/game/devices/list') {
    return { data: { devices: deviceRows(repo, userId).map(deviceWire) } }
  }

  if (path === '/game/devices/describe' || path === '/game/devices/unregister') {
    const deviceId = Number.isInteger(body?.device_id) ? body.device_id : null
    if (deviceId === null) return { error: [400, 2200, { reason: 'device-id-required' }] }
    const rows = deviceRows(repo, userId)
    const index = rows.findIndex(row => Number(row.id) === deviceId)
    if (index === -1) return { error: [400, 2300, { reason: 'device-not-found' }] }

    if (path === '/game/devices/unregister') {
      rows.splice(index, 1)
      repo.setState(userId, NS, KEY, rows)
      return { data: {} }
    }

    const row = { ...rows[index], last_access_time: nowSeconds() }
    rows[index] = row
    repo.setState(userId, NS, KEY, rows)
    return { data: { device: deviceWire(row) } }
  }

  return null
}
