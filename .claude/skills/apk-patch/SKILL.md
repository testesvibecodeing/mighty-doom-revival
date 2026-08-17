---
name: apk-patch
description: Pipeline fim-a-fim de patch do APK do Mighty DOOM 1.13.1 — trocar o hostname da API, patch bundle-aware com UnityPy, zerar o CRC do catálogo Addressables, injetar loading screen, assinar e verificar. Use ao gerar ou alterar o APK, ao ver exit 4 do precheck, ao investigar "CRC Mismatch"/"Will not load AssetBundle", ou antes de instalar um APK patchado no dispositivo.
---

# Patch do APK — Mighty DOOM 1.13.1

## Antes de qualquer coisa

- APK de entrada: `input/mighty-doom.apk` (615 MB, `com.bethsoft.ubu` 1.13.1,
  Unity 2021.3.25f1, IL2CPP arm64). **Nunca commite, nunca redistribua.**
- `java` no PATH desta máquina é **11**. apktool e uber-apk-signer exigem **17+**:

  ```bash
  JAVA=.tools/jre17/jdk-17.0.20+8-jre/bin/java.exe   # Windows
  ```

- UnityPy tem versão fixada: **1.25.3**. Outra versão reserializa diferente e
  invalida os testes.
- Ferramentas em `.tools/` são baixadas por `scripts/setup-patcher-tools.{bat,sh}`.

## Caminho feliz

```bash
scripts\patch-apk.bat        # Windows
./scripts/patch-apk.sh       # Linux/Mac
```

Faz 8 passos, nesta ordem, e para no primeiro erro:

1. preflight HTTPS do servidor (`check_revival_server.py`);
2. `analyze_apk.py` (SHA-256, hosts encontrados);
3. `apktool d -f` → `work/apk-patch/decoded`;
4. `patch_apk.py` (fast path) — se sair **4**, cai para
   `patch_bundle_from_report.py --sweep-all-bundles`;
5. `apktool b` → `work/apk-patch/revival-unsigned.apk`;
6. `verify_patched_apk.py` no APK reconstruído;
7. `uber-apk-signer` (alinha + assina) e depois `--onlyVerify`, seguido de **nova**
   `verify_patched_apk.py` no arquivo assinado;
8. copia para `output/mighty-doom-revival.apk`.

Se você rodar passos manualmente, **não pule 6 nem a re-verificação do 7**.

## Os três caminhos de patch

O endpoint pode estar em lugares diferentes; o pipeline tenta na ordem de menor
risco.

### 1. Fast path — `patch_apk.py` (byte-preserving)

Troca a URL `https://<host>/` por outra **do mesmo comprimento total**:

- host de mesmo tamanho → troca direta;
- host menor → completa com *userinfo* de URI (`https://u000@meu.host/`), que DNS,
  SNI e header `Host` ignoram; faltando 1 byte só, usa o ponto final do FQDN
  (`meu.host.`);
- host maior → **bloqueia com exit 4**. Não force.

Nenhum offset do `global-metadata.dat` se move. É por isso que essa regra existe:
aumentar a string exigiria realocar `stringLiteralData` e
`fieldAndParameterDefaultValueData` e deslocar as ~20 seções seguintes — erro aí e
o IL2CPP não boota.

**Orçamento de bytes real (1.13.1):** o host da API de gameplay é
`international.gear.bethesda.net` = **31 bytes**. `slayersclub.bethesda.net` (24
bytes) é ancilar; quando o host Gear está presente, `patch_apk.py` patcheia só o
Gear. Docs antigos citam "24 bytes" — desatualizado. **Quem decide é o precheck:**

```bash
python scripts/check_patch_length.py input/mighty-doom.apk meu.host.exemplo
# exit 0 = cabe no fast path
# exit 4 = não cabe; siga para o bundle-aware (não é fatal)
# exit 2 = hostname/APK inválido
```

### 2. Bundle-aware — `patch_bundle_from_report.py --sweep-all-bundles`

No 1.13.1 real a `baseUrl` do `ProdGameServer` vive **dentro de bundles
Addressables LZ4**, não como ASCII no ZIP — um scan cru não acha nada. Para cada
`assets/aa/**/*.bundle`:

1. `patch_bundle()` deixa a UnityPy decodificar e resserializa o objeto;
2. sobrando bytes oficiais no payload cru, `patch_raw_bundle()` troca **apenas** o
   que é comprovadamente string Unity serializada (comprimento e alinhamento
   consistentes) — nunca busca-e-substituição cega;
3. mudou algo no bundle → `zero_catalog_crc()` obrigatório (abaixo).

### 3. Bloqueio deliberado

Se a única ocorrência exigir realocação de metadata IL2CPP, o patcher **para** e
preserva a árvore de trabalho. Isso é comportamento correto, não bug. Não contorne
com `sed`/regex no `.dat`.

## Zerar o CRC do catálogo — não é opcional

`assets/aa/catalog.json` guarda, por bundle, o `AssetBundleRequestOptions` com o
CRC **do build oficial** (JSON UTF-16LE dentro do base64 de `m_ExtraDataString`).
Qualquer reserialização muda o CRC real e a Unity recusa carregar:

```text
CRC Mismatch ... Will not load AssetBundle
RemoteProviderException  "Invalid path"   ← sintoma enganoso no logcat
```

A Unity só valida CRC **não-zero**. `zero_catalog_crc()` troca os dígitos por
`"0"` + espaços — mesmo comprimento em bytes, JSON válido, nenhum offset do stream
deslocado. O bundle é casado pelo hash de 32 hex no nome do arquivo.

Sintoma clássico da regressão: o APK abre o menu e morre ao carregar a cena.

Regressão coberta por `tests/test_zero_catalog_crc.py`.

## Loading screen custom

```bash
python scripts/inject_loading_screen.py --image arte.png --mode image+text \
  --title "MIGHTY DOOM REVIVAL" --subtitle "servidor da comunidade" \
  --apk-in output/mighty-doom-revival.apk --report work/apk-patch/loading.json
```

Entrada padrão: `output/mighty-doom-revival.apk` se existir, senão
`input/mighty-doom.apk`. Modos: `auto | image | text | image+text`.
`--export-png` compõe a arte e sai sem injetar (bom para revisar antes).
GUI equivalente: `scripts/loading_screen_editor.py` (Tkinter, worker thread +
`queue.Queue`, `drain_log_queue`).

**Injeção mexe em bundle → o script já chama `zero_catalog_crc`.** Se você injetar
por outro caminho, chame na mão. Depois de injetar, **assine de novo**.

## Assinatura

```bash
$JAVA -jar .tools/uber-apk-signer.jar -a work/apk-patch/revival-unsigned.apk --overwrite --verbose
$JAVA -jar .tools/uber-apk-signer.jar -a work/apk-patch/revival-unsigned.apk --onlyVerify --verbose
```

O signer alinha e assina; não é preciso zipalign/apksigner do Android SDK. A
assinatura difere da oficial — **desinstale a versão oficial antes de instalar**:

```bash
adb uninstall com.bethsoft.ubu
adb install output/mighty-doom-revival.apk
```

## Verificação final (obrigatória)

```bash
python scripts/verify_patched_apk.py --apk output/mighty-doom-revival.apk \
  --server meu.host.exemplo --report work/apk-patch/final-apk-verification.json
```

Ele varre o ZIP **e** os bundles Unity via UnityPy. Critério de aceite: ocorrências
do host novo > 0 e **zero** bytes do host oficial. Rode **depois** da assinatura —
assinar reescreve o ZIP.

## Certificado HTTPS

- Domínio público com CA válida → deixe o campo de CA vazio.
- Laboratório/LAN com CA própria → passe `--ca caminho.pem`; o patcher copia a CA
  como recurso Android e referencia no `network_security_config`
  (`patch_apk.py: write_network_security`).

## Armadilhas já pagas

- **`java` errado** → apktool falha com erro de class version. Use `.tools/jre17`.
- **Verificar antes de assinar e parar por aí** → o arquivo entregue não é o
  verificado. Verifique o assinado.
- **Editar `work/apk-patch/decoded` na mão** e rebuildar sem re-verificar.
- **Rodar o pipeline duas vezes sobre o mesmo `output/`** — `patch-apk.sh` faz
  `rm -rf work/apk-patch` no início; a injeção de loading screen sobrescreve
  `output/` in-place por padrão. Guarde cópia se precisar comparar.
- **APK grande, decode lento**: `apktool d` neste APK leva minutos. Não é travamento.
- Não versionar nada de `work/`, `output/`, `input/`, `.tools/`, `reports/`.

## Testes desta área

```bash
python scripts/test_patch_apk.py
python scripts/test_patch_primary_api_host.py
python scripts/test_patch_network_security.py
python scripts/test_patcher_orchestration.py
python scripts/test_verify_patched_apk.py
python scripts/test_patch_unity_bundle.py
python scripts/test_patch_unity_raw_strings.py
python scripts/test_check_patch_length.py
python tests/test_zero_catalog_crc.py
python tests/test_inject_loading_screen.py
```

Detalhe completo: `docs/APK-PATCH.md`.
