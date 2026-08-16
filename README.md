# Mighty DOOM Revival

> ## ⚖️ AVISO LEGAL — LEIA ANTES DE USAR
>
> **Este é um projeto independente, não comercial, de preservação, pesquisa e interoperabilidade de software descontinuado.**
>
> Mighty DOOM, DOOM, Bethesda, ZeniMax, Microsoft, id Software, Alpha Dog Games, personagens, artes, músicas, logos e demais elementos relacionados pertencem aos seus respectivos titulares. **Este projeto não é oficial, não é afiliado, patrocinado ou endossado por qualquer desses titulares e não reivindica propriedade sobre o jogo ou suas marcas.**
>
> O repositório público deve conter somente código independente do servidor, ferramentas e documentação. **Não é permitido publicar aqui o APK oficial, APK patchado, assets do jogo, músicas, vídeos, código proprietário descompilado, dumps proprietários, credenciais ou conteúdo confidencial.** O usuário deve fornecer localmente sua própria cópia legitimamente obtida, e qualquer patch deve ser produzido localmente para uso do próprio usuário.
>
> O projeto adota como pilares: **preservação, interoperabilidade, clean-room, ausência de redistribuição do cliente, ausência de exploração comercial e ausência de falsa afiliação.**
>
> A legislação brasileira possui regras relevantes sobre cópia de salvaguarda e integração tecnicamente necessária de programas legitimamente adquiridos para uso exclusivo do usuário (Lei nº 9.609/1998, art. 6º, I e IV). Nos Estados Unidos, 17 U.S.C. § 117 e a atual 37 C.F.R. § 201.40 contêm limitações/exceções relevantes a programas e, em condições específicas, a jogos cujo suporte externo de servidor foi descontinuado. **Essas normas não são uma autorização irrestrita para redistribuição, operação comercial ou qualquer forma de servidor público.**
>
> **Os termos/EULA publicados pela ZeniMax/Bethesda também contêm restrições contratuais a engenharia reversa, modificação e emulação de serviço. Por isso, não afirmamos que exista imunidade jurídica automática ou que qualquer uso seja válido em toda jurisdição.** O projeto busca a postura técnica e operacional mais conservadora possível.
>
> ### 📚 [Leia a Política Legal de Preservação e a análise completa das leis, riscos, limites, DMCA, marcas e procedimento para titulares de direitos](docs/LEGAL-PRESERVATION.md)
>
> **Política de retorno do serviço oficial:** se o suporte oficial necessário ao gameplay voltar a funcionar de forma efetiva, ou se um representante verificável do titular solicitar análise/suspensão em razão da restauração oficial, novos releases de substituição serão suspensos e o acesso público ao projeto poderá ser arquivado ou tornado privado durante a avaliação. Consulte a política completa no documento legal acima.

---

## Sobre o projeto

Mighty DOOM Revival é um projeto pessoal de **preservação e interoperabilidade** do cliente Android de Mighty DOOM com um servidor independente/self-hosted.

O objetivo técnico é permitir que uma cópia fornecida localmente pelo próprio usuário possa conversar com uma implementação independente dos serviços que deixaram de existir, preservando os fluxos ainda presentes no cliente 1.13.1.

O projeto busca restaurar progressivamente:

- progressão e capítulos;
- inventário, armas, gear, launchers, ultimates e Slayers;
- quests, recompensas diárias/idle, inbox e reward tracks;
- eventos e temporadas/battle pass preserváveis;
- loja Revival configurável;
- pacotes adquiridos **somente com moedas/recursos internos do jogo**;
- persistência local/self-hosted;
- nenhuma compra com cartão, Google Play Billing ou dinheiro real no servidor Revival.

Documentação principal:

- [`docs/LEGAL-PRESERVATION.md`](docs/LEGAL-PRESERVATION.md) — política legal, preservação e direitos de terceiros;
- [`docs/ROADMAP-100-PERCENT.md`](docs/ROADMAP-100-PERCENT.md) — roadmap;
- [`docs/ENDPOINT-MATRIX.md`](docs/ENDPOINT-MATRIX.md) — matriz de compatibilidade;
- [`docs/APK-PATCH.md`](docs/APK-PATCH.md) — patcher;
- [`docs/SERVER.md`](docs/SERVER.md) — servidor;
- [`server/README.md`](server/README.md) — backend Revival.

## Cliente alvo

- Package: `com.bethsoft.ubu`
- Versão: **1.13.1 / build 84862**
- Engine: Unity 2021.3.25f1 / IL2CPP / ARM64
- API observada: HTTPS + JSON
- API version: `x-ubu-apiversion: 24.0.0`
- SHA-256 da cópia alvo estudada: `519bfbb18c5bbab78f450b549777774e7d0ed78cd8b42cc25c7a2d3167669f35`

## Estrutura

```text
mighty-doom-revival/
├── README.md
├── docs/
│   ├── LEGAL-PRESERVATION.md
│   ├── APK-PATCH.md
│   ├── SERVER.md
│   ├── ENDPOINT-MATRIX.md
│   └── ROADMAP-100-PERCENT.md
├── input/                  # arquivo local do usuário; ignorado pelo Git
├── output/                 # saída local; ignorada pelo Git
├── scripts/
│   ├── analyze_apk.py
│   ├── analyze-official-apk.bat / .sh
│   ├── patch_apk.py
│   ├── patch-apk.bat / .sh
│   ├── setup-patcher-tools.bat / .sh
│   ├── setup-server.bat / .sh
│   ├── start-server.bat / .sh
│   ├── install.sh
│   └── uninstall.sh
└── server/
    ├── src/
    ├── config/
    ├── data/               # dados locais; ignorados pelo Git
    └── runtime/            # SQLite; ignorado pelo Git
```

## 1. Regra de ouro: o cliente não pertence a este repositório

O repositório **não deve ser usado como fonte de distribuição do jogo**.

Para pesquisa/interoperabilidade, trabalhe somente com uma cópia que você possua legitimamente e mantenha-a localmente em:

```text
input/mighty-doom.apk
```

Arquivos `*.apk`, `*.xapk`, `*.apks` e diretórios de extração são bloqueados pelo `.gitignore`.

**Não publique o arquivo de entrada nem o APK gerado pelo patcher em GitHub Releases, Pages, site público, CDN ou outro espelho mantido por este projeto.**

## 2. Analisar uma cópia local

Windows:

```bat
scripts\analyze-official-apk.bat
```

Linux/Mac:

```bash
./scripts/analyze-official-apk.sh
```

Ou diretamente:

```bash
python scripts/analyze_apk.py input/mighty-doom.apk \
  --json-out reports/apk-1.13.1.json \
  --md-out reports/apk-1.13.1.md
```

O relatório deve conter apenas metadados úteis à interoperabilidade. Não commite assets ou código proprietário extraído.

## 3. Servidor Revival

A implementação principal está em `server/`.

### Windows

```bat
scripts\setup-server.bat
scripts\start-server.bat
```

### Linux/Mac

```bash
./scripts/setup-server.sh
./scripts/start-server.sh
```

### Manual

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

O servidor possui fundação para:

- autenticação local;
- SQLite;
- moedas e energia;
- inventário e slots;
- starter bundle;
- entrega de game data;
- loja configurável;
- compras por moeda interna;
- eventos e estado persistente;
- progressão;
- research mode para endpoints ainda não mapeados.

## 4. Deploy self-hosted

Para a postura jurídica mais conservadora, a recomendação do projeto é **self-hosted, pessoal, privado e não comercial**.

Em VPS Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/testesvibecodeing/mighty-doom-revival.git
cd mighty-doom-revival
sudo ./scripts/install.sh
```

Com domínio definido:

```bash
DOMAIN=d.seudominio.com.br sudo -E ./scripts/install.sh
```

O instalador prepara Node.js quando necessário, serviço systemd, reverse proxy compatível, HTTPS e health check.

Comandos úteis:

```bash
systemctl status mighty-doom-revival
journalctl -u mighty-doom-revival -f
```

Atualização:

```bash
cd mighty-doom-revival
git pull
sudo ./scripts/install.sh
```

Desinstalação:

```bash
sudo ./scripts/uninstall.sh
```

> **Importante:** qualquer recurso de upload/local transfer existente no projeto deve ser usado somente em ambiente privado/controlado. A política pública do projeto proíbe transformar o site/repositório em distribuidor do APK proprietário ou de uma cópia modificada dele.

## 5. Game data

O servidor pode depender de dados de jogo esperados pelo cliente em:

```text
server/data/game-data.json
```

Esse conteúdo permanece local e fora do Git.

O backend indexa recursos por `rid/id` e `tag`, permitindo trabalhar com moedas, armas, equipamentos, launchers, energia, ultimates, Slayers, entitlements e cosméticos sem espalhar hardcodes desnecessários.

O material usado para pesquisa deve ser limitado ao necessário para interoperabilidade e não deve transformar este repositório em espelho de conteúdo proprietário.

## 6. Loja Revival — sem dinheiro real

Pacotes ficam na configuração local do servidor.

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

O backend rejeita configuração de pacote com `price`, `iap` ou `real_money`.

A política do projeto é clara:

- sem venda de APK;
- sem assinatura para jogar;
- sem Google Play Billing;
- sem venda de moedas por dinheiro real;
- sem venda de itens por dinheiro real;
- sem acesso pago a conteúdo protegido.

## 7. Eventos e Battle Pass

O servidor possui estrutura para:

- evento sempre ativo;
- janelas de início/fim;
- estado por jogador;
- game mode/store offer/battle pass;
- reativação de conteúdo preservável;
- rotação própria em ambiente self-hosted.

Tudo deve permanecer independente de serviços oficiais e sem exploração comercial de conteúdo de terceiros.

## 8. Patch local do APK

### Windows

```bat
scripts\patch-apk.bat
```

### Linux/Mac

```bash
./scripts/patch-apk.sh
```

O patcher trabalha sobre **arquivo fornecido pelo próprio usuário** e gera a saída localmente.

O fluxo de design do projeto é:

```text
cópia legítima do usuário
        ↓
patch local de interoperabilidade
        ↓
cópia modificada mantida pelo próprio usuário
        ↓
servidor independente/self-hosted
```

E não:

```text
repositório/site público
        ↓
download de APK proprietário modificado
```

Consulte [`docs/APK-PATCH.md`](docs/APK-PATCH.md).

## 9. Clean-room e pesquisa

Contribuições ao servidor devem ser código original do projeto.

Não envie pull requests contendo:

- trechos copiados de código proprietário;
- assets do cliente;
- código descompilado integral;
- segredos comerciais;
- credenciais;
- dados privados;
- arquivos obtidos por vazamento.

O comportamento externo necessário à compatibilidade pode ser documentado e reimplementado com código próprio, dentro dos limites jurídicos aplicáveis.

## 10. Marcas e identidade visual

O nome `Mighty DOOM` é usado somente para identificar o software alvo da preservação/interoperabilidade.

Não use este projeto para:

- fingir ser site oficial;
- se passar pela Bethesda/ZeniMax/Microsoft/id/Alpha Dog;
- vender serviços usando marcas de terceiros;
- remover avisos de titularidade;
- criar falsa impressão de patrocínio ou endosso.

Prefira uma identidade gráfica própria para `Revival` e mantenha a não afiliação visível.

## 11. Contato de titulares e retorno do serviço oficial

Se você representa de forma verificável um titular de direitos e acredita que material deste repositório excede sua finalidade declarada, entre em contato com o mantenedor pelo GitHub ou utilize os canais oficiais de remoção da plataforma.

O mantenedor analisará prontamente a solicitação e suspenderá material contestado quando apropriado durante a avaliação.

Se o serviço oficial necessário ao gameplay for efetivamente restaurado, o projeto suspenderá novos releases de substituição e revisará a necessidade de continuar público. O repositório poderá ser **arquivado ou tornado privado** conforme descrito em [`docs/LEGAL-PRESERVATION.md`](docs/LEGAL-PRESERVATION.md).

## 12. Segurança do repositório

O `.gitignore` deve bloquear:

- APK/XAPK/APKS/AAB;
- dumps;
- conteúdo descompilado;
- game data local;
- SQLite;
- certificados e chaves privadas;
- tokens;
- configs locais com segredos.

Antes de tornar um fork público, consulte o checklist jurídico completo em [`docs/LEGAL-PRESERVATION.md`](docs/LEGAL-PRESERVATION.md).

## Referências técnicas

- `dannyhpy/mightydoom-gameserver` — referência comunitária de protocolo;
- `CTRQuko/mightydoom-preservation` — pesquisa comunitária de preservação.

## Referências legais oficiais

A análise detalhada, links oficiais e limitações estão em:

### **[`docs/LEGAL-PRESERVATION.md`](docs/LEGAL-PRESERVATION.md)**

Entre as fontes oficiais documentadas estão:

- Lei nº 9.609/1998 — Software;
- Lei nº 9.610/1998 — Direitos Autorais;
- Lei nº 9.279/1996 — Marcas/Propriedade Industrial;
- 17 U.S.C. § 117;
- U.S. Copyright Office — Section 1201 / 37 C.F.R. § 201.40;
- GitHub DMCA/Trademark/Acceptable Use Policies;
- Mobile EULA e Terms of Service publicados pela ZeniMax/Bethesda.

## Status técnico

Consulte a fonte atualizada:

- [`docs/ROADMAP-100-PERCENT.md`](docs/ROADMAP-100-PERCENT.md)
- [`docs/ENDPOINT-MATRIX.md`](docs/ENDPOINT-MATRIX.md)

---

### Nota final

**Jogo descontinuado não significa domínio público.** A defesa deste projeto não se baseia em chamar o software de `abandonware`, mas em manter uma arquitetura de preservação/interoperabilidade cuidadosamente limitada: código independente, cópia local do próprio usuário, patch local, ausência de redistribuição, ausência de monetização e respeito explícito aos titulares.
