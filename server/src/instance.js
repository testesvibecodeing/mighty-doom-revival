// Identidade da INSTÂNCIA que respondeu — o dado que faltava para provar onde o
// tráfego do cliente aterrissou.
//
// Motivo (medido 2026-08-19, work/audit-opus/FASE-0-DIVERGENCIAS.md): local e
// VPS devolviam `client_version` e `api_version` IDÊNTICOS, então comparar só
// isso não distingue as duas instâncias. Sete execuções do harness declararam o
// mesmo `--server` — a comparação de host, sozinha, não prova aterrissagem.
//
// Contrato: isto vive SÓ em /revival/health. Nada aqui toca ou inventa rota
// `game/*` — o protocolo do cliente não muda.
//
// Nada aqui pode ser segredo. Só entra o que é publicável: um id de instância,
// o commit do build e um rótulo de ambiente. Se um dia alguém puser segredo
// nessas envs, `sanitizeIdentityValue()` corta pelo tamanho e pelo formato.
import { execFileSync } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

// Nascimento do processo: dois processos da MESMA build têm boot_id diferente.
// É o que separa "reiniciaram o servidor" de "é outra máquina".
const BOOT_ID = randomUUID()

/**
 * Revisão do CONTRATO DO WIRE que este servidor implementa.
 *
 * Sobe de 1 sempre que um contrato `/game/*` muda de forma que o cliente
 * enxerga. Existe para o preflight do pipeline recusar publicar um APK contra
 * um servidor velho demais para ele — antes, um build "verde" podia sair contra
 * uma instância que devolve payload que o cliente não consegue parsear.
 *
 * Histórico (cada item foi medido no cliente real, não suposto):
 *
 *   1 — envelope `uts`/`code`, JWT com `aud`/`audience` como ARRAY.
 *   2 — três contratos provados por bisseção em 2026-08-20:
 *       tutorial/complete-sequence idempotente; iap/get-purchase-history-info
 *       read-only com sucesso; idle-rewards `generation_period` como duração em
 *       texto (`0D00H05M00S`) e `next_claim` como DURAÇÃO EM SEGUNDOS — epoch
 *       absoluto estourava o `System.Timers.Timer` do cliente.
 */
export const CONTRACT_REVISION = 2

/** Contratos desta revisão, publicáveis. Serve de diagnóstico acionável. */
export const CONTRACT_CAPABILITIES = Object.freeze([
  'envelope-uts-code',
  'jwt-audience-array',
  'tutorial-complete-sequence-idempotent',
  'iap-purchase-history-readonly',
  'idle-rewards-duration-wire',
])

const MAX_LEN = 64
const SAFE_RE = /^[A-Za-z0-9._:@/+-]+$/

// Publicável ou nada. Valor longo demais ou com caractere fora do conjunto é
// tratado como ausente — melhor sem identidade do que vazando segredo no health.
export function sanitizeIdentityValue (value) {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed || trimmed.length > MAX_LEN || !SAFE_RE.test(trimmed)) return null
  return trimmed
}

/**
 * Commit do checkout — MARCADO como sujo quando há alteração não commitada.
 *
 * Um `git rev-parse HEAD` puro mentiria: o processo pode estar executando
 * arquivos que não são os daquele commit. Com `-dirty`, quem lê o health sabe
 * que o commit não identifica os bytes em execução, e o preflight de produção
 * recusa (ver `productionReadiness`).
 */
function fromGit (root) {
  try {
    const commit = execFileSync('git', ['rev-parse', '--short=12', 'HEAD'], {
      cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], timeout: 3000
    }).trim()
    if (!commit) return null
    // `--porcelain` vazio = árvore limpa. Só o que o Git rastreia conta:
    // arquivo ignorado (work/, output/) não torna o build sujo.
    let sujo = false
    try {
      const status = execFileSync('git', ['status', '--porcelain', '--untracked-files=no'], {
        cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], timeout: 5000
      })
      sujo = status.trim().length > 0
    } catch {
      // Sem conseguir medir a limpeza, assume sujo: errar para o lado seguro.
      sujo = true
    }
    return sanitizeIdentityValue(sujo ? `${commit}-dirty` : commit)
  } catch {
    return null
  }
}

function fromBuildFile (root) {
  // Arquivo escrito pelo deploy (ex.: `git rev-parse HEAD > server/BUILD_ID`).
  // Existe para o VPS, onde o diretório de deploy pode não ser um repositório.
  const file = resolve(root, 'BUILD_ID')
  if (!existsSync(file)) return null
  try {
    return sanitizeIdentityValue(readFileSync(file, 'utf8').split('\n')[0])
  } catch {
    return null
  }
}

/**
 * Identidade publicável desta instância.
 *
 * Precedência do build_id: env de deploy > arquivo BUILD_ID > git do checkout >
 * "unknown". O `source` diz de onde veio — sem ele, "unknown" e "provado pelo
 * git" seriam indistinguíveis para quem lê o health.
 */
export function instanceIdentity (env = process.env, root = process.cwd()) {
  const fromEnv = sanitizeIdentityValue(env.REVIVAL_BUILD_ID)
  const buildFile = fromEnv ? null : fromBuildFile(root)
  const git = fromEnv || buildFile ? null : fromGit(root)

  let buildId = 'unknown'
  let source = 'unavailable'
  if (fromEnv) { buildId = fromEnv; source = 'env' } else if (buildFile) { buildId = buildFile; source = 'build-file' } else if (git) { buildId = git; source = 'git' }

  return {
    // Estável entre reinícios da MESMA instalação; distingue local de VPS.
    instance_id: sanitizeIdentityValue(env.REVIVAL_INSTANCE_ID) || 'unnamed',
    // Muda a cada `npm start`: separa reinício de troca de máquina.
    boot_id: BOOT_ID,
    build_id: buildId,
    build_id_source: source,
    // `true` quando o commit publicado NÃO representa os arquivos em execução.
    build_dirty: buildId.endsWith('-dirty'),
    environment: sanitizeIdentityValue(env.REVIVAL_ENVIRONMENT) || 'local',
    contract_revision: CONTRACT_REVISION,
    contract_capabilities: CONTRACT_CAPABILITIES
  }
}

/**
 * O servidor pode receber um APK novo em produção?
 *
 * Recusa, com motivo acionável: identidade ausente (build anterior a este
 * módulo), revisão de contrato abaixo da exigida, `research_mode` ligado
 * (endpoint desconhecido responde sucesso vazio e mascara rota faltante) e
 * build sujo (o commit não identifica os bytes em execução).
 */
export function productionReadiness (health, { requiredRevision = CONTRACT_REVISION } = {}) {
  if (!health || typeof health !== 'object') {
    return { ready: false, reasons: ['health indisponível'], revision: null }
  }
  const problemas = []
  const revisao = health.contract_revision
  if (health.instance_id === undefined && health.build_id === undefined) {
    problemas.push('health sem identidade de instância/build (servidor anterior a instance.js)')
  }
  if (typeof revisao !== 'number') {
    problemas.push('health sem contract_revision')
  } else if (revisao < requiredRevision) {
    problemas.push(`contract_revision ${revisao} < ${requiredRevision} exigida — o servidor `
      + 'não tem as correções de wire que este APK espera')
  }
  if (health.research_mode === true) {
    problemas.push('research_mode ligado: rota desconhecida responde sucesso vazio')
  }
  if (health.build_dirty === true) {
    problemas.push('build_id sujo: o commit publicado não identifica os bytes em execução')
  }
  return { ready: problemas.length === 0, reasons: problemas, revision: revisao ?? null }
}

export const bootId = () => BOOT_ID
