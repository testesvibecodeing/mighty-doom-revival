# Revival Server

Servidor de compatibilidade **clean-room** para o cliente Android do Mighty DOOM 1.13.1. Ele não contém APK, assets nem dados proprietários do jogo.

## Objetivo

A arquitetura foi preparada para chegar a 100% de exploração do cliente sem depender de serviços oficiais:

- autenticação por dispositivo;
- persistência SQLite;
- entrega de `game-data.json` local;
- inventário e moedas;
- loja configurável;
- pacotes customizados;
- agenda de eventos;
- estados de eventos por jogador;
- battle pass/eventos através de templates que serão preenchidos conforme o protocolo for mapeado;
- modo de pesquisa que registra endpoints ainda desconhecidos;
- IAP real e anúncios deliberadamente desativados.

## Regra da loja Revival

Pacotes customizados **não aceitam preço em dinheiro real**. Se um pacote tiver `price`, `iap` ou `real_money`, o servidor o rejeita. Toda compra passa por `/game/store/purchase` e o custo deve ser uma moeda/recurso interno do jogo.

## Preparação

```bash
cd server
cp .env.example .env
cp config/revival.example.json config/revival.json
cp config/packs.example.json config/packs.json
cp config/events.example.json config/events.json
npm install
npm run check
npm start
```

O servidor abre em `0.0.0.0:8080`.

## Administração por terminal

O painel web em `/slayer` é a interface principal. Para operação local ou
automação, use o CLI sem dependências externas, sempre com o token exibido pelo
`scripts/install.sh`:

```bash
REVIVAL_ADMIN_TOKEN='seu-token' python3 scripts/revival_admin.py overview
REVIVAL_ADMIN_TOKEN='seu-token' python3 scripts/revival_admin.py users --query nome
REVIVAL_ADMIN_TOKEN='seu-token' python3 scripts/revival_admin.py reload
```

O CLI chama somente as rotas administrativas existentes; mudanças de loja e
eventos continuam gravadas nos arquivos runtime ignorados pelo Git.

## game-data.json

O cliente pede os dados do jogo ao servidor através de `/game/player/game-data-token` e depois `/data`. Por isso `server/data/game-data.json` é obrigatório para compatibilidade completa.

Esse arquivo **não é commitado**. Ele será obtido/validado durante a fase de preservação e colocado localmente em:

```text
server/data/game-data.json
```

Sem ele o servidor ainda inicia, permite desenvolver a camada Revival e informa `game_data_loaded: false` em `/revival/health`.

## Pacotes

Edite `config/packs.json`. Cada pacote tem ID próprio, custo em recursos do jogo e conteúdo. Referências podem ser IDs numéricos ou tags existentes no `game-data.json`.

Exemplo conceitual:

```json
{
  "id": 900100,
  "tag": "revival_weapon_pack",
  "active": true,
  "cost": [
    { "resource": "TAG_MOEDA", "kind": "currency", "amount": 5000 }
  ],
  "contents": [
    { "resource": "TAG_ARMA", "kind": "weapon", "level": 1, "tier": 1 }
  ]
}
```

Depois de editar, reinicie o processo ou faça:

```bash
curl -X POST http://127.0.0.1:8080/revival/reload \
  -H "Authorization: Bearer SEU_TOKEN_ADMIN"
```

## Eventos

`config/events.json` permite ativar eventos indefinidamente (`always: true`) ou por janela de tempo. O campo `args` é codificado em Base64/JSON exatamente no momento de responder `/game/events/get-schedule`.

Conforme capturarmos as definições originais de cada temporada/evento, elas poderão ser cadastradas aqui e reativadas quando quisermos.

## Pesquisa de endpoints

Com `RESEARCH_MODE=true`, uma chamada POST ainda não implementada recebe resposta base de sucesso e é registrada na tabela `request_log`. Isso permite observar a sequência de chamadas do cliente e ir substituindo fallbacks por implementações fiéis.

Para um ambiente estável, depois do mapeamento, use:

```env
RESEARCH_MODE=false
```

## HTTPS

Em produção/LAN, coloque Nginx ou Caddy na frente da porta 8080. O APK será patchado para apontar para o hostname escolhido pelo usuário. O TLS e a CA do APK serão tratados pelo patcher do repositório.

Em uma VPS Ubuntu, [`scripts/install.sh`](../scripts/install.sh) faz isso automaticamente (Caddy + Let's Encrypt + systemd). Veja a seção "Deploy em produção (VPS Ubuntu)" no [README principal](../README.md).
