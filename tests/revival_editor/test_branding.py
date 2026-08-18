#!/usr/bin/env python3
"""Regressão do branding Android seguro (fase 8 do plano).

O fixture é uma árvore decoded sintética (manifest apktool + values com
tradução + mipmap por densidade + adaptive anydpi-v26). As regras testadas
são as da fase 8: label muda no recurso referenciado (nunca no manifest),
ícone só com todos os recursos mapeados, densidades exatas sem distorção,
diff antes de aplicar e campos protegidos intocados.

Execução: python tests/revival_editor/test_branding.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from PIL import Image  # noqa: E402

from revival_editor import branding  # noqa: E402

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.bethsoft.ubu">
    <uses-sdk android:minSdkVersion="24" android:targetSdkVersion="33"/>
    <uses-permission android:name="android.permission.INTERNET"/>
    <uses-permission android:name="android.permission.WAKE_LOCK"/>
    <application
        android:label="@string/app_name"
        android:icon="@mipmap/ic_launcher"
        android:roundIcon="@mipmap/ic_launcher_round">
        <activity android:name="com.bethsoft.ubu.MainActivity" android:exported="true"/>
        <activity android:name="com.bethsoft.ubu.LoginActivity"/>
        <service android:name="com.bethsoft.ubu.PushService"/>
    </application>
</manifest>
"""

STRINGS_EN = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">MIGHTY DOOM</string>
    <string name="outro">não mexe</string>
</resources>
"""

STRINGS_PT = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">MIGHTY DOOM</string>
</resources>
"""

COLORS_BASE = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="splash_bg">#1B1B1B</color>
    <color name="outra">#FFFFFF</color>
    <color name="ic_launcher_background">#000000</color>
</resources>
"""

COLORS_V21 = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="splash_bg">#1B1B1B</color>
</resources>
"""

STYLES = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="SplashTheme">
        <item name="android:windowBackground">@color/splash_bg</item>
    </style>
</resources>
"""

ADAPTIVE = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>
    <background android:drawable="@color/ic_launcher_background"/>
</adaptive-icon>
"""


def arvore_decodificada(destino: Path) -> Path:
    """Árvore decoded sintética no formato que o apktool d produz."""
    res = destino / "res"
    (res / "values").mkdir(parents=True)
    (res / "values-pt").mkdir(parents=True)
    (res / "values" / "strings.xml").write_text(STRINGS_EN, encoding="utf-8")
    (res / "values-pt" / "strings.xml").write_text(STRINGS_PT, encoding="utf-8")
    (res / "values" / "colors.xml").write_text(COLORS_BASE, encoding="utf-8")
    (res / "values" / "styles.xml").write_text(STYLES, encoding="utf-8")
    (res / "values-v21").mkdir(parents=True, exist_ok=True)
    (res / "values-v21" / "colors.xml").write_text(COLORS_V21, encoding="utf-8")

    for nome, densidades in (
        ("ic_launcher", ("mdpi", "xhdpi", "xxxhdpi")),
        ("ic_launcher_round", ("mdpi", "xhdpi")),
        # camada foreground referenciada pelo adaptive-icon: precisa existir
        ("ic_launcher_foreground", ("xxxhdpi",)),
    ):
        for densidade in densidades:
            pasta = res / f"mipmap-{densidade}"
            pasta.mkdir(parents=True, exist_ok=True)
            lado = branding.LAUNCHER_DENSITIES[densidade]
            Image.new("RGBA", (lado, lado), "#336600").save(pasta / f"{nome}.png")
    adaptive_dir = res / "mipmap-anydpi-v26"
    adaptive_dir.mkdir(parents=True)
    (adaptive_dir / "ic_launcher.xml").write_text(ADAPTIVE, encoding="utf-8")

    (destino / "AndroidManifest.xml").write_text(MANIFEST, encoding="utf-8")
    return destino


class TestReadManifest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = arvore_decodificada(Path(self._tmp.name) / "decoded")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_le_fatos_do_manifest(self) -> None:
        info = branding.read_manifest(self.dir)
        self.assertEqual(info.package, "com.bethsoft.ubu")
        self.assertEqual(info.label_raw, "@string/app_name")
        self.assertEqual(info.icon_refs, ["@mipmap/ic_launcher", "@mipmap/ic_launcher_round"])
        self.assertEqual(info.min_sdk, "24")
        self.assertEqual(info.target_sdk, "33")
        self.assertEqual(
            info.permissions,
            ["android.permission.INTERNET", "android.permission.WAKE_LOCK"],
        )
        self.assertEqual(info.exported, ["com.bethsoft.ubu.MainActivity"])
        self.assertEqual(len(info.activities), 2)
        self.assertEqual(info.services, ["com.bethsoft.ubu.PushService"])

    def test_manifest_ausente_recusa_com_instrucao(self) -> None:
        with self.assertRaises(branding.BrandingError) as cm:
            branding.read_manifest(Path(self.dir) / "nao-existe")
        self.assertIn("decode", str(cm.exception))

    def test_resolve_string_em_todos_locales(self) -> None:
        definicoes = branding.resolve_string_resources(self.dir, "app_name")
        self.assertEqual(
            [d.file.parent.name for d in definicoes], ["values", "values-pt"]
        )


class TestPlanLabel(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = arvore_decodificada(Path(self._tmp.name) / "decoded")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_plano_cobre_todos_os_locales(self) -> None:
        plano = branding.plan_label_change(self.dir, "DOOM Revival")
        self.assertEqual(len(plano.label_edits), 2, "values + values-pt")
        for edicao in plano.label_edits:
            self.assertEqual(edicao.old_value, "MIGHTY DOOM")
            self.assertEqual(edicao.new_value, "DOOM Revival")
            self.assertNotEqual(edicao.file.name, "AndroidManifest.xml")

    def test_label_literal_no_manifest_recusado(self) -> None:
        manifesto = self.dir / "AndroidManifest.xml"
        texto = manifesto.read_text(encoding="utf-8").replace(
            '@string/app_name', 'Nome Literal'
        )
        manifesto.write_text(texto, encoding="utf-8")
        with self.assertRaises(branding.BrandingError) as cm:
            branding.plan_label_change(self.dir, "Qualquer")
        self.assertIn("literal", str(cm.exception))
        self.assertIn("AndroidManifest.xml", str(cm.exception))

    def test_recurso_inexistente_recusado(self) -> None:
        manifesto = self.dir / "AndroidManifest.xml"
        texto = manifesto.read_text(encoding="utf-8").replace(
            '@string/app_name', '@string/fantasma'
        )
        manifesto.write_text(texto, encoding="utf-8")
        with self.assertRaises(branding.BrandingError) as cm:
            branding.plan_label_change(self.dir, "Qualquer")
        self.assertIn("fantasma", str(cm.exception))

    def test_valor_vazio_e_excessivo_recusados(self) -> None:
        with self.assertRaises(branding.BrandingError):
            branding.plan_label_change(self.dir, "   ")
        with self.assertRaises(branding.BrandingError) as cm:
            branding.plan_label_change(self.dir, "x" * 51)
        self.assertIn("50", str(cm.exception))

    def test_valor_igual_atual_recusado_sem_trabalho(self) -> None:
        with self.assertRaises(branding.BrandingError) as cm:
            branding.plan_label_change(self.dir, "MIGHTY DOOM")
        self.assertIn("nada a fazer", str(cm.exception))


class TestPlanIcon(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.dir = arvore_decodificada(base / "decoded")
        self.fonte = base / "nova-arte.png"
        Image.new("RGBA", (600, 400), "#cc2222").save(self.fonte, "PNG")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_mapeia_todas_as_densidades_e_adaptive(self) -> None:
        plano = branding.plan_icon_change(self.dir, self.fonte)
        self.assertEqual(len(plano.icon_mappings), 2, "icon + roundIcon")
        principal = plano.icon_mappings[0]
        self.assertEqual(
            sorted(principal.bitmaps), ["mdpi", "xhdpi", "xxxhdpi"]
        )
        self.assertIsNotNone(principal.adaptive_xml)
        self.assertEqual(
            principal.adaptive_layers,
            ["@mipmap/ic_launcher_foreground", "@color/ic_launcher_background"],
        )
        redondo = plano.icon_mappings[1]
        self.assertEqual(sorted(redondo.bitmaps), ["mdpi", "xhdpi"])

    def test_fonte_ausente_recusada(self) -> None:
        with self.assertRaises(branding.BrandingError):
            branding.plan_icon_change(self.dir, self._tmp.name + "/sumiu.png")

    def test_recurso_referenciado_e_ausente_recusa(self) -> None:
        # apaga as densidades do round icon: referência no manifest sem arquivo
        for png in (self.dir / "res").glob("mipmap-*/ic_launcher_round.png"):
            png.unlink()
        with self.assertRaises(branding.BrandingError) as cm:
            branding.plan_icon_change(self.dir, self.fonte)
        self.assertIn("ic_launcher_round", str(cm.exception))
        self.assertIn("recusando", str(cm.exception))


class TestDiffApplyVerify(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.dir = arvore_decodificada(base / "decoded")
        self.manifesto = self.dir / "AndroidManifest.xml"
        self.bytes_manifesto_antes = self.manifesto.read_bytes()
        self.fonte = base / "nova-arte.png"
        Image.new("RGBA", (500, 900), "#22cc88").save(self.fonte, "PNG")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _planos(self):
        label = branding.plan_label_change(self.dir, "DOOM Revival")
        icone = branding.plan_icon_change(self.dir, self.fonte)
        return label, icone

    def test_diff_mostra_antes_e_depois(self) -> None:
        label, _ = self._planos()
        diff = branding.render_diff(label)
        self.assertIn("-<string name=\"app_name\">MIGHTY DOOM</string>", diff)
        self.assertIn("+<string name=\"app_name\">DOOM Revival</string>", diff)
        self.assertIn("strings.xml", diff)

    def test_apply_label_sozinho_nao_toca_manifest(self) -> None:
        label, _ = self._planos()
        resultado = branding.apply_plan(label)
        self.assertEqual(len(resultado["labels_alterados"]), 2)
        self.assertFalse(resultado["manifest_tocado"])
        self.assertEqual(
            self.manifesto.read_bytes(), self.bytes_manifesto_antes,
            "modo normal nunca reescreve o AndroidManifest.xml",
        )
        # o recurso realmente mudou nos dois locales
        for arquivo in (self.dir / "res" / "values" / "strings.xml",
                        self.dir / "res" / "values-pt" / "strings.xml"):
            raiz = ET.parse(arquivo).getroot()
            alvo = [s for s in raiz.findall("string") if s.get("name") == "app_name"]
            self.assertEqual(alvo[0].text, "DOOM Revival")

    def test_apply_icone_gera_densidades_exatas_sem_distorcao(self) -> None:
        _, icone = self._planos()
        resultado = branding.apply_plan(icone)
        # 3 densidades do ic_launcher + 2 do round
        self.assertEqual(len(resultado["icones_gerados"]), 5)
        for mapa in icone.icon_mappings:
            for densidade, arquivo in mapa.bitmaps.items():
                esperado = branding.LAUNCHER_DENSITIES[densidade]
                with Image.open(arquivo) as aberta:
                    self.assertEqual(aberta.size, (esperado, esperado))
                    self.assertEqual(aberta.format, "PNG")
        # adaptive preservado, não regenerado
        adaptive = icone.icon_mappings[0].adaptive_xml
        self.assertIn(
            "ic_launcher_foreground", adaptive.read_text(encoding="utf-8")
        )
        self.assertFalse(
            list((self.dir / "res").glob("**/*.parcial")), "temporário não pode sobrar"
        )

    def test_verify_untouched_apos_apply_completo(self) -> None:
        antes = branding.read_manifest(self.dir)
        label, icone = self._planos()
        branding.apply_plan(label)
        branding.apply_plan(icone)
        self.assertTrue(
            branding.verify_untouched(antes, self.dir),
            "package/sdk/permissões/componentes/exported intocados",
        )
        self.assertEqual(self.manifesto.read_bytes(), self.bytes_manifesto_antes)

    def test_verify_untouched_detecta_violacao(self) -> None:
        antes = branding.read_manifest(self.dir)
        texto = self.manifesto.read_text(encoding="utf-8").replace(
            "com.bethsoft.ubu.PushService", "com.bethsoft.ubu.PushServiceMalicioso"
        )
        self.manifesto.write_text(texto, encoding="utf-8")
        self.assertFalse(branding.verify_untouched(antes, self.dir))

    def test_plano_vazio_recusado_no_apply(self) -> None:
        with self.assertRaises(branding.BrandingError):
            branding.apply_plan(branding.BrandingPlan())

    def test_plano_que_tentaria_editar_manifest_bloqueado(self) -> None:
        from revival_editor.branding import BrandingPlan, EditStep

        plano = BrandingPlan(label_edits=[
            EditStep(file=self.manifesto, name="app_name",
                     old_value="x", new_value="y")
        ])
        with self.assertRaises(branding.BrandingError) as cm:
            branding.apply_plan(plano)
        self.assertIn("manifest", str(cm.exception))


class TestPlanTheme(unittest.TestCase):
    """Cor de tema/splash: somente recurso existente, cobrindo variantes Android."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = arvore_decodificada(Path(self._tmp.name) / "decoded")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_plano_cobra_variacoes_de_versao_android(self) -> None:
        plano = branding.plan_theme_change(self.dir, "splash_bg", "#7B1FA2")
        arquivos = [e.file.parent.name for e in plano.label_edits]
        self.assertEqual(arquivos, ["values", "values-v21"], "base + override v21")
        for edicao in plano.label_edits:
            self.assertEqual(edicao.tag, "color")
            self.assertEqual(edicao.old_value, "#1B1B1B")
            self.assertEqual(edicao.new_value, "#7B1FA2")

    def test_cor_inexistente_recusada_sem_criar_recurso(self) -> None:
        with self.assertRaises(branding.BrandingError) as cm:
            branding.plan_theme_change(self.dir, "nova_cor", "#7B1FA2")
        self.assertIn("não existe", str(cm.exception))
        self.assertIn("não cria recursos", str(cm.exception))

    def test_cor_orfa_nao_referenciada_recusada(self) -> None:
        with self.assertRaises(branding.BrandingError) as cm:
            branding.plan_theme_change(self.dir, "outra", "#7B1FA2")
        self.assertIn("não é referenciada", str(cm.exception))

    def test_cor_malformada_recusada(self) -> None:
        for ruim in ("7B1FA2", "#GGGGGG", "#12345", "vermelho"):
            with self.assertRaises(branding.BrandingError, msg=ruim):
                branding.plan_theme_change(self.dir, "splash_bg", ruim)

    def test_apply_da_cor_edita_colors_sem_tocar_manifest(self) -> None:
        manifesto = self.dir / "AndroidManifest.xml"
        antes_bytes = manifesto.read_bytes()
        plano = branding.plan_theme_change(self.dir, "splash_bg", "#7B1FA2")
        branding.apply_plan(plano)
        raiz = ET.parse(self.dir / "res" / "values-v21" / "colors.xml").getroot()
        alvo = [c for c in raiz.findall("color") if c.get("name") == "splash_bg"]
        self.assertEqual(alvo[0].text, "#7B1FA2")
        self.assertEqual(manifesto.read_bytes(), antes_bytes)


class TestAdvancedSnapshot(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = arvore_decodificada(Path(self._tmp.name) / "decoded")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_snapshot_e_somente_leitura_e_completo(self) -> None:
        snap = branding.advanced_snapshot(self.dir)
        self.assertFalse(snap["writable"], "modo avançado nunca gravável")
        self.assertIn("com.bethsoft.ubu", snap["manifest"])
        self.assertEqual(snap["manifest_info"]["package"], "com.bethsoft.ubu")
        self.assertGreater(snap["resource_total"], 0)
        self.assertLessEqual(len(snap["resources"]), branding.SNAPSHOT_MAX_FILES)
        self.assertEqual(len(snap["resources"]), snap["resource_total"])
        caminhos = [r["path"] for r in snap["resources"]]
        self.assertIn("res/values/strings.xml", caminhos)
        self.assertTrue(all("/" in c and "\\" not in c for c in caminhos))


if __name__ == "__main__":
    unittest.main(verbosity=2)
