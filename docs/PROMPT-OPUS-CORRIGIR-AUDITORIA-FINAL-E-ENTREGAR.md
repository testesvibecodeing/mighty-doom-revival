# PROMPT PARA O OPUS — CORRIGIR A AUDITORIA FINAL E ENTREGAR SEM PAUSAS

Trabalhe diretamente no repositório `D:\DevPrograms\mighty-doom-revival` e leia
integralmente `AGENTS.md`, `research/DEAD-ENDS.md` e as skills aplicáveis antes de
editar: `apk-patch`, `revival-server`, `boot-diagnostics` e, quando precisar do
contrato do cliente, `il2cpp-recon`.

Você não está começando uma nova auditoria por fases. Execute todo o trabalho local
abaixo de forma contínua, da correção até a prova no cliente. Não pare para pedir
liberação entre itens, não entregue inventário intermediário e não considere
`verify_patched_apk.py` ou testes unitários substitutos de E2E funcional. Continue
pelas frentes independentes quando alguma etapa demorar. Só interrompa uma ação
externa destrutiva ou um deploy se realmente faltar autorização/credencial; isso
não autoriza abandonar as correções e provas locais restantes.

O Codex permanece como auditor. Não declare `PRONTO`, `CONCLUÍDO` ou equivalente
antes de cumprir todos os critérios de aceite deste documento e apresentar as
evidências finais para nova auditoria.

## Veredito e linha de base já medidos pelo auditor

O APK abaixo existe e passa na verificação **estática**, mas a entrega funcional
ainda está **REPROVADA**:

- `output/mighty-doom-revival.apk`
- SHA-256 `ce4b98216634e7e29b7e8c30f8ca41e608bab330fa55453da91c2a7d708316bf`
- 650.815.816 bytes
- host `doom.sualoja.app.br`: 14 ocorrências; host oficial: 0
- `RevivalAuthActivity` é o único `MAIN/LAUNCHER`; Unity e deep link foram
  preservados; assinatura v3 passa
- o `network_security_config.xml` decodificado tem
  `cleartextTrafficPermitted="false"`

Isso só prova composição, endpoint e assinatura do APK. Não prova que o APK novo
entra no jogo contra o servidor público, que o fluxo de conta é recuperável, nem
que o framework Python normal gera esse mesmo resultado.

Fatos impeditivos medidos no estado atual:

1. O build foi disparado por `work/audit-opus/rig/build_final_vps.py`, chamando
   manualmente `apply_endpoint(..., revival_auth=True)`. Em
   `scripts/revival_editor/pipeline.py`, o default ainda é `False`, e a chamada
   normal do Studio em `scripts/revival_editor/ui/app.py` não envia
   `revival_auth`. Logo, o botão normal **Aplicar endpoint** ainda gera APK sem a
   Activity. Também não existe
   `work/revival-studio/vps-final/reports/pipeline.json` para esse build.
2. O próprio preflight do build aceitou uma VPS incompatível. Em 2026-08-20, o
   `GET https://doom.sualoja.app.br/revival/health` ainda não retorna
   `instance_id`, `build_id` ou revisão de contrato e expõe
   `research_mode: true`. O build foi publicado mesmo assim, embora a mensagem
   final reconheça que o servidor antigo reproduz payloads inválidos.
3. Nenhuma evidência E2E referencia o SHA-256 novo. Esse hash só aparece em
   relatórios de verificação estática. Não afirme que este APK foi validado no
   cliente.
4. Os E2E anteriores contêm repetidamente uma exceção Unity real que o harness
   deixou passar como sucesso:

   ```text
   ArgumentException: Invalid value '1787260506000' for parameter 'interval'.
   at System.Timers.Timer..ctor
   at Ubu.IdleRewards.IdleRewardsController.UpdateNextClaimEpoch
   at Ubu.IdleRewards.IdleRewardsController.SetIdleRewardState
   ```

   Evidências preservadas, entre outras:
   `work/audit-opus/rig/e2e-final.json/logcat-20260820-210357.txt:1263` e
   `work/audit-opus/rig/e2e-strict.json/logcat-20260820-211359.txt:1339`.
   `server/src/rewards.js` envia `next_claim` como epoch absoluto, e o cliente o
   transforma em intervalo inválido. O contrato exato ainda precisa ser medido;
   não chute a correção.
5. O cadastro salva a senha gerada, porém a Activity mostra somente ID e código
   de recuperação por seis segundos e abre o jogo automaticamente. A tela de
   login exige ID + senha. Após desinstalação ou perda de dados, o usuário comum
   não tem como recuperar a senha sem ADB/extração de arquivo.
6. `server/src/index.js` inclui `device_id` em `SECRET_LOG_KEYS` e troca qualquer
   valor truthy por `"<device_id>"`. Isso corrompe o tipo numérico legítimo de
   `game/devices/*` no request log e nas fixtures derivadas.
7. `scripts/patch_lab_http.py` altera bundles Addressables, mas não zera nem prova
   o `m_Crc` correspondente. O teste anterior só funcionou por herdar um catálogo
   já zerado.
8. `scripts/verify_patched_apk.py` inicializa
   `cleartext_permitted: false`, mas nunca decodifica o AXML nem muda esse campo.
   Portanto, hoje o relatório pode afirmar `false` sem ter verificado o atributo.
9. `server/src/instance.js` pode publicar apenas o `git rev-parse HEAD` mesmo com
   código executado sujo/não commitado. Nesse caso o `build_id` não identifica os
   bytes em execução.
10. `stripNulls()` remove globalmente todos os `null` de objetos. A regra do
    projeto proíbe `null` em campos numéricos não-nullable; ela não prova que todo
    campo referencial nullable de todos os 116 contratos deva ser removido.
11. O estado Git contradiz a mensagem enviada: estes quatro arquivos estão
    atualmente no índice como adicionados, embora tenham sido descritos como
    excluídos e quebrados:
    `server/setup-server.bat`, `server/setup-server.sh`,
    `server/start-server.bat`, `server/start-server.sh`.

## Trabalho obrigatório — execute tudo

### 1. Sanear o estado Git antes de qualquer novo commit

- Registre `git status -sb`, `git diff --cached --name-status` e o HEAD atual.
- Retire do índice, sem apagar o conteúdo local, os quatro wrappers quebrados.
  Eles não podem entrar por acidente em nenhum commit. Não use `git add .`.
- Preserve alterações do usuário e materiais ignorados. Nunca versione APK,
  logcat, screenshot, certificado, keystore, fixture com segredo ou conteúdo de
  `work/`.
- Faça as correções em novos commits lógicos; não reescreva os quatro commits já
  existentes e não faça push sem autorização externa explícita.

### 2. Fazer a autenticação Revival funcionar pelo Studio real

- Modele `revival_auth` no estado/projeto do Studio e persista a escolha.
- Exponha uma opção clara na UI, marcada por padrão para o build Revival, e faça
  a chamada normal de **Aplicar endpoint** repassar o valor ao pipeline.
- O relatório normal `reports/pipeline.json` deve registrar a opção solicitada e
  o resultado do passo `auth`, incluindo classe, dex, launcher único, preservação
  da Unity/deep link, esquema HTTPS e `verified=true`.
- Adicione regressão de integração que passa pelo mesmo job usado pela UI e falha
  se o parâmetro se perder. Testar apenas `apply_endpoint(...,
  revival_auth=True)` diretamente não basta.
- Gere o APK final pelo fluxo normal do Studio, a partir de input limpo. O script
  auxiliar em `work/audit-opus/rig/` não conta como prova desta correção e não pode
  ser necessário para o produto.

### 3. Impedir build “verde” contra servidor público incompatível

- Acrescente ao health público uma revisão/capability de contrato publicável e
  não secreta, além da identidade de instância/build.
- Faça o preflight do pipeline final exigir a revisão mínima necessária às
  correções do wire e rejeitar host legado, identidade ausente, build
  incompatível ou `research_mode: true` em ambiente de produção.
- O preflight deve falhar **antes de publicar o APK**, com mensagem acionável.
  Pode haver override explicitamente nomeado para laboratório, nunca silencioso
  e nunca default.
- Adicione testes para: servidor compatível, health antigo sem identidade,
  revisão insuficiente, research mode ligado e identidade/build divergente.
- Não invente endpoint `game/*`; esta identidade pertence ao namespace Revival.

### 4. Corrigir idle rewards pelo contrato real e fechar o falso positivo

- Primeiro classifique a exceção `Invalid value ... for parameter 'interval'`
  com stack de `IdleRewardsController.UpdateNextClaimEpoch` como fatal e early
  stop no `client_harness.py`, com testes. Um E2E contendo-a deve retornar exit
  diferente de zero.
- Extraia o DTO/semântica com `il2cpp-recon` e/ou faça bisseção controlada no rig
  para determinar o significado e a unidade reais de `next_claim`. Registre
  comando, entrada e evidência. Não troque epoch por duração apenas por intuição.
- Corrija o servidor e seus testes/fixtures sem fabricar campo.
- Prove em boot limpo e restart que não aparece `ArgumentException`,
  `System.Timers.Timer..ctor` nem qualquer assinatura fatal conhecida.
- Não marque a rota como validada antes dessa prova no cliente.

### 5. Tornar cadastro/login utilizáveis sem ADB

- Após o cadastro, mostre ao usuário **ID, senha gerada e código de recuperação**
  em tela selecionável/copiável.
- Remova o auto-dismiss de seis segundos. Só abra a Unity após ação explícita do
  usuário confirmando que guardou os dados.
- Implemente recuperação/reset de senha usando contrato medido ou, se o servidor
  clean-room ainda não tiver esse contrato, forneça dentro do namespace Revival
  um fluxo de recuperação próprio, documentado e testado. Não invente rota
  `game/*`.
- Nunca escreva senha/token/recovery em logcat, relatório, fixture ou Git.
- E2E obrigatório: criar conta pela UI; guardar apenas o que a UI exibiu; abrir o
  jogo; reiniciar; limpar/desinstalar/reinstalar no ambiente de teste; autenticar
  novamente usando somente os dados que um jogador conseguiria ter copiado da
  tela. É proibido usar ADB para ler `credentials.json` como atalho da prova.

### 6. Corrigir os sanitizers sem alterar tipos do wire

- Torne a sanitização do request log sensível ao tipo/contexto:
  `device_id` string de autenticação deve ser redigido; `device_id` numérico de
  `game/devices/*` deve continuar número.
- Adicione teste ponta a ponta do request log até a fixture sanitizada, provando
  que o inteiro preserva o tipo e que UUID/senha/token/puuid continuam redigidos.
- Rode a varredura de segredos sem imprimir os valores encontrados.

### 7. Fechar CRC e verificação real de cleartext

- Toda alteração de bundle em `patch_lab_http.py` deve chamar a rotina canônica
  `zero_catalog_crc()` ou provar, por pós-condição equivalente e testada, que o
  CRC da entrada correspondente do catálogo está zero.
- Adicione regressão com catálogo sintético começando em CRC não zero.
- Faça `verify_patched_apk.py` decodificar/inspecionar de verdade o AXML do
  Manifest/network security config. Reutilize parser existente se houver.
- Adicione APKs/fixtures sintéticos mínimos que provem:
  `cleartextTrafficPermitted=true` reprova entregável; `false` passa; erro de
  parse é inconclusivo/falha segura, nunca `false` inventado.

### 8. Tornar a identidade do build honesta

- `build_id` precisa identificar o código realmente executado. Inclua estado
  dirty e/ou hash de conteúdo, ou exija `REVIVAL_BUILD_ID`/`BUILD_ID` escrito pelo
  deploy e recuse produção sem ele.
- Health não pode afirmar que um commit limpo representa arquivos locais
  diferentes daquele commit.
- Teste checkout limpo, checkout dirty, arquivo/env de deploy e ausência de
  identidade.

### 9. Auditar e estreitar `stripNulls()`

- Extraia os contratos afetados e separe campos numéricos não-nullable de campos
  referenciais realmente nullable.
- Prefira construir DTOs corretos na origem. Não use uma limpeza global para
  esconder desconhecimento de contrato.
- Preserve `null` quando o DTO real o admitir e omita apenas onde o contrato
  exigir. Adicione testes das rotas afetadas e evidência de cliente quando forem
  parte do boot.
- Se algum campo continuar `A VERIFICAR`, não o promova a confirmado e não infle
  `compatibility.json`.

### 10. Provar ausência do Google Play Games e o APK final

- Gere pelo Studio corrigido um novo APK HTTPS final, assine e rode
  `verify_patched_apk.py` **depois** da assinatura.
- Registre SHA-256, tamanho, relatório do pipeline e relatório final de
  verificação. Todos devem referir exatamente os mesmos bytes.
- No emulador, capture `uiautomator dump`/estado da Activity e logcat durante uma
  janela suficiente para provar que o popup “Use Google Play Games?” não aparece
  e que `RevivalAuthActivity` é a tela inicial quando não há credenciais.
- Faça boot, criação de conta, chegada ao menu, restart e novo login. Correlacione
  hash do APK instalado, identidade/build do servidor, cursor antes/depois,
  requests e logcat.
- O APK público final só pode ser chamado de validado contra a VPS depois de o
  servidor compatível estar implantado e identificado. Enquanto não houver
  autorização/credencial para deploy, chame-o honestamente de “artefato estático
  pronto para E2E público”, não de solução concluída.
- Documente a política de assinatura: o build atual usa o debug keystore Android.
  Deixe explícito o impacto em atualização/reinstalação e não o chame de chave de
  produção.

## Gates obrigatórios de aceite

Execute no fim, preservando as saídas completas em `work/`:

```powershell
python run_tests.py
Push-Location server; npm test; Pop-Location
python scripts/generate_endpoint_matrix.py --check
python scripts/verify_everything.py
python scripts/next_task.py --json
git diff --check
git status -sb
git diff --cached --name-status
```

Além disso, são obrigatórias estas provas:

1. O gate Python autodescobre toda suíte nova; zero falhas.
2. Todos os testes Node passam; zero falhas.
3. `git diff --cached` termina vazio após os commits, e os quatro wrappers não
   aparecem em commit novo.
4. O build pelo job normal do Studio contém o passo auth no `pipeline.json` e o
   relatório referencia o SHA final correto.
5. O preflight reprova o health público antigo atualmente observado.
6. O verifier reprova amostra AXML com cleartext verdadeiro.
7. O patch HTTP de laboratório prova CRC zerado a partir de CRC inicialmente não
   zero.
8. O harness reprova a exceção de idle rewards e o E2E final não a contém.
9. O fluxo de conta completo funciona sem extração de credenciais por ADB.
10. O E2E final tem zero assinatura fatal, prova tráfego na instância esperada e
    prova visual/estrutural de que o popup do Google Play Games não apareceu.
11. `compatibility.json` e `docs/ENDPOINT-MATRIX.md` só mudam por evidência real e
    continuam sincronizados.
12. A varredura final encontra zero segredo/material proprietário versionado,
    sem imprimir valores sensíveis.

## Formato da única entrega final

Não envie relatórios por fase. Ao terminar tudo que independe de autorização
externa, responda uma única vez com:

- veredito `PRONTO PARA AUDITORIA` ou `BLOQUEADO`, nunca “pronto” parcial;
- novos commits e arquivos alterados;
- estado final de staging e dos quatro wrappers;
- tabela de todos os gates com comando, exit code e resultado;
- SHA-256 do APK final e caminhos dos relatórios que provam os mesmos bytes;
- prova do job real do Studio e da verificação pós-assinatura;
- prova E2E completa, incluindo idle rewards, cadastro, reinstalação/login,
  ausência do popup Google e aterrissagem na instância correta;
- health público com identidade/revisão, caso o deploy tenha sido autorizado e
  realizado;
- lista curta de pendências genuínas, separando `CONFIRMADO` de `A VERIFICAR`.

Qualquer bloqueio final deve incluir o comando exato de retomada, mas a existência
de um bloqueio externo não permite deixar correções ou testes locais desta lista
sem executar.
