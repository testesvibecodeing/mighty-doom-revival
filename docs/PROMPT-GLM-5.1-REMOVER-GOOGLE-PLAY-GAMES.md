# Prompt executor para GLM-5.1 — remover o bloqueio do Google Play Games e criar autenticação Revival

> Cole este documento inteiro em uma nova sessão do GLM-5.1 aberta na raiz do
> repositório. O GLM é o **executor** e o Codex é o **auditor**. Não faça commit
> nem push antes da auditoria de cada fase.

## Missão

Você está trabalhando em:

```text
D:\DevPrograms\mighty-doom-revival
```

Implemente, com evidência real no emulador, uma autenticação própria do Revival
que:

1. não dependa de uma conta Google Play Games;
2. não exiba o popup `USE GOOGLE PLAY GAMES?` no boot normal;
3. permita **criar uma conta Revival** e **entrar em uma conta Revival**;
4. entregue ao cliente Unity as credenciais no formato que ele já entende;
5. preserve o fluxo real de `/game/auth/register` e
   `/game/auth/login-device`;
6. seja gerada/injetada pelo framework Python e integrada ao pipeline existente;
7. produza um APK final assinado e verificado, sem material proprietário no Git.

Não interprete “criar a tela pelo Python” como executar Python dentro do
Android. O Python deve orquestrar a geração, compilação e injeção de uma tela
Android nativa ou aplicar uma alteração comprovada no cliente. O runtime do APK
continua sendo Android + Unity IL2CPP.

## Autoridade e ordem de leitura

Leia completamente, nesta ordem, antes de editar:

1. `AGENTS.md`;
2. `research/DEAD-ENDS.md`;
3. `.claude/skills/boot-diagnostics/SKILL.md`;
4. `.claude/skills/il2cpp-recon/SKILL.md`;
5. `.claude/skills/apk-patch/SKILL.md`;
6. `.claude/skills/revival-server/SKILL.md` se tocar `server/src/**`;
7. `scripts/revival_editor/pipeline.py` e os patchers atuais;
8. `scripts/client_harness.py` e suas fixtures;
9. os testes relacionados.

Este documento é uma ordem de execução, não uma fonte que autoriza inventar
contratos. Quando uma afirmação daqui divergir do APK, do código atual ou de uma
captura real, pare e apresente a divergência ao auditor.

## Regras inegociáveis

- Nunca baixe, copie para o Git, publique ou redistribua APK, assets, bundles,
  dumps IL2CPP, logcats, screenshots, keystores ou certificados.
- Use somente o APK legítimo já presente em `input/mighty-doom.apk`.
- Nunca use `git add -f`, `git add .`, `git reset --hard` ou descarte alterações
  de outro agente.
- A árvore pode estar suja por outra execução. Faça `git status --short` e
  `git diff --cached` antes de cada fase e não sobrescreva trabalho alheio.
- Não faça commit nem push. Pare ao final de cada fase com um pacote de auditoria.
- Não invente rota `game/*`, request, response, wire name, tipo, nulabilidade ou
  código de erro.
- Não grave `password`, `device_id`, recovery code, JWT ou token administrativo
  em logs, relatórios, fixtures ou testes versionados.
- Não apague dados do app/emulador sem autorização expressa. Use snapshot ou
  instalação descartável para testar primeiro uso.
- Não remova bibliotecas Google em massa. Firebase, notifications, billing e a
  activity Unity atual compartilham dependências Google; uma remoção cega pode
  quebrar o boot.
- Alterou bundle em `assets/aa/**`: execute `zero_catalog_crc` e prove o CRC.
- Não declare APK pronto sem `scripts/verify_patched_apk.py` passando no arquivo
  final, depois da assinatura.
- Não use uma UI falsa que diz “login concluído” sem provar que a Unity leu as
  credenciais e avançou pelo fluxo autenticado.

## Linha de base medida pelo auditor em 2026-08-19

Trate os itens desta seção como `CONFIRMADO` enquanto os comandos e arquivos
citados continuarem reproduzindo o mesmo resultado.

### CONFIRMADO — Google Play Games não é necessário para o backend Revival

O relatório real mais recente do harness contém:

```text
work/harness/fase4-boot3.json/harness-20260819-222115.json
verdict = flow_validated
game/auth/register -> HTTP 200 / code 1000
game/player/game-data-token
game/player/user-data
game/armory/get
game/events/get-schedule
game/events/get-progress
game/tutorial/complete-sequence
game/auth/login-google-play-games não foi necessário
```

Na mesma família de execuções, o logcat registrou o erro do plugin:

```text
*** [Play Games Plugin 0.11.01] ... ERROR: Returning an error code.
GooglePlayGames.OurUtils.PlayGamesHelperObject:Update()
```

Portanto, o diagnóstico correto não é “o servidor exige Google”. O cliente já
consegue registrar uma conta de dispositivo no Revival e carregar dados. O
bloqueio remanescente é o gate/popup do cliente e a experiência de selecionar ou
recuperar uma conta.

### CONFIRMADO — ponto de controle IL2CPP

Extração read-only do metadata real encontrou:

```text
Ubu.GameController
  TryIdentityAutoAuthenticate
  TryIdentityRequestAuthenticate
  TryLoginWithIdentity
  RegisterUserAccount
  LoginWithDeviceCredentials
  CheckDeviceCredentials
  GetIdentityAuthenticatorForPlatform
  GetIdentityLinkRequestStringsForProvider

Ubu.GooglePlay.GooglePlayController
  AutoAuthenticate
  RequestAuthenticate
  LoginToGameServer
  StartManualAuthenticationFlow
  AuthenticateCallback

Ubu.GooglePlay.GooglePlayLocalConfig
  hasCancelledLogin
  hasLoggedOut
  Save
  Load
  Delete

Ubu.UI.OkCancelPopup
  okCallback
  cancelCallback
  OnOkClicked
  OnCancelClicked

Ubu.CredentialStore
  Create
  Load
  TryLoadCredentials
  Save
  Delete
```

O popup da captura usa as chaves reais:

```text
ui_identityLinkRequest_googlePlay_title
ui_identityLinkRequest_googlePlay_body
```

No TextAsset inglês elas resolvem para o título e corpo vistos na imagem. Isso
liga a captura ao fluxo `GetIdentityLinkRequestStringsForProvider` + popup
`OkCancelPopup`; não é uma tela nativa do SDK Google.

### CONFIRMADO — ponte de credenciais já existente

No emulador atual, o cliente criou estes arquivos em seu diretório externo
privado:

```text
/storage/emulated/0/Android/data/com.bethsoft.ubu/files/gpg.config
/storage/emulated/0/Android/data/com.bethsoft.ubu/files/credentials.json
```

`gpg.config` serializa `GooglePlayLocalConfig` e contém os campos
`hasCancelledLogin` e `hasLoggedOut`.

`credentials.json` é lido por `Ubu.CredentialStore` e contém exatamente:

```text
version
user_id
device_id
password
region
platform
```

Na amostra local medida, sem expor os valores secretos:

```text
version = 3
user_id = inteiro
device_id = string UUID de 36 caracteres
password = string de 32 caracteres
region = "US"
platform = 4
```

O fixture real de registro está em:

```text
tests/fixtures/protocol/client/auth/game__auth__register.json
```

Ele prova que o cliente enviou:

```json
{
  "platform_id": 4,
  "client_version": "1.13.1",
  "region": "US"
}
```

e recebeu `user_id`, `device_id`, `password`, `recovery_code`, `token`,
`session_id`, `puuid` e `legal` com `code=1000`.

### A VERIFICAR — não promova a fato sem decompilação/captura

- qual método cria o popup no primeiro boot e em quais condições;
- o significado exato dos dois booleanos de `gpg.config` em cada caminho;
- se apenas persistir `hasCancelledLogin=true` suprime o popup para sempre;
- se o callback Cancel já continua diretamente para `RegisterUserAccount` ou
  `LoginWithDeviceCredentials`;
- como `CredentialStore.Create` escolhe `device_id`, `region` e `platform`;
- o comportamento de `CheckDeviceCredentials` com uma credencial importada;
- os headers reais de `login-device` no primeiro login e após restart;
- se um `device_id` novo pode ser usado ao importar uma conta existente;
- se a Unity tolera escrita externa do `credentials.json` antes de iniciar;
- se é necessário desabilitar também a inicialização silenciosa do
  `GooglePlayController` ou somente o prompt.

## Arquitetura-alvo

Implemente em duas camadas independentes e auditáveis.

### Camada A — retirar o gate Google sem quebrar o login por dispositivo

Use a primeira estratégia comprovada que funcionar, nesta ordem:

1. persistir/semear corretamente `GooglePlayLocalConfig` para respeitar o
   cancelamento e seguir pelo device auth;
2. alterar o asset/configuração que decide o prompt, preservando o callback de
   registro/login por dispositivo;
3. patch nativo ARM64 mínimo em `libil2cpp.so`, com preimage exata, para pular
   somente o pedido Google e cair no caminho de device auth;
4. interceptar o launcher com uma activity Revival e iniciar a activity Unity
   somente depois de preparar as credenciais.

Não troque apenas os textos do popup. Não transforme o botão `SIGN IN` em uma
promessa visual sem mudar o fluxo real.

### Camada B — tela de login e registro Revival

A solução preferencial é uma activity Android própria, criada a partir de fonte
versionável e injetada pelo pipeline Python:

```text
RevivalAuthActivity (launcher)
  -> se credentials.json válido existe: abre MessagingUnityPlayerActivity
  -> se não existe: mostra Criar conta / Entrar
  -> sucesso: grava credenciais de forma atômica
  -> abre com.google.firebase.MessagingUnityPlayerActivity
```

Preserve a activity Unity original, seus meta-dados e seus filtros de deep link.
Mova apenas o filtro `MAIN/LAUNCHER` para a activity Revival, ou use outra
solução que prove não haver dois launchers concorrentes.

Não adicione um novo `MonoBehaviour` C#: este APK é IL2CPP e não carregará
arbitrariamente uma DLL Managed nova como um jogo Mono. Se optar por reutilizar
UI Unity existente, prove o callback nativo correspondente e todos os offsets.

## Fases obrigatórias

### Fase 0 — congelar a linha de base

1. Execute `git status --short`, `git diff --cached` e registre somente a lista
   de arquivos, sem segredos.
2. Identifique a execução anterior ainda não auditada. Não misture esta tarefa
   com mudanças pendentes do prompt de correção do framework.
3. Rode os testes atuais antes de editar:

```bash
python scripts/verify_everything.py
```

4. Verifique o APK assinado atual e guarde o relatório apenas em `work/`.
5. Entregue ao auditor: HEAD, status, testes e hashes dos APKs de entrada/saída.

Pare para auditoria.

### Fase 1 — reproduzir Cancel, Sign In e restart

Use uma instalação descartável ou snapshot. Não limpe a instalação principal.

Capture separadamente:

1. primeiro boot sem credenciais, escolhendo `CANCEL`;
2. restart com as credenciais criadas;
3. primeiro boot escolhendo `SIGN IN`, com o Google indisponível;
4. restart após o erro Google.

Para cada cenário, registre em `work/`:

- janela de logcat;
- sequência temporal real de endpoints;
- requests/responses sanitizados;
- presença e estrutura, nunca os valores secretos, de `gpg.config` e
  `credentials.json`;
- tela final atingida;
- se o popup reaparece.

O cenário só é conclusivo com `client_harness.py`, milestones e captura do
servidor. “O app ficou aberto” não é sucesso.

Pare para auditoria com uma tabela `CONFIRMADO`/`A VERIFICAR`.

### Fase 2 — decompilação dirigida, não dump indiscriminado

Use as ferramentas adequadas a cada camada:

- `scripts/dump_il2cpp_metadata.py`: nomes, campos, métodos, rotas e DTOs;
- UnityPy 1.25.3: TextAssets, prefabs e bundles;
- Apktool 3.0.3: Manifest, resources e smali Android;
- Il2CppDumper + Ghidra: somente para resolver os métodos IL2CPP necessários.

Resolva o endereço e o fluxo de controle de:

```text
Ubu.GameController.TryIdentityAutoAuthenticate
Ubu.GameController.TryIdentityRequestAuthenticate
Ubu.GameController.RegisterUserAccount
Ubu.GameController.LoginWithDeviceCredentials
Ubu.GameController.CheckDeviceCredentials
Ubu.GameController.GetIdentityLinkRequestStringsForProvider
Ubu.GooglePlay.GooglePlayController.get_IsAutomaticAuthenticationAllowed
Ubu.GooglePlay.GooglePlayController.RequestAuthenticate
Ubu.GooglePlay.GooglePlayController.StartManualAuthenticationFlow
Ubu.GooglePlay.GooglePlayLocalConfig.Load/Save
Ubu.CredentialStore.Create/Load/TryLoadCredentials/Save
```

O relatório desta fase deve conter:

- ferramenta e versão;
- SHA-256 do metadata e do `libil2cpp.so` analisados;
- tipo, método, RVA/offset quando aplicável;
- pseudocódigo mínimo relevante;
- condição que abre o popup;
- callback de Cancel;
- caminho posterior até register/login-device;
- layout e forma de gravação de ambos os arquivos locais;
- distinção explícita entre fato observado e inferência.

Mantenha dumps em `work/`; nunca os versione.

Pare para auditoria. Não aplique patch binário antes desta revisão.

### Fase 3 — especificar o contrato da tela Revival

Antes de implementar, escreva testes/fixtures sintéticos para esta máquina de
estados:

```text
START
  -> credenciais válidas -> abrir Unity
  -> sem credenciais -> AUTH_SCREEN

AUTH_SCREEN
  -> Criar conta -> register real -> salvar -> exibir recovery -> abrir Unity
  -> Entrar -> login real -> salvar formato exato -> abrir Unity
  -> erro de rede -> continuar na tela com mensagem e retry
  -> credenciais inválidas -> mensagem sem apagar progresso existente
```

Requisitos mínimos da UI:

- português claro;
- campos de login compatíveis com o contrato comprovado;
- senha oculta por padrão;
- botão de mostrar/ocultar senha;
- estado de carregamento que bloqueie clique duplo;
- erro de rede, erro de credenciais e erro de servidor separados;
- confirmação explícita e copiável do ID/recovery code no registro;
- nenhum segredo em logcat;
- opção de voltar sem corromper credenciais existentes;
- layout utilizável em retrato, inclusive no tamanho da captura fornecida.

Não invente email/username se o servidor e o cliente usam `user_id` numérico e
password. Uma UX mais amigável exige uma rota administrativa Revival separada e
um contrato aprovado pelo auditor; não a crie implicitamente.

#### Gate específico do login em outro dispositivo

O response real de `login-device` e o comportamento do `device_id` precisam ser
provados antes de gravar `credentials.json`. Se o endpoint não devolver os dados
necessários, apresente uma destas opções ao auditor:

1. reproduzir exatamente a criação local de `CredentialStore.Create`, comprovada
   pela decompilação;
2. adicionar um endpoint **explicitamente Revival**, fora de `game/*`, para
   bootstrap autenticado da activity;
3. limitar o primeiro MVP a registro + importação de um backup de credenciais,
   deixando login remoto como bloqueado documentado.

Não escolha silenciosamente.

Pare para auditoria com o contrato e os testes inicialmente vermelhos.

### Fase 4 — implementar o patcher Python e a activity

Crie uma unidade coesa; nomes sugeridos, não obrigatórios:

```text
scripts/patch_revival_auth.py
scripts/revival_auth/
  android/                 # fonte própria, nunca código proprietário
  build.py
  verify.py
tests/test_patch_revival_auth.py
```

Integre ao serviço em `scripts/revival_editor/pipeline.py`; não ressuscite
wrappers `.bat/.sh` orquestradores aposentados.

O patcher deve:

- ter modo `--analyze` sem mutação;
- identificar build/SHA suportado e recusar APK diferente;
- localizar Android SDK/JDK de modo determinístico ou falhar com instrução
  objetiva;
- compilar fonte própria de forma reproduzível;
- injetar classes/resources/Manifest de maneira idempotente;
- preservar a activity Unity `com.google.firebase.MessagingUnityPlayerActivity`;
- receber o host/API do pipeline, sem URL de produção hardcoded no código Java;
- usar HTTPS no uso real;
- respeitar `/collections/doom` e os headers reais medidos;
- gravar `credentials.json` por arquivo temporário + rename atômico;
- preservar credenciais válidas existentes;
- recusar sobrescrita sem ação explícita do usuário;
- suprimir o gate Google pela estratégia aprovada na Fase 2;
- gerar relatório JSON sanitizado.

Relatório mínimo:

```json
{
  "input_sha256": "...",
  "strategy": "...",
  "manifest_changed": true,
  "unity_activity_preserved": true,
  "google_gate_suppressed": true,
  "credential_schema_version": 3,
  "secrets_redacted": true,
  "bundle_crc_zeroed": false,
  "verified": true
}
```

Se usar patch em `libil2cpp.so`, exija adicionalmente:

- arquitetura arm64;
- RVA e file offset comprovados;
- bytes originais exatos;
- replacement do mesmo tamanho e alinhamento;
- recusa em preimage divergente;
- teste de idempotência;
- hash antes/depois;
- desassembly antes/depois no relatório, sem incluir o binário.

Se alterar asset/bundle, liste todos os bundles tocados e prove o
`zero_catalog_crc` correspondente.

Pare para auditoria com diff, testes e relatório. Não gere APK “final” ainda.

### Fase 5 — testes locais e regressões

No mínimo, cubra:

- analyze não altera entrada;
- APK/build não suportado é recusado;
- patch é idempotente;
- preimage divergente é recusada;
- Manifest termina com um único launcher;
- activity Unity original permanece declarada;
- credenciais existentes não são sobrescritas;
- gravação interrompida não deixa JSON parcial;
- todos os segredos são redigidos;
- resposta register válida cria o schema exato;
- erro register/login não cria credenciais;
- response numérico nulo/malformado é recusado;
- timeout/TLS/HTTP/code diferente de 1000 permanece na tela;
- qualquer bundle alterado tem CRC zerado;
- pipeline propaga falha da etapa de autenticação.

Execute:

```bash
python run_tests.py
cd server && npm test
cd ..
python scripts/verify_everything.py
```

Pare para auditoria com a saída integral dos comandos que falharam e o resumo
dos que passaram.

### Fase 6 — validação real no emulador

Valide em uma instalação descartável:

1. boot sem conta Google configurada;
2. o popup `USE GOOGLE PLAY GAMES?` não aparece;
3. a tela Revival aparece quando não há credenciais;
4. `Criar conta` chama `/game/auth/register` e salva o schema comprovado;
5. a Unity abre e chega aos milestones de autenticação e user-data;
6. restart usa `/game/auth/login-device`, não register novamente;
7. `Entrar` com conta existente funciona em instalação limpa;
8. restart preserva a mesma conta e progresso;
9. Google indisponível não bloqueia o boot;
10. não há fallback desconhecido nem assinatura fatal no logcat.

Sucesso mínimo observado no servidor:

```text
primeiro uso: game/auth/register -> code 1000
restart:      game/auth/login-device -> code 1000
depois:       game/player/game-data-token
              game/player/user-data
```

Ausências obrigatórias no fluxo normal:

```text
game/auth/login-google-play-games
game/identity/link-google-play-games
popup de Google Play Games
segredos no logcat/relatório
```

Um erro interno do SDK Google somente pode ser aceito temporariamente se for
silencioso, não fatal e não houver chamada de autenticação Google; registre-o
como dívida. O resultado preferido é impedir também a inicialização de auth do
GooglePlayController sem remover Firebase/billing/notifications.

Capture fixtures `provenance=client` sanitizadas e associe cada uma à execução
atual. Não marque `compatibility.json` manualmente.

Pare para auditoria.

### Fase 7 — APK final e pacote de auditoria

Depois da aprovação das fases anteriores:

1. execute o pipeline completo: decode, patch de host, patch auth, rebuild,
   assinatura e verificações;
2. execute `verify_patched_apk.py` no APK assinado final;
3. rode `client_harness.py` no mesmo arquivo final;
4. regenere a matriz somente com evidência real;
5. execute `verify_everything.py` novamente.

Entregue ao Codex:

- `git status --short`;
- diff por arquivo, sem binários/segredos;
- comandos executados e exit codes;
- relatórios sanitizados em `work/`;
- SHA-256 do APK de entrada e do APK final;
- estratégia exata usada para suprimir Google;
- prova de register, restart/login-device e persistência;
- lista de itens `CONFIRMADO`, `A VERIFICAR` e `BLOQUEADO`;
- nenhuma afirmação “pronto” se qualquer gate abaixo falhar.

## Definition of Done

Só declare concluído quando todos forem verdadeiros:

- [ ] O APK final contém o host Revival e não contém o host oficial.
- [ ] O APK final está assinado e passa em `verify_patched_apk.py`.
- [ ] Há somente um launcher e a activity Unity original está preservada.
- [ ] O popup Google não aparece no primeiro boot nem no restart.
- [ ] Registro Revival funciona contra o servidor real de teste.
- [ ] Login Revival funciona em uma instalação limpa.
- [ ] `credentials.json` é aceito pela Unity sem edição manual.
- [ ] Restart usa login-device e preserva a conta/progresso.
- [ ] O cliente chega a authentication + user-data no harness.
- [ ] Nenhuma rota Google auth/link é chamada no fluxo normal.
- [ ] Nenhum segredo aparece em Git, logcat, fixture ou relatório.
- [ ] Testes Node, Python e gate global passam.
- [ ] Alterações de bundle, se houver, têm CRC corrigido.
- [ ] Nenhum dump/material proprietário está staged ou versionado.
- [ ] O Codex auditou a evidência antes de qualquer commit/push.

## Condições de parada

Pare e marque `BLOQUEADO` se:

- o método/offset do gate não puder ser provado;
- a única proposta for remover todas as dependências Google;
- o login exigir inventar `device_id` ou outro campo sem evidência;
- a activity não conseguir gravar no mesmo caminho lido pela Unity;
- o patch depender de limpar dados do usuário;
- os testes exigirem segredos reais em arquivo versionado;
- o APK final só funcionar no mesmo estado de emulador usado para desenvolvê-lo;
- a árvore suja impedir isolar o diff desta tarefa.

Nesses casos, entregue diagnóstico e opções ao auditor; não simule o resultado.
