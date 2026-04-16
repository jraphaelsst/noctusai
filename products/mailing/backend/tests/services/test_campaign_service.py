"""Unit tests for CampaignService."""
from datetime import datetime, timezone

from noctusai_lib.testing import MockSupabaseClient, MockSupabaseResponse

from app.services.campaign_service import CampaignService

ORG = "org-test-001"
USER = "user-001"


# ---------------------------------------------------------------------------
# create_campaign()
# ---------------------------------------------------------------------------

class TestCreateCampaign:
    def test_sets_org_id_and_created_by(self):
        db = MockSupabaseClient()
        campaign = {"id": "camp1", "org_id": ORG, "created_by": USER, "nome": "Test"}
        db.set_table_data("campaigns", [campaign])

        svc = CampaignService(db, ORG)
        data = {"nome": "Test"}
        result = svc.create_campaign(data, USER)

        assert data["org_id"] == ORG
        assert data["created_by"] == USER
        assert result is not None

    def test_returns_created_campaign(self):
        db = MockSupabaseClient()
        campaign = {"id": "camp1", "nome": "Newsletter", "org_id": ORG, "created_by": USER}
        db.set_table_data("campaigns", [campaign])

        svc = CampaignService(db, ORG)
        result = svc.create_campaign({"nome": "Newsletter"}, USER)

        assert result["id"] == "camp1"


# ---------------------------------------------------------------------------
# update_campaign() — only allows rascunho/agendada
# ---------------------------------------------------------------------------

class TestUpdateCampaign:
    def _setup(self, campaign_data):
        db = MockSupabaseClient()
        # Sequential: first call is get_campaign (select), second is update
        db.set_sequential_responses("campaigns", [
            MockSupabaseResponse(data=[campaign_data] if campaign_data else []),
            MockSupabaseResponse(data=[{**campaign_data, "nome": "Updated"}] if campaign_data else []),
        ])
        return CampaignService(db, ORG)

    def test_allows_update_when_rascunho(self):
        svc = self._setup({"id": "c1", "status": "rascunho", "org_id": ORG})
        result = svc.update_campaign("c1", {"nome": "Updated"})
        assert result is not None

    def test_allows_update_when_agendada(self):
        svc = self._setup({"id": "c1", "status": "agendada", "org_id": ORG})
        result = svc.update_campaign("c1", {"nome": "Updated"})
        assert result is not None

    def test_blocks_update_when_enviando(self):
        svc = self._setup({"id": "c1", "status": "enviando", "org_id": ORG})
        result = svc.update_campaign("c1", {"nome": "Updated"})
        assert result is None

    def test_blocks_update_when_enviada(self):
        svc = self._setup({"id": "c1", "status": "enviada", "org_id": ORG})
        result = svc.update_campaign("c1", {"nome": "Updated"})
        assert result is None

    def test_returns_none_when_campaign_not_found(self):
        svc = self._setup(None)
        result = svc.update_campaign("missing", {"nome": "X"})
        assert result is None


# ---------------------------------------------------------------------------
# delete_campaign() — only allows rascunho
# ---------------------------------------------------------------------------

class TestDeleteCampaign:
    def _setup(self, campaign_data):
        db = MockSupabaseClient()
        db.set_sequential_responses("campaigns", [
            MockSupabaseResponse(data=[campaign_data] if campaign_data else []),
            MockSupabaseResponse(data=[]),  # delete response
        ])
        return CampaignService(db, ORG)

    def test_allows_delete_when_rascunho(self):
        svc = self._setup({"id": "c1", "status": "rascunho", "org_id": ORG})
        assert svc.delete_campaign("c1") is True

    def test_blocks_delete_when_agendada(self):
        svc = self._setup({"id": "c1", "status": "agendada", "org_id": ORG})
        assert svc.delete_campaign("c1") is False

    def test_blocks_delete_when_enviada(self):
        svc = self._setup({"id": "c1", "status": "enviada", "org_id": ORG})
        assert svc.delete_campaign("c1") is False

    def test_returns_false_when_not_found(self):
        svc = self._setup(None)
        assert svc.delete_campaign("missing") is False


# ---------------------------------------------------------------------------
# schedule_campaign()
# ---------------------------------------------------------------------------

class TestScheduleCampaign:
    def test_sets_status_to_agendada(self):
        db = MockSupabaseClient()
        scheduled = {"id": "c1", "status": "agendada", "org_id": ORG}
        db.set_table_data("campaigns", [scheduled])

        svc = CampaignService(db, ORG)
        scheduled_at = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
        result = svc.schedule_campaign("c1", scheduled_at)

        assert result is not None
        assert result["status"] == "agendada"


# ---------------------------------------------------------------------------
# start_send()
# ---------------------------------------------------------------------------

class TestStartSend:
    def test_sets_status_to_enviando(self):
        db = MockSupabaseClient()
        sending = {"id": "c1", "status": "enviando", "org_id": ORG}
        db.set_table_data("campaigns", [sending])

        svc = CampaignService(db, ORG)
        result = svc.start_send("c1")

        assert result is not None
        assert result["status"] == "enviando"


# ---------------------------------------------------------------------------
# pause_campaign()
# ---------------------------------------------------------------------------

class TestPauseCampaign:
    def test_sets_status_to_pausada(self):
        db = MockSupabaseClient()
        paused = {"id": "c1", "status": "pausada", "org_id": ORG}
        db.set_table_data("campaigns", [paused])

        svc = CampaignService(db, ORG)
        result = svc.pause_campaign("c1")

        assert result is not None
        assert result["status"] == "pausada"


# ---------------------------------------------------------------------------
# complete_campaign()
# ---------------------------------------------------------------------------

class TestCompleteCampaign:
    def test_sets_status_to_enviada(self):
        db = MockSupabaseClient()
        completed = {"id": "c1", "status": "enviada", "org_id": ORG}
        db.set_table_data("campaigns", [completed])

        svc = CampaignService(db, ORG)
        result = svc.complete_campaign("c1")

        assert result is not None
        assert result["status"] == "enviada"


# ---------------------------------------------------------------------------
# get_stats()
# ---------------------------------------------------------------------------

class TestGetStats:
    def test_aggregates_send_log_statuses(self):
        db = MockSupabaseClient()
        logs = [
            {"status": "sent"},
            {"status": "sent"},
            {"status": "queued"},
            {"status": "delivered"},
            {"status": "opened"},
            {"status": "bounced"},
            {"status": "failed"},
        ]
        db.set_table_data("send_logs", logs)

        svc = CampaignService(db, ORG)
        stats = svc.get_stats("c1")

        assert stats["total"] == 7
        assert stats["sent"] == 2
        assert stats["queued"] == 1
        assert stats["delivered"] == 1
        assert stats["opened"] == 1
        assert stats["bounced"] == 1
        assert stats["failed"] == 1
        assert stats["clicked"] == 0
        assert stats["complained"] == 0

    def test_returns_zeros_when_no_logs(self):
        db = MockSupabaseClient()
        db.set_table_data("send_logs", [])

        svc = CampaignService(db, ORG)
        stats = svc.get_stats("c1")

        assert stats["total"] == 0
        assert all(v == 0 for k, v in stats.items() if k != "total")
