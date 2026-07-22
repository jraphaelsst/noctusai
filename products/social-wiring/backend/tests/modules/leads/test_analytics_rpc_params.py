"""Structural coverage for the SQL-side analytics path (migration 027).

What's GENUINELY covered here vs. what's structural-only
──────────────────────────────────────────────────────────
There is no real Postgres available in this test environment, so the
actual SQL functions' arithmetic is NOT executed by this suite (see the
migration header + this PR's return note). What IS genuinely exercised,
end to end, with real assertions:

* ``query.to_rpc_params`` — the exact parameter dict built from a
  ``LeadFilters`` (empty repeatable filters -> ``None``, not ``[]``;
  dates -> ISO strings; UUIDs -> strings) — this is the literal contract
  the SQL functions' signatures were authored against.
* Every ``analytics_service.summary``/``timeseries``/``by_dimension``/
  ``heatmap`` and ``leads_service.facets`` calls ``client.rpc(name,
  params)`` with EXACTLY that dict (plus their own extra params where
  applicable — grain/split/dim/limit) and returns ``resp.data``
  unchanged — a spy client below captures the call, no mock aggregation
  math involved.
* The documented default-shape fallback when ``resp.data`` is falsy
  (``None``/``{}``) — a defensive branch a real SQL scalar-jsonb
  function should never actually hit (PostgREST returns the function's
  JSON return value directly), but cheap to assert.

Router-level end-to-end behavior (share_pct summing to 100, variacao_pct
null handling, "Outros" folding, pt-BR labels, blank-month heatmap
cells, etc.) is covered by the EXISTING ``test_analytics_router.py`` /
``test_leads_router.py`` suites, now running against the RPC simulator
installed in ``conftest.py`` — which calls the retained
``_reference_*`` Python implementations, NOT real SQL. That is the
"structurally covered via the fake/mock seam" half of the brief's ask.
"""
from __future__ import annotations

from uuid import UUID

from app.modules.leads.services import analytics_service, leads_service
from app.modules.leads.services.query import LeadFilters, to_rpc_params

ORG = UUID("6dd73140-74a4-41c6-aeff-bc94b5312b53")
SOURCE_ID = UUID("11111111-1111-4111-8111-111111111111")
CORRETOR_ID = UUID("22222222-2222-4222-8222-222222222222")


class _SpyRpcClient:
    """Captures the last ``(name, params)`` an ``.rpc()`` call made and
    replays a canned response — the point is asserting on the CALL, not
    computing anything."""

    def __init__(self, canned):
        self._canned = canned
        self.last_name = None
        self.last_params = None

    def rpc(self, name, params=None):
        self.last_name = name
        self.last_params = params or {}
        return self

    def execute(self):
        return type("Resp", (), {"data": self._canned})()


class TestToRpcParams:
    def test_empty_repeatable_filters_become_none_not_empty_list(self):
        params = to_rpc_params(ORG, LeadFilters())
        for key in (
            "p_ano", "p_mes", "p_origem_id", "p_corretor_id",
            "p_tipo", "p_tier", "p_empreendimento", "p_regiao",
        ):
            assert params[key] is None, f"{key} should be None (SQL '= ANY(NULL)' means no constraint)"
        assert params["p_de"] is None
        assert params["p_ate"] is None
        assert params["p_needs_review"] is None
        assert params["p_q"] is None
        assert params["p_org_id"] == str(ORG)

    def test_populated_filters_marshal_to_json_safe_primitives(self):
        filters = LeadFilters(
            de=__import__("datetime").date(2026, 1, 1),
            ate=__import__("datetime").date(2026, 12, 31),
            ano=[2025, 2026],
            mes=[1, 2],
            origem_id=[SOURCE_ID],
            corretor_id=[CORRETOR_ID],
            tipo=["novo"],
            tier=["simples"],
            empreendimento=["Bosque"],
            regiao=["Km 21"],
            needs_review=True,
            q="zebra",
        )
        params = to_rpc_params(ORG, filters)
        assert params["p_de"] == "2026-01-01"
        assert params["p_ate"] == "2026-12-31"
        assert params["p_ano"] == [2025, 2026]
        assert params["p_mes"] == [1, 2]
        assert params["p_origem_id"] == [str(SOURCE_ID)]
        assert params["p_corretor_id"] == [str(CORRETOR_ID)]
        assert params["p_tipo"] == ["novo"]
        assert params["p_tier"] == ["simples"]
        assert params["p_empreendimento"] == ["Bosque"]
        assert params["p_regiao"] == ["Km 21"]
        assert params["p_needs_review"] is True
        assert params["p_q"] == "zebra"


class TestServiceFunctionsCallTheRightRpc:
    def test_summary_calls_leads_analytics_summary(self):
        client = _SpyRpcClient({"total": 3})
        filters = LeadFilters(tipo=["novo"])
        result = analytics_service.summary(client, ORG, filters)
        assert client.last_name == "leads_analytics_summary"
        assert client.last_params == to_rpc_params(ORG, filters)
        assert result == {"total": 3}

    def test_summary_default_shape_when_no_data(self):
        client = _SpyRpcClient(None)
        result = analytics_service.summary(client, ORG, LeadFilters())
        assert result == {}

    def test_timeseries_calls_leads_analytics_timeseries_with_grain_and_split(self):
        client = _SpyRpcClient({"grain": "dia", "split": "origem", "series_meta": [], "points": []})
        filters = LeadFilters()
        result = analytics_service.timeseries(client, ORG, filters, grain="dia", split="origem")
        assert client.last_name == "leads_analytics_timeseries"
        expected = to_rpc_params(ORG, filters)
        expected["p_grain"] = "dia"
        expected["p_split"] = "origem"
        assert client.last_params == expected
        assert result["grain"] == "dia"

    def test_timeseries_default_shape_when_no_data(self):
        client = _SpyRpcClient(None)
        result = analytics_service.timeseries(client, ORG, LeadFilters(), grain="ano", split=None)
        assert result == {"grain": "ano", "split": None, "series_meta": [], "points": []}

    def test_by_dimension_calls_leads_analytics_by_dimension_with_dim_and_limit(self):
        client = _SpyRpcClient({"dim": "corretor", "total": 0, "buckets": []})
        filters = LeadFilters()
        result = analytics_service.by_dimension(client, ORG, filters, dim="corretor", limit=5)
        assert client.last_name == "leads_analytics_by_dimension"
        expected = to_rpc_params(ORG, filters)
        expected["p_dim"] = "corretor"
        expected["p_limit"] = 5
        assert client.last_params == expected
        assert result["dim"] == "corretor"

    def test_by_dimension_default_shape_when_no_data(self):
        client = _SpyRpcClient(None)
        result = analytics_service.by_dimension(client, ORG, LeadFilters(), dim="origem", limit=15)
        assert result == {"dim": "origem", "total": 0, "buckets": []}

    def test_heatmap_calls_leads_analytics_heatmap(self):
        client = _SpyRpcClient({"anos": [2026], "cells": {"2026": [1] + [None] * 11}, "max": 1})
        filters = LeadFilters()
        result = analytics_service.heatmap(client, ORG, filters)
        assert client.last_name == "leads_analytics_heatmap"
        assert client.last_params == to_rpc_params(ORG, filters)
        assert result["max"] == 1

    def test_heatmap_default_shape_when_no_data(self):
        client = _SpyRpcClient(None)
        result = analytics_service.heatmap(client, ORG, LeadFilters())
        assert result == {"anos": [], "cells": {}, "max": 0}

    def test_facets_calls_leads_facets(self):
        client = _SpyRpcClient({"empreendimentos": [], "regioes": [], "anos": [2026]})
        filters = LeadFilters(regiao=["Km 21"])
        result = leads_service.facets(client, ORG, filters)
        assert client.last_name == "leads_facets"
        assert client.last_params == to_rpc_params(ORG, filters)
        assert result["anos"] == [2026]

    def test_facets_default_shape_when_no_data(self):
        client = _SpyRpcClient(None)
        result = leads_service.facets(client, ORG, LeadFilters())
        assert result == {"empreendimentos": [], "regioes": [], "anos": []}
