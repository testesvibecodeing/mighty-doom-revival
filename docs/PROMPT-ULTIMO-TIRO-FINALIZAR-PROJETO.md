# ÚLTIMO TIRO — finalizar o Mighty DOOM Revival sem “pronto” parcial

Você está assumindo o repositório `mighty-doom-revival` para uma execução final,
contínua e orientada por evidência. O objetivo é concluir o projeto segundo o
contrato do próprio repositório, não apenas obter testes locais verdes ou fazer o
menu abrir.

Este prompt consolida a linha de base medida em **2026-08-23**. Documentos de
status antigos continuam úteis como histórico, mas não prevalecem sobre o código,
os testes, `compatibility.json`, `research/DEAD-ENDS.md` e `AGENTS.md` atuais.

## Ordem de autoridade e leitura obrigatória

Antes de editar qualquer arquivo, leia integralmente, nesta ordem:

1. `AGENTS.md`;
2. `research/DEAD-ENDS.md`;
3. `compatibility.json` e `docs/ENDPOINT-MATRIX.md`;
4. `docs/PLANO-REVIVAL-STUDIO-100-POR-CENTO.md`;
5. `docs/ENTREGA-LOGIN-EMAIL-SMTP.md`;
6. código e testes relacionados à tarefa selecionada por `scripts/next_task.py`.

Invoque as skills do repositório antes do trabalho correspondente:

- `revival-server`: qualquer alteração em `server/src/**`, contrato HTTP/JSON,
  persistência, evento ou painel;
- `il2cpp-recon`: rota, DTO, enum, wire name ou código de erro do cliente;
- `apk-patch`: geração, alteração, assinatura ou verificação de APK;
- `boot-diagnostics`: loading em 100%, tela preta, crash, erro de parse, CRC ou
  investigação com logcat.

Em conflito entre fontes, use esta precedência:

1. `AGENTS.md`;
2. `research/DEAD-ENDS.md`;
3. skills aplicáveis;
4. `compatibility.json` e scripts geradores;
5. código e testes atuais;
6. este prompt;
7. roadmaps e relatórios históricos.

## Mandato de execução

- Trabalhe continuamente enquanto houver uma frente segura e independente.
- Não pare para pedir autorização entre inventário, correções, testes, build e
  E2E.
- Uma falha de teste é trabalho a diagnosticar, não motivo para encerrar.
- Se faltar uma credencial externa ou aparelho físico, conclua primeiro tudo que
  independe disso e reporte o bloqueio somente na entrega final.
- Não faça push sem pedido explícito do usuário.
- Faça commits apenas se isso estiver autorizado na sessão. Antes de cada commit,
  inspecione `git status`, `git diff` e `git diff --cached`; use caminhos explícitos
  no stage e nunca `git add .`.
- Não use `git reset`, `git checkout --`, `git clean`, `git add -f` ou outra ação
  que descarte/misture o trabalho vivo do usuário.
- Não afrouxe teste, assert, verificador ou gate para obter verde.
- Não crie rota, DTO, campo de wire ou código de erro por intuição.
- Em toda evidência, escreva `CONFIRMADO` somente para o medido nesta execução,
  com comando e saída; use `A VERIFICAR` para o restante.

## Linha de base medida — não confundir com conclusão

### Git — CONFIRMADO em 2026-08-23

```text
branch                 main, sincronizada com origin/main
HEAD                   eacf020ba78de9515e43201a22d8f00a6fc8b229
staging                vazio
git diff --check       exit 0
```

A árvore está suja e pertence ao usuário. Foram observadas alterações em 17
fixtures client sob `tests/fixtures/protocol/client/**` e estes arquivos não
rastreados:

```text
docs/PROMPT-OPUS-CORRIGIR-AUDITORIA-FINAL-E-ENTREGAR.md
docs/PROMPT-OPUS-FINALIZAR-LOGIN-EMAIL-SMTP-E2E.md
server/setup-server.bat
server/setup-server.sh
server/start-server.bat
server/start-server.sh
```

Este próprio documento também começa não rastreado. Preserve tudo. Os quatro
wrappers de servidor acima foram classificados pela frente anterior como fora do
escopo de commit; não os versione nem apague sem uma decisão explícita nova.

As fixtures alteradas parecem ser recapturas sanitizadas, mas a autoria e a
proveniência devem ser verificadas por diff e pelos validadores antes de qualquer
stage. Não reverta timestamps/payloads só para reduzir o diff.

### Gates locais — CONFIRMADO em 2026-08-23

```text
python scripts/verify_everything.py
RESULTADO: PASS — 46 verificações
```

O gate confirmou:

- `npm test` passou;
- todas as regressões Python autodescobertas passaram;
- `compatibility.json` e `docs/ENDPOINT-MATRIX.md` estão sincronizados;
- nenhuma rota validada depende de fallback;
- fixtures client sanitizadas estão coerentes.

Esse PASS local **não significa que o projeto acabou**. A mesma execução mediu
somente `4/116` rotas com DoD completo.

### Compatibilidade — CONFIRMADO em 2026-08-23

```text
rotas registradas                    116
implemented=true                    116
schema_extracted=true                79
request_observed=true                22
response_observed=true               22
client_validated=true                11
persistence_validated=true            2
regression_test=true                 92
uses_fallback=true                    0
DoD completo                          4
```

As quatro rotas com DoD completo são as três rotas validadas do fluxo de capítulo
(`start`, `update`, `end`) e `game/armory/get`. Confirme novamente pelo registro
atual antes de citar os nomes na entrega final.

O seletor determinístico mediu:

```text
python scripts/next_task.py --json
module   gear
endpoint game/gear/apply-cosmetic
gate     request_observed
```

Toda a fila inicial de `gear` está implementada e tem schema/teste, mas ainda
precisa de request/response reais e validação no cliente.

### Servidor público — CONFIRMADO em 2026-08-23

```text
URL                https://doom.sualoja.app.br/revival/health
HTTP               200
client_version     1.13.1
api_version        24.0.0
game_data_loaded   true
research_mode      true
instance_id        ausente
build_id           ausente
contract_revision  ausente
packs              0
events             0
apk_available      false
```

`scripts/check_revival_server.py` confirma TLS, versão, GameData, prefixo Gear e
timestamp do wire, mas o servidor público **não atende o gate de produção**: o
`RESEARCH_MODE` está ligado e o health não identifica instância, build nem revisão
de contrato. `packs=0`, `events=0` e `apk_available=false` precisam ser
classificados contra a configuração pretendida; não presuma que sejam aceitáveis
ou defeitos sem medir o requisito.

### APK local — CONFIRMADO estaticamente em 2026-08-23

```text
arquivo  output/mighty-doom-revival.apk
SHA-256  7646f3208ed3333229361717edb910cad5155f89bd9f869e7e5b627c50aae512
host     doom.sualoja.app.br
```

`scripts/verify_patched_apk.py` passou no arquivo acima: host Revival presente,
host Gear oficial ausente nas áreas verificadas, bundle legível, sem marcador LAB
inseguro e `cleartext_permitted=false`.

Isso é somente uma prova estática dos bytes atuais. O arquivo não pode ser chamado
de entrega final enquanto não houver, na mesma execução final:

- servidor público compatível e identificado;
- build pelo pipeline normal, sem override de laboratório;
- assinatura verificada;
- `verify_patched_apk.py` executado depois da assinatura no arquivo copiado para
  `output/`;
- hash correlacionado com o APK instalado;
- E2E limpo contra a instância pública identificada.

## Veredito inicial obrigatório

O projeto **não está 100% pronto** nesta linha de base. Ele já possui um fluxo
jogável e boa cobertura automatizada, mas falha em três critérios centrais do
próprio repositório:

1. somente `4/116` rotas satisfazem o DoD;
2. o servidor público ainda opera com `research_mode=true` e health antigo;
3. falta correlacionar um APK final novo, servidor publicado, instalação e E2E na
   mesma revisão.

Não rebaixe a definição de pronto para contornar esses fatos.

## Regras técnicas inegociáveis

1. Nunca versionar APK, XAPK, AAB, assets, bundles, dumps, logcats, pcaps,
   screenshots, keystores, certificados, bancos, tokens ou credenciais.
2. Nunca ultrapassar o orçamento de hostname medido por
   `scripts/check_patch_length.py`; exit 4 exige o caminho bundle-aware.
3. Alterou bundle em `assets/aa/**`: execute `zero_catalog_crc()` e teste a
   pós-condição.
4. Nunca declarar APK pronto sem `scripts/verify_patched_apk.py` passando no
   arquivo final **depois** da assinatura.
5. Nunca enviar número não-nullable como `null`; omita o campo quando o contrato
   exigir ausência.
6. Nunca usar `server/src/protocol.js` ou `baseline.js` para código novo; o wire
   vivo está no caminho atual importado pelo servidor.
7. Nunca editar `server/config/revival.json`, `packs.json`, `events.json` ou
   `site.json`; altere somente os `*.example.json` quando a mudança versionada for
   realmente necessária.
8. Nunca marcar rota como concluída porque respondeu HTTP 200.
9. Nunca usar fixture `server-replay` como prova de cliente. Evidência de cliente
   precisa de request/response pareados, sanitizados e `provenance=client`.
10. Nunca promover hipótese já refutada em `research/DEAD-ENDS.md` sem evidência
    nova e discriminante.

## Fase 1 — consolidar a árvore viva

Execute e preserve as saídas sanitizadas em `work/final-shot/`:

```powershell
git status --short --branch
git diff --stat
git diff
git diff --cached --name-status
git diff --check
git log -10 --oneline
```

Depois:

1. classifique cada alteração local por autoria provável, objetivo e teste;
2. valide as 17 fixtures com a suíte e com o gerador da matriz;
3. confirme que nenhum valor sensível cru foi introduzido, sem imprimir o valor;
4. mantenha documentos e wrappers não rastreados intactos;
5. não faça limpeza cosmética nem normalização massiva de EOL;
6. grave `work/final-shot/01-ARVORE-E-LINHA-DE-BASE.md` e continue.

Se as fixtures forem capturas reais coerentes, elas podem integrar um commit
específico de evidência, se commits estiverem autorizados. Se não for possível
provar a proveniência, deixe-as fora do stage e registre `A VERIFICAR`.

## Fase 2 — publicar e identificar o servidor correto

Audite primeiro `server/src/instance.js`, `server/src/config.js`, o instalador e o
mecanismo de deploy já existente. Não invente um novo canal de deploy.

O health de produção deve expor e satisfazer, no mínimo:

```text
contract_revision >= revisão exigida pelo pipeline atual
research_mode == false
instance_id presente e não secreto
build_id presente e identificando os bytes executados
build_dirty != true
client_version == 1.13.1
api_version == 24.0.0
game_data_loaded == true
```

Antes de qualquer deploy autorizado:

1. resolva o host, serviço e diretório remoto exatos;
2. faça backup recuperável de código, configs runtime e SQLite afetados;
3. registre plano de rollback sem segredo;
4. preserve os configs runtime ignorados;
5. publique pelo mecanismo já existente;
6. reinicie somente o serviço necessário;
7. meça health, `/revival/research`, prefixo `/collections/doom` e logs;
8. prove `research_mode=false` e delta de fallback zero.

Se não houver credencial de VPS, continue todas as fases locais. Não invente
credencial, não abra acesso inseguro e não chame um servidor local de público.

Aceite desta fase:

```powershell
python scripts/check_revival_server.py --server https://doom.sualoja.app.br
python scripts/verify_everything.py --server https://doom.sualoja.app.br --strict-research
```

O segundo comando precisa passar sem `--skip-node`, `--skip-python` ou override.

## Fase 3 — fechar a matriz de compatibilidade, rota por rota

Não trabalhe a partir de uma lista inventada. Use exclusivamente:

```powershell
python scripts/next_task.py --json
```

Enquanto o resultado contiver uma tarefa, execute o ciclo completo:

1. leia a entrada atual em `compatibility.json`;
2. consulte `research/DEAD-ENDS.md`;
3. extraia o contrato real com `il2cpp-recon` e
   `scripts/dump_il2cpp_metadata.py` quando o gate for schema/DTO/wire;
4. implemente apenas o contrato medido;
5. adicione ou ajuste teste de servidor com casos de sucesso, erro e tipos;
6. execute o servidor local com dados de teste controlados;
7. dispare a tela/ação real no cliente;
8. capture request e response pareados com `scripts/client_harness.py`;
9. sanitize preservando tipos e grave fixture `provenance=client`;
10. prove ausência de assinatura fatal, parse malformado e fallback;
11. quando a rota mutar estado, reinicie o servidor e prove persistência;
12. atualize o registro somente pelos comandos suportados do gerador;
13. rode testes proporcionais e o gate agregado;
14. se commits estiverem autorizados, faça um commit pequeno e coerente;
15. rode `next_task.py --json` novamente e continue.

Comece por:

```text
game/gear/apply-cosmetic -> request_observed
```

Depois deixe o seletor decidir a ordem. Não pule para um módulo mais conveniente.

Para uma rota, DoD significa simultaneamente:

```text
schema_extracted=true
implemented=true
request_observed=true
response_observed=true
client_validated=true
persistence_validated=true ou null somente quando não se aplica de fato
regression_test=true
uses_fallback=false
```

As 10 rotas de ads/IAP continuam desativadas por política, mas precisam de
contrato extraído, resposta desativada aceita pelo cliente, teste e evidência de
cliente. “Fora de escopo” não autoriza payload inventado, erro genérico que quebra
o parse nem `ok()` vazio de pesquisa.

Se uma rota não for emitida pelo cliente no fluxo esperado:

- não fabrique fixture;
- não marque request/response/client como verdadeiros;
- melhore a instrumentação e tente ações discriminantes;
- registre o fluxo, a build, a instância, o cursor e a razão de inconclusão;
- só classifique como bloqueio depois de esgotar os fluxos reais que poderiam
  emiti-la.

Aceite desta fase:

```text
python scripts/next_task.py --json -> nenhuma tarefa restante
compatibility.json                -> 116/116 DoD aplicável
uses_fallback                     -> 0/116
```

## Fase 4 — revalidar autenticação, conta, SMTP e credencial local

O código atual declara login por e-mail, senha com scrypt, recuperação por SMTP,
preflight da credencial e supressão da tela Google. Trate isso como código a
revalidar, não como fato eterno.

Prove em servidor local e depois na instância pública identificada:

1. cadastro pelo site com e-mail e senha;
2. login normal independente de SMTP;
3. e-mail inexistente com resposta neutra e sem envio;
4. SMTP ausente com erro explícito, sem fallback inseguro;
5. senha temporária forte, expiração, rate limit e limite de tentativas;
6. falha SMTP revogando imediatamente o reset criado;
7. senha antiga válida até o uso da temporária;
8. primeiro uso da temporária promovendo a nova senha e encerrando sessões;
9. senha armazenada somente como scrypt/salt, sem plaintext em DB/WAL/log;
10. senha SMTP nunca retornando pela API;
11. certificado SMTP validado por padrão;
12. Activity pedindo e-mail/senha, abrindo cadastro no site e nunca exibindo ID
    numérico como credencial;
13. senha alterada no site fazendo o preflight apagar credencial obsoleta ou
    exigir login novamente de forma determinística;
14. nenhum segredo em logcat, fixture, relatório, Intent ou Toast;
15. popup Google Play Games ausente no primeiro boot e em restart.

O E2E de conta não pode ler `credentials.json` por ADB como atalho para descobrir
credenciais. Use somente dados que um jogador conseguiria digitar/copiar pela UI.

## Fase 5 — concluir o Revival Studio e o pipeline real

Compare a implementação atual com as operações suportadas em
`docs/PLANO-REVIVAL-STUDIO-100-POR-CENTO.md`. Uma função não implementada não deve
ser simulada por botão inerte; superfícies inseguras ou não provadas devem aparecer
honestamente como somente leitura/não suportadas.

Valide no fluxo normal do Studio:

- abrir/criar projeto sem modificar o APK original;
- análise e perfil do servidor;
- precheck de hostname;
- escolha automática do fast path ou bundle-aware;
- `network_security_config` HTTPS seguro;
- Activity Revival e manifest;
- loading screen e branding suportado;
- CRC de catálogo após qualquer bundle alterado;
- rebuild com toolchain pinada e Java 17;
- assinatura;
- verificação da assinatura;
- `verify_patched_apk.py` pós-assinatura;
- cópia final para `output/` com hash correlacionado;
- relatório completo e retomada de projeto;
- segunda execução idempotente ou falha segura claramente explicada.

Não use `--allow-incompatible-server`, `override_lab`, HTTP LAB ou cleartext no
artefato de entrega.

## Fase 6 — gerar o APK final somente depois do servidor compatível

Pré-condições:

```text
health público identificado
contract_revision aceita
research_mode=false
build limpo
zero fallback acumulado no fluxo de validação
gates locais verdes
```

Então:

1. execute o job normal do Studio com HTTPS;
2. use a toolchain pinada, inclusive Java 17 do projeto;
3. preserve o APK de entrada byte a byte;
4. se houver alteração em bundle, prove CRC zerado;
5. reconstrua e assine;
6. verifique a assinatura;
7. copie o resultado final para um nome inequívoco em `output/`;
8. execute o verificador **no arquivo copiado e assinado**;
9. gere relatório em `work/final-shot/reports/`;
10. calcule SHA-256 e tamanho;
11. instale exatamente esses bytes no AVD/aparelho;
12. puxe o `base.apk` instalado apenas para `work/`, calcule o hash e correlacione.

Gate obrigatório:

```powershell
python scripts/verify_patched_apk.py `
  --apk output/mighty-doom-revival.apk `
  --server doom.sualoja.app.br `
  --report work/final-shot/reports/final-apk-verification.json
```

Não reutilize o hash `7646...e512` como prova do novo build. O hash final deve ser
medido novamente após todas as correções e após a assinatura.

## Fase 7 — E2E final correlacionado

Use AVD descartável/snapshot para testes destrutivos. Nunca execute `pm clear` no
AVD principal que guarda progresso do usuário.

Cada execução deve correlacionar:

```text
SHA-256 do APK instalado
host esperado
instance_id e build_id do health
cursor de /revival/requests antes/depois
janela temporal do logcat
ação do usuário que dispara rede
requests/responses pareados
delta de fallbacks
estado persistido antes/depois de restart
```

Matriz mínima:

1. instalação limpa;
2. primeira abertura sem conta Google configurada;
3. criação de conta pelo site;
4. login por e-mail/senha no APK;
5. bootstrap completo até o menu;
6. ausência de popup Google Play Games;
7. evento, loja, inbox, daily/idle rewards e battle pass sem erro de parse;
8. início, atualização e fim de capítulo;
9. recompensa e desbloqueio persistidos;
10. force-stop e restart com `login-device` válido;
11. restart do servidor e nova leitura do estado;
12. troca de senha e recuperação determinística da credencial local;
13. instalação limpa com login de conta existente;
14. ads/IAP desativados sem bloqueio de progressão;
15. zero `Malformed response payload`, CRC mismatch, NRE fatal, `Failed to
    launch`, tela preta ou loading infinito;
16. zero fallback do `RESEARCH_MODE`;
17. emulador aprovado;
18. aparelho físico aprovado;
19. versões Android previstas pela matriz do projeto testadas ou bloqueio
    explicitamente provado por indisponibilidade de dispositivo.

Use `scripts/client_harness.py` como fonte estruturada. Uma tela visualmente aberta
sem tráfego correlacionado não prova que o cliente atingiu a instância esperada.

## Fase 8 — segurança, propriedade e higiene de release

Antes de qualquer commit ou declaração final:

1. liste somente os caminhos rastreados e procure extensões/marcadores proibidos;
2. rode a varredura de segredo sem imprimir valores encontrados;
3. confirme que `input/`, `output/`, `work/`, `reports/`, `.tools/` e
   `server/data/` continuam ignorados;
4. confirme que nenhum config runtime ignorado foi staged;
5. confirme staging por caminho explícito;
6. atualize docs apenas com fatos medidos;
7. regenere a matriz pelo script; nunca edite a tabela gerada à mão;
8. deixe claro o tipo de chave de assinatura e seu impacto em atualização;
9. mantenha evidências proprietárias/sensíveis somente em diretórios ignorados;
10. confirme que os quatro wrappers não entraram em commit por acidente.

## Gates finais — execute, corrija e repita

Não use versões abreviadas ou flags de skip na rodada final:

```powershell
python run_tests.py

Push-Location server
npm test
Pop-Location

python scripts/generate_endpoint_matrix.py
python scripts/generate_endpoint_matrix.py --check
python scripts/next_task.py --json

python scripts/check_revival_server.py `
  --server https://doom.sualoja.app.br

python scripts/verify_patched_apk.py `
  --apk output/mighty-doom-revival.apk `
  --server doom.sualoja.app.br `
  --report work/final-shot/reports/final-apk-verification.json

python scripts/verify_everything.py `
  --server https://doom.sualoja.app.br `
  --strict-research `
  --apk output/mighty-doom-revival.apk

git diff --check
git status --short --branch
git diff --cached --name-status
```

Aceitação:

| Gate | Resultado exigido |
|---|---|
| Python | toda suíte autodescoberta passa |
| Node | toda suíte passa |
| Registro | gerador `--check` passa |
| Fila | `next_task.py --json` não retorna tarefa |
| Compatibilidade | `116/116` DoD aplicável |
| Fallback | zero em registro e servidor vivo |
| Produção | health identificado, revisão aceita, `research_mode=false` |
| APK | assinado e verificado pós-assinatura |
| Segurança de rede | HTTPS, sem LAB e sem cleartext |
| Cliente | instalação, boot, menu, gameplay e restart passam |
| Persistência | estado sobrevive a restart do app e do servidor |
| Conta | cadastro/login/SMTP/troca de senha passam sem segredo exposto |
| Google | popup/rotas Google ausentes |
| Dispositivos | emulador e físico passam |
| Git | sem material proprietário, segredo ou staging acidental |

## Política de bloqueio

Só encerre como `BLOQUEADO` quando a mesma condição externa realmente impedir a
continuação e todas as frentes independentes estiverem concluídas. Exemplos:

- credencial da VPS ausente;
- nenhum AVD utilizável depois de tentativas discriminantes;
- aparelho físico exigido mas não disponibilizado;
- ação real necessária do cliente não alcançável sem dado externo específico.

Não são bloqueios finais:

- teste corrigível falhando;
- necessidade de escolher arquitetura;
- ADB inicialmente vazio;
- documentação divergente;
- build demorado;
- necessidade de reexecutar o pipeline;
- rota ainda sem fixture;
- servidor local ainda não iniciado.

Um bloqueio final deve trazer:

1. o dado/autoridade/estado exato que falta;
2. pelo menos três tentativas discriminantes já executadas, quando aplicável;
3. comandos, exits e evidências sanitizadas;
4. tudo que foi concluído apesar do bloqueio;
5. o comando exato de retomada.

## Formato da única entrega final

Responda uma única vez com `CONCLUÍDO` ou `BLOQUEADO`. Não use “quase pronto”,
“pronto localmente” ou “pronto para auditoria” como substituto da conclusão.

Inclua:

- veredito e escopo realmente concluído;
- commits feitos, se autorizados, e arquivos alterados;
- estado final de Git/staging e disposição dos quatro wrappers;
- tabela de todos os gates com comando, exit code e resultado;
- contagem final de cada gate do `compatibility.json` e DoD total;
- resultado final de `next_task.py --json`;
- health público com `instance_id`, `build_id`, revisão e research mode;
- SHA-256/tamanho do APK final e caminho do relatório pós-assinatura;
- correlação do hash com o APK instalado;
- prova E2E de conta, boot, menu, gameplay, restart e persistência;
- prova de ausência de popup Google, erro fatal, fallback e segredo exposto;
- política/chave de assinatura usada, sem divulgar segredo;
- lista curta de pendências, separando `CONFIRMADO` de `A VERIFICAR`;
- rollback do deploy, se houve deploy.

Somente declare `CONCLUÍDO` se todos os gates aplicáveis da tabela estiverem
verdes e não existir tarefa restante no registro. Até lá, o resultado honesto é
`BLOQUEADO` acompanhado da retomada exata.
