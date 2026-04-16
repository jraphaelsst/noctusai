"""Unit tests for AutomationService."""
from noctusai_lib.testing import MockSupabaseClient, MockSupabaseResponse

from app.services.automation_service import AutomationService

ORG = "org-test-001"
USER = "user-001"


# ---------------------------------------------------------------------------
# create_automation()
# ---------------------------------------------------------------------------

class TestCreateAutomation:
    def test_sets_org_id_and_created_by(self):
        db = MockSupabaseClient()
        automation = {"id": "a1", "org_id": ORG, "created_by": USER, "nome": "Welcome"}
        db.set_table_data("automations", [automation])

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
        db.set_sequential_responses("automations", [
            MockSupabaseResponse(data=[automation_data] if automation_data else []),
            MockSupabaseResponse(data=[]),  # delete response
        ])
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
        reordered = [
            {"id": "s2", "posicao": 1},
            {"id": "s1", "posicao": 2},
        ]
        db.set_table_data("automation_steps", reordered)

        svc = AutomationService(db, ORG)
        result = svc.reorder_steps("a1", ["s2", "s1"])

        assert len(result) == 2

    def test_reorder_single_step(self):
        db = MockSupabaseClient()
        db.set_table_data("automation_steps", [{"id": "s1", "posicao": 1}])

        svc = AutomationService(db, ORG)
        result = svc.reorder_steps("a1", ["s1"])

        assert len(result) == 1

    def test_reorder_empty_list(self):
        db = MockSupabaseClient()
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
        db.set_sequential_responses("automation_steps", [
            MockSupabaseResponse(data=[{"id": "s1", "posicao": 1}]),
        ])
        db.set_table_data("automation_enrollments", [
            {"automation_id": "a1", "contact_id": "ct1", "current_step_id": "s1", "status": "active"},
        ])

        svc = AutomationService(db, ORG)
        result = svc.enroll_contacts("a1", ["ct1"])

        assert len(result) == 1
