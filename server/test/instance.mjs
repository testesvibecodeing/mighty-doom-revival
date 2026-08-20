import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'

import { CONTRACT_CAPABILITIES, CONTRACT_REVISION, bootId, instanceIdentity, productionReadiness, sanitizeIdentityValue } from '../src/instance.js'

// A identidade da instância existe para provar ONDE o tráfego aterrissou.
// Regras: nada secreto entra, a precedência é determinística e o campo diz de
// onde o valor veio (senão "unknown" e "provado" ficam indistinguíveis).

// --- sanitização: publicável ou nada ---------------------------------------
{
  assert.equal(sanitizeIdentityValue('fea3c18abcd0'), 'fea3c18abcd0')
  assert.equal(sanitizeIdentityValue('  vps-revival  '), 'vps-revival', 'trim aplicado')
  assert.equal(sanitizeIdentityValue('prod/main+1'), 'prod/main+1')
  assert.equal(sanitizeIdentityValue(''), null)
  assert.equal(sanitizeIdentityValue('   '), null)
  assert.equal(sanitizeIdentityValue(undefined), null)
  assert.equal(sanitizeIdentityValue(42), null, 'não-string é ausente, não coagido')
  assert.equal(sanitizeIdentityValue('x'.repeat(65)), null, 'valor longo demais é recusado')
  assert.equal(sanitizeIdentityValue('token com espaço'), null, 'espaço fora do conjunto seguro')
  assert.equal(sanitizeIdentityValue('segredo"aspas'), null)
  assert.equal(sanitizeIdentityValue('linha\nquebrada'), null)
}

// --- precedência: env > BUILD_ID > git > unknown ----------------------------
{
  const vazio = mkdtempSync(resolve(tmpdir(), 'revival-instance-'))
  try {
    const porEnv = instanceIdentity(
      { REVIVAL_BUILD_ID: 'deadbeef1234', REVIVAL_INSTANCE_ID: 'vps-revival', REVIVAL_ENVIRONMENT: 'production' },
      vazio
    )
    assert.equal(porEnv.build_id, 'deadbeef1234')
    assert.equal(porEnv.build_id_source, 'env')
    assert.equal(porEnv.instance_id, 'vps-revival')
    assert.equal(porEnv.environment, 'production')

    // BUILD_ID escrito pelo deploy quando o diretório remoto não é um repo git.
    writeFileSync(resolve(vazio, 'BUILD_ID'), 'abc123def456\nlixo depois da primeira linha\n')
    const porArquivo = instanceIdentity({}, vazio)
    assert.equal(porArquivo.build_id, 'abc123def456', 'só a primeira linha do BUILD_ID')
    assert.equal(porArquivo.build_id_source, 'build-file')

    // env vence o arquivo
    const envVence = instanceIdentity({ REVIVAL_BUILD_ID: 'deadbeef1234' }, vazio)
    assert.equal(envVence.build_id, 'deadbeef1234')
    assert.equal(envVence.build_id_source, 'env')
  } finally {
    rmSync(vazio, { recursive: true, force: true })
  }
}

// --- fallback local explícito ----------------------------------------------
{
  const semNada = mkdtempSync(resolve(tmpdir(), 'revival-instance-vazio-'))
  try {
    const id = instanceIdentity({}, semNada)
    assert.equal(id.instance_id, 'unnamed', 'ausência é declarada, não inventada')
    assert.equal(id.environment, 'local')
    // Sem env e sem BUILD_ID, sobra o git do diretório — que aqui não existe.
    assert.ok(['unknown', 'unavailable'].includes(id.build_id) || id.build_id_source === 'git',
      `build_id sem fonte tem que ser explícito, veio ${id.build_id_source}`)
  } finally {
    rmSync(semNada, { recursive: true, force: true })
  }
}

// --- git do checkout real ---------------------------------------------------
{
  const repo = resolve(process.cwd(), '..')
  const id = instanceIdentity({}, repo)
  if (id.build_id_source === 'git') {
    // `-dirty` faz parte do contrato: commit limpo nao pode representar
    // arquivos alterados (ver o bloco de build_id honesto abaixo).
    assert.match(id.build_id, /^[0-9a-f]{7,40}(-dirty)?$/, 'commit curto em hexadecimal')
  }
}

// --- segredo em env NÃO vaza para o health ---------------------------------
{
  const id = instanceIdentity({
    REVIVAL_BUILD_ID: 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJhIjoxfQ.assinatura-secreta-muito-longa',
    REVIVAL_INSTANCE_ID: 'valor com espaço e "aspas"'
  }, process.cwd())
  assert.notEqual(id.build_id, 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJhIjoxfQ.assinatura-secreta-muito-longa')
  assert.equal(id.instance_id, 'unnamed', 'valor fora do conjunto seguro é tratado como ausente')
  const serializado = JSON.stringify(id)
  assert.ok(!serializado.includes('eyJ'), 'nenhum fragmento de JWT no health')
  assert.ok(!serializado.includes('aspas'))
}

// --- boot_id separa reinício de troca de máquina ---------------------------
{
  const a = instanceIdentity({}, process.cwd())
  const b = instanceIdentity({}, process.cwd())
  assert.equal(a.boot_id, b.boot_id, 'estável dentro do MESMO processo')
  assert.equal(a.boot_id, bootId())
  assert.match(a.boot_id, /^[0-9a-f-]{36}$/)
}

// --- forma do objeto: só campos publicáveis --------------------------------
{
  const id = instanceIdentity({}, process.cwd())
  assert.deepEqual(
    Object.keys(id).sort(),
    ['boot_id', 'build_dirty', 'build_id', 'build_id_source', 'contract_capabilities',
      'contract_revision', 'environment', 'instance_id'],
    'nenhum campo extra pode entrar no health sem revisão'
  )
}


// --- build_id honesto: commit sujo NAO pode se passar por commit limpo -------
// Um `git rev-parse HEAD` puro mentiria quando ha alteracao nao commitada: o
// processo executa arquivos que nao sao os daquele commit.
{
  const idReal = instanceIdentity({}, process.cwd())
  if (idReal.build_id_source === 'git') {
    assert.match(idReal.build_id, /^[0-9a-f]{7,40}(-dirty)?$/, 'commit, opcionalmente sujo')
    assert.equal(idReal.build_dirty, idReal.build_id.endsWith('-dirty'),
      'build_dirty tem que refletir o sufixo')
  }
  // env de deploy sempre vence e nunca e marcada suja por conta propria
  const porEnv = instanceIdentity({ REVIVAL_BUILD_ID: 'deadbeef1234' }, process.cwd())
  assert.equal(porEnv.build_dirty, false)
  assert.equal(porEnv.build_id_source, 'env')
}

// --- revisao de contrato publicavel ----------------------------------------
{
  const id = instanceIdentity({}, process.cwd())
  assert.equal(typeof id.contract_revision, 'number')
  assert.equal(id.contract_revision, CONTRACT_REVISION)
  assert.ok(Array.isArray(id.contract_capabilities))
  assert.ok(id.contract_capabilities.includes('idle-rewards-duration-wire'),
    'a revisao 2 carrega o contrato de duracao do idle rewards')
  for (const cap of CONTRACT_CAPABILITIES) {
    assert.match(cap, /^[a-z0-9-]+$/, 'capability e publicavel, sem segredo')
  }
}

// --- gate de producao: os cinco casos exigidos ------------------------------
{
  const compativel = { instance_id: 'vps', build_id: 'abc123', contract_revision: CONTRACT_REVISION, research_mode: false }
  assert.equal(productionReadiness(compativel).ready, true, 'servidor compativel passa')

  const antigo = { ok: true, client_version: '1.13.1', api_version: '24.0.0' }
  const rAntigo = productionReadiness(antigo)
  assert.equal(rAntigo.ready, false, 'health antigo sem identidade reprova')
  assert.ok(rAntigo.reasons.join(' ').includes('identidade'))

  const velho = { ...compativel, contract_revision: CONTRACT_REVISION - 1 }
  const rVelho = productionReadiness(velho)
  assert.equal(rVelho.ready, false, 'revisao insuficiente reprova')
  assert.ok(rVelho.reasons.join(' ').includes('contract_revision'))

  const pesquisa = { ...compativel, research_mode: true }
  assert.equal(productionReadiness(pesquisa).ready, false, 'research_mode ligado reprova')

  const sujo = { ...compativel, build_dirty: true }
  const rSujo = productionReadiness(sujo)
  assert.equal(rSujo.ready, false, 'build sujo reprova')
  assert.ok(rSujo.reasons.join(' ').includes('sujo'))

  assert.equal(productionReadiness(null).ready, false, 'health indisponivel reprova')
  assert.equal(productionReadiness(undefined).reasons.length, 1)

  // O motivo e acionavel: diz O QUE fazer, nao so que falhou.
  for (const r of [rAntigo, rVelho, rSujo]) {
    assert.ok(r.reasons.every(m => m.length > 20), 'motivo curto demais nao ajuda ninguem')
  }
}

console.log('instance.mjs: OK')
