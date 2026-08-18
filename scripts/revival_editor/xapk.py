"""Importação de `.xapk` como fluxo separado (fase 4 do plano).

O plano é explícito: *"Tratar `.xapk` como importação separada: localizar o
base APK e splits, sem assumir que é um APK monolítico"* — e o fluxo principal
só aceita `.apk`.

Um XAPK é um ZIP com `manifest.json` + vários APKs (base + splits de ABI,
densidade e idioma) + possíveis OBBs. Duas regras daqui:

- **tudo é provado do manifest.json**, nunca deduzido do nome de arquivo: o
  base APK é o entry com `id == "base"`; splits e OBBs vêm das listas;
- **extrair só o base APK**, para o diretório do projeto (`work/` é
  gitignored — o plano proíbe copiar APK para diretório versionado), via
  temporário + `promote_atomic`. Splits **não** são mesclados: mesclagem não
  é comprovada nesta fase, então a presença de splits é reportada como
  A VERIFICAR, nunca silenciada.
"""
from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .runner import promote_atomic

__all__ = ["XapkError", "XapkInfo", "inspect_xapk", "extract_base_apk"]


class XapkError(Exception):
    """XAPK rejeitado — mensagem pronta para a UI."""


@dataclass
class XapkInfo:
    """Fatos do XAPK medidos do manifest.json — sem byte proprietário."""

    path: str
    package_name: str | None = None
    version_name: str | None = None
    version_code: str | None = None
    xapk_version: int | None = None
    base_apk: str | None = None
    splits: list[str] = field(default_factory=list)
    obbs: list[str] = field(default_factory=list)

    @property
    def has_splits(self) -> bool:
        return bool(self.splits)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "package_name": self.package_name,
            "version_name": self.version_name,
            "version_code": self.version_code,
            "xapk_version": self.xapk_version,
            "base_apk": self.base_apk,
            "splits": self.splits,
            "obbs": self.obbs,
            "has_splits": self.has_splits,
        }


def _ler_manifest(zf: zipfile.ZipFile) -> dict[str, Any]:
    try:
        with zf.open("manifest.json") as stream:
            dados = json.loads(stream.read().decode("utf-8"))
    except KeyError as exc:
        raise XapkError("XAPK sem manifest.json — não é um XAPK válido") from exc
    except (OSError, ValueError) as exc:
        raise XapkError(f"manifest.json ilegível: {exc}") from exc
    if not isinstance(dados, dict):
        raise XapkError("manifest.json não é um objeto JSON")
    return dados


def _localizar_base(
    manifest: dict[str, Any], nomes: set[str]
) -> tuple[str | None, list[str]]:
    """Devolve (base, splits) provados do manifest — nunca do nome de arquivo."""
    entradas = [
        str(e.get("file") or "")
        for e in (manifest.get("split_apks") or [])
        if isinstance(e, dict)
    ]
    ids = [
        str(e.get("id") or "")
        for e in (manifest.get("split_apks") or [])
        if isinstance(e, dict)
    ]

    base: str | None = None
    splits: list[str] = []
    for arquivo, identificador in zip(entradas, ids):
        if not arquivo:
            continue
        if arquivo not in nomes:
            raise XapkError(f"manifest lista {arquivo!r}, mas o ZIP não contém esse arquivo")
        if identificador == "base" or arquivo == "base.apk":
            base = arquivo
        else:
            splits.append(arquivo)

    if base is None and len(entradas) == 1 and entradas[0] in nomes:
        # manifest de entrada única sem id "base": o único APK é o base.
        base = entradas[0]
    return base, splits


def inspect_xapk(xapk: Path | str) -> XapkInfo:
    """Lê o manifest.json do XAPK e localiza base/splits/OBBs."""
    caminho = Path(xapk)
    if not caminho.is_file():
        raise XapkError(f"XAPK não encontrado: {caminho}")
    try:
        with zipfile.ZipFile(caminho, "r") as zf:
            nomes = set(zf.namelist())
            manifest = _ler_manifest(zf)
    except zipfile.BadZipFile as exc:
        raise XapkError(f"não é um ZIP/XAPK válido: {exc}") from exc

    base, splits = _localizar_base(manifest, nomes)
    if base is None:
        raise XapkError(
            "manifest.json não identifica um base APK (nenhum id 'base'). "
            "Recuse a importação em vez de adivinhar."
        )

    obbs = [
        str(e.get("file") or "")
        for e in (manifest.get("expansions") or [])
        if isinstance(e, dict) and e.get("file")
    ]

    return XapkInfo(
        path=str(caminho),
        package_name=manifest.get("package_name"),
        version_name=manifest.get("version_name"),
        version_code=str(manifest.get("version_code")) if manifest.get("version_code") else None,
        xapk_version=manifest.get("xapk_version"),
        base_apk=base,
        splits=splits,
        obbs=obbs,
    )


def extract_base_apk(info: XapkInfo, destino_dir: Path | str) -> Path:
    """Extrai **somente** o base APK do XAPK para `destino_dir`.

    Extração via temporário + `promote_atomic`: um cancelamento no meio não
    deixa um APK parcial com cara de final. Splits e OBBs ficam no XAPK — a
    decisão de lidar com eles é do usuário, marcada A VERIFICAR pela UI.
    """
    destino_dir = Path(destino_dir)
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / "base.apk"
    temporario = destino.with_name(destino.name + ".parcial")
    origem = Path(info.path)
    try:
        with zipfile.ZipFile(origem, "r") as zf:
            with zf.open(info.base_apk or "") as leitor, open(temporario, "wb") as escritor:
                while True:
                    bloco = leitor.read(1 << 20)
                    if not bloco:
                        break
                    escritor.write(bloco)
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        if temporario.exists():
            temporario.unlink()
        raise XapkError(f"falha ao extrair o base APK: {exc}") from exc
    return promote_atomic(temporario, destino)
