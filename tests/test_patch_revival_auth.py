#!/usr/bin/env python3
"""Testes da injeção da RevivalAuthActivity (scripts/patch_revival_auth.py).

Sem APK proprietário e sem compilar Java: os fixtures são um `AndroidManifest.xml`
sintético com a mesma forma do real e um ZIP montado no teste. A compilação de
verdade (`javac` + `d8`) é exercitada pela detecção de toolchain, que é pulada
quando a máquina não tem JDK/SDK.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import patch_revival_auth as auth  # noqa: E402
from revival_auth.build import BuildError, render_source  # noqa: E402
from revival_auth.manifest import (  # noqa: E402
    ACTIVITY_NAME, UNITY_ACTIVITY, ManifestError, count_launchers, patch_manifest_text,
)

MANIFEST = '''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.bethsoft.ubu">
    <uses-permission android:name="android.permission.INTERNET" />
    <application android:label="@string/app_name" android:networkSecurityConfig="@xml/network_security_config">
        <activity android:configChanges="orientation" android:exported="true" android:launchMode="singleTask" android:name="com.google.firebase.MessagingUnityPlayerActivity" android:screenOrientation="userPortrait">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
            <intent-filter>
                <action android:name="android.intent.action.VIEW" />
                <category android:name="android.intent.category.DEFAULT" />
                <category android:name="android.intent.category.BROWSABLE" />
                <data android:scheme="mightydoom" />
            </intent-filter>
            <meta-data android:name="unityplayer.UnityActivity" android:value="true" />
        </activity>
    </application>
</manifest>
'''


def arvore_sintetica(base: Path) -> Path:
    decoded = base / "decoded"
    (decoded / "res" / "xml").mkdir(parents=True)
    (decoded / "smali").mkdir()
    (decoded / "AndroidManifest.xml").write_text(MANIFEST, encoding="utf-8")
    return decoded


class TestManifest(unittest.TestCase):
    def test_launcher_migra_e_unity_fica(self):
        novo, rel = patch_manifest_text(MANIFEST)
        self.assertEqual(rel["launcher_count"], 1, "um único launcher, sempre")
        self.assertTrue(rel["revival_is_launcher"])
        self.assertFalse(rel["unity_activity_is_launcher"])
        self.assertTrue(rel["unity_activity_preserved"])
        self.assertIn(UNITY_ACTIVITY, novo)
        self.assertIn(ACTIVITY_NAME, novo)

    def test_deep_link_e_metadados_da_unity_preservados(self):
        novo, rel = patch_manifest_text(MANIFEST)
        self.assertTrue(rel["deep_link_preserved"])
        self.assertTrue(rel["unity_meta_preserved"])
        self.assertIn('android:scheme="mightydoom"', novo)
        self.assertIn('android:name="unityplayer.UnityActivity"', novo)
        self.assertIn('android:launchMode="singleTask"', novo, "atributos da Unity intactos")

    def test_idempotente(self):
        uma, _ = patch_manifest_text(MANIFEST)
        duas, rel = patch_manifest_text(uma)
        self.assertEqual(uma, duas, "segunda passada não muda nada")
        self.assertFalse(rel["manifest_changed"])
        self.assertEqual(count_launchers(duas), 1, "nunca duplica launcher")

    def test_sem_activity_unity_recusa(self):
        with self.assertRaises(ManifestError):
            patch_manifest_text(MANIFEST.replace(UNITY_ACTIVITY, "outra.Activity"))

    def test_dois_launchers_recusa(self):
        duplicado = MANIFEST.replace("</application>", MANIFEST[
            MANIFEST.index("<activity"):MANIFEST.index("</activity>") + len("</activity>")]
            + "\n    </application>")
        with self.assertRaises(ManifestError):
            patch_manifest_text(duplicado)

    def test_nenhum_launcher_recusa(self):
        sem = MANIFEST.replace("android.intent.category.LAUNCHER", "android.intent.category.HOME")
        with self.assertRaises(ManifestError):
            patch_manifest_text(sem)


class TestFonteDaActivity(unittest.TestCase):
    def test_marcadores_substituidos(self):
        fonte = render_source(base_url="https://exemplo.br/collections/doom", api_version="24.0.0",
                              client_version="1.13.1", unity_activity=UNITY_ACTIVITY)
        self.assertNotIn("@@REVIVAL_", fonte, "nenhum marcador sobra")
        self.assertIn('"https://exemplo.br/collections/doom"', fonte)
        self.assertIn(f'"{UNITY_ACTIVITY}"', fonte)

    def test_base_url_invalida_recusada(self):
        for ruim in ("exemplo.br", "ftp://exemplo.br", ""):
            with self.subTest(ruim):
                with self.assertRaises(BuildError):
                    render_source(base_url=ruim, api_version="24.0.0",
                                  client_version="1.13.1", unity_activity=UNITY_ACTIVITY)

    def test_valor_com_aspas_nao_vira_literal_java(self):
        # Impede quebrar a fonte (ou injetar código) por um valor de config.
        with self.assertRaises(BuildError):
            render_source(base_url='https://a.br"; System.exit(0);//', api_version="24.0.0",
                          client_version="1.13.1", unity_activity=UNITY_ACTIVITY)

    def test_barra_final_removida(self):
        fonte = render_source(base_url="https://exemplo.br/collections/doom/", api_version="24.0.0",
                              client_version="1.13.1", unity_activity=UNITY_ACTIVITY)
        self.assertIn('"https://exemplo.br/collections/doom"', fonte)


class TestPrecondicoes(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.decoded = arvore_sintetica(self.base)

    def test_arvore_valida_passa(self):
        pre = auth.check_preconditions(self.decoded)
        self.assertEqual(pre["package"], "com.bethsoft.ubu")
        self.assertFalse(pre["already_patched"])
        self.assertEqual(pre["launcher_count"], 1)

    def test_pacote_diferente_recusa(self):
        manifesto = self.decoded / "AndroidManifest.xml"
        manifesto.write_text(MANIFEST.replace("com.bethsoft.ubu", "com.outro.jogo"), encoding="utf-8")
        with self.assertRaises(auth.AuthPatchError):
            auth.check_preconditions(self.decoded)

    def test_arvore_sem_manifest_recusa(self):
        (self.decoded / "AndroidManifest.xml").unlink()
        with self.assertRaises(auth.AuthPatchError):
            auth.check_preconditions(self.decoded)

    def test_analyze_nao_altera_a_arvore(self):
        antes = (self.decoded / "AndroidManifest.xml").read_text(encoding="utf-8")
        rel = auth.apply(decoded=self.decoded, base_url="https://exemplo.br/collections/doom",
                         api_version="24.0.0", client_version="1.13.1", analyze=True)
        self.assertFalse(rel["manifest_changed"])
        self.assertIsNone(rel["dex_added"])
        self.assertEqual((self.decoded / "AndroidManifest.xml").read_text(encoding="utf-8"), antes)


class TestInjecaoDeDex(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.dex = self.base / "classes-revival.dex"
        # "dex" sintético: o detector procura o nome da classe na tabela de strings.
        self.dex.write_bytes(b"dex\n035\x00" + auth.ACTIVITY_CLASS.replace(".", "/").encode() + b"\x00")
        self.apk = self.base / "entrada.apk"
        # O manifest do APK montado já é o PATCHADO: é esse o estado real na
        # hora da injeção (o Apktool constrói a partir da árvore já alterada).
        patchado, _ = patch_manifest_text(MANIFEST)
        with zipfile.ZipFile(self.apk, "w") as z:
            z.writestr("classes.dex", b"dex\n035\x00original")
            z.writestr("classes2.dex", b"dex\n035\x00original2")
            z.writestr("AndroidManifest.xml", patchado.encode("utf-16-le"))
        self.apk_sem_patch = self.base / "sem-patch.apk"
        with zipfile.ZipFile(self.apk_sem_patch, "w") as z:
            z.writestr("classes.dex", b"dex\n035\x00original")
            z.writestr("AndroidManifest.xml", MANIFEST.encode("utf-16-le"))

    def test_entra_como_proximo_classesN(self):
        saida = self.base / "saida.apk"
        rel = auth.inject_dex(self.apk, self.dex, apk_out=saida)
        self.assertEqual(rel["dex_entry"], "classes3.dex")
        self.assertTrue(rel["injected"])
        with zipfile.ZipFile(saida) as z:
            self.assertEqual(sorted(n for n in z.namelist() if n.endswith(".dex")),
                             ["classes.dex", "classes2.dex", "classes3.dex"])
            self.assertEqual(z.read("classes.dex"), b"dex\n035\x00original",
                             "os dex originais não são tocados")

    def test_idempotente(self):
        primeira = self.base / "a.apk"
        auth.inject_dex(self.apk, self.dex, apk_out=primeira)
        segunda = self.base / "b.apk"
        rel = auth.inject_dex(primeira, self.dex, apk_out=segunda)
        self.assertFalse(rel["injected"], "não duplica o dex")
        self.assertEqual(rel["dex_entry"], "classes3.dex")
        with zipfile.ZipFile(segunda) as z:
            self.assertEqual(len([n for n in z.namelist() if n.endswith(".dex")]), 3)

    def test_dex_ausente_falha(self):
        with self.assertRaises(auth.AuthPatchError):
            auth.inject_dex(self.apk, self.base / "nao-existe.dex", apk_out=self.base / "x.apk")

    def test_verify_apk_confere_activity_e_unity(self):
        saida = self.base / "verificado.apk"
        auth.inject_dex(self.apk, self.dex, apk_out=saida)
        v = auth.verify_apk(saida)
        self.assertEqual(v["activity_dex"], "classes3.dex")
        self.assertTrue(v["unity_activity_present"])
        self.assertTrue(v["revival_activity_present"])
        self.assertTrue(v["verified"])

    def test_verify_apk_reprova_apk_sem_activity(self):
        v = auth.verify_apk(self.apk_sem_patch)
        self.assertIsNone(v["activity_dex"], "sem o dex da Activity")
        self.assertFalse(v["revival_activity_present"], "sem a Activity no manifest")
        self.assertFalse(v["verified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
