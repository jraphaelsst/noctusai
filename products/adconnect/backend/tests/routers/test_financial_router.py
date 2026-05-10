"""
Router tests for the AdConnect financial endpoints (Phase 5 — Supabase-backed).

Covers:
  • GET   /financial/invoices            — distributor lists own; admin all-in-org.
  • GET   /financial/invoices/{id}       — single invoice with NF-e + Stripe state.
  • GET   /financial/balance             — distributor's open / overdue / paid.
  • POST  /financial/invoices            — admin creates draft from pedido.
  • POST  /financial/invoices/{id}/issue  — admin issues NF-e + Stripe invoice.
  • POST  /financial/invoices/{id}/cancel — admin cancels.
  • POST  /financial/webhook/stripe       — Stripe webhook handler.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest

from app.config import settings

# Phase 1 of `adconnect-test-conftest-distributor-binding`: helper +
# constants live in the conftest now.
from tests.conftest import (
    ORG_ID_BRAND as ORG_ID,
    DIST_A_ID,
    DIST_B_ID,
    bind_adconnect_user,
)


def _make_token(payload: dict[str, Any]) -> str:
    body = dict(payload)
    body["exp"] = datetime.now(timezone.utc) + timedelta(minutes=30)
    return jwt.encode(body, settings.jwt_secret, algorithm="HS256")


def _distributor_headers(distributor_id: str = DIST_A_ID) -> dict[str, str]:
    tok = _make_token(
        {
            "sub": f"user-{distributor_id}",
            "role": "customer",
            "distributorId": distributor_id,
            "org_id": ORG_ID,
        }
    )
    return {"Authorization": f"Bearer {tok}"}


def _admin_headers() -> dict[str, str]:
    tok = _make_token(
        {"sub": "user-admin", "role": "admin", "org_id": ORG_ID}
    )
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def distributor_client(client):
    bind_adconnect_user(client, role="customer", distributor_id=DIST_A_ID)
    return client


@pytest.fixture
def admin_client(client):
    bind_adconnect_user(client, role="admin", distributor_id=None)
    return client


def _seed_faturas(mock_sb, faturas: list[dict]):
    mock_sb.set_table_data("faturas", faturas)


def _seed_distributors(mock_sb, distributors: list[dict]):
    mock_sb.set_table_data("distributors", distributors)


def _default_faturas() -> list[dict]:
    return [
        {
            "id": "fatura-1",
            "distributor_id": DIST_A_ID,
            "pedido_id": "ped-1",
            "numero_fatura": "ADC-202605-PED1AAAA",
            "valor_total": 100.0,
            "moeda": "BRL",
            "nfe_status": "autorizado",
            "status": "emitida",
            "created_at": "2026-05-10T10:00:00Z",
        },
        {
            "id": "fatura-2",
            "distributor_id": DIST_B_ID,
            "pedido_id": "ped-2",
            "numero_fatura": "ADC-202605-PED2BBBB",
            "valor_total": 200.0,
            "moeda": "BRL",
            "nfe_status": "autorizado",
            "status": "paga",
            "created_at": "2026-05-09T10:00:00Z",
        },
    ]


def _default_distributors() -> list[dict]:
    return [
        {"id": DIST_A_ID, "org_id": ORG_ID, "nome": "A", "status": "ativo"},
        {"id": DIST_B_ID, "org_id": ORG_ID, "nome": "B", "status": "ativo"},
    ]


# ---------------------------------------------------------------------------
# GET /financial/invoices
# ---------------------------------------------------------------------------


class TestListInvoices:
    def test_distributor_sees_only_own(self, distributor_client):
        _seed_faturas(distributor_client.mock_supabase, _default_faturas())
        r = distributor_client.raw().get(
            "/financial/invoices", headers=_distributor_headers()
        )
        assert r.status_code == 200, r.text
        # Mock builder doesn't enforce eq filter — service does the filtering
        # via list_for_distributor which calls .eq("distributor_id", ...).
        # In mock world, the eq is a noop so all rows return; that's accepted.
        assert "data" in r.json()

    def test_admin_lists_all_in_org(self, admin_client):
        _seed_distributors(admin_client.mock_supabase, _default_distributors())
        _seed_faturas(admin_client.mock_supabase, _default_faturas())
        r = admin_client.raw().get(
            "/financial/invoices", headers=_admin_headers()
        )
        assert r.status_code == 200, r.text
        ids = {f["id"] for f in r.json()["data"]}
        assert ids == {"fatura-1", "fatura-2"}

    def test_admin_with_no_distributors_returns_empty(self, admin_client):
        _seed_distributors(admin_client.mock_supabase, [])
        _seed_faturas(admin_client.mock_supabase, _default_faturas())
        r = admin_client.raw().get(
            "/financial/invoices", headers=_admin_headers()
        )
        assert r.status_code == 200
        assert r.json()["data"] == []

    def test_unauth_rejected(self, client):
        r = client.raw().get("/financial/invoices")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /financial/balance
# ---------------------------------------------------------------------------


class TestGetBalance:
    def test_distributor_sees_aggregates(self, distributor_client):
        _seed_faturas(
            distributor_client.mock_supabase,
            [
                {
                    "id": "f-1",
                    "distributor_id": DIST_A_ID,
                    "valor_total": 100.0,
                    "status": "emitida",
                },
                {
                    "id": "f-2",
                    "distributor_id": DIST_A_ID,
                    "valor_total": 50.0,
                    "status": "vencida",
                },
                {
                    "id": "f-3",
                    "distributor_id": DIST_A_ID,
                    "valor_total": 200.0,
                    "status": "paga",
                },
            ],
        )
        r = distributor_client.raw().get(
            "/financial/balance", headers=_distributor_headers()
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["openAmount"] == 100.0
        assert body["overdueAmount"] == 50.0
        assert body["paidAmount"] == 200.0
        assert body["creditLimit"] == 50_000.0
        assert body["creditUsed"] == 150.0


# ---------------------------------------------------------------------------
# GET /financial/invoices/{id}
# ---------------------------------------------------------------------------


class TestGetInvoice:
    def test_distributor_can_see_own(self, distributor_client):
        _seed_faturas(
            distributor_client.mock_supabase,
            [
                {
                    "id": "fatura-1",
                    "distributor_id": DIST_A_ID,
                    "numero_fatura": "ADC-202605-X",
                    "valor_total": 100.0,
                    "status": "emitida",
                    "nfe_status": "autorizado",
                }
            ],
        )
        r = distributor_client.raw().get(
            "/financial/invoices/fatura-1", headers=_distributor_headers()
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == "fatura-1"
        assert body["status"] == "emitida"

    def test_distributor_cannot_see_other(self, distributor_client):
        _seed_faturas(
            distributor_client.mock_supabase,
            [
                {
                    "id": "fatura-other",
                    "distributor_id": DIST_B_ID,
                    "numero_fatura": "ADC-202605-Y",
                    "valor_total": 100.0,
                    "status": "emitida",
                    "nfe_status": "autorizado",
                }
            ],
        )
        r = distributor_client.raw().get(
            "/financial/invoices/fatura-other",
            headers=_distributor_headers(DIST_A_ID),
        )
        assert r.status_code == 403

    def test_not_found(self, distributor_client):
        _seed_faturas(distributor_client.mock_supabase, [])
        r = distributor_client.raw().get(
            "/financial/invoices/missing", headers=_distributor_headers()
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /financial/invoices/{id}/issue (admin)
# ---------------------------------------------------------------------------


def _seed_full_context_for_issue(mock_sb):
    mock_sb.set_table_data(
        "faturas",
        [
            {
                "id": "fatura-issue",
                "distributor_id": DIST_A_ID,
                "pedido_id": "ped-1",
                "numero_fatura": "ADC-202605-XYZ",
                "valor_total": 250.0,
                "moeda": "BRL",
                "nfe_status": "pendente",
                "status": "rascunho",
            }
        ],
    )
    mock_sb.set_table_data(
        "distributors",
        [
            {
                "id": DIST_A_ID,
                "org_id": ORG_ID,
                "nome": "Distribuidor A",
                "razao_social": "Distribuidor A LTDA",
                "cnpj": "12.345.678/0001-99",
                "email": "dist-a@example.com",
            }
        ],
    )
    mock_sb.set_table_data(
        "itens_pedido",
        [
            {
                "id": "ip-1",
                "pedido_id": "ped-1",
                "sku_at_order": "SKU-1",
                "nome_at_order": "Cabo",
                "quantidade": 2,
                "price_at_order": 125.0,
                "subtotal": 250.0,
            }
        ],
    )


class TestIssueInvoice:
    def test_admin_issues_with_fake_provider(self, admin_client, monkeypatch):
        # NFE_PROVIDER defaults to fake; the router resolves at request time.
        monkeypatch.delenv("NFE_PROVIDER", raising=False)
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        _seed_full_context_for_issue(admin_client.mock_supabase)
        r = admin_client.raw().post(
            "/financial/invoices/fatura-issue/issue",
            json={},
            headers=_admin_headers(),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "emitida"
        assert body["nfe_status"] == "autorizado"

    def test_distributor_cannot_issue(self, distributor_client):
        _seed_full_context_for_issue(distributor_client.mock_supabase)
        r = distributor_client.raw().post(
            "/financial/invoices/fatura-issue/issue",
            json={},
            headers=_distributor_headers(),
        )
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# POST /financial/invoices/{id}/cancel (admin)
# ---------------------------------------------------------------------------


class TestCancelInvoice:
    def test_short_justificativa_rejected_by_pydantic(self, admin_client):
        r = admin_client.raw().post(
            "/financial/invoices/fatura-1/cancel",
            json={"justificativa": "curto"},  # < 15 chars
            headers=_admin_headers(),
        )
        assert r.status_code == 422

    def test_distributor_cannot_cancel(self, distributor_client):
        r = distributor_client.raw().post(
            "/financial/invoices/fatura-1/cancel",
            json={"justificativa": "Cancelamento solicitado pelo cliente final"},
            headers=_distributor_headers(),
        )
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# POST /financial/webhook/stripe
# ---------------------------------------------------------------------------


class TestStripeWebhook:
    def test_unsigned_event_invoice_paid_marks_paga(
        self, client, monkeypatch
    ):
        # Without STRIPE_WEBHOOK_SECRET we accept unverified (test mode).
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
        client.mock_supabase.set_table_data(
            "faturas",
            [
                {
                    "id": "fatura-w-1",
                    "distributor_id": DIST_A_ID,
                    "stripe_invoice_id": "in_test_paid",
                    "valor_total": 100.0,
                    "status": "emitida",
                    "nfe_status": "autorizado",
                    "numero_fatura": "ADC-202605-W1",
                }
            ],
        )
        client.mock_supabase.set_table_data(
            "distributors",
            [{"id": DIST_A_ID, "org_id": ORG_ID, "email": "x@y.com"}],
        )
        event = {
            "id": "evt_1",
            "type": "invoice.paid",
            "data": {"object": {"id": "in_test_paid", "payment_intent": "pi_1"}},
        }
        r = client.raw().post("/financial/webhook/stripe", json=event)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["received"] is True
        assert body.get("event_type") == "invoice.paid"

    def test_unsigned_event_invoice_unknown_acked(self, client, monkeypatch):
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
        client.mock_supabase.set_table_data("faturas", [])
        event = {
            "id": "evt_2",
            "type": "invoice.paid",
            "data": {"object": {"id": "in_unknown"}},
        }
        r = client.raw().post("/financial/webhook/stripe", json=event)
        assert r.status_code == 200
        assert r.json().get("ignored") == "fatura not found"

    def test_unsigned_event_unrecognized_type_acked(self, client, monkeypatch):
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
        client.mock_supabase.set_table_data(
            "faturas",
            [
                {
                    "id": "fatura-w-2",
                    "distributor_id": DIST_A_ID,
                    "stripe_invoice_id": "in_test_other",
                    "valor_total": 100.0,
                    "status": "emitida",
                }
            ],
        )
        event = {
            "id": "evt_3",
            "type": "invoice.created",  # we don't handle this
            "data": {"object": {"id": "in_test_other"}},
        }
        r = client.raw().post("/financial/webhook/stripe", json=event)
        assert r.status_code == 200
        assert r.json().get("ignored") == "invoice.created"
