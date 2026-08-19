# Relatório de status — Mighty DOOM Revival

Data: 2026-08-16 · main @ `d855299` · VPS sincronizada e ativa

## Resumo em uma linha

O caminho completo **APK patcheado → servidor Revival → jogo jogando** está
validado de ponta a ponta em emulador Android: conta criada pelo próprio
cliente, login, menu com eventos do servidor e uma partida completa do
estágio 1-1 (vitória, recompensas, desbloqueio do 1-2).

---

## ✅ O que foi feito

### 1. Patcher do APK (end-to-end no APK real 1.13.1)

- Endpoint da API localizado: **dentro de bundles Addressables comprimidos em
  LZ4** (campo `baseUrl` do `ProdGameServer`), não como ASCII no
  `global-metadata.dat` — scan cru de ZIP não vê; a UnityPy decodifica e
  resserializa.
- Patch direto (mesmo comprimento, com padding de userinfo para hostnames
  curtos) + fallback **bundle-aware** com `--sweep-all-bundles`:
  typetree → raw-string (só com prova estrutural) → verificação de zero
  bytes oficiais restantes.
- **Zeramento do `m_Crc` do catálogo Addressables** (`zero_catalog_crc`):
  sem isso a Unity recusa o bundle alterado (`CRC Mismatch` →
  `RemoteProviderException` "Invalid path") e o jogo derruba o load de cena.
  O zero é feito com substituição de mesmo comprimento em bytes (JSON
  UTF-16LE dentro do base64 de `m_ExtraDataString`), sem deslocar offsets.
- APK final reconstruído, alinhado e assinado (`uber-apk-signer`):
  `output/mighty-doom-revival.apk`.

### 2. Servidor — contrato do cliente 1.13.1 decifrado

Três quebras de contrato eram o que faltava para o boot completar:

| Endpoint | Problema | Correção |
|---|---|---|
| envelope geral | timestamp rejeitado no `ParseServerTimestamp` | chave `uts` **sozinha**, formato `yyyy-MM-ddTHH:mm:ss` UTC (confirmado por bisseção no emulador) |
| `armory/get` | `ArmoryController.Init` faz `foreach` em `upgrades` null → NRE | responder `upgrades: []` |
| `events/get-schedule` | "Malformed response payload" → boot aborta após 3 tentativas | DTO real não tem `event_type`; campos numéricos não-nullable **nunca** vão como `null` — valores ausentes são omitidos |

- Middleware `[req]` logando `/game`, `/data` e `/collections` no log do
  systemd (diagnóstico em produção).

### 3. Infra VPS

- `systemd` + nginx + HTTPS Let's Encrypt; serviço `mighty-doom-revival`
  ativo, health OK local e via
  HTTPS (`client_version 1.13.1`, `api_version 24.0.0`, GameData carregado).
- Git da VPS convergido com origin/main (`d855299`), sem divergência de
  working tree.

### 4. Validação no emulador (a prova)

- Conta **revivaltest** criada pelo próprio cliente (register + login).
- Bootstrap completo: `login-device → game-data-token → user-data →
  armory/get → get-schedule → get-progress → session/refresh` — todos 200,
  zero erros no logcat.
- Menu principal vivo **com conteúdo do servidor** (eventos "Slayers Energy" /
  "Speedrun Challenge" com timers, missões e ofertas).
- **Partida completa**: PLAY → Chapter 1 → estágio 1-1 → combate em 5 salas →
  vitória → XP/moedas/gear → **1-2 desbloqueado**.
- `session/refresh` fluindo durante o combate (keepalive de sessão).

### 5. Testes e commits

- Suíte server completa: PASS (tutorial, battle-pass, rewards, quests,
  progression, stats, smoke, site) + regressão do contrato do schedule no
  smoke.
- Novo `tests/test_zero_catalog_crc.py`: 5/5 (mesmo comprimento, JSON
  válido, already-zero, hash ausente, nome sem hash).
- Commits: `d8909f3` (fixes de contrato + testes) e `d855299` (docs).

---

## 🎮 "O jogo já se conectou?"

**Sim** — neste exato momento o emulador mantém sessão ativa contra a VPS
(`session/refresh` contínuo no log do servidor).

### Se o SEU jogo estiver preso no 100% da loading screen

Esse é exatamente o sintoma corrigido hoje: a barra enche, mas o boot aborta
por trás ("Malformed response payload" → 3 tentativas → menu morto). Causas
possíveis, em ordem de probabilidade:

1. **Servidor desatualizado** — o fix do `get-schedule` está no `d8909f3`+.
   - VPS `doom.sualoja.app.br`: já está fixada, nada a fazer.
   - Servidor local: `git pull` até `d855299`+ e reiniciar (`cd server && npm start`).
2. **APK antigo** (gerado antes do zero de CRC) — o load de cena falha com
   `CRC Mismatch`. Regere pelo Studio (menu *APK → Aplicar endpoint*) e reinstale.
3. **Host errado no APK** — confira para qual hostname o APK aponta.

Diagnóstico em 30s:

```bash
adb logcat -d | grep -aiE "malformed|aborting|crc"
curl -s https://SEU-HOST/revival/health
# no servidor: tail do log e ver se chegam as 7 chamadas do boot
```

---

## ⏳ O que falta fazer

### Progressão e conteúdo (o próximo degrau)

1. **Gear / Slayers / Talents com o dataset real** — endpoints existem e são
   transacionais, mas os payloads/custos exatos do GameData completo ainda
   precisam de validação contra o cliente.
2. **Chapter rewards/loot completos** — o fim de capítulo além do 1-1/1-2
   (baús, drops, boss rewards).
3. **Daily Quests completos** — geração/progresso/claim reutilizando a camada
   persistente de stats.
4. **Reward Tracks** — progress/claim ainda pendentes (baseline existe).
5. **Inbox/grants** — lista segura vazia hoje; mensagens e grants a implementar.
6. **Stats/missões** — validar formato real no GameData comunitário completo
   e ligar todas as missões preservadas ao fluxo de stats do cliente.

### Robustez

7. **Eliminar endpoints em `RESEARCH_MODE`** — repetir fluxos no emulador até
   o cliente não depender de fallback de pesquisa.
8. **Reserialização de tamanho variável do `global-metadata.dat`** — hoje o
   patch direto limita hostnames a 24 bytes (o caminho bundle-aware cobre o
   endpoint de API independentemente disso).
9. **Dispositivo físico** — toda a validação foi em emulador; um teste em
   celular real fecha o ciclo.
10. **CI** — Actions continua bloqueado por Billing/Spending Limit da conta;
    testes locais seguem como fonte de validação.

### Limpeza pendente (decisão do usuário)

- `scripts/loading-screen-editor.{bat,sh}` — aposentados para `tmp/` junto com os
  demais wrappers (2026-08-18); o editor segue no Studio (aba Visuais) e via
  `scripts/loading_screen_editor.py`.
- Arquivos soltos de npm na raiz da VPS (`node`, `npm`, `12.0.2`,
  `mighty-doom-revival-server@0.7.0`) — lixo de um comando npm rodado no
  diretório errado; seguros de remover.

---

## Como verificar o estado agora

```bash
# servidor (VPS ou local)
curl -s https://doom.sualoja.app.br/revival/health

# log das requisições do jogo (VPS)
tail -f /root/mighty-doom-revival/deploy/logs/server.log

# emulador: boot limpo = zero linhas
adb logcat -d | grep -aiE "malformed|aborting|failed to launch"
```

Detalhes técnicos completos: `docs/IMPLEMENTATION-STATUS.md` (contrato do
cliente e ordem de trabalho) e `docs/APK-PATCH.md` (patcher bundle-aware + CRC).
