#!/usr/bin/env python3
"""Testes do núcleo da autenticação Revival (scripts/revival_auth/).

Sem emulador e sem material proprietário: o layout do `gpg.config` é reproduzido
a partir do contrato documentado no módulo, e as credenciais usam valores
sintéticos. O arquivo real do dispositivo fica em `work/` (ignorado pelo Git); se
estiver presente, o teste o usa como âncora extra — se não estiver, não falha.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from revival_auth import (  # noqa: E402
    SAVE_DATA_VERSION,
    Credentials,
    CredentialsError,
    GooglePlayLocalConfig,
    GpgConfigError,
    credentials_from_register_response,
    load_credentials,
    parse_gpg_config,
    serialize_gpg_config,
    write_credentials,
)

# Valores sintéticos: nenhum vem de conta real.
DEVICE_ID = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
PASSWORD = "0123456789abcdef0123456789abcdef"   # 32, como o real
REGISTER_OK = {
    "code": 1000, "user_id": 8, "device_id": DEVICE_ID, "password": PASSWORD,
    "recovery_code": "RV-ABCDEF123456", "token": "eyJhbGciOiJIUzI1NiJ9.e30.sig",
    "session_id": 1, "puuid": "00000000-0000-4000-8000-000000000000",
}
ARQUIVO_REAL = ROOT / "work" / "audit-opus" / "60-gpg.config.bin"


class TestGpgConfig(unittest.TestCase):
    def test_round_trip_dos_quatro_estados(self):
        for cancelou in (True, False):
            for saiu in (True, False):
                cfg = GooglePlayLocalConfig(has_cancelled_login=cancelou, has_logged_out=saiu)
                self.assertEqual(parse_gpg_config(serialize_gpg_config(cfg)), cfg)

    def test_tamanho_fixo_de_180_bytes(self):
        # O layout é fixo: só os dois booleanos mudam, nunca o tamanho.
        tamanhos = {len(serialize_gpg_config(GooglePlayLocalConfig(a, b)))
                    for a in (True, False) for b in (True, False)}
        self.assertEqual(tamanhos, {180})

    def test_so_os_dois_bytes_de_valor_mudam(self):
        base = serialize_gpg_config(GooglePlayLocalConfig(False, False))
        outro = serialize_gpg_config(GooglePlayLocalConfig(True, True))
        diferentes = [i for i, (x, y) in enumerate(zip(base, outro)) if x != y]
        self.assertEqual(len(diferentes), 2, "só os valores booleanos podem diferir")
        self.assertEqual(diferentes[1] - diferentes[0], 1, "os dois valores são adjacentes")

    def test_bate_com_o_arquivo_real_quando_disponivel(self):
        if not ARQUIVO_REAL.is_file():
            self.skipTest("gpg.config real ausente (work/ não é versionado)")
        bruto = ARQUIVO_REAL.read_bytes()
        cfg = parse_gpg_config(bruto)
        self.assertEqual(serialize_gpg_config(cfg), bruto,
                         "serializador tem que reproduzir o arquivo do dispositivo byte a byte")
        # Estado medido no boot que COMPLETOU sem Google.
        self.assertTrue(cfg.has_cancelled_login)
        self.assertFalse(cfg.has_logged_out)

    def test_recusa_lixo_em_vez_de_adivinhar(self):
        bom = serialize_gpg_config(GooglePlayLocalConfig(True, False))
        for rotulo, dados in [
            ("vazio", b""),
            ("cabeçalho errado", b"\x99" + bom[1:]),
            ("truncado", bom[:-1]),
            ("MessageEnd ausente", bom[:-1] + b"\x00"),
            ("assembly trocada", bom.replace(b"Ubu.GooglePlay,", b"Outra.Coisa,,")),
        ]:
            with self.subTest(rotulo):
                with self.assertRaises(GpgConfigError):
                    parse_gpg_config(dados)

    def test_valor_nao_booleano_e_recusado(self):
        with self.assertRaises(GpgConfigError):
            serialize_gpg_config(GooglePlayLocalConfig(1, 0))  # type: ignore[arg-type]


class TestCredentials(unittest.TestCase):
    def test_create_a_partir_do_register_real(self):
        cred = credentials_from_register_response(REGISTER_OK)
        self.assertEqual(cred.user_id, 8)
        self.assertEqual(cred.device_id, DEVICE_ID, "device_id vem do servidor, não é inventado")
        self.assertEqual(cred.version, SAVE_DATA_VERSION)
        self.assertEqual(cred.region, "US")
        self.assertEqual(cred.platform, 4)

    def test_ordem_e_tipos_do_wire(self):
        wire = credentials_from_register_response(REGISTER_OK).to_wire()
        self.assertEqual(list(wire), ["version", "user_id", "device_id", "password", "region", "platform"])
        self.assertIsInstance(wire["version"], int)
        self.assertIsInstance(wire["user_id"], int)
        self.assertIsInstance(wire["platform"], int)
        self.assertIsInstance(wire["device_id"], str)

    def test_register_com_erro_nao_vira_credencial(self):
        for rotulo, payload in [
            ("code de erro", {**REGISTER_OK, "code": 2200}),
            ("sem device_id", {k: v for k, v in REGISTER_OK.items() if k != "device_id"}),
            ("sem password", {k: v for k, v in REGISTER_OK.items() if k != "password"}),
            ("device_id vazio", {**REGISTER_OK, "device_id": ""}),
            ("não é objeto", ["lista"]),
        ]:
            with self.subTest(rotulo):
                with self.assertRaises(CredentialsError):
                    credentials_from_register_response(payload)  # type: ignore[arg-type]

    def test_tipos_errados_sao_recusados(self):
        base = dict(user_id=8, device_id=DEVICE_ID, password=PASSWORD)
        for rotulo, over in [
            ("user_id string", {"user_id": "8"}),
            ("user_id bool", {"user_id": True}),
            ("user_id zero", {"user_id": 0}),
            ("device_id curto", {"device_id": "nao-e-uuid"}),
            ("region de 3 letras", {"region": "USA"}),
            ("region numérica", {"region": "12"}),
            ("version diferente", {"version": 2}),
            ("password vazio", {"password": ""}),
        ]:
            with self.subTest(rotulo):
                with self.assertRaises(CredentialsError):
                    Credentials(**{**base, **over})

    def test_erro_nunca_ecoa_o_segredo(self):
        try:
            Credentials(user_id=8, device_id="curto", password=PASSWORD)
        except CredentialsError as exc:
            self.assertNotIn("curto", str(exc))
            self.assertNotIn(PASSWORD, str(exc))
        else:
            self.fail("deveria ter levantado")

    def test_redacted_nao_vaza_valor(self):
        red = credentials_from_register_response(REGISTER_OK).redacted()
        serializado = json.dumps(red)
        self.assertNotIn(DEVICE_ID, serializado)
        self.assertNotIn(PASSWORD, serializado)
        self.assertIn("<password:32>", serializado, "tamanho é publicável; valor não")
        self.assertEqual(red["version"], SAVE_DATA_VERSION)


class TestEscrita(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.arquivo = self.dir / "credentials.json"
        self.cred = credentials_from_register_response(REGISTER_OK)

    def test_grava_e_recarrega_igual(self):
        write_credentials(self.arquivo, self.cred)
        self.assertEqual(load_credentials(self.arquivo), self.cred)

    def test_nao_sobrescreve_sem_ordem_explicita(self):
        write_credentials(self.arquivo, self.cred)
        antes = self.arquivo.read_bytes()
        with self.assertRaises(CredentialsError):
            write_credentials(self.arquivo, self.cred)
        self.assertEqual(self.arquivo.read_bytes(), antes, "credencial existente intacta")

    def test_overwrite_explicito_funciona(self):
        write_credentials(self.arquivo, self.cred)
        outra = Credentials(user_id=9, device_id=DEVICE_ID, password=PASSWORD)
        write_credentials(self.arquivo, outra, overwrite=True)
        self.assertEqual(load_credentials(self.arquivo).user_id, 9)

    def test_escrita_e_atomica_e_nao_deixa_temporario(self):
        write_credentials(self.arquivo, self.cred)
        restos = [p.name for p in self.dir.iterdir() if p.name != "credentials.json"]
        self.assertEqual(restos, [], f"temporário deixado para trás: {restos}")

    def test_falha_no_meio_nao_deixa_json_parcial(self):
        class Quebrado(Credentials):
            def to_wire(self):  # noqa: D102
                raise RuntimeError("falha simulada durante a serialização")
        quebrado = Quebrado(user_id=8, device_id=DEVICE_ID, password=PASSWORD)
        with self.assertRaises(RuntimeError):
            write_credentials(self.arquivo, quebrado)
        self.assertFalse(self.arquivo.exists(), "nenhum arquivo parcial")
        self.assertEqual(list(self.dir.iterdir()), [], "nenhum temporário órfão")

    def test_arquivo_corrompido_nao_vira_credencial(self):
        for rotulo, conteudo in [
            ("não é JSON", "{isto nao e json"),
            ("é lista", "[]"),
            ("campo a mais", json.dumps({**self.cred.to_wire(), "extra": 1})),
            ("campo a menos", json.dumps({k: v for k, v in self.cred.to_wire().items() if k != "password"})),
            ("tipo errado", json.dumps({**self.cred.to_wire(), "user_id": "8"})),
        ]:
            with self.subTest(rotulo):
                self.arquivo.write_text(conteudo, encoding="utf-8")
                with self.assertRaises(CredentialsError):
                    load_credentials(self.arquivo)

    def test_arquivo_ausente_e_erro_claro(self):
        with self.assertRaises(CredentialsError):
            load_credentials(self.dir / "nao-existe.json")


if __name__ == "__main__":
    unittest.main(verbosity=2)
