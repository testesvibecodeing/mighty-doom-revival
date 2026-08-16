# Revival — site da instância

Interface institucional/documental servida pelo próprio Revival Server em `server/public`.

## Identidade visual

O site usa uma identidade **original, neutra e independente**:

- sem logo de Mighty DOOM ou DOOM;
- sem screenshots, personagens ou artes oficiais;
- sem tipografia que imite a identidade visual do jogo;
- sem apresentação que sugira produto oficial;
- ilustração abstrata própria baseada em rede de nós, gradientes e formas geométricas;
- Three.js usado apenas para uma ambientação técnica de rede/infraestrutura.

A referência a **Mighty DOOM** aparece somente quando necessária para descrever a compatibilidade do cliente e a finalidade de interoperabilidade.

## Mensagem principal

> Revival é uma infraestrutura comunitária e independente para servidores administrados pelos próprios usuários. Não é um produto oficial nem possui afiliação com os titulares do jogo.

A página explica explicitamente o fluxo:

1. o usuário obtém legitimamente sua própria cópia do cliente;
2. executa o patcher no próprio computador;
3. informa o servidor Revival escolhido;
4. instala/administra sua própria instância ou conecta-se a uma instância escolhida.

## Patcher local

O patcher continua sendo parte central do projeto. A interface **não esconde nem substitui** esse fluxo.

O site não implementa download automático de APK de sites terceiros. O projeto central não fornece o APK do jogo.

Documentação:

```text
docs/APK-PATCH.md
```

## Servidor self-hosted

A interface consulta o backend da própria instância:

- `GET /revival/health` — status, uptime, jogadores, GameData, pacotes, eventos e versões;
- `GET /revival/apk` — informa se **o administrador desta instância** publicou opcionalmente um pacote configurado.

Same-origin é o padrão. Para hospedar o frontend em outro host, edite:

```text
server/public/assets/js/config.js
```

```js
window.REVIVAL_CONFIG = {
  serverUrl: "https://revival.seudominio.com",
  healthUrl: "",
  apkInfoUrl: "",
  githubUrl: "https://github.com/testesvibecodeing/mighty-doom-revival"
};
```

## Pacote configurado da instância

O endpoint `/revival/apk` continua funcional.

Quando o administrador publicou um arquivo, o site mostra:

- disponibilidade;
- tamanho;
- SHA-256;
- data de publicação;
- botão para o URL retornado pelo próprio servidor.

A interface deixa claro que isso é uma escolha e responsabilidade do **administrador daquela instância**, não uma distribuição oficial ou centralizada do projeto.

Quando nenhum arquivo está publicado, a interface mostra `NÃO PUBLICADO` e não cria nenhum fallback para download em terceiros.

## Arquivos

```text
server/public/
├── index.html
├── README.md
└── assets/
    ├── css/
    │   └── revival.css
    └── js/
        ├── app.js
        ├── config.js
        └── network-scene.js
```

## Three.js

`assets/js/network-scene.js` implementa uma cena abstrata original:

- nós de rede;
- conexões;
- grade técnica;
- anéis geométricos;
- parallax leve;
- pulso visual quando `/revival/health` responde online;
- fallback automático para CSS quando WebGL não estiver disponível ou quando `prefers-reduced-motion` estiver ativo.

## Rodar localmente

Com o backend:

```bash
cd server
npm start
```

Acesse:

```text
http://127.0.0.1:8080/
```

## Aviso legal

O site inclui aviso de independência no hero, em áreas relacionadas a APK e no rodapé.

A política completa do projeto permanece em:

```text
docs/LEGAL-PRESERVATION.md
```
