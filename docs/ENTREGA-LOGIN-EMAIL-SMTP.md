# Entrega: login por e-mail, SMTP e o dead-end da credencial obsoleta

Estado em **2026-08-21**. Separa `CONFIRMADO` (medido nesta execução, com o
comando que mediu) de `A VERIFICAR` (hipótese ou pendência).

---

## O que ficou pronto

### Login do jogador — CONFIRMADO

A tela do APK pede **e-mail e senha**, mostra o domínio Revival, abre
`/account?mode=register` no navegador e autentica em `/account/login`. O
response devolve só identidade pública (`account.id`, `account.uuid`); a senha
nunca volta. A Activity monta o `credentials.json` do `Ubu.CredentialStore` com
esse id, esse uuid e a senha digitada. O fluxo antigo por `game/auth/register`
e a tela "GUARDE ESTES DADOS" foram removidos.

Medido no emulador com o APK real (dump do UIAutomator):

```text
'MIGHTY DOOM REVIVAL' · 'Servidor: 10.0.2.2' · 'Campo E-mail' · 'Campo Senha'
'ENTRAR' · 'ESQUECI MINHA SENHA' · 'CRIAR CONTA NO SITE'
```

Nenhum campo de ID numérico, nenhuma menção a Google Play Games na tela nem no
logcat do processo do jogo.

### Armazenamento de senha — CONFIRMADO

`scrypt` com salt individual, comparação com `timingSafeEqual`. Hash SHA-256
legado ainda autentica uma vez e é convertido para scrypt no primeiro login
válido. A senha temporária também vive só como hash, na tabela
`password_resets`.

Varredura dos bytes do banco **e do WAL** atrás das quatro senhas usadas na
rodada (permanente, definitiva, do admin e a temporária): zero ocorrências.

O `credentials.json` contém a senha porque **esse é o contrato real do
`Ubu.CredentialStore`** — não há criptografia inventada ali, que a Unity não
saberia decifrar. Ele fica só no diretório privado do app e nunca é logado,
enviado por Intent/Toast nem incluído em evidência.

### Recuperação exclusivamente por SMTP — CONFIRMADO

| Regra | Medição |
|---|---|
| Sem SMTP: 503 `smtp-not-configured`, sem fallback | tela do APK: "Recuperação por e-mail desativada: o administrador deste servidor não configurou o SMTP." |
| E-mail inexistente: 200 neutro, zero e-mails | `temporary_password_sent: true`, `captured.jsonl` nem chegou a existir |
| Temporária forte, 30 min | `RV-` + 12 caracteres base64url, `expires_in_seconds: 1800` |
| Mínimo de 60s entre pedidos | segundo pedido → 429 `reset-rate-limited` |
| Máximo de tentativas | 5 por reset (`password_resets.attempts`) |
| Falha de envio revoga a temporária | SMTP derrubado → 502 `mail-send-failed`, `used_at` preenchido, senha atual segue valendo |
| Pedir recuperação não derruba a senha antiga | login com a senha anterior → 200 depois do pedido |
| Primeiro login válido promove a temporária | temporária → 200 e `temporary_password_used: true`; sessões web anteriores encerradas; resets pendentes marcados |
| Rotas antigas respondem 410 | `email-code/request`, `email-code/login`, `reset-password` |
| Senha do SMTP nunca volta na API | painel devolve `has_pass`, nunca `pass`; campo vazio preserva a salva |

**TLS do SMTP:** o certificado passou a ser validado por padrão. Antes,
`rejectUnauthorized: false` estava fixo nas duas conexões (`secure` e
`STARTTLS`) — o servidor aceitava em silêncio o certificado de um interceptador,
que veria a senha de aplicativo do `AUTH LOGIN`. O escape existe
(`allow_invalid_cert`), mas só ligado de propósito, e o painel mostra o aviso.
`AUTH LOGIN` em texto claro só sai para loopback ou com `allow_plaintext_auth`
explícito, porque base64 é codificação e não cifra. As mensagens de erro deixaram
de ecoar o comando enviado — a linha de AUTH **é** a senha em base64, e o erro
terminava em `console.warn`.

### Credencial temporária obsoleta — CONFIRMADO, com duas travas

O `credentials.json` guarda a **senha**, e a senha pode mudar no site depois de
o arquivo ter sido escrito. Sem verificação, o boot seguinte pularia a tela
Revival, entregaria o arquivo para a Unity e o `login-device` bateria 403/2101
sem caminho de volta.

1. **Preflight no boot.** A Activity chama ela mesma
   `game/auth/login-device` com o que está gravado, **antes** de abrir a Unity —
   a mesma rota que o cliente usaria, nada inventado.
   - `code 1000` → abre a Unity;
   - `403/2101` → apaga o `credentials.json` e volta ao login com a razão na
     tela;
   - falha de rede → **não** acusa credencial ruim sem ter medido: mantém o
     arquivo e oferece "TENTAR NOVAMENTE".
2. **Senha temporária nunca é persistida.** Gravar no arquivo uma senha que
   expira em 30 minutos seria fabricar o mesmo dead-end de propósito. Quando
   `/account/login` responde `temporary_password_used`, a Activity exige a senha
   definitiva na hora (`/account/password` com o cookie da sessão) e só então
   grava a credencial e abre o jogo.

Sequência medida no emulador, com o APK instalado:

```text
trocar a senha pelo site  -> reiniciar o app
  POST /collections/doom/game/auth/login-device -> 403      (preflight)
  credentials.json: No such file or directory               (apagado)
  tela: "Sua senha mudou desde o último acesso neste aparelho."
entrar com a senha nova   -> Unity abre, boot inteiro 200/1000
```

### Painel administrativo SMTP — CONFIRMADO

Host, porta, TLS/SSL, usuário, senha de aplicativo, remetente e nome do
remetente; selo `configurado/não configurado` sem revelar segredo; texto
explicando que o SMTP habilita **somente** a recuperação por senha temporária e
que o login normal funciona sem ele; interruptor de certificado inválido com o
aviso do que custa.

---

## Bloqueio externo: deploy do servidor público

**A VERIFICAR — depende de credencial que não existe neste ambiente.**

O mecanismo de deploy do projeto é `git pull` + `sudo bash scripts/install.sh`
**executado na VPS**. Esta máquina não tem chave SSH (`~/.ssh` só tem
`known_hosts`), nem variável de ambiente de deploy, e `main` está à frente de
`origin/main`. Não há como publicar daqui.

Estado público medido:

```bash
curl -s https://doom.sualoja.app.br/revival/health
```

```text
contract_revision : ausente      (exigido >= 2)
research_mode     : true         (exigido false)
instance_id       : ausente
build_id          : ausente
```

O gate de prontidão do pipeline recusa esse servidor, como deve:

```text
health sem identidade de instancia/build (servidor anterior a server/src/instance.js)
health sem contract_revision
research_mode ligado: rota desconhecida responde sucesso vazio
```

Por isso **o entregável HTTPS novo não foi gerado**: produzi-lo exigiria
`--allow-incompatible-server`, que o próprio contrato desta entrega proíbe, e
resultaria num APK apontando para um servidor que não sabe atendê-lo.

`output/mighty-doom-revival.apk` continua sendo o build **anterior** — ele tem a
Activity Revival, mas **sem** o preflight e **sem** a tela de senha obrigatória.

### Roteiro para retomar, depois do deploy

```bash
# 1. na VPS
git pull && sudo bash scripts/install.sh

# 2. aqui: o health tem que passar antes de qualquer build
curl -s https://doom.sualoja.app.br/revival/health
python - <<'PY'
import sys; sys.path.insert(0, "scripts")
from revival_editor.pipeline import _prontidao_do_servidor
print(_prontidao_do_servidor("doom.sualoja.app.br", insecure_lab=False))
PY
# exigido: ready=True

# 3. build pelo pipeline normal do Studio
#    revival_auth_requested=true, override_lab=false,
#    base_url_scheme=https, cleartext_permitted=false, SEM --allow-incompatible-server

# 4. verificação do arquivo COPIADO para output/, não do unsigned
python scripts/verify_patched_apk.py --apk output/mighty-doom-revival.apk \
  --server doom.sualoja.app.br \
  --report work/revival-studio/auth-final/reports/final-copy-verification.json
python - <<'PY'
import sys, json; sys.path.insert(0, "scripts")
from patch_revival_auth import verify_apk
print(json.dumps(verify_apk("output/mighty-doom-revival.apk"), ensure_ascii=False))
PY
```

---

## Pendência de contrato, de outra frente

**A VERIFICAR — `game/quests/get-daily-quests` derruba o parse do cliente.**

Medido nesta rodada, no emulador, com o servidor rodando o código atual:

```text
E Unity : Network response (17):
E Unity : Malformed response payload
E Unity : Ubu.<SendRequestAsync>d__18:MoveNext()
```

A resposta já está recortada para o contrato extraído do metadata v29
(`GetDailyQuestsResponse { dayStartEpoch, dayEndEpoch, milestones, quests }`,
`DailyQuestModel { id, questId, progress, claimed, points, goTo }`,
`DailyQuestMilestoneModel { id, milestoneId, pointsRequired, claimed, rewards }`)
e não tem **nenhum** `null` nem tipo fora do lugar — conferido campo a campo nos
38 quests e 50 milestones. O `dailyQuestWire()` que faz esse recorte é de outra
frente, que trabalhou o arquivo durante esta rodada; o sintoma persiste depois
dele.

O erro **não** derruba o boot: a Unity abre, o menu carrega e o
`session/heartbeat` continua de minuto em minuto. As outras 17 rotas do boot
respondem 200/1000, sem fallback.

Payload exato salvo em `work/e2e-opus-20260821/reports/quests-response.json`
(ignorado pelo Git). O próximo passo é resolver o DTO do item de reward, que o
`dump_il2cpp_metadata.py` ainda devolve como `type: unresolved` — o binding
depende da tabela `il2CppType` do `libil2cpp.so`, não só do metadata.

Retomada:

```bash
python scripts/dump_il2cpp_metadata.py \
  --metadata work/apk-patch/decoded/assets/bin/Data/Managed/Metadata/global-metadata.dat \
  --dtos --pattern reward
```

---

## Nota de método: `network_security_config` no artefato de laboratório

O teste `tests/test_verify_cleartext.py` lia dois APKs por caminho fixo em
`work/` e `output/`. Os dois são artefatos compartilhados e não versionados:
quando o rig regerava um com outro nome, o teste passava a medir uma geração
antiga (foi o que aconteceu — o arquivo daquele caminho era anterior ao patch de
NSC e media `false`), e quando o rig estava gravando, o ZIP vinha truncado
(`BadZipFile`). Agora o teste constrói o par HTTPS/laboratório em diretório
temporário próprio, e medir artefato real virou opt-in por variável de ambiente
(`REVIVAL_VERIFY_APK`, `REVIVAL_LAB_APK`).

O verificador do entregável também passou a **falhar fechado**: um `res/xml/*`
que não abre entra em `cleartext_unreadable` e o gate recusa o APK (exit 7), em
vez de aprovar sem ter lido a política de rede.
