# Prompt executor para Opus — recuperar o trabalho do GLM e finalizar a autenticação Revival

> Cole este documento inteiro em uma nova sessão do Opus aberta na raiz do
> repositório. O Opus é o **executor**. O Codex é o **auditor**. Não faça commit,
> push ou deploy remoto antes do gate de auditoria correspondente.

## Missão

Você está trabalhando em:

```text
D:\DevPrograms\mighty-doom-revival
```

O GLM consumiu o limite de contexto e deixou uma árvore grande, útil em partes,
mas não finalizada. Sua missão tem duas etapas, obrigatoriamente nesta ordem:

1. **recuperar e fechar de forma auditável o trabalho pendente do GLM**, sem
   reescrever tudo e sem promover tentativas inconclusivas a evidência;
2. **implementar e provar a autenticação Revival sem Google Play Games**, usando
   `docs/PROMPT-GLM-5.1-REMOVER-GOOGLE-PLAY-GAMES.md` como especificação de
   produto depois que a linha de base estiver limpa.

O resultado final esperado é:

```text
APK legítimo local
  -> patch existente de endpoint preservado
  -> launcher/tela Revival: Criar conta | Entrar
  -> credentials.json no formato real do Ubu.CredentialStore
  -> gate/popup Google Play Games suprimido
  -> Unity abre usando register/login-device
  -> restart preserva a mesma conta e o progresso
  -> harness observa o MESMO servidor chamado pelo APK
  -> fixtures client sanitizadas
  -> gates Node/Python/registro/APK passam
```

Não comece pela Activity Android. Hoje há um erro de rig/servidor que invalida as
últimas tentativas; resolvê-lo é pré-requisito.

## Autoridade e ordem de leitura

Leia completamente, antes de editar:

1. `AGENTS.md`;
2. `research/DEAD-ENDS.md`;
3. `.claude/skills/boot-diagnostics/SKILL.md`;
4. `.claude/skills/il2cpp-recon/SKILL.md`;
5. `.claude/skills/apk-patch/SKILL.md`;
6. `.claude/skills/revival-server/SKILL.md`;
7. este documento;
8. `docs/PROMPT-GLM-5.1-CORRIGIR-FRAMEWORK-REAL.md`;
9. `docs/PROMPT-GLM-5.1-REMOVER-GOOGLE-PLAY-GAMES.md`;
10. código, testes e relatórios atuais em `work/harness/`.

Documentos antigos são contexto, não fonte de verdade. Se código, teste,
metadata e documento divergirem, apresente a divergência ao auditor.

## Regras inegociáveis

- Nunca baixe, publique, versione ou redistribua APK, assets, bundles, dumps,
  logcats, screenshots, keystores ou certificados.
- Use apenas `input/mighty-doom.apk`, que já existe localmente.
- Nunca use `git add -f`, `git add .`, `git reset --hard` ou descarte alterações.
- Não faça commit nem push. Prepare lotes lógicos para o Codex auditar.
- Não faça deploy/restart no VPS sem autorização explícita do usuário no gate
  indicado neste documento.
- Não limpe dados do app, não recrie o AVD e não desinstale o APK sem autorização.
  `am force-stop` é permitido; `pm clear` não é.
- Não edite configs runtime ignorados para “fazer passar”.
- Não invente rota `game/*`, DTO, campo, tipo, nulabilidade ou código.
- Não registre password, device ID real, recovery code, JWT, admin token ou
  segredo em Git, relatório ou log.
- Não remova bibliotecas Google em massa: Firebase, notifications e billing
  compartilham dependências.
- Alterou bundle em `assets/aa/**`: `zero_catalog_crc` e prova do catálogo são
  obrigatórios.
- APK final só é final depois de assinatura e `verify_patched_apk.py` no arquivo
  assinado.
- Um HTTP 200, app aberto ou screenshot bonito não validam fluxo. Exija request,
  response, milestones e ausência de fallback/fatal.

## Estado medido pelo auditor em 2026-08-19

### CONFIRMADO — árvore e testes

```text
branch: main
HEAD: fea3c18
arquivos modificados: 30
arquivos não rastreados: 11
staged: nenhum
diff rastreado: aproximadamente +1717 / -245 linhas
```

Não trate a árvore como descartável. Há mudanças úteis em:

- captura incremental e fixtures no `client_harness.py`;
- request/response pareados no `request_log`;
- registro/matriz derivados de fixtures;
- extrator IL2CPP;
- consolidação de relatórios bundle-aware;
- correção candidata do battle pass;
- testes correspondentes.

Resultados medidos nesta auditoria:

```text
python run_tests.py
=> 33/33 arquivos de teste Python OK

python scripts/verify_everything.py
=> npm test OK
=> regressões Python listadas OK
=> 36 camadas passaram
=> FALHA única: compatibility.json e docs/ENDPOINT-MATRIX.md desatualizados
```

O verde ainda é incompleto por dois defeitos do próprio gate:

1. `verify_everything.py` mantém uma lista manual e **não executa** os novos
   `tests/test_client_harness.py` e `tests/test_green_gate.py`, embora
   `run_tests.py` os descubra;
2. o harness não classifica
   `ArgumentException: Could not cast or convert from System.String to System.String[]`
   como fatal.

### CONFIRMADO — evidência real útil deixada pelo GLM

O boot válido anterior está em:

```text
work/harness/fase4-boot3.json/harness-20260819-222115.json
verdict = flow_validated
12 requests / 10 endpoints / 10 fixtures client sanitizadas
register -> game-data-token -> user-data -> armory -> events -> battle pass
```

Existem 10 fixtures em `tests/fixtures/protocol/client/`. Ainda **não existe**
fixture `provenance=client` de `game/auth/login-device`.

A correção candidata em `server/src/battle-pass.js` permite reiniciar uma season
com `active_state=2` após `end-season`. O teste unitário passa, mas o cliente real
não revalidou essa mudança.

### CONFIRMADO — as três tentativas de restart são inconclusivas/falhas

Relatórios:

```text
fase4-restart1: failed, 0 requests, milestones ausentes
fase4-restart2: failed, 0 requests, milestones ausentes
fase4-restart3: failed, 0 requests, Failed to launch after 3 attempts
```

No restart1 o logcat contém:

```text
Play Games Plugin 0.11.01 ... ERROR: Returning an error code
ArgumentException: Could not cast or convert from System.String to System.String[]
```

O screenshot final mostra `NETWORK ERROR`. Não promova nenhum desses restarts a
prova de `login-device` ou battle pass.

### CONFIRMADO — o harness observou o servidor errado

O APK conhecido e previamente verificado aponta para:

```text
https://doom.sualoja.app.br
```

As três tentativas de restart, porém, executaram o harness com:

```text
--server http://127.0.0.1:8080
```

Os dois health checks provam que são instâncias diferentes:

```text
local:  players=9,  uptime≈5072s
público: players=16, uptime≈86357s
```

Logo, o cursor `264` e o delta zero eram do servidor local, não necessariamente
do servidor chamado pelo APK. Essa é a principal causa operacional da patinação.

O código local atual em `server/src/jwt.js` emite `audience` e `aud` como arrays.
O erro `String -> String[]` indica que a resposta recebida pelo cliente veio de
uma implementação/configuração diferente ou desatualizada. Não altere novamente
o DTO do cliente antes de identificar a instância real.

### A VERIFICAR

- hash e host do APK realmente instalado no emulador;
- commit/código efetivo atualmente implantado no VPS;
- formato dos claims do JWT devolvido pelo VPS, observando somente tipos;
- token administrativo correto do VPS para captura incremental;
- se o ADB permanece estável durante uma janela inteira;
- se o restart chama `login-device` após corrigir alvo/servidor;
- se o fix do battle pass remove o `2300` no cliente;
- significado exato do `device_id` ao importar conta em outro dispositivo;
- condição e callback nativo exatos do popup Google.

### NÃO IMPLEMENTADO

Não existe hoje código de `RevivalAuthActivity`, `patch_revival_auth.py`, injeção
de launcher ou supressão do gate Google. Há somente o prompt de especificação.

## Fase 0 — inventário sem edição

1. Execute e guarde em `work/audit-opus/`:

```bash
git status --short
git diff --cached
git diff --stat
git log -8 --oneline
python run_tests.py
python scripts/verify_everything.py
```

2. Classifique cada arquivo alterado em um lote, sem mover nem descartar nada:

- **Lote A — cadeia de evidência:** harness, request log, fixtures, registro,
  gates e testes;
- **Lote B — extrator IL2CPP:** script, teste e skill;
- **Lote C — pipeline/toolchain/docs do Studio:** somente mudanças realmente
  necessárias e seus testes;
- **Lote D — battle pass:** código + teste + evidência real pendente;
- **Lote E — prompts/planos/docs históricos:** não misturar com código;
- **Lote F — scripts de setup/start do servidor:** auditar separadamente; não
  assuma que pertencem ao patch de autenticação.

3. Procure material proibido e segredos somente por padrões/redação; nunca
   imprima o valor encontrado.

4. Entregue ao Codex a tabela de lotes e divergências. Não edite ainda.

Pare para auditoria.

## Fase 1 — fechar os defeitos locais deixados pelo GLM

Faça mudanças mínimas, preservando o trabalho útil existente.

### 1.1 Gate Python único de verdade

`verify_everything.py` deve executar a mesma descoberta completa de
`run_tests.py`, sem uma lista manual que volta a deixar testes órfãos.

Solução preferida:

- chamar `python run_tests.py` como uma única camada; ou
- extrair e compartilhar a função de descoberta entre ambos.

Não mantenha duas fontes de verdade.

Teste obrigatório: criar temporariamente um `tests/**/test_*.py` sintético que
falha e provar que `verify_everything.py` fica vermelho. Não deixe o arquivo
sintético na árvore ao final.

### 1.2 Assinatura fatal ausente

Adicione ao harness, com teste unitário:

```text
Could not cast or convert from System.String to System.String[]
```

Classificação: `fatal`, porque o cliente rejeitou o token/payload e terminou em
`NETWORK ERROR`. Considere um padrão geral somente se ele não transformar ruído
inofensivo em fatal.

O early-stop também deve reconhecer a assinatura e não esperar quatro minutos
de uma execução já condenada.

### 1.3 Sincronização honesta do registro

Antes de rodar o gerador:

- valide as 10 fixtures client;
- confirme que vieram do boot3 válido;
- confirme `sanitized=true` e ausência de segredos;
- não crie fixture de `login-device` a partir dos restarts falhos.

Depois rode:

```bash
python scripts/generate_endpoint_matrix.py
python scripts/generate_endpoint_matrix.py --check
```

Não edite `compatibility.json` manualmente.

### 1.4 Coerência documental

Resolva a contradição sobre JWT somente com evidência:

- `research/DEAD-ENDS.md #9` ainda diz que token opaco deve ser mantido;
- o código/skill atual dizem que JWT com arrays foi validado.

Não escolha por preferência. Cite os boots que provaram cada etapa e atualize a
entrada antiga apenas quando a evidência do restart correto existir. Até lá,
marque a divergência como aberta; não reescreva governança para parecer pronta.

Execute `python run_tests.py`, `npm test` e `verify_everything.py`. Pare para
auditoria com diff e saídas.

## Fase 2 — tornar impossível observar o servidor errado

### 2.1 Provar o APK instalado

Recupere o ADB sem limpar dados. Como ele oscilou durante a auditoria, exija
estabilidade antes do teste:

```text
adb devices -l
adb get-state
adb shell getprop sys.boot_completed
```

Faça `am force-stop` no app; não use `pm clear`.

Obtenha o caminho e SHA-256 do `base.apk` instalado. Se precisar puxá-lo, use
somente `work/audit-opus/installed/`, que é ignorado. Rode
`verify_patched_apk.py` nesse APK para extrair/provar o host.

Registre no relatório:

```json
{
  "installed_apk_sha256": "...",
  "game_server_host": "...",
  "capture_server": "...",
  "same_target": true
}
```

### 2.2 Corrigir o harness contra recorrência

Acrescente um preflight que obrigue a declarar/provar o alvo quando houver
captura real. Uma interface aceitável:

```text
--apk <arquivo instalado/puxado>
--expected-game-host <host>
```

O harness deve falhar antes de abrir o jogo quando o host provado do APK e o
host de `--server` não representam a mesma instância administrativa.

Casos como proxy/túnel exigem um identificador de instância exposto pelo health
ou uma justificativa explícita no relatório. Comparar apenas `client_version` e
`api_version` é insuficiente — local e VPS têm os mesmos valores.

Adicione ao health um identificador não secreto de build/instância somente se
isso puder ser feito sem inventar contrato `game/*`. Exemplo: commit/build ID em
`/revival/health`, vindo de env/config de deploy. Não exponha segredo.

### 2.3 Credencial administrativa

Captura real exige token administrativo do **mesmo servidor**. Se o token do VPS
não estiver disponível, pare como `BLOQUEADO` e peça ao usuário. Nunca copie token
do config para relatório ou linha de comando visível.

Pare para auditoria com os testes do preflight.

## Fase 3 — resolver o drift local × VPS

Com o alvo provado:

1. compare health/build ID local e público;
2. capture uma resposta real de register/login-device no servidor correto;
3. decodifique o JWT somente em memória e registre apenas o tipo dos claims:

```json
{
  "aud": "array",
  "audience": "array",
  "sub": "string",
  "ubu_session_id": "integer"
}
```

Nunca grave o JWT.

Se o VPS estiver desatualizado, entregue antes do deploy:

- commit/diff que precisa subir;
- comandos de deploy já existentes no projeto;
- backup/rollback;
- serviços que serão reiniciados;
- preflight pós-deploy.

**Pare e peça autorização explícita.** Só depois faça deploy/restart remoto.

Após autorização, prove:

- health/build ID mudou;
- public preflight passou;
- `aud`/`audience` são arrays;
- `String -> String[]` desapareceu.

Não tente compensar servidor público antigo com patch no APK.

## Fase 4 — revalidar o restart e o battle pass

Use as credenciais já existentes no emulador. Não teste primeiro boot ainda.

Com o servidor e o cursor corretos:

1. tire baseline do request log do VPS;
2. `am force-stop`;
3. limpe somente o logcat;
4. abra o app;
5. capture até authentication + user-data + sequência de battle pass ou fatal;
6. escreva fixtures apenas se request e response estiverem pareados.

Critérios mínimos:

```text
game/auth/login-device -> 200/code 1000
game/player/game-data-token
game/player/user-data
game/battle-pass/end-season
game/battle-pass/start-season -> code 1000, não 2300
fallback delta = 0 nas rotas validadas
sem String -> String[]
sem Failed to launch
sem NETWORK ERROR
```

Se o cliente não chamar battle pass nesse restart, o fix permanece
`A VERIFICAR`; não force o registro para “validá-lo”.

Crie a fixture client de `login-device` somente nesta execução válida e com
segredos redigidos.

Pare para auditoria. Este é o gate que encerra o trabalho pendente do GLM.

## Fase 5 — fechar e separar os lotes do GLM

Depois da aprovação do restart:

```bash
python scripts/generate_endpoint_matrix.py
python scripts/generate_endpoint_matrix.py --check
python run_tests.py
cd server && npm test
cd ..
python scripts/verify_everything.py
git diff --check
```

Entregue:

- diff por lote A–F;
- arquivos que devem ser mantidos, revisados ou excluídos, sem excluir nada;
- resultados dos gates;
- fixtures novas e provenance;
- itens ainda abertos;
- nenhum commit/push.

O Codex decide o destino de cada lote. Não misture o encerramento do GLM com a
implementação da Activity.

## Fase 6 — implementar a autenticação Revival

Somente após o Codex aprovar a linha de base, siga
`docs/PROMPT-GLM-5.1-REMOVER-GOOGLE-PLAY-GAMES.md`, com estas prioridades:

### 6.1 Decompilação dirigida

Não faça full-decompile indiscriminado. Use:

- metadata extractor para nomes/campos/métodos;
- UnityPy 1.25.3 para TextAssets/prefabs/bundles;
- Apktool 3.0.3 para Manifest/resources/smali;
- Il2CppDumper + Ghidra apenas nos métodos de autenticação e CredentialStore.

Prove:

- condição que abre o popup Google;
- callback Cancel;
- caminho até register/login-device;
- semântica de `hasCancelledLogin`/`hasLoggedOut`;
- formato/gravação de `gpg.config`;
- `CredentialStore.Create/Load/Save`;
- regra do `device_id` ao importar uma conta.

Dumps ficam em `work/`, nunca no Git.

### 6.2 Escolha de arquitetura explícita

Compare antes de implementar:

1. Java próprio + `javac`/`d8`/`aapt2` com toolchain detectada/pinada;
2. smali próprio via Apktool já pinado;
3. reutilização de UI Unity existente com patch nativo comprovado.

Escolha com matriz de manutenção, reprodutibilidade e risco. Pare para auditoria.

A arquitetura preferencial continua sendo:

```text
RevivalAuthActivity como único MAIN/LAUNCHER
  -> credentials.json válido: abre MessagingUnityPlayerActivity
  -> ausente: Criar conta | Entrar
  -> sucesso: escrita atômica no diretório do próprio app
  -> abre a Unity
```

Preserve a Activity Unity e seus deep links. Não adicione MonoBehaviour C# novo
em um build IL2CPP.

### 6.3 Separar supressão Google de credenciais

A tela Revival não basta se o popup Google continuar aparecendo. Implemente duas
provas separadas:

- Activity cria/importa credenciais aceitas pela Unity;
- gate Google é suprimido pelo menor patch comprovado.

Ordem para o gate:

1. configuração local gerada pela própria Activity;
2. configuração/asset existente;
3. patch ARM64 mínimo, com preimage e offsets;
4. nenhuma remoção massiva de GMS.

Se usar seeding via ADB, marque `rig-only`; nunca o promova a solução final.

### 6.4 Login em outro dispositivo

Não invente `device_id`. Se a decompilação não provar como criá-lo, pare e
apresente as três opções do prompt anterior:

- reproduzir `CredentialStore.Create`;
- endpoint explicitamente `/revival/*` para bootstrap da Activity;
- MVP limitado a registro + importação de backup.

O usuário/Codex decide.

## Fase 7 — E2E final

Em instalação descartável ou snapshot autorizado:

1. primeiro boot sem Google configurado;
2. tela Revival aparece;
3. Criar conta registra e mostra recovery de forma segura;
4. Unity chega a authentication + user-data;
5. restart chama login-device e mantém a mesma conta;
6. Entrar funciona em instalação limpa;
7. popup Google não aparece;
8. rotas Google auth/link não são chamadas;
9. fluxo de menu/jogo não tem CRC/fatal/fallback;
10. APK final é assinado e verificado após assinatura.

Rode:

```bash
python run_tests.py
cd server && npm test
cd ..
python scripts/generate_endpoint_matrix.py --check
python scripts/verify_everything.py --server <servidor-real> --strict-research
python scripts/verify_patched_apk.py --apk <apk-final-assinado> --server <host>
```

## Definition of Done

- [ ] Trabalho útil do GLM foi separado e auditado, não refeito às cegas.
- [ ] `verify_everything.py` executa todos os testes autodescobertos.
- [ ] Cast `String -> String[]` é fatal no harness e tem regressão.
- [ ] Registro/matriz estão sincronizados.
- [ ] APK instalado e servidor de captura são a mesma instância provada.
- [ ] VPS executa o código esperado e JWT tem arrays reais.
- [ ] `login-device` tem fixture client sanitizada.
- [ ] Restart preserva a conta e chega a user-data.
- [ ] Fix de battle pass foi validado no cliente ou permanece honestamente aberto.
- [ ] Activity Revival cria e entra em conta sem segredo em log.
- [ ] `credentials.json` é aceito pela Unity.
- [ ] Popup/rotas de autenticação Google não aparecem no fluxo normal.
- [ ] APK final assinado passa no verificador pós-assinatura.
- [ ] Nenhum material proprietário/segredo está staged ou versionado.
- [ ] Codex aprovou cada gate antes de commit, push ou deploy.

## Condições de parada

Pare como `BLOQUEADO`, com evidência, se:

- faltar token administrativo do servidor realmente chamado pelo APK;
- o VPS exigir deploy sem autorização;
- o ADB não permanecer estável;
- o APK instalado não puder ser identificado/verificado;
- o login exigir inventar `device_id`;
- o gate Google não puder ser localizado com preimage comprovada;
- a única solução proposta remover todas as bibliotecas Google;
- o diff do GLM não puder ser separado sem sobrescrever trabalho alheio;
- qualquer gate falhar e a única saída for maquiar fixture/registro.

Não use mais tempo repetindo restart contra o servidor errado. Pare, reporte o
alvo divergente e peça o dado/autoridade que falta.
