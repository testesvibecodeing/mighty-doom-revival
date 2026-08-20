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

function fromGit (root) {
  try {
    const out = execFileSync('git', ['rev-parse', '--short=12', 'HEAD'], {
      cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], timeout: 3000
    })
    return sanitizeIdentityValue(out)
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
    environment: sanitizeIdentityValue(env.REVIVAL_ENVIRONMENT) || 'local'
  }
}

export const bootId = () => BOOT_ID
