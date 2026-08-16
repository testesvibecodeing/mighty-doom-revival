# Dados locais do jogo

Este diretório é reservado para dados necessários à interoperabilidade que sejam obtidos da cópia local do usuário.

O servidor procura inicialmente:

```text
server/data/game-data.json
```

`game-data.json` não deve ser commitado. O `.gitignore` mantém todo o conteúdo deste diretório fora do Git, exceto este README.

O arquivo será validado/importado durante a análise do cliente 1.13.1. O objetivo é manter no repositório somente código próprio, schemas, hashes e documentação técnica — nunca APK, assets ou dumps proprietários.
