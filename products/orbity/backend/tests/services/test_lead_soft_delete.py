"""Lead soft delete + captured-lead first-stage (O80). No monkeypatching of our own code."""
from uuid import UUID

from noctusai_lib.testing import MockSupabaseClient

from app.services.automation_service import AutomationService
from app.services.crm_service import CRMService
from app.services.reports_service import ReportsService
from app.services.whatsapp_inbound import find_lead_by_phone
from tests.services.test_crm_service import _lead, _stage

ORG = UUID("00000000-0000-0000-0000-000000000999")
GONE = "2026-10-01T00:00:00+00:00"


def _crm(rows=None, **tables):
    db = MockSupabaseClient(data=rows, schema="orbity")
    for name, data in tables.items():
        db.set_table_data(name, data)
    return db, CRMService(db, org_id=ORG)


class TestSoftDelete:
    def test_delete_stamps_deleted_at_and_never_hard_deletes(self):
        db, svc = _crm([_lead(id_="l-1")])
        assert svc.delete_lead("l-1", deleted_by="u-1") is True
        patch = db.table("leads").updated_payloads[-1]
        assert patch["deleted_by"] == "u-1" and patch["deleted_at"]

    def test_deleting_an_already_deleted_lead_is_false(self):
        _db, svc = _crm([{**_lead(id_="l-1"), "deleted_at": GONE}])
        assert svc.delete_lead("l-1") is False

    def test_deleted_lead_is_gone_from_get_and_list(self):
        _db, svc = _crm([{**_lead(id_="l-1"), "deleted_at": GONE}, {**_lead(id_="l-2"), "deleted_at": None}])
        assert svc.get_lead("l-1") is None
        assert [r["id"] for r in svc.list_leads()["items"]] == ["l-2"]

    def test_deleted_lead_is_gone_from_the_funil(self):
        _db, svc = _crm(
            [{**_lead(id_="l-1"), "deleted_at": GONE}, {**_lead(id_="l-2"), "deleted_at": None}],
            lead_stages=[_stage("s-1")],
        )
        col = svc.get_funil()[0]
        assert [c["id"] for c in col["leads"]] == ["l-2"] and col["count"] == 1

    def test_deleted_lead_cannot_be_updated(self):
        _db, svc = _crm([{**_lead(id_="l-1"), "deleted_at": GONE}])
        assert svc.update_lead("l-1", {"name": "x"}) is None

    def test_deleted_lead_not_counted_in_report(self):
        db = MockSupabaseClient(schema="orbity")
        db.set_table_data("leads", [
            {**_lead(id_="l-1"), "temperature": "hot", "deleted_at": GONE},
            {**_lead(id_="l-2"), "temperature": "hot", "deleted_at": None},
        ])
        agg = ReportsService(db, org_id=ORG)._aggregate_leads("2026-01-01", "2026-12-31")
        assert agg["total"] == 1 and agg["hot"] == 1

    def test_whatsapp_inbound_ignores_deleted_lead(self):
        db = MockSupabaseClient(schema="orbity")
        db.set_table_data("leads", [{"id": "l-1", "org_id": str(ORG), "name": "A", "phone": "5511999998888", "deleted_at": GONE}])
        assert find_lead_by_phone(db, str(ORG), "11999998888") is None


class TestAutomationCancelForRemovedLead:
    def test_running_executions_are_cancelled_and_actions_skipped_rows_kept(self):
        db = MockSupabaseClient(schema="orbity")
        db.set_table_data("automation_executions", [
            {"id": "e-1", "org_id": str(ORG), "lead_id": "l-1", "status": "running"},
            {"id": "e-2", "org_id": str(ORG), "lead_id": "l-1", "status": "done"},
        ])
        db.set_table_data("automation_pending_actions", [
            {"id": "a-1", "org_id": str(ORG), "execution_id": "e-1", "status": "pending"},
        ])
        out = AutomationService(db, org_id=ORG).cancel_for_removed_lead("l-1")
        assert out == {"canceled": 1, "actions_skipped": 1}
        ex = db.table("automation_executions").updated_payloads
        assert len(ex) == 1 and ex[0]["status"] == "canceled" and ex[0]["error_detail"] == "Lead removido"
        assert db.table("automation_pending_actions").updated_payloads[0]["status"] == "skipped"


class TestCaptureFirstStage:
    def test_captured_lead_lands_in_the_lowest_position_stage(self):
        db, svc = _crm([], lead_stages=[_stage("s-2", position=1), _stage("s-1", position=0)])
        svc.capture_lead({"name": "Cap"})
        assert db.table("leads").inserted_payloads[-1]["stage_id"] == "s-1"

    def test_explicit_stage_is_respected(self):
        db, svc = _crm([], lead_stages=[_stage("s-1")])
        svc.capture_lead({"name": "Cap", "stage_id": "s-9"})
        assert db.table("leads").inserted_payloads[-1]["stage_id"] == "s-9"

    def test_org_without_stages_warns_and_keeps_null_stage(self, caplog):
        db, svc = _crm([], lead_stages=[])
        with caplog.at_level("WARNING"):
            svc.capture_lead({"name": "Cap"})
        assert "stage_id" not in db.table("leads").inserted_payloads[-1] or db.table("leads").inserted_payloads[-1]["stage_id"] is None
        assert "no lead stage" in caplog.text

    def test_capture_of_a_deleted_leads_phone_inserts_a_fresh_row(self):
        db, svc = _crm([{**_lead(id_="l-old"), "phone": "5511999998888", "deleted_at": GONE}], lead_stages=[_stage("s-1")])
        row = svc.capture_lead({"name": "Again", "phone": "11999998888"})
        assert len(db.table("leads").inserted_payloads) == 1 and row["name"] == "Again"
        assert db.table("leads").updated_payloads == []
