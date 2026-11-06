"""Aggregation math of the per-turn metrics: percentiles, cache share, daily series, per-group totals."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.studio import metricas as agg


def _row(ms=100, dia=1, custo=0.01, entrada=1000, leitura=0, escrita=0, status="ok", org=None, **kw):
    base = {
        "id": uuid4(), "created_at": datetime(2026, 11, dia, 12, tzinfo=timezone.utc), "org_id": org or uuid4(),
        "agent_key": "julia", "origem": "canal", "status": status, "handoff": False, "llm_calls": 1,
        "tokens_entrada": entrada, "tokens_saida": 10, "tokens_cache_leitura": leitura, "tokens_cache_escrita": escrita,
        "custo_usd": custo, "turno_ms": ms, "llm_ms": ms // 2, "tool_ms": 0, "inbound_bytes": 30, "reply_bytes": 200,
        "prompt_bytes": 5000, "db_bytes": 230, "compiled_hash": "h1",
    }
    return {**base, **kw}


def test_percentiles_are_linear_interpolation():
    assert agg.percentil([], 50) is None
    assert agg.percentil([7], 95) == 7
    assert agg.percentil([10, 20, 30, 40], 50) == 25
    assert agg.percentil(range(1, 101), 95) == pytest.approx(95.05)


def test_summary_totals_cost_per_turn_and_cache_share():
    rows = [_row(ms=100, custo=0.028, entrada=22237, escrita=21648), _row(ms=300, custo=0.0031, entrada=22300, leitura=21631)]
    s = agg.resumir(rows)
    assert s["turnos"] == 2 and s["custo_usd"] == 0.0311 and s["custo_por_turno_usd"] == 0.01555
    assert s["cache_leitura_share"] == round(21631 / 44537, 4)
    assert (s["turno_ms_p50"], s["turno_ms_p95"]) == (200, 290)
    assert s["db_bytes"] == 460 == s["armazenamento_bytes"]


def test_empty_window_is_all_zero_not_an_error():
    s = agg.resumir([])
    assert s["turnos"] == 0 and s["custo_por_turno_usd"] == 0 and s["cache_leitura_share"] == 0 and s["turno_ms_p50"] is None


def test_errors_and_daily_series_and_groups():
    org_a, org_b = uuid4(), uuid4()
    rows = [_row(dia=2, org=org_a), _row(dia=1, org=org_a, status="erro"), _row(dia=1, org=org_b, custo=0.5)]
    serie = agg.serie_diaria(rows)
    assert [d["dia"] for d in serie] == ["2026-11-01", "2026-11-02"] and serie[0]["turnos"] == 2 and serie[0]["turnos_erro"] == 1
    por_org = agg.por_chave(rows, lambda r: str(r["org_id"]), "org_id")
    assert por_org[0]["org_id"] == str(org_b)  # the costliest first


def test_public_turn_shape_has_the_three_blocks():
    r = _row(leitura=900, entrada=1000, version_id=None, tools=["buscar"], tools_ms={"buscar": 12})
    out = agg.turno_publico(r)
    assert set(out) >= {"llm", "velocidade", "tamanho", "ferramentas", "origem", "status"}
    assert out["llm"]["cache_leitura_share"] == 0.9 and out["velocidade"]["ferramentas_ms"] == {"buscar": 12}
    assert out["tamanho"]["media_bytes"] is None
