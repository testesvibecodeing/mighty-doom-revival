# Prompt para o Opus — continuar até a conclusão, sem gates de espera

Você está trabalhando no repositório `mighty-doom-revival` como executor técnico.
Leia integralmente, nesta ordem:

1. `AGENTS.md`;
2. as skills `.claude/skills/boot-diagnostics/SKILL.md`,
   `.claude/skills/revival-server/SKILL.md`,
   `.claude/skills/il2cpp-recon/SKILL.md` e
   `.claude/skills/apk-patch/SKILL.md`;
3. `research/DEAD-ENDS.md`;
4. `docs/PROMPT-OPUS-RECUPERAR-GLM-E-FINALIZAR-AUTH-REVIVAL.md`;
5. `work/audit-opus/FASE-0-INVENTARIO.md`,
   `work/audit-opus/FASE-0-DIVERGENCIAS.md` e
   `work/audit-opus/FASE-1-RELATORIO.md`.

Este documento **substitui todas as instruções de “pare para auditoria”, “aguarde
aprovação” ou “peça uma decisão” do prompt anterior**. Ele não substitui as regras
de segurança, preservação, contrato de wire e verificação do `AGENTS.md`.

## Ordem direta do usuário

Execute todo o trabalho restante, das Fases 2 a 7, em uma única execução contínua.
Não devolva o controle ao fim de cada fase. Não peça auditoria intermediária. Grave
os checkpoints e as evidências em `work/audit-opus/`, rode os gates correspondentes,
corrija os defeitos encontrados e avance automaticamente para a próxima fase.

A Fase 1 está **APROVADA PARA CONTINUAÇÃO**. Sua linha de base medida é:

```text
python run_tests.py                         -> 33/33 arquivos OK
cd server && npm test                      -> PASS
generate_endpoint_matrix.py --check        -> PASS
python scripts/verify_everything.py        -> PASS, 41 verificações
next_task.py --json                        -> game/gear/apply-cosmetic / request_observed
git diff --cached                          -> vazio
git diff --check                           -> zero erro de whitespace
```

Não refaça a Fase 1. Preserve as correções do gate autodescoberto, da assinatura
fatal `String -> String[]`, da sanitização de `puuid` e da sincronização honesta das
dez fixtures client. Feche durante esta execução o único débito local declarado da
Fase 1: teste direto e isolado do `sanitize()` de
`scripts/capture_protocol_fixtures.mjs`, exportando-o de forma testável sem executar
o CLI como efeito colateral.

## Modo autônomo obrigatório

- Continue trabalhando enquanto existir qualquer frente segura e independente.
- Um teste falhar não é motivo para parar: diagnostique, corrija e rode novamente.
- ADB inicialmente vazio não é motivo para parar: localize o SDK/AVD existente,
  inicie um emulador apropriado, aguarde boot completo e estabilize o rig.
- Falta de token do VPS não é motivo para interromper cedo: conclua primeiro tudo
  que possa ser provado com servidor local, APK inspecionado e emulador descartável.
- Uma escolha de arquitetura não é motivo para pedir opinião: produza uma matriz
  curta, escolha a opção de menor invasividade que satisfaça os gates e registre a
  justificativa.
- Resultado inconclusivo em um boot não autoriza repetição cega. Melhore a
  instrumentação, isole a variável e execute a próxima experiência discriminante.
- Mantenha, em cada relatório, `CONFIRMADO` separado de `A VERIFICAR` e inclua os
  comandos, exits e caminhos das evidências.
- Não faça commit nem push. Não use `git add .`, não apague alterações alheias e
  não normalize EOL de arquivos que não precisem de mudança de conteúdo.
- Não versione nem exponha APK, dumps, logcats, pcaps, screenshots, keystores,
  certificados, tokens, JWTs, credenciais ou identificadores pessoais crus.

## Autoridade operacional dentro do escopo

O usuário quer o fluxo inteiro concluído. Portanto, dentro deste projeto:

- você pode iniciar/reiniciar o servidor **local**, iniciar emulador, criar snapshot
  ou AVD descartável, instalar o APK de teste e usar `am force-stop`;
- não use `pm clear` no AVD que contém a conta/progresso existente;
- instalação limpa deve ocorrer em snapshot/clone/AVD descartável, ou somente após
  backup verificável e restaurável;
- você pode executar o deploy/restart estritamente necessário no **VPS Revival já
  configurado no projeto**, caso o acesso já esteja disponível e o mecanismo de
  deploy existente possa ser provado. Antes, faça backup, registre plano de
  rollback, valide os alvos absolutos e não imprima segredos;
- se o acesso remoto não estiver disponível, não invente credenciais e não abra
  acesso inseguro. Continue todas as frentes locais e relate esse único bloqueio
  apenas no final;
- não realize mudanças externas que não pertençam ao servidor Revival deste projeto.

## Sequência de execução contínua

### 1. Consolidar a árvore sem destruir trabalho

Comece com `git status`, `git diff`, `git diff --cached` e o inventário A–F da Fase
0. Trate a árvore atual como trabalho vivo do usuário.

- Preserve e finalize os lotes A–E quando forem necessários ao objetivo.
- Audite os lotes B e C com suas regressões existentes; não aceite mudanças no
  extrator IL2CPP ou pipeline só porque os testes antigos passam.
- Para o lote D, mantenha o fix de battle pass apenas se o teste servidor e a prova
  no cliente sustentarem o comportamento.
- Atualize documentos do lote E apenas para fatos efetivamente medidos.
- Os quatro wrappers quebrados do lote F continuam excluídos da solução. Não os
  versione. Não os apague; apenas registre a disposição final recomendada.
- Confirme que `scripts/inject_loading_screen.py` não ganhou mudança sem conteúdo.

Grave `work/audit-opus/FASE-2A-CONSOLIDACAO.md` e siga, sem esperar resposta.

### 2. Construir prova de aterrissagem, não só prova de hostname

Corrija a premissa incompleta da Fase 2 antiga. `--expected-game-host` é apenas um
guard secundário: todas as execuções anteriores declararam o mesmo `--server`,
inclusive o boot bom, portanto essa comparação isolada não prova onde o tráfego
aterrissou.

Implemente no health Revival um identificador não secreto de instância/build,
derivado de env/config de deploy e com fallback local explícito. Não altere nem
invente contrato `game/*` para isso.

O preflight/harness deve correlacionar, no mínimo:

```text
SHA-256 e host do base.apk realmente instalado
identificador de instância/build do servidor observado
cursor de /revival/requests antes e depois
janela temporal do logcat após force-stop + launch
estado/ação do cliente que deveria disparar rede
delta de requests pareados e de fallbacks
```

Adicione um desfecho precoce estruturado `no_observed_traffic` ou `inconclusive`
quando a ação deveria gerar rede, o logcat está na janela correta e o cursor da
instância observada não avança. Esse resultado **não** pode virar sucesso, nem pode
ser atribuído automaticamente a H1 (servidor público antigo) ou H2 (sessão
persistida). Acrescente testes cobrindo sucesso, host divergente, build/instância
divergente, cursor imóvel, cursor avançando fora da janela e ausência legítima de
ação de rede.

Não passe token administrativo na linha de comando se ele puder aparecer em lista
de processos ou relatório. Use entrada segura/env já prevista e sempre redija o
valor.

### 3. Estabilizar ADB e provar o APK instalado

Localize `adb`, SDK e AVDs sem modificar dados. Se nenhum emulador estiver ativo,
inicie um AVD existente compatível; se isso ameaçar a conta preservada, clone/crie
um AVD descartável para os testes destrutivos. Espere até todos passarem:

```text
adb devices -l
adb get-state
adb shell getprop sys.boot_completed
```

Use `am force-stop`, nunca `pm clear` no AVD primário. Obtenha `pm path`, puxe o
`base.apk` apenas para `work/audit-opus/installed/`, calcule SHA-256 e execute
`verify_patched_apk.py` nele. Registre host provado, instância de captura e se o
cursor avançou na janela observada.

Se não houver AVD utilizável, ainda assim conclua código, testes unitários,
decompilação dirigida, build e verificação estática do APK. Só classifique o E2E
dinâmico como bloqueado ao final, com o erro concreto de inicialização do AVD.

### 4. Resolver drift local × VPS e validar JWT

Compare local e público por build/instance ID, uptime, versão e comportamento; não
use apenas `client_version`/`api_version`. Capture `register` e `login-device` na
mesma instância comprovada pelo cursor.

Decodifique o JWT apenas em memória e persista somente os tipos:

```json
{"aud":"array","audience":"array","sub":"string","ubu_session_id":"integer"}
```

Nunca grave o JWT. Se o VPS estiver desatualizado e o acesso já estiver disponível:

1. identifique exatamente o serviço e diretório remoto;
2. faça backup recuperável de código/config/dados afetados;
3. registre comandos e rollback sem segredos;
4. faça o deploy pelo mecanismo existente;
5. reinicie somente o serviço necessário;
6. prove novo build ID, health, `uts`, JWT com arrays e rollback disponível.

Se a credencial administrativa pública faltar, use uma instância local controlada
para avançar as provas possíveis. Não trate uma captura local como evidência do VPS.

### 5. Revalidar restart, login-device e battle pass

No AVD com credenciais preservadas e na instância comprovada:

1. registre cursor/build baseline;
2. `am force-stop`;
3. limpe somente logcat;
4. abra o app;
5. capture até autenticação, user-data e battle pass, ou fatal;
6. aceite fixture apenas com request/response pareados e sanitizados.

Critérios:

```text
game/auth/login-device -> HTTP válido, code 1000
game/player/game-data-token
game/player/user-data
game/battle-pass/end-season
game/battle-pass/start-season -> code 1000, não 2300
fallback delta = 0 para as rotas declaradas validadas
sem String -> String[]
sem Failed to launch
sem NETWORK ERROR
```

Crie a fixture client de `login-device` apenas a partir dessa execução válida. Se o
cliente não chamar battle pass, deixe-o `A VERIFICAR`; não fabrique observação.
Reavalie `research/DEAD-ENDS.md #9` somente com essa evidência nova de restart.

### 6. Implementar autenticação Revival e suprimir Google Play Games

Faça decompilação **dirigida**. Use o extrator metadata, UnityPy 1.25.3, Apktool
3.0.3 e, somente onde necessário, Il2CppDumper/Ghidra nos métodos de autenticação e
CredentialStore. Dumps permanecem em `work/`.

Prove antes de escolher o patch:

- condição real que abre o popup Google Play Games;
- comportamento do botão Cancel;
- `hasCancelledLogin`/`hasLoggedOut`;
- formato e localização de `gpg.config` e `credentials.json`;
- `CredentialStore.Create/Load/Save`;
- regra do `device_id` e caminho até `register`/`login-device`.

Compare Java próprio compilado com toolchain detectada/pinada, smali próprio e
reuso de UI existente. Escolha automaticamente a opção mais reprodutível e menos
invasiva que possa ser testada. Não adicione MonoBehaviour C# a IL2CPP.

Arquitetura-alvo, salvo prova técnica contrária:

```text
RevivalAuthActivity = MAIN/LAUNCHER
  credentials válidas -> abre MessagingUnityPlayerActivity
  credentials ausentes -> Criar conta | Entrar
  sucesso -> escrita atômica no armazenamento interno do próprio package
  depois -> abre Unity preservando deep links e extras necessários
```

A Activity deve usar HTTPS, timeout, validação de resposta, mensagens de erro
úteis, prevenção de duplo clique, segredo nunca em log e armazenamento privado. O
framework Python deve orquestrar compilação/injeção/manifest/pipeline de forma
idempotente e testável; Python não substitui a UI Android que roda dentro do APK.

Separe duas provas:

1. a Activity cria/importa credenciais aceitas pela Unity;
2. o gate/popup Google é suprimido pelo menor patch comprovado.

Para o gate Google, tente nesta ordem: configuração local gerada pela Activity,
configuração/asset existente, patch ARM64 mínimo com preimage e offsets. Não remova
em massa bibliotecas GMS e não marque seeding ADB como solução final.

Não invente campo `game/*`. Se a decompilação dirigida não provar a geração de
`device_id`, escolha automaticamente a primeira alternativa comprovável:

1. reproduzir `CredentialStore.Create`;
2. usar/criar um bootstrap claramente separado em `/revival/*`, com autenticação,
   testes e documentação próprios, sem fingir que ele pertence ao protocolo do game;
3. limitar o MVP a registro + importação segura de backup somente se as duas
   anteriores forem tecnicamente inviáveis e isso for demonstrado.

Continue sem pedir decisão intermediária.

### 7. Integrar o patcher e produzir o E2E final

Integre a Activity e a supressão Google ao pipeline real em
`scripts/revival_editor/pipeline.py` e módulos adequados. Exija:

- detecção de pré-condição e pós-condição;
- segunda execução idempotente;
- falha segura com relatório útil;
- testes unitários/integrados sem APK proprietário versionado;
- orçamento de hostname decidido por `check_patch_length.py`;
- `zero_catalog_crc` para qualquer bundle alterado;
- Java 17 e toolchain pinada do projeto;
- assinatura e só então `verify_patched_apk.py` no artefato final.

Em AVD descartável/snapshot autorizado, prove:

```text
primeiro boot sem conta Google configurada
tela Revival aparece
Criar conta registra sem segredo no log
Unity chega a authentication + user-data
restart chama login-device e preserva a conta
Entrar funciona numa instalação limpa
popup Google não aparece
rotas Google auth/link não são chamadas
menu/jogo não apresenta CRC, fatal ou fallback inesperado
APK final assinado passa no verificador pós-assinatura
```

Capture somente evidência sanitizada. Não inclua APK ou artefato proprietário no
Git.

### 8. Gates finais e autocorreção

Rode, corrija qualquer falha e repita até todos os gates aplicáveis ficarem verdes:

```bash
python run_tests.py
cd server && npm test
cd ..
python scripts/generate_endpoint_matrix.py
python scripts/generate_endpoint_matrix.py --check
python scripts/verify_everything.py --server <instancia-comprovada> --strict-research
python scripts/verify_patched_apk.py --apk <apk-final-assinado> --server <host>
git diff --check
git status --short
git diff --cached
```

Não promova rota por resposta vazia de `RESEARCH_MODE`. Não transforme falta de
evidência em fixture ou `client_validated`.

## Checkpoints sem pausa

Ao terminar cada bloco, escreva um arquivo em `work/audit-opus/`, por exemplo:

```text
FASE-2-ATERRISSAGEM.md
FASE-3-DRIFT-DEPLOY.md
FASE-4-RESTART-BATTLE-PASS.md
FASE-5-LOTES-FINAIS.md
FASE-6-AUTH-REVIVAL.md
FASE-7-E2E-FINAL.md
RELATORIO-FINAL.md
```

Cada checkpoint contém fatos, hipóteses abertas, arquivos alterados, comandos/exits
e evidências sanitizadas. **Depois de gravá-lo, continue imediatamente.** Não envie
“pronta para auditoria” e não espere o Codex.

## Quando finalmente devolver o controle

Devolva o controle apenas em uma destas duas situações:

### CONCLUÍDO

Todo o Definition of Done do prompt anterior foi satisfeito, com uma ressalva
honesta apenas para fluxo que comprovadamente não foi emitido pelo cliente. Entregue
um único relatório final com:

- resultado funcional;
- diff separado por lotes;
- todos os gates e exits;
- host, SHA e build/instância provados, sem segredo;
- fixtures e provenance;
- caminho do APK final ignorado pelo Git e sua verificação pós-assinatura;
- rollback de eventual deploy;
- `git status`, `git diff --cached` e confirmação de material proprietário/segredo
  fora do versionamento.

### BLOQUEADO APÓS ESGOTAR AS FRENTES INDEPENDENTES

Só use este estado quando tiver concluído tudo que não depende do bloqueio e uma
entrada externa for realmente indispensável, por exemplo credencial remota ausente
ou impossibilidade comprovada de iniciar qualquer AVD. Nesse caso, peça **uma única
vez, no relatório final**, o dado exato que falta e inclua:

- três tentativas discriminantes já executadas;
- saídas/erros e caminhos das evidências;
- tudo que foi concluído apesar do bloqueio;
- o comando exato que continuará a execução após o dado chegar.

Não são condições de parada: necessidade de escolher arquitetura, falha corrigível
de teste, ADB inicialmente vazio, documentação divergente, ausência de aprovação do
Codex entre fases, ou necessidade de reexecutar um build após corrigir um defeito.

