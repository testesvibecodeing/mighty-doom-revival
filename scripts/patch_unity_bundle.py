#!/usr/bin/env python3
"""Safely rewrite preserved Mighty DOOM endpoint strings inside Unity bundles.

The module rewrites only serialized string values containing one of the known
official hosts. It never performs variable-length raw binary replacement.
UnityPy is loaded lazily so the exact-length patch path keeps working even when
the optional dependency is absent.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Any

KNOWN_HOSTS = (
    "slayersclub.bethesda.net",
    "game.9095be396f3547555fe1039cbc894c88.net",
    "international.gear.bethesda.net",
)
UNITYPY_VERSION = "1.25.3"


class UnityPyUnavailable(RuntimeError):
    pass


def _load_unitypy():
    try:
        import UnityPy  # type: ignore
    except ImportError as exc:
        raise UnityPyUnavailable(
            f"UnityPy {UNITYPY_VERSION} não está instalado. Execute scripts\\setup-patcher-tools.bat."
        ) from exc
    version = getattr(UnityPy, "__version__", None)
    if version and version != UNITYPY_VERSION:
        raise UnityPyUnavailable(
            f"Versão UnityPy incompatível: {version}; esperado {UNITYPY_VERSION}."
        )
    return UnityPy


def replace_known_hosts(value: Any, target_host: str) -> tuple[Any, int]:
    """Recursively replace official hostnames in serialized typetree values."""
    if isinstance(value, str):
        changed = value
        count = 0
        for host in KNOWN_HOSTS:
            occurrences = changed.count(host)
            if occurrences:
                changed = changed.replace(host, target_host)
                count += occurrences
        return changed, count

    if isinstance(value, list):
        output = []
        total = 0
        for item in value:
            patched, count = replace_known_hosts(item, target_host)
            output.append(patched)
            total += count
        return output, total

    if isinstance(value, tuple):
        output = []
        total = 0
        for item in value:
            patched, count = replace_known_hosts(item, target_host)
            output.append(patched)
            total += count
        return tuple(output), total

    if isinstance(value, dict):
        output = {}
        total = 0
        for key, item in value.items():
            patched, count = replace_known_hosts(item, target_host)
            output[key] = patched
            total += count
        return output, total

    return value, 0


def _object_name(obj: Any, tree: Any | None = None) -> str:
    if isinstance(tree, dict):
        name = tree.get("m_Name")
        if isinstance(name, str):
            return name
    try:
        name = obj.peek_name()
        return name if isinstance(name, str) else ""
    except Exception:
        return ""


def _raw_host_counts(obj: Any) -> dict[str, int]:
    """Count known hosts in an object's raw payload without modifying it."""
    try:
        data = bytes(obj.get_raw_data())
    except Exception:
        return {}
    counts: dict[str, int] = {}
    for host in KNOWN_HOSTS:
        count = data.count(host.encode("ascii"))
        if count:
            counts[host] = count
    return counts


def inspect_environment(env: Any) -> dict[str, Any]:
    """Map serialized and raw endpoint candidates without exporting payloads."""
    serializable: list[dict[str, Any]] = []
    raw_only: list[dict[str, Any]] = []

    for obj in env.objects:
        type_name = getattr(getattr(obj, "type", None), "name", "")
        path_id = getattr(obj, "path_id", None)
        serialized_count = 0
        tree: Any | None = None

        if type_name == "TextAsset":
            try:
                asset = obj.parse_as_object()
                script = getattr(asset, "m_Script", "")
                if isinstance(script, str):
                    serialized_count = sum(script.count(host) for host in KNOWN_HOSTS)
                name = getattr(asset, "m_Name", "")
            except Exception:
                name = ""
        else:
            try:
                tree = obj.parse_as_dict()
                serialized = json.dumps(tree, ensure_ascii=False, default=str)
                serialized_count = sum(serialized.count(host) for host in KNOWN_HOSTS)
            except Exception:
                tree = None
            name = _object_name(obj, tree)

        raw_counts = _raw_host_counts(obj)
        raw_count = sum(raw_counts.values())
        entry = {
            "type": type_name,
            "name": name,
            "path_id": path_id,
            "serialized_references": serialized_count,
            "raw_references": raw_count,
            "raw_hosts": raw_counts,
        }
        if serialized_count:
            serializable.append(entry)
        elif raw_count:
            raw_only.append(entry)

    return {
        "serializable": serializable,
        "raw_only": raw_only,
        "serializable_references": sum(x["serialized_references"] for x in serializable),
        "raw_only_references": sum(x["raw_references"] for x in raw_only),
    }


def _patch_environment(env: Any, target_host: str) -> list[dict[str, Any]]:
    """Patch every Unity object whose serializable string fields contain a known host.

    UnityPy documents ``parse_as_dict``/``patch`` as the generic editing path
    for Unity objects, so restricting this to MonoBehaviour would miss valid
    endpoint holders such as custom serialized configuration objects.
    """
    changes: list[dict[str, Any]] = []

    for obj in env.objects:
        type_name = getattr(getattr(obj, "type", None), "name", "")

        if type_name == "TextAsset":
            try:
                asset = obj.parse_as_object()
                original = asset.m_Script
                patched, count = replace_known_hosts(original, target_host)
                if count:
                    asset.m_Script = patched
                    obj.patch(asset)
                    changes.append({
                        "type": "TextAsset",
                        "name": getattr(asset, "m_Name", ""),
                        "path_id": getattr(obj, "path_id", None),
                        "replacements": count,
                    })
            except Exception:
                continue
            continue

        try:
            tree = obj.parse_as_dict()
            patched, count = replace_known_hosts(tree, target_host)
            if count:
                obj.patch(patched)
                changes.append({
                    "type": type_name,
                    "name": _object_name(obj, tree),
                    "path_id": getattr(obj, "path_id", None),
                    "replacements": count,
                })
        except Exception:
            # Objects without a usable typetree are recorded by inspect_environment
            # as raw-only candidates rather than being modified blindly.
            continue

    return changes


def _scan_environment(env: Any, target_host: str) -> dict[str, int]:
    counts = {"official": 0, "target": 0}
    for obj in env.objects:
        type_name = getattr(getattr(obj, "type", None), "name", "")
        if type_name == "TextAsset":
            try:
                text = obj.parse_as_object().m_Script
            except Exception:
                continue
            if not isinstance(text, str):
                continue
            counts["target"] += text.count(target_host)
            counts["official"] += sum(text.count(host) for host in KNOWN_HOSTS)
            continue

        try:
            tree = obj.parse_as_dict()
        except Exception:
            continue
        serialized = json.dumps(tree, ensure_ascii=False, default=str)
        counts["target"] += serialized.count(target_host)
        counts["official"] += sum(serialized.count(host) for host in KNOWN_HOSTS)
    return counts


def patch_bundle(path: Path, target_host: str) -> dict[str, Any]:
    """Patch one Unity bundle atomically and verify it can be reparsed."""
    UnityPy = _load_unitypy()
    path = path.resolve()
    # Carrega dos BYTES: UnityPy.load com caminho mantém handle aberto no
    # original e o os.replace(tmp -> original) falha no Windows (WinError 5
    # "acesso negado" — replace sobre arquivo aberto; no Linux passa).
    env = UnityPy.load(path.read_bytes())
    inspection = inspect_environment(env)
    changes = _patch_environment(env, target_host)
    if not changes:
        return {
            "path": str(path),
            "changed": False,
            "objects": [],
            "replacements": 0,
            "verified": False,
            "inspection": inspection,
        }

    payload = env.file.save()
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".revival.tmp", dir=str(path.parent))
    os.close(fd)
    temp = Path(temp_name)
    try:
        temp.write_bytes(payload)
        # Verificação a partir dos BYTES: UnityPy.load com caminho mantém
        # handle aberto no tmp e o replace abaixo estoura WinError 32 no
        # Windows ("arquivo já está sendo usado por outro processo").
        check = UnityPy.load(payload)
        verification = _scan_environment(check, target_host)
        if verification["target"] <= 0:
            raise RuntimeError("bundle reserializado não contém o hostname alvo em objetos verificáveis")
        if verification["official"] > 0:
            raise RuntimeError("bundle reserializado ainda contém hostname oficial em objetos serializáveis")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()

    return {
        "path": str(path),
        "changed": True,
        "objects": changes,
        "replacements": sum(int(x["replacements"]) for x in changes),
        "verified": True,
        "verification": verification,
        "inspection": inspection,
    }


def zero_catalog_crc(catalog_path: Path, bundle_path: Path) -> dict[str, Any]:
    """Zerar o ``m_Crc`` do bundle re-salvo no catalog.json do Addressables.

    O CRC gravado no catálogo se refere ao bundle ORIGINAL do build oficial.
    Qualquer reserialização muda o CRC e a Unity recusa carregar o bundle em
    runtime ("CRC Mismatch ... Will not load AssetBundle"), derrubando o load
    de cena com um ``RemoteProviderException`` enganoso. A Unity só valida o
    CRC quando o valor passado é não-zero, então zerar o campo no
    ``AssetBundleRequestOptions`` daquele bundle (identificado pelo hash
    presente no nome do arquivo) desativa a checagem. Os objetos do catálogo
    vivem serializados como JSON UTF-16LE dentro de ``m_ExtraDataString``
    (base64); a substituição preserva o comprimento em bytes para não
    deslocar os offsets do stream apontados pelas entradas do catálogo.
    """
    name = bundle_path.name
    stem = name[:-len(".bundle")] if name.endswith(".bundle") else name
    bundle_hash = stem.rsplit("_", 1)[-1].lower()
    if len(bundle_hash) != 32 or any(c not in "0123456789abcdef" for c in bundle_hash):
        return {
            "path": str(catalog_path),
            "bundle": name,
            "zeroed": False,
            "error": f"não foi possível extrair o hash 32-hex do nome do bundle: {name}",
        }

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    extra_b64 = catalog.get("m_ExtraDataString")
    if not extra_b64:
        return {
            "path": str(catalog_path),
            "bundle": name,
            "zeroed": False,
            "error": "catalog.json sem m_ExtraDataString",
        }
    raw = base64.b64decode(extra_b64)

    def u16(text: str) -> bytes:
        return text.encode("utf-16-le")

    hash_at = raw.find(u16(f'"m_Hash":"{bundle_hash}"'))
    if hash_at == -1:
        return {
            "path": str(catalog_path),
            "bundle": name,
            "zeroed": False,
            "error": f"m_Hash {bundle_hash} não encontrado no catálogo",
        }
    field_at = raw.find(u16('"m_Crc":'), hash_at)
    if field_at == -1:
        return {
            "path": str(catalog_path),
            "bundle": name,
            "zeroed": False,
            "error": "m_Crc não encontrado após o m_Hash do bundle",
        }

    prefix = u16('"m_Crc":')
    digits_at = field_at + len(prefix)
    digits_end = digits_at
    digits: list[str] = []
    while digits_end + 1 < len(raw):
        char = raw[digits_end:digits_end + 2].decode("utf-16-le", errors="ignore")
        if not char.isdigit():
            break
        digits.append(char)
        digits_end += 2
    old_digits = "".join(digits)
    if not old_digits:
        return {
            "path": str(catalog_path),
            "bundle": name,
            "zeroed": False,
            "error": "valor numérico do m_Crc não encontrado",
        }
    if old_digits == "0":
        return {"path": str(catalog_path), "bundle": name, "zeroed": False, "already_zero": True}

    # '0' + espaços mantém o JSON válido (espaço em branco é permitido entre
    # tokens) e o comprimento em bytes idêntico aos dígitos originais.
    replacement = u16("0" + " " * (len(old_digits) - 1))
    if len(replacement) != digits_end - digits_at:
        return {
            "path": str(catalog_path),
            "bundle": name,
            "zeroed": False,
            "error": "substituição de mesmo comprimento impossível",
        }
    patched = raw[:digits_at] + replacement + raw[digits_end:]
    catalog["m_ExtraDataString"] = base64.b64encode(patched).decode("ascii")
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="",
    )
    return {
        "path": str(catalog_path),
        "bundle": name,
        "hash": bundle_hash,
        "crc_before": int(old_digits),
        "zeroed": True,
    }


def inspect_bundle(path: Path) -> dict[str, Any]:
    UnityPy = _load_unitypy()
    path = path.resolve()
    env = UnityPy.load(str(path))
    return {"path": str(path), **inspect_environment(env)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--server")
    parser.add_argument("--inspect", action="store_true", help="Mapeia candidatos sem alterar o bundle")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not args.inspect and not args.server:
        parser.error("--server é obrigatório fora do modo --inspect")

    try:
        if args.inspect:
            result = inspect_bundle(Path(args.bundle))
        else:
            result = patch_bundle(Path(args.bundle), args.server)
    except UnityPyUnavailable as exc:
        print(str(exc))
        return 5
    except Exception as exc:
        print(f"Falha no processamento bundle-aware: {exc}")
        return 4

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result)
    if args.inspect:
        return 0
    return 0 if result["changed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
