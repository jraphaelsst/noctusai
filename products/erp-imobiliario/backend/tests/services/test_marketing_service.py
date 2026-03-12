"""
Unit tests for marketing_service — campaign stats aggregation and alert matching.
"""
import pytest

from tests.conftest import MockSupabaseClient


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
        rows = [
            {"status": "pendente"},
            {"status": "enviado"},
            {"status": "enviado"},
            {"status": "aberto"},
            {"status": "clicado"},
            {"status": "erro"},
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
        rows = [
            {"status": "pendente"},
            {"status": "desconhecido"},
        ]
        db = MockSupabaseClient(data=rows)

        from app.services.marketing_service import get_campaign_stats
        stats = get_campaign_stats("camp-1", db)

        assert stats["total"] == 2
        assert stats["pendente"] == 1
        # "desconhecido" is not in the recognized statuses
        assert stats["enviado"] == 0

    def test_missing_status_defaults_to_pendente(self):
        rows = [{"foo": "bar"}]
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
        db = MockSupabaseClient()
        db.set_table_data("ativos", [
            {"id": "imv-1", "tipo_imovel": "apartamento", "cidade": "Curitiba",
             "bairro": "Batel", "valor": 600000, "titulo_anuncio": "Apt Batel",
             "natureza": "imovel", "status": "ativo"},
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
        db = MockSupabaseClient()
        db.set_table_data("ativos", [
            {"id": "imv-1", "tipo_imovel": "casa", "cidade": "Curitiba",
             "bairro": "Centro", "valor": 300000, "titulo_anuncio": "Casa Centro",
             "natureza": "imovel", "status": "ativo"},
            {"id": "imv-2", "tipo_imovel": "apartamento", "cidade": "Curitiba",
             "bairro": "Batel", "valor": 600000, "titulo_anuncio": "Apt Batel",
             "natureza": "imovel", "status": "ativo"},
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
