# Roadmap — compatibilidade de 100% do Mighty DOOM

O objetivo é preservar tudo o que o cliente 1.13.1 ainda contém e substituir somente os serviços que morreram.

## Base já estruturada

- [x] download verificável do APK 1.13.1 sem commit do binário;
- [x] relatório estático sanitizado com hashes/offsets;
- [x] servidor HTTP próprio (`node:http` builtin, sem Koa);
- [x] SQLite persistente;
- [x] autenticação local;
- [x] endpoint de game data;
- [x] loja Revival configurável;
- [x] bloqueio de dinheiro real/IAP;
- [x] compra por moeda interna;
- [x] scheduler de eventos configurável;
- [x] estado de eventos por jogador;
- [x] research mode para descobrir chamadas faltantes.

## Compatibilidade a validar com o APK real

- [ ] patch do hostname dentro do Unity Addressables sem restrição de tamanho;
- [ ] TLS/CA em Android 10–16;
- [ ] formato exato de `user-data` por categoria;
- [ ] slots/equipamento;
- [ ] capítulos: start/update/end/revive/stage rewards;
- [ ] energia e regeneração;
- [ ] progressão do Slayer;
- [ ] armas, gear, launchers e ultimates;
- [ ] talentos;
- [ ] quests;
- [ ] daily rewards;
- [ ] idle rewards;
- [ ] inbox;
- [ ] reward tracks;
- [ ] cosméticos;
- [ ] eventos de game mode;
- [ ] store-offer events;
- [ ] todas as temporadas de battle pass disponíveis no dataset preservado;
- [ ] missões de battle pass e atualização via stats;
- [ ] desafios de capítulo;
- [ ] tutorial completo;
- [ ] Xbox/MSAL/Google Play substituídos por identidade local quando necessário;
- [ ] anúncios removidos ou convertidos em recompensa gratuita/local;
- [ ] IAP removido da progressão;
- [ ] todos os itens originalmente pagos acessíveis por gameplay/moeda interna;
- [ ] matriz de testes em Android físico e emulador.

## Política de conteúdo do Revival

A loja do servidor não processará cartão, Google Play Billing, dinheiro real ou equivalentes. Conteúdo originalmente associado a IAP poderá ser disponibilizado no servidor pessoal através de moedas que existam dentro do jogo, recompensas, quests ou eventos.

## Estratégia

1. Executar a análise CI do APK oficial e registrar os locais exatos do endpoint.
2. Fazer o APK patchado abrir e alcançar `/game/auth/register`.
3. Gravar a sequência completa de endpoints solicitados pelo cliente.
4. Implementar cada endpoint com o schema real observado.
5. Importar as definições preservadas de eventos/battle passes sem colocar APK/assets no Git.
6. Criar testes de regressão para cada tela/fluxo antes de desligar `RESEARCH_MODE`.
