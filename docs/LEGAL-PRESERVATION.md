# Aviso Legal, Política de Preservação e Base Jurídica

> **Versão:** 16 de agosto de 2026  
> **Projeto:** Mighty DOOM Revival  
> **Natureza:** preservação, interoperabilidade, pesquisa técnica e uso não comercial

## 1. Aviso importante

Este documento registra a finalidade do projeto, as medidas adotadas para respeitar propriedade intelectual e os fundamentos jurídicos que podem ser relevantes à preservação e à interoperabilidade de software descontinuado.

**Este documento não é uma garantia de imunidade jurídica, não substitui parecer de advogado e não afirma que toda forma possível de uso deste projeto seja automaticamente lícita em qualquer país.** Direitos autorais, marcas, contratos de licença, regras de plataforma e leis de anticircunvenção podem produzir resultados diferentes conforme o país, o modo de uso e os fatos concretos.

A política deste projeto é adotar a interpretação mais conservadora compatível com preservação e interoperabilidade, evitando redistribuição de conteúdo proprietário e exploração comercial.

---

## 2. Finalidade do projeto

O Mighty DOOM Revival existe para estudar e preservar a possibilidade de execução de um jogo cujo serviço oficial foi descontinuado, por meio de uma implementação independente dos serviços de rede necessários ao funcionamento do cliente.

O objetivo não é substituir comercialmente o produto original, concorrer com seus titulares, vender cópias do jogo, apropriar-se de marcas, remover créditos ou distribuir conteúdo proprietário.

O projeto busca:

- preservar conhecimento técnico sobre um software descontinuado;
- permitir interoperabilidade com uma implementação independente de servidor;
- documentar protocolos e comportamentos necessários ao funcionamento do cliente;
- permitir que uma pessoa utilize uma cópia legitimamente obtida em ambiente próprio;
- manter código de servidor e ferramentas próprias separados do conteúdo protegido do jogo;
- impedir monetização com dinheiro real dentro do Revival;
- manter reconhecimento expresso de todos os titulares originais.

---

## 3. Titularidade e ausência de afiliação

Mighty DOOM, DOOM, Bethesda, ZeniMax, Microsoft, id Software, Alpha Dog Games e todas as marcas, personagens, ilustrações, músicas, sons, modelos, textos, logos, nomes e demais elementos protegidos relacionados pertencem aos seus respectivos titulares.

Este projeto:

- **não é oficial**;
- **não é afiliado** à Bethesda, ZeniMax, Microsoft, id Software ou Alpha Dog Games;
- **não é endossado** por qualquer dessas empresas;
- **não reivindica propriedade** sobre o jogo ou suas marcas;
- usa referências ao nome do jogo somente para identificar o software com o qual busca interoperabilidade e preservação.

Nenhum aviso presente neste repositório transfere ou pretende transferir direitos de terceiros ao mantenedor do projeto.

---

## 4. Política obrigatória de não redistribuição

Para reduzir risco jurídico e respeitar direitos autorais, este repositório público **não deve conter nem distribuir**:

- APK oficial do Mighty DOOM;
- APK modificado/patcheado do Mighty DOOM;
- XAPK/APKS/AAB proprietários;
- assets extraídos do jogo;
- músicas, efeitos sonoros, vídeos, texturas, modelos ou artes proprietárias;
- dumps completos de código descompilado;
- dumps completos de IL2CPP/global metadata que reproduzam material proprietário além do necessário para pesquisa técnica;
- chaves, tokens, credenciais ou segredos de serviços oficiais;
- dados privados obtidos de infraestrutura oficial;
- código-fonte proprietário do cliente ou do servidor original;
- arquivos de licenciamento, chaves ou mecanismos destinados a liberar conteúdo pago por meios não autorizados.

O usuário deve fornecer **localmente** a sua própria cópia, obtida de forma legítima, quando uma ferramenta precisar operar sobre o cliente.

O patcher deve produzir sua saída apenas no computador do próprio usuário. O resultado não deve ser commitado nem publicado pelo projeto.

---

## 5. Clean-room / implementação independente

O servidor Revival deve ser desenvolvido como implementação independente de compatibilidade.

A política técnica é:

1. observar comportamento externo necessário à interoperabilidade;
2. documentar requests/responses, formatos, estados e requisitos funcionais;
3. escrever código próprio para reproduzir o comportamento necessário;
4. não copiar código-fonte proprietário;
5. não importar trechos descompilados para o servidor;
6. não usar segredos ou credenciais oficiais;
7. não acessar servidores oficiais sem autorização;
8. não interferir com usuários, infraestrutura ou serviços do titular.

Quando identificadores técnicos forem necessários para interoperabilidade, devem ser usados apenas na extensão necessária para compatibilidade e sem incorporar conteúdo protegido desnecessário.

---

## 6. Brasil — Lei do Software (Lei nº 9.609/1998)

Fonte oficial:  
https://www.planalto.gov.br/ccivil_03/leis/l9609.htm

A Lei nº 9.609/1998 é especialmente relevante porque trata de programas de computador.

### 6.1. Cópia de salvaguarda

O art. 6º, I, estabelece que não constitui ofensa aos direitos do titular a reprodução, em um só exemplar, de cópia legitimamente adquirida quando destinada à salvaguarda ou armazenamento eletrônico.

**Aplicação adotada pelo projeto:** o repositório não fornece a cópia do jogo. O usuário deve trabalhar com sua própria cópia legitimamente obtida.

### 6.2. Integração tecnicamente indispensável para uso exclusivo

O art. 6º, IV, prevê como hipótese que não constitui ofensa a integração de um programa, mantendo suas características essenciais, a sistema aplicativo ou operacional quando tecnicamente indispensável às necessidades do usuário e destinada ao uso exclusivo de quem promove a integração.

**Aplicação adotada pelo projeto:** ferramentas de patch e interoperabilidade devem ser concebidas para permitir que o próprio usuário conecte sua cópia a uma infraestrutura que ele controla, evitando redistribuir a cópia modificada.

### 6.3. Limitação importante

A mesma Lei prevê proteção autoral ao programa e sanções para violações. Por isso, os arts. 6º, I e IV **não devem ser interpretados como licença geral para publicar, distribuir ou comercializar o software de terceiros**.

Também é relevante o art. 9º, que trata do uso de programa de computador mediante contrato de licença. Termos contratuais aplicáveis ao software podem gerar discussão separada da análise puramente autoral.

---

## 7. Brasil — Lei de Direitos Autorais (Lei nº 9.610/1998)

Fonte oficial:  
https://www.planalto.gov.br/ccivil_03/leis/l9610.htm

A Lei nº 9.610/1998 protege, entre outros elementos, obras audiovisuais, músicas, fotografias, ilustrações e programas de computador, ressalvada a legislação específica destes últimos.

### 7.1. O que a lei reforça

O art. 29 estabelece, como regra geral, que reprodução, adaptação, transformação e distribuição de obra protegida dependem de autorização do titular, salvo limitações legais aplicáveis.

O art. 46 contém limitações aos direitos autorais, mas **não cria uma autorização genérica para redistribuir integralmente um jogo, seus assets, músicas, vídeos ou artes**.

**Conclusão operacional do projeto:** não hospedar nem redistribuir APK, assets ou material audiovisual proprietário é uma medida central de conformidade.

---

## 8. Brasil — marcas (Lei nº 9.279/1996)

Fonte oficial:  
https://www.planalto.gov.br/ccivil_03/leis/l9279.htm

A Lei nº 9.279/1996 assegura ao titular de marca registrada uso exclusivo nos termos do art. 129 e proteção à integridade/reputação da marca.

O art. 132, IV, por outro lado, prevê que o titular não pode impedir a citação da marca em discurso, obra científica, literária ou outra publicação quando realizada sem conotação comercial e sem prejuízo ao caráter distintivo.

### Política de marca deste projeto

- usar `Mighty DOOM` apenas para identificação clara do objeto de interoperabilidade/preservação;
- manter aviso de **não afiliação** em destaque;
- não afirmar ou sugerir que o projeto é oficial;
- não registrar domínio, produto ou serviço de modo a imitar identidade oficial;
- evitar uso desnecessário de logos oficiais em documentação e interface pública;
- preferir identidade visual própria para o projeto Revival;
- não vender produtos ou serviços utilizando a marca.

---

## 9. Estados Unidos — 17 U.S.C. § 117

Fonte oficial:  
https://uscode.house.gov/view.xhtml?req=%28title%3A17+section%3A117+edition%3Aprelim%29

A seção 117 do Copyright Act contém limitações relativas a programas de computador. Em determinadas condições, o proprietário de uma cópia de um programa pode fazer uma cópia/adaptação adicional quando isso for etapa essencial à utilização do programa com uma máquina ou para finalidade de arquivo.

A própria seção restringe a transferência das adaptações: adaptações preparadas sob essa regra não recebem uma autorização geral de redistribuição.

**Política adotada:** patch local da cópia do próprio usuário, sem disponibilização pública do APK modificado.

---

## 10. Estados Unidos — DMCA § 1201 e jogos com servidores descontinuados

Fontes oficiais:

- U.S. Copyright Office — processo de 2024:  
  https://www.copyright.gov/1201/2024/
- Regra atual, 37 C.F.R. § 201.40:  
  https://www.copyright.gov/title37/201/37cfr201-40.html

A regra vigente decorrente do processo trienal de 2024 contém uma isenção específica para determinadas situações envolvendo jogos legalmente adquiridos cujo suporte de servidor externo necessário à autenticação/gameplay deixou de ser fornecido.

A classe atual inclui, em condições específicas, modificação de programa para restaurar acesso a jogo para **gameplay pessoal/local**, além de hipóteses próprias para preservação por bibliotecas, arquivos e museus.

### Limites que este projeto reconhece

Essa isenção **não deve ser tratada como autorização universal para qualquer servidor privado público, qualquer plataforma, qualquer redistribuição do cliente ou qualquer uso comercial**.

A regulamentação possui definições e condições específicas, inclusive quanto a `complete games`, `ceased to provide access` e `local gameplay`.

Por isso, a referência à regra norte-americana serve como fundamento de que a preservação de jogos abandonados e a restauração de acesso são usos juridicamente reconhecidos em certas circunstâncias — **não como um salvo-conduto irrestrito**.

---

## 11. Termos/EULA da ZeniMax/Bethesda — risco contratual que não deve ser escondido

Fonte oficial do Mobile EULA disponível atualmente:  
https://bethesda.net/data/mobile_eula/pt-br.html

Fonte oficial dos Termos de Serviço:  
https://bethesda.net/data/tos/en.html

Os termos publicados pela ZeniMax/Bethesda incluem restrições contratuais a modificação, engenharia reversa, distribuição e emulação/redirecionamento de serviços.

Isso significa que **não é correto afirmar que a existência de exceções legais elimina automaticamente qualquer risco contratual**.

A relação entre limitações legais de copyright, legislação local, direitos do consumidor, validade/enforceability de cláusulas contratuais e fatos específicos deve ser avaliada caso a caso por profissional habilitado.

Esta transparência faz parte da política de boa-fé do projeto.

---

## 12. Por que o repositório não deve hospedar o APK

Hospedar o APK oficial ou um APK patchado cria um risco jurídico muito maior do que distribuir somente:

- código independente de servidor;
- documentação de interoperabilidade;
- patcher que opera sobre arquivo fornecido pelo próprio usuário;
- testes sintéticos;
- scripts de instalação do servidor.

A estratégia mais defensável é a **transformação local**:

```text
cópia legítima do usuário
        |
        | patch local
        v
cópia modificada somente no dispositivo do usuário
        |
        v
servidor independente controlado pelo usuário
```

E não:

```text
GitHub/site público
        |
        v
APK proprietário modificado para download público
```

Por política, este projeto adota o primeiro modelo.

---

## 13. Política de monetização

O projeto deve permanecer não comercial quanto ao conteúdo de terceiros.

É proibido pelo projeto:

- vender APK;
- cobrar para liberar o jogo;
- vender moeda virtual por dinheiro real;
- vender itens ou personagens por dinheiro real;
- oferecer assinatura paga para acesso ao conteúdo protegido;
- usar publicidade ou monetização que transforme o conteúdo de terceiros em produto comercial do projeto;
- vender suporte como condição para acesso ao jogo.

Pacotes internos do servidor Revival devem utilizar exclusivamente moedas/recursos internos do jogo obtidos por gameplay ou concedidos pelo servidor pessoal.

Doações, se algum dia existirem, devem ser juridicamente avaliadas antes de serem implementadas e nunca podem comprar acesso, vantagem ou conteúdo protegido.

---

## 14. Política de servidor

Para a posição jurídica mais conservadora, o uso recomendado é:

- self-hosted;
- pessoal;
- privado;
- sem cobrança;
- sem acesso a serviços oficiais;
- sem uso de credenciais oficiais;
- sem matchmaking com infraestrutura oficial;
- sem mascarar o servidor como serviço oficial;
- sem coleta desnecessária de dados pessoais.

A operação de um serviço público para terceiros pode mudar substancialmente a análise jurídica, especialmente em jurisdições nas quais exceções se limitam a uso pessoal/local.

---

## 15. Política de dados e segurança

O Revival não deve:

- reutilizar credenciais Bethesda/Microsoft/Google;
- pedir senha de conta oficial;
- interceptar credenciais de terceiros;
- acessar infraestrutura oficial;
- contornar autenticação para obter conteúdo ainda comercialmente protegido em serviço ativo;
- coletar informações pessoais além do estritamente necessário ao servidor independente.

A identidade do Revival deve ser local e independente.

---

## 16. GitHub — DMCA e propriedade intelectual

Fontes oficiais:

- Política de DMCA do GitHub:  
  https://docs.github.com/pt/site-policy/content-removal-policies/dmca-takedown-policy
- Política de marcas do GitHub:  
  https://docs.github.com/pt/site-policy/content-removal-policies/github-trademark-policy
- Política de uso aceitável:  
  https://docs.github.com/pt/site-policy/acceptable-use-policies/github-acceptable-use-policies

O GitHub possui processo próprio para notificações de copyright/DMCA e pode remover conteúdo quando recebe reclamações válidas. Também possui política contra uso de marca que possa gerar confusão sobre afiliação.

### Se chegar uma notificação

O mantenedor deve:

1. não ignorar a mensagem;
2. preservar logs e histórico de commits;
3. identificar exatamente o material apontado;
4. remover ou tornar inacessível preventivamente o material específico quando apropriado;
5. não publicar novamente o mesmo material durante a análise;
6. responder de forma profissional e documentada;
7. consultar advogado antes de apresentar contranotificação DMCA, porque ela possui consequências jurídicas reais;
8. nunca enviar declaração falsa ao GitHub ou ao titular.

---

## 17. Política de contato de titulares de direitos

Se você representa de forma verificável um titular de direitos relacionado a Mighty DOOM/DOOM e acredita que algum conteúdo deste repositório excede a finalidade de preservação/interoperabilidade, entre em contato com o mantenedor pelo próprio GitHub ou utilize os canais oficiais de remoção do GitHub.

O mantenedor se compromete a:

- analisar prontamente uma solicitação identificada;
- remover conteúdo proprietário que tenha sido incluído por engano;
- suspender a disponibilização do material contestado enquanto a questão é avaliada, quando razoável;
- cooperar de boa-fé para diferenciar código independente de conteúdo proprietário;
- não utilizar esse processo para ocultar ou destruir provas de fatos relevantes.

---

## 18. Se o serviço oficial voltar a funcionar

O objetivo deste projeto é preservação de um software cujo suporte oficial deixou de funcionar.

Se o titular restaurar de forma efetiva o serviço oficial necessário ao funcionamento do cliente, ou anunciar formalmente uma restauração com acesso disponível, o mantenedor adotará a seguinte política:

1. suspender novos releases públicos relacionados à substituição do serviço oficial;
2. interromper divulgação que possa ser confundida com alternativa oficial;
3. revisar a necessidade de manutenção do servidor de compatibilidade;
4. tornar o repositório **arquivado ou privado**, se isso for necessário para respeitar a restauração do serviço e os direitos do titular;
5. manter, quando juridicamente apropriado, apenas documentação histórica/educacional que não distribua conteúdo proprietário.

Se um representante verificável do titular entrar em contato solicitando a suspensão em razão da restauração oficial, o acesso público ao projeto será suspenso durante a análise da solicitação.

**Essa política é voluntária e demonstra boa-fé; ela não pretende reconhecer previamente infração ou renunciar a direitos que possam existir.**

---

## 19. O que um fork/contribuidor deve respeitar

Ao contribuir, a pessoa declara que não incluirá:

- código proprietário copiado;
- APK ou assets do jogo;
- conteúdo obtido por vazamento;
- credenciais;
- segredos comerciais;
- dados de usuários;
- materiais cuja distribuição ela não esteja autorizada a fazer.

Pull requests contendo esse tipo de material devem ser rejeitados e removidos do histórico quando tecnicamente necessário.

---

## 20. Checklist de conformidade antes de tornar o repositório público

- [ ] Nenhum APK oficial no Git ou Releases.
- [ ] Nenhum APK patchado no Git, Releases ou site.
- [ ] Nenhum asset proprietário incluído.
- [ ] Nenhum dump completo de código descompilado incluído.
- [ ] Nenhuma chave/credencial oficial incluída.
- [ ] `.gitignore` protege binários e dumps.
- [ ] Servidor é implementação independente.
- [ ] Patcher exige arquivo fornecido pelo usuário.
- [ ] Saída do patcher permanece local.
- [ ] Site não oferece download do jogo proprietário.
- [ ] Aviso de não afiliação aparece no README e site.
- [ ] Marca é usada apenas de forma descritiva e não enganosa.
- [ ] Nenhum pagamento real libera conteúdo do jogo.
- [ ] Nenhum serviço oficial é acessado/interferido.
- [ ] Não existem credenciais oficiais no fluxo de login.
- [ ] Existe canal de contato para titulares.
- [ ] Existe política para retorno do serviço oficial.
- [ ] Mudanças relevantes de copyright/EULA/DMCA são revisadas periodicamente.

---

## 21. Documentação de boa-fé recomendada

Manter no Git histórico claro de:

- finalidade de preservação;
- origem de cada arquivo autoral próprio;
- ausência de binários proprietários;
- decisões de clean-room;
- testes sintéticos usados em vez de conteúdo proprietário;
- data em que o suporte oficial deixou de existir;
- data e fonte de eventual retorno do serviço;
- solicitações recebidas de titulares e medidas adotadas.

A documentação não transforma automaticamente uma atividade em lícita, mas ajuda a demonstrar finalidade, proporcionalidade e boa-fé.

---

## 22. Pontos que NÃO devem ser afirmados publicamente

Para evitar declarações juridicamente frágeis, o projeto não deve dizer:

- `este projeto é 100% legal em qualquer lugar`;
- `copyright não se aplica porque o jogo foi abandonado`;
- `é abandonware, então é domínio público`;
- `podemos distribuir o APK porque o servidor morreu`;
- `a DMCA permite qualquer servidor privado`;
- `uso sem fins lucrativos elimina copyright`;
- `engenharia reversa é sempre permitida`.

Nenhuma dessas afirmações é suficientemente precisa como regra geral.

A formulação correta é: **o projeto busca operar dentro de fundamentos de preservação, interoperabilidade, uso pessoal e implementação independente, com medidas expressas para evitar redistribuição e exploração de conteúdo proprietário.**

---

## 23. Resumo da posição jurídica do projeto

A posição de conformidade do Mighty DOOM Revival é construída sobre quatro pilares:

1. **cópia do cliente fornecida pelo próprio usuário**, e não pelo repositório;
2. **modificação local e uso pessoal**, em vez de distribuição de APK modificado;
3. **servidor independente/clean-room**, sem código ou segredos do servidor original;
4. **ausência de exploração comercial e de falsa afiliação**.

Há fundamentos legais relevantes no Brasil para cópia de salvaguarda e integração tecnicamente necessária de programa legitimamente adquirido para uso exclusivo do usuário, e nos Estados Unidos existem limitações relativas a cópia/adaptação de programas e uma isenção temporária específica de anticircunvenção para determinadas situações envolvendo jogos cujo suporte de servidor foi encerrado.

Esses fundamentos fortalecem a justificativa de preservação/interoperabilidade, mas **não eliminam automaticamente riscos decorrentes de contratos/EULA, marcas, direitos sobre assets ou usos públicos que excedam as condições das exceções aplicáveis**.

---

## 24. Recomendação profissional

Antes de disponibilizar publicamente servidor para terceiros, hospedar qualquer arquivo derivado do cliente, aceitar dinheiro, usar logos oficiais em destaque ou responder a notificação de titular, recomenda-se obter parecer de advogado especializado em propriedade intelectual/software com análise das jurisdições relevantes.

Isso é especialmente importante porque o Mobile EULA publicado pela ZeniMax contém restrições expressas a engenharia reversa e porque a isenção norte-americana para jogos descontinuados possui escopo limitado.

---

## 25. Referências oficiais

### Brasil

- Lei nº 9.609/1998 — Software:  
  https://www.planalto.gov.br/ccivil_03/leis/l9609.htm
- Lei nº 9.610/1998 — Direitos Autorais:  
  https://www.planalto.gov.br/ccivil_03/leis/l9610.htm
- Lei nº 9.279/1996 — Propriedade Industrial/Marcas:  
  https://www.planalto.gov.br/ccivil_03/leis/l9279.htm

### Estados Unidos

- 17 U.S.C. § 117:  
  https://uscode.house.gov/view.xhtml?req=%28title%3A17+section%3A117+edition%3Aprelim%29
- U.S. Copyright Office — Section 1201:  
  https://www.copyright.gov/1201/
- 2024 Section 1201 Rulemaking:  
  https://www.copyright.gov/1201/2024/
- 37 C.F.R. § 201.40:  
  https://www.copyright.gov/title37/201/37cfr201-40.html

### GitHub

- DMCA Takedown Policy:  
  https://docs.github.com/pt/site-policy/content-removal-policies/dmca-takedown-policy
- Trademark Policy:  
  https://docs.github.com/pt/site-policy/content-removal-policies/github-trademark-policy
- Acceptable Use Policies:  
  https://docs.github.com/pt/site-policy/acceptable-use-policies/github-acceptable-use-policies

### Titular / termos do software

- ZeniMax/Bethesda Mobile EULA (pt-BR):  
  https://bethesda.net/data/mobile_eula/pt-br.html
- ZeniMax/Bethesda Terms of Service:  
  https://bethesda.net/data/tos/en.html

---

## 26. Short English notice for rights holders

**Mighty DOOM Revival is an independent, non-commercial preservation and interoperability project. It is not affiliated with, sponsored by, or endorsed by Bethesda, ZeniMax, Microsoft, id Software, or Alpha Dog Games. The public repository is intended to contain only independently written server/tooling code and documentation; it must not distribute the original or patched game APK, proprietary game assets, decompiled proprietary source code, credentials, or confidential service data. Users are expected to supply their own lawfully obtained copy locally.**

**If you are a verified rights holder and believe material in this repository exceeds those boundaries, please contact the maintainer or use GitHub's rights-reporting channels. The maintainer will promptly review the request and suspend disputed public material where appropriate. If official server support required for gameplay is effectively restored, the maintainer will review the continued necessity of the replacement service and may archive or make the repository private.**

---

## 27. Última observação

A melhor proteção jurídica deste projeto não é uma frase dizendo `uso educacional` ou `sem fins lucrativos`. É o desenho técnico e operacional consistente com essa finalidade:

**não distribuir o jogo, não copiar código proprietário, não explorar comercialmente, não fingir afiliação oficial, exigir cópia legítima do usuário, manter o patch local, limitar a interoperabilidade ao necessário e cooperar de boa-fé com titulares de direitos.**
