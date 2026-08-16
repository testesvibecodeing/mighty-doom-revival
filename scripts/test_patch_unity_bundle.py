#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy

from patch_unity_bundle import (
    KNOWN_HOSTS,
    _patch_environment,
    _scan_environment,
    inspect_environment,
    replace_known_hosts,
)


class FakeType:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeGenericObject:
    def __init__(self, type_name: str, tree: dict, path_id: int = 1) -> None:
        self.type = FakeType(type_name)
        self.tree = deepcopy(tree)
        self.path_id = path_id
        self.patch_calls = 0

    def parse_as_dict(self):
        return deepcopy(self.tree)

    def patch(self, value):
        self.tree = deepcopy(value)
        self.patch_calls += 1

    def peek_name(self):
        return self.tree.get("m_Name", "")

    def get_raw_data(self):
        return str(self.tree).encode("utf-8")


class FakeRawOnlyObject:
    def __init__(self, raw: bytes, path_id: int = 2) -> None:
        self.type = FakeType("UnknownType")
        self.raw = raw
        self.path_id = path_id

    def parse_as_dict(self):
        raise RuntimeError("typetree unavailable")

    def peek_name(self):
        return ""

    def get_raw_data(self):
        return self.raw


class FakeEnvironment:
    def __init__(self, objects) -> None:
        self.objects = objects


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

    # Regression: the endpoint may live in any object with a usable Unity
    # typetree, not only TextAsset/MonoBehaviour. The generic patch path must
    # modify and verify such objects without raw binary replacement.
    runtime_data = FakeGenericObject(
        "ResourceManagerRuntimeData",
        {
            "m_Name": "AddressablesRuntimeData",
            "ApiBase": f"https://{source}",
            "Nested": {"Telemetry": f"https://{other}/events"},
        },
    )
    env = FakeEnvironment([runtime_data])
    inspection = inspect_environment(env)
    assert inspection["serializable_references"] == 2
    assert inspection["raw_only_references"] == 0

    changes = _patch_environment(env, target)
    assert len(changes) == 1
    assert changes[0]["type"] == "ResourceManagerRuntimeData"
    assert changes[0]["replacements"] == 2
    assert runtime_data.patch_calls == 1
    assert runtime_data.tree["ApiBase"] == f"https://{target}"
    assert runtime_data.tree["Nested"]["Telemetry"] == f"https://{target}/events"

    verified = _scan_environment(env, target)
    assert verified == {"official": 0, "target": 2}

    # If UnityPy cannot deserialize an object but its raw payload contains the
    # host, inspection must surface it as a mapping blocker rather than modify
    # bytes blindly.
    raw_only = FakeRawOnlyObject(b"prefix-" + source.encode("ascii") + b"-suffix")
    raw_inspection = inspect_environment(FakeEnvironment([raw_only]))
    assert raw_inspection["serializable_references"] == 0
    assert raw_inspection["raw_only_references"] == 1
    assert raw_inspection["raw_only"][0]["type"] == "UnknownType"
    assert raw_inspection["raw_only"][0]["raw_hosts"][source] == 1

    # Main regression: arbitrary-length replacement is legal at the serialized
    # object layer. Raw binary replacement remains forbidden for this case.
    assert len(target.encode("ascii")) != len(source.encode("ascii"))

    print("Mighty DOOM Revival bundle-aware replacement logic: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
