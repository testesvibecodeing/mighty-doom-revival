# Opus — retomar agora: HTTP de laboratório autorizado, concluir sem nova pausa

Retome a execução exatamente do estado descrito em
`work/audit-opus/RELATORIO-FINAL.md`. Preserve todo o trabalho já concluído e não
refaça as Fases 0–5. Leia novamente `AGENTS.md`, as quatro skills do projeto e este
documento antes de agir.

## Correção explícita da autorização

O usuário já havia ordenado execução contínua. A cláusula que permitia devolver
`BLOQUEADO` por falta de autorização foi uma falha do handoff anterior.

**Está expressamente autorizado rebaixar `https://` para `http://` somente em um
APK descartável de laboratório, somente para o rig local isolado, com a finalidade
de vencer o bloqueio TLS e concluir os testes dinâmicos.**

Não peça nova autorização para isso. Não devolva outro relatório intermediário.

Esta autorização não vale para o entregável:

- APK de laboratório: HTTP local permitido;
- APK final: HTTPS obrigatório;
- servidor público: HTTPS obrigatório;
- nenhuma credencial pode trafegar pela LAN ou Internet em HTTP.

## Controles obrigatórios do laboratório

1. Use AVD descartável, clone ou snapshot restaurável. Não use `pm clear` no AVD
   primário que contém a conta preservada.
2. O rig HTTP deve ficar acessível somente pelo host/emulador da máquina. Faça bind
   em loopback quando possível e mantenha firewall/DNAT restritos ao experimento.
3. Não grave JWT, token, senha, recovery code ou `device_id` cru. Mantenha a
   sanitização já implementada.
4. O patch `https://` → `http://` deve preservar rigorosamente o comprimento da
   string/metadata. Use preimage, postimage, contagem de bytes e offsets. Não
   realoque `global-metadata.dat` e não faça substituição global cega.
5. Se for necessário padding sintático, prove que a URI resultante resolve para a
   instância local esperada e que path, Host e requests continuam corretos.
6. Adicione uma opção de uso deliberado, por exemplo `--allow-insecure-lab`, que:
   - seja recusada por padrão;
   - exija destino local/privado comprovado;
   - marque relatório e nome do artefato como `LAB_ONLY_INSECURE_HTTP`;
   - nunca seja acionada pelo fluxo normal do Studio;
   - tenha testes de rejeição para host público, ausência da flag e saída em
     `output/mighty-doom-revival.apk`.
7. Grave o APK HTTP apenas dentro de `work/audit-opus/rig/`, com nome inequívoco
   como `mighty-doom-revival-LAB-HTTP.apk`. Ele nunca pode ser copiado para
   `output/`, publicado no site ou tratado como artefato final.
8. Antes de cada instalação, prove SHA-256, host/esquema, assinatura e relatório.
   Depois do teste, restaure DNAT, mounts, APK e snapshot/backup conforme necessário.

## Ordem de execução — não parar entre blocos

### 1. Implementar e testar o modo HTTP de laboratório

Implemente o menor patch possível para o APK de rig, integrado a uma ferramenta
específica de laboratório ou opção explicitamente insegura e opt-in. Não enfraqueça
o verificador do APK final. O verificador normal deve continuar exigindo HTTPS;
somente o modo de laboratório pode aceitar HTTP e deve emitir o marcador de risco.

Exija testes para:

- preservação byte a byte do comprimento;
- preimage única e postimage esperada;
- rejeição sem `--allow-insecure-lab`;
- rejeição de destino público/não isolado;
- separação absoluta entre artefato de rig e artefato final;
- idempotência ou falha segura na segunda execução;
- zero ocorrência do endpoint oficial e esquema/host esperados no APK de rig.

Construa, assine e verifique o APK de laboratório. Instale-o apenas no AVD
descartável/snapshot autorizado.

### 2. Reabrir a prova dinâmica imediatamente

Suba o servidor de rig em porta separada usando cópia consistente do banco. Arme
somente o roteamento necessário e prove a aterrissagem por:

```text
SHA-256 e esquema/host do APK instalado
build/instance ID do servidor do rig
cursor antes/depois
janela do logcat
request/response pareados
fallback delta
```

Execute o restart preservando as credenciais. O critério mínimo é:

```text
game/auth/login-device -> code 1000
game/player/game-data-token
game/player/user-data
sem String -> String[]
sem Failed to launch
sem NETWORK ERROR
landing identified=true e cursor avançando na janela
```

Crie a fixture client sanitizada de `login-device` apenas se o par real estiver
completo. Atualize o registro pelo gerador, nunca à mão.

### 3. Revalidar battle pass no cliente

Na mesma instância comprovada, execute o estado que gera:

```text
game/battle-pass/end-season -> code 1000
game/battle-pass/start-season -> code 1000, nunca 2300
```

Se a correção ainda falhar, faça bisseção do estado persistido e compare o contrato
extraído antes de alterar o código. Corrija, teste no servidor e repita no cliente.
Não pare no primeiro erro. Só marque `client_validated` com request/response
pareados e ausência de fatal.

Com a nova evidência de restart, reavalie honestamente
`research/DEAD-ENDS.md #9` e mantenha separados fato e hipótese.

### 4. Finalizar a RevivalAuthActivity e o Manifest

O bloqueio TLS deixou de existir no rig. Portanto, a justificativa anterior para
não construir a Activity não vale mais.

Use o núcleo já provado em `scripts/revival_auth/` e finalize:

- `RevivalAuthActivity` como único `MAIN/LAUNCHER`;
- preservação de `MessagingUnityPlayerActivity`, deep links e extras;
- tela `Criar conta | Entrar`;
- validação de campos, timeout, prevenção de clique duplo e erros úteis;
- escrita atômica no armazenamento privado do mesmo package;
- round-trip real de `gpg.config` e `credentials.json`;
- credenciais válidas abrem diretamente a Activity Unity;
- ausência/corrupção de credenciais volta de forma segura à tela Revival;
- nenhum segredo em log, intent, arquivo público ou relatório.

Não use a ausência de JDK compilador como motivo para parar. Faça, nesta ordem:

1. procure `javac`, `d8` e Android SDK já instalados fora do PATH;
2. use toolchain Android já presente e registre versão/SHA;
3. se não existir compilador utilizável, implemente a Activity em smali pelo
   Apktool 3.0.3 já pinado, com testes estruturais e E2E;
4. não baixe/atualize ferramenta aleatória para “ver se funciona”.

Escolha automaticamente entre Java/d8 e smali com base na disponibilidade real.
Não peça decisão arquitetural.

### 5. Suprimir o popup Google Play Games

Use a decompilação dirigida e a evidência dinâmica agora disponível. Prove a
condição que abre o popup, o efeito de Cancel e os estados
`hasCancelledLogin`/`hasLoggedOut`.

Aplique o menor mecanismo comprovado, nesta ordem:

1. `gpg.config` gerado pela Activity com `hasCancelledLogin=True`, se o cliente o
   honrar de ponta a ponta;
2. configuração/asset existente;
3. patch ARM64 mínimo com preimage, offset, bytes esperados e regressão.

Não remova bibliotecas Google em massa. Não use seeding ADB como solução final.
Depois do patch, prove no logcat e no request log:

```text
popup Google não aparece
rotas Google auth/link não são chamadas
Activity Revival cria/entra na conta
Unity usa login-device no restart
```

### 6. Integrar tudo ao framework Python

Integre Activity, Manifest, credenciais e supressão Google ao pipeline real do
Studio. Exija:

- etapas com precondição/pós-condição e relatório;
- falha segura sem deixar APK parcialmente promovido;
- segunda execução idempotente;
- testes unitários e integrados;
- diferenciação explícita entre build `LAB_ONLY_INSECURE_HTTP` e build final;
- `zero_catalog_crc` se qualquer bundle mudar;
- Java/toolchain conforme `AGENTS.md` e skills;
- assinatura seguida de verificação do APK realmente assinado.

### 7. E2E completo no laboratório

Em instalação descartável, execute até passar:

```text
primeiro boot sem Google configurado
RevivalAuthActivity aparece
Criar conta funciona
Unity chega a authentication + user-data
restart chama login-device e preserva a mesma conta
Entrar funciona numa instalação limpa
popup Google não aparece
rotas Google auth/link não aparecem
battle pass não devolve 2300
menu/jogo não tem CRC, fatal ou fallback inesperado
```

Falha corrigível implica diagnosticar, corrigir e repetir — não implica devolver o
controle.

### 8. Produzir separadamente o APK final HTTPS

Depois do E2E de laboratório, gere novamente a partir de fonte/entrada limpa o APK
entregável com:

```text
https://doom.sualoja.app.br
RevivalAuthActivity integrada
supressão Google integrada
nenhum marcador ou permissão LAB_ONLY_INSECURE_HTTP
nenhum downgrade cleartext
```

Assine e execute `verify_patched_apk.py` **depois da assinatura**. Acrescente uma
verificação negativa que reprove o entregável se encontrar base URL HTTP, flag de
laboratório ou artefato de CA/rig não solicitado.

Não declare E2E público se o VPS antigo impedir a prova. Nesse caso, declare
separadamente:

- E2E funcional completo: comprovado no rig isolado;
- artefato final HTTPS: construído e verificado estaticamente;
- validação contra VPS público: pendente exclusivamente de credencial/deploy,
  sem reduzir o status das duas provas anteriores.

Essa limitação externa não autoriza abandonar Activity, Manifest, popup Google ou
APK final.

## Gates finais obrigatórios

Rode, corrija e repita:

```bash
python run_tests.py
cd server && npm test
cd ..
python scripts/generate_endpoint_matrix.py
python scripts/generate_endpoint_matrix.py --check
python scripts/verify_everything.py
python scripts/verify_patched_apk.py --apk <apk-final-https-assinado> --server doom.sualoja.app.br
git diff --check
git status --short
git diff --cached
```

Além disso, rode o harness completo no rig com `--strict-research` ou equivalente
contra uma instância `RESEARCH_MODE=false`. É permitido alterar o runtime **da
instância descartável do rig** para isso; não altere silenciosamente o servidor
primário ou o VPS.

## Única resposta permitida

Não responda com “autorização necessária”: ela foi concedida acima.
Não responda após implementar apenas o modo HTTP.
Não responda após validar apenas o restart.
Não responda após escolher a arquitetura.
Não responda após construir apenas a Activity.

Continue até entregar, em uma única resposta final:

- E2E de laboratório completo;
- Activity + Manifest integrados;
- login/register e persistência comprovados;
- popup e rotas Google ausentes;
- battle pass revalidado ou uma falha de contrato nova, corrigida e retestada;
- APK final HTTPS assinado e verificado;
- gates verdes;
- evidências sanitizadas;
- estado restaurado do AVD/rig;
- `git diff --cached` vazio e nenhum material proprietário versionado.

Se surgir um obstáculo novo, procure e execute alternativas seguras antes de
considerá-lo terminal. A autorização HTTP de laboratório remove o bloqueio atual.

