// Aviso legal visível do site Revival.
// Não concede licença sobre o jogo; apenas informa a política do projeto/instância.
(() => {
  const VERSION = '2026-08-16-v2'
  const KEY = `revival-legal-accepted:${VERSION}`
  const cfg = window.MD_CONFIG || {}
  const github = (cfg.githubUrl || 'https://github.com/testesvibecodeing/mighty-doom-revival').replace(/\/+$/, '')
  const legalUrl = `${github}/blob/main/docs/LEGAL-PRESERVATION.md`

  const styles = document.createElement('style')
  styles.textContent = `
    .revival-legal-modal{position:fixed;inset:0;z-index:99999;display:grid;place-items:center;padding:18px;background:rgba(0,0,0,.86);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px)}
    .revival-legal-modal[hidden]{display:none}
    .revival-legal-box{width:min(760px,100%);max-height:min(88vh,820px);overflow:auto;border:1px solid rgba(255,104,28,.55);background:linear-gradient(180deg,#170b07,#090504);color:#eadfd2;box-shadow:0 28px 90px rgba(0,0,0,.7),0 0 55px rgba(255,65,0,.12);font-family:Rajdhani,Arial,sans-serif;clip-path:polygon(2% 0,98% 0,100% 3%,100% 97%,98% 100%,2% 100%,0 97%,0 3%)}
    .revival-legal-head{padding:22px 24px 16px;border-bottom:1px solid rgba(255,104,28,.22);background:linear-gradient(90deg,rgba(120,18,4,.28),rgba(255,104,28,.04));display:flex;gap:14px;align-items:flex-start}.revival-legal-head i{color:#ff7b22;font-size:24px;margin-top:3px}.revival-legal-head h2{margin:0 0 4px;font:400 clamp(22px,4vw,30px)/1.05 'Black Ops One',Rajdhani,sans-serif;color:#fff0dc}.revival-legal-head p{margin:0;color:#bcae9f}
    .revival-legal-body{padding:20px 24px}.revival-legal-body>p{margin:0 0 14px;color:#cbbcaf;line-height:1.65}.revival-legal-list{margin:0;padding:0;list-style:none;display:grid;gap:10px}.revival-legal-list li{display:grid;grid-template-columns:20px 1fr;gap:10px;align-items:flex-start;color:#d8cabd;line-height:1.55}.revival-legal-list i{color:#ff7b22;margin-top:4px}.revival-legal-list strong{color:#fff1df}.revival-legal-policy{margin-top:16px;padding:14px 15px;border-left:3px solid #ff4d20;background:rgba(255,72,22,.08);color:#e9cfc2;line-height:1.6}.revival-legal-policy strong{color:#ff9b45}.revival-legal-check{display:flex;gap:10px;align-items:flex-start;margin-top:18px;padding:13px;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.025)}.revival-legal-check input{margin-top:4px;accent-color:#ff6a20}.revival-legal-check label{color:#c8b9aa;line-height:1.45;cursor:pointer}.revival-legal-actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:18px}.revival-legal-actions button,.revival-legal-actions a{min-height:48px;padding:0 18px;display:inline-flex;align-items:center;justify-content:center;gap:9px;border:1px solid rgba(255,255,255,.13);font-weight:700;text-transform:uppercase;cursor:pointer}.revival-legal-accept{background:linear-gradient(180deg,#b9250c,#6f1007);border-color:#ff6328!important;color:white}.revival-legal-accept:disabled{opacity:.38;cursor:not-allowed}.revival-legal-read{background:#111;color:#ddd}.revival-legal-small{margin-top:14px!important;font-size:12px;color:#80746c!important}
    .revival-site-notice{position:relative;z-index:4;margin:0 auto 22px;width:min(1480px,calc(100% - 28px));padding:12px 16px;border:1px solid rgba(255,99,32,.28);background:linear-gradient(90deg,rgba(71,12,5,.72),rgba(15,8,6,.9));color:#d8c2b3;font-family:Rajdhani,Arial,sans-serif;line-height:1.45;text-align:center}.revival-site-notice strong{color:#ff9c4b}.revival-site-notice a{color:#ffba76;text-decoration:underline}
    .hero-media{background:radial-gradient(circle at 70% 34%,rgba(255,79,18,.16),transparent 24%),radial-gradient(circle at 58% 58%,rgba(117,14,4,.18),transparent 32%),linear-gradient(135deg,#090302,#180604 48%,#070201)}
    .hero-media img{display:none!important}
    .revival-unofficial-badge{display:inline-flex;align-items:center;gap:7px;margin-bottom:11px;padding:6px 10px;border:1px solid rgba(255,93,21,.34);background:rgba(20,8,5,.76);color:#ff9b50;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em}
    @media(max-width:640px){.revival-legal-actions>*{width:100%}.revival-legal-head,.revival-legal-body{padding-left:16px;padding-right:16px}}
  `
  document.head.appendChild(styles)

  function injectPermanentNotice () {
    const footer = document.querySelector('footer')
    if (!footer || document.querySelector('.revival-site-notice')) return
    const notice = document.createElement('div')
    notice.className = 'revival-site-notice'
    notice.innerHTML = `<strong>PROJETO NÃO OFICIAL · PRESERVAÇÃO E INTEROPERABILIDADE</strong> — Mighty DOOM/DOOM e marcas, personagens, artes, músicas e demais elementos pertencem aos seus respectivos titulares. O Revival não concede licença sobre o jogo, não é afiliado à Bethesda, ZeniMax, Microsoft, id Software ou Alpha Dog Games e não deve ser usado para redistribuir o cliente original, assets ou conteúdo proprietário. <strong>Se os serviços oficiais necessários ao gameplay voltarem a operar de forma funcional, a política deste projeto é retirar do ar/arquivar a substituição comunitária.</strong> <a href="${legalUrl}" target="_blank" rel="noopener">Política legal completa</a>.`
    footer.parentNode.insertBefore(notice, footer)
  }

  function injectHeroBadge () {
    const copy = document.querySelector('.hero-copy')
    if (!copy || copy.querySelector('.revival-unofficial-badge')) return
    const badge = document.createElement('div')
    badge.className = 'revival-unofficial-badge'
    badge.innerHTML = '<i class="fa-solid fa-shield-halved"></i> projeto comunitário não oficial'
    copy.insertBefore(badge, copy.firstChild)
  }

  function createModal () {
    if (document.querySelector('.revival-legal-modal')) return
    const modal = document.createElement('div')
    modal.className = 'revival-legal-modal'
    modal.hidden = localStorage.getItem(KEY) === 'accepted'
    modal.innerHTML = `
      <div class="revival-legal-box" role="dialog" aria-modal="true" aria-labelledby="revivalLegalTitle">
        <div class="revival-legal-head">
          <i class="fa-solid fa-triangle-exclamation"></i>
          <div><h2 id="revivalLegalTitle">Aviso de uso e preservação</h2><p>Leia antes de continuar nesta instância Revival.</p></div>
        </div>
        <div class="revival-legal-body">
          <p>Esta instância existe para <strong>preservação, pesquisa técnica e interoperabilidade self-hosted</strong> com uma cópia do cliente que o próprio usuário tenha obtido legitimamente. Ela não é produto oficial e não concede qualquer direito sobre o jogo.</p>
          <ul class="revival-legal-list">
            <li><i class="fa-solid fa-circle-check"></i><span><strong>Uso privado/self-hosted:</strong> o servidor foi pensado para uso pessoal ou de uma comunidade administrada pelo próprio operador. Cada administrador responde pelo uso da sua instância.</span></li>
            <li><i class="fa-solid fa-ban"></i><span><strong>Sem redistribuição de conteúdo proprietário:</strong> não publique nem redistribua o cliente original, APK original, assets, músicas, vídeos, modelos, credenciais, chaves ou código proprietário dos titulares.</span></li>
            <li><i class="fa-solid fa-screwdriver-wrench"></i><span><strong>Patcher local:</strong> o usuário fornece a própria cópia e gera localmente uma versão configurada para o servidor escolhido. Este projeto não transforma isso em licença de distribuição.</span></li>
            <li><i class="fa-solid fa-file-contract"></i><span><strong>Termos do jogo:</strong> o uso do cliente continua sujeito às licenças/EULA dos titulares e às leis aplicáveis. O Revival não substitui, altera nem revoga esses termos.</span></li>
            <li><i class="fa-solid fa-copyright"></i><span><strong>Direitos preservados:</strong> Mighty DOOM, DOOM, Bethesda, ZeniMax, Microsoft, id Software, Alpha Dog Games e seus elementos protegidos pertencem aos respectivos titulares. Não há afiliação, patrocínio ou endosso.</span></li>
            <li><i class="fa-solid fa-coins"></i><span><strong>Sem monetização real pelo Revival:</strong> o objetivo é restaurar funcionalidades e eventos do jogo sem cobrança em dinheiro real pelo servidor comunitário.</span></li>
          </ul>
          <div class="revival-legal-policy"><strong>Política expressa de encerramento:</strong> se os serviços oficiais necessários ao funcionamento do jogo voltarem a operar de forma efetiva, ou se a preservação deixar de depender desta substituição comunitária, o mantenedor declara a intenção de retirar do ar/arquivar este projeto e interromper a substituição do serviço oficial.</div>
          <label class="revival-legal-check"><input type="checkbox" id="revivalLegalCheck"><span>Li e entendi que este projeto é não oficial, não me concede licença sobre o jogo e não autoriza redistribuição de conteúdo proprietário.</span></label>
          <div class="revival-legal-actions">
            <button class="revival-legal-accept" id="revivalLegalAccept" type="button" disabled><i class="fa-solid fa-check"></i> Li e entendi</button>
            <a class="revival-legal-read" href="${legalUrl}" target="_blank" rel="noopener"><i class="fa-solid fa-book"></i> Ler política legal</a>
          </div>
          <p class="revival-legal-small">Este aviso é uma política do projeto e não é garantia de imunidade jurídica. O operador da instância continua responsável por observar a legislação e os termos aplicáveis na sua jurisdição.</p>
        </div>
      </div>`
    document.body.appendChild(modal)

    const checkbox = modal.querySelector('#revivalLegalCheck')
    const accept = modal.querySelector('#revivalLegalAccept')
    checkbox.addEventListener('change', () => { accept.disabled = !checkbox.checked })
    accept.addEventListener('click', () => {
      if (!checkbox.checked) return
      localStorage.setItem(KEY, 'accepted')
      modal.hidden = true
    })
  }

  function boot () {
    injectHeroBadge()
    injectPermanentNotice()
    createModal()
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true })
  else boot()
})()
