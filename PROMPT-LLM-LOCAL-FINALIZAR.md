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

Pacotes personalizados devem usar apenas moedas/recursos internos do jogo. Conteúdo que originalmente era vendido pode ser disponibilizado usando economia interna do jogo.

---

# 4. Estado atual conhecido

Antes de alterar qualquer coisa, confirme tudo diretamente no repositório e rode os testes.

Stack principal do backend:

```text
Node.js 24+
Koa
SQLite / better-sqlite3
```

Diretório principal:

```text
server/
```

Já existem bases para autenticação local, login por device, SQLite persistente, player data, game-data-token, inventário, moedas, energia, slots, starter bundle, sessão, settings, loja Revival, packs configuráveis, compra transacional usando moeda interna, quotas, scheduler de eventos, estado de eventos por jogador, capítulos básicos, `RESEARCH_MODE`, bloqueio de IAP e Docker.

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

Local esperado:

```text
server/data/game-data.json
```

Existe:

```text
scripts/fetch-community-gamedata.py
```

O snapshot comunitário é bootstrap/referência; o comportamento real do APK 1.13.1 tem prioridade.

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

O starter bundle deve conceder recursos iniciais e equipar `slot_primary_weapon` e `slot_slayer`. Valide contra o GameData real.

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
| xbox/msal | substituir/remover quando não necessário |
| IAP real | manter desativado |
| ads externos | manter desativados ou converter em recompensa local |

---

# 7. Prioridade máxima: conectar o APK REAL

Não desperdice horas implementando endpoints hipotéticos antes de fazer o cliente real conversar com o servidor.

Prioridade:

```text
APK oficial
   -> patch
   -> instalação
   -> abre
   -> HTTPS
   -> /game/auth/register
   -> login
   -> game-data
   -> user-data
   -> menu
   -> primeiro capítulo
```

Quando o cliente alcançar o servidor, registre a sequência de chamadas e implemente exatamente o que ele pedir.

---

# 8. Downloader / analisador

```text
scripts/fetch-uptodown-apk.py
scripts/analyze_apk.py
scripts/analyze-official-apk.bat
```

O downloader deve baixar 1.13.1, calcular SHA-256, recusar hash diferente, deixar o APK somente local e nunca adicioná-lo ao Git.

Procure no APK real:

```text
slayersclub.bethesda.net
```

e quaisquer outros endpoints de backend.

---

# 9. Patcher APK

```text
scripts/patch-apk.bat
scripts/patch_apk.py
docs/APK-PATCH.md
```

Objetivo UX: executar `patch-apk.bat`, informar APK + servidor e gerar `output/mighty-doom-revival.apk` pronto para instalar.

Pipeline:

```text
APK original -> apktool -> endpoint -> network_security_config -> TLS/CA -> rebuild -> zipalign -> apksigner -> APK Revival
```

Host original:

```text
slayersclub.bethesda.net
```

Uma alternativa de mesmo comprimento já identificada:

```text
d.debruinsistemas.com.br
```

Se isso permitir patch binário confiável do bundle sem reserialização, use para obter o primeiro APK funcional rapidamente. Depois implemente hostname arbitrário corretamente.

**Não corrompa Unity bundle fazendo substituição de tamanho diferente sem reconstrução adequada.**

---

# 10. TLS

Priorizar domínio com certificado público válido (Let's Encrypt) para reduzir problemas com CA customizada em Android moderno.

```text
Android -> HTTPS público válido -> Nginx/Caddy -> 127.0.0.1:8080 -> Revival Server
```

Não considerar pronto apenas porque curl funciona: validar em Android real/emulador.

---

# 11. Módulos a finalizar

## Chapters

Completar/validar start, update, revive, end, capítulo/estágio/checkpoint, vitória/derrota, revives, energia, stats, XP, moedas, drops, stage rewards, chapter rewards, challenges, desbloqueio do capítulo seguinte e persistência.

## Inventory / Gear / Slayer

Finalizar equip/unequip/slot/upgrade/multi-upgrade/tier/level/weapon/equipment/launcher/ultimate/Slayer/cosmetic/entitlement. Tudo persistente em SQLite.

## Talents

Árvore, estado, custos, compra, upgrade, requisitos e persistência.

## Quests

Lista, progresso, stats, claims, daily/weekly, rotação, rewards e persistência.

## Daily Rewards

State, eligibility, claim, next reward, streak, reset, grants e persistência.

## Idle Rewards

Timestamp, tempo offline, limite, cálculo, claim, boost local/gratuito e persistência.

## Inbox

Mensagens, rewards, claim, claim-all, expiration e read state.

## Reward Tracks

Definição, progresso, níveis, rewards, claim e persistência.

## Eventos

Reativar eventos antigos, criar rotações, always-on, início/fim, progresso por usuário e rewards sem depender da Bethesda.

## Battle Pass

Temporadas antigas, temporada ativa, tiers, XP/pontos, missões, stats, free track, premium liberado localmente, rewards, claims, anti-duplicação, persistência, troca e reativação de temporadas. Nenhum pagamento real.

---

# 12. Loja Revival

`server/config/packs.json`

Permitir packs comprados apenas com currencies do jogo. Testar saldo suficiente/insuficiente, atomicidade, quotas diária/semanal/lifetime, restart, duplicados, cosméticos, Slayer, weapon, gear, moedas e energia.

---

# 13. RESEARCH_MODE

Enquanto cliente real estiver sendo analisado:

```env
RESEARCH_MODE=true
```

Registrar endpoint, método, body, headers relevantes, ordem, user e timestamp. Não deixar fallback genérico mascarar bugs. Cada endpoint observado deve virar implementação explícita.

Quando compatibilidade estiver validada:

```env
RESEARCH_MODE=false
```

Nenhum fluxo normal do cliente pode cair no fallback.

---

# 14. Testes obrigatórios

Criar testes automatizados para auth, login, starter bundle, GameData, inventory, equip, chapters, currency, energy regen, store, packs, quotas, events, battle pass, daily rewards, idle rewards, quests, talents, persistence, restart, IAP bloqueado e endpoints desconhecidos.

Também fazer smoke test HTTP real levantando o servidor.

Teste de persistência obrigatório: criar usuário, progredir, comprar, equipar, avançar evento/battle pass, reiniciar servidor e confirmar tudo após novo login.

---

# 15. Definition of Done mínima de gameplay

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

---

# 16. Definition of Done FINAL

Não diga `100%` até:

```text
[ ] Server instala em máquina limpa
[ ] Server inicia por script/comando simples
[ ] SQLite funciona
[ ] GameData carrega
[ ] Patcher funciona em Windows
[ ] Downloader funciona
[ ] SHA do APK é validado
[ ] Host do servidor é patchado
[ ] TLS funciona em Android
[ ] APK instala e abre
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

# 17. Modo de trabalho obrigatório da LLM

Não responda apenas `analisei`, `faltam X coisas`, `recomendo fazer` ou `próximo passo`.

Faça:

```text
analisar -> alterar arquivos -> executar comandos -> executar testes -> observar falhas -> corrigir -> testar novamente -> commit -> continuar
```

Ataque sempre o bloqueio mais próximo de impedir:

```text
SERVER -> PATCHER -> APK -> LOGIN -> GAMEPLAY
```

Não fique polindo documentação enquanto o jogo ainda não conecta.

---

# 18. Primeiro ciclo obrigatório

Comece imediatamente:

```text
1. git status
2. git log --oneline -20
3. ler README + ROADMAP + ENDPOINT-MATRIX + APK-PATCH
4. listar server/src, testes, scripts e configs
5. instalar dependências
6. rodar todos os testes existentes
7. subir servidor local
8. executar smoke test
9. baixar/analisar APK oficial
10. atacar primeiro bloqueio real de conexão APK -> servidor
```

**Não espere nova autorização para corrigir arquivos do projeto.**

Prioridade absoluta:

```text
Servidor Revival rodando + APK oficial validado + Patcher funcionando + APK instalado + Cliente conectado + Gameplay
```

Depois complete todas as funcionalidades até a matriz chegar a 100%.

**Faça acontecer.**
