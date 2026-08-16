# Servidor self-hosted

Este projeto não reimplementa o backend do zero na primeira etapa. Vamos partir do servidor comunitário existente e completar/corrigir o que o cliente 1.13.1 exigir.

## Implementação de referência

Projeto upstream:

```text
https://gitlab.com/dannyhpy/mightydoom-gameserver
```

O upstream atual usa Node.js/Koa, banco via Knex e pode rodar com SQLite (`better-sqlite3`). O `package.json` atual exige Node.js `>=24.0.0` e npm `>=11.0.0`.

## Instalação rápida

### 1. Instale Node.js 24+

Confirme:

```bash
node --version
npm --version
```

### 2. Clone o servidor

A partir da raiz deste repositório:

```bash
git clone https://gitlab.com/dannyhpy/mightydoom-gameserver.git server/community
cd server/community
```

O servidor upstream fica separado para que possamos acompanhar atualizações sem misturar APK/assets proprietários neste repositório.

### 3. Dependências

Comandos documentados pelo upstream:

```bash
npm install --omit=dev --omit=optional
npm install better-sqlite3
```

### 4. Banco SQLite

```bash
npx knex migrate:latest
```

Por padrão a configuração usa:

```text
db/local.sqlite3
```

### 5. Inicie o servidor

```bash
npm run start -- --addr 0.0.0.0 --port 8080 --debug
```

Sem argumentos, o upstream escuta em `0.0.0.0:8080`.

Para uso atrás de Nginx/Caddy, acrescente `--proxy`:

```bash
npm run start -- --addr 127.0.0.1 --port 8080 --proxy --debug
```

## Reverse proxy HTTPS com Nginx

O cliente do jogo espera HTTPS. Em uma VPS, um exemplo mínimo é:

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

Se o hostname for seu e possuir certificado público válido (ex.: Let's Encrypt), não é necessário incorporar uma CA privada no APK.

## Teste básico

Primeiro confirme que o processo responde localmente:

```bash
curl -v http://127.0.0.1:8080/
```

Um `404` em `/` não significa necessariamente que o servidor esteja quebrado; o importante nesta fase é confirmar que o processo Koa está atendendo e então testar endpoints reais do jogo.

Quando o reverse proxy estiver pronto:

```bash
curl -vk https://doom.seudominio.com/
```

## Próximos testes do cliente

A ordem sugerida é:

1. conexão TLS;
2. registro/login por device;
3. bootstrap/player data;
4. inventário;
5. tutorial;
6. entrada no primeiro capítulo;
7. conclusão do capítulo;
8. quests/eventos/recompensas;
9. funcionalidades baseadas em relógio/tempo;
10. loja/IAP substituída por comportamento local seguro.

## Segurança

Para uma instalação pessoal:

- mantenha a porta `8080` inacessível publicamente e exponha apenas Nginx/Caddy;
- use HTTPS;
- não reutilize senhas/chaves do ambiente de produção;
- faça backup periódico do SQLite;
- não exponha endpoints administrativos sem autenticação;
- não use credenciais reais Bethesda/Microsoft/Google no servidor alternativo.

## Upstream

O servidor comunitário é um projeto externo. Antes de incorporarmos qualquer código diretamente aqui, precisamos respeitar a licença aplicável do upstream. Por enquanto, este repositório apenas documenta como cloná-lo e usá-lo como dependência de pesquisa.
