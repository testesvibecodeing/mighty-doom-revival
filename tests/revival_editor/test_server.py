#!/usr/bin/env python3
"""Regressão do serviço de servidor local (planos §6.1 e §9.2).

Cobre `revival_editor.server` sem exigir Node.js nem rede: o Node é validado
via `check_node` mockado, os passos de `node --check`/smoke passam por um
ctx falso que registra argv, e o health/spawn são patcheados. As regras que
importam estão testadas de verdade:

- configs locais **nunca** são sobrescritos (example copiado só quando falta);
- iniciar sem `.env` recusa e aponta o preparo;
- iniciar é idempotente (health já verde não cria segundo processo);
- subir sem health encerra o processo que nós mesmos iniciamos;
- encerrar sem PID registrado, mas com health vivo, recusa (não mata
  processo desconhecido).
Execução: python tests/revival_editor/test_server.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from revival_editor import server as srv  # noqa: E402


class _CtxFake:
    """JobContext mínimo: registra argv e devolve rc configurável."""

    def __init__(self, rc_por_comando: dict[str, int] | None = None) -> None:
        self.chamadas: list[list[str]] = []
        self.rc_por_comando = rc_por_comando or {}
        self.progressos: list[str] = []

    def run_process(self, command, *, cwd=None, env=None, stage="processo", timeout=None):
        argv = [str(c) for c in command]
        self.chamadas.append(argv)
        texto = " ".join(argv)
        for marca, rc in self.rc_por_comando.items():
            if marca in texto:
                return rc
        return 0

    def progress(self, stage, mensagem, extra):
        self.progressos.append(mensagem)

    def raise_if_cancelled(self):
        return None

    def log(self, *args, **kwargs):
        return None


def _repo_fake(tmp: Path) -> Path:
    """Repositório mínimo: examples presentes, configs locais ausentes."""
    raiz = tmp / "repo"
    server = raiz / "server"
    for rel in (
        ".env.example",
        "config/revival.example.json",
        "config/packs.example.json",
        "config/events.example.json",
    ):
        destino = server / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text('{"exemplo": true}\n', encoding="utf-8")
    for rel in srv.CHECK_FILES:
        destino = server / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text("// sintese\n", encoding="utf-8")
    return raiz


def _node_ok(*args, **kwargs):
    return ("v24.0.0", None)


class TestPrepareServer(unittest.TestCase):
    def test_copia_configs_faltantes_e_preserva_existentes(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            raiz = _repo_fake(Path(tmp))
            ctx = _CtxFake()
            with mock.patch.object(srv, "check_node", _node_ok), \
                    mock.patch.object(srv, "resolve_node", lambda: "node"):
                primeiro = srv.prepare_server(raiz, ctx)
            self.assertTrue(primeiro.ok, primeiro.erro)
            self.assertEqual(len(primeiro.copied), 4, "4 examples deveriam virar configs locais")
            self.assertTrue((raiz / "server" / ".env").is_file())
            self.assertTrue((raiz / "server" / "config" / "revival.json").is_file())

            # .env personalizado NÃO pode ser sobrescrito na segunda execução
            env_local = raiz / "server" / ".env"
            env_local.write_text("PORT=9123\nREVIVAL_ADMIN_TOKEN=segredo\n", encoding="utf-8")
            with mock.patch.object(srv, "check_node", _node_ok), \
                    mock.patch.object(srv, "resolve_node", lambda: "node"):
                segundo = srv.prepare_server(raiz, _CtxFake())
            self.assertTrue(segundo.ok, segundo.erro)
            self.assertEqual(segundo.copied, [], "configs existentes não podem ser recopiados")
            self.assertIn("PORT=9123", env_local.read_text(encoding="utf-8"))

    def test_rejeita_node_ausente_antes_de_tocar_configs(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            raiz = _repo_fake(Path(tmp))
            with mock.patch.object(srv, "check_node", lambda: (None, "Node.js não encontrado")):
                relatorio = srv.prepare_server(raiz, _CtxFake())
            self.assertFalse(relatorio.ok)
            self.assertIn("Node.js", relatorio.erro)
            self.assertFalse((raiz / "server" / ".env").exists(), "falha de Node não cria config")

    def test_falha_de_check_aponta_o_arquivo(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            raiz = _repo_fake(Path(tmp))
            ctx = _CtxFake(rc_por_comando={"--check": 1})
            with mock.patch.object(srv, "check_node", _node_ok), \
                    mock.patch.object(srv, "resolve_node", lambda: "node"):
                relatorio = srv.prepare_server(raiz, ctx)
            self.assertFalse(relatorio.ok)
            self.assertIn("node --check", relatorio.erro)
            self.assertIn("src/index.js", relatorio.erro)

    def test_falha_de_smoke_reporta_codigo(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            raiz = _repo_fake(Path(tmp))
            ctx = _CtxFake(rc_por_comando={"--check": 0, "smoke.mjs": 4})
            with mock.patch.object(srv, "check_node", _node_ok), \
                    mock.patch.object(srv, "resolve_node", lambda: "node"):
                relatorio = srv.prepare_server(raiz, ctx)
            self.assertFalse(relatorio.ok)
            self.assertIn("smoke test", relatorio.erro)
            self.assertIn("4", relatorio.erro)

    def test_example_ausente_e_erro_claro(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            raiz = _repo_fake(Path(tmp))
            (raiz / "server" / "config" / "packs.example.json").unlink()
            with mock.patch.object(srv, "check_node", _node_ok), \
                    mock.patch.object(srv, "resolve_node", lambda: "node"):
                relatorio = srv.prepare_server(raiz, _CtxFake())
            self.assertFalse(relatorio.ok)
            self.assertIn("packs.example.json", relatorio.erro)


class TestReadPort(unittest.TestCase):
    def test_port_do_env_senao_default(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            raiz = _repo_fake(Path(tmp))
            self.assertEqual(srv.read_port(raiz), srv.DEFAULT_PORT)
            (raiz / "server" / ".env").write_text("PORT=9099\n", encoding="utf-8")
            self.assertEqual(srv.read_port(raiz), 9099)
            (raiz / "server" / ".env").write_text('PORT="8123"\nRUIDO=x\n', encoding="utf-8")
            self.assertEqual(srv.read_port(raiz), 8123)
            (raiz / "server" / ".env").write_text("PORT=não-número\n", encoding="utf-8")
            self.assertEqual(srv.read_port(raiz), srv.DEFAULT_PORT)


class _ProcFake:
    pid = 4242
    _returncode: int | None = None

    @property
    def returncode(self) -> int | None:
        return self._returncode

    def poll(self):
        return self._returncode

    def terminate(self):
        self._returncode = 0

    def kill(self):
        self._returncode = 9

    def wait(self, timeout=None):
        return self._returncode


class TestStartServer(unittest.TestCase):
    def test_exige_preparo_previo(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            raiz = _repo_fake(Path(tmp))  # sem .env local
            relatorio = srv.start_server(raiz, _CtxFake())
            self.assertFalse(relatorio.ok)
            self.assertIn("Preparar", relatorio.erro)

    def test_idempotente_quando_health_ja_responde(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            raiz = _repo_fake(Path(tmp))
            (raiz / "server" / ".env").write_text("PORT=8080\n", encoding="utf-8")
            spawn = mock.Mock()
            with mock.patch.object(srv, "check_node", _node_ok), \
                    mock.patch.object(srv, "health_probe", lambda p, **k: {"ok": True}), \
                    mock.patch.object(srv, "_spawn_node", spawn):
                relatorio = srv.start_server(raiz, _CtxFake())
            self.assertTrue(relatorio.ok, relatorio.erro)
            self.assertTrue(relatorio.ja_em_execucao)
            spawn.assert_not_called(), "health verde não pode criar segundo processo"

    def test_sobe_escreve_pid_e_health(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            raiz = _repo_fake(Path(tmp))
            (raiz / "server" / ".env").write_text("PORT=8080\n", encoding="utf-8")
            respostas = iter([None, None, {"ok": True, "game_data_loaded": True}])
            with mock.patch.object(srv, "check_node", _node_ok), \
                    mock.patch.object(srv, "resolve_node", lambda: "node"), \
                    mock.patch.object(srv, "health_probe", lambda p, **k: next(respostas)), \
                    mock.patch.object(srv, "_spawn_node", lambda *a, **k: _ProcFake()):
                relatorio = srv.start_server(raiz, _CtxFake())
            self.assertTrue(relatorio.ok, relatorio.erro)
            self.assertEqual(relatorio.pid, 4242)
            self.assertEqual(relatorio.health.get("game_data_loaded"), True)
            pid_file = srv.state_dir(raiz) / "server.pid"
            self.assertEqual(pid_file.read_text(encoding="ascii").strip(), "4242")

    def test_sem_health_encerra_o_processo_e_limpa_pid(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            raiz = _repo_fake(Path(tmp))
            (raiz / "server" / ".env").write_text("PORT=8080\n", encoding="utf-8")
            proc = _ProcFake()
            with mock.patch.object(srv, "check_node", _node_ok), \
                    mock.patch.object(srv, "resolve_node", lambda: "node"), \
                    mock.patch.object(srv, "health_probe", lambda p, **k: None), \
                    mock.patch.object(srv, "_spawn_node", lambda *a, **k: proc), \
                    mock.patch.object(srv, "START_TIMEOUT", 0.2):
                relatorio = srv.start_server(raiz, _CtxFake())
            self.assertFalse(relatorio.ok)
            self.assertIn("não respondeu", relatorio.erro)
            self.assertIsNotNone(proc.poll(), "processo iniciado por nós deve ser encerrado")
            self.assertFalse((srv.state_dir(raiz) / "server.pid").exists())


class TestStopServer(unittest.TestCase):
    def test_nada_rodando_e_ok(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            raiz = _repo_fake(Path(tmp))
            with mock.patch.object(srv, "health_probe", lambda p, **k: None):
                relatorio = srv.stop_server(raiz, _CtxFake())
            self.assertTrue(relatorio.ok, relatorio.erro)

    def test_recusa_matar_processo_desconhecido(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            raiz = _repo_fake(Path(tmp))
            (raiz / "server" / ".env").write_text("PORT=8080\n", encoding="utf-8")
            with mock.patch.object(srv, "health_probe", lambda p, **k: {"ok": True}):
                relatorio = srv.stop_server(raiz, _CtxFake())
            self.assertFalse(relatorio.ok)
            self.assertIn("sem PID registrado", relatorio.erro)

    def test_encerra_pid_registrado_windows(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            raiz = _repo_fake(Path(tmp))
            srv.state_dir(raiz).mkdir(parents=True, exist_ok=True)
            (srv.state_dir(raiz) / "server.pid").write_text("4242", encoding="ascii")
            # health vivo na checagem inicial, morto nas conferências seguintes
            respostas = iter([{"ok": True}, None, None, None])
            with mock.patch.object(srv, "WINDOWS", True), \
                    mock.patch.object(srv, "_probe", lambda cmd, **k: (0, "")), \
                    mock.patch.object(srv, "health_probe", lambda p, **k: next(respostas)):
                relatorio = srv.stop_server(raiz, _CtxFake())
            self.assertTrue(relatorio.ok, relatorio.erro)
            self.assertEqual(relatorio.pid, 4242)
            self.assertFalse((srv.state_dir(raiz) / "server.pid").exists())

    def test_taskkill_falhando_reporta(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            raiz = _repo_fake(Path(tmp))
            srv.state_dir(raiz).mkdir(parents=True, exist_ok=True)
            (srv.state_dir(raiz) / "server.pid").write_text("4242", encoding="ascii")
            with mock.patch.object(srv, "WINDOWS", True), \
                    mock.patch.object(srv, "_probe", lambda cmd, **k: (1, "acesso negado")), \
                    mock.patch.object(srv, "health_probe", lambda p, **k: {"ok": True}):
                relatorio = srv.stop_server(raiz, _CtxFake())
            self.assertFalse(relatorio.ok)
            self.assertIn("taskkill", relatorio.erro)


class TestServerStatus(unittest.TestCase):
    def test_status_agrega_pid_e_health(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            raiz = _repo_fake(Path(tmp))
            (raiz / "server" / ".env").write_text("PORT=8155\n", encoding="utf-8")
            srv.state_dir(raiz).mkdir(parents=True, exist_ok=True)
            (srv.state_dir(raiz) / "server.pid").write_text("777", encoding="ascii")
            with mock.patch.object(srv, "pid_alive", lambda pid: True), \
                    mock.patch.object(srv, "health_probe", lambda p, **k: {"ok": True}):
                estado = srv.server_status(raiz)
            self.assertEqual(estado["porta"], 8155)
            self.assertEqual(estado["pid"], 777)
            self.assertTrue(estado["pid_vivo"])
            self.assertEqual(estado["health"], {"ok": True})


if __name__ == "__main__":
    unittest.main(verbosity=2)
