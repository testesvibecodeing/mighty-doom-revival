"""Diálogos "Sobre", "Preservação de jogos" e "Base legal" do Revival Studio.

Todo o texto aqui é extraído de `docs/LEGAL-PRESERVATION.md` (versão de
17/08/2026) e da seção legal do `README.md` — este módulo apenas apresenta o
que o repositório já afirma, na paleta DOOM do tema. Se o documento-fonte
mudar, mude aqui junto: o teste `tests/revival_editor/test_about.py` ancora
os fatos centrais e proíbe as afirmações que a política do projeto vetou
(§23 do documento legal).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .. import __version__
from .theme import BG, CARD_DARK, GOLD, LINE_SOLID, ORANGE, TEXT

__all__ = [
    "SOBRE_TEXTO", "PRESERVACAO_TEXTO", "LEI_TEXTO",
    "mostrar_sobre", "mostrar_preservacao", "mostrar_lei",
]


SOBRE_TEXTO = f"""Revival Studio {__version__}
mighty-doom-revival

O Mighty DOOM Revival é um projeto independente, sem fins comerciais, de
preservação e interoperabilidade: estuda e mantém viva a possibilidade de
executar um jogo cujo serviço oficial foi descontinuado, por meio de uma
implementação independente dos serviços de rede que o cliente precisa.

O QUE ELE FAZ
  • Servidor de compatibilidade próprio (código clean-room);
  • Ferramentas de patch que operam SOMENTE sobre a cópia local do
    próprio usuário — o repositório nunca fornece o jogo;
  • Documentação de protocolo e registro de compatibilidade auditável.

OS QUATRO PILARES DA POSIÇÃO DO PROJETO
  1. A cópia do cliente é fornecida pelo próprio usuário;
  2. Modificação local e uso pessoal — nunca distribuição de APK alterado;
  3. Servidor independente, sem código nem segredos do original;
  4. Sem exploração comercial e sem falsa afiliação.

AVISO DE NÃO AFILIAÇÃO
Mighty DOOM, DOOM, Bethesda, ZeniMax, Microsoft, id Software e Alpha Dog
Games pertencem aos seus respectivos titulares. Este projeto não é oficial,
não é afiliado e não é endossado por nenhuma dessas empresas. O nome do jogo
é citado apenas para identificar o software com o qual busca
interoperabilidade.

Este diálogo não é garantia de imunidade jurídica e não substitui parecer
de advogado. A análise completa está em docs/LEGAL-PRESERVATION.md e nos
menus "Ajuda → Preservação de jogos" e "Ajuda → Base legal"."""


PRESERVACAO_TEXTO = """POR QUE ESTE PROJETO EXISTE — PRESERVAÇÃO DE GAMES

Mighty DOOM era um jogo-como-serviço (games-as-a-service): exigia conexão
permanente com servidores oficiais para funcionar e não oferecia modo
offline. Os fatos relevantes:

  • o estúdio desenvolvedor, Alpha Dog Games, foi encerrado em 2024;
  • os servidores oficiais foram desligados em 7 de agosto de 2024,
    conforme reconhecido pelo suporte oficial da Bethesda;
  • o jogo foi removido das lojas de aplicativos;
  • não foi disponibilizado modo offline, ferramenta de migração ou
    restore oficial;
  • em consequência, cópias legitimamente adquiridas — incluindo conteúdo
    pago nelas obtido — tornaram-se integralmente inutilizáveis.

Esse cenário é o objeto central do debate internacional sobre preservação
de jogos-como-serviço (movimento Stop Killing Games,
stopkillinggames.com, e iniciativas de defesa do consumidor correlatas):
quem adquiriu legitimamente uma cópia de um jogo não deve perder o acesso
ao que pagou apenas porque o suporte externo de servidor foi desligado.

A RESPOSTA TÉCNICA ADOTADA (DELIBERADAMENTE CONSERVADORA)
Interoperabilidade — o cliente existente, fornecido pelo próprio usuário,
conversando com um servidor alternativo independente — e NÃO
redistribuição de software protegido.

POR ISSO O REPOSITÓRIO NÃO CONTÉM NUNCA:
  APK oficial · APK modificado · XAPK/APKS/AAB proprietários · assets
  extraídos · músicas/sons/texturas/modelos · dumps completos de código
  descompilado · chaves ou credenciais de serviços oficiais · código
  proprietário do cliente ou do servidor original.

COMO ESPERAMOS QUE SEJA USADO
  self-hosted · pessoal · privado · sem cobrança · sem acesso a serviços
  oficiais · sem uso de credenciais oficiais · sem se passar pelo serviço
  oficial.

SE O SERVIÇO OFICIAL VOLTAR
Se o titular restaurar de forma efetiva o suporte necessário ao gameplay,
novos releases de substituição serão suspensos e o acesso público ao
projeto poderá ser arquivado ou tornado privado durante a avaliação.

Fonte: docs/LEGAL-PRESERVATION.md (seções 2, 4, 14, 15 e 19)."""


LEI_TEXTO = """BASE LEGAL DA PRESERVAÇÃO E DA INTEROPERABILIDADE
(leitura completa em docs/LEGAL-PRESERVATION.md, versão 17/08/2026)

AVISO INICIAL
Nada disso é garantia de imunidade jurídica, não substitui parecer de
advogado e não afirma que toda forma de uso deste projeto seja
automaticamente lícita em qualquer país. Direitos autorais, marcas,
contratos de licença, regras de plataforma e leis de anticircunvenção
podem produzir resultados diferentes conforme o país e os fatos.

━━ BRASIL — Lei nº 9.609/1998 (Lei do Software)
  art. 6º, I  — cópia de salvaguarda: não constitui ofensa a reprodução,
                em um só exemplar, de cópia legitimamente adquirida para
                salvaguarda/armazenamento eletrônico.
  art. 6º, IV — integração tecnicamente indispensável: a integração de um
                programa a sistema aplicativo/operacional, quando
                tecnicamente indispensável e destinada ao uso exclusivo de
                quem a promove, não constitui ofensa.
  Aplicação: o repositório não fornece a cópia do jogo; o usuário trabalha
  com a própria cópia legítima e conecta-a à infraestrutura que controla.
  Limitação: os incisos NÃO são licença geral para publicar, distribuir ou
  comercializar software de terceiros (art. 9º trata do uso por contrato
  de licença).

━━ BRASIL — Lei nº 9.610/1998 (Direitos Autorais)
  art. 29 — reprodução/adaptação/distribuição dependem de autorização,
            salvo limitações legais; art. 46 não autoriza redistribuir
            integralmente jogo, assets ou material audiovisual.
  Conclusão operacional: não hospedar nem redistribuir APK, assets ou
  material proprietário é medida central de conformidade.

━━ BRASIL — Lei nº 9.279/1996 (Marcas)
  art. 129 — uso exclusivo do titular; art. 132, IV — o titular não pode
  impedir citação sem conotação comercial e sem prejuízo ao caráter
  distintivo. Política: citar "Mighty DOOM" apenas para identificar o
  objeto de interoperabilidade, com aviso de não afiliação em destaque.

━━ ESTADOS UNIDOS — 17 U.S.C. § 117
  O proprietário de uma cópia pode fazer cópia/adaptação adicional quando
  etapa essencial à utilização do programa ou para arquivo; as adaptações
  NÃO ganham autorização geral de redistribuição.
  Aplicação: patch local da cópia do próprio usuário, sem publicação do
  APK modificado.

━━ ESTADOS UNIDOS — DMCA: § 1201(f) e 37 C.F.R. § 201.40
  § 1201(f) — exceção permanente de engenharia reversa: quem obteve
  legitimamente o direito de usar um programa pode desenvolver os meios
  necessários à interoperabilidade de programa independente, se as
  informações não estiverem prontamente disponíveis e sem exceder essa
  finalidade.
  37 C.F.R. § 201.40 (regra trienal de 2024) — isenção específica para
  jogos legalmente adquiridos cujo suporte de servidor externo necessário
  à autenticação/gameplay deixou de ser fornecido; inclui, em condições
  específicas, gameplay pessoal/local e preservação por bibliotecas,
  arquivos e museus.
  Limite reconhecido: NÃO é autorização universal para qualquer servidor
  privado público, qualquer redistribuição do cliente ou uso comercial.

━━ UNIÃO EUROPEIA — Diretiva 2009/24/CE
  art. 5º, 3 — observação/estudo do funcionamento do programa durante o
  uso legítimo não exige autorização (base da pesquisa de protocolo);
  art. 6º — descompilação permitida quando indispensável para obter
  informações de interoperabilidade não prontamente disponíveis, restrita
  ao necessário e sem desenvolver programa substancialmente similar;
  art. 15º — cláusulas contratuais contrárias aos arts. 5º/6º são nulas
  ou ineficazes, na transposição de cada Estado-Membro.
  Ressalva: invocação comparativa — o projeto não está sob jurisdição da
  UE e a Diretiva não autoriza redistribuição nem operação comercial.

━━ RISCO CONTRATUAL (EULA) — NÃO ESCONDIDO
Os termos publicados pela ZeniMax/Bethesda incluem restrições expressas a
modificação, engenharia reversa, distribuição e emulação/redirecionamento
de serviços. A existência de exceções legais NÃO elimina
automaticamente risco contratual; a relação entre limitações de copyright,
legislação local, direitos do consumidor e enforceability de cláusulas
deve ser avaliada caso a caso por profissional habilitado.

━━ O QUE ESTE PROJETO NÃO AFIRMA
  "100% legal em qualquer lugar" · "copyright não se aplica porque o jogo
  foi abandonado" · "é abandonware, logo domínio público" · "a DMCA permite
  qualquer servidor privado" · "sem fins lucrativos elimina copyright" ·
  "engenharia reversa é sempre permitida".

A formulação correta: o projeto busca operar dentro de fundamentos de
preservação, interoperabilidade, uso pessoal e implementação independente,
com medidas expressas para evitar redistribuição e exploração de conteúdo
proprietário.

━━ REFERÊNCIAS OFICIAIS
  Lei 9.609/1998 ....... planalto.gov.br/ccivil_03/leis/l9609.htm
  Lei 9.610/1998 ....... planalto.gov.br/ccivil_03/leis/l9610.htm
  Lei 9.279/1996 ....... planalto.gov.br/ccivil_03/leis/l9279.htm
  17 U.S.C. § 117 ...... uscode.house.gov (title 17, section 117)
  17 U.S.C. § 1201 ..... uscode.house.gov (title 17, section 1201)
  37 C.F.R. § 201.40 ... copyright.gov/title37/201/37cfr201-40.html
  Regra 1201 de 2024 ... copyright.gov/1201/2024/
  Diretiva 2009/24/CE .. eur-lex.europa.eu (celex 32009L0024)
  EULA mobile (pt-BR) .. bethesda.net/data/mobile_eula/pt-br.html
  Termos de Serviço .... bethesda.net/data/tos/en.html"""


def _janela_documento(root: tk.Misc, titulo: str, texto: str,
                      destaque: str) -> tk.Toplevel:
    """Diálogo somente-leitura com o documento, na paleta DOOM."""
    janela = tk.Toplevel(root)
    janela.title(titulo)
    janela.transient(root.winfo_toplevel())
    janela.configure(background=BG)
    janela.geometry("780x560")
    janela.minsize(560, 380)

    ttk.Label(janela, text=destaque, style="Heading.TLabel").pack(
        anchor="w", padx=16, pady=(12, 2),
    )
    ttk.Frame(janela, height=2, style="TSeparator").pack(fill="x", padx=16)

    corpo = ttk.Frame(janela)
    corpo.pack(fill="both", expand=True, padx=16, pady=10)
    corpo.rowconfigure(0, weight=1)
    corpo.columnconfigure(0, weight=1)

    conteudo = tk.Text(
        corpo, wrap="word", state="disabled", padx=12, pady=10,
        background=CARD_DARK, foreground=TEXT, insertbackground=TEXT,
        selectbackground=BG, relief="flat", borderwidth=0,
        highlightthickness=1, highlightbackground=LINE_SOLID,
        highlightcolor=ORANGE, font=("Consolas", 10),
    )
    conteudo.grid(row=0, column=0, sticky="nsew")
    rolagem = ttk.Scrollbar(corpo, orient="vertical", command=conteudo.yview)
    rolagem.grid(row=0, column=1, sticky="ns")
    conteudo.configure(yscrollcommand=rolagem.set)

    conteudo.configure(state="normal")
    conteudo.insert("1.0", texto)
    _pintar_secoes(conteudo, texto)
    conteudo.configure(state="disabled")

    ttk.Button(janela, text="Fechar", command=janela.destroy).pack(
        anchor="e", padx=16, pady=(0, 12),
    )
    janela.protocol("WM_DELETE_WINDOW", janela.destroy)
    return janela


def _pintar_secoes(texto_widget: tk.Text, texto: str) -> None:
    """Marca título (ouro) e seções "━━ …" (laranja) depois do insert."""
    texto_widget.tag_configure("secao", foreground=ORANGE)
    texto_widget.tag_configure("titulo", foreground=GOLD)
    for numero, linha in enumerate(texto.splitlines(), start=1):
        if linha.startswith("━━"):
            texto_widget.tag_add("secao", f"{numero}.0", f"{numero}.end")
        elif numero == 1:
            texto_widget.tag_add("titulo", f"{numero}.0", f"{numero}.end")


def mostrar_sobre(root: tk.Misc) -> tk.Toplevel:
    return _janela_documento(
        root, "Sobre o Revival Studio", SOBRE_TEXTO,
        destaque="REVIVAL STUDIO",
    )


def mostrar_preservacao(root: tk.Misc) -> tk.Toplevel:
    return _janela_documento(
        root, "Preservação de jogos", PRESERVACAO_TEXTO,
        destaque="PRESERVAÇÃO DE JOGOS",
    )


def mostrar_lei(root: tk.Misc) -> tk.Toplevel:
    return _janela_documento(
        root, "Base legal da preservação", LEI_TEXTO,
        destaque="BASE LEGAL",
    )
