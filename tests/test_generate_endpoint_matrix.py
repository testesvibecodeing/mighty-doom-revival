#!/usr/bin/env python3
"""Testes de apply_set do generate_endpoint_matrix (evidência via CLI).

Cobre o item §20.3 da fase 13 do plano: `persistence_validated` aceita
true/false/null por CLI, com teste — em vez de editar o JSON à mão.
"""
from __future__ import annotations

import json
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


class TestFixtureDerivation(unittest.TestCase):
    """Fixture client aciona os gates derivados; server-replay, não."""

    def setUp(self):
        self._original = (gem.implemented_routes, gem.test_routes, gem.load_fixtures)
        gem.implemented_routes = lambda: {"game/gear/upgrade"}
        gem.test_routes = lambda: set()
        gem.load_fixtures = lambda: {
            "game/gear/upgrade": {"file": "tests/fixtures/protocol/client/gear/game__gear__upgrade.json",
                                  "provenance": "client", "sanitized": True},
            "game/store/get": {"file": "tests/fixtures/protocol/server-replay/store/game__store__get.json",
                               "provenance": "server-replay", "sanitized": True},
        }

    def tearDown(self):
        gem.implemented_routes, gem.test_routes, gem.load_fixtures = self._original

    def _compat(self, previous_endpoints=None):
        # sem metadata, o previous é a fonte das rotas — as duas base precisam
        # existir para os testes derivarem gates delas.
        base = {"game/gear/upgrade": {}, "game/store/get": {}}
        base.update(previous_endpoints or {})
        return gem.build_compat(None, {"_meta": {}, "endpoints": base})

    def test_fixture_client_aciona_os_dois_gates(self):
        compat = self._compat()
        ep = compat["endpoints"]["game/gear/upgrade"]
        self.assertIs(ep["request_observed"], True)
        self.assertIs(ep["response_observed"], True)
        self.assertEqual(ep["evidence_provenance"], "client-fixture")
        self.assertEqual(ep["fixture_provenance"], "client")

    def test_server_replay_nao_aciona_gates_de_cliente(self):
        compat = self._compat()
        ep = compat["endpoints"]["game/store/get"]
        self.assertIs(ep["request_observed"], False)
        self.assertIs(ep["response_observed"], False)
        self.assertIsNone(ep["evidence_provenance"])

    def test_fixture_client_sem_sanitized_nao_aciona_gates(self):
        gem.load_fixtures = lambda: {
            "game/gear/upgrade": {"file": "x.json", "provenance": "client", "sanitized": False}}
        ep = self._compat()["endpoints"]["game/gear/upgrade"]
        self.assertIs(ep["request_observed"], False)
        self.assertIs(ep["evidence_provenance"], None)

    def test_observed_herdado_sem_provenance_nao_propaga(self):
        gem.load_fixtures = lambda: {}
        previous = {"game/gear/upgrade": {"request_observed": True, "response_observed": True}}
        ep = self._compat(previous)["endpoints"]["game/gear/upgrade"]
        self.assertIs(ep["request_observed"], False, "correção honesta: sem provenance, gate desce")

    def test_observed_herdado_com_provenance_valida_propaga(self):
        gem.load_fixtures = lambda: {}
        previous = {"game/gear/upgrade": {"request_observed": True, "response_observed": True,
                                          "evidence_provenance": "client-manual"}}
        ep = self._compat(previous)["endpoints"]["game/gear/upgrade"]
        self.assertIs(ep["request_observed"], True)
        self.assertEqual(ep["evidence_provenance"], "client-manual")

    def test_seed_legado_ganha_provenance_legacy_observation(self):
        route = "game/auth/register"
        ep = self._compat({route: {}})["endpoints"][route]
        self.assertIs(ep["request_observed"], True)
        self.assertEqual(ep["evidence_provenance"], "legacy-observation")
        self.assertIn("2026-08-16", ep["evidence"])


class TestLoadFixturesPriority(unittest.TestCase):
    def test_client_vence_server_replay_na_mesma_rota(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client_dir = root / "protocol" / "client" / "gear"
            replay_dir = root / "protocol" / "server-replay" / "gear"
            client_dir.mkdir(parents=True)
            replay_dir.mkdir(parents=True)
            base = {"endpoint": "game/gear/upgrade", "sanitized": True}
            (client_dir / "game__gear__upgrade.json").write_text(
                json.dumps({**base, "provenance": "client"}), encoding="utf-8")
            (replay_dir / "game__gear__upgrade.json").write_text(
                json.dumps({**base, "provenance": "server-replay"}), encoding="utf-8")
            original = gem.FIXTURES_DIR
            gem.FIXTURES_DIR = root / "protocol"
            try:
                loaded = gem.load_fixtures()
            finally:
                gem.FIXTURES_DIR = original
            self.assertEqual(loaded["game/gear/upgrade"]["provenance"], "client")


class TestNoteSemSetCLI(unittest.TestCase):
    """--note sem --set não pode ser descartado (bug: nota sumia calada)."""

    def test_note_sem_set_anexa_evidencia(self):
        import sys as _sys
        import tempfile
        saved = None
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                saved = (gem.COMPAT_JSON, gem.MATRIX_MD, gem.implemented_routes,
                         gem.test_routes, gem.load_fixtures, _sys.argv)
                gem.COMPAT_JSON = root / "compatibility.json"
                gem.MATRIX_MD = root / "ENDPOINT-MATRIX.md"
                gem.COMPAT_JSON.write_text(json.dumps(registro_minimo()), encoding="utf-8")
                gem.implemented_routes = lambda: {"game/gear/upgrade", "game/store/get"}
                gem.test_routes = lambda: set()
                gem.load_fixtures = lambda: {}
                _sys.argv = ["generate_endpoint_matrix.py",
                             "--note", "game/gear/upgrade=observação manual 2026-08-19"]
                import contextlib
                import io
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(gem.main(), 0)
                compat = json.loads(gem.COMPAT_JSON.read_text(encoding="utf-8"))
                evidence = compat["endpoints"]["game/gear/upgrade"]["evidence"]
                self.assertIn("observação manual 2026-08-19", evidence,
                              "--note sem --set foi descartado pelo CLI")
                self.assertIn("observação manual 2026-08-19",
                              gem.MATRIX_MD.read_text(encoding="utf-8"))
        finally:
            if saved is not None:
                (gem.COMPAT_JSON, gem.MATRIX_MD, gem.implemented_routes,
                 gem.test_routes, gem.load_fixtures, _sys.argv) = saved


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

    def test_note_nao_apaga_evidencia_historica(self):
        compat = registro_minimo()
        compat["endpoints"]["game/gear/upgrade"]["evidence"] = "RELATORIO-STATUS 2026-08-16: boot completo"
        gem.apply_set(compat, "game/gear/upgrade", [], {"game/gear/upgrade": "nova captura 2026-08-19"})
        ep = compat["endpoints"]["game/gear/upgrade"]
        self.assertIn("RELATORIO-STATUS 2026-08-16", ep["evidence"])
        self.assertIn("nova captura 2026-08-19", ep["evidence"])

    def test_client_validated_manual_ganha_provenance_client_manual(self):
        compat = registro_minimo()
        gem.apply_set(compat, "game/store/get", ["client_validated=true"], {})
        self.assertEqual(compat["endpoints"]["game/store/get"]["evidence_provenance"], "client-manual")

    def test_client_authoritative_true_sem_note_e_rejeitado(self):
        compat = registro_minimo()
        with self.assertRaises(SystemExit):
            gem.apply_set(compat, "game/gear/upgrade", ["client_authoritative=true"], {})

    def test_client_authoritative_true_com_note_aplica(self):
        compat = registro_minimo()
        gem.apply_set(
            compat, "game/gear/upgrade", ["client_authoritative=true"],
            {"game/gear/upgrade": "DEAD-ENDS #21: flows completos, zero wire"},
        )
        ep = compat["endpoints"]["game/gear/upgrade"]
        self.assertIs(ep["client_authoritative"], True)
        self.assertIn("DEAD-ENDS #21", ep["evidence"])

    def test_client_authoritative_false_nao_exige_note(self):
        compat = registro_minimo()
        gem.apply_set(compat, "game/gear/upgrade", ["client_authoritative=false"], {})
        self.assertIs(compat["endpoints"]["game/gear/upgrade"]["client_authoritative"], False)

    def test_client_authoritative_rejeita_valor_invalido(self):
        compat = registro_minimo()
        with self.assertRaises(SystemExit):
            gem.apply_set(compat, "game/gear/upgrade", ["client_authoritative=maybe"],
                          {"game/gear/upgrade": "nota"})


class TestClientAuthoritativeDerivation(unittest.TestCase):
    """client_authoritative=true na entrada anterior deve virar terminal
    (gates de round-trip -> null) sem prova real de cliente, e nunca contar
    como 'DoD completo' na métrica — sem enfraquecer silenciosamente."""

    def setUp(self):
        self._original = (gem.implemented_routes, gem.test_routes, gem.load_fixtures)
        gem.implemented_routes = lambda: {"game/gear/apply-cosmetic"}
        gem.test_routes = lambda: {"game/gear/apply-cosmetic"}
        gem.load_fixtures = lambda: {}

    def tearDown(self):
        gem.implemented_routes, gem.test_routes, gem.load_fixtures = self._original

    def _prev(self, **overrides):
        base = {
            "module": "gear", "implemented": True, "schema_extracted": True,
            "request_observed": False, "response_observed": False,
            "client_validated": False, "client_authoritative": True,
            "persistence_validated": None, "regression_test": True,
            "fixture": None, "fixture_provenance": None,
            "uses_fallback": False, "evidence": "DEAD-ENDS #21",
        }
        base.update(overrides)
        return {"_meta": {}, "endpoints": {"game/gear/apply-cosmetic": base}}

    def test_terminal_sem_prova_vira_null_nos_tres_gates(self):
        compat = gem.build_compat(None, self._prev())
        ep = compat["endpoints"]["game/gear/apply-cosmetic"]
        self.assertIsNone(ep["request_observed"])
        self.assertIsNone(ep["response_observed"])
        self.assertIsNone(ep["client_validated"])
        self.assertTrue(ep["client_authoritative"])

    def test_terminal_nao_conta_como_done(self):
        compat = gem.build_compat(None, self._prev())
        ep = compat["endpoints"]["game/gear/apply-cosmetic"]
        self.assertTrue(gem.endpoint_terminal(ep), "deveria ser reconhecida como terminal")
        self.assertFalse(gem.endpoint_done(ep), "terminal não pode contar como DoD completo")

    def test_terminal_nao_bloqueia_next_task_indefinidamente(self):
        # first_failed_gate (a mesma lógica usada por next_task.py) deve
        # devolver None: nada pendente para repetir em loop.
        compat = gem.build_compat(None, self._prev())
        ep = compat["endpoints"]["game/gear/apply-cosmetic"]
        self.assertIsNone(gem.first_failed_gate(ep))

    def _com_fixture_client(self):
        gem.load_fixtures = lambda: {
            "game/gear/apply-cosmetic": {
                "file": "tests/fixtures/protocol/client/gear/game__gear__apply-cosmetic.json",
                "provenance": "client", "sanitized": True,
            }
        }

    def test_fixture_client_real_vence_o_marcador_terminal(self):
        self._com_fixture_client()
        compat = gem.build_compat(None, self._prev())
        ep = compat["endpoints"]["game/gear/apply-cosmetic"]
        self.assertIs(ep["request_observed"], True, "captura real de cliente deve reabrir a rota")
        self.assertIs(ep["response_observed"], True)
        self.assertFalse(gem.endpoint_terminal(ep), "com prova real não é mais terminal")

    def test_fixture_client_real_limpa_o_proprio_client_authoritative(self):
        """O marcador afirma 'o cliente NUNCA emite'. Uma captura real é a
        evidência que refuta isso: o campo tem que cair sozinho, senão fica
        mentindo `true` no registro contra a própria evidência ao lado."""
        self._com_fixture_client()
        compat = gem.build_compat(None, self._prev())
        ep = compat["endpoints"]["game/gear/apply-cosmetic"]
        self.assertIs(ep["client_authoritative"], False,
                      "o marcador terminal não pode sobreviver a uma fixture client real")

    def test_reabertura_por_fixture_client_deixa_gates_coerentes(self):
        """Cadeia completa da reabertura, sem sobra de `null` do marcador."""
        self._com_fixture_client()
        compat = gem.build_compat(None, self._prev())
        ep = compat["endpoints"]["game/gear/apply-cosmetic"]
        self.assertIs(ep["request_observed"], True)
        self.assertIs(ep["response_observed"], True)
        self.assertIs(ep["client_authoritative"], False)
        self.assertFalse(gem.endpoint_terminal(ep))
        # client_validated volta ao padrão honesto (False), NUNCA a True: a
        # fixture prova request/response observados, não que o fluxo completo
        # passou no client_harness. `null` aqui seria pior ainda — num gate de
        # DoD significa "não aplicável", e validar no cliente É aplicável.
        self.assertIs(ep["client_validated"], False,
                      "sem `null` residual do marcador e sem promoção inventada")
        self.assertEqual(gem.first_failed_gate(ep), "client_validated",
                         "a rota reaberta volta para a fila de trabalho real")

    def test_reabertura_nao_promove_rota_a_dod_completo(self):
        """Reabrir não pode virar atalho para paridade: a rota reaberta
        continua fora do DoD até a validação real de cliente existir."""
        self._com_fixture_client()
        compat = gem.build_compat(None, self._prev())
        ep = compat["endpoints"]["game/gear/apply-cosmetic"]
        self.assertFalse(gem.endpoint_done(ep))

    def test_client_authoritative_false_nao_afeta_gates(self):
        compat = gem.build_compat(None, self._prev(client_authoritative=False))
        ep = compat["endpoints"]["game/gear/apply-cosmetic"]
        self.assertIs(ep["request_observed"], False)
        self.assertIs(ep["response_observed"], False)
        self.assertFalse(gem.endpoint_terminal(ep))


if __name__ == "__main__":
    unittest.main(verbosity=2)
