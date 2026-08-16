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


class CheckRevivalServerTests(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_accepts_compatible_server(self, urlopen):
        urlopen.return_value = FakeResponse(health())
        result = preflight.check_server("doom.example.com", None, 2.0)
        self.assertTrue(result["verified"])
        self.assertEqual(result["client_version"], "1.13.1")
        self.assertEqual(result["api_version"], "24.0.0")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://doom.example.com/revival/health")

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
        urlopen.return_value = FakeResponse(health(game_data_loaded=False))
        result = preflight.check_server(
            "doom.example.com", None, 2.0, require_game_data=False
        )
        self.assertTrue(result["verified"])
        self.assertFalse(result["game_data_loaded"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
