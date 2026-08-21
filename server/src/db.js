import { createHash, randomBytes, randomUUID, scryptSync, timingSafeEqual } from 'node:crypto'
import { mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { DatabaseSync } from 'node:sqlite'

function legacyPasswordHash (password) {
  return createHash('sha256').update(password, 'utf8').digest('hex')
}

function passwordHash (password) {
  const salt = randomBytes(16).toString('hex')
  const digest = scryptSync(password, salt, 32).toString('hex')
  return `scrypt$${salt}$${digest}`
}

function verifyPassword (stored, password) {
  if (typeof stored !== 'string' || typeof password !== 'string') return false
  if (stored?.startsWith('scrypt$')) {
    const [, salt, digest] = stored.split('$')
    if (!salt || !digest) return false
    const expected = Buffer.from(digest, 'hex')
    if (expected.length !== 32) return false
    const actual = scryptSync(password, salt, expected.length)
    return expected.length === actual.length && timingSafeEqual(expected, actual)
  }
  const expected = Buffer.from(stored, 'utf8')
  const actual = Buffer.from(legacyPasswordHash(password), 'utf8')
  return expected.length === actual.length && timingSafeEqual(expected, actual)
}

function tokenHash (token) {
  return createHash('sha256').update(token, 'utf8').digest('hex')
}

export class Repository {
  constructor (filename) {
    const path = resolve(filename)
    mkdirSync(dirname(path), { recursive: true })
    this.db = new DatabaseSync(path)
    this.db.exec('PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;')
    this.migrate()
  }

  migrate () {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uuid TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        email TEXT,
        display_name TEXT,
        recovery_hash TEXT,
        token TEXT NOT NULL UNIQUE,
        is_admin INTEGER NOT NULL DEFAULT 0,
        level INTEGER NOT NULL DEFAULT 1,
        chapter_progression INTEGER NOT NULL DEFAULT 0,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL
      );

      CREATE TABLE IF NOT EXISTS currencies (
        user_id INTEGER NOT NULL,
        rid INTEGER NOT NULL,
        amount INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, rid),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
      );

      CREATE TABLE IF NOT EXISTS energies (
        user_id INTEGER NOT NULL,
        rid INTEGER NOT NULL,
        amount INTEGER NOT NULL DEFAULT 0,
        regen_epoch INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, rid),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
      );

      CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        rid INTEGER NOT NULL,
        kind TEXT NOT NULL DEFAULT 'item',
        level INTEGER NOT NULL DEFAULT 1,
        tier INTEGER,
        amount INTEGER NOT NULL DEFAULT 1,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
      );

      CREATE TABLE IF NOT EXISTS cosmetics (
        user_id INTEGER NOT NULL,
        rid INTEGER NOT NULL,
        PRIMARY KEY (user_id, rid),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
      );

      CREATE TABLE IF NOT EXISTS entitlements (
        user_id INTEGER NOT NULL,
        rid INTEGER NOT NULL,
        PRIMARY KEY (user_id, rid),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
      );

      CREATE TABLE IF NOT EXISTS inventory_slots (
        user_id INTEGER NOT NULL,
        slot_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        PRIMARY KEY (user_id, slot_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
      );

      CREATE TABLE IF NOT EXISTS settings (
        user_id INTEGER PRIMARY KEY,
        blood_built_in INTEGER NOT NULL DEFAULT 0,
        blood_cosmetic INTEGER,
        confirm_gem_spend INTEGER NOT NULL DEFAULT 1,
        skin_randomization INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
      );

      CREATE TABLE IF NOT EXISTS pack_purchases (
        user_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        bucket TEXT NOT NULL,
        count INTEGER NOT NULL DEFAULT 0,
        last_at INTEGER NOT NULL,
        PRIMARY KEY (user_id, item_id, bucket),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
      );

      CREATE TABLE IF NOT EXISTS user_state (
        user_id INTEGER NOT NULL,
        namespace TEXT NOT NULL,
        state_key TEXT NOT NULL,
        value_json TEXT NOT NULL,
        PRIMARY KEY (user_id, namespace, state_key),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
      );

      CREATE TABLE IF NOT EXISTS request_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        path TEXT NOT NULL,
        body_json TEXT,
        method TEXT,
        status INTEGER,
        code INTEGER,
        response_json TEXT,
        note TEXT,
        created_at INTEGER NOT NULL
      );

      CREATE TABLE IF NOT EXISTS web_sessions (
        token_hash TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
      );

      CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        body TEXT NOT NULL DEFAULT '',
        kind TEXT NOT NULL DEFAULT 'info',
        created_by INTEGER,
        created_at INTEGER NOT NULL,
        FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
      );
      CREATE TABLE IF NOT EXISTS login_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        code_hash TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        used_at INTEGER,
        expires_at INTEGER NOT NULL,
        created_at INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        password_hash TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        used_at INTEGER,
        expires_at INTEGER NOT NULL,
        created_at INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
      );
    `)
    const columns = new Set(this.db.prepare('PRAGMA table_info(users)').all().map(row => row.name))
    if (!columns.has('email')) this.db.exec('ALTER TABLE users ADD COLUMN email TEXT')
    if (!columns.has('display_name')) this.db.exec('ALTER TABLE users ADD COLUMN display_name TEXT')
    if (!columns.has('recovery_hash')) this.db.exec('ALTER TABLE users ADD COLUMN recovery_hash TEXT')
    if (!columns.has('is_admin')) this.db.exec('ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0')
    // Contas criadas via código por e-mail nascem sem senha (password_set=0)
    // até o primeiro acesso definir uma; contas existentes já tinham senha.
    if (!columns.has('password_set')) this.db.exec('ALTER TABLE users ADD COLUMN password_set INTEGER NOT NULL DEFAULT 1')
    this.db.exec('CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique ON users(lower(email)) WHERE email IS NOT NULL AND email <> \'\'')
    // request_log ganhou pairing request/response (2026-08-19): bancos antigos
    // preservam as linhas existentes e recebem as colunas novas como NULL.
    const logColumns = new Set(this.db.prepare('PRAGMA table_info(request_log)').all().map(row => row.name))
    if (!logColumns.has('method')) this.db.exec('ALTER TABLE request_log ADD COLUMN method TEXT')
    if (!logColumns.has('status')) this.db.exec('ALTER TABLE request_log ADD COLUMN status INTEGER')
    if (!logColumns.has('code')) this.db.exec('ALTER TABLE request_log ADD COLUMN code INTEGER')
    if (!logColumns.has('response_json')) this.db.exec('ALTER TABLE request_log ADD COLUMN response_json TEXT')
    if (!logColumns.has('note')) this.db.exec('ALTER TABLE request_log ADD COLUMN note TEXT')
  }

  tx (fn) {
    this.db.exec('BEGIN IMMEDIATE')
    try {
      const result = fn()
      this.db.exec('COMMIT')
      return result
    } catch (error) {
      try { this.db.exec('ROLLBACK') } catch {}
      throw error
    }
  }

  close () {
    this.db.close()
  }

  createUser (options = {}) {
    const password = options.password || randomBytes(24).toString('base64url')
    const recoveryCode = options.recoveryCode || `RV-${randomBytes(6).toString('hex').toUpperCase()}`
    const token = randomBytes(32).toString('base64url')
    const uuid = randomUUID()
    const createdAt = Math.floor(Date.now() / 1000)
    const info = this.db.prepare(`
      INSERT INTO users (uuid, password_hash, email, display_name, recovery_hash, token, is_admin, password_set, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(uuid, passwordHash(password), options.email || null, options.displayName || null, passwordHash(recoveryCode), token, options.isAdmin ? 1 : 0, options.passwordSet === false ? 0 : 1, createdAt)
    const user = this.userById(Number(info.lastInsertRowid))
    return { user, password, recoveryCode }
  }

  userById (id) {
    return this.db.prepare('SELECT * FROM users WHERE id = ?').get(id) || null
  }

  userByToken (token) {
    return this.db.prepare('SELECT * FROM users WHERE token = ?').get(token) || null
  }

  userByLogin (login) {
    const value = String(login || '').trim()
    if (!value) return null
    return this.db.prepare(`
      SELECT * FROM users
      WHERE CAST(id AS TEXT) = ? OR lower(email) = lower(?)
      LIMIT 1
    `).get(value, value) || null
  }

  userByEmail (email) {
    const value = String(email || '').trim().toLowerCase()
    if (!value) return null
    return this.db.prepare('SELECT * FROM users WHERE lower(email) = ? LIMIT 1').get(value) || null
  }

  countUsers () {
    return this.db.prepare('SELECT COUNT(*) AS total FROM users').get().total
  }

  incrementAttemptCount (userId) {
    this.db.prepare('UPDATE users SET attempt_count = attempt_count + 1 WHERE id = ?').run(userId)
    return this.userById(userId)?.attempt_count ?? 0
  }

  setChapterProgression (userId, value) {
    const next = Math.max(0, Math.floor(Number(value) || 0))
    this.db.prepare(`
      UPDATE users
      SET chapter_progression = CASE WHEN chapter_progression > ? THEN chapter_progression ELSE ? END
      WHERE id = ?
    `).run(next, next, userId)
    return this.userById(userId)?.chapter_progression ?? 0
  }

  login (id, password) {
    const user = this.userById(id)
    if (!user || !verifyPassword(user.password_hash, password)) return null
    if (!user.password_hash.startsWith('scrypt$')) {
      this.db.prepare('UPDATE users SET password_hash = ? WHERE id = ?').run(passwordHash(password), id)
    }
    return user
  }

  loginAccount (login, password) {
    return this.loginAccountDetailed(login, password)?.user || null
  }

  loginAccountDetailed (email, password) {
    const user = this.userByEmail(email)
    if (!user || typeof password !== 'string') return null
    if (verifyPassword(user.password_hash, password)) {
      if (!user.password_hash.startsWith('scrypt$')) {
        this.db.prepare('UPDATE users SET password_hash = ? WHERE id = ?').run(passwordHash(password), user.id)
      }
      return { user: this.userById(user.id), temporaryPasswordUsed: false }
    }

    const now = Math.floor(Date.now() / 1000)
    const reset = this.db.prepare(`
      SELECT * FROM password_resets
      WHERE user_id = ? AND used_at IS NULL AND expires_at > ?
      ORDER BY id DESC LIMIT 1
    `).get(user.id, now)
    if (!reset || reset.attempts >= 5) return null
    const valid = verifyPassword(reset.password_hash, password)
    this.db.prepare('UPDATE password_resets SET attempts = attempts + 1 WHERE id = ?').run(reset.id)
    if (!valid) return null

    this.tx(() => {
      // A senha temporária só substitui a anterior quando é usada com sucesso.
      // Até esse momento, pedir recuperação não expulsa o dono da conta.
      this.db.prepare('UPDATE users SET password_hash = ?, password_set = 1 WHERE id = ?').run(reset.password_hash, user.id)
      this.db.prepare('UPDATE password_resets SET used_at = ? WHERE user_id = ? AND used_at IS NULL').run(now, user.id)
      this.db.prepare('DELETE FROM web_sessions WHERE user_id = ?').run(user.id)
    })
    return { user: this.userById(user.id), temporaryPasswordUsed: true }
  }

  updateProfile (userId, { email, displayName }) {
    this.db.prepare('UPDATE users SET email = ?, display_name = ? WHERE id = ?').run(email || null, displayName || null, userId)
    return this.userById(userId)
  }

  updatePassword (userId, password) {
    this.tx(() => {
      this.db.prepare('UPDATE users SET password_hash = ?, password_set = 1 WHERE id = ?').run(passwordHash(password), userId)
      this.db.prepare('UPDATE password_resets SET used_at = ? WHERE user_id = ? AND used_at IS NULL').run(Math.floor(Date.now() / 1000), userId)
    })
  }

  createTemporaryPassword (userId, ttlSeconds = 30 * 60) {
    const now = Math.floor(Date.now() / 1000)
    this.db.prepare('DELETE FROM password_resets WHERE expires_at < ?').run(now - 86400)
    const latest = this.db.prepare('SELECT created_at FROM password_resets WHERE user_id = ? ORDER BY id DESC LIMIT 1').get(userId)
    if (latest && now - latest.created_at < 60) return null
    const password = `RV-${randomBytes(9).toString('base64url')}`
    const result = this.tx(() => {
      this.db.prepare('UPDATE password_resets SET used_at = ? WHERE user_id = ? AND used_at IS NULL').run(now, userId)
      return this.db.prepare(`
        INSERT INTO password_resets (user_id, password_hash, expires_at, created_at)
        VALUES (?, ?, ?, ?)
      `).run(userId, passwordHash(password), now + ttlSeconds, now)
    })
    return { id: Number(result.lastInsertRowid), password, expiresAt: now + ttlSeconds }
  }

  revokeTemporaryPassword (resetId) {
    this.db.prepare('UPDATE password_resets SET used_at = ? WHERE id = ? AND used_at IS NULL').run(Math.floor(Date.now() / 1000), resetId)
  }


  // Códigos de acesso por e-mail: 6 dígitos, hash scrypt, TTL curto,
  // mínimo de 60s entre envios para o mesmo destinatário.
  createLoginCode (email, ttlSeconds = 600) {
    const now = Math.floor(Date.now() / 1000)
    const normalized = String(email || '').toLowerCase()
    this.db.prepare('DELETE FROM login_codes WHERE expires_at < ?').run(now - 3600)
    const latest = this.db.prepare('SELECT created_at FROM login_codes WHERE lower(email) = ? ORDER BY id DESC LIMIT 1').get(normalized)
    if (latest && now - latest.created_at < 60) return null
    const code = String(100000 + Math.floor(Math.random() * 900000))
    this.db.prepare('INSERT INTO login_codes (email, code_hash, expires_at, created_at) VALUES (?, ?, ?, ?)').run(normalized, passwordHash(code), now + ttlSeconds, now)
    return code
  }

  consumeLoginCode (email, code) {
    const now = Math.floor(Date.now() / 1000)
    const row = this.db.prepare(`
      SELECT * FROM login_codes
      WHERE lower(email) = ? AND used_at IS NULL AND expires_at > ?
      ORDER BY id DESC LIMIT 1
    `).get(String(email || '').toLowerCase(), now)
    if (!row || row.attempts >= 5) return false
    const valid = verifyPassword(row.code_hash, String(code || ''))
    this.db.prepare('UPDATE login_codes SET attempts = attempts + 1, used_at = ? WHERE id = ?').run(valid ? now : null, row.id)
    return valid
  }

  // Contas do jogo (login-device) ainda sem identidade de site: podem ser
  // "adotadas" por quem provar posse de uma conta de e-mail.
  listClaimableAccounts (limit = 50) {
    return this.db.prepare(`
      SELECT id, display_name, level, chapter_progression, attempt_count, created_at
      FROM users
      WHERE (email IS NULL OR email = '') AND is_admin = 0
      ORDER BY created_at DESC
      LIMIT ?
    `).all(Math.max(1, Math.min(100, Math.floor(Number(limit)) || 50)))
  }

  // Adoção: move a identidade (e-mail/senha/recovery) da conta do site para a
  // conta do jogo com progresso real, apaga a conta do site e devolve a linha
  // adotada. Uma transação: ou vira uma conta só, ou nada muda.
  claimGameAccount (siteUserId, gameUserId) {
    return this.tx(() => {
      const site = this.userById(siteUserId)
      const game = this.userById(gameUserId)
      if (!site || !game) return { error: 'not-found' }
      if (site.id === game.id) return { error: 'same-account' }
      if (!site.email) return { error: 'site-account-has-no-email' }
      if (game.email) return { error: 'already-claimed' }
      // A conta do site perde starter bundle/painel ao ser adotada — só faz
      // sentido quando ela não tem progresso de jogo próprio.
      if ((site.attempt_count || 0) > 0 || (site.level || 1) > 1) return { error: 'site-account-has-progress' }
      this.db.prepare('DELETE FROM users WHERE id = ?').run(site.id)
      this.db.prepare(`
        UPDATE users SET
          email = ?,
          password_hash = ?,
          recovery_hash = ?,
          password_set = ?,
          display_name = COALESCE(NULLIF(display_name, ''), ?),
          is_admin = CASE WHEN ? = 1 THEN 1 ELSE is_admin END
        WHERE id = ?
      `).run(site.email, site.password_hash, site.recovery_hash, site.password_set === 0 ? 0 : 1, site.display_name || '', site.is_admin ? 1 : 0, game.id)
      return { account: this.userById(game.id) }
    })
  }

  createWebSession (userId, ttlSeconds = 30 * 24 * 3600) {
    const token = randomBytes(32).toString('base64url')
    const expiresAt = Math.floor(Date.now() / 1000) + ttlSeconds
    this.db.prepare('INSERT INTO web_sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)').run(tokenHash(token), userId, expiresAt)
    return { token, expiresAt }
  }

  userByWebSession (token) {
    if (!token) return null
    const row = this.db.prepare(`
      SELECT u.* FROM web_sessions s JOIN users u ON u.id = s.user_id
      WHERE s.token_hash = ? AND s.expires_at > ?
    `).get(tokenHash(token), Math.floor(Date.now() / 1000))
    return row || null
  }

  revokeWebSession (token) {
    if (token) this.db.prepare('DELETE FROM web_sessions WHERE token_hash = ?').run(tokenHash(token))
  }

  revokeUserSessions (userId) {
    this.db.prepare('DELETE FROM web_sessions WHERE user_id = ?').run(userId)
  }

  listUsers (query = '', limit = 100) {
    const term = String(query || '').trim().toLowerCase()
    const filter = `%${term}%`
    return this.db.prepare(`
      SELECT id, uuid, email, display_name, is_admin, level, chapter_progression, attempt_count, created_at
      FROM users
      WHERE ? = '' OR lower(CAST(id AS TEXT)) LIKE ? OR lower(email) LIKE ? OR lower(display_name) LIKE ?
      ORDER BY id
      LIMIT ?
    `).all(term, filter, filter, filter, Math.max(1, Math.min(500, Number(limit) || 100)))
  }

  deleteUser (userId) {
    const info = this.db.prepare('DELETE FROM users WHERE id = ? AND is_admin = 0').run(userId)
    return info.changes > 0
  }

  setAdminFlag (userId, flag) {
    this.db.prepare('UPDATE users SET is_admin = ? WHERE id = ?').run(flag ? 1 : 0, userId)
  }

  createNotification ({ title, body = '', kind = 'info', createdBy = null }) {
    const info = this.db.prepare(`
      INSERT INTO notifications (title, body, kind, created_by, created_at)
      VALUES (?, ?, ?, ?, ?)
    `).run(String(title).slice(0, 120), String(body).slice(0, 2000), kind, createdBy, Math.floor(Date.now() / 1000))
    return this.notificationById(Number(info.lastInsertRowid))
  }

  notificationById (id) {
    return this.db.prepare('SELECT * FROM notifications WHERE id = ?').get(id) || null
  }

  listNotifications (limit = 30) {
    return this.db.prepare('SELECT * FROM notifications ORDER BY id DESC LIMIT ?')
      .all(Math.max(1, Math.min(100, Number(limit) || 30)))
  }

  deleteNotification (id) {
    const info = this.db.prepare('DELETE FROM notifications WHERE id = ?').run(id)
    return info.changes > 0
  }

  currencies (userId) {
    return this.db.prepare('SELECT rid, amount FROM currencies WHERE user_id = ? ORDER BY rid').all(userId)
  }

  balance (userId, rid) {
    return this.db.prepare('SELECT amount FROM currencies WHERE user_id = ? AND rid = ?').get(userId, rid)?.amount || 0
  }

  addCurrency (userId, rid, delta) {
    const current = this.balance(userId, rid)
    const next = current + delta
    if (next < 0) throw new Error(`Saldo insuficiente rid=${rid}`)
    this.db.prepare(`
      INSERT INTO currencies (user_id, rid, amount) VALUES (?, ?, ?)
      ON CONFLICT(user_id, rid) DO UPDATE SET amount = excluded.amount
    `).run(userId, rid, next)
    return next
  }

  energies (userId) {
    return this.db.prepare('SELECT rid, amount, regen_epoch FROM energies WHERE user_id = ? ORDER BY rid').all(userId)
  }

  energy (userId, rid) {
    return this.db.prepare('SELECT rid, amount, regen_epoch FROM energies WHERE user_id = ? AND rid = ?').get(userId, rid) || null
  }

  setEnergy (userId, rid, amount, regenEpoch = 0) {
    if (!Number.isFinite(amount) || amount < 0) throw new Error(`Energia inválida rid=${rid}`)
    this.db.prepare(`
      INSERT INTO energies (user_id, rid, amount, regen_epoch) VALUES (?, ?, ?, ?)
      ON CONFLICT(user_id, rid) DO UPDATE SET
        amount = excluded.amount,
        regen_epoch = excluded.regen_epoch
    `).run(userId, rid, Math.floor(amount), Math.max(0, Math.floor(regenEpoch || 0)))
  }

  addItem (userId, resource) {
    const info = this.db.prepare(`
      INSERT INTO items (user_id, rid, kind, level, tier, amount, metadata_json)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).run(
      userId,
      resource.rid,
      resource.kind || 'item',
      resource.level ?? 1,
      resource.tier ?? null,
      resource.amount ?? 1,
      JSON.stringify(resource.metadata || {})
    )
    return Number(info.lastInsertRowid)
  }

  updateItemMetadata (userId, itemId, metadata) {
    const result = this.db.prepare('UPDATE items SET metadata_json = ? WHERE user_id = ? AND id = ?')
      .run(JSON.stringify(metadata || {}), userId, itemId)
    return result.changes === 1
  }

  // Remove o item e limpa slots que o referenciam (mesma transação do chamador),
  // senão o wire de inventário expõe slot apontando para item inexistente.
  deleteItem (userId, itemId) {
    this.db.prepare('DELETE FROM inventory_slots WHERE user_id = ? AND item_id = ?').run(userId, itemId)
    const result = this.db.prepare('DELETE FROM items WHERE user_id = ? AND id = ?').run(userId, itemId)
    return result.changes === 1
  }

  items (userId) {
    return this.db.prepare('SELECT * FROM items WHERE user_id = ? ORDER BY id').all(userId)
  }

  itemById (userId, itemId) {
    return this.db.prepare('SELECT * FROM items WHERE user_id = ? AND id = ?').get(userId, itemId) || null
  }

  cosmetics (userId) {
    return this.db.prepare('SELECT rid FROM cosmetics WHERE user_id = ? ORDER BY rid').all(userId)
  }

  addCosmetic (userId, rid) {
    this.db.prepare('INSERT OR IGNORE INTO cosmetics (user_id, rid) VALUES (?, ?)').run(userId, rid)
  }

  entitlements (userId) {
    return this.db.prepare('SELECT rid FROM entitlements WHERE user_id = ? ORDER BY rid').all(userId)
  }

  addEntitlement (userId, rid) {
    this.db.prepare('INSERT OR IGNORE INTO entitlements (user_id, rid) VALUES (?, ?)').run(userId, rid)
  }

  slots (userId) {
    return this.db.prepare('SELECT slot_id, item_id FROM inventory_slots WHERE user_id = ? ORDER BY slot_id').all(userId)
  }

  setSlot (userId, slotId, itemId) {
    const item = this.itemById(userId, itemId)
    if (!item) return false
    this.db.prepare(`
      INSERT INTO inventory_slots (user_id, slot_id, item_id)
      VALUES (?, ?, ?)
      ON CONFLICT(user_id, slot_id) DO UPDATE SET item_id = excluded.item_id
    `).run(userId, slotId, itemId)
    return true
  }

  settings (userId) {
    return this.db.prepare('SELECT * FROM settings WHERE user_id = ?').get(userId) || null
  }

  saveSettings (userId, value) {
    this.db.prepare(`
      INSERT INTO settings (user_id, blood_built_in, blood_cosmetic, confirm_gem_spend, skin_randomization)
      VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(user_id) DO UPDATE SET
        blood_built_in = excluded.blood_built_in,
        blood_cosmetic = excluded.blood_cosmetic,
        confirm_gem_spend = excluded.confirm_gem_spend,
        skin_randomization = excluded.skin_randomization
    `).run(
      userId,
      value.blood_built_in ?? 0,
      value.blood_cosmetic ?? null,
      value.confirm_gem_spend === false ? 0 : 1,
      value.skin_randomization ?? 0
    )
  }

  purchaseCount (userId, itemId, bucket) {
    return this.db.prepare(`
      SELECT count FROM pack_purchases WHERE user_id = ? AND item_id = ? AND bucket = ?
    `).get(userId, itemId, bucket)?.count || 0
  }

  incrementPurchase (userId, itemId, bucket) {
    const now = Math.floor(Date.now() / 1000)
    this.db.prepare(`
      INSERT INTO pack_purchases (user_id, item_id, bucket, count, last_at)
      VALUES (?, ?, ?, 1, ?)
      ON CONFLICT(user_id, item_id, bucket) DO UPDATE SET
        count = count + 1,
        last_at = excluded.last_at
    `).run(userId, itemId, bucket, now)
  }

  getState (userId, namespace, key, fallback = null) {
    const row = this.db.prepare(`
      SELECT value_json FROM user_state WHERE user_id = ? AND namespace = ? AND state_key = ?
    `).get(userId, namespace, key)
    return row ? JSON.parse(row.value_json) : fallback
  }

  setState (userId, namespace, key, value) {
    this.db.prepare(`
      INSERT INTO user_state (user_id, namespace, state_key, value_json)
      VALUES (?, ?, ?, ?)
      ON CONFLICT(user_id, namespace, state_key) DO UPDATE SET value_json = excluded.value_json
    `).run(userId, namespace, key, JSON.stringify(value))
  }

  // meta (opcional, retrocompatível): { method, status, code, response, note }.
  // O pairing request/response vive na MESMA linha — é o que permite ao
  // harness provar que o response capturado é da chamada real observada.
  logRequest (userId, path, body, meta = {}) {
    const info = this.db.prepare(`
      INSERT INTO request_log (user_id, path, body_json, method, status, code, response_json, note, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      userId || null,
      path,
      body === undefined || body === null ? null : JSON.stringify(body),
      meta.method || null,
      Number.isInteger(meta.status) ? meta.status : null,
      Number.isInteger(meta.code) ? meta.code : null,
      meta.response === undefined || meta.response === null ? null : JSON.stringify(meta.response),
      meta.note || null,
      Math.floor(Date.now() / 1000)
    )
    const id = Number(info.lastInsertRowid)
    if (id % 50 === 0) this.trimRequestLog()
    return id
  }

  // O log é evidência de captura recente, não histórico infinito: mantém só
  // as `keep` linhas mais novas (o cursor incremental não depende do resto).
  trimRequestLog (keep = 20000) {
    this.db.prepare('DELETE FROM request_log WHERE id <= (SELECT COALESCE(MAX(id), 0) FROM request_log) - ?').run(keep)
  }

  requestLog (limit = 100) {
    return this.db.prepare('SELECT * FROM request_log ORDER BY id DESC LIMIT ?').all(Math.max(1, Math.min(1000, Number(limit) || 100)))
  }

  // Captura incremental determinística: só linhas com id > sinceId, em ordem
  // crescente de chegada. É a sequência temporal real da execução.
  requestsSince (sinceId, limit = 500) {
    return this.db.prepare('SELECT * FROM request_log WHERE id > ? ORDER BY id ASC LIMIT ?')
      .all(Math.max(0, Math.floor(Number(sinceId) || 0)), Math.max(1, Math.min(1000, Math.floor(Number(limit)) || 500)))
  }

  // Cursor para o baseline do harness: maior id já escrito (0 se vazio).
  requestLogCursor () {
    return this.db.prepare('SELECT COALESCE(MAX(id), 0) AS last_id FROM request_log').get().last_id
  }
}
