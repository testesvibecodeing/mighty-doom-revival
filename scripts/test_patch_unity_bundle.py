#!/usr/bin/env python3
from __future__ import annotations

from patch_unity_bundle import KNOWN_HOSTS, replace_known_hosts


def main() -> int:
    target = "doom.example.com"
    source = KNOWN_HOSTS[0]
    other = KNOWN_HOSTS[1]

    payload = {
        "url": f"https://{source}/game/auth/register",
        "nested": [
            {"endpoint": f"https://{other}/game/player/user-data"},
            "unrelated",
            123,
        ],
        "tuple": (source, "keep"),
    }

    patched, count = replace_known_hosts(payload, target)
    assert count == 3
    assert patched["url"] == f"https://{target}/game/auth/register"
    assert patched["nested"][0]["endpoint"] == f"https://{target}/game/player/user-data"
    assert patched["nested"][1] == "unrelated"
    assert patched["nested"][2] == 123
    assert patched["tuple"] == (target, "keep")

    untouched, zero = replace_known_hosts({"x": "nothing"}, target)
    assert zero == 0
    assert untouched == {"x": "nothing"}

    # Main regression: arbitrary-length replacement is legal at the serialized
    # object layer. Raw binary replacement remains forbidden for this case.
    assert len(target.encode("ascii")) != len(source.encode("ascii"))

    print("Mighty DOOM Revival bundle-aware replacement logic: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
