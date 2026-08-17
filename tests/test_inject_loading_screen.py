#!/usr/bin/env python3
"""Regressão do injetor de tela de loading.

Cobre a composição dos três modos, a localização do bundle de conteúdo e a
reconstrução cirúrgica do ZIP (membros não-trocados preservados byte a byte,
confirmados por CRC32). O patch real do bundle Unity e a assinatura do APK
dependem de UnityPy/java e são exercidos pelo fluxo de injeção completo.

Execução: python tests/test_inject_loading_screen.py (ou python -m unittest).
"""
from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from inject_loading_screen import (  # noqa: E402
    _copy_zip_info,
    compose_loading_image,
    find_bundle_member,
    mean_channel_diff,
    rebuild_apk,
)


def solid(size, color):
    return Image.new("RGB", size, color)


class ComposeLoadingImageTest(unittest.TestCase):
    def test_image_mode_covers_texture_size(self):
        art = compose_loading_image(mode="image", background=solid((100, 3000), (10, 20, 30)))
        self.assertEqual(art.size, (2048, 2048))
        # cover-fit: a imagem 100x3000 é ampliada para cobrir 2048x2048
        self.assertEqual(art.getpixel((10, 10)), (10, 20, 30))

    def test_image_mode_requires_background(self):
        with self.assertRaises(ValueError):
            compose_loading_image(mode="image", background=None)

    def test_text_mode_uses_background_color(self):
        art = compose_loading_image(mode="text", title="REVIVAL", bg_color="#001122")
        self.assertEqual(art.size, (2048, 2048))

    def test_text_mode_draws_text(self):
        empty = compose_loading_image(mode="text", title="", bg_color="#001122")
        titled = compose_loading_image(mode="text", title="REVIVAL", bg_color="#001122")
        self.assertGreater(mean_channel_diff(empty, titled), 1.0)

    def test_image_text_mode_combines(self):
        art = compose_loading_image(
            mode="image+text", background=solid((2048, 2048), (5, 5, 5)), title="REVIVAL")
        self.assertGreater(mean_channel_diff(art, solid((2048, 2048), (5, 5, 5))), 1.0)

    def test_auto_mode_resolves_by_inputs(self):
        self.assertEqual(
            compose_loading_image(background=solid((64, 64), (1, 2, 3))).getpixel((5, 5)),
            (1, 2, 3))
        with_text = compose_loading_image(
            background=solid((64, 64), (1, 2, 3)), title="REVIVAL")
        self.assertGreater(mean_channel_diff(with_text, solid((2048, 2048), (1, 2, 3))), 1.0)
        only_text = compose_loading_image(title="X")
        self.assertEqual(only_text.size, (2048, 2048))

    def test_unknown_mode_rejected(self):
        with self.assertRaises(ValueError):
            compose_loading_image(mode="banner", background=solid((8, 8), (0, 0, 0)))


class FindBundleMemberTest(unittest.TestCase):
    def test_picks_defaultlocalgroup_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            apk_path = Path(tmp) / "app.apk"
            with zipfile.ZipFile(apk_path, "w") as zf:
                zf.writestr("assets/aa/catalog.json", "{}")
                zf.writestr("assets/aa/Android/otherbundle_abc.bundle", "x" * 10)
                zf.writestr(
                    "assets/aa/Android/defaultlocalgroup_assets_all_hash.bundle", "y" * 50)
            with zipfile.ZipFile(apk_path, "r") as zf:
                self.assertEqual(
                    find_bundle_member(zf),
                    "assets/aa/Android/defaultlocalgroup_assets_all_hash.bundle")

    def test_missing_bundle_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            apk_path = Path(tmp) / "app.apk"
            with zipfile.ZipFile(apk_path, "w") as zf:
                zf.writestr("assets/aa/catalog.json", "{}")
            with zipfile.ZipFile(apk_path, "r") as zf:
                with self.assertRaises(RuntimeError):
                    find_bundle_member(zf)


class RebuildApkTest(unittest.TestCase):
    def _make_apk(self, path: Path):
        with zipfile.ZipFile(path, "w") as zf:
            info = zipfile.ZipInfo("stored.bin", date_time=(2024, 1, 2, 3, 4, 5))
            info.compress_type = zipfile.ZIP_STORED
            zf.writestr(info, b"stored-content")
            zf.writestr("deflated.txt", b"deflated-content" * 100, compress_type=zipfile.ZIP_DEFLATED)
            zf.writestr("assets/aa/Android/b.bundle", b"bundle-bytes")

    def test_replaces_only_requested_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apk_in = root / "in.apk"
            apk_out = root / "out.apk"
            self._make_apk(apk_in)
            replacement = root / "new-bundle"
            replacement.write_bytes(b"patched-bundle-bytes")

            report = rebuild_apk(
                apk_in, apk_out,
                {"assets/aa/Android/b.bundle": replacement},
                log=lambda _msg: None)

            self.assertTrue(report["verified"])
            self.assertEqual(report["replaced_members"], ["assets/aa/Android/b.bundle"])
            with zipfile.ZipFile(apk_out, "r") as zf:
                self.assertEqual(zf.read("assets/aa/Android/b.bundle"), b"patched-bundle-bytes")
                self.assertEqual(zf.read("stored.bin"), b"stored-content")
                self.assertEqual(zf.read("deflated.txt"), b"deflated-content" * 100)
                # compressão preservada por membro
                infos = {i.filename: i.compress_type for i in zf.infolist()}
            self.assertEqual(infos["stored.bin"], zipfile.ZIP_STORED)
            self.assertEqual(infos["deflated.txt"], zipfile.ZIP_DEFLATED)

    def test_no_op_replacement_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            apk_in = root / "in.apk"
            apk_out = root / "out.apk"
            self._make_apk(apk_in)
            same = root / "same-bundle"
            same.write_bytes(b"bundle-bytes")

            # substituição byte a byte igual à original: o gate recusa
            # porque o membro declarado como trocado não mudou
            with self.assertRaises(RuntimeError):
                rebuild_apk(apk_in, apk_out,
                            {"assets/aa/Android/b.bundle": same},
                            log=lambda _msg: None)


class MeanChannelDiffTest(unittest.TestCase):
    def test_identical_images(self):
        a = solid((32, 32), (10, 10, 10))
        self.assertEqual(mean_channel_diff(a, a.copy()), 0.0)

    def test_different_images(self):
        a = solid((32, 32), (0, 0, 0))
        b = solid((32, 32), (255, 255, 255))
        self.assertGreater(mean_channel_diff(a, b), 200.0)


class CopyZipInfoTest(unittest.TestCase):
    def test_preserves_metadata(self):
        info = zipfile.ZipInfo("x.bin", date_time=(2020, 5, 4, 3, 2, 1))
        info.compress_type = zipfile.ZIP_STORED
        info.external_attr = 0o644 << 16
        clone = _copy_zip_info(info)
        self.assertEqual(clone.filename, "x.bin")
        self.assertEqual(clone.date_time, (2020, 5, 4, 3, 2, 1))
        self.assertEqual(clone.compress_type, zipfile.ZIP_STORED)
        self.assertEqual(clone.external_attr, 0o644 << 16)


if __name__ == "__main__":
    unittest.main()
