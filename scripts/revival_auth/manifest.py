"""Patch do AndroidManifest: RevivalAuthActivity como ÚNICO MAIN/LAUNCHER.

Opera sobre o `AndroidManifest.xml` em TEXTO da árvore decodificada pelo Apktool
3.0.3 (o do APK é AXML binário; o Apktool já faz a conversão nos dois sentidos).

O que muda, e só isso:

1. o `<intent-filter>` de `MAIN`/`LAUNCHER` sai da Activity Unity;
2. entra uma `<activity>` nova, `br.com.revival.auth.RevivalAuthActivity`,
   com esse filtro.

O que NÃO muda: a Activity Unity continua declarada, com `launchMode`,
`configChanges`, `screenOrientation`, os `meta-data` (`unityplayer.UnityActivity`,
`android.notch_support`) e o deep link `mightydoom://` intactos — ela deixa de
ser o launcher, não de existir.

Idempotente: rodar de novo sobre um manifest já patchado não duplica nada.
"""
from __future__ import annotations

import re
from pathlib import Path

ACTIVITY_NAME = "br.com.revival.auth.RevivalAuthActivity"
UNITY_ACTIVITY = "com.google.firebase.MessagingUnityPlayerActivity"

_LAUNCHER_FILTER = re.compile(
    r"[ \t]*<intent-filter>\s*"
    r"<action android:name=\"android\.intent\.action\.MAIN\" />\s*"
    r"<category android:name=\"android\.intent\.category\.LAUNCHER\" />\s*"
    r"</intent-filter>\s*",
    re.MULTILINE,
)


class ManifestError(Exception):
    """Precondição violada. Melhor parar do que gerar um APK sem launcher."""


def _activity_block(indent: str, activity_name: str) -> str:
    return (
        f'{indent}<activity android:configChanges="orientation|screenSize|keyboardHidden" '
        f'android:exported="true" android:name="{activity_name}" '
        f'android:screenOrientation="userPortrait" '
        f'android:theme="@android:style/Theme.Material.NoActionBar">\n'
        f'{indent}    <intent-filter>\n'
        f'{indent}        <action android:name="android.intent.action.MAIN" />\n'
        f'{indent}        <category android:name="android.intent.category.LAUNCHER" />\n'
        f'{indent}    </intent-filter>\n'
        f'{indent}</activity>\n'
    )


def count_launchers(texto: str) -> int:
    return len(_LAUNCHER_FILTER.findall(texto))


def patch_manifest_text(texto: str, *, activity_name: str = ACTIVITY_NAME,
                        unity_activity: str = UNITY_ACTIVITY) -> tuple[str, dict]:
    """Devolve `(manifest novo, relatório)`. Não escreve nada em disco."""
    if unity_activity not in texto:
        raise ManifestError(f"Activity Unity {unity_activity} não está no manifest")

    ja_aplicado = activity_name in texto
    if ja_aplicado:
        # Idempotência: confere o invariante e devolve sem mexer.
        relatorio = _relatorio(texto, activity_name, unity_activity, alterado=False)
        if relatorio["launcher_count"] != 1:
            raise ManifestError(
                f"manifest já patchado mas com {relatorio['launcher_count']} launchers")
        return texto, relatorio

    filtros = _LAUNCHER_FILTER.findall(texto)
    if len(filtros) != 1:
        raise ManifestError(
            f"esperava exatamente 1 intent-filter MAIN/LAUNCHER, achei {len(filtros)}")

    # 1) tira o launcher da Unity
    novo = _LAUNCHER_FILTER.sub("", texto, count=1)
    if UNITY_ACTIVITY not in novo:
        raise ManifestError("a Activity Unity sumiu na remoção do filtro")

    # 2) insere a Activity Revival logo após a abertura de <application>
    m = re.search(r"^([ \t]*)<application\b[^>]*>\n", novo, re.MULTILINE)
    if not m:
        raise ManifestError("tag <application> não encontrada")
    indent = m.group(1) + "    "
    posicao = m.end()
    novo = novo[:posicao] + _activity_block(indent, activity_name) + novo[posicao:]

    relatorio = _relatorio(novo, activity_name, unity_activity, alterado=True)
    if relatorio["launcher_count"] != 1:
        raise ManifestError(
            f"pós-condição falhou: {relatorio['launcher_count']} launchers no manifest")
    if not relatorio["unity_activity_preserved"]:
        raise ManifestError("pós-condição falhou: Activity Unity não preservada")
    if not relatorio["deep_link_preserved"]:
        raise ManifestError("pós-condição falhou: deep link mightydoom:// perdido")
    return novo, relatorio


def _relatorio(texto: str, activity_name: str, unity_activity: str, *, alterado: bool) -> dict:
    return {
        "revival_activity": activity_name,
        "manifest_changed": alterado,
        "launcher_count": count_launchers(texto),
        "revival_is_launcher": bool(re.search(
            re.escape(activity_name) + r"[\s\S]{0,400}?android\.intent\.category\.LAUNCHER", texto)),
        "unity_activity_preserved": unity_activity in texto,
        "unity_activity_is_launcher": bool(re.search(
            re.escape(unity_activity) + r"[\s\S]{0,300}?android\.intent\.category\.LAUNCHER", texto)),
        "deep_link_preserved": 'android:scheme="mightydoom"' in texto,
        "unity_meta_preserved": 'android:name="unityplayer.UnityActivity"' in texto,
    }


def patch_manifest_file(caminho: Path | str, **kwargs) -> dict:
    caminho = Path(caminho)
    if not caminho.is_file():
        raise ManifestError(f"AndroidManifest.xml não existe: {caminho}")
    original = caminho.read_text(encoding="utf-8")
    novo, relatorio = patch_manifest_text(original, **kwargs)
    if novo != original:
        caminho.write_text(novo, encoding="utf-8")
    return relatorio
