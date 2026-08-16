#!/usr/bin/env python3
from __future__ import annotations

from patch_unity_bundle import KNOWN_HOSTS
from patch_unity_raw_strings import RawStringPatchError, patch_serialized_strings


def unity_string(text: str) -> bytes:
    payload = text.encode("utf-8")
    end = 4 + len(payload)
    padded = (end + 3) & ~3
    return len(payload).to_bytes(4, "little") + payload + (b"\x00" * (padded - end))


def unaligned_unity_string(prefix: bytes, text: str) -> bytes:
    payload = text.encode("utf-8")
    start = len(prefix)
    payload_end = start + 4 + len(payload)
    aligned_end = (payload_end + 3) & ~3
    return prefix + len(payload).to_bytes(4, "little") + payload + (b"\x00" * (aligned_end - payload_end))


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

    # The uint32 prefix itself is not guaranteed to begin at an absolute
    # 4-byte offset inside the object's raw payload. A valid string following
    # an unaligned field must still be patchable when its length, UTF-8 data
    # and zero alignment padding uniquely prove the region.
    unaligned = unaligned_unity_string(b"\x01\x02\x03", f"https://{source}/game/auth/login-device")
    unaligned_patched, unaligned_info = patch_serialized_strings(unaligned, target)
    assert unaligned_info == {"changed": True, "replacements": 1, "regions": 1}
    assert source.encode("ascii") not in unaligned_patched
    assert f"https://{target}/game/auth/login-device".encode() in unaligned_patched

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
    # remain blocked. `source` (KNOWN_HOSTS[0]) is 24 bytes, so its 4-byte
    # length prefix plus payload already lands on a 4-byte boundary with no
    # padding at all -- there would be nothing to corrupt. Use `other`
    # (KNOWN_HOSTS[1], 41 bytes) instead: its prefix+payload is unaligned, so
    # real padding bytes exist and can be poisoned with non-zero bytes.
    payload = other.encode()
    pad_len = (((4 + len(payload) + 3) & ~3) - (4 + len(payload)))
    assert pad_len > 0, "test host must require real alignment padding"
    malformed = len(payload).to_bytes(4, "little") + payload + (b"\xff" * pad_len)
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
