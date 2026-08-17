# Matriz de compatibilidade da API

Esta matriz acompanha o trabalho necessário para chegar ao máximo de funcionalidades acessíveis pelo cliente Android 1.13.1.

Legenda:

- ✅ implementado no Revival;
- 🧪 base implementada, aguardando validação no APK real;
- 🔬 schema/semântica ainda em pesquisa;
- ⛔ serviço externo deliberadamente removido.

| Módulo | Estado | Escopo |
|---|---:|---|
| auth | 🧪 | registro local, login por device, token e bootstrap do starter bundle |
| player | 🧪 | game-data-token, user-data, settings, stats baseline; user-data agora reflete talentos persistidos |
| inventory | 🧪 | wire de inventário, slots, equip sequence, equip |
| session | 🧪 | heartbeat e refresh |
| store | 🧪 | catálogo Revival, quota e compra transacional por moeda interna |
| iap | ⛔ | dinheiro real desativado |
| ads | ⛔ | anúncios externos desativados |
| events | 🧪 | schedule, args e estado por jogador |
| battle-pass | 🧪 | temporadas arquivadas visíveis, start-season, missões, pontos, tiers, grants e persistência; wire final ainda precisa ser validado no APK real |
| chapters | 🧪 | start/update/revive/end persistentes; user-data reflete current_run; grants/stage rewards ainda aguardam schema real |
| daily-rewards | 🧪 | get-state + claim diário transacional/persistente; wire final ainda precisa ser validado no APK real |
| idle-rewards | 🧪 | get-state + geração por progresso + claim persistente; boost/schema final pendentes |
| inbox | 🧪 | lista vazia segura; grants/messages pendentes |
| reward-tracks | 🧪 | lista, progresso e claim persistentes com grants; wire final ainda precisa ser validado no APK real |
| gear | 🔬 | upgrade, multi-upgrade e cosméticos pendentes |
| slayers | 🔬 | upgrade e cosméticos pendentes |
| talents | 🧪 | get/buy, requisitos, custos e persistência no user-data; upgrade/schema final pendentes |
| quests | 🔬 | baseline diária vazia; definições, progresso, claim e rotação pendentes |
| tutorial | 🔬 | sequências/progresso pendentes |
| identity | 🧪 | identidade local; links externos rejeitados |
| xbox/msal | ⛔ | dependência externa será substituída quando não for necessária ao gameplay |

## Bootstrap crítico

Com `game-data.json` carregado, o registro tenta reproduzir o bootstrap necessário do cliente:

1. encontra o bundle com tag `starter`;
2. concede seus recursos usando as categorias do game data;
3. persiste moedas, energias, itens, cosméticos e entitlements por tipo;
4. encontra os slots `slot_primary_weapon` e `slot_slayer` por tag;
5. equipa automaticamente a primeira arma e o primeiro Slayer concedidos pelo starter bundle.

Isso evita hardcode de IDs e permite seguir exatamente a cópia de game data usada pelo cliente.

## Battle Pass arquivado

Em `archive_mode`, temporadas preservadas agora aparecem no progresso de eventos antes do primeiro `start-season`, usando um estado inicial não persistido. Isso permite que o cliente descubra e renderize a temporada restaurada sem bloquear a criação do estado real quando iniciar a temporada. Depois do início, missões, pontos, claims de tiers e grants passam a usar o estado persistido do jogador.

## Estado de capítulos

O Revival agora persiste o ciclo básico de uma tentativa de capítulo em `user_state`:

1. `/chapters/start` cria `current_run` com capítulo/challenge/stage;
2. `/chapters/update` preserva avanço, checkpoint e stats recebidos;
3. `/chapters/revive` incrementa o contador de revives da tentativa atual;
4. `/chapters/end` encerra a tentativa e registra a conclusão básica;
5. `/player/user-data` devolve a mesma progressão persistida após reiniciar o servidor.

Os endpoints de stage rewards respondem grant vazio de forma explícita até o formato real ser validado. Eles não usam o fallback genérico do `RESEARCH_MODE`, evitando marcar recompensa fictícia como entregue.

## Categorias de recurso modeladas

O Revival reconhece as categorias observadas no backend de referência:

| Categoria | Tipo |
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

Quando a categoria não estiver explícita, o servidor tenta classificar pela coleção correspondente do `game-data.json`.

## Critério para marcar ✅

Um módulo só passa para ✅ depois de:

1. observarmos a chamada do APK patchado;
2. validarmos request e response reais;
3. persistirmos os efeitos necessários;
4. testarmos reinício do servidor sem perda de progresso;
5. confirmarmos o fluxo na UI do jogo;
6. adicionarmos teste de regressão.

`RESEARCH_MODE=true` existe justamente para não fingir compatibilidade: endpoints desconhecidos são registrados até serem implementados com comportamento conhecido.
