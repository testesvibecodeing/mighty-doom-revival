import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const html = readFileSync(resolve(root, 'public/slayer.html'), 'utf8')
const js = readFileSync(resolve(root, 'public/assets/js/slayer.js'), 'utf8')

// Regression for the empty Admin screen: secondary panels start hidden in the
// HTML, so navigation must synchronize the native hidden attribute as well as
// the CSS class.
for (const section of ['overview', 'users', 'packs', 'events', 'notices', 'site', 'smtp']) {
  assert.match(html, new RegExp(`id="admin-${section}"`))
}
assert.match(js, /sub\.hidden\s*=\s*!active/)
assert.match(js, /panel\.hidden\s*=\s*!active/)
assert.match(js, /loadAdminSection\('overview'\)/)
assert.match(js, /\/account\/admin\/users/)
assert.match(js, /\/account\/admin\/packs/)
assert.match(js, /\/account\/admin\/events/)
assert.match(js, /\/account\/admin\/notifications/)
assert.match(js, /\/account\/admin\/site/)
assert.match(js, /\/account\/admin\/smtp/)
assert.match(js, /\/account\/admin\/users\/\$\{userId\}\/profile/)
assert.match(js, /data-profile-grant/)
assert.match(js, /data-profile-refresh/)
assert.match(js, /function packVisual/)
assert.match(js, /packVisual\(coverEntries\)/)
assert.match(js, /packVisual\(pack\.preview\?\.contents/)

console.log('Mighty DOOM Revival admin UI test: PASS')
