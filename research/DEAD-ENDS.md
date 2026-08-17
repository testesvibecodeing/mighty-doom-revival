# DEAD-ENDS — hipóteses refutadas neste projeto

Propósito: **impedir trabalho em círculos**. Antes de tentar consertar
qualquer coisa, confira se a abordagem já foi refutada nesta base. Retomar um
dead end exige evidência nova e mensurável (não "faz sentido").

Regras:

1. Toda entrada tem estado `REFUTADO` + a evidência que mediu.
2. Entradas novas só entram com comando/observação que refuta.
3. A alternativa válida (o que FUNCIONA) está em cada entrada — use ela.

| # | Hipótese refutada | Evidência | Alternativa válida |
|---|---|---|---|
| 1 | Timestamp do envelope como epoch (`timestamp`), `yyyy-MM-dd HH:mm:ss`, ou chaves `timestamp`/`utc_timestamp` | `Ubu.GameController:ParseServerTimestamp` faz parse estrito; bisseção no emulador (RELATORIO-STATUS 2026-08-16) | Chave `uts` sozinha, `yyyy-MM-ddTHH:mm:ss` UTC ([index.js `wire()`](../server/src/index.js)) |
| 2 | `event_type` é campo do DTO do schedule (discriminador de subclasse de evento) | Bisseção do boot: `Malformed response payload` → abort após 3 tentativas quando presente; o DTO real do cluster v29 não o lista. Teste de regressão em `server/test/smoke.mjs` | Nunca enviar `event_type`; omissão de ausentes ([events.js](../server/src/events.js)) |
| 3 | Campo numérico sem valor pode ir como `null` no wire | `Malformed response payload` + abort no boot (mesma bisseção acima); regra fixa do parse Newtonsoft do cliente | Omitir o campo inteiro |
| 4 | `armory/get` pode responder sem `upgrades` | `ArmoryController.Init` faz `foreach` em `upgrades` null → NRE logo após login | Sempre `upgrades: []` (array vazio) |
| 5 | O endpoint da API está como string ASCII no ZIP do APK / no `global-metadata.dat` (scan cru acha) | Scan de bytes do ZIP não vê nada; decodificação UnityPy mostra que o `baseUrl` vive em bundle Addressables comprimido em LZ4 | Patch direto no metadata (hostname) + `patch_unity_bundle.py` com `--sweep-all-bundles` |
| 6 | Crescer o hostname no `global-metadata.dat` além do comprimento original | Crescer exigiria realocar seções e deslocar todos os offsets — o app não boota. `scripts/check_patch_length.py` exit 4 | Hostname ≤ orçamento de bytes (31 no 1.13.1) com padding de userinfo; senão caminho bundle-aware |
| 7 | Alterar bundle em `assets/aa/**` sem tocar o catálogo | `CRC Mismatch ... Will not load AssetBundle` → `RemoteProviderException` na carga de cena | `zero_catalog_crc` sempre após reserializar bundle ([patch_unity_bundle.py](../scripts/patch_unity_bundle.py)) |
| 8 | "Atualizar" UnityPy/apktool/uber-apk-signer para resolver problemas de resserialização | Outra versão reserializa diferente e invalida os testes de regressão do patcher; toolchain pinada com SHA-256 | UnityPy 1.25.3 exata, Apktool 3.0.3, uber-apk-signer 1.3.0 |
| 9 | Trocar o token de sessão por JWT para consertar o travamento em 100% | O logcat registra `Session token is not a well formed JWT as expected` (warning), mas o boot COMPLETA com o token base64url atual — causa real era o contrato do `get-schedule`. RELATORIO-STATUS 2026-08-16 | Manter token opaco; só voltar aqui se um fluxo real quebrar por autenticação |
| 10 | Rotas inventadas/transcritas à mão (`talents/get`, `chapters/stage-rewards`, `reward-tracks/get-state`, ...) | Comparação server × 116 rotas do metadata: 10 literais do servidor não existem no cliente (ver `server_only_routes` em `compatibility.json`) | Toda rota vem de `scripts/dump_il2cpp_metadata.py`; o registro acusa drift |
| 11 | `RESEARCH_MODE` respondendo `ok()` vazio é compatibilidade | Cliente aceita HTTP 200 vazio sem abortar, mas a funcionalidade não existe — é fallback de pesquisa, contado em `/revival/research` e bloqueado no gate de fluxos validados | Implementar o contrato real; `verify_everything.py` falha se fluxo validado usar fallback |
| 12 | Marcar endpoint como done porque respondeu HTTP 200 | HTTP 200 com payload vazio/errado ainda derruba o cliente (`Malformed response payload`) ou finge função | DoD completo só com os 8 gates do `compatibility.json` |

## Em teste (não refutado, não confirmado)

- Nada neste momento. Ao testar uma hipótese nova, registre aqui o resultado —
  confirmado vira fato em AGENTS.md/docs, refutado fica nesta tabela.
