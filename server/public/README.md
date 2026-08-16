# Mighty DOOM Revival — Website

Site estático servido pelo próprio Revival Server em `server/public`.
Ao acessar o domínio (`https://seu-dominio/`) o `index.html` desta pasta
abre direto — sem servidor web extra: o nginx/Caddy da VPS já aponta tudo
para o processo Node, que também cuida do site.

## Dados reais

O site consulta no mesmo domínio, a cada 30 segundos:

- `GET /revival/health` — status, jogadores, pacotes, eventos, uptime,
  versões de cliente/API, game data, APK disponível.
- `GET /revival/apk` — metadados do APK publicado (tamanho, SHA-256, data).

O fundo interativo usa three.js (`assets/js/hell-scene.js`): fumaça
procedural, portal com runas e brasas em partículas GPU, com parallax de
mouse/scroll e degradação automática de qualidade. Cai para um fundo
estático em `prefers-reduced-motion` ou sem WebGL.

## Configuração

Tudo funciona sem configurar nada (same-origin). Só edite
`assets/js/config.js` se o site rodar em um host diferente do servidor:

```js
window.MD_CONFIG = {
  serverUrl: "https://doom.seudominio.com", // vazio = mesmo domínio
  githubUrl: "https://github.com/testesvibecodeing/mighty-doom-revival"
};
```

## APK para download

`scripts/install.sh` imprime no final um link temporário de upload
(`https://dominio/upload/<token>`, válido 24h) e, logo abaixo, o link de
cancelamento imediato (`https://dominio/upload-cancel/<token>`). O APK
enviado é servido em `/download/mighty-doom-revival.apk` (com suporte a
Range/retomada) e o botão de download do site passa a exibir tamanho e
SHA-256 reais.

## Rodar local

```bash
cd server && npm start   # http://127.0.0.1:8080
```
