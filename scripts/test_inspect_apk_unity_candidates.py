#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
MODULE_PATH = ROOT / "inspect_apk_unity_candidates.py"
spec = importlib.util.spec_from_file_location("inspect_apk_unity_candidates", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class CandidateBundleTests(unittest.TestCase):
    def test_filters_and_deduplicates_only_addressable_bundles(self):
        report = {
            "host_hits": [
                {"file": "assets/aa/android/a.bundle"},
                {"file": "assets/aa/android/a.bundle"},
                {"file": "assets/aa/android/catalog.json"},
                {"file": "res/xml/network.xml"},
                {"file": "assets/aa/android/b.bundle"},
            ]
        }
        self.assertEqual(
            module.candidate_bundle_paths(report),
            ["assets/aa/android/a.bundle", "assets/aa/android/b.bundle"],
        )

    def test_inspection_exports_metadata_only(self):
        report = {"host_hits": [{"file": "assets/aa/android/a.bundle"}]}
        with tempfile.TemporaryDirectory() as td:
            apk = Path(td) / "game.apk"
            with zipfile.ZipFile(apk, "w") as zf:
                zf.writestr("assets/aa/android/a.bundle", b"proprietary-test-payload")

            fake = {
                "path": "/tmp/private.bundle",
                "serializable": [
                    {
                        "type": "MonoBehaviour",
                        "name": "EndpointConfig",
                        "path_id": 42,
                        "serialized_references": 1,
                        "raw_references": 1,
                        "raw_hosts": {"slayersclub.bethesda.net": 1},
                    }
                ],
                "raw_only": [],
                "serializable_references": 1,
                "raw_only_references": 0,
            }
            with mock.patch.object(module, "inspect_bundle", return_value=fake) as inspect:
                result = module.inspect_apk(apk, report)

            self.assertEqual(result["candidate_bundles"], 1)
            self.assertEqual(result["serializable_references"], 1)
            self.assertEqual(result["raw_only_references"], 0)
            self.assertEqual(result["bundles"][0]["bundle"], "assets/aa/android/a.bundle")
            self.assertNotIn("path", result["bundles"][0])
            inspected_path = Path(inspect.call_args.args[0])
            self.assertFalse(inspected_path.exists())
            self.assertNotIn("proprietary-test-payload", json.dumps(result))

    def test_missing_member_is_reported_without_extraction(self):
        report = {"host_hits": [{"file": "assets/aa/android/missing.bundle"}]}
        with tempfile.TemporaryDirectory() as td:
            apk = Path(td) / "game.apk"
            with zipfile.ZipFile(apk, "w") as zf:
                zf.writestr("placeholder.txt", "x")
            with mock.patch.object(module, "inspect_bundle") as inspect:
                result = module.inspect_apk(apk, report)
            inspect.assert_not_called()
            self.assertEqual(result["bundles"], [
                {"bundle": "assets/aa/android/missing.bundle", "error": "missing-from-apk"}
            ])


if __name__ == "__main__":
    unittest.main()
