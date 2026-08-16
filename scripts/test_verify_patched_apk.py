#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import verify_patched_apk as verifier
from verify_patched_apk import scan_apk, scan_unity_bundle_payload

GEAR_HOST = "international.gear.bethesda.net"
AUX_HOST = "slayersclub.bethesda.net"
TARGET = "doom.debruinsistemas.com.br"


def build_apk(path: Path, bundle_payload: bytes = b"", metadata_payload: bytes = b"") -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("AndroidManifest.xml", b"manifest")
        archive.writestr("assets/aa/Android/catalog.bundle", bundle_payload)
        archive.writestr(
            "assets/bin/Data/Managed/Metadata/global-metadata.dat",
            metadata_payload,
        )


class FakeType:
    name = "MonoBehaviour"


class FakeObject:
    type = FakeType()

    def __init__(self, text: str):
        self.text = text

    def parse_as_dict(self):
        return {"endpoint": self.text}


class FakeEnv:
    def __init__(self, text: str):
        self.objects = [FakeObject(text)]


class FakeUnityPy:
    payload_map: dict[bytes, str] = {}

    @classmethod
    def load(cls, payload: bytes):
        return FakeEnv(cls.payload_map.get(bytes(payload), ""))


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # Realistic happy path: the redirect can live only in IL2CPP metadata,
        # and an unrelated Slayers Club URL may remain elsewhere in the APK.
        good = root / "good.apk"
        build_apk(
            good,
            bundle_payload=f"https://{AUX_HOST}/news".encode("ascii"),
            metadata_payload=f"https://u00@{TARGET}/collections/doom".encode("ascii"),
        )
        result = scan_apk(good, TARGET)
        assert result["target_occurrences"] >= 1
        assert result["official_occurrences"] == 0
        assert result["known_host_occurrences"] >= 1
        assert result["known_host_hits"][0]["host"] == AUX_HOST

        # A stale Gear API reference must still fail the final gate even when
        # the Revival hostname is present somewhere else.
        stale = root / "stale.apk"
        build_apk(
            stale,
            bundle_payload=f"https://{TARGET}/data".encode("ascii"),
            metadata_payload=f"https://{GEAR_HOST}/collections/doom".encode("ascii"),
        )
        result = scan_apk(stale, TARGET)
        assert result["target_occurrences"] >= 1
        assert result["official_occurrences"] >= 1
        assert result["forbidden_endpoint_hits"][0]["host"] == GEAR_HOST

        missing = root / "missing.apk"
        build_apk(missing, metadata_payload=b"no endpoint here")
        result = scan_apk(missing, TARGET)
        assert result["target_occurrences"] == 0
        assert result["official_occurrences"] == 0

        # Regression: LZ4-compressed bundle internals can hide the hostname
        # from raw ZIP scans. Model that by using an opaque bundle payload and
        # a fake Unity loader that exposes a serialized endpoint only after
        # bundle decoding.
        opaque_target = b"opaque-compressed-target-bundle"
        opaque_stale = b"opaque-compressed-stale-bundle"
        FakeUnityPy.payload_map = {
            opaque_target: f"https://{TARGET}/collections/doom",
            opaque_stale: f"https://{GEAR_HOST}/collections/doom",
        }

        structured = scan_unity_bundle_payload(opaque_target, TARGET, unitypy=FakeUnityPy)
        assert structured == {"target": 1, "known": 0, "forbidden": 0}
        structured = scan_unity_bundle_payload(opaque_stale, TARGET, unitypy=FakeUnityPy)
        assert structured["target"] == 0
        assert structured["known"] == 1
        assert structured["forbidden"] == 1

        original_loader = verifier._load_unitypy
        verifier._load_unitypy = lambda: FakeUnityPy
        try:
            compressed_good = root / "compressed-good.apk"
            build_apk(compressed_good, bundle_payload=opaque_target)
            result = scan_apk(compressed_good, TARGET)
            assert result["raw_target_occurrences"] == 0
            assert result["unity_target_occurrences"] == 1
            assert result["target_occurrences"] == 1
            assert result["official_occurrences"] == 0
            assert result["bundle_scan_available"] is True

            compressed_stale = root / "compressed-stale.apk"
            build_apk(
                compressed_stale,
                bundle_payload=opaque_stale,
                metadata_payload=f"https://{TARGET}/bootstrap".encode("ascii"),
            )
            result = scan_apk(compressed_stale, TARGET)
            assert result["raw_official_occurrences"] == 0
            assert result["unity_official_occurrences"] == 1
            assert result["official_occurrences"] == 1
        finally:
            verifier._load_unitypy = original_loader

    print("verify_patched_apk compressed bundle regression: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
