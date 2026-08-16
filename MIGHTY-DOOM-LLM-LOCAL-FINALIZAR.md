# MISSÃO FINAL — Mighty DOOM Revival

## Objetivo principal

Você está trabalhando no repositório:

`testesvibecodeing/mighty-doom-revival`

Sua missão é **analisar o estado real do repositório e FINALIZAR o projeto**, não apenas revisar, sugerir ou gerar relatórios.

O objetivo final é permitir que o usuário faça, no Windows:

1. subir o servidor Revival;
2. baixar/usar o APK oficial do Mighty DOOM 1.13.1;
3. executar o patcher;
4. informar o domínio/servidor;
5. gerar um APK assinado e instalável;
6. instalar no Android;
7. abrir o Mighty DOOM;
8. conectar no Revival Server;
9. jogar normalmente;
10. acessar progressão, capítulos, inventário, armas, gear, Slayer, talentos, quests, recompensas, loja, eventos e battle pass;
11. manter progresso persistente;
12. permitir que conteúdo originalmente ligado a IAP seja obtido apenas com moedas/recursos internos do jogo.

**Não pare em análise. Faça alterações no código, rode testes, corrija erros e continue até o caminho fim-a-fim funcionar.**

---

# 1. Cliente alvo

Mighty DOOM Android:

- Package: `com.bethsoft.ubu`
- Versão: `1.13.1`
- Build: `84862`
- Engine: Unity `2021.3.25f1`
- Build: IL2CPP
- ABI: ARM64
- API observada: HTTPS + JSON
- Header de API: `x-ubu-apiversion: 24.0.0`
- SHA-256 esperado do APK alvo:

```text
519bfbb18c5bbab78f450b549777774e7d0ed78cd8b42cc25c7a2d3167669f35
```

Página usada para obtenção do APK:

```text
https://mighty-doom.br.uptodown.com/android/download
```

O repositório já possui scripts para baixar/analisar o APK.

**Nunca commit o APK, assets proprietários, dumps completos de IL2CPP ou conteúdo descompilado proprietário.**

---

# 2. Resultado esperado

O projeto só deve ser considerado finalizado quando existir um fluxo real semelhante a:

```text
Mighty DOOM 1.13.1
        |
        | HTTPS
        v
Mighty DOOM Revival Server
        |
        +-- auth local
        +-- player data
        +-- inventory
        +-- chapters
        +-- progression
        +-- slayers
        +-- weapons
        +-- gear
        +-- launchers
        +-- ultimates
        +-- talents
        +-- quests
        +-- daily rewards
        +-- idle rewards
        +-- inbox
        +-- reward tracks
        +-- store
        +-- events
        +-- battle pass
        +-- SQLite persistence
```

O cliente precisa realmente conseguir consumir essas rotas.

---

# 3. Regras obrigatórias

## Loja / monetização

Não usar dinheiro real.

O Revival Server deve rejeitar:

```text
price
iap
real_money
Google Play Billing
cartão
pagamento real
```

Pacotes personalizados devem usar apenas:

- coins;
- crystals;
- outras currencies do GameData;
- recursos internos do jogo;
- recompensas de gameplay;
- quests;
- eventos.

Conteúdo que originalmente era vendido pode ser disponibilizado usando economia interna do jogo.

---

# 4. Estado atual conhecido

Antes de alterar qualquer coisa, confirme tudo diretamente no repositório e rode os testes.

Já existe uma base relevante.

## Backend

Stack:

```text
Node.js 24+
Koa
SQLite / better-sqlite3
```

Diretório principal:

```text
server/
```

Já existem bases para:

- autenticação local;
- login por device;
- SQLite persistente;
- player data;
- game-data-token;
- inventário;
- moedas;
- energia;
- slots;
- starter bundle;
- sessão;
- settings;
- loja Revival;
- packs configuráveis;
- compra transacional usando moeda interna;
- quotas;
- scheduler de eventos;
- estado de eventos por jogador;
- capítulos básicos;
- `RESEARCH_MODE`;
- bloqueio de IAP;
- Docker.

Arquivos importantes:

```text
server/src/index.js
server/src/db.js
server/src/config.js
server/src/store.js
server/src/events.js
server/src/game-data-model.js
server/config/
server/data/
server/runtime/
```

---

# 5. GameData

O cliente depende do GameData.

Local esperado:

```text
server/data/game-data.json
```

Existe script:

```text
scripts/fetch-community-gamedata.py
```

Esse snapshot comunitário serve como bootstrap e referência, mas o comportamento real do APK 1.13.1 tem prioridade.

O servidor já tenta indexar recursos por:

```text
rid
id
tag
```

Categorias já modeladas:

| ID | Tipo |
|---:|---|
| 1 | currency |
| 2 | weapon |
| 3 | equipment |
| 4 | launcher |
| 5 | energy |
| 6 | ultimate |
| 7 | slayer |
| 8 | entitlement |
| 9 | cosmetic |

O starter bundle deve conceder recursos iniciais e equipar automaticamente:

```text
slot_primary_weapon
slot_slayer
```

Valide isso contra o GameData real.

---

# 6. Compatibilidade atual aproximada

**Não confie cegamente nesta tabela. Rode os testes e leia o código.**

| Módulo | Estado esperado |
|---|---|
| auth | base implementada |
| player | base implementada |
| inventory | base implementada |
| session | base implementada |
| store | base implementada |
| events | base implementada |
| chapters | parcialmente implementado |
| battle-pass | incompleto |
| daily-rewards | incompleto |
| idle-rewards | incompleto |
| inbox | incompleto |
| reward-tracks | incompleto |
| gear | incompleto |
| slayers | incompleto |
| talents | incompleto |
| quests | incompleto |
| tutorial | incompleto |
| identity | parcialmente implementado |
| xbox/msal | deve ser removido/substituído quando não necessário |
| IAP real | deve continuar desativado |
| ads externos | devem continuar desativados ou virar recompensa local |

---

# 7. Prioridade máxima: conectar o APK REAL

Não desperdice horas implementando endpoints hipotéticos antes de fazer o cliente real conversar com o servidor.

A prioridade é:

```text
APK oficial
   ->
patch
   ->
instalação
   ->
abre
   ->
HTTPS
   ->
/game/auth/register
   ->
login
   ->
game-data
   ->
user-data
   ->
menu
   ->
primeiro capítulo
```

Quando o cliente alcançar o servidor, registre a sequência de chamadas e implemente exatamente o que ele pedir.

---

# 8. Downloader / analisador

Scripts relevantes:

```text
scripts/fetch-uptodown-apk.py
scripts/analyze_apk.py
scripts/analyze-official-apk.bat
```

O downloader deve:

1. baixar a versão 1.13.1;
2. calcular SHA-256;
3. recusar o arquivo caso o hash seja diferente;
4. deixar o APK somente local;
5. nunca adicioná-lo ao Git.

Rode a análise real do APK.

Procure:

```text
slayersclub.bethesda.net
```

e qualquer outro endpoint de backend.

---

# 9. Patcher APK

Arquivos:

```text
scripts/patch-apk.bat
scripts/patch_apk.py
docs/APK-PATCH.md
```

Objetivo UX:

```text
patch-apk.bat
```

Pergunta:

```text
APK:
Servidor:
```

e gera:

```text
output/mighty-doom-revival.apk
```

pronto para instalar.

Pipeline esperado:

```text
APK original
    |
apktool
    |
alteração endpoint
    |
network_security_config
    |
TLS/CA
    |
rebuild
    |
zipalign
    |
apksigner
    |
APK Revival
```

## Host original

```text
slayersclub.bethesda.net
```

Esse hostname possui 24 bytes.

Uma alternativa de mesmo comprimento já identificada é:

```text
d.debruinsistemas.com.br
```

também com 24 bytes.

Se isso permitir patch binário confiável do bundle sem reserialização, use essa rota para obter o primeiro APK funcional rapidamente.

Depois implemente hostname arbitrário de forma correta.

**Não corrompa Unity bundle fazendo substituição de tamanho diferente sem reconstrução adequada.**

---

# 10. TLS

O cliente precisa aceitar HTTPS do servidor Revival.

Priorizar domínio com certificado público válido, por exemplo Let's Encrypt, porque reduz os problemas com CA customizada em Android moderno.

Fluxo recomendado:

```text
Android
   |
HTTPS público válido
   |
Nginx/Caddy
   |
127.0.0.1:8080
   |
Revival Server
```

Validar em Android real/emulador.

Não considerar pronto apenas porque curl funciona.

---

# 11. Chapters

Já existe persistência básica esperada para:

```text
/chapters/start
/chapters/update
/chapters/revive
/chapters/end
```

Validar e completar:

- capítulo selecionado;
- estágio;
- checkpoint;
- run atual;
- vitória/derrota;
- revives;
- energia;
- stats;
- XP;
- moedas;
- drops;
- stage rewards;
- chapter rewards;
- challenges;
- desbloqueio do capítulo seguinte;
- persistência após reiniciar o servidor.

Não retornar recompensa fictícia vazia quando o formato real já puder ser determinado.

---

# 12. Inventory / Gear / Slayer

Finalizar operações usadas pelo cliente:

- equip;
- unequip;
- slot;
- upgrade;
- multi-upgrade;
- tier;
- level;
- weapon;
- equipment;
- launcher;
- ultimate;
- Slayer;
- cosmetic;
- entitlement.

Toda alteração deve persistir em SQLite.

---

# 13. Talents

Implementar:

- árvore disponível;
- estado por jogador;
- custos;
- compra;
- upgrade;
- requisitos;
- persistência;
- resposta compatível com UI.

Usar GameData para não hardcodar conteúdo quando possível.

---

# 14. Quests

Implementar:

- lista de quests;
- progresso;
- atualização por stats;
- claims;
- daily/weekly;
- rotação;
- rewards;
- persistência.

---

# 15. Daily Rewards

Implementar fluxo completo:

```text
state
eligibility
claim
next reward
streak
reset
reward grant
```

Persistente.

---

# 16. Idle Rewards

Implementar:

- timestamp;
- tempo offline;
- limite máximo;
- reward calculation;
- claim;
- boost apenas local/gratuito;
- persistência.

---

# 17. Inbox

Implementar suporte suficiente para:

- mensagens;
- rewards;
- claim;
- claim-all;
- expiration;
- read state.

---

# 18. Reward Tracks

Implementar:

- definição;
- progresso;
- níveis;
- rewards;
- claim;
- persistência.

---

# 19. Eventos

O projeto deve ser capaz de:

- reativar eventos antigos;
- criar rotação personalizada;
- manter eventos sempre ativos;
- configurar início/fim;
- manter progresso por usuário;
- entregar rewards;
- usar GameData preservado;
- não depender da Bethesda.

Arquivos:

```text
server/config/events.json
server/src/events.js
```

Mapear eventos preservados disponíveis.

---

# 20. Battle Pass

Este é um requisito importante.

Implementar e validar:

- temporadas antigas;
- temporada ativa;
- tiers;
- XP/pontos;
- missões;
- progresso via stats;
- free track;
- premium track liberado localmente;
- rewards;
- claim;
- proteção contra claim duplicado;
- persistência;
- troca de temporada;
- reativação de temporada vencida.

Nenhum premium pass deve exigir pagamento real.

---

# 21. Loja Revival

Arquivo:

```text
server/config/packs.json
```

Permitir criar packs como:

```json
{
  "id": 900100,
  "tag": "revival_weapon_pack",
  "active": true,
  "cost": [
    {
      "resource": "coins",
      "kind": "currency",
      "amount": 5000
    }
  ],
  "contents": [
    {
      "resource": "heavy_cannon",
      "kind": "weapon",
      "level": 1,
      "tier": 1
    }
  ]
}
```

Testar:

- saldo suficiente;
- saldo insuficiente;
- atomicidade;
- quota diária;
- quota semanal;
- quota lifetime;
- restart do servidor;
- itens duplicados;
- cosméticos;
- Slayer;
- weapon;
- gear;
- moedas;
- energia.

---

# 22. RESEARCH_MODE

Enquanto cliente real estiver sendo analisado:

```env
RESEARCH_MODE=true
```

Registrar:

- endpoint;
- método;
- body;
- headers relevantes;
- ordem;
- user;
- timestamp.

Mas **não deixe fallback genérico mascarar bugs**.

Cada endpoint observado deve virar implementação explícita.

Quando compatibilidade estiver validada:

```env
RESEARCH_MODE=false
```

e nenhum fluxo normal do cliente pode cair no fallback.

---

# 23. Testes obrigatórios

Não considerar uma função pronta sem teste.

Criar testes automatizados para:

- auth;
- login;
- starter bundle;
- GameData;
- inventory;
- equip;
- chapters;
- currency;
- energy regen;
- store;
- packs;
- quota;
- events;
- battle pass;
- daily rewards;
- idle rewards;
- quests;
- talents;
- persistence;
- restart;
- IAP bloqueado;
- endpoints desconhecidos.

Também fazer smoke test HTTP real levantando o servidor.

---

# 24. Teste de persistência

Obrigatório:

1. criar usuário;
2. jogar/progredir;
3. comprar item;
4. equipar;
5. progredir evento;
6. progredir battle pass;
7. parar servidor;
8. iniciar novamente;
9. autenticar;
10. verificar se absolutamente tudo continua.

---

# 25. Teste Android fim-a-fim

Definition of Done mínima para gameplay:

```text
[ ] APK 1.13.1 validado por SHA
[ ] APK patchado
[ ] APK assinado
[ ] APK instalado
[ ] jogo abre
[ ] TLS funciona
[ ] auth funciona
[ ] menu abre
[ ] inventário aparece
[ ] arma/Slayer aparecem
[ ] primeiro capítulo inicia
[ ] combate funciona
[ ] capítulo termina
[ ] progresso salva
[ ] fechar e abrir jogo mantém progresso
```

Depois validar todos os outros menus.

---

# 26. Definition of Done FINAL

Não diga "100%" até todos os itens abaixo serem verdadeiros.

```text
[ ] Server instala em máquina limpa
[ ] Server inicia com um único comando/script
[ ] SQLite funciona
[ ] GameData carrega
[ ] Patcher funciona em Windows
[ ] Downloader funciona
[ ] SHA do APK é validado
[ ] Host do servidor é patchado
[ ] TLS funciona em Android
[ ] APK instala
[ ] APK abre
[ ] Cliente conecta ao Revival
[ ] Auth completo
[ ] Player data completo
[ ] Inventory completo
[ ] Chapters completos
[ ] Progressão completa
[ ] Energy completo
[ ] Weapons completo
[ ] Gear completo
[ ] Slayer completo
[ ] Launchers completos
[ ] Ultimates completos
[ ] Talents completos
[ ] Quests completas
[ ] Daily Rewards completo
[ ] Idle Rewards completo
[ ] Inbox completo
[ ] Reward Tracks completos
[ ] Events completos
[ ] Battle Pass completo
[ ] Store Revival completa
[ ] Custom packs completos
[ ] Nenhum dinheiro real necessário
[ ] IAP real desativado
[ ] Persistência validada
[ ] RESEARCH_MODE=false sem endpoints normais faltando
[ ] Testes automatizados passam
[ ] Teste Android real/emulador passa
```

---

# 27. Modo de trabalho obrigatório da LLM

Você NÃO deve responder apenas:

```text
"Analisei o projeto."
"Faltam X coisas."
"Recomendo fazer..."
"Próximo passo..."
```

Você deve:

```text
analisar
-> alterar arquivos
-> executar comandos
-> executar testes
-> observar falhas
-> corrigir
-> testar novamente
-> commit
-> continuar
```

Sempre atacar o bloqueio mais próximo de impedir:

```text
SERVER -> PATCHER -> APK -> LOGIN -> GAMEPLAY
```

Não ficar polindo documentação enquanto o jogo ainda não conecta.

---

# 28. Git

Trabalhe diretamente no repositório existente.

Antes de começar:

```bash
git status
git log --oneline -20
```

Leia:

```text
README.md
docs/ROADMAP-100-PERCENT.md
docs/ENDPOINT-MATRIX.md
docs/APK-PATCH.md
server/README.md
```

Depois rode os testes atuais.

Faça commits pequenos e objetivos.

Exemplos:

```text
fix: patch Mighty DOOM backend hostname
feat: complete chapter rewards
feat: implement daily reward claims
feat: restore battle pass progression
fix: persist equipped inventory
test: add end-to-end revival server smoke test
```

---

# 29. Não destruir o que já funciona

Antes de reescrever módulos:

- leia implementação atual;
- rode testes;
- preserve compatibilidade;
- prefira completar ao invés de refazer do zero;
- não troque stack sem necessidade.

---

# 30. Referências do projeto

Projetos de referência conhecidos:

```text
dannyhpy/mightydoom-gameserver
CTRQuko/mightydoom-preservation
```

Use-os para entender protocolo/comportamento, mas mantenha o Revival como implementação independente e adequada ao projeto atual.

---

# 31. Primeiro comando da LLM

Ao receber este arquivo, comece imediatamente com:

```text
1. git status
2. git log --oneline -20
3. ler README + ROADMAP + ENDPOINT-MATRIX + APK-PATCH
4. listar server/src, server/test(s), scripts e configs
5. instalar dependências
6. rodar todos os testes existentes
7. subir o servidor local
8. executar smoke test
9. baixar/analisar APK oficial
10. atacar o primeiro bloqueio real de conexão APK -> servidor
```

**Não espere nova autorização para corrigir arquivos do projeto.**

---

# 32. Prioridade desta sessão

A prioridade absoluta é entregar um caminho fim-a-fim funcional:

```text
Servidor Revival rodando
        +
APK oficial validado
        +
Patcher funcionando
        +
APK instalado
        +
Cliente conectado
        +
Gameplay
```

Depois complete todas as funcionalidades até a matriz chegar a 100%.

**Faça acontecer.**
