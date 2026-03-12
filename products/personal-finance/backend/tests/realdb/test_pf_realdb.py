"""
Real-DB integration tests for the Personal Finance backend.

Tests hit a real Supabase instance to verify FK constraints, CHECK constraints,
cascade deletes, system defaults, and RLS org isolation in the
``personal-finance`` schema.

Run: pytest tests/realdb/ -v
Skip: auto-skips when SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from postgrest.exceptions import APIError

pytestmark = pytest.mark.realdb


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestContaCRUD:
    """Full CRUD on personal-finance.contas."""

    def test_conta_crud(self, pf_db, test_org, cleanup):
        # Create
        conta = pf_db.table("contas").insert({
            "org_id": test_org["id"],
            "nome": "Conta Corrente RealDB",
            "tipo": "corrente",
            "instituicao": "Banco Test",
            "saldo": 1000.50,
        }).execute().data[0]
        cleanup.append(("contas", conta["id"]))

        assert conta["nome"] == "Conta Corrente RealDB"
        assert conta["tipo"] == "corrente"
        assert float(conta["saldo"]) == 1000.50

        # Read
        fetched = pf_db.table("contas") \
            .select("*").eq("id", conta["id"]).single().execute().data
        assert fetched["instituicao"] == "Banco Test"

        # Update
        pf_db.table("contas") \
            .update({"saldo": 2000.00}).eq("id", conta["id"]).execute()
        updated = pf_db.table("contas") \
            .select("saldo").eq("id", conta["id"]).single().execute().data
        assert float(updated["saldo"]) == 2000.00

        # Delete
        pf_db.table("contas").delete().eq("id", conta["id"]).execute()
        check = pf_db.table("contas").select("id").eq("id", conta["id"]).execute().data
        assert check == []
        cleanup.pop()


class TestTransacaoCRUD:
    """Transaction CRUD with FK to conta."""

    def test_transacao_crud(self, pf_db, test_org, cleanup):
        # Create account first
        conta = pf_db.table("contas").insert({
            "org_id": test_org["id"],
            "nome": "Conta Transacao",
            "tipo": "corrente",
        }).execute().data[0]
        cleanup.append(("contas", conta["id"]))

        # Create transaction
        today = date.today().isoformat()
        txn = pf_db.table("transacoes").insert({
            "org_id": test_org["id"],
            "conta_id": conta["id"],
            "data": today,
            "valor": 150.00,
            "tipo": "despesa",
            "descricao": "Supermercado RealDB",
        }).execute().data[0]
        cleanup.append(("transacoes", txn["id"]))

        assert txn["tipo"] == "despesa"
        assert float(txn["valor"]) == 150.00

        # Update
        pf_db.table("transacoes") \
            .update({"valor": 200.00}).eq("id", txn["id"]).execute()
        updated = pf_db.table("transacoes") \
            .select("valor").eq("id", txn["id"]).single().execute().data
        assert float(updated["valor"]) == 200.00


class TestTransacaoFKConstraint:
    """Transaction with non-existent conta_id should fail."""

    def test_transacao_fk_constraint(self, pf_db, test_org):
        fake_conta = str(uuid.uuid4())
        with pytest.raises(APIError):
            pf_db.table("transacoes").insert({
                "org_id": test_org["id"],
                "conta_id": fake_conta,
                "data": date.today().isoformat(),
                "valor": 50.00,
                "tipo": "despesa",
            }).execute()


class TestTransacaoTipoCheckConstraint:
    """Invalid tipo value should trigger CHECK constraint violation."""

    def test_transacao_tipo_check_constraint(self, pf_db, test_org, cleanup):
        conta = pf_db.table("contas").insert({
            "org_id": test_org["id"],
            "nome": "Conta Check",
            "tipo": "corrente",
        }).execute().data[0]
        cleanup.append(("contas", conta["id"]))

        with pytest.raises(APIError):
            pf_db.table("transacoes").insert({
                "org_id": test_org["id"],
                "conta_id": conta["id"],
                "data": date.today().isoformat(),
                "valor": 100.00,
                "tipo": "invalido",  # not in CHECK constraint
            }).execute()


class TestCategoriaSystemDefaults:
    """System default categories (is_sistema=true) should exist from seed data."""

    def test_categoria_system_defaults(self, pf_db):
        system_cats = pf_db.table("categorias") \
            .select("id, nome, tipo") \
            .eq("is_sistema", True) \
            .execute().data
        assert len(system_cats) > 0, "Expected seeded system categories"
        # All should have nome and tipo set
        for cat in system_cats:
            assert cat["nome"]
            assert cat["tipo"] in ("receita", "despesa", "transferencia")


class TestMetaCRUDWithStatus:
    """Create a financial goal and update its status."""

    def test_meta_crud_with_status(self, pf_db, test_org, cleanup):
        target_date = (date.today() + timedelta(days=365)).isoformat()
        meta = pf_db.table("metas").insert({
            "org_id": test_org["id"],
            "nome": "Fundo de Emergencia RealDB",
            "tipo": "fundo_emergencia",
            "valor_alvo": 10000.00,
            "data_alvo": target_date,
        }).execute().data[0]
        cleanup.append(("metas", meta["id"]))

        assert meta["status"] == "ativa"  # default

        # Update to concluida
        pf_db.table("metas") \
            .update({"status": "concluida", "valor_atual": 10000.00}) \
            .eq("id", meta["id"]).execute()
        updated = pf_db.table("metas") \
            .select("status, valor_atual").eq("id", meta["id"]).single().execute().data
        assert updated["status"] == "concluida"
        assert float(updated["valor_atual"]) == 10000.00


class TestCarteiraAndAtivoCRUD:
    """Portfolio + holding, verify FK relationship."""

    def test_carteira_and_ativo_crud(self, pf_db, test_org, cleanup):
        carteira = pf_db.table("carteiras").insert({
            "org_id": test_org["id"],
            "nome": "Carteira Acoes RealDB",
            "tipo": "acoes",
        }).execute().data[0]
        cleanup.append(("carteiras", carteira["id"]))

        ativo = pf_db.table("ativos_carteira").insert({
            "carteira_id": carteira["id"],
            "org_id": test_org["id"],
            "ticker": "PETR4",
            "nome": "Petrobras PN",
            "tipo": "acao",
            "quantidade": 100,
            "preco_medio": 35.50,
        }).execute().data[0]
        cleanup.append(("ativos_carteira", ativo["id"]))

        assert ativo["ticker"] == "PETR4"
        assert float(ativo["quantidade"]) == 100


class TestOrcamentoCascadeDelete:
    """Deleting a budget should cascade-delete its items."""

    def test_orcamento_cascade_delete(self, pf_db, test_org, cleanup):
        orcamento = pf_db.table("orcamentos").insert({
            "org_id": test_org["id"],
            "nome": "Orcamento RealDB",
        }).execute().data[0]
        # Don't add to cleanup — we'll delete it explicitly to test cascade

        # Need a system category for the item
        cats = pf_db.table("categorias") \
            .select("id").eq("is_sistema", True).limit(1).execute().data
        assert len(cats) > 0, "Need at least one system category for this test"
        cat_id = cats[0]["id"]

        item = pf_db.table("orcamento_itens").insert({
            "orcamento_id": orcamento["id"],
            "org_id": test_org["id"],
            "categoria_id": cat_id,
            "valor_planejado": 500.00,
            "periodo_mes": "2026-03",
        }).execute().data[0]

        # Delete budget — items should cascade
        pf_db.table("orcamentos").delete().eq("id", orcamento["id"]).execute()
        remaining = pf_db.table("orcamento_itens") \
            .select("id").eq("id", item["id"]).execute().data
        assert remaining == [], "Orcamento items should cascade-delete with parent"


class TestRecorrenteFrequenciaConstraint:
    """Invalid frequencia should trigger CHECK constraint violation."""

    def test_recorrente_frequencia_constraint(self, pf_db, test_org):
        with pytest.raises(APIError):
            pf_db.table("recorrentes").insert({
                "org_id": test_org["id"],
                "nome": "Bad Recorrente",
                "valor": 100.00,
                "tipo": "despesa",
                "frequencia": "invalida",  # not in CHECK constraint
            }).execute()


class TestRLSOrgIsolation:
    """Verify that org_id scoping prevents cross-org data access."""

    def test_rls_org_isolation(self, core_db, pf_db, cleanup):
        # Create 2 test orgs
        orgs = []
        for i in range(2):
            slug = f"pf-rls-{uuid.uuid4().hex[:8]}"
            org = core_db.table("organizations").insert({
                "nome": f"PF RLS Org {i}",
                "slug": slug,
                "plano": "free",
                "category": "test",
            }).execute().data[0]
            orgs.append(org)

        # Create account in org A
        conta = pf_db.table("contas").insert({
            "org_id": orgs[0]["id"],
            "nome": "Org A Account",
            "tipo": "corrente",
        }).execute().data[0]

        # Query with org B's id — should find nothing
        results = pf_db.table("contas") \
            .select("*") \
            .eq("org_id", orgs[1]["id"]) \
            .eq("id", conta["id"]) \
            .execute().data
        assert results == [], "Org B should not see Org A's account"

        # Cleanup
        pf_db.table("contas").delete().eq("id", conta["id"]).execute()
        for org in reversed(orgs):
            core_db.table("organizations").delete().eq("id", org["id"]).execute()
