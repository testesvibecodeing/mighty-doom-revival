# Patch do APK — Windows / Linux / Mac

O objetivo do patcher é receber **uma cópia local do APK do próprio usuário** e gerar uma cópia assinada para laboratório apontando para um backend self-hosted.

Os scripts existem em duas versões equivalentes: `.bat` para Windows e `.sh` para Linux/Mac. Os exemplos abaixo mostram a versão Windows; basta trocar `scripts\nome.bat` por `./scripts/nome.sh` no Linux/Mac.

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

- Python 3.11+
- Java/JDK 17+
- apktool
- Android SDK Build Tools (`zipalign` e `apksigner`)
- ADB, recomendado para instalação/testes

Confirme no Prompt/PowerShell:

```bat
python --version
java -version
apktool --version
zipalign -h
apksigner version
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

```bat
scripts\patch-apk.bat
```

No Linux/Mac:

```bash
./scripts/patch-apk.sh
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
- recompila, alinha e assina o APK.

## Como o patch lida com o tamanho (e por que hostname maior é bloqueado)

No APK real 1.13.1, o endpoint não está em um Addressable/bundle — está
embutido duas vezes no `global-metadata.dat` do IL2CPP como a URL completa
`https://slayersclub.bethesda.net/` (33 bytes): uma na tabela de string
literals (`stringLiteralData`) e outra no blob de valores default de
campo/parâmetro (`fieldAndParameterDefaultValueData`). Strings dentro desse
formato não devem ser aumentadas por uma simples busca-e-substituição: isso
exigiria realocar as duas seções e deslocar os offsets de todas as ~20 seções
de metadata que vêm depois no arquivo, e um erro aí quebra o boot do IL2CPP
(o app nem abre).

O patcher aceita qualquer hostname com **até o comprimento do oficial**
(24 bytes no build atual):

- **mesmo comprimento** (24 bytes): troca direta byte a byte;
- **mais curto** (ex.: `doom.sualoja.app.br`, 19 bytes): o patcher troca a
  URL inteira `https://<host>/` por outra **de mesmo comprimento total**,
  preenchendo a diferença com *userinfo* de URI:
  `https://u000@doom.sualoja.app.br/`. Userinfo é ignorado por DNS, SNI e
  pelo header `Host` — o servidor vê o hostname real — e nenhum offset do
  arquivo é deslocado. Validado contra o `global-metadata.dat` real: as duas
  ocorrências trocadas, tamanho idêntico, zero bytes do host oficial;
  faltando 1 byte só, usa o ponto final do FQDN (`<host>.`), também válido;
- **mais longo** (ex.: `doom.debruinsistemas.com.br`, 27 bytes): **bloqueado
  de propósito** (exit 4), preservando o APK de trabalho.

Hosts conhecidos atualmente:

```text
slayersclub.bethesda.net                  -> 24 bytes ASCII
game.9095be396f3547555fe1039cbc894c88.net -> 41 bytes ASCII
```

## Próxima etapa: patch bundle-aware / metadata-aware

Para aceitar um hostname maior que o oficial, o patcher vai precisar
reconstruir corretamente as duas seções do `global-metadata.dat` citadas
acima (e ainda o caminho bundle-aware para Addressables, caso um build futuro
mova o endpoint para lá). Até isso existir, use um hostname com no máximo
24 bytes — `check_patch_length.py` avisa o limite antes de você perder tempo
com o apktool.

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

Se o patcher parar com `needs_bundle_aware_patch`, isso não é uma falha inesperada: significa que ele encontrou a configuração, mas se recusou a corromper o bundle ao trocar por uma string de tamanho diferente.

O arquivo abaixo terá os detalhes:

```text
work\apk-patch\patch-report.json
```

Quando tivermos o APK alvo em mãos, esse relatório mais a análise direta do bundle será a base para concluir o patcher de hostname arbitrário.
