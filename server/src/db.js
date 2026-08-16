import { createHash, randomBytes, randomUUID } from 'node:crypto'
import { mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import Database from 'better-sqlite3'

function passwordHash (password) {
  return createHash('sha256').update(password, 'utf8').digest('hex')
}

export class Repository {
  constructor (filename) {
    const path = resolve(filename)
    mkdirSync(dirname(path), { recursive: true })
    this.db = new Database(path)
    this.db.pragma('journal_mode = WAL')
    this.db.pragma('foreign_keys = ON')
    this.migrate()
  }

  migrate () {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uuid TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        token TEXT NOT NULL UNIQUE,
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
        created_at INTEGER NOT NULL
      );
    `)
  }

  tx (fn) {
    return this.db.transaction(fn)()
  }

  createUser () {
    const password = randomBytes(24).toString('base64url')
    const token = randomBytes(32).toString('base64url')
    const uuid = randomUUID()
    const createdAt = Math.floor(Date.now() / 1000)
    const info = this.db.prepare(`
      INSERT INTO users (uuid, password_hash, token, created_at)
      VALUES (?, ?, ?, ?)
    `).run(uuid, passwordHash(password), token, createdAt)
    const user = this.userById(Number(info.lastInsertRowid))
    return { user, password }
  }

  userById (id) {
    return this.db.prepare('SELECT * FROM users WHERE id = ?').get(id) || null
  }

  userByToken (token) {
    return this.db.prepare('SELECT * FROM users WHERE token = ?').get(token) || null
  }

  login (id, password) {
    const user = this.userById(id)
    if (!user || user.password_hash !== passwordHash(password)) return null
    return user
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

  items (userId) {
    return this.db.prepare('SELECT * FROM items WHERE user_id = ? ORDER BY id').all(userId)
  }

  slots (userId) {
    return this.db.prepare('SELECT slot_id, item_id FROM inventory_slots WHERE user_id = ? ORDER BY slot_id').all(userId)
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

  logRequest (userId, path, body) {
    this.db.prepare(`
      INSERT INTO request_log (user_id, path, body_json, created_at) VALUES (?, ?, ?, ?)
    `).run(userId || null, path, body === undefined ? null : JSON.stringify(body), Math.floor(Date.now() / 1000))
  }
}
