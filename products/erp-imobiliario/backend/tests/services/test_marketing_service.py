"""
Unit tests for marketing_service — campaign stats aggregation and alert matching.
"""
from datetime import datetime, timezone

import pytest

from tests.conftest import MockSupabaseClient

# `process_alerts` filters ativos by `.gte("created_at", cutoff)` where cutoff
# is 7 days ago. Use "now" so seed rows always satisfy the predicate regardless
# of when the test runs (pre-MOCK-SELECT-PREDICATE-FIX the predicate was
# tracked-but-unevaluated, so the column was absent).
_NOW_ISO = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# get_campaign_stats
# ---------------------------------------------------------------------------

class TestGetCampaignStats:

    def test_empty_sends(self):
        db = MockSupabaseClient(data=[])

        from app.services.marketing_service import get_campaign_stats
        stats = get_campaign_stats("camp-1", db)

        assert stats["total"] == 0
        assert stats["pendente"] == 0
        assert stats["enviado"] == 0
        assert stats["aberto"] == 0
        assert stats["clicado"] == 0
        assert stats["erro"] == 0

    def test_all_statuses_counted(self):
        # `campanha_id` required on each seed row: production filters by
        # `.eq("campanha_id", campanha_id)`. Pre-MOCK-SELECT-PREDICATE-FIX
        # predicates were tracked-but-unevaluated; once SELECT obeys them,
        # missing `campanha_id` silently strips rows.
        rows = [
            {"campanha_id": "camp-1", "status": "pendente"},
            {"campanha_id": "camp-1", "status": "enviado"},
            {"campanha_id": "camp-1", "status": "enviado"},
            {"campanha_id": "camp-1", "status": "aberto"},
            {"campanha_id": "camp-1", "status": "clicado"},
            {"campanha_id": "camp-1", "status": "erro"},
        ]
        db = MockSupabaseClient(data=rows)

        from app.services.marketing_service import get_campaign_stats
        stats = get_campaign_stats("camp-1", db)

        assert stats["total"] == 6
        assert stats["pendente"] == 1
        assert stats["enviado"] == 2
        assert stats["aberto"] == 1
        assert stats["clicado"] == 1
        assert stats["erro"] == 1

    def test_unknown_status_ignored(self):
        # `campanha_id` required on seed — same MOCK-SELECT shape as
        # test_all_statuses_counted above.
        rows = [
            {"campanha_id": "camp-1", "status": "pendente"},
            {"campanha_id": "camp-1", "status": "desconhecido"},
        ]
        db = MockSupabaseClient(data=rows)

        from app.services.marketing_service import get_campaign_stats
        stats = get_campaign_stats("camp-1", db)

        assert stats["total"] == 2
        assert stats["pendente"] == 1
        # "desconhecido" is not in the recognized statuses
        assert stats["enviado"] == 0

    def test_missing_status_defaults_to_pendente(self):
        # `campanha_id` required on seed — same MOCK-SELECT shape as
        # test_all_statuses_counted above. The `foo: bar` quirk is preserved
        # to exercise the "missing status defaults to pendente" branch.
        rows = [{"campanha_id": "camp-1", "foo": "bar"}]
        db = MockSupabaseClient(data=rows)

        from app.services.marketing_service import get_campaign_stats
        stats = get_campaign_stats("camp-1", db)

        assert stats["total"] == 1
        assert stats["pendente"] == 1


# ---------------------------------------------------------------------------
# process_alerts
# ---------------------------------------------------------------------------

class TestProcessAlerts:

    def test_no_imoveis_returns_empty(self):
        db = MockSupabaseClient(data=[])

        from app.services.marketing_service import process_alerts
        result = process_alerts("org-1", db)

        assert result == []

    def test_no_clients_returns_empty(self):
        """Properties exist but no clients with interests -> empty."""
        db = MockSupabaseClient()
        db.set_table_data("ativos", [
            {"id": "imv-1", "tipo_imovel": "casa", "cidade": "SP", "bairro": "Centro",
             "valor": 500000, "titulo_anuncio": "Casa bonita", "natureza": "imovel", "status": "ativo"},
        ])
        db.set_table_data("clientes", [])

        from app.services.marketing_service import process_alerts
        result = process_alerts("org-1", db)

        assert result == []

    def test_keyword_match(self):
        # `created_at` required on each ativo seed row: production filters by
        # `.gte("created_at", cutoff)` (cutoff = now − 7d). Pre-MOCK-SELECT-
        # PREDICATE-FIX the gte predicate was tracked-but-unevaluated; once
        # SELECT obeys it, rows without `created_at` are stripped (gte against
        # None returns False).
        db = MockSupabaseClient()
        db.set_table_data("ativos", [
            {"id": "imv-1", "tipo_imovel": "apartamento", "cidade": "Curitiba",
             "bairro": "Batel", "valor": 600000, "titulo_anuncio": "Apt Batel",
             "natureza": "imovel", "status": "ativo", "created_at": _NOW_ISO},
        ])
        db.set_table_data("clientes", [
            {"id": "cli-1", "nome": "Joao", "email": "joao@test.com",
             "interesse": "apartamento Batel", "telefone": "41999"},
        ])

        from app.services.marketing_service import process_alerts
        result = process_alerts("org-1", db)

        assert len(result) == 1
        assert result[0]["cliente_id"] == "cli-1"
        assert result[0]["imovel_id"] == "imv-1"
        assert "apartamento" in result[0]["motivo"].lower() or "batel" in result[0]["motivo"].lower()

    def test_no_keyword_match(self):
        db = MockSupabaseClient()
        db.set_table_data("ativos", [
            {"id": "imv-1", "tipo_imovel": "casa", "cidade": "SP",
             "bairro": "Centro", "valor": 500000, "titulo_anuncio": "Casa SP",
             "natureza": "imovel", "status": "ativo"},
        ])
        db.set_table_data("clientes", [
            {"id": "cli-1", "nome": "Maria", "email": "m@test.com",
             "interesse": "terreno Curitiba", "telefone": "41888"},
        ])

        from app.services.marketing_service import process_alerts
        result = process_alerts("org-1", db)

        assert result == []

    def test_empty_interesse_skipped(self):
        db = MockSupabaseClient()
        db.set_table_data("ativos", [
            {"id": "imv-1", "tipo_imovel": "casa", "cidade": "SP",
             "bairro": "Centro", "valor": 500000, "titulo_anuncio": "Casa SP",
             "natureza": "imovel", "status": "ativo"},
        ])
        db.set_table_data("clientes", [
            {"id": "cli-1", "nome": "Ana", "email": "a@test.com",
             "interesse": "", "telefone": ""},
        ])

        from app.services.marketing_service import process_alerts
        result = process_alerts("org-1", db)

        assert result == []

    def test_multiple_matches(self):
        # `created_at` required on each ativo seed row — same MOCK-SELECT shape
        # as test_keyword_match above.
        db = MockSupabaseClient()
        db.set_table_data("ativos", [
            {"id": "imv-1", "tipo_imovel": "casa", "cidade": "Curitiba",
             "bairro": "Centro", "valor": 300000, "titulo_anuncio": "Casa Centro",
             "natureza": "imovel", "status": "ativo", "created_at": _NOW_ISO},
            {"id": "imv-2", "tipo_imovel": "apartamento", "cidade": "Curitiba",
             "bairro": "Batel", "valor": 600000, "titulo_anuncio": "Apt Batel",
             "natureza": "imovel", "status": "ativo", "created_at": _NOW_ISO},
        ])
        db.set_table_data("clientes", [
            {"id": "cli-1", "nome": "Pedro", "email": "p@test.com",
             "interesse": "Curitiba", "telefone": "41999"},
        ])

        from app.services.marketing_service import process_alerts
        result = process_alerts("org-1", db)

        # Both properties are in Curitiba, so both should match
        assert len(result) == 2
        imovel_ids = {m["imovel_id"] for m in result}
        assert "imv-1" in imovel_ids
        assert "imv-2" in imovel_ids
