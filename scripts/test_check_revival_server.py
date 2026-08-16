#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

import check_revival_server as preflight


class FakeResponse:
    def __init__(self, payload: dict[str, object], status: int = 200):
        self.status = status
        self.headers = {"Content-Type": "application/json; charset=utf-8"}
        self._body = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def getcode(self):
        return self.status

    def read(self, limit: int = -1):
        return self._body.read(limit)


def health(**changes):
    payload = {
        "ok": True,
        "server": "Mighty DOOM Revival",
        "client_version": "1.13.1",
        "api_version": "24.0.0",
        "game_data_loaded": True,
        "research_mode": True,
        "runtime": "node-builtin-http+sqlite",
    }
    payload.update(changes)
    return payload


def compatible_sequence(**health_changes):
    payload = health(**health_changes)
    return [
        FakeResponse(payload),
        FakeResponse(payload),
        FakeResponse({"uts": "2026-08-16T17:04:46.000Z", "code": 2200}, status=400),
    ]


class CheckRevivalServerTests(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_accepts_compatible_server_and_exact_gear_client_path(self, urlopen):
        urlopen.side_effect = compatible_sequence()
        result = preflight.check_server("doom.example.com", None, 2.0)
        self.assertTrue(result["verified"])
        self.assertEqual(result["client_version"], "1.13.1")
        self.assertEqual(result["api_version"], "24.0.0")
        self.assertEqual(result["gear_prefix"]["health_status"], 200)
        self.assertEqual(result["gear_prefix"]["auth_probe_status"], 400)
        self.assertEqual(result["gear_prefix"]["auth_probe_code"], 2200)
        self.assertEqual(
            result["gear_prefix"]["auth_probe_uts"],
            "2026-08-16T17:04:46.000Z",
        )

        calls = [call.args[0] for call in urlopen.call_args_list]
        self.assertEqual(calls[0].full_url, "https://doom.example.com/revival/health")
        self.assertEqual(
            calls[1].full_url,
            "https://doom.example.com/collections/doom/revival/health",
        )
        self.assertEqual(
            calls[2].full_url,
            "https://doom.example.com/collections/doom/game/auth/register",
        )
        self.assertEqual(calls[2].get_header("X-ubu-apiversion"), "24.0.0")
        self.assertEqual(json.loads(calls[2].data), {"client_version": "revival-preflight-invalid"})

    @patch("urllib.request.urlopen")
    def test_rejects_wrong_client_version(self, urlopen):
        urlopen.return_value = FakeResponse(health(client_version="1.12.0"))
        with self.assertRaisesRegex(RuntimeError, "client_version"):
            preflight.check_server("doom.example.com", None, 2.0)

    @patch("urllib.request.urlopen")
    def test_requires_game_data_for_release_patcher(self, urlopen):
        urlopen.return_value = FakeResponse(health(game_data_loaded=False))
        with self.assertRaisesRegex(RuntimeError, "game_data_loaded"):
            preflight.check_server("doom.example.com", None, 2.0)

    @patch("urllib.request.urlopen")
    def test_can_relax_game_data_for_development_probe(self, urlopen):
        urlopen.side_effect = compatible_sequence(game_data_loaded=False)
        result = preflight.check_server(
            "doom.example.com", None, 2.0, require_game_data=False
        )
        self.assertTrue(result["verified"])
        self.assertFalse(result["game_data_loaded"])

    @patch("urllib.request.urlopen")
    def test_rejects_proxy_that_drops_gear_prefix(self, urlopen):
        urlopen.side_effect = [
            FakeResponse(health()),
            FakeResponse({"ok": False, "error": "not-found"}, status=200),
        ]
        with self.assertRaisesRegex(RuntimeError, "rota Gear incompatível"):
            preflight.check_server("doom.example.com", None, 2.0)

    @patch("urllib.request.urlopen")
    def test_rejects_when_auth_probe_does_not_reach_game_handler(self, urlopen):
        urlopen.side_effect = [
            FakeResponse(health()),
            FakeResponse(health()),
            FakeResponse({"ok": False, "error": "not-found"}, status=404),
        ]
        with self.assertRaisesRegex(RuntimeError, "auth probe"):
            preflight.check_server("doom.example.com", None, 2.0)

    @patch("urllib.request.urlopen")
    def test_rejects_numeric_auth_wire_timestamp_that_crashes_client(self, urlopen):
        urlopen.side_effect = [
            FakeResponse(health()),
            FakeResponse(health()),
            FakeResponse({"uts": 1786900000, "code": 2200}, status=400),
        ]
        with self.assertRaisesRegex(RuntimeError, "string ISO 8601 UTC"):
            preflight.check_server("doom.example.com", None, 2.0)

    @patch("urllib.request.urlopen")
    def test_rejects_timezone_less_auth_wire_timestamp(self, urlopen):
        urlopen.side_effect = [
            FakeResponse(health()),
            FakeResponse(health()),
            FakeResponse({"uts": "2026-08-16T17:04:46.000", "code": 2200}, status=400),
        ]
        with self.assertRaisesRegex(RuntimeError, "offset UTC explícito"):
            preflight.check_server("doom.example.com", None, 2.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)