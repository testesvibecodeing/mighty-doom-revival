# PROMPT PARA O OPUS — FINALIZAR LOGIN POR E-MAIL, SMTP, APK E E2E SEM PAUSAS

Você está assumindo uma árvore de trabalho viva e editada em paralelo. Sua tarefa
é **terminar a entrega**, não produzir outra auditoria intermediária. Leia
`AGENTS.md` inteiro, consulte `research/DEAD-ENDS.md` e invoque as skills
`revival-server`, `apk-patch` e `boot-diagnostics` antes das respectivas ações.

## Regra de execução: não pare entre fases

- Não pergunte “posso continuar?”, “libera a próxima fase?” ou equivalentes.
- Não encerre depois de inventário, testes locais, build estático ou deploy.
- Execute continuamente: auditoria curta → correções → testes → deploy possível →
  build final → instalação → E2E → persistência após restart → relatório único.
- Se uma frente depender de credencial externa realmente ausente, continue todas
  as demais frentes independentes. Só declare bloqueio no final, depois de
  esgotá-las, identificando exatamente a credencial/estado ausente.
- Não promova hipótese a fato. Use `CONFIRMADO` apenas para o que você medir nesta
  execução; todo o restante fica `A VERIFICAR`.
- Não afrouxe testes, não remova asserts e não transforme erro em warning para
  deixar o gate verde.

## Estado que você está recebendo

Últimos commits em `main`:

```text
c32c292 feat(studio): Activity pelo botao normal, preflight de contrato e verificacoes que medem
a109c2d fix(server): next_claim e DURACAO, identidade de build honesta e sanitizacao por tipo
52f3c50 docs: DEAD-ENDS com 6 hipoteses novas refutadas + extrator IL2CPP e drift documental
3760d81 feat(auth): RevivalAuthActivity como unico launcher, sem Google Play Games
f53e6c7 feat(evidencia): prova de aterrissagem no harness + gate autodescoberto + fixtures client reais
3a47406 fix(server): 3 contratos do wire provados no cliente + regra do null no envelope
```

Há mudanças **não commitadas** importantes. Não use `git reset`, `git checkout --`,
`git clean`, `git add .` ou qualquer ação que apague/misture trabalho alheio.
Comece por:

```bash
git status --short
git diff --cached --name-status
git diff --stat
```

`git diff --cached` estava vazio na passagem deste prompt.

### Mudanças de autenticação já implementadas pelo Codex — audite, integre e finalize

```text
scripts/revival_auth/android/RevivalAuthActivity.java
server/public/account.html
server/public/assets/js/account.js
server/src/db.js
server/src/index.js
server/src/mail.js
server/test/account.mjs
server/test/mail-auth.mjs
tests/test_patch_revival_auth.py
```

O painel também tem alterações vivas em `server/public/slayer.html`,
`server/public/assets/js/slayer.js`, `server/public/assets/css/slayer.css`,
`server/src/admin.js` e `server/test/admin-ui.mjs`. Algumas nasceram em outra
frente. Preserve-as e integre por diff; não as substitua por uma versão antiga.

### Trabalho paralelo que não pode ser descartado

Os seguintes arquivos estavam sendo trabalhados na frente de prova LAB/E2E:

```text
scripts/client_harness.py
scripts/patch_lab_http.py
tests/test_client_harness.py
tests/test_patch_lab_http.py
tests/test_verify_cleartext.py
tests/fixtures/protocol/client/**
```

Não assuma autoria exclusiva. Leia o diff atual antes de editar e faça apenas a
correção necessária, preservando a intenção e as evidências existentes.

Os quatro wrappers abaixo continuam fora do escopo e não devem entrar em commit:

```text
server/setup-server.bat
server/setup-server.sh
server/start-server.bat
server/start-server.sh
```

Também preserve documentos não rastreados já existentes. Nunca versione APK,
assets, dumps, screenshots, certificados, keystores, bancos ou conteúdo de
`input/`, `output/`, `work/`, `.tools/` e `reports/`.

## Contrato funcional obrigatório

### 1. Login do jogador

- A tela do APK deve pedir **e-mail e senha**, nunca ID numérico.
- Cadastro é feito no site; o APK deve abrir
  `https://doom.sualoja.app.br/account?mode=register` pelo navegador.
- A tela do APK deve mostrar claramente `doom.sualoja.app.br`.
- O botão **CRIAR CONTA NO SITE** precisa abrir o navegador de verdade.
- O login da Activity usa `/account/login` com `{email, password}`.
- O response fornece identidade pública (`account.id` e `account.uuid`); a senha
  nunca volta no response.
- A Activity monta o `credentials.json` exigido pelo cliente Unity usando o ID,
  UUID e a senha digitada. Não invente campo de `/game/*`.
- O fluxo antigo da Activity por `game/auth/register` ou ID numérico não pode
  permanecer acessível.

### 2. Armazenamento de senha

O usuário chamou isso de “senha criptografada”. A implementação correta no
servidor é **hash não reversível**, não criptografia recuperável:

- novas senhas: `scrypt` com salt aleatório individual;
- comparação constante (`timingSafeEqual`);
- nenhum plaintext em SQLite, log, response, fixture ou relatório;
- hashes SHA-256 legados, se ainda aceitos para migração, devem ser convertidos
  para scrypt no primeiro login válido;
- senha temporária também fica apenas como hash no banco.

Não faça uma afirmação falsa sobre o arquivo interno do cliente: o
`credentials.json` contém a senha porque esse é o contrato real do
`Ubu.CredentialStore`. Ele deve ficar apenas no diretório privado do app e nunca
ser logado, enviado por Intent/Toast ou incluído em evidência. Não invente
criptografia nesse arquivo se a Unity não souber decifrá-la.

### 3. “Esqueci minha senha” exclusivamente por SMTP

- Só funciona quando um administrador configurou SMTP em `/slayer`.
- Sem SMTP completo: HTTP 503 `smtp-not-configured`; não existe fallback local,
  recovery code público nem login sem senha.
- E-mail inexistente recebe resposta neutra 200 e nenhum e-mail é enviado
  (anti-enumeração).
- Conta existente recebe senha temporária forte, validade de 30 minutos.
- Mínimo de 60 segundos entre pedidos para a mesma conta.
- Máximo de tentativas deve ser limitado.
- Se o envio SMTP falhar, revogue imediatamente a senha temporária criada.
- Pedir recuperação não invalida a senha antiga antes de a temporária ser usada.
- No primeiro login válido com a temporária, ela passa a ser a senha ativa, as
  sessões web anteriores são encerradas e todos os resets pendentes são usados.
- O painel permite trocar para uma senha permanente.
- `/account/email-code/request`, `/account/email-code/login` e o reset antigo por
  recovery code devem responder 410 e não autenticar.
- A senha SMTP nunca volta na API do painel; campo vazio preserva a salva.

Revise ainda `server/src/mail.js`: TLS/STARTTLS precisa ser tratado com segurança.
Não aceite certificado SMTP inválido silenciosamente em produção e não imprima
usuário, senha temporária ou senha SMTP em log.

### 4. Corrigir o risco de credencial temporária obsoleta no APK

Audite este caso ponta a ponta e entregue uma solução real:

1. jogador entra no APK usando a senha temporária;
2. o APK grava essa senha no `credentials.json` e abre a Unity;
3. jogador troca a senha no site;
4. o arquivo local ficaria com a senha antiga e o boot seguinte poderia pular a
   tela Revival e falhar no `login-device`.

Não deixe esse dead-end. A aceitação é: depois de trocar a senha temporária por
uma permanente, o próximo boot entra com a credencial nova ou volta de forma
determinística à tela de login. Não invente rota `/game/*`; uma solução pode usar
`/account/*`, UX de troca obrigatória antes de persistir ou validação explícita,
mas precisa ser testada no APK real.

### 5. Painel administrativo SMTP

- Área SMTP profissional no painel: host, porta, TLS/SSL, usuário, senha de
  aplicativo, remetente e nome do remetente.
- Mostrar estado `configurado/não configurado` sem revelar segredo.
- Explicar que SMTP habilita somente a recuperação por senha temporária.
- O login normal por e-mail/senha funciona independentemente de SMTP.
- Sem SMTP, o botão do APK deve explicar claramente que a recuperação foi
  desabilitada pelo administrador.

## Defeito restante do gate Python

Na passagem mais recente:

```text
python run_tests.py
37/38 arquivos OK
falha única: tests/test_verify_cleartext.py
```

Em uma execução a falha foi `cleartext_permitted False is not True`; em outra,
durante trabalho paralelo, `BadZipFile: File is not a zip file`. Descubra a causa
real. O teste LAB precisa:

- construir/usar artefato temporário isolado e completo;
- não depender de `output/` ou de arquivo sendo sobrescrito por outro job;
- provar `cleartext_permitted: true` apenas no APK explicitamente LAB;
- provar `cleartext_permitted: false` no entregável HTTPS;
- falhar fechado se o AXML/XML não puder ser lido;
- nunca enfraquecer o verificador para acomodar ZIP truncado.

Corrija o teste/fixture/coordenação da frente LAB, não o APK HTTPS para fazê-lo
ficar inseguro.

## Artefato de referência já produzido

Existe um build separado, sem sobrescrever o APK anterior:

```text
output/mighty-doom-revival-email.apk
sha256 7963ab3543dd129a20fa95957842ab816bafd15ce6ffef91815be5c179d35ad8
650819912 bytes
```

Relatórios ignorados pelo Git:

```text
work/revival-studio/auth-email-20260820/reports/copied-apk-verification.json
work/revival-studio/auth-email-20260820/reports/final-apk-verification.json
```

Medição estática desse artefato:

```text
verified: true
Activity: classes3.dex
Unity Activity preservada: true
host doom.sualoja.app.br: 14 ocorrências
host oficial Gear: 0 ocorrências
cleartext_permitted: false
lab_markers.insecure: false
```

O build passou decode → bundle-aware patch → CRC zerado → Activity → rebuild →
injeção dex → verify pré → assinatura → verificação da assinatura → verify pós.
Entretanto ele foi gerado com `override_lab: true` porque a VPS pública ainda
estava antiga. Portanto é referência estática, **não entrega pública validada**.

## Deploy obrigatório antes do build final

Publique o servidor atualizado em `doom.sualoja.app.br` pelo mecanismo já
existente e autorizado no projeto. Não exponha token/chave no terminal, relatório
ou commit. Antes de seguir, esta chamada precisa medir:

```bash
curl -s https://doom.sualoja.app.br/revival/health
```

Aceitação:

```text
contract_revision >= 2
research_mode == false
instance_id presente
build_id presente e identificando o código realmente publicado
build_dirty != true
```

Se a credencial de deploy não existir no ambiente, não invente nem peça no meio
do trabalho. Termine código, testes, build local, documentação e roteiro
reproduzível; só então reporte esse único bloqueio externo.

Depois do deploy, gere novamente pelo pipeline normal do Studio, com:

```text
revival_auth_requested: true
override_lab: false
base_url_scheme: https
cleartext_permitted: false
```

Não use `--allow-incompatible-server` no entregável. Verifique o arquivo final
copiado para `output/mighty-doom-revival.apk`, não apenas o unsigned ou um arquivo
de `work/`.

## E2E obrigatório no APK real

Use instalação limpa ou preserve credenciais de forma segura conforme a política
de assinatura. Não use ADB para descobrir senha/ID como prova de UX.

### Fluxo principal

1. Instale o APK final assinado.
2. Confirme que a tela Revival aparece antes da Unity.
3. Confirme por UIAutomator que há campo E-mail, campo Senha, domínio, Entrar,
   Esqueci minha senha e Criar conta no site.
4. Confirme que não há Google Play Games na UI/logcat e nenhuma rota Google.
5. Clique em Criar conta e prove que o navegador abre o domínio correto.
6. Crie uma conta real de teste por e-mail/senha no site.
7. Volte ao APK e entre com o mesmo e-mail/senha.
8. Prove `/account/login` 200 e depois `game/auth/login-device` 200/1000.
9. Prove Unity aberta, tráfego aterrissando na instância pública identificada,
   cursor avançando, rotas do boot 200/1000, zero fallback e zero fatal.
10. Reinicie app e servidor quando seguro e prove persistência.

### Recuperação SMTP

1. Sem SMTP: botão retorna `smtp-not-configured`, nenhum fallback e nenhum segredo.
2. Configure SMTP pelo painel (servidor fake isolado para regressão e, se houver
   credencial autorizada, teste público real).
3. Solicite recuperação de conta existente e receba a senha temporária.
4. Prove no SQLite que só há hash scrypt, nunca plaintext.
5. Entre com a temporária, troque para senha permanente e reinicie o APK.
6. Prove que o cliente não fica preso com credencial obsoleta.
7. Prove e-mail inexistente com resposta neutra e zero mensagem enviada.
8. Prove rate limit e revogação quando o SMTP falha.

O harness deve terminar `flow_validated`, com `landing.identified=true`, cursor
antes/depois, build/instance ID, zero assinaturas fatais e zero fallback. Não
classifique apenas 200 do servidor como validação de cliente.

## Testes e gates finais

Execute todos, corrija até ficarem verdes e registre exit code:

```bash
python run_tests.py
cd server && npm test
cd ..
python scripts/generate_endpoint_matrix.py --check
python scripts/verify_everything.py
python scripts/next_task.py --json
git diff --check
python scripts/verify_patched_apk.py --apk output/mighty-doom-revival.apk \
  --server doom.sualoja.app.br \
  --report work/revival-studio/auth-final/reports/final-copy-verification.json
```

Também rode:

- compilação real da Activity (`javac` + `d8`) pelo toolchain pinado;
- `patch_revival_auth.verify_apk()` no APK assinado final;
- varredura de segredos em fixtures, relatórios versionáveis e diffs, sem imprimir
  os valores encontrados;
- `git diff --cached --name-status` antes de cada commit.

Não altere `compatibility.json` à mão. Só sincronize evidência de rota `game/*`
se o harness real produziu fixture client sanitizada e o gate correspondente foi
de fato cumprido. Rotas `/account/*` não contam como novas rotas do APK.

## Commits

Separe commits lógicos e inclua apenas arquivos cuja autoria/integração você
confirmou pelo diff. Sugestão:

```text
fix(auth): login por email com senha scrypt e recuperacao SMTP
fix(apk): fluxo Revival por email sem credencial temporaria obsoleta
test(auth): cobre SMTP, hash, Activity e cleartext isolado
```

Não versione o APK nem os relatórios ignorados. Não inclua os wrappers quebrados.
Ao final, `git diff --cached` precisa estar vazio.

## Relatório final único

Só encerre depois de concluir tudo que o ambiente permitir. Entregue:

1. commits e arquivos incluídos em cada um;
2. saída resumida e exit code de todos os gates;
3. health público medido, build/instance/revisão/research mode;
4. APK final: caminho, bytes, SHA-256, assinatura, Activity/dex, host, cleartext,
   marcador LAB e relatório pós-cópia;
5. E2E principal e de recuperação, com cursor, endpoints, UI e fatais;
6. persistência após restart;
7. varredura de segredos;
8. qualquer pendência restante marcada `A VERIFICAR`, com evidência e comando de
   retomada — nunca escondida sob “pronto”.

Critério de término: o usuário instala o APK, vê o domínio, cria conta no site,
entra no jogo com e-mail/senha, não vê Google Play Games, recupera por senha
temporária somente quando SMTP está configurado e continua entrando após trocar a
senha e reiniciar. Build estático sozinho não satisfaz esse critério.
