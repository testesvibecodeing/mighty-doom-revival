#!/usr/bin/env python3
"""Regressão do serviço de visuais (fase 7 do plano).

O ponto central: `compose` aqui é a MESMA `compose_loading_image` do fluxo de
injeção — importada, nunca copiada. Se alguém duplicar a função, o teste de
identidade abaixo aponta.

Execução: python tests/revival_editor/test_visuals.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from PIL import Image  # noqa: E402

from revival_editor import visuals  # noqa: E402


def _png(destino: Path, tamanho: tuple[int, int] = (64, 64)) -> Path:
    Image.new("RGB", tamanho, "#204060").save(destino, "PNG")
    return destino


class TestFonteUnica(unittest.TestCase):
    def test_compose_e_a_mesma_funcao_do_fluxo_de_injecao(self) -> None:
        """Fase 7: 'mover sem duplicar' — identidade de função, não cópia."""
        from inject_loading_screen import compose_loading_image

        self.assertIs(visuals.compose_loading_image, compose_loading_image)
        self.assertIs(visuals.compose, compose_loading_image)
        self.assertEqual(visuals.TEXTURE_SIZE, (2048, 2048))

    def test_modos_preservados(self) -> None:
        self.assertEqual(
            set(visuals.COMPOSE_MODES), {"image", "text", "image+text"}
        )


class TestCompose(unittest.TestCase):
    def test_texto_compoe_em_2048(self) -> None:
        arte = visuals.compose("text", None, title="REVIVAL")
        self.assertEqual(arte.size, (2048, 2048))

    def test_modo_imagem_exige_fundo(self) -> None:
        with self.assertRaises(ValueError):
            visuals.compose("image", None)

    def test_modo_desconhecido_recusado(self) -> None:
        with self.assertRaises(ValueError):
            visuals.compose("video", None)


class TestOpenSourceImage(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_png_valido_com_avisos_honestos(self) -> None:
        imagem, info = visuals.open_source_image(_png(self.dir / "arte.png"))
        self.assertEqual(info.format, "PNG")
        self.assertEqual((info.width, info.height), (64, 64))
        self.assertFalse(info.icc_profile)
        self.assertIn("ICC", " ".join(info.warnings))
        self.assertIn("resolução baixa", " ".join(info.warnings))
        self.assertEqual(imagem.size, (64, 64))

    def test_formato_nao_suportado_rejeitado(self) -> None:
        destino = self.dir / "arte.bmp"
        Image.new("RGB", (32, 32)).save(destino, "BMP")
        with self.assertRaises(visuals.VisualsError) as cm:
            visuals.open_source_image(destino)
        self.assertIn("BMP", str(cm.exception))
        self.assertIn("PNG", str(cm.exception))

    def test_arquivo_ausente(self) -> None:
        with self.assertRaises(visuals.VisualsError):
            visuals.open_source_image(self.dir / "sumiu.png")

    def test_limite_de_memoria_recusa_antes_de_estourar(self) -> None:
        with mock.patch.object(visuals, "MAX_PIXELS", 1024):
            with self.assertRaises(visuals.VisualsError) as cm:
                visuals.open_source_image(_png(self.dir / "grande.png", (64, 64)))
        self.assertIn("grande demais", str(cm.exception))

    def test_png_com_icc_nao_avisa_cor(self) -> None:
        destino = self.dir / "com-icc.png"
        Image.new("RGB", (2048, 2048), "#102030").save(
            destino, "PNG", icc_profile=b"fake-icc"
        )
        _img, info = visuals.open_source_image(destino)
        self.assertTrue(info.icc_profile)
        self.assertEqual(info.warnings, [], "2048 com ICC não tem o que avisar")


class TestPreviews(unittest.TestCase):
    def setUp(self) -> None:
        self.arte = Image.new("RGB", (2048, 2048), "#304050")

    def test_recortes_nas_proporcoes_comuns(self) -> None:
        recortes = visuals.aspect_crops(self.arte, thumb=96)
        self.assertEqual([r for r, _ in recortes], ["16:9", "19.5:9", "4:3"])
        esperados = {"16:9": 16 / 9, "19.5:9": 195 / 90, "4:3": 4 / 3}
        for rotulo, recorte in recortes:
            self.assertLessEqual(max(recorte.size), 96)
            proporcao = recorte.size[0] / recorte.size[1]
            self.assertAlmostEqual(proporcao, esperados[rotulo], delta=0.05)

    def test_safe_area(self) -> None:
        self.assertEqual(visuals.safe_area_rect((2048, 2048)), (102, 102, 1946, 1946))


class TestExportEInjecao(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_exporta_png_sem_apk(self) -> None:
        arte = Image.new("RGB", (64, 64), "#506070")
        destino = visuals.export_png(arte, self.dir / "aninhado" / "arte.png")
        self.assertTrue(destino.is_file())
        with Image.open(destino) as aberta:
            self.assertEqual(aberta.format, "PNG")
            self.assertEqual(aberta.size, (64, 64))

    def test_injecao_delega_ao_fluxo_validado(self) -> None:
        """A UI não reimplementa injeção: encadeia para `inject_loading_screen`."""
        arte = Image.new("RGB", (64, 64))
        relatorio = {"status": "ok", "apk_out": "x.apk"}
        with mock.patch.object(
            visuals, "inject_loading_screen", return_value=relatorio
        ) as injeta:
            resultado = visuals.inject_loading_into_apk(
                "entra.apk", arte, "sai.apk", log=print, report_path="r.json"
            )
        self.assertEqual(resultado, relatorio)
        chamada = injeta.call_args
        self.assertEqual(chamada.args[0], Path("entra.apk"))
        self.assertEqual(chamada.args[2], Path("sai.apk"))
        self.assertEqual(chamada.kwargs["report_path"], Path("r.json"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
