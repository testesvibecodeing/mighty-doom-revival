# Revival Studio — guia do usuário

O Revival Studio é o editor desktop (Python + Tkinter, sem dependências
extras de GUI) que reúne em uma janela o fluxo completo de preparação do
cliente Mighty DOOM 1.13.1 para o servidor Revival: análise, patch,
visuais, branding, catálogo de assets e o registro de compatibilidade.

Este documento cobre **uso**. O desenho interno e as regras de segurança
estão em [`docs/PLANO-REVIVAL-STUDIO-100-POR-CENTO.md`](PLANO-REVIVAL-STUDIO-100-POR-CENTO.md)
e no código em `scripts/revival_editor/`.

## Antes de abrir

- Python 3.11 ou superior no `PATH` (Tkinter incluso).
- Uma cópia local sua do APK 1.13.1 (`input/mighty-doom.apk`). O Studio
  **nunca altera o APK de entrada** — todo resultado é um arquivo novo.
- Opcional: `adb` no `PATH` (aba/serviços de dispositivo).

Nada é baixado em silêncio: as ferramentas externas (Apktool, assinador)
são baixadas apenas quando você clica em **Preparar ferramentas**, com
hashes pinados e log completo.

## Abrir o Studio

Windows:

```bat
scripts\revival-studio.bat
```

Linux/macOS:

```bash
./scripts/revival-studio.sh
```

Execução direta por Python (caminho documentado e suportado — o empacotamento
com PyInstaller é opcional e não é pré-requisito):

```bash
python scripts/revival_studio.py
```

## Primeira execução

1. **Ferramentas → Verificar ferramentas** — mostra caminho e versão de cada
   ferramenta e o que falta.
2. **Ferramentas → Preparar ferramentas** — baixa Apktool e o assinador com
   hashes pinados (você confirma antes; nada é instalado fora do projeto).
3. **Projeto → Novo projeto** — escolha o APK de entrada e o hostname do
   servidor Revival (ex.: o host do seu VPS com HTTPS).

## Pipeline do projeto

O estado do projeto avança por etapas; uma etapa só habilita a seguinte e
mudanças de host/CA/APK invalidam as etapas de build (nada fica "velho"
sem aviso):

`VAZIO → APK_ANALISADO → SERVIDOR_VALIDADO → WORKSPACE_PREPARADO →
PATCH_APLICADO → CUSTOMIZACOES_APLICADAS → APK_RECONSTRUIDO →
APK_ASSINADO → APK_VERIFICADO → INSTALADO → CLIENTE_VALIDADO`

Menu **APK**:

- **Analisar APK** (menu Projeto): SHA-256, Unity/IL2CPP, hosts encontrados.
- **Precheck de hostname**: orçamento de bytes antes de qualquer patch.
- **Aplicar endpoint (decode → patch → build → sign → verify)**: o caminho
  completo com verificação obrigatória após a assinatura.
- **Importar base APK de um .xapk**: extrai a base de um XAPK válido.

Menu **Servidor**:

- **Validar servidor**: preflight HTTPS (`/revival/health` + `uts` do
  envelope vivo). Exige o servidor rodando com certificado válido.
- **Preparar servidor local**: o fluxo do `setup-server` como serviço —
  valida Node.js + `node:sqlite`, cria `server/.env` e `config/*.json` a
  partir dos `*.example` **somente quando faltam** (configs existentes
  nunca são sobrescritos), roda `node --check` nos módulos e o smoke test
  end-to-end.
- **Iniciar servidor local**: sobe o servidor em segundo plano (PID e log
  em `work/revival-studio/server/`) e espera o `/revival/health` ficar
  verde. Idempotente: se já está ativo, não cria segundo processo.
- **Encerrar servidor local**: termina o processo registrado (com
  confirmação). Recusa-se a matar servidor iniciado fora do Studio.
- **Status do servidor local**: porta, PID, `game_data_loaded` e research
  mode do servidor vivo agora.

Fechar o Studio **não** encerra o servidor local — para não interromper um
teste de dispositivo em andamento; use o menu quando quiser parar.

Cada etapa grava relatório JSON em `work/revival-studio/<id-do-projeto>/reports/`
e o log da sessão em `…/logs/`.

## Abas

### Projeto
Formulário (APK de entrada, hostname, CA opcional, estratégia de patch),
checks de estado e etapas do pipeline.

### Visuais (fase 7)
Editor da tela de loading: o bundle é aberto, as texturas candidatas são
listadas e a substituição é validada (diff de imagem, CRC de catálogo
zerado, original preservado). Sem bundle informado, o Studio usa o
fast path.

### Branding (fase 8)
Nome exibido, ícone e cor de tema/splash — tudo aplicado em recursos
Android existentes, com **diff antes de aplicar** e verificação de que o
`AndroidManifest.xml` permanece intacto. O modo avançado é somente leitura.

### Assets (fase 9)
Catálogo somente-leitura dos bundles Unity: lista membros, escaneia com
política de tipos seguros (Texture2D/Sprite/TextAsset/AudioClip;
GameObject/MonoBehaviour não são desserializados — leitura de tipo sem
parser nativo derruba o processo), exibe o seletor estável
`apk_sha256|member|path_id|type|name|obj_sha256` e grava relatório
sanitizado (sem bytes de asset).

### Compatibilidade (fase 16)
Painel do registro `compatibility.json` (116 rotas do cliente):

- resumo: total, implementadas, DoD completo, schemas extraídos,
  requisições/respostas observadas, validação de cliente, persistência,
  testes de regressão e fallbacks;
- árvore por rota com o próximo gate aberto;
- próxima tarefa de `scripts/next_task.py --json`;
- mutação de evidência **somente** via
  `scripts/generate_endpoint_matrix.py --set ROTA=campo=valor`, com
  confirmação e diff antes/depois — não existe checkbox "done" e a aba
  nunca escreve no JSON;
- estado do servidor vivo em `GET /revival/research`, avisando quando
  `research_mode` está ativo ou há fallbacks (modo final exige
  `RESEARCH_MODE=false` e zero fallbacks).

## Testes

- **Testes → Testes Python do editor**: suíte de regressão do Studio.
- **Testes → verify_everything.py**: o mesmo gate do repositório (npm,
  Python, registro, coerência).

## Regras que o Studio segue (e você pode confiar)

- O APK de entrada nunca é modificado; toda saída é promovida
  atomicamente (`promote_atomic`).
- Fechar a janela com job rodando pede confirmação, cancela e só então
  encerra — saída válida anterior não é sobrescrita.
- Item de menu desabilitado quando o pré-requisito de estado não existe.
- Nada versiona APK, XAPK, bundles, dumps, certificados ou keystores:
  `work/` é ignorado por padrão.
- Instalação no dispositivo nunca é automática: o Studio detecta e valida,
  você decide.

## Solução de problemas

- **"python não encontrado"**: instale Python 3.11+ e reabra o launcher.
- **Ferramentas bloqueando**: rode *Preparar ferramentas* e depois
  *Verificar* de novo; o log mostra o hash esperado de cada JAR.
- **Servidor inválido no preflight**: confira HTTPS/certificado e se
  `/revival/health` responde; CA local só em laboratório.
- **Job travado**: use o botão de cancelar na barra de job; o subprocesso
  é encerrado de forma controlada e registrada no log.
- **Logs**: **Log → Abrir pasta de logs do projeto** ou
  `work/revival-studio/<id>/logs/`.
