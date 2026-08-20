# Prompt executor para GLM-5.1 — corrigir a cadeia de execução e evidência real

> Cole este documento inteiro em uma nova sessão do GLM-5.1 aberta na raiz do
> repositório. O GLM é o **executor**. O Codex é o **auditor**: nenhuma fase deve
> ser commitada ou enviada ao remoto antes de o pacote de auditoria da fase ser
> revisado.

## Papel e resultado obrigatório

Você está trabalhando em `D:\DevPrograms\mighty-doom-revival`.

Sua missão não é criar outro roadmap, redesenhar o Revival Studio nem declarar
que a suíte passou. Sua missão é **corrigir a cadeia que transforma uma execução
real do cliente em evidência real, sanitizada e auditável**, além de corrigir as
inconsistências do framework que esta auditoria já mediu.

O resultado esperado é este fluxo, executado de verdade:

```text
APK local legítimo
  -> análise IL2CPP comprovada
  -> patch bundle-aware + CRC
  -> rebuild + assinatura + verificação pós-assinatura
  -> instalação/abertura no emulador
  -> requests reais do cliente isolados por execução
  -> responses reais do servidor associadas aos requests
  -> fixtures sanitizadas com provenance=client
  -> compatibility.json regenerado, nunca maquiado
  -> próximo gate escolhido por next_task.py
```

Não confunda três afirmações diferentes:

1. `APK apontado`: o host Revival está no APK final e a API Gear oficial não.
2. `fluxo sem crash conhecido`: o logcat não contém uma assinatura fatal
   conhecida durante uma janela de observação.
3. `endpoint validado`: request e response daquele endpoint foram capturados na
   execução atual, o cliente avançou pelo fluxo esperado e a evidência
   sanitizada foi registrada.

Uma não implica automaticamente as outras.

## Autoridade e precedência

Leia completamente, nesta ordem, antes de editar qualquer arquivo:

1. `AGENTS.md`;
2. `research/DEAD-ENDS.md`;
3. `.claude/skills/il2cpp-recon/SKILL.md`;
4. `.claude/skills/apk-patch/SKILL.md`;
5. `.claude/skills/revival-server/SKILL.md` quando tocar `server/src/**`;
6. `.claude/skills/boot-diagnostics/SKILL.md` quando interpretar logcat;
7. `compatibility.json`, `scripts/next_task.py` e
   `scripts/generate_endpoint_matrix.py`;
8. código e testes atuais;
9. documentos antigos somente como contexto histórico.

Em caso de conflito, a fonte anterior vence. Não siga como fonte de verdade
`PROMPT-LLM-LOCAL-FINALIZAR.md`, `MIGHTY-DOOM-LLM-LOCAL-FINALIZAR.md` ou
`docs/PLANO-REVIVAL-STUDIO-100-POR-CENTO.md`: há fatos obsoletos neles.

## Regras inegociáveis

- Nunca baixe, redistribua, versione ou publique APK, assets, bundles, dumps,
  logcats, pcaps, screenshots, keystores ou certificados.
- Use somente o APK que já existe localmente em `input/mighty-doom.apk`.
- Nunca use `git add -f`, `git add .`, `git reset --hard` ou descarte alterações
  alheias.
- Não edite os runtime configs ignorados
  `server/config/{revival,packs,events,site}.json`; altere apenas os exemplos
  quando a mudança for versionável.
- Nunca invente rota, DTO, tipo, nulabilidade, wire name ou código de erro.
- Campo numérico não-nullable sem valor é omitido, nunca enviado como `null`.
- Não altere bundle em `assets/aa/**` sem zerar e provar o `m_Crc` correspondente.
- Não declare APK pronto sem `verify_patched_apk.py` passando no arquivo final
  depois da assinatura.
- Não grave token administrativo, JWT, password, device id real ou segredo em
  relatório, fixture, log versionado ou saída de auditoria.
- Não faça commit nem push. Ao fim de cada fase, pare e entregue o pacote de
  auditoria ao Codex.
- Se faltar emulador, token administrativo, acesso ao servidor ou uma decisão
  destrutiva, marque a fase como `BLOQUEADA`; não simule o resultado.

## Linha de base já medida pelo auditor em 2026-08-19

Trate os itens abaixo como `CONFIRMADO` somente enquanto os comandos continuarem
reproduzindo o mesmo resultado no HEAD atual.

### O que já funciona

O framework Python não está globalmente quebrado:

```text
python run_tests.py
=> 31/31 arquivos de teste Python OK
```

O APK local é analisável e o extrator atual processa os dados reais:

```text
python scripts/dump_il2cpp_metadata.py \
  --apk input/mighty-doom.apk --all --out work/audit-glm-il2cpp.json
=> 116 rotas, 1555 enums, 403 dtos, 455 wire names
```

O preflight HTTPS real passou para o host registrado no projeto local:

```text
python scripts/check_revival_server.py \
  --server doom.sualoja.app.br \
  --report work/audit-glm-server-preflight.json
=> TLS, versão 1.13.1, API 24.0.0, GameData, prefixo /collections/doom,
   code=2200 e uts estrito validados
```

O APK assinado existente foi verificado novamente:

```text
python scripts/verify_patched_apk.py \
  --apk work/revival-studio/e2e-vps-fase13/output/mighty-doom-revival.apk \
  --server doom.sualoja.app.br \
  --report work/audit-glm-final-apk.json
=> target_occurrences=14, official_occurrences=0, verified=true
```

O relatório real do pipeline registra decode, patch bundle-aware, rebuild,
verificação pré-assinatura, assinatura, verificação da assinatura, verificação
pós-assinatura e publicação com exit 0. Portanto, **não reescreva o patcher para
“conseguir apontar o APK”**. Esse apontamento já foi provado.

O commit `7c5571c` corrigiu três bloqueios medidos no cliente e o teste JWT atual
passa com `aud`/`audience` como arrays.

### O que ainda não funciona de forma auditável

O último relatório real do harness contém:

```json
{
  "verdict": "clean",
  "endpoint_sequence": null,
  "endpoints_called": null,
  "fallback_endpoints": []
}
```

Isso ocorreu porque o harness foi executado sem `--admin-token`. Logo, esse
relatório prova somente ausência das assinaturas fatais conhecidas na janela; ele
**não prova quais endpoints foram chamados** e não pode criar evidência de
request/response.

Também foi medido:

```text
python scripts/next_task.py --json
=> game/gear/apply-cosmetic, gate=request_observed

python scripts/verify_everything.py
=> suítes Node e Python passam no HEAD atual;
   falha porque docs/ENDPOINT-MATRIX.md está desatualizado

compatibility.json
=> apenas 4/116 rotas com DoD completo

/revival/health
=> research_mode=true no servidor vivo
```

Não promova o relatório `clean` para “cliente validado”.

## Defeitos concretos que você deve corrigir

### P0 — captura real do harness não existe como a documentação promete

Arquivos centrais:

- `scripts/client_harness.py`;
- `server/src/index.js`;
- `server/src/db.js`;
- `scripts/generate_endpoint_matrix.py`;
- `scripts/verify_everything.py`;
- `tests/fixtures/protocol/README.md`;
- testes novos sob `tests/` e `server/test/`.

Problemas medidos:

1. Sem token administrativo, o harness ainda termina com `verdict=clean`, mas
   `endpoint_sequence` fica `null`.
2. `--update-registry` pode marcar `request_observed` e `response_observed`
   diretamente no JSON; isso não cria a fixture `provenance=client` prometida
   pela documentação.
3. O harness não grava nenhuma fixture client hoje.
4. `response_observed=true` pode ser marcado apenas porque o logcat ficou limpo;
   o response body não foi capturado e associado ao request.
5. O endpoint `/revival/requests` retorna histórico; o harness não tira um
   baseline antes do lançamento. Uma execução pode herdar requests antigos.
6. O campo chamado `endpoint_sequence` é uma contagem agregada ordenada
   alfabeticamente, não a sequência temporal real.
7. `repo.logRequest()` só é chamado depois da autenticação; register e
   login-device não entram no log atual.
8. `/revival/research` acumula fallbacks desde o boot. O harness precisa medir o
   delta da execução, não atribuir todo o histórico ao fluxo atual.
9. O harness só abre o app e espera. Não exige milestones ou endpoints mínimos
   do fluxo selecionado; “ficou aberto” não significa “chegou ao menu”.
10. `verify_everything.py` não reprova `request_observed/response_observed=true`
    sem evidência estruturada compatível.

Implemente uma cadeia conservadora com estes critérios funcionais:

- O token administrativo vem de `--admin-token` ou de variável de ambiente
  dedicada. Nunca persista ou ecoe o valor.
- `--update-registry`, `--capture-fixtures` ou um modo de validação real deve
  recusar execução sem credencial para ler a captura do servidor.
- Sem captura de endpoints, o veredito deve ser `inconclusive`, não `clean`,
  salvo um modo explicitamente chamado apenas de diagnóstico de logcat.
- Tire um cursor/baseline antes de abrir o app. Depois leia somente requests com
  id posterior ao baseline, em ordem crescente.
- A API administrativa deve suportar captura incremental determinística e
  limitada. Preserve compatibilidade e exija autenticação.
- Registre também register/login e associe a cada request: id, rota normalizada,
  instante, request sanitizável, status HTTP, envelope/code e response
  sanitizável. Faça migração SQLite retrocompatível e teste banco antigo.
- Não armazene headers secretos. O corpo persistido deve ser o mínimo necessário
  para o contrato e continuar restrito ao servidor/admin.
- Meça fallbacks por delta da execução.
- Produza a sequência temporal real e, separadamente, um resumo por contagem.
- Adicione `--flow` ou mecanismo equivalente com perfis explícitos, por exemplo
  `boot`, `menu` e `chapter`. Cada perfil lista endpoints/milestones mínimos e
  retorna exit não zero se não forem observados.
- Adicione `--require-endpoint` repetível para validar uma tarefa específica do
  `next_task.py`.
- Crie uma fixture por endpoint realmente observado em
  `tests/fixtures/protocol/client/<modulo>/...json`, com request e response da
  mesma chamada, `provenance=client`, `sanitized=true` e timestamp UTC.
- A sanitização deve remover tokens, passwords, códigos de recuperação, ids de
  dispositivo e hosts privados, preservando chaves, tipos, arrays, omissões e
  nullabilidade do wire.
- Não sobrescreva uma fixture client válida com `server-replay`.
- `client_harness.py --update-registry` deve escrever/atualizar fixtures e então
  chamar o gerador. Não deve editar campos derivados do registro diretamente.
- `response_observed` só pode ficar verdadeiro quando existe response capturado
  para a chamada real. `client_validated` exige também os milestones do fluxo e
  ausência das assinaturas fatais aplicáveis.
- O relatório final precisa distinguir `diagnostic_clean`, `captured`,
  `flow_validated` e `inconclusive`, ou estados equivalentes sem ambiguidade.

Testes mínimos desta fase:

- falta de token + captura solicitada => exit 2 e nenhuma mutação;
- baseline exclui requests antigos;
- sequência preserva a ordem por id/tempo;
- auth/register e auth/login-device aparecem;
- request e response mantêm o pareamento;
- sanitizer não vaza nenhum segredo de fixtures sintéticas;
- fixture client aciona os dois gates derivados;
- server-replay não aciona gates de cliente;
- execução inconclusiva não altera `compatibility.json`;
- fluxo com endpoint obrigatório ausente falha;
- fallback anterior ao baseline não contamina a execução;
- migração de SQLite existente preserva usuários e progresso.

### P0 — integridade do registro e do gate final

Corrija a fonte de verdade sem fabricar história.

- Não invente fixtures para as 11 rotas atualmente semeadas por
  `EVIDENCE_SEED`.
- Separe evidência histórica textual de uma captura estruturada. Se não há o par
  request/response sanitizado, ele não pode ser criado retroativamente.
- Preserve a informação histórica como `client-manual`, `legacy-observation` ou
  outra provenance explícita, mas não a faça parecer uma fixture que não existe.
- Torne `generate_endpoint_matrix.py` a única escrita autorizada dos campos
  derivados.
- Faça `verify_everything.py` reprovar combinações impossíveis, no mínimo:
  fixture client sem `sanitized=true`; observed verdadeiro sem provenance
  aceita; response sem request; client_validated usando fallback; fixture cuja
  rota diverge da chave do registro; material sensível em fixture.
- Corrija a matriz atualmente desatualizada apenas pelo gerador e mostre o diff
  antes de aceitar a escrita.
- Não aumente artificialmente a contagem de DoD. Uma correção honesta pode
  reduzir a métrica até novas capturas reais acontecerem.

### P1 — o extrator IL2CPP ainda não entrega contratos focados por endpoint

O comando `--all` funciona, mas há limites explícitos no código atual:

- `--dtos --pattern GearApi` retorna zero porque responses aninhados têm
  namespace vazio e o declaring type não é emitido;
- o output não qualifica DTOs pelo tipo externo/nestedTypes;
- method names e parâmetros não são associados ao DTO externo no output;
- tipos C#/nulabilidade não são resolvidos;
- `--wire-names` extrai 455 candidatos globais, mas não liga cada
  `[JsonProperty]` ao field correspondente;
- todos os fields de DTO são marcados como fallback snake_case, mesmo quando um
  override pode existir;
- não há binding provado `rota -> método -> request -> response` consumível por
  `next_task.py`.

Evolua `scripts/dump_il2cpp_metadata.py` e seus testes sintéticos sem fingir que
o metadata contém informação que depende do `libil2cpp.so`:

- emita `declaring_type`/`qualified_name` para tipos aninhados;
- faça `--pattern` casar também com o declaring type;
- emita métodos e nomes dos parâmetros associados, além dos índices/tipos que
  puderem ser provados;
- quando o tipo real não puder ser resolvido sem a tabela nativa, emita um estado
  explícito `unresolved`, nunca um tipo adivinhado;
- ligue JsonProperty a fields somente após implementar e testar o pareamento
  `attributeDataRange -> token/field`; até lá mantenha o wire como hipótese;
- adicione um modo de contrato focado somente se o binding for demonstrável;
- inclua provenance por propriedade (`metadata`, `attribute`,
  `fallback_snakecase`, `unresolved`);
- preserve todos os sanity checks existentes e acrescente fechamentos para cada
  nova tabela lida;
- não versione dumps do APK real; use metadata sintético nos testes.

Critério mínimo: um filtro por `GearApi` precisa devolver o tipo externo,
métodos, parâmetros e responses aninhados correspondentes sem confundi-los com
outros `UpgradeResponse` do jogo.

### P1 — relatório do pipeline contradiz o patch real

O relatório real contém um bundle alterado e `catalog_crc.zeroed=true`, mas os
campos agregados `bundles_alterados` e `crcs_zerados` saíram vazios. O
`PipelineResult` procura chaves antigas no topo, enquanto o relatório atual
guarda os dados dentro de `bundle_aware`.

Corrija `scripts/revival_editor/pipeline.py` e os testes para consumir o schema
real de `patch_bundle_from_report.py`:

- derive os bundles alterados de entradas `changed=true`;
- derive CRCs zerados somente quando `catalog_crc.zeroed=true`;
- exija um CRC zerado para todo bundle alterado sob `assets/aa/**`;
- faça o pipeline falhar se a relação não fechar;
- teste com o formato real atual, não apenas com um fake de chaves antigas;
- mantenha a verificação pós-assinatura como gate final.

### P1 — scripts untracked gerados com caminhos quebrados

Há arquivos não versionados em `server/`:

```text
server/setup-server.bat
server/setup-server.sh
server/start-server.bat
server/start-server.sh
```

Eles referenciam `server/revival_studio.py` e `scripts/start-server.*`, que não
existem nesses caminhos. Não os adicione ao Git como estão.

Primeiro determine, pela arquitetura atual e pelos testes de wrappers, se eles
devem existir. Se forem mantidos:

- corrija todos os caminhos de Windows e POSIX;
- não duplique a orquestração do framework Python;
- não baixe GameData silenciosamente;
- não abra GUI inesperadamente em fluxo headless;
- adicione testes que executem/resolvam os caminhos reais.

Se forem redundantes, não os apague silenciosamente: proponha a remoção no pacote
de auditoria e espere aprovação.

### P2 — documentação e prompts antigos sabotam o executor

Corrija o drift documental que fez o GLM trabalhar no alvo errado:

- `.claude/skills/il2cpp-recon/SKILL.md` ainda diz que
  `dump_il2cpp_metadata.py` não existe;
- `docs/APK-PATCH.md` mistura wrappers aposentados, orçamento antigo de 24 bytes
  e afirmações contraditórias sobre metadata e Addressables;
- os prompts antigos mandam baixar APK, procurar apenas
  `slayersclub.bethesda.net`, usar Koa, ressuscitar wrappers e criar scripts que
  já não existem;
- `docs/PLANO-REVIVAL-STUDIO-100-POR-CENTO.md` foi escrito contra um snapshot
  antigo e descreve fases já concluídas como pendentes;
- o runtime vivo é `node:http` builtin + SQLite, não Koa;
- o host de gameplay medido é `international.gear.bethesda.net`, com 31 bytes;
- quem decide o orçamento é `check_patch_length.py`;
- o Studio Python e seu pipeline já existem.

Use banners claros de `OBSOLETO` quando um documento histórico precisar ser
preservado. Não deixe dois documentos ativos darem comandos incompatíveis.

### P2 — ambiente Node não determinístico

O ambiente auditado usa Node `v25.3.0` com npm `12.0.1`; o npm avisa que essa
combinação não é suportada. Os testes atuais passam depois do commit `7c5571c`,
mas o projeto recomenda Node 24 LTS.

- Não atribua bugs de contrato ao warning do npm.
- Documente e valide uma faixa realmente suportada com `node:sqlite`.
- Prefira Node 24 LTS para o gate reproduzível.
- Se alterar `engines`, setup ou diagnóstico, cubra a decisão com teste e não
  bloqueie versões por palpite.

## Ordem obrigatória de execução

### Fase 0 — congelar e reproduzir

Execute e guarde a saída no pacote de auditoria, sem ainda editar:

```powershell
git status --short
git diff
git diff --cached
git log -8 --oneline --decorate
python run_tests.py
python scripts/verify_everything.py
python scripts/generate_endpoint_matrix.py --check
python scripts/next_task.py --json
```

Não toque em alterações concorrentes. Se o HEAD ou o status mudar durante a
execução, tire uma nova linha de base.

### Fase 1 — fechar P0 de captura/evidência

Implemente primeiro a captura incremental, o pareamento request/response, a
sanitização, as fixtures client e os gates conservadores. Não avance ao extrator
ou à GUI enquanto os testes desta fase não passarem.

### Fase 2 — fechar P1 de relatório e extrator

Corrija o schema do relatório do pipeline e torne os contratos IL2CPP focáveis
sem promover hipóteses.

### Fase 3 — limpar drift e entrypoints

Corrija skills/docs ativos e resolva os scripts untracked somente após decisão
auditada.

### Fase 4 — prova real controlada

Use valores locais já configurados; não invente segredos. Antes da captura:

1. confirme APK final com `verify_patched_apk.py`;
2. confirme o servidor com `check_revival_server.py`;
3. obtenha o token administrativo de variável de ambiente ou peça ao usuário;
4. tire baseline do request log e dos fallbacks;
5. execute um perfil de boot/menu com endpoints obrigatórios;
6. gere fixtures client sanitizadas;
7. inspecione cada fixture por vazamento;
8. regenere o registro;
9. rode `next_task.py` novamente.

Exemplo conceitual — ajuste à CLI que você implementar e nunca coloque o token
literal no histórico:

```powershell
python scripts/client_harness.py `
  --server https://doom.sualoja.app.br `
  --apk work/revival-studio/e2e-vps-fase13/output/mighty-doom-revival.apk `
  --flow boot `
  --require-endpoint game/auth/register `
  --require-endpoint game/player/user-data `
  --capture-fixtures `
  --update-registry
```

Para a tarefa atualmente selecionada, não marque
`game/gear/apply-cosmetic=request_observed` até executar no cliente uma ação que
realmente chame essa rota e produzir a fixture correspondente.

### Fase 5 — gate final

O pacote só pode ser apresentado como candidato quando todos passarem:

```powershell
python run_tests.py
python scripts/verify_everything.py
python scripts/generate_endpoint_matrix.py --check
python scripts/verify_everything.py `
  --server https://doom.sualoja.app.br `
  --apk work/revival-studio/e2e-vps-fase13/output/mighty-doom-revival.apk
```

`--strict-research` só pode passar depois de o operador desligar
`RESEARCH_MODE` no ambiente do servidor vivo. Você não está autorizado a editar
o runtime local/produção escondido para forçar esse resultado. Se continuar
ligado, reporte a pendência honestamente.

## Testes e qualidade exigidos

- Todo bug corrigido ganha teste que falhava antes.
- Testes do harness usam servidor/ADB fakes ou fixtures sintéticas; não dependem
  de APK proprietário no CI.
- Testes do extrator usam metadata sintético.
- Testes do pipeline usam o schema real do relatório bundle-aware.
- Faça compile/syntax checks proporcionais.
- Não aceite teste que apenas verifica que uma string aparece no código quando o
  comportamento pode ser exercitado.
- Não enfraqueça gates existentes para obter verde.
- Não converta uma falha em warning sem evidência nova.

## Pacote obrigatório para auditoria do Codex

Ao fim de cada fase, pare e responda exatamente com:

```text
FASE: <número e nome>
STATUS: PRONTA PARA AUDITORIA | BLOQUEADA

CONFIRMADO:
- <fato + comando/arquivo que prova>

A VERIFICAR:
- <hipótese ainda não medida>

ARQUIVOS ALTERADOS:
- <caminho>: <por que mudou>

TESTES EXECUTADOS:
- <comando> => <exit e resumo exato>

EVIDÊNCIA REAL:
- APK verificado: sim/não/inaplicável
- servidor preflight: sim/não/inaplicável
- requests isolados desta execução: <número ou indisponível>
- responses pareados: <número ou indisponível>
- fixtures client novas: <lista ou nenhuma>
- fallbacks no delta: <número ou indisponível>
- milestones do fluxo: <lista>

RISCOS/BLOQUEIOS:
- <item>

GIT:
- git status --short
- resumo de git diff --stat
- nenhum commit/push realizado
```

Inclua também os caminhos dos relatórios em `work/`, mas nunca cole tokens ou
payloads sensíveis na resposta.

## Definition of Done desta missão

Esta missão do framework só termina quando:

- [ ] a suíte Node passa;
- [ ] `python run_tests.py` passa;
- [ ] `verify_everything.py` passa no modo local;
- [ ] registro e matriz estão sincronizados;
- [ ] execução sem captura não pode se declarar validação de endpoint;
- [ ] captura real é incremental e não herda requests/fallbacks antigos;
- [ ] auth e rotas autenticadas entram na sequência temporal real;
- [ ] request e response da mesma chamada são pareados;
- [ ] fixtures client são realmente criadas e sanitizadas;
- [ ] o gerador, não o harness, deriva os gates observados;
- [ ] o gate final detecta provenance incoerente;
- [ ] o pipeline reporta corretamente bundles alterados e CRCs zerados;
- [ ] o extrator qualifica DTOs aninhados e não mistura responses homônimos;
- [ ] nenhuma hipótese de wire/type é promovida a fato;
- [ ] docs e skills ativos não contradizem o código atual;
- [ ] entrypoints mantidos apontam para arquivos existentes e têm teste;
- [ ] o APK final continua passando na verificação pós-assinatura;
- [ ] ao menos um fluxo real produz endpoints não nulos e fixtures
  `provenance=client`;
- [ ] `next_task.py` avança somente por evidência nova verdadeira;
- [ ] o Codex aprovou o diff e os relatórios antes de qualquer commit/push.

Comece agora pela Fase 0. Não escreva outro plano e não altere arquivos antes de
reproduzir a linha de base.
