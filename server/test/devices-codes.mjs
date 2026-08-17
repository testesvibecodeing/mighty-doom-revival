import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'

import { Repository } from '../src/db.js'
import { handleDevicesRequest } from '../src/devices.js'
import { redeemCode } from '../src/codes.js'

const coins = { id: 100, tag: 'coins', category_id: 1 }
const gems = { id: 101, tag: 'gems', category_id: 1 }
const runtime = {
  gameData: {
    resources: [coins, gems],
    codes: [
      { code: 'REVIVAL', resources: [{ resource: 'coins', amount: 150 }] },
      { code: 'GEMS', resources: [{ resource: 'gems', kind: 'currency', amount: 5 }] },
      { code: 'EMPTY', resources: [] }
    ]
  },
  revival: {},
  index: { byId: new Map([[100, coins], [101, gems]]), byTag: new Map([['coins', 100], ['gems', 101]]) }
}

const dir = mkdtempSync(resolve(tmpdir(), 'mighty-doom-devices-'))
const dbPath = resolve(dir, 'devices.sqlite3')
const repo = new Repository(dbPath)

try {
  const { user } = repo.createUser()
  const UID = user.id

  // ---- DevicesApi (4 rotas) ----
  assert.equal(handleDevicesRequest('/game/devices/register', {}, UID, repo).error[2].reason, 'platform-required')
  let response = handleDevicesRequest('/game/devices/register', { platform: 'android', region: 'US' }, UID, repo)
  assert.equal(Object.keys(response.data).length, 1, 'Register só tem device no wrapper')
  assert.equal(response.data.device.id, 1)
  assert.equal(response.data.device.platform, 'android')
  assert.equal(response.data.device.region, 'US')
  assert.equal(typeof response.data.device.authorization_time, 'number')
  response = handleDevicesRequest('/game/devices/register', { platform: 'ios' }, UID, repo)
  assert.equal(response.data.device.id, 2, 'ids sequenciais por jogador')
  assert.equal(response.data.device.region, null)

  response = handleDevicesRequest('/game/devices/list', {}, UID, repo)
  assert.deepEqual(response.data.devices.map(device => device.id), [1, 2])

  assert.equal(handleDevicesRequest('/game/devices/describe', {}, UID, repo).error[2].reason, 'device-id-required')
  assert.equal(handleDevicesRequest('/game/devices/describe', { device_id: 9 }, UID, repo).error[2].reason, 'device-not-found')
  response = handleDevicesRequest('/game/devices/describe', { device_id: 1 }, UID, repo)
  assert.equal(response.data.device.platform, 'android')

  assert.equal(handleDevicesRequest('/game/devices/unregister', { device_id: 9 }, UID, repo).error[2].reason, 'device-not-found')
  response = handleDevicesRequest('/game/devices/unregister', { device_id: 1 }, UID, repo)
  assert.equal(Object.keys(response.data).length, 0, 'Unregister sem DTO -> envelope puro')
  response = handleDevicesRequest('/game/devices/list', {}, UID, repo)
  assert.deepEqual(response.data.devices.map(device => device.id), [2])

  // ---- CodesApi.Redeem(code) ----
  assert.equal(redeemCode(repo, UID, {}, runtime).error[2].reason, 'code-required')
  assert.equal(redeemCode(repo, UID, { code: 'NOPE' }, runtime).error[2].reason, 'code-not-found')
  response = redeemCode(repo, UID, { code: 'REVIVAL' }, runtime)
  assert.deepEqual(response.data.resources, [{ rid: 100, amount: 150 }])
  assert.equal(repo.balance(UID, 100), 150)
  assert.equal(redeemCode(repo, UID, { code: 'REVIVAL' }, runtime).error[2].reason, 'code-already-redeemed')
  response = redeemCode(repo, UID, { code: 'GEMS' }, runtime)
  assert.deepEqual(response.data.resources, [{ rid: 101, amount: 5 }])
  assert.equal(repo.balance(UID, 101), 5)
  response = redeemCode(repo, UID, { code: 'EMPTY' }, runtime)
  assert.deepEqual(response.data.resources, [], 'código sem recursos concede lista vazia honesta')

  // persistência: devices e resgates sobrevivem ao restart.
  repo.close()
  const reopened = new Repository(dbPath)
  response = handleDevicesRequest('/game/devices/list', {}, UID, reopened)
  assert.deepEqual(response.data.devices.map(device => device.id), [2])
  assert.equal(redeemCode(reopened, UID, { code: 'REVIVAL' }, runtime).error[2].reason, 'code-already-redeemed')
  assert.equal(reopened.balance(UID, 100), 150)
  assert.equal(reopened.balance(UID, 101), 5)
  reopened.close()

  console.log('Mighty DOOM Revival devices/codes test: PASS')
} finally {
  try { repo.close() } catch {}
  rmSync(dir, { recursive: true, force: true })
}
