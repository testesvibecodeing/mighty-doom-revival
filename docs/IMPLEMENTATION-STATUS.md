# Estado de implementação — Mighty DOOM Revival

Este arquivo é o ponto de retomada técnico do projeto. Atualize-o quando um fluxo passar de implementação teórica para teste real.

## Regra de status

- ✅ **VALIDADO**: executado em processo real com persistência/teste de regressão;
- 🧪 **IMPLEMENTADO**: código existe, mas ainda precisa do cliente 1.13.1 real;
- 🔬 **EM PESQUISA**: schema/comportamento ainda incompleto;
- ⛔ **REMOVIDO**: serviço externo propositalmente não usado no Revival.

## Servidor

| Área | Estado | Observação |
|---|---:|---|
| Node HTTP standalone | ✅ | `node:http`, sem Koa/npm runtime |
| SQLite | ✅ | `node:sqlite`, persistência real |
| Auth register/login-device | ✅ | testado via HTTP |
| Starter bundle | ✅/🧪 | lógica testada; filtro por `slot.type` alinhado ao backend preservado, aguardando GameData/APK final |
| Inventory/currencies/energy/slots | ✅ | testado via HTTP + SQLite |
| GameData token + `/data` | ✅ | testado com dataset sintético |
| Tutorial dependencies/rewards | ✅ | SQLite isolado + HTTP integrado |
| Chapters start/update/revive/end | ✅/🧪 | persistência testada; payload alinhado ao backend preservado; loot/rewards finais ainda incompletos |
| Store Revival | ✅ | compra transacional, quotas e moeda interna |
| IAP dinheiro real | ⛔ | explicitamente bloqueado |
| Ads externos | ⛔ | desativados |
| Custom events | ✅ | schedule/progress testados |
| Battle Pass arquivado | ✅/🧪 | start/mission/tier/premium reward testados; progressão automática por stats ainda pendente |
| Daily rewards | 🧪 | get-state + claim marker; recompensa real pendente |
| Idle rewards | 🧪 | estado/generation baseline; claim/boost pendentes |
| Daily quests | 🧪 | endpoint explícito; geração/progresso/claim pendentes |
| Gear upgrades/cosmetics | 🔬 | protocolo conhecido, implementação Revival pendente |
| Slayer upgrades/cosmetics | 🔬 | protocolo conhecido, implementação Revival pendente |
| Talents | 🔬 | `/talents/buy` e GameData conhecidos, implementação pendente |
| Reward tracks | 🔬 | baseline existe; progress/claim pendentes |
| Inbox | 🧪 | lista segura vazia; mensagens/grants pendentes |
| Identity externa | ⛔ | Google/Game Center/Xbox não necessários ao servidor pessoal |

## GameData preservado

Formato confirmado pelo backend comunitário preservado:

- `resources`
- `weapons`, `equipment`, `launchers`, `ultimates`, `energies`, `slayers`, `cosmetics`
- `bundles`
- `inventory.slots`
- `chapter_mode.chapters`
- `talents.talents`
- `tutorial.sequences`
- `store.catalogs`
- `story_battle_passes`

`server/src/game-data-schema.js` normaliza esse layout e também aceita alguns nomes usados por snapshots alternativos.

## Battle Pass / modo arquivo

Config padrão:

```json
{
  "archive_mode": true,
  "unlock_premium_battle_pass": true
}
```

Com `archive_mode`, temporadas presentes em `story_battle_passes` podem ser expostas pelo `/game/events/get-schedule` mesmo que as datas históricas já tenham expirado. O cliente recebe os `args` em Base64/JSON como no protocolo preservado.

A trilha premium pode ser tratada como conteúdo preservado desbloqueado sem Google Play Billing/IAP real.

### Teste já executado

Uma temporada histórica sintética com `start_time/end_time` expirados foi executada contra SQLite real:

1. apareceu no schedule com datas neutralizadas;
2. `start-season` criou estado persistente;
3. start duplicado foi bloqueado;
4. missão não concluída não pôde ser resgatada;
5. missão concluída concedeu pontos;
6. tier premium foi resgatado;
7. recompensa em moeda interna foi persistida;
8. claim repetido não duplicou recompensa;
9. estado apareceu em `events/get-progress`.

## APK / patcher

Cliente alvo:

- package `com.bethsoft.ubu`
- versão `1.13.1` / build `84862`
- SHA-256 alvo `519bfbb18c5bbab78f450b549777774e7d0ed78cd8b42cc25c7a2d3167669f35`

### Validado

O patcher foi testado contra bundle Unity sintético:

- `slayersclub.bethesda.net` possui 24 bytes;
- `d.debruinsistemas.com.br` possui 24 bytes;
- substituição 24→24 não altera tamanho do bundle;
- Manifest/TLS são atualizados;
- hostname incompatível é recusado antes de alterar o bundle.

Teste: `scripts/test_patch_apk.py`.

### Ainda NÃO validado

- o APK real 1.13.1 não foi executado neste ambiente;
- ainda não foi confirmado no binário real que o host oficial aparece exatamente no bundle esperado;
- reconstrução/assinatura do APK real ainda não foi instalada em Android;
- handshake HTTPS do APK real contra Revival ainda não foi confirmado;
- gameplay real no cliente ainda não foi confirmado.

Não marcar o projeto como jogável/100% antes desses testes.

## Infra/CI

O GitHub Actions está configurado, porém os runners da conta não iniciaram por bloqueio de Billing/Spending Limit. Não usar falha de Actions como falha do código enquanto esse bloqueio existir.

Os testes locais são a fonte atual de validação.

## Próxima ordem de trabalho

1. validar/importar GameData comunitário completo contra `game-data-schema.js`;
2. implementar Gear, Slayer e Talents usando custos/limites do GameData;
3. implementar Daily/Idle rewards e Quests completos;
4. completar chapter rewards/loot e progressão de jogador;
5. alimentar progressão de Battle Pass via stats/missões;
6. executar `scripts/analyze-official-apk.bat` em ambiente com acesso ao APK;
7. executar `scripts/patch-apk.bat` no APK real;
8. apontar `d.debruinsistemas.com.br` para um Revival HTTPS válido;
9. instalar APK assinado em Android e capturar `/revival/requests`;
10. eliminar endpoints ainda vistos apenas em `RESEARCH_MODE`;
11. repetir fluxos até o cliente não depender de fallback de pesquisa;
12. só então declarar o caminho server + patcher + client como jogável.
