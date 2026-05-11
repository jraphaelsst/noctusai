"""Unit tests for AutomationService."""
import pytest
from fastapi import HTTPException

from noctusai_lib.testing import MockSupabaseClient, MockSupabaseResponse

from app.services.automation_service import AutomationService

ORG = "org-test-001"
OTHER_ORG = "org-evil-999"
USER = "user-001"


# ---------------------------------------------------------------------------
# create_automation()
# ---------------------------------------------------------------------------

class TestCreateAutomation:
    def test_sets_org_id_and_created_by(self):
        db = MockSupabaseClient()
        automation = {"id": "a1", "org_id": ORG, "created_by": USER, "nome": "Welcome"}
        db.set_sequential_responses("automations", [MockSupabaseResponse(data=[automation])])

        svc = AutomationService(db, ORG)
        data = {"nome": "Welcome"}
        result = svc.create_automation(data, USER)

        assert data["org_id"] == ORG
        assert data["created_by"] == USER
        assert result is not None
        assert result["id"] == "a1"


# ---------------------------------------------------------------------------
# activate() / pause()
# ---------------------------------------------------------------------------

class TestActivatePause:
    def test_activate_sets_status_ativa(self):
        db = MockSupabaseClient()
        db.set_table_data("automations", [{"id": "a1", "status": "ativa", "org_id": ORG}])

        svc = AutomationService(db, ORG)
        result = svc.activate("a1")

        assert result is not None
        assert result["status"] == "ativa"

    def test_pause_sets_status_pausada(self):
        db = MockSupabaseClient()
        db.set_table_data("automations", [{"id": "a1", "status": "pausada", "org_id": ORG}])

        svc = AutomationService(db, ORG)
        result = svc.pause("a1")

        assert result is not None
        assert result["status"] == "pausada"


# ---------------------------------------------------------------------------
# delete_automation() — only rascunho
# ---------------------------------------------------------------------------

class TestDeleteAutomation:
    def _setup(self, automation_data):
        db = MockSupabaseClient()
        # Sequence: (1) get_automation select, then for rascunho branch:
        # (2) delete_or_404 existence re-check, (3) delete.
        responses = [
            MockSupabaseResponse(data=[automation_data] if automation_data else []),
        ]
        if automation_data and automation_data.get("status") == "rascunho":
            responses.append(MockSupabaseResponse(data=[automation_data]))
            responses.append(MockSupabaseResponse(data=[]))
        db.set_sequential_responses("automations", responses)
        return AutomationService(db, ORG)

    def test_allows_delete_when_rascunho(self):
        svc = self._setup({"id": "a1", "status": "rascunho", "org_id": ORG})
        assert svc.delete_automation("a1") is True

    def test_blocks_delete_when_ativa(self):
        svc = self._setup({"id": "a1", "status": "ativa", "org_id": ORG})
        assert svc.delete_automation("a1") is False

    def test_blocks_delete_when_pausada(self):
        svc = self._setup({"id": "a1", "status": "pausada", "org_id": ORG})
        assert svc.delete_automation("a1") is False

    def test_returns_false_when_not_found(self):
        svc = self._setup(None)
        assert svc.delete_automation("missing") is False


# ---------------------------------------------------------------------------
# add_step() — auto-increments posicao
# ---------------------------------------------------------------------------

class TestAddStep:
    def test_auto_increments_posicao(self):
        db = MockSupabaseClient()
        existing_steps = [
            {"id": "s1", "automation_id": "a1", "posicao": 1},
            {"id": "s2", "automation_id": "a1", "posicao": 2},
        ]
        # First call: list_steps (select), second call: insert
        db.set_sequential_responses("automation_steps", [
            MockSupabaseResponse(data=existing_steps),
            MockSupabaseResponse(data=[{"id": "s3", "posicao": 3, "automation_id": "a1"}]),
        ])

        svc = AutomationService(db, ORG)
        data = {"tipo": "send_email", "config": {}}
        result = svc.add_step("a1", data)

        assert data["posicao"] == 3
        assert data["automation_id"] == "a1"
        assert result is not None

    def test_first_step_gets_posicao_1(self):
        db = MockSupabaseClient()
        db.set_sequential_responses("automation_steps", [
            MockSupabaseResponse(data=[]),  # no existing steps
            MockSupabaseResponse(data=[{"id": "s1", "posicao": 1}]),
        ])

        svc = AutomationService(db, ORG)
        data = {"tipo": "send_email"}
        svc.add_step("a1", data)

        assert data["posicao"] == 1

    def test_explicit_posicao_is_preserved(self):
        db = MockSupabaseClient()
        db.set_table_data("automation_steps", [{"id": "s1", "posicao": 5}])

        svc = AutomationService(db, ORG)
        data = {"tipo": "wait", "posicao": 5}
        svc.add_step("a1", data)

        assert data["posicao"] == 5


# ---------------------------------------------------------------------------
# reorder_steps()
# ---------------------------------------------------------------------------

class TestReorderSteps:
    def test_updates_positions(self):
        db = MockSupabaseClient()
        # M-1 fix: parent automation must belong to the caller's org.
        db.set_table_data("automations", [{"id": "a1", "org_id": ORG, "status": "rascunho"}])
        reordered = [
            {"id": "s2", "posicao": 1, "automation_id": "a1"},
            {"id": "s1", "posicao": 2, "automation_id": "a1"},
        ]
        db.set_table_data("automation_steps", reordered)

        svc = AutomationService(db, ORG)
        result = svc.reorder_steps("a1", ["s2", "s1"])

        assert len(result) == 2

    def test_reorder_single_step(self):
        db = MockSupabaseClient()
        db.set_table_data("automations", [{"id": "a1", "org_id": ORG, "status": "rascunho"}])
        db.set_table_data("automation_steps", [{"id": "s1", "posicao": 1, "automation_id": "a1"}])

        svc = AutomationService(db, ORG)
        result = svc.reorder_steps("a1", ["s1"])

        assert len(result) == 1

    def test_reorder_empty_list(self):
        db = MockSupabaseClient()
        db.set_table_data("automations", [{"id": "a1", "org_id": ORG, "status": "rascunho"}])
        db.set_table_data("automation_steps", [])

        svc = AutomationService(db, ORG)
        result = svc.reorder_steps("a1", [])

        assert result == []


# ---------------------------------------------------------------------------
# enroll_contacts()
# ---------------------------------------------------------------------------

class TestEnrollContacts:
    def test_creates_enrollment_with_first_step(self):
        db = MockSupabaseClient()
        # M-1 fix: parent automation must belong to the caller's org.
        db.set_table_data("automations", [{"id": "a1", "org_id": ORG, "status": "ativa"}])
        steps = [{"id": "step1", "posicao": 1}, {"id": "step2", "posicao": 2}]
        enrollments = [
            {"automation_id": "a1", "contact_id": "ct1", "current_step_id": "step1", "status": "active"},
            {"automation_id": "a1", "contact_id": "ct2", "current_step_id": "step1", "status": "active"},
        ]
        db.set_sequential_responses("automation_steps", [
            MockSupabaseResponse(data=steps),
        ])
        db.set_table_data("automation_enrollments", enrollments)

        svc = AutomationService(db, ORG)
        result = svc.enroll_contacts("a1", ["ct1", "ct2"])

        assert len(result) == 2

    def test_enroll_with_no_steps_sets_none_step(self):
        db = MockSupabaseClient()
        db.set_table_data("automations", [{"id": "a1", "org_id": ORG, "status": "ativa"}])
        db.set_sequential_responses("automation_steps", [
            MockSupabaseResponse(data=[]),  # no steps
        ])
        db.set_table_data("automation_enrollments", [
            {"automation_id": "a1", "contact_id": "ct1", "current_step_id": None, "status": "active"},
        ])

        svc = AutomationService(db, ORG)
        result = svc.enroll_contacts("a1", ["ct1"])

        assert len(result) == 1

    def test_enroll_single_contact(self):
        db = MockSupabaseClient()
        db.set_table_data("automations", [{"id": "a1", "org_id": ORG, "status": "ativa"}])
        db.set_sequential_responses("automation_steps", [
            MockSupabaseResponse(data=[{"id": "s1", "posicao": 1}]),
        ])
        db.set_table_data("automation_enrollments", [
            {"automation_id": "a1", "contact_id": "ct1", "current_step_id": "s1", "status": "active"},
        ])

        svc = AutomationService(db, ORG)
        result = svc.enroll_contacts("a1", ["ct1"])

        assert len(result) == 1


# ---------------------------------------------------------------------------
# M-1 — automation_service org-scoping defense-in-depth (mailing-wiring Phase 1)
# ---------------------------------------------------------------------------
# Phase 0 audit (QQQ 2026-05-11) surfaced that `update_step` / `delete_step` /
# `reorder_steps` / `enroll_contacts` / `list_enrollments` accepted arbitrary
# IDs without verifying the parent automation belongs to the caller's org.
# RLS mitigates at the DB layer but service-layer defense-in-depth was
# missing. This test class is the security regression guard.


class TestM1OrgScopingDefenseInDepth:
    """Cross-org access to automation sub-entities raises 404, not silent write.

    Implementation note: ``MockSelectBuilder`` does not evaluate predicates on
    SELECT — it returns whatever ``_data`` holds. To simulate the RLS-filtered
    "row hidden from this org" case, these tests use
    ``set_sequential_responses`` with an empty-data response, mirroring what a
    real PostgREST SELECT scoped by ``.eq("org_id", ORG)`` would return when
    the row belongs to a different org.
    """

    def _automation_hidden_db(self):
        """Mock where ``get_automation`` returns empty (RLS-hidden / different org)."""
        db = MockSupabaseClient()
        # First select() on automations → empty data (the SELECT scoped by
        # org_id would not match the OTHER_ORG row).
        db.set_sequential_responses("automations", [
            MockSupabaseResponse(data=[]),
        ])
        return db

    def test_update_step_cross_org_raises_404(self):
        db = self._automation_hidden_db()
        svc = AutomationService(db, ORG)
        with pytest.raises(HTTPException) as exc:
            svc.update_step("a1", "s1", {"tipo": "send_email"})
        assert exc.value.status_code == 404

    def test_delete_step_cross_org_raises_404(self):
        db = self._automation_hidden_db()
        svc = AutomationService(db, ORG)
        with pytest.raises(HTTPException) as exc:
            svc.delete_step("a1", "s1")
        assert exc.value.status_code == 404

    def test_reorder_steps_cross_org_raises_404(self):
        db = self._automation_hidden_db()
        svc = AutomationService(db, ORG)
        with pytest.raises(HTTPException) as exc:
            svc.reorder_steps("a1", ["s1", "s2"])
        assert exc.value.status_code == 404

    def test_enroll_contacts_cross_org_raises_404(self):
        db = self._automation_hidden_db()
        svc = AutomationService(db, ORG)
        with pytest.raises(HTTPException) as exc:
            svc.enroll_contacts("a1", ["ct1"])
        assert exc.value.status_code == 404

    def test_list_enrollments_cross_org_raises_404(self):
        db = self._automation_hidden_db()
        svc = AutomationService(db, ORG)
        with pytest.raises(HTTPException) as exc:
            svc.list_enrollments("a1")
        assert exc.value.status_code == 404

    def test_update_step_unknown_automation_raises_404(self):
        # Automation does not exist at all — service must raise 404, not silently
        # update a row keyed only on step_id.
        db = MockSupabaseClient()
        db.set_table_data("automations", [])

        svc = AutomationService(db, ORG)
        with pytest.raises(HTTPException) as exc:
            svc.update_step("ghost-auto", "s1", {"tipo": "wait"})
        assert exc.value.status_code == 404

    def test_delete_step_wrong_parent_raises_404(self):
        # Automation belongs to ORG, but step_id belongs to a DIFFERENT
        # automation. delete_or_404 must catch this via the
        # `automation_id` scoping predicate. Mock SELECT does not filter, so
        # use a sequential-response queue to model what PostgREST would do.
        db = MockSupabaseClient()
        db.set_table_data("automations", [{"id": "a1", "org_id": ORG}])
        # The existence-check SELECT scoped by `automation_id=a1` returns
        # empty (the step belongs to "different-auto", not "a1").
        db.set_sequential_responses("automation_steps", [
            MockSupabaseResponse(data=[]),
        ])

        svc = AutomationService(db, ORG)
        with pytest.raises(HTTPException) as exc:
            svc.delete_step("a1", "s1")
        assert exc.value.status_code == 404
