"""`GET /api/custos` — per-integration spend for the Custos page.

Two sources: `social_wiring.llm_usage` (own-schema, admin-scoped) and
`public.cost_ledger` (cross-schema, `get_core_client()`). Both patched
through the SAME `DatabaseModule.get_*_client` seam `test_painel_router.py`
uses, so `get_core_client()` in this product resolves to the identical
`MockSupabaseClient` instance (unscoped — schema="public" is the mock's own
default) that seeds `cost_ledger` / `fx_rates`.

**Strict `== 401`** per `KB § PATTERNS/compliance/auth-boundary-false-green.md`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.testing import MockSupabaseClient, MockUser, MockUserResponse

from app.dependencies import coerce_org_uuid

ORG_RAW = "test-org-123"
ORG_ID = str(coerce_org_uuid(ORG_RAW))
URL = "/api/custos"


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _today_iso(hour: int = 12) -> str:
    now = datetime.now(timezone.utc)
    return now.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


_next_id = iter(range(1, 100_000))


def _llm_row(*, provider="anthropic", model="claude-sonnet-5", cost=1.0, tokens=1000, at=None):
    return {
        "id": next(_next_id),
        "org_id": ORG_ID,
        "provider": provider,
        "model": model,
        "total_tokens": tokens,
        "cost_estimate_usd": cost,
        "at": at or _today_iso(),
    }


def _cost_ledger_row(*, category="infosimples", amount_brl="10.00", fx_pending=False, created_at=None):
    return {
        "id": next(_next_id),
        "org_id": ORG_ID,
        "category": category,
        "amount_brl": amount_brl,
        "fx_pending": fx_pending,
        "created_at": created_at or _today_iso(),
    }


def _client_for(*, llm_rows=None, cost_ledger_rows=None, fx_rates=None):
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(org_id=ORG_RAW, org_role="owner"))
    )
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.dependencies import get_scoped_admin_client
        from app.main import app

        scoped = get_scoped_admin_client("social_wiring")
        scoped.set_table_data("llm_usage", llm_rows or [])
        # `cost_ledger` / `fx_rates` live in `public` — `get_core_client()`
        # resolves to `mock_sb` itself (unscoped), per the module docstring.
        mock_sb.set_table_data("cost_ledger", cost_ledger_rows or [])
        mock_sb.set_table_data("fx_rates", fx_rates or [])
        tc = TestClient(app, raise_server_exceptions=True)
        yield tc


@pytest.fixture
def client():
    yield from _client_for()


class TestAuth:
    def test_without_a_token_is_401(self, client):
        assert client.get(URL).status_code == 401


class TestAggregation:
    def test_empty_org_returns_zeroed_payload(self):
        for tc in _client_for():
            resp = tc.get(URL, headers=_auth())
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["total_brl"] == 0
            assert body["llm_por_modelo"] == []
            assert body["serie_diaria"] == []
            nomes = {i["nome"] for i in body["integracoes"]}
            assert nomes == {"llm", "infosimples", "d4sign", "google_maps"}

    def test_llm_usage_converts_usd_to_brl_via_latest_ptax(self):
        for tc in _client_for(
            llm_rows=[_llm_row(cost=2.0), _llm_row(provider="openai", model="gpt-4o-mini", cost=1.0)],
            fx_rates=[{"pair": "USD/BRL", "quote_date": "2026-09-20", "rate": "5.00"}],
        ):
            resp = tc.get(URL, headers=_auth())
            assert resp.status_code == 200, resp.text
            body = resp.json()
            llm_card = next(i for i in body["integracoes"] if i["nome"] == "llm")
            assert llm_card["chamadas"] == 2
            assert llm_card["fx_pendente"] is False
            assert llm_card["custo_brl"] == pytest.approx(15.0)  # (2+1) USD * 5.00
            assert body["total_brl"] == pytest.approx(15.0)
            by_model = {(m["provider"], m["model"]): m for m in body["llm_por_modelo"]}
            assert by_model[("anthropic", "claude-sonnet-5")]["custo_usd"] == pytest.approx(2.0)
            assert by_model[("anthropic", "claude-sonnet-5")]["custo_brl"] == pytest.approx(10.0)

    def test_no_ptax_bulletin_reports_fx_pending_never_a_guessed_rate(self):
        for tc in _client_for(llm_rows=[_llm_row(cost=3.0)], fx_rates=[]):
            resp = tc.get(URL, headers=_auth())
            body = resp.json()
            llm_card = next(i for i in body["integracoes"] if i["nome"] == "llm")
            assert llm_card["fx_pendente"] is True
            assert llm_card["custo_brl"] is None
            assert body["fx_pendente"] is True
            # USD total is still visible per-model even while BRL is pending.
            assert body["llm_por_modelo"][0]["custo_usd"] == pytest.approx(3.0)
            assert body["llm_por_modelo"][0]["custo_brl"] is None

    def test_infosimples_cost_ledger_rows_are_summed_in_brl_natively(self):
        for tc in _client_for(
            cost_ledger_rows=[
                _cost_ledger_row(amount_brl="1.50"),
                _cost_ledger_row(amount_brl="2.50"),
            ],
        ):
            resp = tc.get(URL, headers=_auth())
            body = resp.json()
            info_card = next(i for i in body["integracoes"] if i["nome"] == "infosimples")
            assert info_card["chamadas"] == 2
            assert info_card["custo_brl"] == pytest.approx(4.0)
            assert body["total_brl"] == pytest.approx(4.0)

    def test_pending_infosimples_rows_excluded_from_total_and_flagged(self):
        for tc in _client_for(
            cost_ledger_rows=[
                _cost_ledger_row(amount_brl="1.50", fx_pending=False),
                _cost_ledger_row(amount_brl=None, fx_pending=True),
            ],
        ):
            resp = tc.get(URL, headers=_auth())
            body = resp.json()
            info_card = next(i for i in body["integracoes"] if i["nome"] == "infosimples")
            assert info_card["chamadas"] == 2
            assert info_card["custo_brl"] == pytest.approx(1.5)
            assert info_card["fx_pendente"] is True

    def test_other_org_cost_ledger_rows_never_leak_in(self):
        other_org_row = _cost_ledger_row(amount_brl="99.00")
        other_org_row["org_id"] = "22222222-2222-4222-8222-222222222222"
        for tc in _client_for(cost_ledger_rows=[other_org_row]):
            resp = tc.get(URL, headers=_auth())
            body = resp.json()
            info_card = next(i for i in body["integracoes"] if i["nome"] == "infosimples")
            assert info_card["chamadas"] == 0
            assert info_card["custo_brl"] == 0

    def test_d4sign_and_google_maps_are_not_invented_zero_cost(self):
        """Untracked integrations report `custo_brl=None` (not `0`) — a
        confirmed zero would falsely read as 'this is free'."""
        for tc in _client_for():
            resp = tc.get(URL, headers=_auth())
            body = resp.json()
            for nome in ("d4sign", "google_maps"):
                card = next(i for i in body["integracoes"] if i["nome"] == nome)
                assert card["custo_brl"] is None
                assert card["observacao"]

    def test_date_range_query_params_are_honored(self):
        old_day = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        for tc in _client_for(llm_rows=[_llm_row(cost=5.0, at=old_day)]):
            resp = tc.get(URL, headers=_auth())  # default range = this month
            body = resp.json()
            assert body["llm_por_modelo"] == []
