import assert from 'node:assert/strict'
import { claimDailyReward, claimIdleReward, dailyRewardState, durationSeconds, formatDuration, idleRewardState, proximoClaimEmSegundos } from '../src/rewards.js'

class MemoryRepo {
  constructor () {
    this.states = new Map()
    this.balances = new Map()
    this.user = { id: 1, chapter_progression: 0 }
  }

  tx (fn) { return fn() }
  userById () { return this.user }

  stateKey (userId, namespace, key) { return `${userId}:${namespace}:${key}` }
  getState (userId, namespace, key, fallback = null) {
    return this.states.has(this.stateKey(userId, namespace, key))
      ? this.states.get(this.stateKey(userId, namespace, key))
      : fallback
  }
  setState (userId, namespace, key, value) {
    this.states.set(this.stateKey(userId, namespace, key), structuredClone(value))
  }

  balance (userId, rid) { return this.balances.get(`${userId}:${rid}`) || 0 }
  addCurrency (userId, rid, delta) {
    const key = `${userId}:${rid}`
    const next = this.balance(userId, rid) + delta
    if (next < 0) throw new Error('negative balance')
    this.balances.set(key, next)
    return next
  }

  energy () { return null }
  setEnergy () { throw new Error('not expected') }
  addCosmetic () { throw new Error('not expected') }
  addEntitlement () { throw new Error('not expected') }
  addItem () { throw new Error('not expected') }
}

const coins = { id: 100, rid: 100, tag: 'coins', category_id: 1 }
const runtime = {
  revival: {},
  gameData: {
    resources: [coins],
    daily_rewards: {
      days: [
        { resources: [{ resource: 'coins', amount: 25 }] },
        { resources: [{ resource: 'coins', amount: 50 }] }
      ]
    },
    idle_reward: {
      generation_period: 60,
      max_generation_periods: 10,
      chapter_idle_generation: [
        { chapter_progress: 0, idle_generation: [{ resource: 'coins', amount: 3 }] }
      ]
    }
  },
  index: {
    byTag: new Map([['coins', 100]]),
    byId: new Map([[100, coins]])
  }
}

const repo = new MemoryRepo()
const dayOne = 2_000_000_000

const before = dailyRewardState(repo, 1, runtime, dayOne)
assert.equal(before.claimable, true)
assert.equal(before.state.day, 1)

const first = claimDailyReward(repo, 1, runtime, dayOne)
assert.equal(first.ok, true)
assert.equal(first.claimed_day, 1)
assert.deepEqual(first.resources, [{ rid: 100, amount: 25 }])
assert.equal(repo.balance(1, 100), 25)

const duplicate = claimDailyReward(repo, 1, runtime, dayOne + 30)
assert.deepEqual(duplicate, { ok: false, reason: 'already-claimed' })
assert.equal(repo.balance(1, 100), 25)

const second = claimDailyReward(repo, 1, runtime, dayOne + 86400)
assert.equal(second.ok, true)
assert.equal(second.claimed_day, 2)
assert.equal(repo.balance(1, 100), 75)
assert.equal(dailyRewardState(repo, 1, runtime, dayOne + 86401).state.day, 1)

const idleInitial = idleRewardState(repo, 1, runtime, dayOne)
assert.equal(idleInitial.claimable_periods, 0)

const idle = claimIdleReward(repo, 1, runtime, dayOne + 305)
assert.equal(idle.ok, true)
assert.equal(idle.periods, 5)
assert.equal(repo.balance(1, 100), 90)

const idleAfter = idleRewardState(repo, 1, runtime, dayOne + 305)
assert.equal(idleAfter.claimable_periods, 0)

const capped = claimIdleReward(repo, 1, runtime, dayOne + 60 * 30)
assert.equal(capped.ok, true)
assert.equal(capped.periods, 10)
assert.equal(repo.balance(1, 100), 120)


// ---------------------------------------------------------------------------
// Regressao medida no rig em 2026-08-20 (request_log 326, `Network response (14)`):
// o game-data real traz `idle_reward.generation_period === '0D00H05M00S'`, uma
// DURACAO em texto. `Number(...)` disso e NaN, e `JSON.stringify(NaN)` emite
// **null** — o wire saiu com `"generation_period": null` e o cliente abortou o
// restart com `Malformed response payload`. Numerico nao-nullable jamais vai
// como null (DEAD-ENDS #3).
// ---------------------------------------------------------------------------
{
  assert.equal(durationSeconds('0D00H05M00S'), 300, 'formato real do game-data')
  assert.equal(durationSeconds('0D01H00M00S'), 3600)
  assert.equal(durationSeconds('1D00H00M00S'), 86400)
  assert.equal(durationSeconds('0D00H00M45S'), 45)
  assert.equal(durationSeconds(300), 300, 'numero passa direto')
  assert.equal(durationSeconds('300'), 300, 'numero em texto tambem')
  for (const ruim of [null, undefined, '', '   ', 'lixo', NaN, {}, []]) {
    const r = durationSeconds(ruim)
    assert.equal(r, 0, `valor irreconhecivel vira o fallback: ${JSON.stringify(ruim)}`)
    assert.ok(Number.isFinite(r), 'nunca NaN')
  }
  assert.equal(durationSeconds('lixo', 7), 7, 'fallback e configuravel')
}

{
  // O wire com o game-data REAL nao pode conter null nem NaN em campo numerico.
  const repoWire = new MemoryRepo()
  const runtimeReal = {
    gameData: {
      idle_reward: {
        generation_period: '0D00H05M00S',
        chapter_idle_generation: [{ chapter_progress: 0, idle_generation: [{ rid: 100, amount: 4 }] }]
      }
    }
  }
  const estado = idleRewardState(repoWire, 1, runtimeReal, 1000)
  // CONTRATO medido por bissecao no rig (2026-08-20): `generation_period` vai
  // no wire como DURACAO EM TEXTO. Inteiro derruba o parse do cliente com
  // `Malformed response payload`; TimeSpan .NET ('00:05:00') tambem. Este
  // formato — o mesmo do game-data oficial — passa.
  assert.equal(estado.generation_period, '0D00H05M00S', 'duracao em texto, nunca inteiro')
  assert.equal(typeof estado.generation_period, 'string')
  for (const [chave, valor] of Object.entries(estado)) {
    if (typeof valor === 'number') {
      assert.ok(Number.isFinite(valor), `${chave} finito, nunca NaN`)
    }
    assert.notEqual(valor, null, `${chave} nunca null no wire`)
  }
  const serializado = JSON.stringify(estado)
  assert.ok(!serializado.includes(':null'), `nenhum null no wire: ${serializado}`)
}

{
  // Sem generation_period utilizavel, o estado degrada para 0 — mas nunca null.
  const repoVazio = new MemoryRepo()
  const estado = idleRewardState(repoVazio, 1, { gameData: { idle_reward: {} } }, 1000)
  assert.equal(estado.generation_period, '0D00H00M00S', 'sem periodo: duracao zero, ainda em texto')
  assert.equal(estado.next_claim, 0)
  assert.equal(estado.claimable_periods, 0)
  assert.ok(!JSON.stringify(estado).includes(':null'))
}


{
  // formatDuration e o inverso de durationSeconds para todo valor conhecido.
  assert.equal(formatDuration(300), '0D00H05M00S')
  assert.equal(formatDuration(0), '0D00H00M00S')
  assert.equal(formatDuration(3600), '0D01H00M00S')
  assert.equal(formatDuration(86400), '1D00H00M00S')
  assert.equal(formatDuration(90061), '1D01H01M01S')
  assert.equal(formatDuration(-5), '0D00H00M00S', 'negativo nao vaza para o wire')
  assert.equal(formatDuration(NaN), '0D00H00M00S', 'NaN nunca vira null nem texto invalido')
  for (const s of [0, 1, 59, 300, 3600, 86399, 86400, 90061]) {
    assert.equal(durationSeconds(formatDuration(s)), s, `round-trip de ${s}s`)
  }
}


// ---------------------------------------------------------------------------
// `next_claim` e DURACAO EM SEGUNDOS ate o proximo claim, nunca epoch absoluto.
//
// CONFIRMADO por bisseccao no rig em 2026-08-20 (request_log 541 x 555):
// IdleRewardsController.UpdateNextClaimEpoch monta `Timer(next_claim * 1000)`.
// Epoch absoluto -> 1.787.259.906.000 ms, acima de int.MaxValue (2147483647),
// e o cliente estoura com `ArgumentException: Invalid value ... 'interval'`,
// matando o timer de idle rewards. Duracao (246 s) -> 246.000 ms, boot limpo.
// ---------------------------------------------------------------------------
{
  const TETO_TIMER_MS = 2 ** 31 - 1

  assert.equal(proximoClaimEmSegundos(1000, 300, 0, 1000), 300, 'primeiro periodo inteiro')
  assert.equal(proximoClaimEmSegundos(1000, 300, 0, 1200), 100, 'desconta o tempo ja corrido')
  assert.equal(proximoClaimEmSegundos(1000, 300, 1, 1200), 400, 'periodo seguinte')
  assert.equal(proximoClaimEmSegundos(1000, 300, 0, 9999), 0, 'nunca negativo')
  assert.equal(proximoClaimEmSegundos(1000, 0, 0, 1000), 0, 'sem periodo, sem timer')

  const repoNC = new MemoryRepo()
  const runtimeNC = {
    gameData: {
      idle_reward: {
        generation_period: '0D00H05M00S',
        chapter_idle_generation: [{ chapter_progress: 0, idle_generation: [{ rid: 100, amount: 4 }] }]
      }
    }
  }
  const agora = 1787259306
  repoNC.setState(1, 'idle-rewards', 'last_claim', agora)
  const estadoNC = idleRewardState(repoNC, 1, runtimeNC, agora + 54)

  assert.equal(estadoNC.next_claim, 246, 'segundos restantes, o valor que o rig provou')
  assert.ok(estadoNC.next_claim * 1000 <= TETO_TIMER_MS,
    `next_claim*1000 (${estadoNC.next_claim * 1000}) tem que caber no System.Timers.Timer`)
  assert.ok(estadoNC.next_claim < 86400 * 365,
    'duracao plausivel: epoch absoluto seria da ordem de 1.7e9')
  assert.equal(estadoNC.last_claim, agora, 'last_claim continua epoch absoluto')

  // O caso que quebrava: muito tempo parado nao pode virar intervalo gigante.
  const parado = idleRewardState(repoNC, 1, runtimeNC, agora + 86400 * 30)
  assert.ok(parado.next_claim * 1000 <= TETO_TIMER_MS,
    'mesmo apos 30 dias parado o intervalo continua valido')
}

console.log('Mighty DOOM Revival rewards test: PASS')
