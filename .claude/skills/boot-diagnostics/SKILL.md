---
name: boot-diagnostics
description: Triagem de logcat do Mighty DOOM patchado até a causa raiz — barra de loading travando em 100%, "Malformed response payload", "Failed to launch after 3 attempts", "Session token is not a well formed JWT", "CRC Mismatch", "Cant find corresponding data tool data". Use quando o jogo não passar do boot, travar, fechar sozinho ou não carregar cena.
---

# Diagnóstico de boot — do logcat à causa raiz

## Capturar

```bash
adb logcat -c                                   # limpa antes de abrir o jogo
adb logcat -v time > work/apk-patch/bootN-logcat.txt
# abra o jogo, espere travar/abortar, Ctrl+C
```

Em paralelo, guarde o stdout do servidor — ele loga
`[req] POST /collections/doom/game/... -> 200 123B 4ms`. **A correlação entre os
dois lados é a ferramenta principal desta skill.**

`work/` está no `.gitignore`; logcats **não** são commitados.

## Triagem em 30 segundos

```bash
grep -nE "Malformed response payload|Failed to launch|not a well formed JWT|CRC Mismatch|RemoteProviderException|Cant find corresponding|Network response" work/apk-patch/bootN-logcat.txt | head -40
```

Ruído esperado no emulador, **ignore**: `goldfish_vulkan: exportSyncFdForQSRILocked
... Bad file descriptor` repetido a cada frame. Não é causa de nada.

## Assinaturas conhecidas

### 1. `Malformed response payload` → abort (CONFIRMADO — é o travamento em 100%)

```text
E Unity : Network response (5):
E Unity : Malformed response payload
E Unity : Ubu.<SendRequestAsync>d__18:MoveNext()
...
E Unity : Failed to launch after 3 attempts. Aborting.
E Unity : Ubu.GameController:Relaunch()
E Unity : Ubu.GameController:RestartConnectionHandler(Request, Response)
```

O cliente falha ao desserializar uma resposta, o `GameController` relança o boot,
falha 3 vezes e aborta — é exatamente o "enche a barra e morre".

**Causa quase sempre é uma destas:**

- campo numérico **não-nullable** enviado como `null` explícito (omita o campo);
- tipo errado (string onde o DTO espera int, ou vice-versa);
- campo obrigatório ausente;
- `uts` fora do formato `yyyy-MM-ddTHH:mm:ss` UTC;
- `code` diferente de `1000` numa resposta que o cliente trata como sucesso.

Ver skill `revival-server`, seção "Regra do `null`".

**Sobre o `(N)` de `Network response (N)`** — `A VERIFICAR`. Em
`work/apk-patch/boot6-logcat.txt` a sequência das 3 tentativas é `5`, `11`, `17`:
passo constante de 6, o que **sugere** contador sequencial de request na fila (6
requests por tentativa de boot), não um enum de erro. Não afirme que é enum sem ter
resolvido o tipo no metadata (skill `il2cpp-recon`).

**Método de bisseção (é assim que se resolve, não por palpite):**

1. no log do servidor, conte os `[req]` da tentativa e ache o **N-ésimo** —
   ele é o candidato;
2. capture o corpo exato que o servidor devolveu naquela chamada;
3. valide cada campo contra o DTO real (`Ubu.GameApi.Methods.*Response`) via
   `il2cpp-recon`: nulabilidade, tipo, nome de wire;
4. reduza a resposta ao mínimo (só os campos obrigatórios) e suba de novo. Se
   bootar, devolva os campos **um a um** até reproduzir;
5. registre o resultado com o comando que o produziu.

### 2. `Session token is not a well formed JWT as expected` (CONFIRMADO)

```text
E Unity : Session token is not a well formed JWT as expected
          Ubu.GameController:UpdateSessionToken(String)
```

O servidor emite token opaco (`randomBytes(32).toString('base64url')` em
`server/src/db.js`), e o cliente espera **JWT** com claims
`iss/aud/iat/exp/sub` + `ubu_sid` + `ubu_nonce` (evidência: DTO
`Ubu.GameApi.DataObjects.GameSessionToken`, literais `ubu_sid`/`ubu_nonce`, e
`JwtInvalid/JwtExpired/JwtBadSignature/JwtBadSub` = 2110–2113 no `ResponseCode`).

Sozinho isso pode não abortar o boot, mas envenena tudo depois. Trate junto com
`/game/session/refresh`, que hoje devolve o mesmo token em vez de um novo.

### 3. `Cant find corresponding data tool data for ability <Nome> id <N>` (CONFIRMADO)

```text
E Unity : Cant find corresponding data tool data for ability SleightOfHand1 id 229
          Ubu.GameController:ProcessGameData(String)
```

Centenas de linhas. O `game-data.json` servido em `/data` não tem as definições de
ability que o cliente exige. Extraia os pares `<Nome> id <N>` do log para saber
exatamente o que falta:

```bash
grep -oE "for ability [A-Za-z0-9_]+ id [0-9]+" work/apk-patch/bootN-logcat.txt | sort -u
```

Checagens rápidas: `GET /revival/health` → `game_data_loaded: true`; `/data` só
responde se o `Authorization` terminar com o `game_data_token` do config, senão
`403`, e `503` se o arquivo não existe.

### 4. `CRC Mismatch` / `RemoteProviderException` (CONFIRMADO — regressão fácil)

```text
E Unity : CRC Mismatch. Provided f870449, calculated fc165b0 from data.
          Will not load AssetBundle 'aa\Android\defaultlocalgroup_scenes_all_<hash>.bundle'
E Unity : RemoteProviderException : Invalid path in AssetBundleProvider: 'jar:file:///...'
```

O `Invalid path` é **enganoso** — o caminho está certo; a Unity recusou o bundle
pelo CRC. Sintoma: menu abre, o load da cena morre.

Causa: um bundle foi resserializado (patch bundle-aware ou injeção de loading
screen) sem zerar o `m_Crc` correspondente em `assets/aa/catalog.json`. Correção:
`zero_catalog_crc()` — ver skill `apk-patch`.

## Árvore de decisão

```text
Trava em 100% / relança 3x e aborta
├── tem "Malformed response payload"? ......... assinatura 1 (bisseção do request N)
├── tem "not a well formed JWT"? .............. assinatura 2 (token de sessão)
├── tem "Cant find corresponding data"? ....... assinatura 3 (game-data.json)
└── nenhuma das três?
    └── o servidor recebeu algum [req]?
        ├── não → problema de rede/TLS/hostname:
        │        verifique o APK (verify_patched_apk.py), DNS, CA no
        │        network_security_config e /revival/health por HTTPS
        └── sim → compare status e corpo com o DTO real (il2cpp-recon)

Menu abre e morre ao carregar cena
└── "CRC Mismatch" / RemoteProviderException ... assinatura 4 (zero_catalog_crc)

Nem abre / crash imediato
└── suspeite de metadata IL2CPP corrompido: reconstrua do APK original.
    Nunca "conserte" global-metadata.dat com regex.
```

## Preflight antes de acusar o cliente

```bash
python scripts/check_revival_server.py --server meu.host.exemplo --report work/apk-patch/server-preflight.json
python scripts/verify_patched_apk.py  --apk output/mighty-doom-revival.apk --server meu.host.exemplo
```

O primeiro valida HTTPS, `/revival/health` e o formato do `uts`. O segundo prova
que o APK aponta para o seu host e que **zero** bytes do host oficial sobraram. Se
qualquer um falhar, o problema não é o wire.

## Higiene

- Um logcat por tentativa, numerado (`boot7-logcat.txt`), com a mudança que motivou
  a tentativa anotada na resposta ao usuário — não no repositório.
- Mude **uma coisa por tentativa**. Duas mudanças juntas e a bisseção morre.
- Não cole logcat inteiro em arquivo versionado; cite linha e assinatura.
- Ao concluir, marque `CONFIRMADO` só o que este ciclo mediu; o resto é
  `A VERIFICAR`.
