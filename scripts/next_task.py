#!/usr/bin/env python3
"""Seleciona deterministicamente o próximo gap de paridade funcional.

Lê `compatibility.json` (fonte de verdade), percorre os módulos na ordem de
prioridade do plano de convergência e devolve o primeiro endpoint + o primeiro
gate do DEFINITION OF DONE que ainda falha. Substitui decisão humana/LLM sobre
"o que fazer agora": quem decide é o estado de evidência, não o humor.

Fluxo por módulo (a ordem é a mesma do plano):
  extrair contrato -> implementar -> testar servidor -> testar cliente ->
  testar persistência -> atualizar compatibility.json -> commit -> next_task

Uso:
  python scripts/next_task.py            # humano
  python scripts/next_task.py --json     # máquina (CI/agentes)

Exit codes: 0 tarefa selecionada; 3 nada a fazer (DoD do projeto alcançado
segundo o registro — rode scripts/verify_everything.py para o gate completo);
2 compatibility.json ausente/corrompido.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPAT_JSON = ROOT / "compatibility.json"

GATE_ACTIONS = {
    "schema_extracted": (
        "extrair o DTO request/response real do global-metadata.dat "
        "(skill il2cpp-recon; métodos Ubu.GameApi.Methods.*Api/*Response via nestedTypes)"
    ),
    "implemented": (
        "implementar a rota em server/src com o contrato extraído "
        "(revival-server skill; envelope wire() ok()/fail(); numérico ausente se omite, nunca null)"
    ),
    "request_observed": (
        "observar a chamada real do cliente: rodar o fluxo com scripts/client_harness.py "
        "e salvar fixture provenance=client em tests/fixtures/protocol/"
    ),
    "response_observed": (
        "observar a resposta aceita pelo cliente (logcat sem 'Malformed response payload') "
        "e salvar o fixture correspondente"
    ),
    "client_validated": (
        "validar o fluxo completo no cliente/emulador via scripts/client_harness.py "
        "(exit 0, sem assinaturas de erro no logcat)"
    ),
    "persistence_validated": (
        "provar que o efeito sobrevive a restart do servidor "
        "(parar servidor, subir de novo, conferir user-data/estado)"
    ),
    "regression_test": (
        "adicionar caso de regressão em server/test/*.mjs citando a rota como literal "
        "e rodar cd server && npm test"
    ),
    "uses_fallback": (
        "eliminar o fallback do RESEARCH_MODE nesta rota: o cliente deixou de "
        "depender da resposta vazia de pesquisa"
    ),
}


def load_compat() -> dict:
    if not COMPAT_JSON.is_file():
        print(f"ERRO: {COMPAT_JSON} não existe — rode scripts/generate_endpoint_matrix.py primeiro",
              file=sys.stderr)
        raise SystemExit(2)
    try:
        return json.loads(COMPAT_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERRO: compatibility.json corrompido: {exc}", file=sys.stderr)
        raise SystemExit(2)


def first_failed_gate(endpoint: dict) -> str | None:
    for gate in endpoint.get("_dod_gates") or (
        "schema_extracted", "implemented", "request_observed", "response_observed",
        "client_validated", "persistence_validated", "regression_test",
    ):
        value = endpoint.get(gate)
        if value is None:  # persistence_validated null = não aplicável
            continue
        if value is False:
            return gate
    if endpoint.get("uses_fallback"):
        return "uses_fallback"
    return None


def select(compat: dict) -> dict | None:
    endpoints = compat["endpoints"]
    priority = compat.get("module_priority", {})

    modules: dict[str, list[tuple[str, dict]]] = {}
    for route, data in endpoints.items():
        modules.setdefault(data["module"], []).append((route, data))

    for module in sorted(modules, key=lambda m: (priority.get(m, 99), m)):
        pending = []
        for route, data in sorted(modules[module]):
            gate = first_failed_gate(data)
            if gate:
                pending.append((route, data, gate))
        if not pending:
            continue
        route, data, gate = pending[0]
        return {
            "module": module,
            "module_priority": priority.get(module, 99),
            "endpoint": route,
            "gate": gate,
            "action": GATE_ACTIONS[gate],
            "evidence": data.get("evidence", ""),
            "module_pending": [
                {"endpoint": r, "gate": g} for r, _, g in pending
            ],
            "module_total": len(modules[module]),
        }
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="saída JSON para consumo por máquina")
    args = parser.parse_args()

    compat = load_compat()
    task = select(compat)

    if task is None:
        if args.json:
            print(json.dumps({"status": "done", "task": None}, ensure_ascii=False))
        else:
            print("Nenhum gap restante no registro. Rode scripts/verify_everything.py")
            print("para o gate completo (testes, fallback, APK, persistência).")
        return 3

    if args.json:
        print(json.dumps({"status": "task", "task": task}, ensure_ascii=False, indent=2))
        return 0

    pending = task["module_pending"]
    print(f"PRÓXIMA TAREFA — módulo {task['module']} (prioridade {task['module_priority']})")
    print(f"  endpoint: {task['endpoint']}")
    print(f"  gate que falha: {task['gate']}")
    print(f"  ação: {task['action']}")
    if task["evidence"]:
        print(f"  evidência atual: {task['evidence']}")
    print()
    print(f"  Fila do módulo ({len(pending)}/{task['module_total']} endpoints com gap):")
    for item in pending:
        print(f"    - {item['endpoint']}  [{item['gate']}]")
    print()
    print("Ciclo por funcionalidade: contrato -> implementar -> teste -> servidor ->")
    print("cliente (client_harness.py) -> persistência -> generate_endpoint_matrix.py")
    print("--set ... -> commit -> next_task.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
