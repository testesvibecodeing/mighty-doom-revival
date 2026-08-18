#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'server' / 'public' / 'assets' / 'js' / 'revival-items.js'
HTML = ROOT / 'server' / 'public' / 'slayer.html'

old = "const src = revivalAsset(resource) || (serverIcon && !serverIcon.startsWith('/assets/img/kinds/') ? serverIcon : artUrl(resource))"
new = "const src = serverIcon && !serverIcon.startsWith('/assets/img/kinds/') ? `${serverIcon}${serverIcon.includes('?') ? '&' : '?'}v=revival-unique-20260817` : (revivalAsset(resource) || artUrl(resource))"

text = JS.read_text(encoding='utf-8')
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit('revival-items.js: icon priority expression not found')
JS.write_text(text, encoding='utf-8')

html = HTML.read_text(encoding='utf-8')
old_script = '<script src="assets/js/revival-items.js"></script>'
new_script = '<script src="assets/js/revival-items.js?v=20260817-unique-icons"></script>'
if old_script in html:
    html = html.replace(old_script, new_script, 1)
elif new_script not in html:
    raise SystemExit('slayer.html: revival-items.js script tag not found')
HTML.write_text(html, encoding='utf-8')

print('Dedicated server PNGs now have priority over category Revival fallbacks.')
