# Mighty DOOM Revival

Projeto pessoal de **preservação e interoperabilidade** do cliente Android de Mighty DOOM com um servidor comunitário/self-hosted.

> **Não afiliado à Bethesda, ZeniMax, Microsoft, id Software ou Alpha Dog Games.**
>
> Este repositório **não distribui o APK oficial, assets, código descompilado ou outros arquivos proprietários do jogo**. O usuário deve fornecer localmente a própria cópia do APK.

## Alvo inicial

- Jogo: Mighty DOOM
- Android package: `com.bethsoft.ubu`
- Última versão oficial conhecida: **1.13.1 (build 84862)**
- Engine: Unity 2021.3.25f1 / IL2CPP / ARM64
- API do jogo: HTTPS + JSON
- API version observada: `x-ubu-apiversion: 24.0.0`

## Estrutura

```text
mighty-doom-revival/
├── README.md
├── .gitignore
├── docs/
│   ├── APK-PATCH.md
│   └── SERVER.md
├── input/                  # coloque seu APK aqui; ignorado pelo Git
├── output/                 # APKs gerados; ignorado pelo Git
├── work/                   # arquivos temporários/descompilados; ignorado
└── scripts/
    ├── analyze_apk.py
    ├── patch_apk.py
    └── patch-apk.bat
```

## 1. Obter o APK

Use uma cópia que você possua legitimamente. Para esta pesquisa o alvo é a versão `1.13.1` / build `84862`.

Coloque-a localmente como:

```text
input/mighty-doom.apk
```

O diretório `input/` e todos os `*.apk` ficam no `.gitignore` para impedir upload acidental.

## 2. Analisar o APK

No Windows:

```bat
python scripts\analyze_apk.py input\mighty-doom.apk
```

O analisador procura, sem extrair conteúdo proprietário para o Git:

- package/version quando disponíveis;
- arquitetura e bibliotecas Unity/IL2CPP;
- bundles em `assets/aa/`;
- referências aos hosts conhecidos;
- `network_security_config`;
- SHA-256 do APK.

Depois de recebermos e analisarmos a cópia local do APK, vamos registrar apenas hashes, offsets/nomes técnicos e documentação necessária para interoperabilidade.

## 3. Servidor comunitário

A implementação comunitária que estamos usando como referência é:

```text
https://gitlab.com/dannyhpy/mightydoom-gameserver
```

Ela usa Node.js/Koa e suporta SQLite. A versão atual requer **Node.js >= 24** e **npm >= 11**.

Instalação básica em Linux/Windows:

```bash
git clone https://gitlab.com/dannyhpy/mightydoom-gameserver.git server/community
cd server/community
npm install --omit=dev --omit=optional
npm install better-sqlite3
npx knex migrate:latest
npm run start -- --addr 0.0.0.0 --port 8080 --debug
```

Por padrão o servidor escuta em `0.0.0.0:8080`. Para uso real com o cliente Android, coloque um reverse proxy HTTPS (Nginx/Caddy) na frente dele.

Veja [docs/SERVER.md](docs/SERVER.md).

## 4. Patch do APK

Execute:

```bat
scripts\patch-apk.bat
```

O script foi feito para trabalhar **somente em uma cópia local fornecida pelo usuário**. Ele:

1. valida dependências;
2. faz backup/working copy;
3. desmonta o APK com `apktool`;
4. configura `network_security_config` para o host informado;
5. opcionalmente incorpora uma CA local para HTTPS de laboratório;
6. procura o host hardcoded nos Unity Addressables;
7. executa uma substituição binária **somente quando ela puder ser feita sem alterar o tamanho da string**;
8. recompila;
9. executa `zipalign`;
10. assina o APK com uma chave pessoal de laboratório;
11. grava o resultado em `output/`.

### Limitação atual importante

O endpoint do jogo aparece dentro de um bundle Unity. Alterar uma string para tamanho diferente pode exigir reserialização/reempacotamento correto do bundle. Por segurança, o patcher atual **não corrompe o bundle tentando fazer isso no escuro**.

Assim que analisarmos o APK 1.13.1 real que será usado no projeto, a próxima etapa é implementar o patch **bundle-aware**, permitindo informar um hostname arbitrário sem a limitação de comprimento.

Veja [docs/APK-PATCH.md](docs/APK-PATCH.md).

## 5. Instalar o APK modificado

O APK recompilado terá assinatura diferente da versão oficial. Em um aparelho de testes, normalmente será necessário remover a instalação oficial antes:

```bat
adb uninstall com.bethsoft.ubu
adb install output\mighty-doom-revival.apk
```

Isso remove os dados locais existentes do app. Faça backup do que for importante antes.

## Objetivo do projeto

O objetivo é tornar um cliente de jogo descontinuado capaz de conversar com uma implementação independente do serviço necessário para funcionar, para **uso pessoal, pesquisa e preservação**.

Não serão adicionados ao repositório:

- APK oficial;
- assets do jogo;
- dumps completos do IL2CPP;
- código descompilado proprietário;
- chaves privadas;
- credenciais.

## Referências técnicas

- Servidor comunitário: `dannyhpy/mightydoom-gameserver` (GitLab)
- Pesquisa de preservação: `CTRQuko/mightydoom-preservation` (GitHub)

## Status

- [x] Repositório inicial
- [x] Documentação de servidor
- [x] Analisador local de APK
- [x] Patcher Windows inicial
- [ ] Validar contra o APK oficial 1.13.1 build 84862
- [ ] Identificar exatamente o objeto/string do endpoint no bundle Unity
- [ ] Implementar patch de hostname de tamanho arbitrário
- [ ] Validar TLS em Android moderno
- [ ] Testar login, tutorial e primeiro capítulo
- [ ] Mapear endpoints faltantes
