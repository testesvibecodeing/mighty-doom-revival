#!/usr/bin/env python3
"""Regression tests for the Android network-security config written by patch_apk.

These tests use only synthetic XML/CA fixtures. They make sure a generated
client trusts the selected Revival hostname over HTTPS without silently
allowing cleartext or retaining an official endpoint in the trust policy.
"""
from __future__ import annotations

import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from patch_apk import ANDROID_NS, KNOWN_HOSTS, patch_manifest, write_network_security

TARGET = "revival.example.org"
ANDROID = f"{{{ANDROID_NS}}}"


def _make_decoded(root: Path) -> None:
    (root / "res" / "xml").mkdir(parents=True, exist_ok=True)
    (root / "AndroidManifest.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
          package="com.example.revival.fixture">
  <uses-permission android:name="android.permission.INTERNET" />
  <application android:label="fixture" android:usesCleartextTraffic="true" />
</manifest>
""",
        encoding="utf-8",
    )


def _parse_security(root: Path) -> ET.Element:
    return ET.parse(root / "res" / "xml" / "network_security_config.xml").getroot()


def test_public_ca_config() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        decoded = Path(tmp)
        _make_decoded(decoded)

        patch_manifest(decoded)
        write_network_security(decoded, TARGET, None)

        manifest = ET.parse(decoded / "AndroidManifest.xml").getroot()
        app = manifest.find("application")
        assert app is not None
        assert app.get(f"{ANDROID}networkSecurityConfig") == "@xml/network_security_config"

        root = _parse_security(decoded)
        configs = root.findall("domain-config")
        assert len(configs) == 1
        config = configs[0]
        assert config.get("cleartextTrafficPermitted") == "false"

        domains = config.findall("domain")
        assert len(domains) == 1
        assert (domains[0].text or "").strip() == TARGET
        assert domains[0].get("includeSubdomains") == "true"

        certs = config.findall("./trust-anchors/certificates")
        assert [item.get("src") for item in certs] == ["system"]

        serialized = (decoded / "res" / "xml" / "network_security_config.xml").read_text(encoding="utf-8")
        for official in KNOWN_HOSTS:
            assert official not in serialized


def test_embedded_ca_config() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        decoded = Path(tmp)
        _make_decoded(decoded)
        ca = decoded / "fixture-ca.pem"
        ca.write_text(
            "-----BEGIN CERTIFICATE-----\nSYNTHETIC-TEST-ONLY\n-----END CERTIFICATE-----\n",
            encoding="ascii",
        )

        patch_manifest(decoded)
        write_network_security(decoded, TARGET, ca)

        embedded = decoded / "res" / "raw" / "mightydoom_ca.pem"
        assert embedded.is_file()
        assert embedded.read_bytes() == ca.read_bytes()

        config = _parse_security(decoded).find("domain-config")
        assert config is not None
        certs = config.findall("./trust-anchors/certificates")
        assert [item.get("src") for item in certs] == ["system", "@raw/mightydoom_ca"]


def main() -> int:
    test_public_ca_config()
    test_embedded_ca_config()
    print("network-security regression: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
