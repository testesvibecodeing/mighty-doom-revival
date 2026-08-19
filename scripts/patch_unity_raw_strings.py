#!/usr/bin/env python3
"""Safely rewrite endpoint hostnames inside raw Unity serialized object strings.

This is the fallback for objects whose typetree cannot be parsed. It only edits
bytes when every official-host occurrence can be proven to live inside exactly
one Unity-style UTF-8 string: a little-endian uint32 byte length, UTF-8 payload,
and zero padding to a 4-byte boundary. Ambiguous/raw binary hits remain blocked.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from patch_unity_bundle import KNOWN_HOSTS, _load_unitypy


class RawStringPatchError(RuntimeError):
    pass


def _align4(value: int) -> int:
    return (value + 3) & ~3


def _host_offsets(data: bytes) -> list[int]:
    offsets: list[int] = []
    for host in KNOWN_HOSTS:
        needle = host.encode("ascii")
        start = 0
        while True:
            index = data.find(needle, start)
            if index < 0:
                break
            offsets.append(index)
            start = index + 1
    return sorted(set(offsets))


def _candidate_regions(data: bytes, host_offset: int, max_string_bytes: int = 8192) -> list[tuple[int, int, int]]:
    """Return plausible (prefix, payload_end, aligned_end) Unity string regions.

    Do not require the uint32 length prefix itself to start at a 4-byte offset.
    Unity strings are padded to a 4-byte boundary after their payload, but the
    containing field can begin unaligned depending on the preceding serialized
    fields. Safety comes from requiring a unique length-delimited UTF-8 region,
    known-host containment and zero alignment padding before any bytes change.
    """
    candidates: list[tuple[int, int, int]] = []
    lower = max(0, host_offset - max_string_bytes - 4)
    for prefix in range(lower, host_offset):
        if prefix + 4 > host_offset:
            break
        length = int.from_bytes(data[prefix:prefix + 4], "little", signed=False)
        if length <= 0 or length > max_string_bytes:
            continue
        payload_start = prefix + 4
        payload_end = payload_start + length
        aligned_end = _align4(payload_end)
        if not (payload_start <= host_offset < payload_end):
            continue
        if aligned_end > len(data):
            continue
        payload = data[payload_start:payload_end]
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if "\x00" in text or not any(host in text for host in KNOWN_HOSTS):
            continue
        padding = data[payload_end:aligned_end]
        if any(byte != 0 for byte in padding):
            continue
        candidates.append((prefix, payload_end, aligned_end))
    return candidates


def patch_serialized_strings(data: bytes, target_host: str) -> tuple[bytes, dict[str, Any]]:
    offsets = _host_offsets(data)
    if not offsets:
        return data, {"changed": False, "replacements": 0, "regions": 0}

    regions: dict[int, tuple[int, int, int]] = {}
    for offset in offsets:
        candidates = _candidate_regions(data, offset)
        if len(candidates) != 1:
            raise RawStringPatchError(
                f"host raw em offset {offset} pertence a {len(candidates)} string(s) Unity plausível(is); recusando patch ambíguo"
            )
        region = candidates[0]
        regions[region[0]] = region

    output = data
    replacements = 0
    # Descending offsets keep earlier region coordinates stable while lengths change.
    for prefix, payload_end, aligned_end in sorted(regions.values(), reverse=True):
        payload_start = prefix + 4
        text = output[payload_start:payload_end].decode("utf-8")
        patched = text
        local = 0
        for host in KNOWN_HOSTS:
            count = patched.count(host)
            if count:
                patched = patched.replace(host, target_host)
                local += count
        if not local:
            continue
        encoded = patched.encode("utf-8")
        new_end = payload_start + len(encoded)
        new_aligned_end = _align4(new_end)
        replacement = len(encoded).to_bytes(4, "little") + encoded + (b"\x00" * (new_aligned_end - new_end))
        output = output[:prefix] + replacement + output[aligned_end:]
        replacements += local

    remaining = sum(output.count(host.encode("ascii")) for host in KNOWN_HOSTS)
    if remaining:
        raise RawStringPatchError(f"{remaining} referência(s) oficial(is) permaneceram no objeto após patch")
    if output.count(target_host.encode("ascii")) < replacements:
        raise RawStringPatchError("hostname alvo não foi encontrado na quantidade esperada após patch")

    return output, {"changed": replacements > 0, "replacements": replacements, "regions": len(regions)}


def patch_raw_bundle(path: Path, target_host: str) -> dict[str, Any]:
    """Patch raw serialized strings atomically using UnityPy set_raw_data()."""
    UnityPy = _load_unitypy()
    path = path.resolve()
    # Dos bytes pelo mesmo motivo do patch_unity_bundle: handle aberto no
    # original bloquearia o replace no Windows (WinError 5).
    env = UnityPy.load(path.read_bytes())
    changes: list[dict[str, Any]] = []

    for obj in env.objects:
        try:
            raw = bytes(obj.get_raw_data())
        except Exception:
            continue
        if not any(host.encode("ascii") in raw for host in KNOWN_HOSTS):
            continue
        patched, info = patch_serialized_strings(raw, target_host)
        if info["changed"]:
            obj.set_raw_data(patched)
            changes.append({
                "type": getattr(getattr(obj, "type", None), "name", ""),
                "path_id": getattr(obj, "path_id", None),
                "replacements": info["replacements"],
                "regions": info["regions"],
            })

    if not changes:
        return {"path": str(path), "changed": False, "objects": [], "replacements": 0, "verified": False}

    payload = env.file.save()
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".raw-revival.tmp", dir=str(path.parent))
    os.close(fd)
    temp = Path(temp_name)
    try:
        temp.write_bytes(payload)
        # Mesmo motivo do patch_unity_bundle: carregar do caminho mantém o
        # handle do tmp aberto e o replace falha com WinError 32 no Windows.
        check = UnityPy.load(payload)
        official = 0
        target = 0
        for obj in check.objects:
            try:
                raw = bytes(obj.get_raw_data())
            except Exception:
                continue
            official += sum(raw.count(host.encode("ascii")) for host in KNOWN_HOSTS)
            target += raw.count(target_host.encode("ascii"))
        if official:
            raise RawStringPatchError(f"bundle reserializado ainda contém {official} referência(s) oficial(is) raw")
        expected = sum(int(x["replacements"]) for x in changes)
        if target < expected:
            raise RawStringPatchError("bundle reserializado não contém todas as referências do hostname alvo")
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
    }
