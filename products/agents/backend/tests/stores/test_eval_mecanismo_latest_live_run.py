"""SupabaseMecanismoStore.latest_live_run asks the DB function eval_run_cobre_casos for the consolidated coverage.

Prod incident 2026-11-11: the call site used ``exec_rpc`` without importing it, so every readiness request
(GET /api/studio/agents/<key>/prontidao) died with NameError -> 500 as soon as a version had a finished live
mechanism run. The Fake store never reaches this line, so the suite stayed green. This test drives the
Supabase store itself through a client double.
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from app.stores.studio_eval_mecanismo import SupabaseMecanismoStore


def _client(rows: list[dict], cobre: bool) -> MagicMock:
    client = MagicMock()
    schema = client.schema.return_value
    query = schema.table.return_value.select.return_value
    for _ in range(4):  # .eq(org).eq(version).eq(driver).eq(status)
        query.eq.return_value = query
    query.order.return_value.limit.return_value.execute.return_value.data = rows
    schema.rpc.return_value.execute.return_value.data = cobre
    return client


def _row(agent_id: str) -> dict:
    return {
        "id": str(uuid4()), "agent_id": agent_id, "compiled_hash": "h", "status": "concluida", "driver": "live",
        "completa": True, "aprovado": True, "orcamento_excedido": False, "total_casos": 3, "casos_aprovados": 3,
    }


def test_latest_live_run_asks_the_db_for_coverage():
    agent_id = str(uuid4())
    client = _client([_row(agent_id)], cobre=True)
    run = SupabaseMecanismoStore(client).latest_live_run(uuid4(), uuid4())
    assert run is not None
    client.schema.return_value.rpc.assert_called_once()
    fn, params = client.schema.return_value.rpc.call_args.args
    assert fn == "eval_run_cobre_casos"
    assert params["p_agent_id"] == agent_id and params["p_suite"] == "mecanismo"


def test_latest_live_run_without_a_run_skips_the_rpc():
    client = _client([], cobre=False)
    assert SupabaseMecanismoStore(client).latest_live_run(uuid4(), uuid4()) is None
    client.schema.return_value.rpc.assert_not_called()
