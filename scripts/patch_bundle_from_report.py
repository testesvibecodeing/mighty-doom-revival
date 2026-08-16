#!/usr/bin/env python3
"""Continue a blocked APK patch using safe Unity object reserialization."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from patch_apk import normalize_host
from patch_unity_bundle import UnityPyUnavailable, patch_bundle, zero_catalog_crc
from patch_unity_raw_strings import RawStringPatchError, patch_raw_bundle


def _candidate_summary(results: list[dict]) -> dict:
    serializable = []
    raw_only = []
    for result in results:
        inspection = result.get("inspection") or {}
        rel = result.get("path")
        for candidate in inspection.get("serializable", []):
            serializable.append({"bundle": rel, **candidate})
        for candidate in inspection.get("raw_only", []):
            raw_only.append({"bundle": rel, **candidate})
    return {
        "serializable": serializable,
        "raw_only": raw_only,
        "serializable_references": sum(int(x.get("serialized_references", 0)) for x in serializable),
        "raw_only_references": sum(int(x.get("raw_references", 0)) for x in raw_only),
    }


def _all_official_raw_refs(path: Path) -> int:
    """Count official hosts after all patch stages without exporting payloads."""
    from patch_unity_bundle import KNOWN_HOSTS, _load_unitypy

    UnityPy = _load_unitypy()
    env = UnityPy.load(str(path))
    total = 0
    for obj in env.objects:
        try:
            raw = bytes(obj.get_raw_data())
        except Exception:
            continue
        total += sum(raw.count(host.encode("ascii")) for host in KNOWN_HOSTS)
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decoded", required=True)
    parser.add_argument("--server", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument(
        "--sweep-all-bundles",
        action="store_true",
        help=(
            "Varre TODOS os .bundle de assets/aa, não apenas os arquivos com hit "
            "ASCII cru no relatório. Necessário porque blocos LZ4 fragmentam o "
            "hostname oficial (ex.: 'game.<hash>.net' dentro do bundle de cenas) "
            "sem produzir uma ocorrência contígua escaneável em bytes brutos."
        ),
    )
    args = parser.parse_args()

    decoded = Path(args.decoded).resolve()
    report_path = Path(args.report).resolve()
    if not decoded.is_dir() or not report_path.is_file():
        print("ERRO: diretório decoded ou relatório inexistente.", file=sys.stderr)
        return 2

    try:
        host = normalize_host(args.server)
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"ERRO ao ler parâmetros do bundle-aware patch: {exc}", file=sys.stderr)
        return 2

    paths = {str(hit.get("path", "")) for hit in report.get("known_host_hits", []) if hit.get("path")}
    addressables = decoded / "assets" / "aa"
    if args.sweep_all_bundles and addressables.is_dir():
        for bundle in sorted(addressables.rglob("*.bundle")):
            paths.add(str(bundle.relative_to(decoded)))
    paths = sorted(paths)
    results = []
    try:
        for rel in paths:
            candidate = (decoded / rel).resolve()
            try:
                candidate.relative_to(decoded)
            except ValueError:
                print(f"ERRO: caminho fora do decoded recusado: {rel}", file=sys.stderr)
                return 2
            if not candidate.is_file():
                continue

            # Stage 1: prefer normal Unity typetree/object patching.
            result = patch_bundle(candidate, host)
            result["path"] = rel

            # A reserialized bundle no longer matches the build-time CRC kept
            # in the Addressables catalog; Unity refuses to load it at runtime
            # ("CRC Mismatch"). Zero the catalog's m_Crc for this bundle so
            # the engine skips validation. A failure here means a patched
            # bundle that cannot load, so it must block the pipeline.
            if result.get("changed"):
                catalog = decoded / "assets" / "aa" / "catalog.json"
                if not catalog.is_file():
                    raise RawStringPatchError(
                        f"{rel}: bundle foi reserializado mas assets/aa/catalog.json não existe "
                        "para zerar o m_Crc; o APK carregado rejeitaria o bundle por CRC."
                    )
                crc_result = zero_catalog_crc(catalog, candidate)
                result["catalog_crc"] = crc_result
                if not crc_result.get("zeroed") and not crc_result.get("already_zero"):
                    raise RawStringPatchError(
                        f"{rel}: falha ao zerar o m_Crc no catalog.json "
                        f"({crc_result.get('error', 'erro desconhecido')}); "
                        "a Unity recusaria carregar o bundle reserializado."
                    )

            # Stage 2: if official host bytes remain, only patch them when they
            # are provably Unity serialized UTF-8 strings with length/alignment.
            remaining_raw = _all_official_raw_refs(candidate)
            if remaining_raw:
                raw_result = patch_raw_bundle(candidate, host)
                raw_result["path"] = rel
                result["raw_string_patch"] = raw_result
                result["raw_string_replacements"] = int(raw_result.get("replacements", 0))
                result["changed"] = bool(result.get("changed") or raw_result.get("changed"))
                result["verified"] = bool(result.get("verified") or raw_result.get("verified"))
                result["replacements"] = int(result.get("replacements", 0)) + int(raw_result.get("replacements", 0))

            final_raw = _all_official_raw_refs(candidate)
            result["remaining_official_raw_references"] = final_raw
            if final_raw:
                raise RawStringPatchError(
                    f"{rel}: {final_raw} referência(s) oficial(is) permaneceram após typetree + raw-string patch"
                )
            results.append(result)
    except UnityPyUnavailable as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 5
    except RawStringPatchError as exc:
        report["status"] = "needs_raw_object_mapping"
        report["raw_string_blocker"] = str(exc)
        report["bundle_aware"] = results
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"BLOQUEADO COM SEGURANÇA: {exc}", file=sys.stderr)
        print(f"Mapa salvo em: {report_path}", file=sys.stderr)
        return 4
    except Exception as exc:
        print(f"ERRO no patch bundle-aware: {exc}", file=sys.stderr)
        return 4

    candidates = _candidate_summary(results)
    report["bundle_aware"] = results
    report["bundle_candidates"] = candidates
    changed = [x for x in results if x.get("changed")]
    if not changed:
        # Sweep mode always inspects every bundle. If the stage-1 byte patch
        # already succeeded and no bundle holds an official host anywhere, the
        # tree is simply clean: report success instead of a false blocker.
        if args.sweep_all_bundles and report.get("status") == "ok":
            report["status"] = "ok_no_bundle_changes"
            report["bundle_aware"] = results
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(json.dumps({
                "status": report["status"],
                "server_host": host,
                "inspected_bundles": len(results),
                "replacements": 0,
            }, indent=2, ensure_ascii=False))
            return 0
        if candidates["raw_only_references"]:
            report["status"] = "needs_typetree_mapping"
            detail = (
                f"{candidates['raw_only_references']} referência(s) localizada(s) em payload bruto de "
                f"{len(candidates['raw_only'])} objeto(s), mas sem uma string Unity serializada comprovável. "
                "O relatório contém type/path_id para mapear o objeto sem alterar bytes no escuro."
            )
        else:
            report["status"] = "needs_object_mapping"
            detail = (
                "o hostname foi localizado no bundle bruto do APK, mas o parser Unity não o associou "
                "a um objeto serializável nem a uma string raw estruturada."
            )
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"BLOQUEADO COM SEGURANÇA: {detail}", file=sys.stderr)
        print(f"Mapa salvo em: {report_path}", file=sys.stderr)
        return 4

    report["status"] = "ok_bundle_aware"
    report["bundle_aware_patched_files"] = [x["path"] for x in changed]
    report["bundle_aware_replacements"] = sum(int(x.get("replacements", 0)) for x in changed)
    report["raw_string_replacements"] = sum(int(x.get("raw_string_replacements", 0)) for x in changed)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": report["status"],
        "server_host": host,
        "patched_files": report["bundle_aware_patched_files"],
        "replacements": report["bundle_aware_replacements"],
        "raw_string_replacements": report["raw_string_replacements"],
        "serializable_candidates": len(candidates["serializable"]),
        "raw_only_candidates": len(candidates["raw_only"]),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
