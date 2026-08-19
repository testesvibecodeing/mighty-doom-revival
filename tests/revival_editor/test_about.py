#!/usr/bin/env python3
"""Regressão dos diálogos "Ajuda" do Revival Studio.

Trava três coisas:

  1. o menu Ajuda existe com Sobre/Preservação/Base legal sempre habilitados;
  2. os textos carregam os fatos centrais do projeto (datas, leis, não
     afiliação) — que vêm de docs/LEGAL-PRESERVATION.md, não da imaginação;
  3. os textos NÃO contêm as afirmações que a política legal do projeto
     vetou (§23 do documento: "100% legal", "abandonware", "domínio
     público"…).

Execução: python tests/revival_editor/test_about.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - ambiente sem Tcl/Tk
    tk = None

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from revival_editor.ui import about  # noqa: E402
from revival_editor.actions import ACTIONS, MENUS, menu_actions  # noqa: E402

# Fatos que os textos precisam carregar (fonte: docs/LEGAL-PRESERVATION.md).
ANCORAS = {
    about.SOBRE_TEXTO: [
        "não é oficial", "não é afiliado", "não é endossado",
        "clean-room", "usuário", "não substitui parecer",
    ],
    about.PRESERVACAO_TEXTO: [
        "jogo-como-serviço", "Alpha Dog Games",
        "7 de agosto de 2024", "Stop Killing Games",
        "interoperabilidade", "NÃO", "self-hosted",
    ],
    about.LEI_TEXTO: [
        "Lei nº 9.609/1998", "art. 6º, I", "art. 6º, IV",
        "Lei nº 9.610/1998", "Lei nº 9.279/1996",
        "17 U.S.C. § 117", "§ 1201(f)", "37 C.F.R. § 201.40",
        "Diretiva 2009/24/CE", "EULA", "imunidade jurídica",
    ],
}

# Afirmações vetadas pela política do projeto (§23 do documento legal).
VETADOS = [
    "100% legal", "domínio público", "abandonware",
    "podemos distribuir o APK", "a DMCA permite qualquer servidor privado",
    "elimina copyright", "engenharia reversa é sempre permitida",
]


class TestTextosDosDialogos(unittest.TestCase):
    def test_ancoras_fatuais_presentes(self) -> None:
        for texto, ancoras in ANCORAS.items():
            minusculo = texto.lower()
            for ancora in ancoras:
                with self.subTest(ancora=ancora):
                    self.assertIn(ancora.lower(), minusculo)

    def test_nenhuma_afirmacao_vetada(self) -> None:
        """Fora das citações (trechos entre aspas), nada de frase vetada."""
        import re

        for texto in ANCORAS:
            sem_citacoes = re.sub(r'"[^"]*"', " ", texto, flags=re.DOTALL)
            normalizado = " ".join(sem_citacoes.split()).lower()
            for vetado in VETADOS:
                with self.subTest(vetado=vetado):
                    self.assertNotIn(vetado, normalizado)

    def test_fonte_e_data_do_documento_legal(self) -> None:
        """O diálogo aponta para o documento-fonte, não se basta."""
        self.assertIn("docs/LEGAL-PRESERVATION.md", about.LEI_TEXTO)
        self.assertIn("docs/LEGAL-PRESERVATION.md", about.PRESERVACAO_TEXTO)


class TestMenuAjuda(unittest.TestCase):
    def test_menu_ajuda_registrado_com_tres_acoes(self) -> None:
        self.assertIn("Ajuda", MENUS)
        self.assertEqual(MENUS[-1], "Ajuda", "Ajuda é o último menu da barra")
        ids = [spec.action_id for spec in menu_actions("Ajuda")]
        self.assertEqual(
            ids, ["ajuda.sobre", "ajuda.preservacao", "ajuda.base_legal"],
        )

    def test_acoes_de_ajuda_nunca_precisam_de_projeto_nem_ficam_bloqueadas(self) -> None:
        for spec in menu_actions("Ajuda"):
            self.assertFalse(spec.needs_project, spec.action_id)
            self.assertIsNone(spec.requires, spec.action_id)
            self.assertTrue(spec.busy_safe, spec.action_id)


@unittest.skipUnless(tk, "sem Tkinter nesta máquina")
class TestDialogos(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self) -> None:
        self.root.destroy()

    def _filhos_texto(self, janela: tk.Toplevel) -> list[tk.Text]:
        encontrados: list[tk.Text] = []
        for widget in janela.winfo_children():
            if isinstance(widget, tk.Text):
                encontrados.append(widget)
            for neto in widget.winfo_children():
                if isinstance(neto, tk.Text):
                    encontrados.append(neto)
        return encontrados

    def test_dialogos_abrem_com_texto_e_paleta_doom(self) -> None:
        from revival_editor.ui.theme import CARD_DARK, TEXT

        for funcao in (about.mostrar_sobre, about.mostrar_preservacao, about.mostrar_lei):
            with self.subTest(dialogo=funcao.__name__):
                janela = funcao(self.root)
                try:
                    self.assertEqual(str(janela.winfo_toplevel().cget("background")).lower(),
                                     "#080403")
                    textos = self._filhos_texto(janela)
                    self.assertEqual(len(textos), 1)
                    corpo = textos[0]
                    self.assertEqual(str(corpo.cget("state")), "disabled")
                    self.assertEqual(str(corpo.cget("background")).lower(), CARD_DARK)
                    self.assertEqual(str(corpo.cget("foreground")).lower(), TEXT)
                    self.assertGreater(len(corpo.get("1.0", "end").strip()), 400)
                finally:
                    janela.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=2)
