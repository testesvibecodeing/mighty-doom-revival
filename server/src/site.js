import { createHash } from 'node:crypto'
import {
  createReadStream,
  createWriteStream,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  statSync,
  unlinkSync,
  writeFileSync
} from 'node:fs'
import { extname, join, resolve, sep } from 'node:path'
import { pipeline } from 'node:stream/promises'

// Site estático (server/public) + upload do APK por link temporário.
//
// O link de upload é criado por scripts/install.sh, que grava
// runtime/upload-token.json com um token aleatório e validade de 24 horas. O
// servidor relê esse arquivo a cada requisição (é minúsculo), então nada
// precisa reiniciar: enquanto o arquivo existir e não estiver expirado, o
// upload é aceito. Abrir "/upload-cancel/<token>" apaga o arquivo e mata o
// link na hora (antes das 24h) para ninguém mais enviar/substituir o APK. A
// expiração das 24h é aplicada pelo próprio servidor em cada requisição, sem
// precisar de cron.

const APK_FILENAME = 'mighty-doom-revival.apk'
const APK_PUBLIC_PATH = `/download/${APK_FILENAME}`
// APK do Mighty DOOM ~587 MB; 3 GiB cobre versões futuras com folga.
const UPLOAD_MAX_BYTES = 3 * 1024 * 1024 * 1024
const ZIP_MAGIC = Buffer.from([0x50, 0x4b, 0x03, 0x04])

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/plain; charset=utf-8',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.apk': 'application/vnd.android.package-archive'
}

function nowSeconds () {
  return Math.floor(Date.now() / 1000)
}

// rename com fallback: runtime/ e public/download podem viver em filesystems
// distintos (ex: volume do docker-compose), onde rename devolve EXDEV.
async function moveFile (from, to) {
  try {
    renameSync(from, to)
    return
  } catch (error) {
    if (error?.code !== 'EXDEV') throw error
  }
  await pipeline(createReadStream(from), createWriteStream(to))
  try {
    unlinkSync(from)
  } catch {}
}

// Todos os responders deste módulo retornam true (ou false, em serveFile)
// para que o roteador do index.js saiba que a resposta já foi escrita.
function json (res, status, payload) {
  const body = JSON.stringify(payload)
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(body),
    'cache-control': 'no-store'
  })
  res.end(body)
  return true
}

function htmlPage (res, status, title, bodyHtml) {
  const body = `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>${title}</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;background:radial-gradient(circle at 50% -20%,#2a0c04 0%,#0b0403 55%,#050201 100%);color:#f1e8db;font:16px/1.6 Rajdhani,system-ui,sans-serif}
.card{width:min(640px,100%);padding:32px 28px;border:1px solid rgba(255,93,21,.4);background:linear-gradient(160deg,rgba(30,16,10,.96),rgba(9,6,5,.97));box-shadow:0 30px 80px rgba(0,0,0,.55);clip-path:polygon(3% 0,97% 0,100% 12%,100% 88%,97% 100%,3% 100%,0 88%,0 12%)}
h1{margin:0 0 14px;font:400 clamp(22px,4.5vw,32px)/1.15 'Black Ops One',Rajdhani,sans-serif;letter-spacing:.02em;color:#ff8414;text-transform:uppercase}
p{margin:8px 0;color:#c9bfb2}
code{font:14px/1.6 Consolas,monospace;color:#ffb12a;word-break:break-all}
a.btn{display:inline-flex;align-items:center;gap:10px;margin-top:18px;padding:13px 22px;border:1px solid rgba(255,255,255,.14);background:linear-gradient(180deg,rgba(180,29,8,.94),rgba(91,8,4,.96));color:#ffe9d2;text-transform:uppercase;font-weight:700;text-decoration:none;clip-path:polygon(3% 0,97% 0,100% 20%,100% 80%,97% 100%,3% 100%,0 80%,0 20%)}
</style>
</head>
<body><main class="card">${bodyHtml}</main></body>
</html>`
  res.writeHead(status, {
    'content-type': 'text/html; charset=utf-8',
    'content-length': Buffer.byteLength(body),
    'cache-control': 'no-store',
    'x-robots-tag': 'noindex, nofollow'
  })
  res.end(body)
  return true
}

function uploadPageHtml (token, expiresAt) {
  const expiresIso = new Date(expiresAt * 1000).toISOString()
  const tokenJson = JSON.stringify(token)
  const expiresJson = JSON.stringify(expiresIso)
  return `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Enviar APK - Mighty DOOM Revival</title>
<style>
:root{color-scheme:dark;--orange:#ff7a0a;--green:#41e85b;--red:#ef493c}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;padding:clamp(14px,3vw,36px);background:radial-gradient(circle at 50% -20%,#2a0c04 0%,#0b0403 55%,#050201 100%);color:#f1e8db;font:16px/1.6 Rajdhani,system-ui,sans-serif;display:flex;justify-content:center}
main{width:min(760px,100%)}
h1{margin:8px 0 4px;font:400 clamp(24px,5vw,38px)/1.05 'Black Ops One',Rajdhani,sans-serif;text-transform:uppercase;background:linear-gradient(#ff3e20 5%,#ff9707 42%,#ffd231 66%,#ff7b00 92%);-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{margin:0 0 22px;color:#a59688;text-transform:uppercase;letter-spacing:.18em;font-size:13px;font-weight:700}
.panel{padding:clamp(18px,3vw,28px);border:1px solid rgba(255,93,21,.4);background:linear-gradient(160deg,rgba(30,16,10,.96),rgba(9,6,5,.97));box-shadow:0 30px 80px rgba(0,0,0,.55);clip-path:polygon(3% 0,97% 0,100% 10%,100% 90%,97% 100%,3% 100%,0 90%,0 10%)}
.drop{position:relative;display:grid;place-items:center;gap:8px;min-height:190px;padding:26px 18px;border:2px dashed rgba(255,122,10,.5);background:rgba(255,90,10,.04);text-align:center;transition:.2s;cursor:pointer}
.dragover .drop,.drop:hover{border-color:#ff9d27;background:rgba(255,110,20,.1)}
.drop .icon{font-size:44px;line-height:1}
.drop b{font-size:clamp(16px,3vw,19px);color:#ffd9a8}
.drop small{color:#a59688}
input[type=file]{position:absolute;inset:0;opacity:0;cursor:pointer}
.bar{height:16px;margin:18px 0 8px;border:1px solid rgba(255,255,255,.14);background:rgba(0,0,0,.5);clip-path:polygon(1% 0,99% 0,100% 30%,100% 70%,99% 100%,1% 100%,0 70%,0 30%);overflow:hidden}
.bar>div{height:100%;width:0%;background:linear-gradient(90deg,#b51d08,#ff7a0a,#ffd231);transition:width .15s}
.status{min-height:24px;color:#ffb12a;font-weight:600;overflow-wrap:anywhere}
.status.ok{color:var(--green)}.status.err{color:var(--red)}
.kv{display:grid;grid-template-columns:auto 1fr;gap:4px 16px;margin:12px 0 0;padding:14px 16px;border:1px solid rgba(255,255,255,.08);background:rgba(0,0,0,.35);font-size:15px}
.kv b{color:#ff8b24}
.kv code{font:13px/1.5 Consolas,monospace;color:#ffb12a;word-break:break-all}
.meta{display:flex;flex-wrap:wrap;gap:8px 22px;margin:16px 0 6px;color:#a59688;font-size:13px}
.meta b{color:#ff8b24}
.help{margin:18px 0 0;color:#8f867c;font-size:14px}
.help code{color:#ffb12a}
footer{margin-top:16px;color:#675f58;font-size:12px;text-align:center}
</style>
</head>
<body>
<main>
<h1>Enviar APK</h1>
<p class="sub">Mighty DOOM Revival // link tempor&aacute;rio</p>
<div class="panel">
  <div class="drop" id="drop">
    <span class="icon">&#128293;</span>
    <b>Arraste o APK aqui ou toque para escolher</b>
    <small>APK j&aacute; patcheado com o seu dom&iacute;nio (.apk) &mdash; at&eacute; 3 GB</small>
    <input type="file" id="file" accept=".apk,application/vnd.android.package-archive">
  </div>
  <div class="bar" aria-hidden="true"><div id="fill"></div></div>
  <div class="status" id="status" role="status" aria-live="polite">Aguardando arquivo...</div>
  <div class="meta">
    <span>Expira em <b id="countdown">--</b></span>
    <span>Arquivo <b id="size">--</b></span>
  </div>
  <div class="kv" id="result" hidden>
    <b>Arquivo</b><code id="rName">-</code>
    <b>Tamanho</b><code id="rSize">-</code>
    <b>SHA-256</b><code id="rSha">-</code>
    <b>Download</b><code id="rUrl">-</code>
  </div>
  <p class="help">Depois de enviar, o bot&atilde;o de download do site passa a servir este APK automaticamente.
  Para desativar este link de upload imediatamente (opcional): <code>/upload-cancel/${token}</code></p>
</div>
<footer>N&atilde;o afiliado &agrave; Bethesda, ZeniMax, Microsoft, id Software ou Alpha Dog Games.</footer>
</main>
<script>
(function(){
  var token=${tokenJson},expires=${expiresAt},expiresIso=${expiresJson};
  var drop=document.getElementById('drop'),input=document.getElementById('file'),
      fill=document.getElementById('fill'),status=document.getElementById('status'),
      sizeEl=document.getElementById('size'),cd=document.getElementById('countdown');
  function fmt(b){if(!b||b<=0)return'0 B';var u=['B','KB','MB','GB'],i=0,v=b;while(v>=1024&&i<3){v/=1024;i++}return(v>=100||i===0?v.toFixed(0):v.toFixed(1))+' '+u[i]}
  function tick(){var s=expires-Math.floor(Date.now()/1000);
    if(s<=0){cd.textContent='expirado';return}
    var h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=s%60;
    cd.textContent=(h<10?'0':'')+h+':'+(m<10?'0':'')+m+':'+(x<10?'0':'')+x;
    setTimeout(tick,1000)}
  tick();
  ['dragover','dragenter'].forEach(function(e){drop.addEventListener(e,function(ev){ev.preventDefault();drop.classList.add('dragover')})});
  ['dragleave','drop'].forEach(function(e){drop.addEventListener(e,function(ev){ev.preventDefault();drop.classList.remove('dragover')})});
  drop.addEventListener('drop',function(ev){if(ev.dataTransfer.files.length)send(ev.dataTransfer.files[0])});
  input.addEventListener('change',function(){if(input.files.length)send(input.files[0])});
  function send(file){
    if(!/\\.apk$/i.test(file.name)){status.textContent='Selecione um arquivo .apk';status.className='status err';return}
    sizeEl.textContent=fmt(file.size);
    status.textContent='Enviando '+file.name+' ('+fmt(file.size)+')...';status.className='status';
    fill.style.width='0%';
    var xhr=new XMLHttpRequest();
    xhr.open('POST','/upload/'+token,true);
    xhr.setRequestHeader('Content-Type','application/octet-stream');
    xhr.upload.onprogress=function(ev){if(ev.lengthComputable){fill.style.width=(ev.loaded/ev.total*100).toFixed(1)+'%';
      status.textContent='Enviando... '+fmt(ev.loaded)+' de '+fmt(ev.total)}};
    xhr.onload=function(){
      var body={};try{body=JSON.parse(xhr.responseText)}catch(_){}
      if(xhr.status===200){
        fill.style.width='100%';
        status.textContent='APK publicado! Já está disponível no site.';status.className='status ok';
        document.getElementById('result').hidden=false;
        document.getElementById('rName').textContent=body.filename||file.name;
        document.getElementById('rSize').textContent=fmt(body.size);
        document.getElementById('rSha').textContent=body.sha256||'-';
        document.getElementById('rUrl').textContent=location.origin+(body.url||'');
      }else{
        status.textContent='Falhou ('+xhr.status+'): '+(body.error||'tente de novo');status.className='status err';
        fill.style.width='0%';
      }
    };
    xhr.onerror=function(){status.textContent='Erro de rede durante o envio.';status.className='status err'};
    xhr.send(file);
  }
})();
</script>
</body>
</html>`
}

export function createSiteRouter ({ publicDir, uploadDir }) {
  const root = resolve(publicDir)
  mkdirSync(join(root, 'download'), { recursive: true })
  const tokenFile = join(uploadDir, 'upload-token.json')
  const apkMetaFile = join(uploadDir, 'apk-meta.json')
  const apkFile = join(root, 'download', APK_FILENAME)

  function readUploadToken () {
    try {
      const raw = JSON.parse(readFileSync(tokenFile, 'utf8'))
      if (typeof raw?.token !== 'string' || !raw.token) return null
      if (!Number.isFinite(raw?.expires_at) || raw.expires_at <= 0) return null
      return { token: raw.token, expiresAt: Math.floor(raw.expires_at) }
    } catch {
      return null
    }
  }

  // 'valid' | 'expired' | 'missing' - um token errado responde igual a um
  // link inexistente, para não confirmar a existência de link ativo a quem
  // não o conhece.
  function uploadTokenState (candidate) {
    if (typeof candidate !== 'string' || !/^[a-f0-9]{16,128}$/i.test(candidate)) return 'missing'
    const stored = readUploadToken()
    if (!stored || stored.token !== candidate) return 'missing'
    if (nowSeconds() >= stored.expiresAt) return 'expired'
    return 'valid'
  }

  function apkInfo () {
    if (!existsSync(apkFile)) {
      return { available: false, filename: APK_FILENAME, url: APK_PUBLIC_PATH }
    }
    let meta = {}
    try {
      meta = JSON.parse(readFileSync(apkMetaFile, 'utf8'))
    } catch {}
    const stats = statSync(apkFile)
    return {
      available: true,
      filename: APK_FILENAME,
      url: APK_PUBLIC_PATH,
      size: Number.isFinite(meta.size) ? meta.size : stats.size,
      sha256: typeof meta.sha256 === 'string' ? meta.sha256 : null,
      uploaded_at: Number.isFinite(meta.uploaded_at) ? meta.uploaded_at : Math.floor(stats.mtimeMs / 1000)
    }
  }

  // Resolve um caminho de URL dentro do root público bloqueando path
  // traversal ("../" escapando do root).
  function safeResolve (pathname) {
    let decoded
    try {
      decoded = decodeURIComponent(pathname)
    } catch {
      return null
    }
    if (decoded.includes('\0')) return null
    const target = resolve(root, `.${decoded}`)
    if (target !== root && !target.startsWith(root + sep)) return null
    return target
  }

  function serveFile (req, res, filePath, cacheControl = 'public, max-age=3600') {
    let stats
    try {
      stats = statSync(filePath)
    } catch {
      return false
    }
    if (!stats.isFile()) return false

    const type = MIME_TYPES[extname(filePath).toLowerCase()] || 'application/octet-stream'
    const size = stats.size
    const headers = {
      'content-type': type,
      'accept-ranges': 'bytes',
      'cache-control': cacheControl,
      'last-modified': stats.mtime.toUTCString()
    }

    // Range (retomada de download) - essencial para um APK de ~600 MB.
    const range = String(req.headers.range || '')
    const match = /^bytes=(\d*)-(\d*)$/.exec(range)
    if (match && (match[1] !== '' || match[2] !== '')) {
      let start
      let end
      if (match[1] !== '') {
        start = Number.parseInt(match[1], 10)
        end = match[2] !== '' ? Number.parseInt(match[2], 10) : size - 1
      } else {
        const suffix = Number.parseInt(match[2], 10)
        start = Math.max(0, size - suffix)
        end = size - 1
      }
      if (!Number.isFinite(start) || !Number.isFinite(end) || start > end || start >= size) {
        res.writeHead(416, { 'content-range': `bytes */${size}`, 'cache-control': 'no-store' })
        res.end()
        return true
      }
      end = Math.min(end, size - 1)
      res.writeHead(206, {
        ...headers,
        'content-range': `bytes ${start}-${end}/${size}`,
        'content-length': end - start + 1
      })
      createReadStream(filePath, { start, end }).pipe(res)
      return true
    }

    res.writeHead(200, { ...headers, 'content-length': size })
    if (req.method === 'HEAD') {
      res.end()
      return true
    }
    createReadStream(filePath).pipe(res)
    return true
  }

  function invalidUploadLink (res, state) {
    const expired = state === 'expired'
    return htmlPage(res, 410, 'Link indisponível - Mighty DOOM Revival', `
      <h1>Link ${expired ? 'expirado' : 'inv&aacute;lido'}</h1>
      <p>Este link tempor&aacute;rio de upload ${expired ? 'passou das 24 horas de validade' : 'n&atilde;o existe ou j&aacute; foi desativado'}.
      Nenhum upload pode ser feito por ele.</p>
      <p>Para gerar um novo link, rode <code>sudo ./scripts/install.sh</code> na VPS.</p>
      <a class="btn" href="/">&#8592; Voltar ao site</a>`)
  }

  function receiveUpload (req, res, token) {
    const declared = Number.parseInt(String(req.headers['content-length'] || ''), 10)
    if (!Number.isFinite(declared) || declared <= 0) {
      return json(res, 411, { ok: false, error: 'content-length obrigatório' })
    }
    if (declared > UPLOAD_MAX_BYTES) {
      return json(res, 413, { ok: false, error: `APK maior que o limite de 3 GB (${declared} bytes)` })
    }
    if (declared < 4) {
      return json(res, 400, { ok: false, error: 'arquivo pequeno demais para ser um APK' })
    }

    mkdirSync(uploadDir, { recursive: true })
    mkdirSync(join(root, 'download'), { recursive: true })
    const tmpFile = join(uploadDir, `${APK_FILENAME}.part-${process.pid}-${Date.now()}`)
    const out = createWriteStream(tmpFile)
    const hash = createHash('sha256')
    let received = 0
    let head = Buffer.alloc(0)
    let failed = false

    const cleanup = () => {
      failed = true
      out.destroy()
      try {
        unlinkSync(tmpFile)
      } catch {}
    }

    req.on('data', chunk => {
      if (failed) return
      received += chunk.length
      if (received > UPLOAD_MAX_BYTES) {
        cleanup()
        json(res, 413, { ok: false, error: 'APK maior que o limite de 3 GB' })
        req.destroy()
        return
      }
      if (head.length < 4) head = Buffer.concat([head, chunk.subarray(0, 4 - head.length)])
      hash.update(chunk)
      out.write(chunk)
      // Backpressure: em uploads de centenas de MB, não deixar o buffer do
      // stream crescer sem limite enquanto o disco não acompanha.
      if (out.writableLength > 8 * 1024 * 1024) {
        req.pause()
        out.once('drain', () => {
          if (!failed) req.resume()
        })
      }
    })

    out.on('error', error => {
      if (failed) return
      cleanup()
      json(res, 500, { ok: false, error: `falha ao gravar: ${error.message}` })
    })

    req.on('error', () => {
      if (!failed) cleanup()
    })

    req.on('end', () => {
      if (failed) return
      if (received !== declared) {
        cleanup()
        return json(res, 400, { ok: false, error: `upload incompleto (${received} de ${declared} bytes)` })
      }
      if (!head.subarray(0, 4).equals(ZIP_MAGIC)) {
        cleanup()
        return json(res, 400, { ok: false, error: 'isso não parece um APK (assinatura ZIP ausente)' })
      }
      // Revalida o token no fim do upload: o link pode ter sido desativado
      // enquanto o arquivo trafegava.
      if (uploadTokenState(token) !== 'valid') {
        cleanup()
        return json(res, 410, { ok: false, error: 'link de upload desativado durante o envio' })
      }
      out.end(async () => {
        if (failed) return
        try {
          await moveFile(tmpFile, apkFile)
        } catch (error) {
          try { unlinkSync(tmpFile) } catch {}
          return json(res, 500, { ok: false, error: `falha ao publicar: ${error.message}` })
        }
        const meta = {
          size: received,
          sha256: hash.digest('hex'),
          uploaded_at: nowSeconds()
        }
        try {
          writeFileSync(apkMetaFile, JSON.stringify(meta, null, 2))
        } catch {}
        json(res, 200, {
          ok: true,
          filename: APK_FILENAME,
          url: APK_PUBLIC_PATH,
          size: meta.size,
          sha256: meta.sha256,
          uploaded_at: meta.uploaded_at
        })
      })
    })
  }

  function handle (req, res, path) {
    // --- metadados públicos do APK enviado (o site usa para o botão) ---
    if (path === '/revival/apk') {
      if (req.method !== 'GET' && req.method !== 'HEAD') {
        return json(res, 405, { ok: false, error: 'method-not-allowed' })
      }
      return json(res, 200, { ok: true, ...apkInfo() })
    }

    // --- página de upload temporária ---
    let match = /^\/upload\/([A-Za-z0-9]+)$/.exec(path)
    if (match) {
      const state = uploadTokenState(match[1])
      if (state !== 'valid') return invalidUploadLink(res, state)
      if (req.method === 'GET' || req.method === 'HEAD') {
        const body = uploadPageHtml(match[1], readUploadToken().expiresAt)
        res.writeHead(200, {
          'content-type': 'text/html; charset=utf-8',
          'content-length': Buffer.byteLength(body),
          'cache-control': 'no-store',
          'x-robots-tag': 'noindex, nofollow'
        })
        res.end(req.method === 'HEAD' ? undefined : body)
        return true
      }
      if (req.method === 'POST') {
        receiveUpload(req, res, match[1])
        return true
      }
      return json(res, 405, { ok: false, error: 'method-not-allowed' })
    }

    // --- desativa o link de upload imediatamente ---
    match = /^\/upload-cancel\/([A-Za-z0-9]+)$/.exec(path)
    if (match) {
      if (req.method !== 'GET' && req.method !== 'HEAD') {
        return json(res, 405, { ok: false, error: 'method-not-allowed' })
      }
      const stored = readUploadToken()
      if (stored && stored.token === match[1]) {
        try {
          unlinkSync(tokenFile)
        } catch {}
        return htmlPage(res, 200, 'Upload desativado - Mighty DOOM Revival', `
          <h1>Link desativado</h1>
          <p class="ok">O link tempor&aacute;rio de upload foi <b>eliminado agora</b>.
          Ningu&eacute;m (nem voc&ecirc;) consegue mais enviar ou substituir o APK por ele.</p>
          <p>O APK j&aacute; publicado, se houver, continua no ar normalmente no download do site.</p>
          <a class="btn" href="/">&#8592; Voltar ao site</a>`)
      }
      return htmlPage(res, 200, 'Upload desativado - Mighty DOOM Revival', `
        <h1>Nada a desativar</h1>
        <p>Este link de cancelamento n&atilde;o corresponde a nenhum upload ativo
        (j&aacute; foi desativado, expirou ou nunca existiu).</p>
        <a class="btn" href="/">&#8592; Voltar ao site</a>`)
    }

    // --- download do APK enviado ---
    if (path === APK_PUBLIC_PATH && (req.method === 'GET' || req.method === 'HEAD')) {
      if (!existsSync(apkFile)) {
        return htmlPage(res, 404, 'APK indisponível - Mighty DOOM Revival', `
          <h1>APK ainda n&atilde;o enviado</h1>
          <p>Nenhum APK foi publicado neste servidor ainda. Use o link tempor&aacute;rio
          de upload impresso pelo <code>scripts/install.sh</code> no terminal da VPS.</p>
          <a class="btn" href="/">&#8592; Voltar ao site</a>`)
      }
      serveFile(req, res, apkFile, 'no-cache')
      return true
    }

    // --- site estático ---
    if ((req.method === 'GET' || req.method === 'HEAD') && path === '/account') {
      if (serveFile(req, res, join(root, 'account.html'), 'no-cache')) return true
      return json(res, 404, { ok: false, error: 'account-page-not-found' })
    }

    if ((req.method === 'GET' || req.method === 'HEAD') && (path === '/' || path === '/index.html')) {
      if (serveFile(req, res, join(root, 'index.html'), 'no-cache')) return true
      return json(res, 500, { ok: false, error: 'index.html ausente em server/public' })
    }

    if ((req.method === 'GET' || req.method === 'HEAD') &&
        (path === '/assets/' || path.startsWith('/assets/') || path === '/favicon.ico' || path === '/robots.txt')) {
      const target = safeResolve(path)
      if (target && serveFile(req, res, target)) return true
      return json(res, 404, { ok: false, error: 'not-found' })
    }

    return false
  }

  return { handle, apkInfo }
}
