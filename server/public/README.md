# Mighty DOOM Revival — Website

Site estático servido pelo próprio Revival Server em `server/public`.

## Visual

O frontend usa novamente o layout vermelho/laranja original do projeto, com HUD, painéis técnicos e fundo Three.js. A arte oficial do jogo foi removida do repositório: o hero agora usa apenas fundo procedural/CSS + Three.js.

O visual pode fazer referência descritiva ao cliente compatível, mas o site exibe aviso claro de que o Revival é um projeto comunitário, independente e não oficial.

## Aviso legal no site

`assets/js/legal-modal.js` exibe, na primeira visita, um modal obrigatório explicando:

- uso de preservação/interoperabilidade e operação self-hosted;
- ausência de afiliação com Bethesda, ZeniMax, Microsoft, id Software e Alpha Dog Games;
- que Mighty DOOM/DOOM e conteúdo relacionado pertencem aos respectivos titulares;
- que o usuário deve fornecer a própria cópia do cliente;
- que o patcher gera a saída localmente;
- que o projeto não concede licença para redistribuir APK original, assets ou outro conteúdo proprietário;
- que o uso do cliente continua sujeito às licenças/EULA e leis aplicáveis;
- que o Revival não usa monetização real no servidor comunitário;
- política expressa do mantenedor: se os serviços oficiais necessários ao gameplay voltarem a operar de forma funcional, o projeto será retirado do ar/arquivado e a substituição comunitária será interrompida.

O aceite é gravado apenas no `localStorage` do navegador. A política completa continua em `docs/LEGAL-PRESERVATION.md`.

## Dados reais

O site consulta, no mesmo domínio, a cada 30 segundos:

- `GET /revival/health` — status, jogadores, pacotes, eventos, uptime, versões e GameData;
- `GET /revival/apk` — metadados do pacote publicado pela própria instância, quando houver.

## Configuração

Edite `assets/js/config.js` apenas se o frontend estiver em outro host:

```js
window.MD_CONFIG = {
  serverUrl: "https://doom.seudominio.com",
  healthUrl: "",
  apkInfoUrl: "",
  githubUrl: "https://github.com/testesvibecodeing/mighty-doom-revival"
};
```

## Patcher local

O fluxo principal permanece:

1. usuário fornece sua própria cópia local;
2. executa o patcher;
3. informa o domínio da instância Revival;
4. recebe localmente o pacote configurado;
5. instala no próprio dispositivo.

O frontend não cria download automático de APK de terceiros.

## Rodar local

```bash
cd server
npm start
```

Acesse `http://127.0.0.1:8080/`.
