# Plano de execução — Revival Studio e compatibilidade total do cliente 1.13.1

> **⚠️ OBSOLETO (2026-08-19) — snapshot histórico, não siga os comandos daqui.**
> Este plano foi escrito contra um estado anterior do repositório e descreve
> como pendentes fases já concluídas (o Studio Python, o pipeline bundle-aware
> com zero de `m_Crc`, o boot do 1.13.1 no emulador e o servidor `node:http`
> + SQLite já existem). Ele ainda menciona wrappers (`setup-patcher-tools.*`,
> `setup-server.*`/`start-server.*`) que foram **aposentados** — a porta de
> entrada é `scripts/revival_studio.py` e o deploy é `scripts/install.sh`.
> Estado atual autoritativo: `docs/PROMPT-GLM-5.1-CORRIGIR-FRAMEWORK-REAL.md`,
> `docs/APK-PATCH.md`, `docs/SERVER.md` e `docs/ENDPOINT-MATRIX.md`.
>
> Documento de trabalho para outra LLM executar. Este arquivo é um plano; sua
> criação não executou patcher, servidor, testes, APK, ADB, deploy ou alteração de
> código funcional.

## 1. Objetivo

Construir um editor desktop em Python, chamado provisoriamente **Revival Studio**,
que conduza todo o ciclo seguro e suportado de personalização da cópia local do
Mighty DOOM 1.13.1:

1. importar e identificar o APK correto;
2. validar o servidor Revival e o TLS;
3. trocar o endpoint oficial pelo servidor escolhido;
4. personalizar superfícies do APK que possam ser alteradas com prova estrutural;
5. reconstruir, alinhar, assinar e verificar o APK final;
6. instalar e diagnosticar o cliente em emulador ou aparelho, quando autorizado;
7. acompanhar a compatibilidade real das 116 rotas do cliente;
8. provar os fluxos de jogo e a persistência até o projeto atingir o DoD.

O editor deve reutilizar os scripts existentes. Ele não deve criar um segundo
patcher paralelo nem copiar lógica crítica para dentro da interface gráfica.

### Requisito adicional obrigatório — um único framework Python

Todos os scripts `.bat` e `.sh` devem deixar de ser caminhos de execução
principais. O usuário deve abrir **um único programa Python** e encontrar menus
para todo o ciclo do projeto.

O aplicativo deve centralizar, no mínimo:

- preparar e validar a toolchain;
- criar/abrir projeto;
- selecionar e analisar APK;
- validar servidor, hostname, HTTPS e CA;
- verificar limite de hostname;
- executar patch fast path e bundle-aware;
- inspecionar bundles e assets Unity;
- editar loading screen;
- editar branding Android seguro;
- exportar e substituir assets permitidos;
- reconstruir APK;
- assinar e verificar assinatura;
- validar o APK final;
- instalar/remover com confirmação explícita;
- abrir o app via ADB;
- capturar logcat;
- executar harness do cliente;
- subir/parar/recarregar o servidor local, quando configurado;
- consultar health, research e requests;
- executar testes Python e Node;
- consultar a matriz de compatibilidade;
- selecionar a próxima rota com `next_task.py`;
- abrir relatórios e logs.

Os `.bat` e `.sh` existentes devem ser tratados assim:

1. primeiro, suas funções devem ser mapeadas para ações do framework;
2. depois, a lógica duplicada deve ser movida para módulos Python reutilizáveis;
3. em seguida, a GUI deve chamar esses módulos diretamente ou usar um runner
   seguro para ferramentas externas;
4. os wrappers podem permanecer por compatibilidade de terminal, mas devem apenas
   encaminhar para o framework Python;
5. não pode existir comportamento disponível no `.bat`/`.sh` que esteja ausente
   nos menus do aplicativo;
6. cada menu precisa indicar o script/serviço original que substituiu e o relatório
   produzido;
7. o framework deve funcionar no Windows sem exigir que o usuário conheça
   PowerShell, Bash, Java, apktool, UnityPy ou comandos ADB;
8. exceção obrigatória e permanente: `scripts/install.sh` (e seu par direto
   `scripts/uninstall.sh`, que consome o estado gravado pelo instalador)
   NÃO deve ser convertido para Python nem removido. Ele roda na VPS Linux
   de produção via `sudo`, num ambiente onde Python e o Studio não existem,
   e é o caminho de deploy documentado em `docs/guia-completo.html`. O
   Studio pode, no máximo, exibir e copiar o comando
   `sudo ./scripts/install.sh` no menu Deploy; o script shell permanece
   como implementação real do deploy.

O resultado esperado é:

```text
python scripts/revival_studio.py
  ├── Projeto
  ├── Ferramentas
  ├── APK
  ├── Servidor
  ├── Recon IL2CPP
  ├── Assets Unity
  ├── Loading screen
  ├── Branding Android
  ├── Build e assinatura
  ├── Dispositivo / ADB
  ├── Diagnóstico
  ├── Compatibilidade
  ├── Testes
  └── Relatórios
```

Nenhum menu pode simplesmente executar um `.bat` ou `.sh` inteiro e esconder o
resultado. A interface deve conhecer as etapas, mostrar progresso, capturar
exit codes, permitir cancelamento e apontar o relatório da etapa que falhou.

## 2. O que significa “100%” neste plano

“Editar 100% o app” não significa que qualquer byte, código nativo, cena ou asset
Unity poderá ser alterado arbitrariamente. Isso seria tecnicamente falso e
arriscaria corromper o cliente IL2CPP.

Neste plano, **100%** só pode ser declarado quando dois objetivos independentes
forem cumpridos.

### 2.1. Cobertura de edição suportada

O Revival Studio deve oferecer interface gráfica para 100% das operações seguras
e reproduzíveis mantidas pelo projeto:

- análise e identificação do APK;
- perfil do servidor, hostname, HTTPS e CA opcional;
- patch de endpoint por estratégia automática;
- `network_security_config` e manifest;
- loading screen;
- branding Android seguro, quando implementado e testado;
- catálogo somente-leitura de objetos Unity;
- substituição de assets Unity apenas em tipos e objetos validados;
- rebuild, assinatura e verificação final;
- instalação opcional, logcat e diagnóstico;
- relatórios e retomada de projeto.

Qualquer superfície sem prova de edição segura deve aparecer como **somente
leitura / não suportada**, e não como uma promessa quebrada.

### 2.2. Compatibilidade de runtime

As 116 rotas `game/*` do cliente precisam satisfazer o DoD do
`compatibility.json`:

- `schema_extracted=true`;
- `implemented=true`;
- `request_observed=true`;
- `response_observed=true`;
- `client_validated=true`;
- `persistence_validated=true` ou `null` somente quando comprovadamente não se
  aplica;
- `regression_test=true`;
- `uses_fallback=false`.

As 10 rotas de ads/IAP continuam desativadas por política. Elas ainda precisam de
contrato extraído, resposta desativada aceita pelo cliente, teste e evidência de
cliente. “Fora de escopo” não autoriza resposta inventada nem fallback vazio.

## 3. Fontes de verdade e ordem de precedência

A LLM executora deve usar esta ordem quando encontrar divergências:

1. `AGENTS.md`;
2. `research/DEAD-ENDS.md`;
3. as skills `.claude/skills/apk-patch/`, `il2cpp-recon/`,
   `revival-server/` e `boot-diagnostics/`;
4. `compatibility.json` e os scripts que o geram;
5. código e testes atuais;
6. documentos de status e roadmaps antigos.

Regras editoriais obrigatórias em commits, relatórios e documentação:

- `CONFIRMADO`: medido nesta base, acompanhado do comando e da evidência;
- `A VERIFICAR`: hipótese ainda não medida;
- uma hipótese não vira fato porque parece plausível;
- antes de tentar uma correção, consultar `research/DEAD-ENDS.md`;
- nunca declarar endpoint pronto porque respondeu HTTP 200.

## 4. Estado inicial confirmado por leitura da árvore em 2026-08-17

### 4.1. Cliente alvo

- pacote: `com.bethsoft.ubu`;
- versão: 1.13.1, build 84862;
- Unity: 2021.3.25f1;
- runtime: IL2CPP arm64;
- metadata: v29, sanity `0xFAB11BAF`;
- endpoint base oficial:
  `https://international.gear.bethesda.net/collections/doom`;
- host principal: `international.gear.bethesda.net`, 31 bytes;
- 116 rotas `game/*` registradas.

### 4.2. Patcher já existente

Já existem e devem ser reutilizados:

- `scripts/analyze_apk.py`;
- `scripts/check_patch_length.py`;
- `scripts/check_revival_server.py`;
- `scripts/patch_apk.py`;
- `scripts/patch_unity_bundle.py`;
- `scripts/patch_unity_raw_strings.py`;
- `scripts/patch_bundle_from_report.py`;
- `scripts/inject_loading_screen.py`;
- `scripts/loading_screen_editor.py`;
- `scripts/verify_patched_apk.py`;
- `scripts/client_harness.py`;
- `scripts/verify_everything.py`;
- os orquestradores `scripts/patch-apk.bat` e `.sh`.

### 4.3. Compatibilidade atual

Leitura estática atual de `compatibility.json`:

- 116/116 rotas aparecem como implementadas;
- 78/116 têm schema extraído;
- 11/116 têm request observado;
- 11/116 têm response observado;
- 11/116 têm validação no cliente;
- 88/116 têm teste de regressão;
- 0 rotas estão marcadas como fallback no registro;
- apenas 4/116 têm DoD completo:
  `game/armory/get`, `game/chapters/start`, `game/chapters/update` e
  `game/chapters/end`.

Portanto, “116 implementadas” não significa “100% compatível”. O maior trabalho
restante é extrair contratos ausentes e validar cada fluxo no cliente real.

### 4.4. Divergências que devem ser corrigidas antes da GUI

- Alguns documentos antigos falam em limite de 24 bytes e no host
  `slayersclub.bethesda.net`. Para gameplay 1.13.1, quem decide é
  `scripts/check_patch_length.py`; a base atual registra 31 bytes para o host
  Gear.
- Alguns textos antigos descrevem o servidor como Koa. O servidor vivo atual usa
  `node:http` builtin.
- O JWT de sessão já está implementado em `server/src/jwt.js` e é coberto por
  `server/test/session-jwt.mjs`. Não refazer a antiga tarefa de “adicionar JWT”.
- `scripts/dump_il2cpp_metadata.py` existe, mas hoje extrai somente rotas. A
  interface prometida para enums, DTOs e wire names ainda precisa ser
  implementada.
- O Java do `PATH` desta máquina pode ser 11, enquanto apktool e signer exigem
  17+. A GUI precisa resolver e validar explicitamente o runtime Java correto.

## 5. Restrições inegociáveis

- [ ] Nunca versionar APK, XAPK, AAB, bundles, dumps, logcats, pcaps,
  screenshots, keystores, certificados, imagens do usuário ou assets oficiais.
- [ ] Nunca usar `git add -f` nem `git add .` sem revisar o status.
- [ ] Nunca alterar o APK de entrada no lugar; ele é imutável.
- [ ] Nunca aumentar string em `global-metadata.dat` sem realocador formal e
  testes; o caminho atual deve bloquear.
- [ ] Nunca fazer busca/substituição cega em bundle Unity.
- [ ] Todo bundle alterado em `assets/aa/**` deve passar por
  `zero_catalog_crc()` para sua entrada correspondente.
- [ ] Nunca pular a verificação do APK depois da assinatura.
- [ ] Nunca desabilitar validação TLS globalmente.
- [ ] Nunca trocar `applicationId`/package name por padrão. O pacote
  `com.bethsoft.ubu` participa do contrato e do estado instalado.
- [ ] Nunca emitir campo numérico não-nullable como `null` no wire do servidor;
  sem valor, omitir.
- [ ] Nunca inventar rota, DTO, wire name ou código de erro.
- [ ] Nunca reativar ads ou dinheiro real/IAP.
- [ ] Nunca editar `server/config/revival.json`, `packs.json`, `events.json` ou
  `site.json` para uma mudança versionada; usar os `*.example.json`.
- [ ] Nunca desinstalar o app automaticamente: a desinstalação pode apagar dados
  locais e exige confirmação explícita do usuário.

## 6. Arquitetura proposta

Manter o launcher pequeno e separar domínio, execução e UI:

```text
scripts/
  revival_studio.py                 # launcher Tkinter
  revival-studio.bat
  revival-studio.sh
  revival_editor/
    __init__.py
    models.py                       # dataclasses e estados
    project.py                      # abrir/salvar projeto sem segredos
    paths.py                        # validação e isolamento de caminhos
    toolchain.py                    # Python/Java/JARs/ADB
    runner.py                       # jobs, subprocess, cancelamento e logs
    pipeline.py                     # máquina de estados do patch
    reports.py                      # JSON sanitizado e resumo humano
    assets.py                       # catálogo e políticas de edição Unity
    android_resources.py            # branding Android seguro
    diagnostics.py                  # assinaturas de logcat
    compatibility.py                # leitura do registry/next_task
    ui/
      app.py
      project_tab.py
      server_tab.py
      patch_tab.py
      visuals_tab.py
      build_tab.py
      device_tab.py
      compatibility_tab.py
      log_panel.py
tests/
  revival_editor/
    test_project.py
    test_paths.py
    test_toolchain.py
    test_runner.py
    test_pipeline.py
    test_android_resources.py
    test_asset_policy.py
    test_reports.py
```

Não criar um diretório chamado `scripts/revival_studio/`, pois ele conflitaria
com o launcher `scripts/revival_studio.py` no mecanismo de imports.

### 6.1. Mapeamento obrigatório dos wrappers existentes

Antes de apagar ou alterar qualquer wrapper, criar uma tabela de inventário no
plano de implementação:

| Wrapper | Ações que ele contém | Menu destino | Serviço Python | Mantido como compatibilidade? |
|---|---|---|---|---|
| `patch-apk.bat/.sh` | preflight, análise, decode, patch, build, sign, verify | APK → Pipeline completo | `pipeline.py` | sim, encaminhador |
| `loading-screen-editor.bat/.sh` | abrir editor Tkinter | Loading screen | `ui/visuals_tab.py` | sim, encaminhador |
| `analyze-official-apk.bat/.sh` | validar/analisar APK local | APK → Analisar | `analyze_apk.py` + adapter | sim, encaminhador |
| `setup-patcher-tools.bat/.sh` | baixar/verificar ferramentas | Ferramentas → Preparar | `toolchain.py` | sim, encaminhador |
| `setup-server.bat/.sh` | preparar configs/dependências | Servidor → Preparar | `server.py` | sim, encaminhador |
| `start-server.bat/.sh` | iniciar servidor | Servidor → Iniciar | `server.py` | sim, encaminhador |
| `install.sh` | instalação/deploy de servidor | Deploy, se autorizado | nenhum — o `.sh` é a implementação real (ver regra 1.8) | permanente, nunca remover |
| `uninstall.sh` | remoção/deploy destrutivo | Deploy, protegido | nenhum — o `.sh` é a implementação real (ver regra 1.8) | permanente, nunca remover; confirmação obrigatória |

Completar a tabela com todos os arquivos retornados por:

```bash
rg --files scripts -g '*.bat' -g '*.sh'
```

O inventário deve ser revisado antes de qualquer wrapper ser removido.
`scripts/install.sh` e `scripts/uninstall.sh` estão fora do escopo de
remoção/conversão: são o par de deploy da VPS e permanecem como scripts
shell canônicos (ver regra 1.8).

### 6.2. Máquina de estados

```text
VAZIO
  -> APK_ANALISADO
  -> SERVIDOR_VALIDADO
  -> WORKSPACE_PREPARADO
  -> PATCH_APLICADO
  -> CUSTOMIZACOES_APLICADAS
  -> APK_RECONSTRUIDO
  -> APK_ASSINADO
  -> APK_VERIFICADO
  -> INSTALADO
  -> CLIENTE_VALIDADO
```

Qualquer alteração de servidor ou customização depois do build deve invalidar os
estados `APK_RECONSTRUIDO` em diante. A UI não pode continuar exibindo um selo
verde baseado em relatório antigo.

### 6.3. Modelo de projeto

Salvar em `work/revival-studio/<id>/project.json`, nunca na raiz versionada.
Campos mínimos:

```json
{
  "schema_version": 1,
  "input_apk": "caminho local",
  "input_sha256": "...",
  "server_host": "doom.exemplo.br",
  "ca_path": null,
  "patch_strategy": "auto",
  "customizations": {},
  "output_apk": "output/mighty-doom-revival.apk",
  "completed_stages": [],
  "reports": {}
}
```

Não salvar senha de keystore, token admin, segredo JWT ou conteúdo de
certificado no JSON. Senhas ficam apenas em memória; tokens podem vir de variável
de ambiente ou prompt temporário.

## 7. Fase 0 — congelar a linha de base

- [ ] Ler `AGENTS.md` inteiro.
- [ ] Ler as quatro skills relevantes.
- [ ] Ler `research/DEAD-ENDS.md`.
- [ ] Rodar `git status --short` e `git diff --cached`.
- [ ] Se houver mudanças alheias, não as modificar nem incluir em commit.
- [ ] Criar uma branch com prefixo `codex/`, salvo instrução diferente do usuário.
- [ ] Registrar em um relatório local: commit base, Python, Node, Java, adb,
  sistema operacional e hash do APK.
- [ ] Rodar a linha de base antes de refatorar:

```bash
python scripts/verify_everything.py
```

Resultado esperado: todas as suítes atuais passam. Se falhar, registrar a falha
como baseline e não misturar sua correção com o primeiro commit da GUI.

### Gate da fase 0

- [ ] A árvore e os testes de base estão compreendidos.
- [ ] Nenhum material proprietário está staged.
- [ ] As divergências documentais da seção 4.4 viraram issues/tarefas explícitas.

## 8. Fase 1 — transformar os scripts em serviços reutilizáveis

O objetivo é a GUI chamar a mesma implementação dos CLIs.

- [ ] Identificar em cada script a função pública reutilizável e a camada de
  `argparse`.
- [ ] Manter todos os argumentos e exit codes existentes compatíveis.
- [ ] Adicionar `log: Callable[[str], None]` e, quando necessário,
  `progress: Callable[[StageProgress], None]` sem acoplar Tkinter ao domínio.
- [ ] Criar tipos de resultado serializáveis, por exemplo:
  `AnalyzeResult`, `ServerPreflightResult`, `PatchResult`, `BuildResult`,
  `VerifyResult` e `HarnessResult`.
- [ ] Não capturar `SystemExit` da lógica de domínio; somente o CLI converte
  exceções conhecidas em exit code.
- [ ] Padronizar falhas com código, etapa, mensagem curta, detalhes e caminho de
  relatório.
- [ ] Adicionar testes unitários para cada adapter sem abrir a GUI.

### Estratégia de invocação

- Função Python no mesmo processo para operações puramente Python e já
  thread-safe.
- `subprocess` com lista de argumentos e `shell=False` para apktool, signer, adb
  e processos que precisam de cancelamento forte.
- Nunca montar comando concatenando hostname, caminhos ou texto do usuário.

### Gate da fase 1

- [ ] Os CLIs antigos continuam funcionando sem mudança de uso.
- [ ] A nova camada retorna dados estruturados, não exige parse de texto colorido.
- [ ] Todos os testes antigos do patcher continuam passando.

## 9. Fase 2 — runner assíncrono e painel de logs

Reutilizar o padrão correto já presente em `loading_screen_editor.py`:
worker thread, `queue.Queue` e `after()` para atualizar Tkinter.

- [ ] Criar um `JobRunner` com apenas um job mutável por projeto.
- [ ] A thread de trabalho nunca toca widgets.
- [ ] Toda atualização da UI passa pela fila.
- [ ] Implementar progresso por etapas e progresso indeterminado para apktool.
- [ ] Implementar cancelamento cooperativo para Python e encerramento controlado
  de subprocessos.
- [ ] Se o cancelamento ocorrer durante uma escrita, manter o arquivo temporário
  e nunca substituir a saída válida anterior.
- [ ] Salvar log completo em `work/revival-studio/<id>/logs/`.
- [ ] Mascarar tokens, senhas, userinfo de URL e caminhos de segredo no painel.
- [ ] Adicionar testes de job concluído, falho, cancelado e timeout.

### 9.1. Menus e comandos do framework único

Implementar uma barra de menus e uma tela inicial com as seguintes ações:

**Arquivo**

- Novo projeto;
- Abrir projeto;
- Salvar projeto;
- Salvar projeto como;
- Fechar projeto;
- Sair.

**Projeto**

- Analisar APK;
- Validar servidor;
- Ver resumo de hashes;
- Ver workspace;
- Limpar somente artefatos temporários do projeto.

**APK**

- Precheck de hostname;
- Patch automático;
- Patch avançado por etapa;
- Inspecionar bundles;
- Ver relatório de patch;
- Rebuild;
- Assinar;
- Verificar APK assinado;
- Exportar APK final.

**Personalização**

- Loading screen;
- Branding Android;
- Catálogo de assets Unity;
- Substituições pendentes;
- Validação de CRC.

**Servidor**

- Preparar servidor local;
- Iniciar servidor;
- Parar servidor iniciado pela GUI;
- Reiniciar servidor;
- Health;
- Research;
- Requests;
- Abrir configuração de exemplo.

**Cliente**

- Detectar dispositivos ADB;
- Instalar APK;
- Abrir app;
- Limpar logcat;
- Capturar logcat;
- Rodar harness;
- Abrir relatório do harness.

**Compatibilidade**

- Abrir matriz;
- Próxima tarefa;
- Extrair rotas;
- Extrair DTOs/enums/wire names;
- Capturar fixture;
- Atualizar evidência;
- Verificar zero fallback.

**Testes**

- Testes Python do patcher;
- Testes Python do editor;
- `npm test`;
- `verify_everything.py`;
- Gate completo com servidor;
- Gate completo com APK.

**Ajuda**

- Abrir documentação;
- Abrir pasta de relatórios;
- Diagnóstico da instalação;
- Sobre e versão do framework.

Cada item deve ficar desabilitado quando seus pré-requisitos não estiverem
cumpridos. Por exemplo, “Assinar” não aparece disponível antes de “Rebuild”, e
“Instalar” não aparece disponível antes da verificação pós-assinatura.

### 9.2. Encaminhamento dos wrappers

Depois que o framework estiver funcional:

- [ ] alterar `patch-apk.bat` e `patch-apk.sh` para chamar o launcher Python com
  modo compatibilidade, preservando argumentos existentes;
- [ ] alterar os wrappers de loading screen para chamar a aba correspondente;
- [ ] alterar setup/start do servidor para chamar o controlador Python quando
  possível;
- [ ] manter comandos headless para CI e VPS, porque a GUI não deve ser requisito
  de automação;
- [ ] impedir recursão: o Python launcher nunca deve chamar um wrapper que chama o
  Python launcher de volta;
- [ ] adicionar teste que verifica que cada wrapper encaminha para uma ação
  existente;
- [ ] adicionar teste que detecta wrapper com lógica não mapeada;
- [ ] documentar claramente que wrappers são compatibilidade, não a arquitetura
  principal.

### Gate da fase 2

- [ ] A janela continua responsiva durante decode, build e assinatura.
- [ ] Fechar a janela durante job solicita confirmação e não corrompe saída.
- [ ] O log permite localizar etapa e exit code sem expor segredo.

## 10. Fase 3 — toolchain determinística

- [ ] Exigir Python 3.11+.
- [ ] Exigir `UnityPy==1.25.3` exata.
- [ ] Exigir Pillow na versão compatível registrada pelo projeto.
- [ ] Resolver Java nesta ordem no Windows:
  `.tools/jre17/jdk-17.0.20+8-jre/bin/java.exe`, configuração explícita do
  usuário e somente então `PATH` se a versão for 17+.
- [ ] No Linux/macOS, aceitar configuração explícita ou `PATH` somente com Java
  17+.
- [ ] Validar os hashes fixados de Apktool 3.0.3 e uber-apk-signer 1.3.0.
- [ ] Não atualizar ferramentas automaticamente para versões diferentes.
- [ ] Mostrar adb como opcional até a aba de dispositivo.
- [ ] Criar botão “Preparar ferramentas” que usa os scripts existentes e pede
  confirmação antes de download/instalação.
- [ ] Corrigir os orquestradores antigos para consumirem o mesmo resolvedor de
  Java, sem depender cegamente do `PATH`.

### Gate da fase 3

- [ ] A tela informa caminho e versão de cada ferramenta.
- [ ] Java 11 é rejeitado com instrução clara; Java 17 local é selecionado.
- [ ] Hash divergente de JAR bloqueia o build.

## 11. Fase 4 — aba Projeto / Analisar

- [ ] Permitir selecionar apenas `.apk` para o fluxo principal.
- [ ] Tratar `.xapk` como importação separada: localizar o base APK e splits,
  sem assumir que é um APK monolítico.
- [ ] Calcular SHA-256 em thread.
- [ ] Chamar `analyze_apk.py` e exibir:
  package, versão, build, Unity, IL2CPP, ABI, metadata, tamanho e hosts.
- [ ] Confirmar a entrada esperada antes de habilitar edição:
  `com.bethsoft.ubu`, 1.13.1, build 84862, Unity 2021.3.25f1, arm64 e metadata
  v29.
- [ ] Se algum campo divergir, abrir somente em modo inspeção e marcar
  `A VERIFICAR`; não aplicar regras do 1.13.1 automaticamente.
- [ ] Rodar `check_patch_length.py` quando o hostname estiver preenchido.
- [ ] Explicar na UI:
  exit 0 = fast path possível; exit 4 = tentar bundle-aware; exit 2 = entrada
  inválida.
- [ ] Nunca copiar o APK para dentro de diretório versionado.

### Gate da fase 4

- [ ] Um APK sintético válido e entradas inválidas são cobertos por teste.
- [ ] A UI não habilita “Construir” antes de uma análise válida.
- [ ] O relatório contém hash e fatos, não bytes proprietários.

## 12. Fase 5 — aba Servidor / TLS

- [ ] Aceitar hostname, não URL com caminho, no campo principal.
- [ ] Normalizar `https://host` para `host`; rejeitar esquema diferente, query,
  fragmento, credenciais fornecidas pelo usuário e porta inválida.
- [ ] Preservar o path do cliente `/collections/doom`; o editor troca o host,
  não registra rotas com esse prefixo no servidor.
- [ ] Oferecer dois perfis:
  certificado público e CA local opcional.
- [ ] Validar arquivo CA sem copiar chave privada.
- [ ] Chamar `check_revival_server.py` e exigir:
  HTTPS válido, `/revival/health`, cliente 1.13.1, API 24.0.0, `uts` correto e
  game data carregado.
- [ ] Mostrar DNS, TLS e health como checks separados.
- [ ] Não oferecer opção “ignorar TLS”.
- [ ] Invalidar build anterior se hostname ou CA mudar.

Comando de referência que a GUI deve representar:

```bash
python scripts/check_revival_server.py --server HOST \
  --report work/revival-studio/ID/server-preflight.json
```

### Gate da fase 5

- [ ] Servidor inválido bloqueia patch por padrão.
- [ ] CA pública e CA local têm testes separados.
- [ ] O relatório não contém segredo nem chave privada.

## 13. Fase 6 — pipeline de patch do endpoint

Implementar uma única ação “Aplicar endpoint” com estratégia `auto`:

1. criar workspace isolado;
2. analisar e registrar hash da entrada;
3. executar preflight do servidor;
4. desmontar com apktool quando o fluxo exigir Android resources;
5. executar `patch_apk.py`;
6. se o patch direto retornar 4, executar
   `patch_bundle_from_report.py --sweep-all-bundles`;
7. bloquear se a única solução exigir crescimento não suportado de metadata;
8. validar o relatório antes de habilitar rebuild.

- [ ] O workspace deve ser
  `work/revival-studio/<id>/decoded`, nunca um caminho amplo.
- [ ] Antes de limpar/recriar workspace, resolver o caminho absoluto e provar
  que está dentro de `work/revival-studio/<id>`.
- [ ] Usar o host principal de 31 bytes quando presente; não assumir o host
  ancilar de 24 bytes.
- [ ] Manter o padding de userinfo somente quando calculado por
  `build_url_replacement()`.
- [ ] Nunca alterar comprimento de literal em metadata no fast path.
- [ ] No bundle-aware, alterar apenas typetree/string Unity validada.
- [ ] Depois de qualquer mutação de bundle, registrar qual hash de bundle teve
  CRC zerado no catálogo.
- [ ] Escanear novamente para provar que o host oficial foi removido.

### Gate da fase 6

- [ ] O relatório lista estratégia, ocorrências antes/depois, bundles alterados
  e CRCs zerados.
- [ ] Nenhum erro deixa um APK parcialmente promovido como saída final.
- [ ] Os testes existentes de patch, raw strings, bundle e CRC passam.

## 14. Fase 7 — aba Visuais: loading screen

Primeiro incorporar o editor já funcional, sem regressão:

- [ ] Mover a composição reutilizável para o pacote de domínio sem duplicar
  `compose_loading_image()`.
- [ ] Manter modos `image`, `text` e `image+text`.
- [ ] Manter preview em 2048×2048.
- [ ] Validar PNG/JPG/WebP, dimensões, memória e perfil de cor.
- [ ] Exibir safe area e preview em proporções comuns de tela.
- [ ] Exportar PNG sem injetar.
- [ ] Ao injetar, trocar somente texturas de loading identificadas.
- [ ] Reabrir o bundle resultante com UnityPy e comparar a textura.
- [ ] Zerar CRC correspondente.
- [ ] Marcar assinatura e verificação anteriores como inválidas.

### Gate da fase 7

- [ ] `tests/test_inject_loading_screen.py` continua passando.
- [ ] Um teste prova que a textura mudou e o restante dos objetos não foi
  selecionado por engano.
- [ ] O APK precisa ser assinado novamente depois da injeção.

## 15. Fase 8 — branding Android seguro

Esta fase adiciona personalização do invólucro Android, não do gameplay.

- [ ] Implementar editor de nome exibido usando o recurso realmente referenciado
  por `android:label`.
- [ ] Implementar ícone legado e adaptive icon somente após mapear todos os
  recursos referenciados pelo manifest.
- [ ] Gerar densidades Android a partir de imagem do usuário sem distorção.
- [ ] Implementar cor de tema/splash somente em recursos existentes e com teste
  por versão Android.
- [ ] Mostrar diff dos XML/resources antes de aplicar.
- [ ] Bloquear mudança de package name, minSdk, targetSdk, componentes,
  permissões ou exported flags no modo normal.
- [ ] Criar modo avançado somente-leitura para manifest e resources.
- [ ] Não permitir que imagem do usuário seja copiada para pasta versionada.

### Gate da fase 8

- [ ] Apktool recompila o fixture após cada classe de alteração.
- [ ] Manifest final continua declarando os componentes necessários.
- [ ] O ícone aparece em Android compatível sem impedir o boot.

## 16. Fase 9 — catálogo e editor seguro de assets Unity

Esta é a fase que dá alcance ao “editar o app” sem prometer edição binária
arbitrária.

### 16.1. Catálogo somente-leitura primeiro

- [ ] Criar scanner que liste, sem exportar conteúdo por padrão:
  membro do APK, bundle, `path_id`, tipo Unity, `m_Name`, dimensões/duração,
  hash e capacidade de escrita.
- [ ] Categorizar cada objeto:
  `EDITÁVEL_VALIDADO`, `SOMENTE_LEITURA`, `BLOQUEADO` ou `A_VERIFICAR`.
- [ ] Salvar somente metadados sanitizados em relatório.
- [ ] Permitir busca por nome/tipo/bundle.

### 16.2. Seletores estáveis

Uma substituição deve apontar para:

```text
sha256 do APK fonte + membro do bundle + path_id + tipo + m_Name + hash do objeto
```

Se qualquer parte divergir, bloquear em vez de aplicar a outro objeto com nome
parecido.

### 16.3. Ordem de suporte

- [ ] `Texture2D` usado por loading: já validado.
- [ ] `Texture2D`/`Sprite` adicional: liberar um conjunto por vez com fixture e
  reabertura do bundle.
- [ ] `TextAsset`: liberar apenas quando a serialização e encoding forem
  comprovados.
- [ ] campos string de `MonoBehaviour`: liberar somente com typetree íntegra e
  teste de round-trip.
- [ ] `AudioClip`: permanecer somente leitura até existir writer e teste de
  round-trip para o formato real.
- [ ] `Scene`, `GameObject`, `MonoScript`, `Mesh`, `Shader`,
  `global-metadata.dat`, `libil2cpp.so` e bibliotecas nativas: bloqueados no
  editor genérico.

### 16.4. Transação de bundle

Para cada asset editado:

1. copiar o bundle para arquivo temporário dentro do workspace;
2. confirmar seletor estável;
3. escrever com UnityPy 1.25.3;
4. reabrir o bundle;
5. verificar objeto alterado e contagem dos demais;
6. promover o temporário atomicamente;
7. chamar `zero_catalog_crc()`;
8. verificar o catálogo;
9. registrar hash anterior/posterior.

### Gate da fase 9

- [ ] Nenhum tipo é editável sem teste de round-trip.
- [ ] Todo bundle alterado possui prova de CRC zerado.
- [ ] Cancelamento ou falha preserva a última versão íntegra.
- [ ] Nenhum asset extraído entra no Git.

## 17. Fase 10 — rebuild, assinatura e verificação

Pipeline obrigatório, sem botão para pular etapas:

1. `apktool b` para APK não assinado;
2. `verify_patched_apk.py` no reconstruído;
3. uber-apk-signer para alinhar e assinar;
4. `uber-apk-signer --onlyVerify`;
5. `verify_patched_apk.py` novamente no APK assinado;
6. cópia atômica para `output/`;
7. SHA-256 e relatório final.

- [ ] Nunca promover a saída se qualquer etapa retornar código não zero.
- [ ] Mostrar claramente que a assinatura difere da oficial.
- [ ] Suportar chave de laboratório e chave fornecida pelo usuário, sem guardar
  senha.
- [ ] Nunca gerar/guardar keystore fora de `work/` sem escolha explícita.
- [ ] Não sobrescrever um output anterior aprovado; usar temporário e rotação
  recuperável.
- [ ] Exibir host, hash, assinatura e horário da verificação final.

Comando final representado pela GUI:

```bash
python scripts/verify_patched_apk.py \
  --apk output/mighty-doom-revival.apk \
  --server HOST \
  --report work/revival-studio/ID/final-apk-verification.json
```

Critério: host Revival encontrado mais de zero vezes e host oficial encontrado
zero vezes no arquivo assinado.

### Gate da fase 10

- [ ] Assinatura válida.
- [ ] Verificação pós-assinatura válida.
- [ ] Relatório e hash correspondem exatamente ao APK entregue.

## 18. Fase 11 — aba Dispositivo e diagnóstico

- [ ] Detectar adb e listar dispositivos autorizados.
- [ ] Mostrar package instalado, versão e assinatura quando possível.
- [ ] Usar `adb install -r` somente quando a assinatura for compatível.
- [ ] Se for necessário desinstalar, explicar que dados locais podem ser
  apagados e exigir confirmação explícita digitada.
- [ ] Limpar logcat apenas quando o usuário iniciar uma sessão de diagnóstico.
- [ ] Abrir o app e acompanhar por janela configurável.
- [ ] Reutilizar `client_harness.py` para relatório.
- [ ] Destacar as assinaturas:
  `Malformed response payload`, `Failed to launch`, JWT malformado,
  `CRC Mismatch`, `RemoteProviderException`, dados de ability ausentes,
  exceção fatal e SIGSEGV.
- [ ] Correlacionar horário do logcat com `[req]` do servidor quando houver token
  admin.
- [ ] Nunca versionar logcat; manter em `work/`.

### Árvore de diagnóstico que a UI deve ensinar

- Sem request no servidor: hostname, DNS, TLS, CA ou rede.
- Request chega e há `Malformed response payload`: DTO/wire do servidor.
- Menu abre e cena falha com CRC: bundle alterado sem catálogo zerado.
- Crash imediato antes da rede: metadata/bundle/native corrompido; reconstruir a
  partir do APK original.
- Abilities ausentes: completar o game data; não “consertar” o APK no chute.

### Gate da fase 11

- [ ] Um harness limpo retorna exit 0.
- [ ] Falhas fatais retornam exit não zero e apontam a próxima ação.
- [ ] Warnings conhecidos não são promovidos a causa fatal sem evidência.

## 19. Fase 12 — completar o extrator IL2CPP

Antes de fechar o servidor, expandir o extrator atual em vez de criar dumps
manuais.

- [ ] Preservar `--apk`, `--metadata`, `--out` e extração das 116 rotas.
- [ ] Adicionar modos explícitos:
  `--routes`, `--enums`, `--dtos`, `--wire-names`, `--response-codes` e `--all`.
- [ ] Validar limites, alinhamento e contagem de cada região do header v29.
- [ ] Resolver `typeDefinitions`, `nestedTypes`, fields, methods e parâmetros.
- [ ] Resolver default values e compressed ints para enums.
- [ ] Resolver custom attributes para `[JsonProperty]`.
- [ ] Marcar fallback `SnakeCaseNamingStrategy` quando não houver override.
- [ ] Emitir JSON sanitizado, sem dump bruto de metadata.
- [ ] Criar metadata sintético mínimo para testes de todas as tabelas.
- [ ] Exigir os checks independentes:
  116 rotas, `game/auth/login-device`, `game/events/get-schedule`,
  `Success=1000` e família JWT 2110–2113.
- [ ] Se um sanity check falhar, abortar; nunca ajustar offset por tentativa.

### Gate da fase 12

- [ ] O extrator reproduz contratos determinísticos a partir do APK local.
- [ ] Nenhuma rota/DTO é transcrita à mão como fonte primária.
- [ ] Os testes sintéticos não contêm material proprietário.

## 20. Fase 13 — convergir as 116 rotas do servidor

O editor pode mostrar o progresso, mas a compatibilidade é implementada em
`server/src/**`. Trabalhar uma rota e um gate por vez.

### 20.1. Ciclo obrigatório por rota

1. selecionar a próxima tarefa:

```bash
python scripts/next_task.py --json
```

2. extrair request, response, tipos, nulabilidade, wire names e códigos;
3. registrar evidência `CONFIRMADO` ou manter `A VERIFICAR`;
4. implementar no módulo correto;
5. usar o envelope vivo de `server/src/index.js`;
6. omitir valores ausentes em vez de enviar numérico não-nullable como `null`;
7. persistir em `Repository`, com transação para recursos;
8. adicionar teste em `server/test/*.mjs` e no `package.json` quando novo;
9. rodar `cd server && npm test`;
10. observar request/response no cliente;
11. capturar fixture sanitizada com provenance `client`;
12. validar o fluxo com `client_harness.py`;
13. reiniciar servidor e provar persistência quando aplicável;
14. atualizar o registro somente pelos scripts;
15. regenerar a matriz;
16. fazer commit pequeno;
17. chamar `next_task.py` novamente.

### 20.2. Regras do wire

- Toda rota `/game/*` é POST com JSON e header `x-ubu-apiversion` correto.
- Autenticadas usam `x-ubu-token` ou Bearer.
- Envelope: `{ "uts": "yyyy-MM-ddTHH:mm:ss", "code": 1000, ... }`.
- `uts` é UTC sem timezone textual.
- `protocol.js` e `baseline.js` são legado; não importar em código novo.
- O path interno é `/game/*`; `normalizePath()` remove `/collections/doom`.
- Nunca responder fallback vazio e marcar como compatível.

### 20.3. Persistência

O registro atual possui somente duas rotas com persistência explicitamente
validada e muitas com `null`. Auditar a aplicabilidade antes de aceitar `null`:

- [ ] mutações de inventário, moeda, gear, slayer, talentos, capítulos, quests,
  rewards, inbox, eventos e battle pass devem sobreviver a restart quando o
  contrato exigir;
- [ ] rotas puramente descritivas podem ter `null`, com nota explicando por que;
- [ ] ampliar `generate_endpoint_matrix.py` para aceitar
  `persistence_validated=true|false|null` por CLI, com teste, em vez de editar o
  JSON à mão;
- [ ] guardar evidência do restart no campo de nota/fixture apropriado.

### 20.4. Ordem de módulos

Respeitar `module_priority` do registro:

1. gear;
2. slayers;
3. talents;
4. chapters;
5. quests;
6. reward-tracks;
7. inbox;
8. player;
9. events;
10. battle-pass;
11. daily-rewards;
12. idle-rewards;
13. store;
14. inventory;
15. armory;
16. tutorial;
17. session;
18. auth;
19. identity;
20. devices;
21. codes;
22. xbox;
23. bnet;
24. ads/IAP desativados por política.

Não pular para um módulo “mais interessante” enquanto o primeiro gate da fila
determinística estiver aberto, salvo bloqueio documentado.

### Gate da fase 13

- [ ] 116/116 contratos extraídos.
- [ ] 116/116 implementações sem fallback.
- [ ] 116/116 com requests/responses observados ou justificativa de rota
  inalcançável acompanhada de teste dirigido.
- [ ] 116/116 comportamentos aceitos pelo cliente, inclusive disabled-by-design.
- [ ] Todos os efeitos persistentes validados após restart.
- [ ] `compatibility.json` e matriz sincronizados.

## 21. Fase 14 — completar game data e conteúdo preservado

O cliente funcional depende de `/data`; não basta responder endpoints.

- [ ] Inventariar coleções esperadas pelo cliente a partir do metadata, game data
  local permitido e logcat.
- [ ] Garantir definições para resources, abilities, weapons, gear, launchers,
  ultimates, slayers, cosmetics, slots, chapters, stages, rewards, quests,
  battle passes, events, talents e armory.
- [ ] Extrair do logcat cada par `ability <Nome> id <N>` ausente.
- [ ] Corrigir o dataset na fonte local permitida, não criar definição no chute.
- [ ] Validar referências: todo RID apontado existe e tem categoria compatível.
- [ ] Validar starter bundle e slots primário/slayer.
- [ ] Validar custos, drops, XP, energia e regeneração.
- [ ] Validar todas as temporadas preservadas que o cliente realmente contém.
- [ ] Manter `server/data/game-data.json` ignorado; versionar somente schema,
  exemplos sem conteúdo proprietário e ferramentas clean-room.
- [ ] Exibir no Revival Studio apenas status, contagens e inconsistências
  sanitizadas do game data.

### Gate da fase 14

- [ ] `/revival/health` mostra `game_data_loaded: true`.
- [ ] `/data` autentica e entrega documento aceito pelo cliente.
- [ ] Boot e fluxos testados não geram `Cant find corresponding data tool data`.
- [ ] Nenhum dataset proprietário foi commitado.

## 22. Fase 15 — matriz de fluxos ponta a ponta

Cada linha deve ter: dispositivo, versão Android, conta limpa/existente, passos,
endpoints chamados, mutações esperadas, evidência antes/depois do restart e
resultado do logcat.

- [ ] instalação limpa;
- [ ] atualização sobre APK com mesma assinatura;
- [ ] conflito de assinatura tratado sem desinstalação automática;
- [ ] primeiro registro e login por device;
- [ ] login de conta existente;
- [ ] refresh/heartbeat de sessão;
- [ ] menu principal;
- [ ] user data e armory;
- [ ] equipar/upgrade/fuse/dismantle gear;
- [ ] upgrade e cosmético de Slayer;
- [ ] compra de talento;
- [ ] capítulo: start, update, vitória, derrota, revive e rewards;
- [ ] energia e regeneração com passagem de tempo;
- [ ] quests e milestones;
- [ ] daily e idle rewards;
- [ ] inbox: listar, ler, claim e delete;
- [ ] reward tracks;
- [ ] loja por moeda interna e quotas;
- [ ] eventos game mode/store offer/battle pass;
- [ ] cosméticos e entitlements;
- [ ] identidade local, devices e codes;
- [ ] Xbox/BNet indisponíveis de forma aceita;
- [ ] ads/IAP desativados sem bloquear progressão;
- [ ] reinício do servidor no meio de estado persistente;
- [ ] rede indisponível e retorno;
- [ ] certificado público;
- [ ] CA local em ambiente de laboratório;
- [ ] emulador Android;
- [ ] pelo menos um aparelho físico;
- [ ] Android 10 até a maior versão disponível para teste.

Usar um APK final recém-verificado em cada campanha relevante. Não reutilizar um
APK antigo depois de alterar host, CA, bundle ou branding.

## 23. Fase 16 — aba Compatibilidade no Revival Studio

- [ ] Ler `compatibility.json` sem modificá-lo diretamente.
- [ ] Mostrar total, DoD, schemas, validações de cliente, testes e fallbacks.
- [ ] Mostrar a próxima tarefa de `next_task.py --json`.
- [ ] Permitir abrir evidência e fixture sanitizada.
- [ ] Botões que alteram registro devem chamar scripts oficiais e mostrar diff.
- [ ] Nunca permitir checkbox manual “done”.
- [ ] Mostrar estado do servidor vivo em `/revival/research`.
- [ ] Em modo final, exigir `RESEARCH_MODE=false` e zero fallbacks.

### Gate da fase 16

- [ ] A UI não confunde `implemented` com DoD completo.
- [ ] O número exibido corresponde exatamente ao registro regenerado.
- [ ] Toda mutação do registro é auditável.

## 24. Fase 17 — acabamento, acessibilidade e empacotamento

- [ ] Tema escuro legível, sem depender apenas de cor para status.
- [ ] Navegação completa por teclado.
- [ ] Labels e mensagens em português claro.
- [ ] Escala correta em 100%, 125%, 150% e 200% no Windows.
- [ ] Layout utilizável em 1366×768 e telas maiores.
- [ ] Diálogos de arquivo iniciam em diretórios seguros, mas aceitam caminhos
  escolhidos pelo usuário.
- [ ] Erros mostram ação recomendada e caminho do relatório.
- [ ] Criar launcher `.bat` e `.sh` sem instalar dependências silenciosamente.
- [ ] Documentar execução por Python antes de considerar PyInstaller.
- [ ] Se empacotar, reproduzir build em CI sem incluir JARs baixados, APK,
  certificados ou assets proprietários.
- [ ] Criar `docs/REVIVAL-STUDIO.md` com tutorial do usuário.

## 25. Estratégia de testes do editor

### 25.1. Unitários sem APK proprietário

- [ ] normalização de hostname e URL;
- [ ] validação de caminhos;
- [ ] máquina de estados e invalidação de etapas;
- [ ] serialização de projeto sem segredos;
- [ ] runner, cancelamento e timeout;
- [ ] detecção de versões da toolchain;
- [ ] parse de relatórios;
- [ ] política de tipos Unity;
- [ ] mapeamento de diagnósticos;
- [ ] recursos Android sintéticos.

### 25.2. Fixtures sintéticas

- [ ] ZIP/APK mínimo;
- [ ] metadata v29 mínimo;
- [ ] bundle Unity mínimo quando possível;
- [ ] catálogo Addressables com CRC;
- [ ] manifest/resources Android mínimos;
- [ ] respostas health válidas e inválidas;
- [ ] logcats com cada assinatura conhecida.

### 25.3. Integração local privada

Executar somente na máquina autorizada com a cópia local do usuário:

- [ ] análise do APK 1.13.1;
- [ ] patch fast path quando aplicável;
- [ ] patch bundle-aware;
- [ ] loading screen;
- [ ] branding Android;
- [ ] um tipo adicional de asset Unity por vez;
- [ ] rebuild e assinatura;
- [ ] verificação final;
- [ ] instalação e harness.

## 26. Comandos de verificação final

A outra LLM deve executar estes comandos somente quando a implementação chegar ao
respectivo estágio.

```bash
# Gate completo local
python scripts/verify_everything.py

# Registro sincronizado
python scripts/generate_endpoint_matrix.py --check

# Servidor vivo, sem research fallback
python scripts/verify_everything.py \
  --server https://HOST \
  --strict-research

# APK final assinado + servidor
python scripts/verify_everything.py \
  --server https://HOST \
  --strict-research \
  --apk output/mighty-doom-revival.apk

# Cliente/emulador
python scripts/client_harness.py \
  --server https://HOST \
  --apk output/mighty-doom-revival.apk \
  --admin-token TOKEN \
  --duration 300 \
  --update-registry
```

Depois do harness, regenerar e verificar novamente:

```bash
python scripts/generate_endpoint_matrix.py
python scripts/generate_endpoint_matrix.py --check
python scripts/next_task.py
```

Resultado final esperado de `next_task.py`: nenhuma tarefa restante. Isso ainda
deve ser seguido por `verify_everything.py`; o fim da fila não substitui o gate.

## 27. Critério de conclusão do projeto

Só escrever “100% pronto” quando todos os itens abaixo forem verdadeiros:

- [ ] Revival Studio cobre todas as operações suportadas deste documento.
- [ ] Entrada original permanece byte a byte intacta.
- [ ] Toda saída possui relatório, SHA-256 e assinatura verificada.
- [ ] O APK final passou em `verify_patched_apk.py` depois da assinatura.
- [ ] Todo bundle modificado possui CRC de catálogo zerado e validado.
- [ ] O app instala e abre.
- [ ] Boot não contém assinatura fatal.
- [ ] Menu e carregamento de cena funcionam.
- [ ] Matriz de fluxos da seção 22 passou.
- [ ] `RESEARCH_MODE=false` em validação final.
- [ ] Zero fallbacks observados.
- [ ] 116/116 rotas satisfazem o DoD aplicável.
- [ ] Ads e IAP permanecem desativados e não bloqueiam progressão.
- [ ] Game data necessário está completo para os fluxos preservados.
- [ ] Persistência sobrevive a restart.
- [ ] Emulador e aparelho físico passaram.
- [ ] Suíte Node passa.
- [ ] Regressões Python passam.
- [ ] Registro e matriz estão sincronizados.
- [ ] Nenhum material proprietário ou segredo está versionado.
- [ ] Documentação foi corrigida para refletir o código atual.

## 28. Protocolo de trabalho e commits para a LLM executora

Antes de cada commit:

```bash
git status --short
git diff
git diff --cached
```

- [ ] Stage somente caminhos explícitos.
- [ ] Não misturar refactor, feature e correção de endpoint no mesmo commit.
- [ ] Rodar os testes proporcionais ao risco.
- [ ] Registrar falha de teste exatamente como ocorreu.
- [ ] Não fazer push sem pedido do usuário.

Sequência sugerida de commits:

1. `test: lock Revival Studio foundations`;
2. `refactor: expose patcher services for Studio`;
3. `feat: add Revival Studio project workflow`;
4. `feat: add server and endpoint patch workflow`;
5. `feat: integrate loading and Android branding`;
6. `feat: add safe Unity asset catalog`;
7. `feat: add build signing and verification workflow`;
8. `feat: add device diagnostics and compatibility dashboard`;
9. commits pequenos por rota/fluxo de servidor;
10. `docs: finalize Revival Studio and compatibility evidence`.

## 29. Condições de parada

A LLM deve parar e pedir decisão quando:

- o APK não corresponde ao alvo 1.13.1;
- a única solução exige crescer/realocar metadata sem implementação formal;
- UnityPy não consegue reabrir o bundle alterado;
- o CRC correspondente não pode ser localizado com segurança;
- um selector de asset ficou ambíguo;
- a ação exigiria redistribuir conteúdo proprietário;
- a ação exigiria desinstalar o app ou apagar dados sem autorização;
- o contrato do endpoint não pôde ser extraído;
- testes contradizem documentação;
- há alterações alheias que se sobrepõem aos mesmos arquivos;
- o servidor de produção exigiria mudança não autorizada.

Nesses casos, preservar workspace e relatórios, marcar `A VERIFICAR` e explicar a
evidência. Não contornar o bloqueio para “terminar mais rápido”.

## 30. Primeira tarefa concreta da próxima LLM

A próxima LLM não deve começar desenhando telas. A primeira entrega deve ser:

1. inventariar todos os `.bat` e `.sh` e preencher a tabela da seção 6.1;
2. auditar a linha de base e corrigir as divergências documentais da seção 4.4;
3. centralizar o resolvedor de Java 17 e toolchain;
4. criar os modelos, a máquina de estados e o `JobRunner` com testes;
5. adaptar `analyze_apk.py`, `check_revival_server.py` e
   `check_patch_length.py` como primeiros serviços;
6. criar a janela mínima com menus Projeto, APK, Servidor, Cliente, Testes e Log;
7. fazer os wrappers antigos encaminharem para o launcher Python, sem remover
   ainda os caminhos headless;
8. passar o gate local antes de incorporar patch, loading ou assets.

Essa ordem prova primeiro a fundação e evita construir uma GUI bonita em cima de
processos duplicados ou não determinísticos.
