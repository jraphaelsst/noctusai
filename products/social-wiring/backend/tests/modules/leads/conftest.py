"""Shared fixtures for the Leads module test suite.

Backed by ``noctusai_lib.testing.MockSupabaseClient`` (NOT the SQLite dev
client) — the leads services use ``gte``/``lte``/``in_``/``ilike``,
which the mock's ``_FilterMixin`` evaluates literally (confirmed against
``noctusai_lib/testing/mocks.py``); the SQLite dev adapter only
implements ``eq``/``lt``/``in_``/``or_``(cursor-only) and would silently
under-filter. Per ``KB § PATTERNS/di-test-seam.md``.

RPC simulator (migration 027)
──────────────────────────────
``analytics_service.summary``/``timeseries``/``by_dimension``/``heatmap``
and ``leads_service.facets`` now call ``client.rpc(<name>, params)`` —
real SQL functions in prod. ``MockSupabaseClient.rpc()`` cannot execute
SQL (it only replays whatever ``set_rpc_data`` was given), so without
help every EXISTING analytics/facets router test (which drives real
math by inserting leads via ``POST`` then asserting on computed values,
never calling ``set_rpc_data``) would start seeing an empty/default RPC
response and fail. ``_install_rpc_simulator`` patches the schema-scoped
mock's ``.rpc`` so that, for exactly the 5 function names this module
defines, it reconstructs a ``LeadFilters`` from the SQL parameter dict
and calls the retained ``_reference_*`` Python implementations (the
same aggregation math the SQL functions were authored to match) against
the mock's own stored rows. This keeps every existing test body
UNCHANGED and still exercising real business-rule math (share_pct
summing to 100, variacao_pct null-vs-zero, "Outros" folding, etc.) — it
is a Python REFERENCE MODEL standing in for Postgres, not a live SQL
engine; see the module docstrings in ``analytics_service.py`` /
``leads_service.py`` for the honesty caveat this implies.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.testing import (
    MockSelectBuilder,
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)

from app.modules.leads.services import analytics_service, leads_service
from app.modules.leads.services.query import LeadFilters

ORG_A = "00000000-0000-4000-8000-0000000000a1"
ORG_B = "00000000-0000-4000-8000-0000000000b2"


def _filters_from_rpc_params(params: dict) -> LeadFilters:
    """Inverse of ``query.to_rpc_params`` — reconstructs the
    ``LeadFilters`` a real SQL function would have received, for the
    simulator to hand to a ``_reference_*`` Python implementation."""
    from datetime import date

    def _d(value):
        return date.fromisoformat(value) if value else None

    return LeadFilters(
        de=_d(params.get("p_de")),
        ate=_d(params.get("p_ate")),
        ano=list(params.get("p_ano") or []),
        mes=list(params.get("p_mes") or []),
        origem_id=list(params.get("p_origem_id") or []),
        corretor_id=list(params.get("p_corretor_id") or []),
        tipo=list(params.get("p_tipo") or []),
        tier=list(params.get("p_tier") or []),
        empreendimento=list(params.get("p_empreendimento") or []),
        regiao=list(params.get("p_regiao") or []),
        needs_review=params.get("p_needs_review"),
        q=params.get("p_q"),
    )


def _install_rpc_simulator(scoped_client) -> None:
    """Bind a ``.rpc`` on ``scoped_client`` (the `social_wiring`-scoped
    mock instance ``deps.get_leads_client()`` will cache and reuse for
    the rest of this test) that simulates the 5 RPC functions migration
    027 defines by calling the equivalent ``_reference_*`` Python
    implementation. Raises loudly for any unrecognized RPC name — a
    typo'd/renamed function name must fail the test, not silently return
    an empty response."""

    def _simulated_rpc(name: str, params: dict | None = None):
        params = params or {}
        org_id = params["p_org_id"]
        filters = _filters_from_rpc_params(params)

        if name == "leads_analytics_summary":
            refs = leads_service.build_refs(scoped_client, org_id)
            result = analytics_service._reference_summary(scoped_client, org_id, filters, refs)
        elif name == "leads_analytics_timeseries":
            refs = leads_service.build_refs(scoped_client, org_id)
            result = analytics_service._reference_timeseries(
                scoped_client, org_id, filters, refs,
                grain=params.get("p_grain") or "mes", split=params.get("p_split"),
            )
        elif name == "leads_analytics_by_dimension":
            refs = leads_service.build_refs(scoped_client, org_id)
            result = analytics_service._reference_by_dimension(
                scoped_client, org_id, filters, refs,
                dim=params["p_dim"], limit=params.get("p_limit") or 15,
            )
        elif name == "leads_analytics_heatmap":
            result = analytics_service._reference_heatmap(scoped_client, org_id, filters)
        elif name == "leads_facets":
            result = leads_service._reference_facets(scoped_client, org_id, filters)
        else:
            raise AssertionError(f"unsimulated RPC in leads tests: {name!r}")

        return MockSelectBuilder(result)

    scoped_client.rpc = _simulated_rpc


@pytest.fixture
def mock_db():
    return MockSupabaseClient()


@pytest.fixture
def http_client(mock_db):
    mock_db.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(org_id=ORG_A))
    )

    # Wrap `.schema(...)` so the SAME scoped instance `deps.get_leads_client()`
    # caches (see that module's docstring) gets the RPC simulator wired in
    # too — `mock_db.rpc` itself is left alone since nothing in this module
    # calls it directly on the unscoped client.
    _original_schema = mock_db.schema

    def _schema_with_rpc_sim(name):
        scoped = _original_schema(name)
        _install_rpc_simulator(scoped)
        return scoped

    mock_db.schema = _schema_with_rpc_sim

    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_db),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_db),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_db),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_db)
        tc = TestClient(app, raise_server_exceptions=True)
        yield tc


def auth_headers() -> dict:
    return {"Authorization": "Bearer test-token"}


__all__ = ["ORG_A", "ORG_B", "auth_headers"]
