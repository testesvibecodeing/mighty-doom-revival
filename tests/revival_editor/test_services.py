#!/usr/bin/env python3
"""Regressão dos adaptadores de serviço do Revival Studio.

Usa APK sintético mínimo — nenhum material proprietário entra no Git
(§25.2 do plano: "ZIP/APK mínimo", "metadata v29 mínimo").

O caso mais importante é `test_desconhecido_nao_e_aprovacao`: sem `aapt` no
PATH o analisador não consegue provar package/versão, e a fase 4 proíbe
"aplicar regras do 1.13.1 automaticamente" nesse caso.

Execução: python tests/revival_editor/test_services.py
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from revival_editor.models import HostnameError  # noqa: E402
from revival_editor.services import (  # noqa: E402
    CaFileError,
    EXPECTED_ABI,
    EXPECTED_METADATA_VERSION,
    EXPECTED_UNITY,
    METADATA_SANITY,
    PrecheckVerdict,
    analyze_apk,
    check_hostname_budget,
    read_metadata_version,
    validate_ca_file,
)

METADATA_MEMBER = "assets/bin/Data/Managed/Metadata/global-metadata.dat"


def metadata_sintetico(*, sanity: int = METADATA_SANITY, versao: int = 29) -> bytes:
    """Header v29 mínimo: sanity + version + 30 pares (offset,size) zerados."""
    return struct.pack("<II", sanity, versao) + b"\x00" * 120


def apk_sintetico(
    destino: Path,
    *,
    metadata: bytes | None = None,
    abis: tuple[str, ...] = (EXPECTED_ABI,),
    unity: str | None = EXPECTED_UNITY,
    host: str | None = None,
) -> Path:
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("AndroidManifest.xml", b"\x03\x00\x08\x00fake-axml")
        for abi in abis:
            zf.writestr(f"lib/{abi}/libil2cpp.so", b"\x7fELF" + b"\x00" * 64)
            zf.writestr(f"lib/{abi}/libunity.so", b"\x7fELF" + b"\x00" * 64)
        if metadata is not None:
            zf.writestr(METADATA_MEMBER, metadata)
        if unity:
            zf.writestr(
                "assets/bin/Data/globalgamemanagers",
                b"\x00" * 20 + unity.encode("ascii") + b"\x00" * 64,
            )
        corpo = b"nada aqui"
        if host:
            corpo = b"prefixo https://" + host.encode() + b"/ sufixo"
        zf.writestr("assets/aa/catalog.json", corpo)
    return destino


class TestReadMetadataVersion(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_le_versao_29(self) -> None:
        apk = apk_sintetico(self.dir / "a.apk", metadata=metadata_sintetico())
        versao, erro = read_metadata_version(apk, METADATA_MEMBER)
        self.assertEqual(versao, 29)
        self.assertIsNone(erro)

    def test_sanity_errado_nao_devolve_versao(self) -> None:
        """Sanity errado significa 'não é metadata IL2CPP' — não ajuste offset."""
        apk = apk_sintetico(self.dir / "b.apk", metadata=metadata_sintetico(sanity=0xDEADBEEF))
        versao, erro = read_metadata_version(apk, METADATA_MEMBER)
        self.assertIsNone(versao)
        self.assertIn("sanity", erro)

    def test_metadata_truncado(self) -> None:
        apk = apk_sintetico(self.dir / "c.apk", metadata=b"\x00\x01")
        versao, erro = read_metadata_version(apk, METADATA_MEMBER)
        self.assertIsNone(versao)
        self.assertIn("truncado", erro)

    def test_membro_ausente(self) -> None:
        apk = apk_sintetico(self.dir / "d.apk", metadata=None)
        versao, erro = read_metadata_version(apk, METADATA_MEMBER)
        self.assertIsNone(versao)
        self.assertIsNotNone(erro)


class TestAnalyzeApk(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _analisar(self, apk: Path, package: dict | None = None):
        # try_aapt vive no CLI; substituí-lo mantém o teste independente do PATH.
        import analyze_apk as cli

        with mock.patch.object(cli, "try_aapt", lambda _: package or {}):
            return analyze_apk(apk)

    def test_extrai_os_fatos_da_fase_4(self) -> None:
        apk = apk_sintetico(self.dir / "alvo.apk", metadata=metadata_sintetico())
        r = self._analisar(
            apk,
            package={"package": "com.bethsoft.ubu", "versionName": "1.13.1", "versionCode": "84862"},
        )
        self.assertEqual(r.metadata_version, EXPECTED_METADATA_VERSION)
        self.assertEqual(r.abis, [EXPECTED_ABI])
        self.assertEqual(r.unity_version, EXPECTED_UNITY)
        self.assertEqual(r.package, "com.bethsoft.ubu")
        self.assertEqual(len(r.sha256), 64)
        self.assertEqual(r.divergences, [])
        self.assertEqual(r.unknown, [])
        self.assertTrue(r.matches_target)

    def test_desconhecido_nao_e_aprovacao(self) -> None:
        """Sem aapt, package/versão ficam A VERIFICAR e o alvo NÃO é confirmado."""
        apk = apk_sintetico(self.dir / "sem-aapt.apk", metadata=metadata_sintetico())
        r = self._analisar(apk, package={})
        self.assertEqual(r.divergences, [], "nada divergiu de fato")
        self.assertTrue(r.unknown, "package/versão/build ficaram sem medição")
        self.assertFalse(r.matches_target, "desconhecido não pode liberar edição")

    def test_versao_divergente_e_apontada(self) -> None:
        apk = apk_sintetico(self.dir / "outro.apk", metadata=metadata_sintetico())
        r = self._analisar(
            apk,
            package={"package": "com.bethsoft.ubu", "versionName": "1.14.0", "versionCode": "99999"},
        )
        self.assertFalse(r.matches_target)
        self.assertTrue(any("1.14.0" in d for d in r.divergences))

    def test_metadata_v28_diverge(self) -> None:
        apk = apk_sintetico(self.dir / "v28.apk", metadata=metadata_sintetico(versao=28))
        r = self._analisar(apk, package={})
        self.assertEqual(r.metadata_version, 28)
        self.assertTrue(any("metadata" in d for d in r.divergences))

    def test_abi_errada_diverge(self) -> None:
        apk = apk_sintetico(self.dir / "arm32.apk", metadata=metadata_sintetico(), abis=("armeabi-v7a",))
        r = self._analisar(apk, package={})
        self.assertEqual(r.abis, ["armeabi-v7a"])
        self.assertTrue(any("ABI" in d for d in r.divergences))
        self.assertTrue(any("libil2cpp" in d for d in r.divergences))

    def test_detecta_host_oficial(self) -> None:
        apk = apk_sintetico(
            self.dir / "host.apk",
            metadata=metadata_sintetico(),
            host="international.gear.bethesda.net",
        )
        r = self._analisar(apk, package={})
        self.assertTrue(r.official_host_present)

    def test_sem_host_oficial(self) -> None:
        apk = apk_sintetico(self.dir / "limpo.apk", metadata=metadata_sintetico())
        self.assertFalse(self._analisar(apk, package={}).official_host_present)

    def test_relatorio_e_json_serializavel(self) -> None:
        import json

        apk = apk_sintetico(self.dir / "rel.apk", metadata=metadata_sintetico())
        destino = self.dir / "sub" / "analyze.json"
        import analyze_apk as cli

        with mock.patch.object(cli, "try_aapt", lambda _: {}):
            analyze_apk(apk, report_path=destino)
        dados = json.loads(destino.read_text(encoding="utf-8"))
        self.assertIn("sha256", dados)
        self.assertIn("matches_target", dados)

    def test_apk_inexistente(self) -> None:
        with self.assertRaises(FileNotFoundError):
            analyze_apk(self.dir / "nao-existe.apk")

    def test_nao_altera_o_apk_de_entrada(self) -> None:
        """O APK de entrada é imutável (AGENTS.md / §5 do plano)."""
        apk = apk_sintetico(self.dir / "imutavel.apk", metadata=metadata_sintetico())
        antes = apk.read_bytes()
        self._analisar(apk, package={})
        self.assertEqual(apk.read_bytes(), antes)


class TestCheckHostnameBudget(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.apk = apk_sintetico(
            self.dir / "orcamento.apk",
            metadata=metadata_sintetico(),
            host="international.gear.bethesda.net",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_host_curto_cabe_no_fast_path(self) -> None:
        r = check_hostname_budget(self.apk, "doom.exemplo.com")
        self.assertEqual(r.exit_code, 0)
        self.assertEqual(r.verdict, PrecheckVerdict.FAST_PATH)
        self.assertTrue(r.can_fast_path)
        self.assertFalse(r.blocks_pipeline)

    def test_exit_4_nao_bloqueia_o_pipeline(self) -> None:
        """Exit 4 é 'siga para bundle-aware', não fatal (skill apk-patch)."""
        r = check_hostname_budget(self.apk, "a" * 28 + ".com")
        self.assertEqual(r.exit_code, 4)
        self.assertEqual(r.verdict, PrecheckVerdict.BUNDLE_AWARE)
        self.assertFalse(r.can_fast_path)
        self.assertFalse(r.blocks_pipeline, "exit 4 não pode parar o pipeline")
        self.assertIsNone(r.failure)

    def test_normaliza_o_host_antes_de_medir(self) -> None:
        r = check_hostname_budget(self.apk, "  HTTPS://Doom.Exemplo.COM  ")
        self.assertEqual(r.host, "doom.exemplo.com")

    def test_url_com_path_e_recusada_antes_do_precheck(self) -> None:
        with self.assertRaises(HostnameError):
            check_hostname_budget(self.apk, "https://doom.exemplo.com/collections/doom")

    def test_apk_inexistente(self) -> None:
        with self.assertRaises(FileNotFoundError):
            check_hostname_budget(self.dir / "nao-existe.apk", "doom.exemplo.com")


def _saude_do_servador(**sobrepos) -> dict:
    """Payload plano que o `check_server` real devolve no sucesso."""
    bruto = {
        "verified": True,
        "url": "https://doom.exemplo.com/revival/health",
        "http_status": 200,
        "content_type": "application/json",
        "server": "revival-node/1.0",
        "client_version": "1.13.1",
        "api_version": "24.0.0",
        "game_data_loaded": True,
        "research_mode": False,
        "runtime": "node",
        "gear_prefix": {
            "collection": "doom",
            "health_url": "https://doom.exemplo.com/collections/doom/revival/health",
            "health_status": 200,
            "auth_probe_url": "https://doom.exemplo.com/collections/doom/game/auth/register",
            "auth_probe_status": 400,
            "auth_probe_code": 2200,
            "auth_probe_uts": "2026-08-18T12:00:00",
            "auth_probe_content_type": "application/json",
        },
    }
    bruto.update(sobrepos)
    return bruto


class TestServerPreflight(unittest.TestCase):
    """Fase 5: DNS, TLS e health como checks separados — sem inventar verde.

    O `check_server` real devolve dict PLANO e comunica falha por exceção;
    estes testes travam esse contrato (o adaptador antigo lia `ok`/`checks`
    que não existem — servidor saudável reportava falha).
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _preflight(self, efeito, **kw):
        import check_revival_server as cli
        import revival_editor.services as svc

        with mock.patch.object(cli, "check_server", efeito):
            return svc.server_preflight("https://doom.exemplo.com", **kw)

    def test_servidor_saudavel_ok_com_checks_separados(self) -> None:
        resultado = self._preflight(lambda *a, **kw: _saude_do_servador())
        self.assertTrue(resultado.ok, str(resultado.errors))
        self.assertEqual(resultado.client_version, "1.13.1")
        self.assertEqual(resultado.api_version, "24.0.0")
        self.assertTrue(resultado.game_data_loaded)
        self.assertEqual(resultado.uts, "2026-08-18T12:00:00")
        for check in ("dns", "tls", "health", "gear_prefix"):
            self.assertIn(check, resultado.checks, f"check {check} ausente")
            self.assertTrue(resultado.checks[check]["ok"], resultado.checks[check])
        self.assertIsNone(resultado.failure)

    def test_falha_de_dns_isolada(self) -> None:
        import socket
        import urllib.error

        def explode(*a, **kw):
            raise urllib.error.URLError(socket.gaierror(8, "Name or service not known"))

        resultado = self._preflight(explode)
        self.assertFalse(resultado.ok)
        self.assertFalse(resultado.checks["dns"]["ok"])
        self.assertIn("não resolve", resultado.checks["dns"]["detail"])
        self.assertNotIn("tls", resultado.checks, "TLS não pode ser provado sem DNS")
        self.assertNotIn("health", resultado.checks)
        self.assertEqual(resultado.failure.code, "SERVER_PREFLIGHT")
        self.assertIn("dns", resultado.failure.message)

    def test_falha_de_tls_isolada(self) -> None:
        import ssl
        import urllib.error

        def explode(*a, **kw):
            raise urllib.error.URLError(
                ssl.SSLCertVerificationError(
                    1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"
                )
            )

        resultado = self._preflight(explode)
        self.assertFalse(resultado.ok)
        self.assertTrue(resultado.checks["dns"]["ok"], "resolveu — DNS não é o problema")
        self.assertFalse(resultado.checks["tls"]["ok"])
        self.assertIn("CERTIFICATE", resultado.checks["tls"]["detail"])
        self.assertNotIn("health", resultado.checks, "health não rodou sem handshake")

    def test_falha_de_contrato_marca_dns_e_tls_provos(self) -> None:
        def explode(*a, **kw):
            raise RuntimeError("servidor Revival incompatível: client_version='1.12.0'")

        resultado = self._preflight(explode)
        self.assertFalse(resultado.ok)
        self.assertTrue(resultado.checks["dns"]["ok"], "HTTPS respondeu: DNS provado")
        self.assertTrue(resultado.checks["tls"]["ok"], "handshake completo: TLS provado")
        self.assertFalse(resultado.checks["health"]["ok"])

    def test_ca_publica_e_ca_local_chegam_ao_cli_separadas(self) -> None:
        """Gate da fase 5: os dois perfis passam pelo mesmo gate, sem ignorar TLS."""
        import check_revival_server as cli
        import revival_editor.services as svc

        chamadas: list[tuple[str, Path | None]] = []

        def registra(host, ca, timeout, require_game_data=True):
            chamadas.append((host, ca))
            return _saude_do_servador()

        ca = self.dir / "ca-local.pem"
        ca.write_text(
            "-----BEGIN CERTIFICATE-----\nlocal\n-----END CERTIFICATE-----\n", encoding="utf-8"
        )
        with mock.patch.object(cli, "check_server", registra):
            publica = svc.server_preflight("doom.exemplo.com")
            local = svc.server_preflight("doom.exemplo.com", ca_file=ca)
        self.assertIsNone(chamadas[0][1], "perfil público: sem CA")
        self.assertEqual(chamadas[1][1], ca, "perfil local: CA informada")
        self.assertTrue(publica.ok and local.ok)
        self.assertIn("certificado público", publica.checks["tls"]["detail"])
        self.assertIn("CA local", local.checks["tls"]["detail"])

    def test_ca_ausente_e_erro_de_chamada(self) -> None:
        import revival_editor.services as svc

        with self.assertRaises(FileNotFoundError):
            svc.server_preflight("doom.exemplo.com", ca_file=self.dir / "sumiu.pem")

    def test_relatorio_sem_segredo_nem_chave_privada(self) -> None:
        destino = self.dir / "server-preflight.json"
        resultado = self._preflight(
            lambda *a, **kw: _saude_do_servador(), report_path=destino
        )
        texto = destino.read_text(encoding="utf-8")
        self.assertIn('"ok": true', texto)
        self.assertNotIn("PRIVATE KEY", texto)
        self.assertNotIn("-----BEGIN", texto)

    def test_hostname_invalido_recusado_antes_da_rede(self) -> None:
        import revival_editor.services as svc

        with self.assertRaises(HostnameError):
            svc.server_preflight("https://doom.exemplo.com/collections/doom")


class TestValidateCaFile(unittest.TestCase):
    """Gate da fase 5: CA validada sem copiar chave privada."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _ca(self, nome: str, conteudo: str) -> Path:
        caminho = self.dir / nome
        caminho.write_text(conteudo, encoding="utf-8")
        return caminho

    def test_certificado_publico_valido(self) -> None:
        ca = self._ca(
            "publica.pem", "-----BEGIN CERTIFICATE-----\nabc123\n-----END CERTIFICATE-----\n"
        )
        info = validate_ca_file(ca)
        self.assertEqual(info.certificates, 1)
        self.assertEqual(info.size_bytes, ca.stat().st_size)
        self.assertEqual(info.sha256, hashlib.sha256(ca.read_bytes()).hexdigest())
        self.assertNotIn("abc123", json.dumps(info.to_dict()), "corpo PEM não entra em relatório")

    def test_bundle_com_varios_certificados(self) -> None:
        ca = self._ca(
            "bundle.pem",
            "-----BEGIN CERTIFICATE-----\num\n-----END CERTIFICATE-----\n"
            "-----BEGIN CERTIFICATE-----\ndois\n-----END CERTIFICATE-----\n",
        )
        self.assertEqual(validate_ca_file(ca).certificates, 2)

    def test_chave_privada_recusada(self) -> None:
        ca = self._ca(
            "com-chave.pem",
            "-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----\n"
            "-----BEGIN RSA PRIVATE KEY-----\nshh\n-----END RSA PRIVATE KEY-----\n",
        )
        with self.assertRaises(CaFileError) as cm:
            validate_ca_file(ca)
        self.assertIn("chave privada", str(cm.exception))

    def test_chave_privada_ec_recusada(self) -> None:
        ca = self._ca(
            "ec.pem", "-----BEGIN EC PRIVATE KEY-----\nshh\n-----END EC PRIVATE KEY-----\n"
        )
        with self.assertRaises(CaFileError):
            validate_ca_file(ca)

    def test_sem_certificado_recusado(self) -> None:
        ca = self._ca("csr.txt", "Certificate Request: xyz")
        with self.assertRaises(CaFileError) as cm:
            validate_ca_file(ca)
        self.assertIn("CERTIFICATE", str(cm.exception))

    def test_arquivo_ausente_recusado(self) -> None:
        with self.assertRaises(CaFileError):
            validate_ca_file(self.dir / "nao-existe.pem")


if __name__ == "__main__":
    unittest.main(verbosity=2)
