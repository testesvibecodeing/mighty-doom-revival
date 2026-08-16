#!/usr/bin/env python3
from __future__ import annotations

from patch_unity_bundle import KNOWN_HOSTS
from patch_unity_raw_strings import RawStringPatchError, patch_serialized_strings


def unity_string(text: str) -> bytes:
    payload = text.encode("utf-8")
    end = 4 + len(payload)
    padded = (end + 3) & ~3
    return len(payload).to_bytes(4, "little") + payload + (b"\x00" * (padded - end))


def main() -> int:
    source = KNOWN_HOSTS[0]
    other = KNOWN_HOSTS[1]
    target = "revival.example.net"

    raw = (
        b"\x11\x22\x33\x44"
        + unity_string(f"https://{source}/game/auth/register")
        + b"\x55\x66\x77\x88"
        + unity_string(f"telemetry=https://{other}/events")
        + b"\xaa\xbb\xcc\xdd"
    )
    patched, info = patch_serialized_strings(raw, target)
    assert info == {"changed": True, "replacements": 2, "regions": 2}
    assert source.encode("ascii") not in patched
    assert other.encode("ascii") not in patched
    assert patched.count(target.encode("ascii")) == 2
    assert f"https://{target}/game/auth/register".encode() in patched
    assert f"telemetry=https://{target}/events".encode() in patched

    # Same-length is supported too; the helper still updates the serialized
    # string structurally rather than performing a blind file-wide replace.
    same = "x" * len(source)
    same_patched, same_info = patch_serialized_strings(unity_string(source), same)
    assert same_info["replacements"] == 1
    assert same.encode() in same_patched

    # A raw hostname with no valid uint32-length UTF-8 string envelope must be
    # rejected. This preserves the previous safety property for arbitrary
    # binary/compressed payloads.
    try:
        patch_serialized_strings(b"prefix-" + source.encode() + b"-suffix", target)
    except RawStringPatchError:
        pass
    else:
        raise AssertionError("raw binary hostname without Unity string envelope was patched")

    # Non-zero padding is not a valid aligned Unity string candidate and must
    # remain blocked.
    payload = source.encode()
    malformed = len(payload).to_bytes(4, "little") + payload
    malformed += b"\xff" * (((4 + len(payload) + 3) & ~3) - (4 + len(payload)))
    try:
        patch_serialized_strings(malformed, target)
    except RawStringPatchError:
        pass
    else:
        raise AssertionError("malformed Unity padding was accepted")

    print("Mighty DOOM Revival raw Unity string patch logic: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
