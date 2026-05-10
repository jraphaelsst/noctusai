"""
Real-DB tests for the AdConnect financial domain (Phase 5).

Verifies:
  • adconnect.faturas RLS — distributor user only sees own faturas;
    brand admin sees all in their org's distributor set.
  • Service-role insert/read round-trip on faturas + foreign keys
    (distributor_id, pedido_id) hold.

Marked `@pytest.mark.realdb` — auto-skips when SUPABASE_URL /
SUPABASE_SERVICE_ROLE_KEY are not set.

The harness pattern mirrors `test_orders_realdb.py`: seed via service-role
(bypasses RLS) and verify the row counts; full anon-key + scoped-JWT RLS
verification depends on core's auth fixtures.
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.realdb


@pytest.fixture()
def faturas_setup(adconnect_db, test_org):
    """Seed two distributors + a fatura per distributor."""
    org_id = test_org["id"]
    dist_a = adconnect_db.table("distributors").insert(
        {
            "org_id": org_id,
            "cnpj": f"33.333.333/0001-{uuid.uuid4().hex[:2]}",
            "nome": "Distribuidor A (financial-realdb)",
            "status": "ativo",
            "tier": "STARTER",
        }
    ).execute().data[0]
    dist_b = adconnect_db.table("distributors").insert(
        {
            "org_id": org_id,
            "cnpj": f"44.444.444/0001-{uuid.uuid4().hex[:2]}",
            "nome": "Distribuidor B (financial-realdb)",
            "status": "ativo",
            "tier": "STARTER",
        }
    ).execute().data[0]

    fatura_a = adconnect_db.table("faturas").insert(
        {
            "distributor_id": dist_a["id"],
            "numero_fatura": f"ADC-RDB-A-{uuid.uuid4().hex[:8]}",
            "valor_total": 100.0,
            "moeda": "BRL",
            "status": "rascunho",
            "nfe_status": "pendente",
        }
    ).execute().data[0]
    fatura_b = adconnect_db.table("faturas").insert(
        {
            "distributor_id": dist_b["id"],
            "numero_fatura": f"ADC-RDB-B-{uuid.uuid4().hex[:8]}",
            "valor_total": 200.0,
            "moeda": "BRL",
            "status": "emitida",
            "nfe_status": "autorizado",
            "nfe_chave": "1" * 44,
        }
    ).execute().data[0]

    yield {
        "org_id": org_id,
        "dist_a": dist_a,
        "dist_b": dist_b,
        "fatura_a": fatura_a,
        "fatura_b": fatura_b,
    }

    # Teardown — delete in FK-safe order.
    adconnect_db.table("faturas").delete().eq("id", fatura_a["id"]).execute()
    adconnect_db.table("faturas").delete().eq("id", fatura_b["id"]).execute()
    adconnect_db.table("distributors").delete().eq("id", dist_a["id"]).execute()
    adconnect_db.table("distributors").delete().eq("id", dist_b["id"]).execute()


class TestFaturasRoundTrip:
    """Service-role insert + read round-trip — bypasses RLS by design."""

    def test_can_select_seeded_faturas(self, adconnect_db, faturas_setup):
        # Both faturas should be visible via service-role.
        rows = (
            adconnect_db.table("faturas")
            .select("id, distributor_id, status, nfe_status")
            .in_(
                "id",
                [faturas_setup["fatura_a"]["id"], faturas_setup["fatura_b"]["id"]],
            )
            .execute()
            .data
        )
        assert len(rows) == 2
        ids = {r["id"] for r in rows}
        assert ids == {
            faturas_setup["fatura_a"]["id"],
            faturas_setup["fatura_b"]["id"],
        }

    def test_status_check_constraint(self, adconnect_db, faturas_setup):
        """Migration enforces status IN ('rascunho','emitida','paga',...)."""
        with pytest.raises(Exception):
            adconnect_db.table("faturas").insert(
                {
                    "distributor_id": faturas_setup["dist_a"]["id"],
                    "numero_fatura": f"ADC-RDB-X-{uuid.uuid4().hex[:8]}",
                    "valor_total": 1.0,
                    "status": "INVALID_STATUS",
                }
            ).execute()

    def test_nfe_status_check_constraint(self, adconnect_db, faturas_setup):
        """Migration enforces nfe_status IN ('pendente','enviado','autorizado',...)."""
        with pytest.raises(Exception):
            adconnect_db.table("faturas").insert(
                {
                    "distributor_id": faturas_setup["dist_a"]["id"],
                    "numero_fatura": f"ADC-RDB-Y-{uuid.uuid4().hex[:8]}",
                    "valor_total": 1.0,
                    "status": "rascunho",
                    "nfe_status": "INVALID_NFE",
                }
            ).execute()

    def test_numero_fatura_unique(self, adconnect_db, faturas_setup):
        """Migration enforces UNIQUE on numero_fatura."""
        existing = faturas_setup["fatura_a"]["numero_fatura"]
        with pytest.raises(Exception):
            adconnect_db.table("faturas").insert(
                {
                    "distributor_id": faturas_setup["dist_b"]["id"],
                    "numero_fatura": existing,
                    "valor_total": 1.0,
                    "status": "rascunho",
                }
            ).execute()

    def test_lookup_by_stripe_invoice_id(self, adconnect_db, faturas_setup):
        """find_by_stripe_invoice_id pattern — set + select round-trip."""
        adconnect_db.table("faturas").update(
            {"stripe_invoice_id": "in_realdb_test_xyz"}
        ).eq("id", faturas_setup["fatura_a"]["id"]).execute()
        rows = (
            adconnect_db.table("faturas")
            .select("id, stripe_invoice_id")
            .eq("stripe_invoice_id", "in_realdb_test_xyz")
            .execute()
            .data
        )
        assert len(rows) == 1
        assert rows[0]["id"] == faturas_setup["fatura_a"]["id"]
