#!/usr/bin/env python3
"""Testes de apply_set do generate_endpoint_matrix (evidência via CLI).

Cobre o item §20.3 da fase 13 do plano: `persistence_validated` aceita
true/false/null por CLI, com teste — em vez de editar o JSON à mão.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import generate_endpoint_matrix as gem  # noqa: E402


def registro_minimo() -> dict:
    return {
        "_meta": {"route_count": 2},
        "endpoints": {
            "game/gear/upgrade": {
                "module": "gear", "implemented": True, "schema_extracted": False,
                "request_observed": False, "response_observed": False,
                "client_validated": False, "persistence_validated": None,
                "regression_test": False, "fixture": None,
                "fixture_provenance": None, "uses_fallback": False, "evidence": "",
            },
            "game/store/get": {
                "module": "store", "implemented": True, "schema_extracted": True,
                "request_observed": True, "response_observed": True,
                "client_validated": True, "persistence_validated": None,
                "regression_test": True, "fixture": None,
                "fixture_provenance": None, "uses_fallback": False, "evidence": "",
            },
        },
    }


class TestApplySet(unittest.TestCase):
    def test_persistence_validated_true_false_null(self):
        for raw, esperado in (("true", True), ("false", False), ("null", None)):
            compat = registro_minimo()
            gem.apply_set(compat, "game/gear/upgrade", [f"persistence_validated={raw}"], {})
            self.assertIs(compat["endpoints"]["game/gear/upgrade"]["persistence_validated"], esperado)

    def test_campos_bool_continham_true_false(self):
        compat = registro_minimo()
        gem.apply_set(
            compat, "game/store/get",
            ["schema_extracted=true", "client_validated=false", "uses_fallback=false"], {},
        )
        ep = compat["endpoints"]["game/store/get"]
        self.assertIs(ep["schema_extracted"], True)
        self.assertIs(ep["client_validated"], False)
        self.assertIs(ep["uses_fallback"], False)

    def test_bool_nao_aceita_null(self):
        compat = registro_minimo()
        with self.assertRaises(SystemExit):
            gem.apply_set(compat, "game/gear/upgrade", ["schema_extracted=null"], {})

    def test_persistence_nao_aceita_valor_invalido(self):
        compat = registro_minimo()
        with self.assertRaises(SystemExit):
            gem.apply_set(compat, "game/gear/upgrade", ["persistence_validated=maybe"], {})

    def test_campo_fora_da_whitelist_rejeitado(self):
        compat = registro_minimo()
        with self.assertRaises(SystemExit):
            gem.apply_set(compat, "game/gear/upgrade", ["implemented=true"], {})

    def test_rota_desconhecida_rejeitada(self):
        compat = registro_minimo()
        with self.assertRaises(SystemExit):
            gem.apply_set(compat, "game/nao/existe", ["schema_extracted=true"], {})

    def test_note_anexa_evidencia(self):
        compat = registro_minimo()
        gem.apply_set(
            compat, "game/gear/upgrade", ["persistence_validated=true"],
            {"game/gear/upgrade": "restart 2026-08-18: nível persistiu"},
        )
        ep = compat["endpoints"]["game/gear/upgrade"]
        self.assertIs(ep["persistence_validated"], True)
        self.assertIn("restart", ep["evidence"])


def main() -> int:
    unittest.main(verbosity=2, exit=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
