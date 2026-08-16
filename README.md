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
│   ├── analyze-official-apk.bat / .sh
│   ├── patch_apk.py
│   ├── patch-apk.bat / .sh
│   ├── setup-patcher-tools.bat / .sh
│   ├── setup-server.bat / .sh
│   ├── start-server.bat / .sh
│   ├── install.sh          # instalador completo para VPS Ubuntu/Debian
│   └── uninstall.sh        # desinstalador (remove só o que é deste projeto)
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

No Linux/Mac, o equivalente é:

```bash
./scripts/analyze-official-apk.sh
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

No Linux/Mac:

```bash
./scripts/setup-server.sh
./scripts/start-server.sh
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

## 3b. Deploy em produção (VPS Ubuntu)

Como este repositório é público, a forma recomendada de colocar o Revival Server no ar é uma VPS Ubuntu com HTTPS de verdade, usando o instalador [`scripts/install.sh`](scripts/install.sh). Ele é idempotente (pode rodar de novo a cada `git pull`) e faz tudo sozinho:

- instala Node.js 24 LTS (precisa de `node:sqlite`) e o Caddy, se ainda não existirem;
- prepara `server/.env` e os `config/*.json` a partir dos `.example`;
- roda a suíte de testes do servidor como gate de deploy (aborta se algo quebrar);
- sobe o servidor como serviço `systemd` (reinício automático);
- configura o Caddy como reverse proxy com HTTPS automático via Let's Encrypt para o domínio informado;
- valida `http://127.0.0.1:8080/revival/health` e depois `https://SEU_DOMINIO/revival/health` antes de terminar.

**Seguro para VPS compartilhada com outros projetos:** se Node.js e/ou Caddy já estiverem instalados (por exemplo, por outro projeto na mesma VPS), o instalador nunca os reinstala nem passa a "possuí-los". Ele também nunca sobrescreve `/etc/caddy/Caddyfile` — só acrescenta a linha `import` (se ainda não houver) e escreve o domínio deste projeto em um arquivo próprio dentro de `/etc/caddy/conf.d/`, sem tocar em blocos de outros domínios. Cada decisão sobre o que pertence a este projeto é registrada permanentemente em `deploy/.install-state` (local, não versionado) e documentada com o prefixo `[OWNERSHIP]` em `deploy/logs/install-<timestamp>.log`, incluindo um resumo de propriedade ao final da execução.

Pré-requisitos:

- VPS Ubuntu 22.04+ (ou Debian) com acesso root/sudo;
- um domínio/subdomínio com registro DNS `A` apontando para o IP público da VPS;
- portas `80` e `443` liberadas no firewall do provedor (security group) além do `ufw`.

Instalação (primeira vez):

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/testesvibecodeing/mighty-doom-revival.git
cd mighty-doom-revival
sudo ./scripts/install.sh
```

O script pergunta o domínio HTTPS (ex: `d.seudominio.com.br`). Para rodar sem prompt interativo, informe-o antes:

```bash
DOMAIN=d.seudominio.com.br sudo -E ./scripts/install.sh
```

Ao final ele imprime o `REVIVAL_ADMIN_TOKEN` gerado (guarde-o — autoriza `POST /revival/reload`) e os comandos úteis para inspecionar os serviços:

```bash
systemctl status mighty-doom-revival
systemctl status caddy
journalctl -u mighty-doom-revival -f
```

Atualizar o servidor em produção depois de mudanças no código:

```bash
cd mighty-doom-revival
git pull
sudo ./scripts/install.sh
```

Se `server/data/game-data.json` ainda não existir na VPS, o serviço sobe mesmo assim (`game_data_loaded: false`); depois de colocar o arquivo real, reinicie:

```bash
sudo systemctl restart mighty-doom-revival
```

Por fim, use o domínio configurado (`https://d.seudominio.com.br`) em `scripts\patch-apk.bat`, no Windows, para gerar o APK apontando para o seu Revival Server.

### Desinstalar

Para remover o Revival Server desta VPS, use o par do instalador: [`scripts/uninstall.sh`](scripts/uninstall.sh). Ele só remove o que pertence a este projeto (o serviço `systemd` e o site próprio do Caddy em `/etc/caddy/conf.d/mighty-doom-revival.caddy`); nunca apaga `/etc/caddy/Caddyfile` nem blocos de outros domínios/projetos que já estejam nele.

```bash
sudo ./scripts/uninstall.sh
```

Ele mostra e pede confirmação antes de remover (use `-y`/`--yes` para pular o prompt em automação). Por padrão **preserva** Node.js, Caddy e os arquivos locais (`server/.env`, `server/config/*.json`, `server/data/`, `server/runtime/`), mesmo que este instalador os tenha criado. Duas flags opcionais liberam uma limpeza mais completa, sempre respeitando o que é (ou não) deste projeto:

```bash
# Também remove Node.js/Caddy via apt, mas SÓ os que scripts/install.sh
# registrou como instalados por ele (deploy/.install-state). Se já existiam
# antes deste projeto, ou se há outros sites em /etc/caddy/conf.d/ além do
# nosso, ficam preservados mesmo com esta flag.
sudo ./scripts/uninstall.sh --purge-packages

# Também apaga server/.env, server/config/*.json, server/data/ e
# server/runtime/ (inclui o banco SQLite com progresso de jogadores).
sudo ./scripts/uninstall.sh --purge-data
```

Toda a execução (o que foi removido e o que foi preservado, e por quê) fica registrada em `deploy/logs/uninstall-<timestamp>.log`.

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

No Linux/Mac:

```bash
./scripts/patch-apk.sh
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
