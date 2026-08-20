#!/usr/bin/env python3
"""Testes da cadeia de evidência do client_harness (P0 captura real).

Sem ADB e sem servidor real: exercita as funções puras (sanitização, delta,
sequência, fluxos, veredito) e o gate de credencial do main() — captura
solicitada sem token sai em exit 2 antes de qualquer mutação.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import client_harness as hch  # noqa: E402


def log_row(row_id: int, path: str, body=None, response=None, status=200, code=1000, note=None):
    return {
        "id": row_id, "user_id": 1, "path": path, "method": "POST", "status": status,
        "code": code, "note": note,
        "body_json": None if body is None else json.dumps(body),
        "response_json": None if response is None else json.dumps(response),
        "created_at": 1700000000 + row_id,
    }


class TestSanitize(unittest.TestCase):
    def test_redige_segredos_preservando_shape(self):
        wire = {
            "uts": "2026-08-19T10:00:00", "code": 1000,
            "token": "eyJhbGciOiJIUo.eyJzdWIiOiIxIn0.sig",
            "password": "senhasecreta", "recovery_code": "RV-ABCDEF123456",
            "device_id": "device-xyz", "push_token": None,
            "legal": {"tos_version": 1, "allow_sharing": False},
            "items": [{"id": 1, "token": "eyJx.y.z"}],
        }
        out = hch.sanitize_value(wire)
        self.assertEqual(out["uts"], "<uts>")
        self.assertEqual(out["code"], 1000)
        self.assertEqual(out["token"], "<token>")
        self.assertEqual(out["password"], "<password>")
        self.assertEqual(out["recovery_code"], "<recovery-code>")
        self.assertEqual(out["device_id"], "<device-id>")
        self.assertIsNone(out["push_token"], "null preservado (nullabilidade)")
        self.assertEqual(out["legal"]["tos_version"], 1)
        self.assertFalse(out["legal"]["allow_sharing"])
        self.assertEqual(out["items"][0]["token"], "<token>")
        self.assertEqual(out["items"][0]["id"], 1)

    def test_puuid_vira_placeholder_preservando_chave_e_tipo(self):
        # puuid não é credencial — é o identificador estável da conta no wire.
        # A fixture versionada guarda a chave e o tipo, nunca o valor.
        out = hch.sanitize_value({
            "user_id": 8,
            "puuid": "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
            "nested": {"puuid": "00000000-0000-4000-8000-000000000000"},
            "sem_valor": {"puuid": None},
        })
        self.assertEqual(out["puuid"], "<puuid>")
        self.assertEqual(out["nested"]["puuid"], "<puuid>")
        self.assertIsNone(out["sem_valor"]["puuid"], "null preservado (nullabilidade)")
        self.assertEqual(out["user_id"], 8, "identificador numérico do contrato não é segredo")

    def test_device_id_numerico_nao_vira_string(self):
        # game/devices/describe e game/devices/unregister usam device_id como id
        # NUMÉRICO da linha de dispositivo — não é a credencial UUID de
        # game/auth/*. Redigir o inteiro mudaria o TIPO do wire (DEAD-ENDS #3).
        out = hch.sanitize_value({"device_id": 1, "user_id": 8})
        self.assertEqual(out["device_id"], 1)
        self.assertIsInstance(out["device_id"], int)
        self.assertNotIsInstance(out["device_id"], str)
        # e o caso string (credencial de auth) continua redigido
        self.assertEqual(
            hch.sanitize_value({"device_id": "3f2504e0-4f89-11d3-9a0c-0305e82c3301"})["device_id"],
            "<device-id>")

    def test_jwt_e_bearer_soltos_sao_redigidos(self):
        self.assertEqual(hch.sanitize_value("eyJhbGciOiJIUzI1NiJ9.eyJhIjoxfQ.sig"), "<token>")
        self.assertEqual(hch.sanitize_value("Bearer abc123def456"), "Bearer <token>")

    def test_url_perde_host_mas_guarda_path(self):
        self.assertEqual(hch.sanitize_value("https://doom.exemplo.br/data"), "<base>/data")
        self.assertEqual(hch.sanitize_value("http://192.168.0.10:8080/data"), "<base>/data")

    def test_campos_volateis_zeram(self):
        out = hch.sanitize_value({"account_age": 12345, "last_login": 99})
        self.assertEqual(out, {"account_age": 0, "last_login": 0})

    def test_nao_inventa_chave_ausente(self):
        self.assertEqual(hch.sanitize_value({"a": 1}), {"a": 1})
        self.assertEqual(hch.sanitize_value([1, "x"]), [1, "x"])


class TestFixture(unittest.TestCase):
    def test_fixture_so_existe_com_response_pareado(self):
        row = log_row(1, "/game/auth/register", body={"client_version": "1.13.1"},
                      response={"uts": "x", "code": 1000})
        fixture = hch.build_fixture(row, "2026-08-19T00:00:00Z")
        self.assertIsNotNone(fixture)
        self.assertEqual(fixture["provenance"], "client")
        self.assertIs(fixture["sanitized"], True)
        self.assertEqual(fixture["endpoint"], "game/auth/register")
        self.assertEqual(fixture["response"]["status"], 200)
        self.assertIsNotNone(fixture["request"]["body"])

    def test_sem_response_nao_ha_fixture(self):
        self.assertIsNone(hch.build_fixture(log_row(1, "/game/gear/upgrade", body={}), "ts"))
        self.assertIsNone(hch.build_fixture(log_row(1, "/game/gear/upgrade", response={"code": 1}, status=None), "ts"))

    def test_rota_fora_de_game_ignorada(self):
        self.assertIsNone(hch.build_fixture(log_row(1, "/account/login", response={"ok": 1}), "ts"))

    def test_write_fixtures_um_por_endpoint_ultima_chamada(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = hch.FIXTURES_CLIENT_DIR
            hch.FIXTURES_CLIENT_DIR = Path(tmp)
            try:
                rows = [
                    log_row(1, "/game/gear/upgrade", response={"code": 1000, "uts": "a"}),
                    log_row(2, "/game/gear/upgrade", response={"code": 1000, "uts": "b"}),
                    log_row(3, "/game/player/user-data", response={"code": 1000, "user_data": {}}),
                    log_row(4, "/game/session/heartbeat", response=None),
                ]
                written = hch.write_client_fixtures(rows, "2026-08-19T00:00:00Z")
            finally:
                hch.FIXTURES_CLIENT_DIR = original
            self.assertEqual(len(written), 2, "heartbeat sem response não vira fixture")
            gear = json.loads((Path(tmp) / "gear" / "game__gear__upgrade.json").read_text(encoding="utf-8"))
            self.assertEqual(gear["response"]["body"]["uts"], "<uts>", "captura mais recente + sanitizada")
            player = json.loads((Path(tmp) / "player" / "game__player__user-data.json").read_text(encoding="utf-8"))
            self.assertEqual(player["endpoint"], "game/player/user-data")


class TestResearchDelta(unittest.TestCase):
    def test_baseline_exclui_fallbacks_antigos(self):
        before = {"fallback_total": 10, "fallback_endpoints": [
            {"path": "/game/old/route", "count": 10, "first_seen": 1, "last_seen": 1}]}
        after = {"fallback_total": 12, "fallback_endpoints": [
            {"path": "/game/old/route", "count": 10},
            {"path": "/game/new/route", "count": 2}]}
        delta = hch.research_delta(before, after)
        self.assertEqual(delta["delta"], {"game/new/route": 2}, "fallback anterior ao baseline não contamina")
        self.assertEqual(delta["total"], 2)
        self.assertFalse(delta["reset"])

    def test_reset_de_servidor_detectado(self):
        delta = hch.research_delta({"fallback_total": 50, "fallback_endpoints": []},
                                   {"fallback_total": 1, "fallback_endpoints": [{"path": "/x", "count": 1}]})
        self.assertTrue(delta["reset"])

    def test_indisponivel_nao_finge_delta(self):
        delta = hch.research_delta({"error": "x"}, {"error": "y"})
        self.assertTrue(delta["unavailable"])


class TestSequence(unittest.TestCase):
    def test_sequencia_preserva_ordem_temporal(self):
        rows = [
            log_row(3, "/game/player/user-data", response={}),
            log_row(1, "/game/auth/register", response={}),
            log_row(2, "/game/auth/login-device", response={}),
        ]
        sequence, counts = hch.summarize_sequence(rows)
        self.assertEqual([e["endpoint"] for e in sequence],
                         ["game/auth/register", "game/auth/login-device", "game/player/user-data"])
        self.assertEqual([e["id"] for e in sequence], [1, 2, 3])
        self.assertEqual({c["endpoint"]: c["calls"] for c in counts}["game/auth/register"], 1)

    def test_resumo_por_contagem_separado_da_sequencia(self):
        rows = [log_row(1, "/game/session/heartbeat", response={}),
                log_row(2, "/game/session/heartbeat", response={})]
        sequence, counts = hch.summarize_sequence(rows)
        self.assertEqual(len(sequence), 2)
        self.assertEqual(counts, [{"endpoint": "game/session/heartbeat", "calls": 2}])

    def test_rotas_nao_game_nao_entram(self):
        sequence, counts = hch.summarize_sequence([log_row(1, "/revival/health", response={})])
        self.assertEqual(sequence, [])
        self.assertEqual(counts, [])


class TestFlows(unittest.TestCase):
    def test_boot_exige_auth_e_user_data(self):
        milestones = hch.resolve_profile("boot")["milestones"]
        ok = hch.evaluate_milestones(milestones, {"game/auth/login-device", "game/player/user-data"})
        self.assertTrue(all(m["matched"] for m in ok), "login-device satisfaz o any_of do auth")

    def test_fluxo_com_endpoint_obrigatorio_ausente_falha(self):
        milestones = hch.resolve_profile("boot")["milestones"]
        status = hch.evaluate_milestones(milestones, {"game/auth/register"})
        missing = [m["label"] for m in status if not m["matched"]]
        self.assertEqual(missing, ["game/player/user-data"])

    def test_menu_herdando_boot(self):
        milestones = hch.resolve_profile("menu")["milestones"]
        routes = [m.get("endpoint") for m in milestones]
        self.assertIn("game/player/user-data", routes, "menu herda boot via extends")
        self.assertIn("game/events/get-schedule", routes)


class TestSignatures(unittest.TestCase):
    # Linha real do rig local (work/harness/fase4-restart1.json, 22:57:07.281).
    CAST = ("08-19 22:57:07.281  4533  4585 E Unity   : ArgumentException: Could not "
            "cast or convert from System.String to System.String[].")

    def test_cast_string_array_e_fatal(self):
        achados = hch.scan_logcat(self.CAST)
        self.assertEqual(len(achados), 1, "a assinatura tem que ser reconhecida")
        self.assertEqual(achados[0]["severity"], "fatal")
        self.assertIn("aud/audience", achados[0]["description"])

    def test_cast_string_array_corta_a_janela_cedo(self):
        hits = hch.early_stop_hits(self.CAST)
        self.assertEqual(len(hits), 1)
        self.assertIn(hits[0]["signature"], hch.EARLY_STOP_SIGNATURES)

    def test_early_stop_nao_dispara_com_warning_nem_com_log_limpo(self):
        # O warning do JWT convive com boot são (DEAD-ENDS #9): não corta nada.
        warning = "E Unity : Session token is not a well formed JWT as expected"
        self.assertEqual(hch.early_stop_hits(warning), [])
        self.assertEqual(hch.scan_logcat(warning)[0]["severity"], "warning")
        self.assertEqual(hch.early_stop_hits("I Unity : nada de anormal aqui"), [])

    def test_early_stop_e_subconjunto_dos_fatais(self):
        fatais = {p for p, sev, _ in hch.SIGNATURES if sev == "fatal"}
        self.assertTrue(hch.EARLY_STOP_SIGNATURES <= fatais,
                        "early-stop não pode conter padrão que não é fatal")

    def test_fatal_reprova_o_veredito(self):
        verdict, _ = hch.decide_verdict(
            has_fatal=bool(hch.scan_logcat(self.CAST)), capture_error=False,
            missing_milestones=[], required_missing=[], validated_fallbacks=[],
            capture_requested=True, flow="boot", diagnostic=False)
        self.assertEqual(verdict, "failed",
                         "cast String->String[] não pode terminar em flow_validated")


class TestLanding(unittest.TestCase):
    """Prova de ATERRISSAGEM: onde o tráfego caiu, não onde dissemos que cairia.

    Medido em 2026-08-19: as sete execuções do rig declararam o MESMO --server,
    inclusive a única boa — comparar host declarado não separou nada. E
    client_version/api_version eram idênticos entre local e VPS.
    """

    BASE = dict(apk_host="doom.exemplo.br", expected_host="doom.exemplo.br",
                launched=True, window_seconds=200.0,
                instance={"identified": True, "instance_id": "local-rig", "build_id": "fea3c185"})

    def landing(self, **over):
        return hch.landing_evidence(**{**self.BASE, **over})

    def test_sucesso_cursor_andou_com_requests(self):
        land = self.landing(cursor_before=10, cursor_after=22, requests_in_window=12)
        self.assertTrue(land["cursor_advanced"])
        self.assertIn("aterrissou nesta instância", land["proves"])
        self.assertEqual(land["does_not_prove"], [])
        self.assertIsNone(hch.landing_verdict(land))

    def test_cursor_imovel_vira_no_observed_traffic(self):
        land = self.landing(cursor_before=264, cursor_after=264, requests_in_window=0)
        self.assertFalse(land["cursor_advanced"])
        self.assertEqual(hch.landing_verdict(land), "no_observed_traffic")
        verdict, validado = hch.decide_verdict(
            has_fatal=False, capture_error=False,
            missing_milestones=["game/player/user-data"], required_missing=[],
            validated_fallbacks=[], capture_requested=True, flow="boot",
            diagnostic=False, landing=land)
        self.assertEqual(verdict, "no_observed_traffic",
                         "não pode virar sucesso nem se esconder atrás de 'milestone ausente'")
        self.assertFalse(validado)

    def test_cursor_imovel_nao_escolhe_entre_H1_e_H2(self):
        land = self.landing(cursor_before=264, cursor_after=264, requests_in_window=0)
        self.assertIn("nenhum tráfego observado", land["proves"])
        # As três hipóteses ficam explicitamente NÃO provadas.
        self.assertEqual(len(land["does_not_prove"]), 3)
        texto = " ".join(land["does_not_prove"])
        self.assertIn("rig de interceptação quebrado", texto)
        self.assertIn("outra instância", texto)
        self.assertIn("sessão persistida", texto)

    def test_host_declarado_divergente_e_sinalizado(self):
        land = self.landing(apk_host="doom.exemplo.br", expected_host="outro.exemplo.br",
                            cursor_before=10, cursor_after=22, requests_in_window=12)
        self.assertFalse(land["declared_host_matches"])
        # Guard SECUNDÁRIO: divergência de host declarado não decide o veredito.
        self.assertIsNone(hch.landing_verdict(land))

    def test_instancia_sem_identificador_e_fato_registrado(self):
        land = self.landing(cursor_before=1, cursor_after=2, requests_in_window=1,
                            instance=hch.instance_fingerprint(
                                {"ok": True, "client_version": "1.13.1", "api_version": "24.0.0"}))
        self.assertFalse(land["instance"]["identified"])
        self.assertIn("instance.js", land["instance"]["reason"])
        # instância nova responde com identidade
        nova = hch.instance_fingerprint({"instance_id": "vps", "build_id": "abc123",
                                         "boot_id": "u-u-i-d", "build_id_source": "env"})
        self.assertTrue(nova["identified"])
        self.assertEqual(nova["build_id"], "abc123")

    def test_cursor_andou_fora_da_janela_nao_conta(self):
        # O delta da execução é 0, mas o cursor da instância avançou: tráfego de
        # OUTRA fonte. Sem requests pareados nesta janela não há prova de fluxo.
        land = self.landing(cursor_before=100, cursor_after=103, requests_in_window=0)
        self.assertTrue(land["cursor_advanced"])
        self.assertEqual(land["requests_in_window"], 0)
        self.assertIn("nenhum tráfego observado", land["proves"],
                      "cursor que anda sem requests pareados não prova fluxo desta execução")

    def test_sem_acao_de_rede_nao_ha_desfecho_precoce(self):
        # --no-launch: ninguém pediu rede, cursor parado é esperado.
        land = self.landing(cursor_before=5, cursor_after=5, requests_in_window=0, launched=False)
        self.assertFalse(land["network_expected"])
        self.assertIsNone(hch.landing_verdict(land),
                          "ausência legítima de ação de rede não pode reprovar")

    def test_cursor_indisponivel_nao_inventa_veredito(self):
        land = self.landing(cursor_before=None, cursor_after=None, requests_in_window=0)
        self.assertIsNone(hch.landing_verdict(land))
        self.assertFalse(land["cursor_advanced"])


class TestApkProof(unittest.TestCase):
    def _relatorio(self, dados):
        arq = Path(tempfile.mkdtemp()) / "verify.json"
        arq.write_text(json.dumps(dados), encoding="utf-8")
        return arq

    def test_relatorio_verificado_vira_prova(self):
        p = self._relatorio({"verified": True, "server_host": "doom.exemplo.br",
                             "sha256": "a" * 64, "target_occurrences": 14,
                             "official_occurrences": 0})
        prova = hch.apk_proof(p)
        self.assertTrue(prova["proven"])
        self.assertEqual(prova["host"], "doom.exemplo.br")
        self.assertEqual(prova["apk_sha256"], "a" * 64)

    def test_host_oficial_presente_invalida_a_prova(self):
        p = self._relatorio({"verified": True, "server_host": "doom.exemplo.br",
                             "official_occurrences": 2})
        prova = hch.apk_proof(p)
        self.assertFalse(prova["proven"])
        self.assertIn("oficial", prova["reason"])

    def test_sem_relatorio_nao_ha_prova_nem_erro(self):
        prova = hch.apk_proof(None)
        self.assertFalse(prova["proven"])
        self.assertIn("sem --apk-verify-report", prova["reason"])

    def test_relatorio_ilegivel_e_declarado(self):
        prova = hch.apk_proof(Path(tempfile.mkdtemp()) / "nao-existe.json")
        self.assertFalse(prova["proven"])
        self.assertIn("ilegível", prova["reason"])


class TestVerdict(unittest.TestCase):
    def test_sem_captura_e_inconclusive_exceto_diagnostico_declarado(self):
        verdict, _ = hch.decide_verdict(has_fatal=False, capture_error=False, missing_milestones=[],
                                        required_missing=[], validated_fallbacks=[],
                                        capture_requested=False, flow=None, diagnostic=False)
        self.assertEqual(verdict, "inconclusive")
        verdict, _ = hch.decide_verdict(has_fatal=False, capture_error=False, missing_milestones=[],
                                        required_missing=[], validated_fallbacks=[],
                                        capture_requested=False, flow=None, diagnostic=True)
        self.assertEqual(verdict, "diagnostic_clean")

    def test_capturado_diferencia_flow_validated(self):
        base = dict(has_fatal=False, capture_error=False, missing_milestones=[],
                    required_missing=[], validated_fallbacks=[], capture_requested=True,
                    diagnostic=False)
        verdict, flow = hch.decide_verdict(**base, flow="boot")
        self.assertEqual((verdict, flow), ("flow_validated", True))
        verdict, flow = hch.decide_verdict(**base, flow=None)
        self.assertEqual((verdict, flow), ("captured", False))

    def test_fatal_milestone_e_fallback_falam(self):
        base = dict(capture_error=False, required_missing=[], capture_requested=True,
                    flow="boot", diagnostic=False)
        self.assertEqual(hch.decide_verdict(**base, has_fatal=True, missing_milestones=[],
                                            validated_fallbacks=[])[0], "failed")
        self.assertEqual(hch.decide_verdict(**base, has_fatal=False,
                                            missing_milestones=["game/player/user-data"],
                                            validated_fallbacks=[])[0], "failed")
        self.assertEqual(hch.decide_verdict(**base, has_fatal=False, missing_milestones=[],
                                            validated_fallbacks=["game/chapters/start"])[0], "failed")

    def test_registro_nao_muda_em_execucao_inconclusiva(self):
        for verdict in ("inconclusive", "failed", "diagnostic_clean"):
            self.assertFalse(hch.should_update_registry(verdict))
        for verdict in ("captured", "flow_validated"):
            self.assertTrue(hch.should_update_registry(verdict))

    def test_comando_de_registro_marca_fallback_e_milestone(self):
        command = hch.registry_update_command(
            flow_validated=True,
            fallback_routes=["game/gear/upgrade"],
            milestone_routes=["game/auth/register", "game/player/user-data"],
            note="client_harness 2026-08-19 fluxo boot",
        )
        self.assertIn("game/gear/upgrade=uses_fallback=true", command)
        self.assertIn("game/auth/register=client_validated=true", command)
        self.assertIn("game/player/user-data=client_validated=true", command)
        notes = [command[i + 1] for i, arg in enumerate(command) if arg == "--note"]
        self.assertEqual(len(notes), 2)

    def test_sem_evidencia_nao_gera_comando(self):
        self.assertIsNone(hch.registry_update_command(False, [], [], "nota"))


class TestCredentialGate(unittest.TestCase):
    def test_captura_sem_token_exit2_sem_mutacao(self):
        compat = Path(__file__).resolve().parent.parent / "compatibility.json"
        before = compat.read_bytes()
        env_token = ""  # força ausência mesmo que a shell tenha a env
        import os
        original = os.environ.pop("REVIVAL_ADMIN_TOKEN", None)
        try:
            code = hch.main(["--server", "http://127.0.0.1:9", "--capture-fixtures"])
        finally:
            if original is not None:
                os.environ["REVIVAL_ADMIN_TOKEN"] = original
        self.assertEqual(code, 2)
        self.assertEqual(compat.read_bytes(), before, "nenhuma mutação no registro")
        self.assertFalse(env_token)


if __name__ == "__main__":
    unittest.main(verbosity=2)
