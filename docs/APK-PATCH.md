# Patch do APK — Windows / Linux / Mac

O objetivo do patcher é receber **uma cópia local do APK do próprio usuário** e gerar uma cópia assinada para laboratório apontando para um backend self-hosted.

A porta de entrada é o **Revival Studio** (`python scripts/revival_studio.py`, ou os launchers `scripts/revival-studio.bat`/`.sh`), que orquestra `scripts/patch_apk.py` e o pipeline bundle-aware. Os antigos wrappers encaminhadores de `scripts/` foram **aposentados em 2026-08-18** — além do launcher do Studio, só `install.sh`/`uninstall.sh` (deploy do servidor) permanecem; `tests/revival_editor/test_wrappers.py` guarda essa regra.

O APK oficial e seus assets não fazem parte deste repositório.

## Alvo

A primeira versão que queremos validar é:

```text
Mighty DOOM 1.13.1
build 84862
package com.bethsoft.ubu
Unity 2021.3.25f1
ARM64 / IL2CPP
```

## Dependências

Instale e deixe no `PATH`:

- Python 3.11+ (com `UnityPy==1.25.3`; o patcher instala sozinho se faltar)
- Java/JDK 17+ — o patcher resolve na ordem: `REVIVAL_JAVA` explícito >
  JRE 17 embarcado em `.tools\jre17\` > `PATH` **somente se for 17+**
  (Java 11 no `PATH` é rejeitado com instrução; veja `scripts/resolve_java.py`)
- ADB, recomendado para instalação/testes

O `apktool.jar` e o `uber-apk-signer.jar` são baixados para `.tools\` pelo
serviço **Ferramentas → Preparar ferramentas…** do Revival Studio
(`scripts/revival_editor/toolchain.py::prepare_tools`, SHA-256 pinado) — não é
preciso instalar apktool/zipalign/apksigner do Android SDK; o signer cuida de
alinhar e assinar.

Confirme no Prompt/PowerShell:

```bat
python --version
python scripts\resolve_java.py
adb version
```

## Coloque o APK localmente

Crie a pasta `input` e coloque sua cópia como:

```text
input\mighty-doom.apk
```

O `.gitignore` bloqueia `*.apk`, `input/`, `output/`, dumps e material de assinatura.

## Analise antes de alterar

```bat
python scripts\analyze_apk.py input\mighty-doom.apk
```

O relatório mostra SHA-256, indicadores Unity/IL2CPP e em quais arquivos foram encontradas referências aos hosts conhecidos.

Não publique o APK ou dumps completos no GitHub. Para documentação, registre apenas dados técnicos necessários, como versão, hash e nomes de arquivos/objetos relevantes.

## Executar o patcher

Pelo Revival Studio (menu *APK → Aplicar endpoint*):

```bash
python scripts/revival_studio.py
```

O assistente pede:

1. caminho do APK;
2. hostname HTTPS do servidor;
3. CA local opcional.

Exemplo de hostname:

```text
doom.seudominio.com
```

Use **hostname**, não IP, nesta primeira versão.

Antes de tocar no apktool, o patcher já roda `scripts/check_patch_length.py`
(um simples `ZipFile` read, sem decode): ele confere se o hostname digitado
tem **no máximo** o número de bytes do(s) host(s) oficial(is) realmente
encontrado(s) neste APK e **para na hora**, com uma mensagem explicando o
limite, se for maior. Isso evita esperar minutos de `apktool d` só para
descobrir o bloqueio de segurança depois.

## O que o script modifica

Depois de `apktool d`, o patcher:

- aponta o `AndroidManifest.xml` para `@xml/network_security_config`;
- gera uma política TLS com o hostname informado;
- opcionalmente incorpora uma CA PEM/CRT fornecida pelo usuário;
- varre `assets/aa/` (Addressables) **e** `global-metadata.dat` (tabela de
  string literals do IL2CPP) procurando hosts conhecidos;
- troca cada ocorrência do host oficial por outra de **exatamente o mesmo
  tamanho binário** (detalhes abaixo);
- no fallback bundle-aware, varre **todos** os `.bundle` de `assets/aa/` com
  UnityPy: reescreve o campo do host em objetos serializados (typetree) e, se
  restarem bytes oficiais, aplica o patch raw-string em strings Unity
  comprovadas (com comprimento/alinhamento válidos);
- zera o `m_Crc` do catálogo Addressables para cada bundle alterado
  (detalhes abaixo);
- recompila, alinha e assina o APK.

## Como o patch lida com o tamanho (e por que hostname maior é bloqueado)

Quem decide o orçamento é o precheck, não uma tabela fixa neste documento:

```bash
python scripts/check_patch_length.py input/mighty-doom.apk <host>
# medido nesta base 1.13.1: host de 31 bytes -> exit 0; 32 bytes -> exit 4
```

O host da **API de gameplay** medido no 1.13.1 é
`international.gear.bethesda.net` = **31 bytes** — é o orçamento do build.
Onde cada host vive:

- **`international.gear.bethesda.net`** (gameplay): dentro de bundles
  Addressables comprimidos em LZ4, como campo `baseUrl` do objeto
  `ProdGameServer` (ver "Patch bundle-aware" abaixo);
- **`slayersclub.bethesda.net`** (ancilar): embutido duas vezes no
  `global-metadata.dat` como a URL completa `https://slayersclub.bethesda.net/`
  (33 bytes) — uma na tabela de string literals (`stringLiteralData`) e outra
  no blob de valores default (`fieldAndParameterDefaultValueData`).

Strings nessas estruturas não devem ser aumentadas por uma simples
busca-e-substituição: isso exigiria realocar seções e deslocar os offsets de
todas as ~20 seções de metadata que vêm depois no arquivo, e um erro aí quebra
o boot do IL2CPP (o app nem abre).

O patcher aceita qualquer hostname com **até o comprimento do oficial**
(31 bytes para o host de gameplay no build atual):

- **mesmo comprimento**: troca direta byte a byte;
- **mais curto** (ex.: `doom.sualoja.app.br`, 19 bytes): o patcher troca a
  URL inteira `https://<host>/` por outra **de mesmo comprimento total**,
  preenchendo a diferença com *userinfo* de URI:
  `https://u000@doom.sualoja.app.br/`. Userinfo é ignorado por DNS, SNI e
  pelo header `Host` — o servidor vê o hostname real — e nenhum offset do
  arquivo é deslocado. Validado contra o `global-metadata.dat` real: as duas
  ocorrências trocadas, tamanho idêntico, zero bytes do host oficial;
  faltando 1 byte só, usa o ponto final do FQDN (`<host>.`), também válido;
- **mais longo**: **bloqueado de propósito** (exit 4), preservando o APK de
  trabalho.

Hosts conhecidos atualmente:

```text
international.gear.bethesda.net           -> 31 bytes ASCII  (API de gameplay; define o orçamento)
slayersclub.bethesda.net                  -> 24 bytes ASCII  (ancilar)
game.9095be396f3547555fe1039cbc894c88.net -> 41 bytes ASCII
```

## Patch bundle-aware (implementado e validado no 1.13.1)

No build real 1.13.1, o endpoint da API de gameplay **não** está como ASCII
no `global-metadata.dat` — ele vive dentro de bundles Addressables
comprimidos em LZ4, como campo de um objeto Unity serializado (o
`ProdGameServer` guarda a `baseUrl`). Por isso um scan ASCII cru do ZIP não
encontra nada: é preciso deixar a UnityPy decodificar o bundle e resserializar
o objeto com o novo host. Quando o patch direto (etapa 4) devolve exit 4, o
patcher reexecuta com `--sweep-all-bundles`:

1. para cada `assets/aa/**/*.bundle`, `patch_bundle()` resserializa objetos
   serializáveis cujo campo string contém um host oficial;
2. se ainda restarem bytes oficiais no payload bruto, `patch_raw_bundle()`
   só troca o que for comprovadamente uma string Unity serializada
   (comprimento/alinhamento consistentes) — nada de busca-e-substituição às
   cegas;
3. se **algo** mudou no bundle, `zero_catalog_crc()` zera o `m_Crc` daquele
   bundle no `assets/aa/catalog.json`.

### Por que zerar o m_Crc do catálogo

O `catalog.json` do Addressables guarda, por bundle, o `AssetBundleRequestOptions`
com o CRC **do build oficial** (serializado como JSON UTF-16LE dentro do
base64 de `m_ExtraDataString`). Qualquer resserialização muda o CRC real e a
Unity recusa carregar o bundle em runtime com `CRC Mismatch ... Will not
load AssetBundle` — o load de cena cai com um `RemoteProviderException`
"Invalid path" enganoso no logcat. A Unity só valida CRC quando o valor é
não-zero, então o zero_catalog_crc troca os dígitos por `"0"` + espaços
(comprimento em bytes idêntico; espaço entre tokens é JSON válido), sem
deslocar os offsets do stream apontados pelas entradas do catálogo. O bundle
é identificado pelo hash de 32 hex presente no nome do arquivo.

Esse foi o último bloqueio do 1.13.1: sem o zero, o APK patcheado abria o
menu e derrubava ao carregar a cena; com o zero, o jogo carrega e joga
normalmente (validado em emulador Android com gameplay completo).

### Validação no 1.13.1

O pipeline completo (fast path → bundle-aware → assinatura) foi
executado no APK real 1.13.1 e o APK resultante foi instalado em um emulador
Android: registro de conta, login, bootstrap de sessão e um run completo do
estágio 1-1 (vitória, recompensas, desbloqueio do 1-2) contra o servidor
Revival em VPS.

## Certificado HTTPS

### Domínio público próprio

Se o servidor usa um domínio seu com certificado válido emitido por uma CA pública, deixe o campo de CA vazio.

### Laboratório/LAN com CA própria

Informe um arquivo PEM/CRT no prompt do patcher. Ele será copiado para o APK de trabalho como recurso Android e referenciado no `network_security_config`.

Nunca commite a chave privada da CA.

## Assinatura

O APK oficial não pode ser recompilado mantendo a assinatura original. O script gera uma chave pessoal de laboratório em:

```text
work\signing\revival.keystore
```

Ela é ignorada pelo Git.

A senha fixa usada nesta fase experimental é apenas para uma chave descartável de laboratório; não use essa chave para publicar aplicações reais.

## Instalação

Como a assinatura será diferente, uma instalação oficial existente normalmente precisa ser removida primeiro:

```bat
adb uninstall com.bethsoft.ubu
adb install output\mighty-doom-revival.apk
```

**A desinstalação apaga os dados locais do aplicativo.** Faça backup antes se houver algo que queira preservar.

## Diagnóstico

Se o patcher parar com `needs_raw_object_mapping` /
`needs_typetree_mapping` / `needs_object_mapping`, isso não é uma falha
inesperada: significa que ele encontrou bytes do host oficial em um bundle,
mas se recusou a alterá-los sem provar que a troca é estruturalmente segura
(string Unity serializada com comprimento/alinhamento consistentes).

O arquivo abaixo terá os detalhes, incluindo type/path_id dos objetos
envolvidos para um mapeamento manual:

```text
work\apk-patch\patch-report.json
```

No emulador, `adb logcat` é o instrumento principal: `CRC Mismatch` /
`RemoteProviderException` apontam para um bundle alterado sem o zero do
catálogo; `Malformed response payload` aponta para o contrato JSON do
servidor, não para o APK.
