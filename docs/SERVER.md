# Servidor self-hosted Revival

O runtime principal está em `server/` e é uma implementação própria de compatibilidade, construída para evoluir endpoint por endpoint conforme o cliente 1.13.1 for analisado.

O projeto comunitário `dannyhpy/mightydoom-gameserver` continua sendo uma referência técnica útil para comparar nomes de endpoints e comportamento observado, mas o Revival não precisa cloná-lo para iniciar.

## Stack

CONFIRMADO em 2026-08-17 (`server/package.json` sem `dependencies`,
`grep -n "^import" server/src/index.js`, `server/src/db.js:4`):

- Node.js **>= 22.5.0** (`engines` do `package.json`; o CI usa 24)
- HTTP: `node:http` builtin — **sem Koa** e sem framework
- SQLite: `node:sqlite` (`DatabaseSync`) — **sem `better-sqlite3`**
- **zero dependências npm**: `npm install` não baixa nada
- JSON para configuração de packs/eventos
- Nginx/Caddy recomendado para HTTPS

## Instalação

```bash
cd server
cp config/revival.example.json config/revival.json
cp config/packs.example.json config/packs.json
cp config/events.example.json config/events.json
npm install
npm run check
npm start
```

Por padrão:

```text
http://0.0.0.0:8080
```

Health check:

```bash
curl http://127.0.0.1:8080/revival/health
```

## Persistência

O SQLite fica por padrão em:

```text
server/runtime/revival.sqlite3
```

O banco guarda usuários locais, moedas, itens, slots, configurações, quotas de packs, estado de eventos e um log de chamadas ainda não implementadas.

## Dados do jogo

O cliente solicita um token em `/game/player/game-data-token` e depois busca `/data`.

O arquivo esperado localmente é:

```text
server/data/game-data.json
```

Ele fica fora do Git. Até a importação/validação desse dataset, o health check informa `game_data_loaded: false`.

## Loja Revival

A loja própria foi desenhada com uma regra rígida: **nenhum pacote usa dinheiro real**.

`server/config/packs.json` define custo e conteúdo usando `rid` ou `tag` de recursos existentes no game data. O backend rejeita packs que tentem declarar `price`, `iap` ou `real_money`.

A compra acontece por `/game/store/purchase`, debita recursos internos do jogador de forma transacional e concede os recursos configurados.

Rotas de IAP real permanecem desativadas.

## Eventos

`server/config/events.json` aceita eventos sempre ativos ou com janela de início/fim.

Cada jogador pode ter estado persistente separado para:

- game mode events;
- store offer events;
- battle pass events.

O servidor gera a agenda em `/game/events/get-schedule` e o progresso em `/game/events/get-progress`. As definições específicas das temporadas serão preenchidas conforme forem recuperadas/validadas.

## Research Mode

Enquanto a compatibilidade não estiver completa, use:

```env
RESEARCH_MODE=true
```

Uma chamada POST autenticada ainda desconhecida é registrada no SQLite. Isso permite descobrir a sequência real que o APK exige e substituir respostas genéricas por implementações fiéis.

Quando a matriz de endpoints estiver fechada:

```env
RESEARCH_MODE=false
```

## Docker

Na raiz:

```bash
docker compose up --build -d
```

Os volumes locais preservam banco/config/dados sem colocar esses arquivos no Git.

## Reverse proxy HTTPS com Nginx

Exemplo:

```nginx
server {
    listen 443 ssl http2;
    server_name doom.seudominio.com;

    ssl_certificate     /etc/letsencrypt/live/doom.seudominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/doom.seudominio.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

Se o hostname possuir certificado público válido, a solução tende a ser mais simples do que depender de CA privada instalada no Android.

## Ordem de validação

1. patch do hostname/TLS no APK;
2. `/game/auth/register` e login local;
3. game data;
4. user data/inventário;
5. tutorial;
6. capítulos e recompensas;
7. slayers/gear/talentos;
8. quests/daily/idle/inbox;
9. loja e packs por moeda interna;
10. eventos/store-offer/battle pass;
11. regressão completa antes de desativar Research Mode.

Veja também `docs/ROADMAP-100-PERCENT.md`.
