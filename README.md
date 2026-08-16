# Mighty DOOM Revival

Projeto pessoal de **preservação e interoperabilidade** do cliente Android de Mighty DOOM com um servidor independente/self-hosted.

> **Não afiliado à Bethesda, ZeniMax, Microsoft, id Software ou Alpha Dog Games.**
>
> Este repositório **não distribui o APK oficial, assets, código descompilado ou outros arquivos proprietários do jogo**. O APK e os dados necessários à interoperabilidade permanecem locais/efêmeros.

## Objetivo

Fazer o cliente final do Mighty DOOM voltar a funcionar com uma infraestrutura controlada pelo usuário e, progressivamente, recuperar todos os fluxos ainda presentes no cliente 1.13.1:

- progressão, capítulos, inventário, armas, gear e slayers;
- quests, recompensas diárias/idle, inbox e reward tracks;
- eventos e temporadas/battle pass que possam ser reconstruídos a partir dos dados preservados;
- loja Revival configurável;
- pacotes personalizados adquiridos **somente com moedas/recursos internos do jogo**;
- nenhuma compra com cartão, Google Play Billing ou dinheiro real no servidor Revival.

Acompanhe o trabalho em [`docs/ROADMAP-100-PERCENT.md`](docs/ROADMAP-100-PERCENT.md) e [`docs/ENDPOINT-MATRIX.md`](docs/ENDPOINT-MATRIX.md).

## Cliente alvo

- Package: `com.bethsoft.ubu`
- Versão: **1.13.1 / build 84862**
- Engine: Unity 2021.3.25f1 / IL2CPP / ARM64
- API observada: HTTPS + JSON
- API version: `x-ubu-apiversion: 24.0.0`
- SHA-256 da cópia alvo do APK: `519bfbb18c5bbab78f450b549777774e7d0ed78cd8b42cc25c7a2d3167669f35`

## Estrutura

```text
mighty-doom-revival/
├── .github/workflows/
│   ├── analyze-official-apk.yml
│   └── server-ci.yml
├── docs/
│   ├── APK-PATCH.md
│   ├── SERVER.md
│   ├── ENDPOINT-MATRIX.md
│   └── ROADMAP-100-PERCENT.md
├── input/                  # APK local; ignorado pelo Git
├── output/                 # APK patchado; ignorado pelo Git
├── scripts/
│   ├── fetch-uptodown-apk.py
│   ├── fetch-community-gamedata.py
│   ├── analyze_apk.py
│   ├── analyze-official-apk.bat
│   ├── patch_apk.py
│   └── patch-apk.bat
└── server/
    ├── src/                # servidor Revival próprio
    ├── config/             # packs, eventos e configuração
    ├── data/               # game-data local; ignorado pelo Git
    └── runtime/            # SQLite; ignorado pelo Git
```

## 1. Obter e validar o APK

Quem já possui a cópia pode colocá-la em:

```text
input/mighty-doom.apk
```

Para reproduzir a pesquisa a partir da página informada da Uptodown, existe um downloader local que resolve o fluxo atual do site e **recusa o arquivo se o SHA-256 não corresponder ao alvo**:

```bash
python scripts/fetch-uptodown-apk.py --output input/mighty-doom.apk
```

No Windows também existe o fluxo em um clique:

```bat
scripts\analyze-official-apk.bat
```

O APK nunca é adicionado ao Git. O workflow de análise também apaga o binário antes de publicar qualquer artifact.

## 2. Analisar o APK

```bash
python scripts/analyze_apk.py input/mighty-doom.apk \
  --json-out reports/apk-1.13.1.json \
  --md-out reports/apk-1.13.1.md
```

O relatório é sanitizado e contém apenas metadados úteis à interoperabilidade: hash, estrutura Unity/IL2CPP, Addressables e offsets de strings de endpoint conhecidas. Assets e código proprietário não são exportados.

## 3. Servidor Revival próprio

A implementação principal está em `server/`. A implementação comunitária `dannyhpy/mightydoom-gameserver` continua sendo referência importante de protocolo, mas não é necessária como runtime do projeto.

No Windows:

```bat
scripts\setup-server.bat
```

Ou manualmente:

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

Health check:

```text
GET http://127.0.0.1:8080/revival/health
```

O servidor já tem base para autenticação local, SQLite, categorias de recursos, moedas/energia, inventário/slots, starter bundle, entrega de game data, loja configurável, compras por moeda interna, agenda de eventos e estado persistente. Endpoints ainda desconhecidos podem ser registrados pelo `RESEARCH_MODE` durante a fase de compatibilidade.

Veja [`server/README.md`](server/README.md).

## 4. Game data

A compatibilidade completa depende dos dados que o cliente espera receber de `/game/player/game-data-token` + `/data`.

O arquivo local esperado é:

```text
server/data/game-data.json
```

Ele não é commitado. O servidor indexa recursos por `rid/id` e `tag` e reconhece moedas, armas, equipamentos, launchers, energia, ultimates, slayers, entitlements e cosméticos.

Existe um **snapshot comunitário público** de GameData que pode ser usado apenas como bootstrap/comparação enquanto validamos a cópia final contra o cliente 1.13.1. Para importá-lo localmente:

```bash
python scripts/fetch-community-gamedata.py
```

O script valida a estrutura JSON, mostra o SHA-256 e contagens das coleções, mas mantém o arquivo em `server/data/`, fora do Git. A fonte comunitária não é tratada como oficial: qualquer divergência será resolvida a favor do comportamento observado no APK alvo.

Quando o game data possui o bundle `starter`, o registro do Revival pode conceder os recursos dele e equipar automaticamente os slots `slot_primary_weapon` e `slot_slayer`, sem hardcode de IDs.

## 5. Loja Revival: sem dinheiro real

Pacotes ficam em `server/config/packs.json`.

Exemplo conceitual:

```json
{
  "id": 900100,
  "tag": "revival_weapon_pack",
  "active": true,
  "cost": [
    { "resource": "coins", "kind": "currency", "amount": 5000 }
  ],
  "contents": [
    { "resource": "heavy_cannon", "kind": "weapon", "level": 1, "tier": 1 }
  ]
}
```

O backend rejeita configuração de pacote com `price`, `iap` ou `real_money`. A compra debita moedas internas de forma transacional e pode conceder moedas, energia, armas, gear, launchers, ultimates, slayers, entitlements ou cosméticos. As rotas de IAP real ficam deliberadamente desativadas.

## 6. Eventos e battle pass

`server/config/events.json` suporta:

- evento sempre ativo;
- janela de início/fim;
- estado independente por jogador;
- canais de game mode, store offer e battle pass;
- `args` serializados para o formato esperado pela agenda do cliente.

A estrutura está pronta para receber as definições reais conforme forem identificadas no APK/game data. Isso permitirá reativar eventos preservados e também montar rotações próprias sem depender dos servidores oficiais.

A parte de **claim de missões, tiers, temporadas e progressão completa de battle pass ainda precisa ser validada e implementada** antes de considerarmos esse módulo compatível.

## 7. Patch do APK

No Windows:

```bat
scripts\patch-apk.bat
```

O patcher atual desmonta, ajusta configuração de rede/TLS, recompila, alinha e assina uma cópia local. A alteração do hostname dentro do Unity Addressables ainda está limitada até identificarmos e reserializarmos corretamente o objeto do bundle no APK alvo.

A próxima etapa técnica após a análise real é remover essa limitação e aceitar qualquer hostname HTTPS sem corromper o bundle.

Veja [`docs/APK-PATCH.md`](docs/APK-PATCH.md).

## 8. Docker

A base também inclui `server/Dockerfile` e `docker-compose.yml` para o backend. Os dados SQLite, configs locais e `game-data.json` ficam fora do Git.

## Segurança do repositório

O `.gitignore` bloqueia APK/XAPK/APKS/AAB, dumps, conteúdo descompilado, game data local, banco SQLite, chaves privadas, certificados pessoais e configs locais.

## Referências técnicas

- `dannyhpy/mightydoom-gameserver` — implementação comunitária usada como referência de protocolo
- `CTRQuko/mightydoom-preservation` — pesquisa comunitária de preservação
- `OyunErbabi/GameData.json` — snapshot comunitário opcional para comparação/bootstrapping
- Obtainium — referência para o fluxo atual de download da Uptodown

## Status

- [x] downloader local com validação SHA-256
- [x] análise estática sanitizada
- [x] patcher Windows inicial
- [x] servidor Revival próprio
- [x] SQLite/persistência
- [x] categorias de recursos + starter bundle
- [x] base de loja somente com moeda interna
- [x] base de eventos/battle pass
- [x] importador opcional de GameData comunitário
- [x] IAP real desativado
- [x] Docker/base de deploy
- [ ] executar análise do APK alvo em ambiente com runner disponível
- [ ] patch bundle-aware de hostname arbitrário
- [ ] conectar o APK ao servidor Revival
- [ ] validar GameData contra o cliente 1.13.1
- [ ] mapear schemas reais endpoint por endpoint
- [ ] restaurar capítulos/progressão completa
- [ ] restaurar eventos/battle passes disponíveis
- [ ] validar 100% dos fluxos acessíveis no cliente 1.13.1
