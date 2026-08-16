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

## O que o script modifica

Depois de `apktool d`, o patcher:

- aponta o `AndroidManifest.xml` para `@xml/network_security_config`;
- gera uma política TLS com o hostname informado;
- opcionalmente incorpora uma CA PEM/CRT fornecida pelo usuário;
- varre `assets/aa/` procurando hosts conhecidos;
- tenta alterar o hostname hardcoded somente quando a troca mantém exatamente o mesmo tamanho binário;
- recompila, alinha e assina o APK.

## Por que existe a limitação de tamanho?

A pesquisa comunitária encontrou o endpoint dentro de um Unity Addressable/bundle. Strings dentro de bundles serializados não devem ser aumentadas/reduzidas por uma simples busca-e-substituição: isso pode invalidar offsets, tamanhos de blocos, compressão ou metadados.

Hosts conhecidos atualmente:

```text
slayersclub.bethesda.net                  -> 24 bytes ASCII
game.9095be396f3547555fe1039cbc894c88.net -> 41 bytes ASCII
```

O patcher atual aceita uma troca binária somente se o hostname destino tiver o mesmo comprimento do hostname realmente encontrado no APK. Caso contrário ele **para de propósito**, preservando o APK de trabalho.

Isso é provisório.

## Próxima etapa: patch bundle-aware

Depois que o APK oficial 1.13.1 usado no projeto for analisado, devemos identificar:

- o bundle exato;
- o objeto Unity que contém a configuração;
- o tipo do objeto (TextAsset/MonoBehaviour/etc.);
- a forma correta de reserializar/reempacotar o bundle.

Então o patcher poderá aceitar um hostname de tamanho arbitrário, por exemplo:

```text
doom.debruinsistemas.com.br
```

sem corromper o Unity bundle.

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
