"""
Table-driven unit tests for AutomationEngine.advance() and run_due_actions().

These are PURE unit tests — no DB, no network. The engine is a pure-logic
state machine; tests drive it directly.

Coverage goals:
  - send_message/send_whatsapp_media: schedules pending_action
  - wait: schedules pending_action with wake_at
  - condition: equals/not_equals/contains/exists/greater_than/less_than +
               is_true/is_false + on_true/on_false branching
  - branch: on_true_step_ord / on_false_step_ord jumps
  - action: schedules pending_action
  - end: marks done
  - no_reply stop rule (condition on_false=stop)
  - out-of-steps edge (all steps done → done)
  - empty flow (no steps → done)
  - unknown step_type (skip + advance)
  - lead with no phone (send step → skip_reason=no_phone + advance)
  - _evaluate_condition: all operators
  - _interpolate_template: double-brace + single-brace + unknown key
  - run_due_actions: send + wait + action + skip (no phone) + fake sender
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, call

import pytest

from app.services.automation_engine import (
    AdvanceResult,
    AutomationEngine,
    FakeWhatsAppSender,
    _evaluate_condition,
    _interpolate_template,
    run_due_actions,
)


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------

ORG_ID = str(uuid.uuid4())
EXEC_ID = str(uuid.uuid4())
FLOW_ID = str(uuid.uuid4())
LEAD_ID = str(uuid.uuid4())
EXEC_ID = str(uuid.uuid4())


def _flow(trigger_type: str = "lead_created", schedule_window: dict | None = None) -> dict:
    return {
        "id": FLOW_ID,
        "org_id": ORG_ID,
        "name": "Test Flow",
        "trigger_type": trigger_type,
        "trigger_config": {},
        "active": True,
        "schedule_window": schedule_window or {},
        "stop_rules": {"stop_on_reply": True},
    }


def _step(ord: int, step_type: str, config: dict | None = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "org_id": ORG_ID,
        "flow_id": FLOW_ID,
        "ord": ord,
        "step_type": step_type,
        "config": config or {},
    }


def _execution(current_step_ord: int = 0, status: str = "running", context: dict | None = None) -> dict:
    return {
        "id": EXEC_ID,
        "org_id": ORG_ID,
        "flow_id": FLOW_ID,
        "lead_id": LEAD_ID,
        "status": status,
        "current_step_ord": current_step_ord,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "context": context or {},
    }


def _lead(phone: str = "5511999990000", source: str = "Meta Ads", tags: list | None = None, **kwargs) -> dict:
    return {
        "id": LEAD_ID,
        "org_id": ORG_ID,
        "name": "Maria Teste",
        "email": "maria@teste.com",
        "phone": phone,
        "company": "Agência XYZ",
        "source": source,
        "temperature": "warm",
        "tags": tags or [],
        "custom_fields": {"servico_interesse": "Tráfego Pago"},
        **kwargs,
    }


engine = AutomationEngine()


# ---------------------------------------------------------------------------
# Empty flow
# ---------------------------------------------------------------------------

class TestEmptyFlow:
    def test_no_steps_returns_done(self):
        result = engine.advance(_flow(), [], _execution(), _lead())
        assert result.new_status == "done"
        assert result.pending_action is None


# ---------------------------------------------------------------------------
# end step
# ---------------------------------------------------------------------------

class TestEndStep:
    def test_end_step_marks_done(self):
        steps = [_step(0, "end")]
        result = engine.advance(_flow(), steps, _execution(0), _lead())
        assert result.new_status == "done"
        assert result.pending_action is None


# ---------------------------------------------------------------------------
# send_message
# ---------------------------------------------------------------------------

class TestSendMessageStep:
    def test_send_message_schedules_pending_action(self):
        steps = [_step(0, "send_message", {"template": "Olá {nome}! Interesse em {servico_interesse}."})]
        result = engine.advance(_flow(), steps, _execution(0), _lead())
        assert result.pending_action is not None
        assert result.pending_action["payload"]["step_type"] == "send_message"
        assert result.pending_action["payload"]["phone"] == "5511999990000"
        assert "Maria Teste" in result.pending_action["payload"]["message"]
        assert "Tráfego Pago" in result.pending_action["payload"]["message"]
        assert result.pending_action["status"] == "pending"

    def test_send_message_with_double_brace_template(self):
        steps = [_step(0, "send_message", {"template": "Olá {{nome}}! Serviço: {{servico_interesse}}"})]
        result = engine.advance(_flow(), steps, _execution(0), _lead())
        assert "Maria Teste" in result.pending_action["payload"]["message"]
        assert "Tráfego Pago" in result.pending_action["payload"]["message"]

    def test_send_message_unknown_var_is_empty_string(self):
        steps = [_step(0, "send_message", {"template": "Olá {nome}! Ref: {unknown_key}."})]
        result = engine.advance(_flow(), steps, _execution(0), _lead())
        msg = result.pending_action["payload"]["message"]
        assert "unknown_key" not in msg
        assert "Ref: ." in msg  # unknown_key → ""

    def test_send_message_no_phone_skips_with_reason(self):
        steps = [_step(0, "send_message", {"template": "Olá {nome}!"}), _step(1, "end")]
        result = engine.advance(_flow(), steps, _execution(0), _lead(phone=""))
        assert result.skip_reason == "no_phone"
        assert result.pending_action is None
        # Should advance to next step
        assert result.next_step_ord == 1

    def test_send_message_advances_to_next_step(self):
        steps = [
            _step(0, "send_message", {"template": "Hi"}),
            _step(1, "end"),
        ]
        result = engine.advance(_flow(), steps, _execution(0), _lead())
        assert result.next_step_ord == 1

    def test_send_message_last_step_status_is_running(self):
        """When there's a next step, status stays running."""
        steps = [
            _step(0, "send_message", {"template": "Hi"}),
            _step(1, "end"),
        ]
        result = engine.advance(_flow(), steps, _execution(0), _lead())
        assert result.new_status == "running"

    def test_send_whatsapp_media_behaves_same_as_send_message(self):
        steps = [_step(0, "send_whatsapp_media", {"template": "Veja o material sobre {servico_interesse}!"})]
        result = engine.advance(_flow(), steps, _execution(0), _lead())
        assert result.pending_action is not None
        assert result.pending_action["payload"]["step_type"] == "send_whatsapp_media"


# ---------------------------------------------------------------------------
# wait
# ---------------------------------------------------------------------------

class TestWaitStep:
    def test_wait_schedules_pending_action_with_duration(self):
        steps = [
            _step(0, "wait", {"duration_minutes": 30}),
            _step(1, "end"),
        ]
        result = engine.advance(_flow(), steps, _execution(0), _lead())
        assert result.pending_action is not None
        assert result.pending_action["payload"]["step_type"] == "wait"
        assert result.pending_action["payload"]["duration_minutes"] == 30
        assert result.next_step_ord == 1
        assert result.new_status == "running"

    def test_wait_next_action_at_is_future(self):
        steps = [_step(0, "wait", {"duration_minutes": 60})]
        now = datetime.now(timezone.utc)
        result = engine.advance(_flow(), steps, _execution(0), _lead())
        assert result.next_action_at is not None
        assert result.next_action_at > now

    def test_wait_zero_duration(self):
        steps = [_step(0, "wait", {"duration_minutes": 0})]
        result = engine.advance(_flow(), steps, _execution(0), _lead())
        assert result.pending_action is not None


# ---------------------------------------------------------------------------
# condition step
# ---------------------------------------------------------------------------

class TestConditionStep:
    def test_condition_equals_passes(self):
        steps = [
            _step(0, "condition", {
                "field": "source",
                "operator": "equals",
                "value": "Meta Ads",
                "on_true": "next",
                "on_false": "stop",
            }),
            _step(1, "end"),
        ]
        result = engine.advance(_flow(), steps, _execution(0), _lead(source="Meta Ads"))
        assert result.new_status == "running"
        assert result.next_step_ord == 1

    def test_condition_equals_fails_stops(self):
        """on_false=stop → canceled."""
        steps = [
            _step(0, "condition", {
                "field": "source",
                "operator": "equals",
                "value": "Meta Ads",
                "on_true": "next",
                "on_false": "stop",
            }),
        ]
        result = engine.advance(_flow(), steps, _execution(0), _lead(source="Google Ads"))
        assert result.new_status == "canceled"
        assert result.pending_action is None

    def test_condition_not_equals(self):
        steps = [
            _step(0, "condition", {
                "field": "source",
                "operator": "not_equals",
                "value": "Meta Ads",
                "on_true": "next",
                "on_false": "stop",
            }),
            _step(1, "end"),
        ]
        result = engine.advance(_flow(), steps, _execution(0), _lead(source="Google Ads"))
        assert result.next_step_ord == 1

    def test_condition_contains(self):
        steps = [
            _step(0, "condition", {
                "field": "source",
                "operator": "contains",
                "value": "Meta",
                "on_true": "next",
                "on_false": "stop",
            }),
            _step(1, "end"),
        ]
        result = engine.advance(_flow(), steps, _execution(0), _lead(source="Meta Ads"))
        assert result.new_status == "running"

    def test_condition_not_contains(self):
        steps = [
            _step(0, "condition", {
                "field": "source",
                "operator": "not_contains",
                "value": "Google",
                "on_true": "next",
                "on_false": "stop",
            }),
            _step(1, "end"),
        ]
        result = engine.advance(_flow(), steps, _execution(0), _lead(source="Meta Ads"))
        assert result.next_step_ord == 1

    def test_condition_exists_present(self):
        steps = [
            _step(0, "condition", {
                "field": "email",
                "operator": "exists",
                "on_true": "next",
                "on_false": "stop",
            }),
            _step(1, "end"),
        ]
        result = engine.advance(_flow(), steps, _execution(0), _lead())
        assert result.next_step_ord == 1

    def test_condition_not_exists_absent(self):
        steps = [
            _step(0, "condition", {
                "field": "email",
                "operator": "not_exists",
                "on_true": "next",
                "on_false": "stop",
            }),
            _step(1, "end"),
        ]
        lead = _lead()
        lead["email"] = None
        result = engine.advance(_flow(), steps, _execution(0), lead)
        assert result.next_step_ord == 1

    def test_condition_greater_than(self):
        steps = [
            _step(0, "condition", {
                "field": "qualification_score",
                "operator": "greater_than",
                "value": 4,
                "on_true": "next",
                "on_false": "stop",
            }),
            _step(1, "end"),
        ]
        lead = _lead()
        lead["qualification_score"] = 7
        result = engine.advance(_flow(), steps, _execution(0), lead)
        assert result.next_step_ord == 1

    def test_condition_less_than(self):
        steps = [
            _step(0, "condition", {
                "field": "qualification_score",
                "operator": "less_than",
                "value": 3,
                "on_true": "next",
                "on_false": "stop",
            }),
            _step(1, "end"),
        ]
        lead = _lead()
        lead["qualification_score"] = 1
        result = engine.advance(_flow(), steps, _execution(0), lead)
        assert result.next_step_ord == 1

    def test_condition_is_true_from_context(self):
        """Condition reads execution context (e.g. lead_replied)."""
        steps = [
            _step(0, "condition", {
                "field": "lead_replied",
                "operator": "is_true",
                "on_true": "next",
                "on_false": "stop",
            }),
            _step(1, "end"),
        ]
        exec_with_ctx = _execution(0, context={"lead_replied": True})
        result = engine.advance(_flow(), steps, exec_with_ctx, _lead())
        assert result.next_step_ord == 1

    def test_condition_is_false_from_context(self):
        steps = [
            _step(0, "condition", {
                "field": "lead_replied",
                "operator": "is_false",
                "on_true": "next",
                "on_false": "stop",
            }),
            _step(1, "end"),
        ]
        exec_with_ctx = _execution(0, context={"lead_replied": False})
        result = engine.advance(_flow(), steps, exec_with_ctx, _lead())
        assert result.next_step_ord == 1

    def test_condition_no_reply_stop(self):
        """The canonical 'stop chasing on reply' rule: on_true=stop."""
        steps = [
            _step(0, "condition", {
                "field": "lead_replied",
                "operator": "is_true",
                "on_true": "stop",
                "on_false": "next",
            }),
            _step(1, "send_message", {"template": "Follow-up!"}),
        ]
        # lead_replied is True → on_true=stop → canceled
        exec_with_reply = _execution(0, context={"lead_replied": True})
        result = engine.advance(_flow(), steps, exec_with_reply, _lead())
        assert result.new_status == "canceled"

    def test_condition_unknown_operator_returns_false(self):
        """Unknown operator → warning + condition evaluates False."""
        steps = [
            _step(0, "condition", {
                "field": "source",
                "operator": "unknown_op",
                "value": "Meta Ads",
                "on_true": "next",
                "on_false": "stop",
            }),
        ]
        result = engine.advance(_flow(), steps, _execution(0), _lead())
        # False → on_false=stop → canceled
        assert result.new_status == "canceled"

    def test_condition_on_false_jump_to_ord(self):
        """on_false can be a numeric step ord to jump to."""
        steps = [
            _step(0, "condition", {
                "field": "source",
                "operator": "equals",
                "value": "Meta Ads",
                "on_true": "next",
                "on_false": 2,  # jump to ord 2
            }),
            _step(1, "send_message", {"template": "branch 1"}),
            _step(2, "end"),
        ]
        result = engine.advance(_flow(), steps, _execution(0), _lead(source="Google"))
        assert result.next_step_ord == 2


# ---------------------------------------------------------------------------
# branch step
# ---------------------------------------------------------------------------

class TestBranchStep:
    def test_branch_on_true_jumps_to_correct_ord(self):
        steps = [
            _step(0, "branch", {
                "field": "lead_replied",
                "operator": "is_true",
                "on_true_step_ord": 2,
                "on_false_step_ord": 1,
            }),
            _step(1, "send_message", {"template": "No reply yet"}),
            _step(2, "end"),
        ]
        exec_replied = _execution(0, context={"lead_replied": True})
        result = engine.advance(_flow(), steps, exec_replied, _lead())
        assert result.next_step_ord == 2

    def test_branch_on_false_jumps_to_correct_ord(self):
        steps = [
            _step(0, "branch", {
                "field": "lead_replied",
                "operator": "is_true",
                "on_true_step_ord": 2,
                "on_false_step_ord": 1,
            }),
            _step(1, "send_message", {"template": "No reply follow-up"}),
            _step(2, "end"),
        ]
        exec_no_reply = _execution(0, context={"lead_replied": False})
        result = engine.advance(_flow(), steps, exec_no_reply, _lead())
        assert result.next_step_ord == 1

    def test_branch_invalid_target_ord_returns_done(self):
        """Branch to non-existent ord → done (safe fallback)."""
        steps = [
            _step(0, "branch", {
                "field": "lead_replied",
                "operator": "is_true",
                "on_true_step_ord": 99,  # doesn't exist
                "on_false_step_ord": 1,
            }),
            _step(1, "end"),
        ]
        exec_replied = _execution(0, context={"lead_replied": True})
        result = engine.advance(_flow(), steps, exec_replied, _lead())
        assert result.new_status == "done"


# ---------------------------------------------------------------------------
# action step
# ---------------------------------------------------------------------------

class TestActionStep:
    def test_action_step_schedules_pending_action(self):
        steps = [
            _step(0, "action", {
                "action_type": "create_task",
                "title": "Follow-up comercial",
            }),
            _step(1, "end"),
        ]
        result = engine.advance(_flow(), steps, _execution(0), _lead())
        assert result.pending_action is not None
        assert result.pending_action["payload"]["step_type"] == "action"
        assert result.pending_action["payload"]["action_type"] == "create_task"
        assert result.next_step_ord == 1

    def test_action_step_is_immediately_scheduled(self):
        """Actions execute immediately (scheduled_for ≈ now)."""
        steps = [_step(0, "action", {"action_type": "add_tag", "tag": "quente"})]
        now = datetime.now(timezone.utc)
        result = engine.advance(_flow(), steps, _execution(0), _lead())
        assert result.next_action_at is not None
        # scheduled_for is very close to now (within 5 seconds)
        delta = abs((result.next_action_at - now).total_seconds())
        assert delta < 5


# ---------------------------------------------------------------------------
# unknown step type
# ---------------------------------------------------------------------------

class TestUnknownStepType:
    def test_unknown_step_type_skips_and_advances(self):
        steps = [
            _step(0, "some_future_step_type", {}),
            _step(1, "end"),
        ]
        result = engine.advance(_flow(), steps, _execution(0), _lead())
        assert result.skip_reason is not None
        assert "unknown_step_type" in result.skip_reason
        assert result.next_step_ord == 1


# ---------------------------------------------------------------------------
# End-of-flow edge cases
# ---------------------------------------------------------------------------

class TestEndOfFlow:
    def test_past_last_step_ord_returns_done(self):
        """Execution's current_step_ord has no matching step → done."""
        steps = [_step(0, "end")]
        exec_past = _execution(current_step_ord=5)  # no step at ord 5
        result = engine.advance(_flow(), steps, exec_past, _lead())
        assert result.new_status == "done"

    def test_single_send_then_end_of_steps_marks_done(self):
        """After a send step with no further steps, status = done (next_ord = None)."""
        steps = [_step(0, "send_message", {"template": "Last message"})]
        result = engine.advance(_flow(), steps, _execution(0), _lead())
        # next_step_ord = None → new_status = 'done'
        assert result.next_step_ord is None
        assert result.new_status == "done"


# ---------------------------------------------------------------------------
# Multi-step sequence integration
# ---------------------------------------------------------------------------

class TestMultiStepSequence:
    def test_three_step_sequence(self):
        """Simulates advancing through a 3-step flow manually."""
        steps = [
            _step(0, "condition", {
                "field": "source",
                "operator": "equals",
                "value": "Meta Ads",
                "on_true": "next",
                "on_false": "stop",
            }),
            _step(1, "send_message", {"template": "Olá {nome}!"}),
            _step(2, "end"),
        ]
        flow = _flow()

        # Step 0: condition passes (source=Meta Ads)
        exec0 = _execution(0)
        r0 = engine.advance(flow, steps, exec0, _lead(source="Meta Ads"))
        assert r0.new_status == "running"
        assert r0.next_step_ord == 1

        # Step 1: send_message
        exec1 = _execution(1)
        r1 = engine.advance(flow, steps, exec1, _lead(source="Meta Ads"))
        assert r1.pending_action is not None
        assert r1.next_step_ord == 2

        # Step 2: end
        exec2 = _execution(2)
        r2 = engine.advance(flow, steps, exec2, _lead(source="Meta Ads"))
        assert r2.new_status == "done"


# ---------------------------------------------------------------------------
# Template interpolation unit tests
# ---------------------------------------------------------------------------

class TestInterpolateTemplate:
    def test_double_brace_replaced(self):
        result = _interpolate_template("Olá {{nome}}!", _lead())
        assert result == "Olá Maria Teste!"

    def test_single_brace_replaced(self):
        result = _interpolate_template("Olá {nome}!", _lead())
        assert result == "Olá Maria Teste!"

    def test_double_brace_takes_precedence_over_single(self):
        """{{nome}} should not double-match."""
        result = _interpolate_template("{{nome}} e {nome}", _lead())
        assert result == "Maria Teste e Maria Teste"

    def test_unknown_key_is_empty(self):
        result = _interpolate_template("Ref: {unknown_key}.", _lead())
        assert result == "Ref: ."

    def test_email_interpolation(self):
        result = _interpolate_template("Email: {email}", _lead())
        assert result == "Email: maria@teste.com"

    def test_tags_joined(self):
        result = _interpolate_template("Tags: {tag}", _lead(tags=["vip", "hot"]))
        assert result == "Tags: vip, hot"

    def test_empty_template(self):
        assert _interpolate_template("", _lead()) == ""

    def test_no_variables_unchanged(self):
        assert _interpolate_template("Hello, world!", _lead()) == "Hello, world!"


# ---------------------------------------------------------------------------
# _evaluate_condition unit tests (operator coverage)
# ---------------------------------------------------------------------------

class TestEvaluateCondition:
    def _cfg(self, **kwargs) -> dict:
        return {"field": "source", **kwargs}

    def _lead_for_eval(self, source: str = "Meta Ads") -> dict:
        return {"source": source, "custom_fields": {}}

    def test_equals_true(self):
        assert _evaluate_condition(
            self._cfg(operator="equals", value="Meta Ads"),
            self._lead_for_eval("Meta Ads"), {},
        ) is True

    def test_equals_false(self):
        assert _evaluate_condition(
            self._cfg(operator="equals", value="Meta Ads"),
            self._lead_for_eval("Google"), {},
        ) is False

    def test_not_equals(self):
        assert _evaluate_condition(
            self._cfg(operator="not_equals", value="Meta Ads"),
            self._lead_for_eval("Google"), {},
        ) is True

    def test_contains(self):
        assert _evaluate_condition(
            self._cfg(operator="contains", value="Meta"),
            self._lead_for_eval("Meta Ads"), {},
        ) is True

    def test_not_contains(self):
        assert _evaluate_condition(
            self._cfg(operator="not_contains", value="Google"),
            self._lead_for_eval("Meta Ads"), {},
        ) is True

    def test_exists_true(self):
        assert _evaluate_condition(
            {"field": "email", "operator": "exists"},
            {"email": "a@b.com", "custom_fields": {}}, {},
        ) is True

    def test_exists_false_none(self):
        assert _evaluate_condition(
            {"field": "email", "operator": "exists"},
            {"email": None, "custom_fields": {}}, {},
        ) is False

    def test_not_exists_true(self):
        assert _evaluate_condition(
            {"field": "email", "operator": "not_exists"},
            {"email": None, "custom_fields": {}}, {},
        ) is True

    def test_greater_than_true(self):
        assert _evaluate_condition(
            {"field": "score", "operator": "greater_than", "value": 4},
            {"score": 7, "custom_fields": {}}, {},
        ) is True

    def test_less_than_true(self):
        assert _evaluate_condition(
            {"field": "score", "operator": "less_than", "value": 3},
            {"score": 1, "custom_fields": {}}, {},
        ) is True

    def test_is_true(self):
        assert _evaluate_condition(
            {"field": "replied", "operator": "is_true"},
            {}, {"replied": True},
        ) is True

    def test_is_false(self):
        assert _evaluate_condition(
            {"field": "replied", "operator": "is_false"},
            {}, {"replied": False},
        ) is True

    def test_context_takes_precedence_over_lead(self):
        assert _evaluate_condition(
            {"field": "source", "operator": "equals", "value": "context_val"},
            {"source": "lead_val", "custom_fields": {}},
            {"source": "context_val"},
        ) is True

    def test_unknown_operator_returns_false(self):
        assert _evaluate_condition(
            self._cfg(operator="future_op", value="x"),
            self._lead_for_eval(), {},
        ) is False


# ---------------------------------------------------------------------------
# run_due_actions — FakeWhatsAppSender integration
# ---------------------------------------------------------------------------

class TestRunDueActions:
    """run_due_actions over the stateful MockSupabaseClient + injected sender."""

    def _db(self, actions: list[dict], executions: list[dict] | None = None):
        from noctusai_lib.testing import MockSupabaseClient

        db = MockSupabaseClient(schema="orbity")
        db.set_table_data("automation_pending_actions", actions)
        db.set_table_data(
            "automation_executions",
            executions if executions is not None else [
                {"id": EXEC_ID, "org_id": ORG_ID, "status": "running"}
            ],
        )
        return db

    def _pending(self, step_type: str, phone: str = "5511999990000", **payload) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "org_id": ORG_ID,
            "execution_id": EXEC_ID,
            "status": "pending",
            "scheduled_for": "2026-01-01T00:00:00+00:00",
            "payload": {
                "step_type": step_type,
                "phone": phone,
                "message": "Hello!",
                "action_type": "add_tag",
                **payload,
            },
        }

    @staticmethod
    def _row(db, table: str, row_id: str) -> dict:
        return next(r for r in db.table(table).select("*").execute().data if r["id"] == row_id)

    def test_no_due_actions_returns_zeros(self):
        counts = run_due_actions(self._db([]), ORG_ID, FakeWhatsAppSender())
        assert counts == {"processed": 0, "sent": 0, "skipped": 0, "failed": 0}

    def test_send_message_sends_marks_sent_and_advances(self):
        row = self._pending("send_message")
        db = self._db([row])
        sender = FakeWhatsAppSender()
        advanced: list[str] = []
        counts = run_due_actions(db, ORG_ID, sender, advance=advanced.append)
        assert counts == {"processed": 1, "sent": 1, "skipped": 0, "failed": 0}
        assert sender.sent[0]["phone"] == "5511999990000"
        stored = self._row(db, "automation_pending_actions", row["id"])
        assert stored["status"] == "sent" and stored["processed_at"]
        assert advanced == [EXEC_ID]

    def test_send_failure_is_failed_never_sent_and_stops_the_flow(self):
        from app.services.whatsapp_sender import WhatsAppSendError

        class Boom:
            def send(self, phone, message, org_id):
                raise WhatsAppSendError("Falha ao enviar pelo WhatsApp: HTTP 500")

        row = self._pending("send_message")
        db = self._db([row])
        advanced: list[str] = []
        counts = run_due_actions(db, ORG_ID, Boom(), advance=advanced.append)
        assert counts["failed"] == 1 and counts["sent"] == 0
        stored = self._row(db, "automation_pending_actions", row["id"])
        assert stored["status"] == "failed"
        assert stored["error_detail"] == "Falha ao enviar pelo WhatsApp: HTTP 500"
        ex = self._row(db, "automation_executions", EXEC_ID)
        assert ex["status"] == "failed" and "WhatsApp" in ex["error_detail"]
        assert advanced == []

    def test_unexpected_exception_gets_generic_message_not_the_traceback(self):
        class Boom:
            def send(self, phone, message, org_id):
                raise ValueError("secret-token=abc")

        row = self._pending("send_message")
        db = self._db([row])
        run_due_actions(db, ORG_ID, Boom())
        detail = self._row(db, "automation_pending_actions", row["id"])["error_detail"]
        assert "secret" not in detail and detail.startswith("Falha inesperada")

    def test_not_connected_org_fails_explicitly(self):
        from app.services.whatsapp_sender import RealWhatsAppSender
        from types import SimpleNamespace

        row = self._pending("send_message")
        db = self._db([row])
        stub = SimpleNamespace(
            encryption_key="", waha_base_url="", waha_api_key="", waha_session="default",
            waha_external_base_url="", whatsapp_allow_fake=False,
        )
        counts = run_due_actions(db, ORG_ID, RealWhatsAppSender(lambda: db, stub))
        assert counts["failed"] == 1 and counts["sent"] == 0
        assert "WhatsApp não conectado" in self._row(
            db, "automation_pending_actions", row["id"]
        )["error_detail"]

    def test_second_drain_does_not_resend_claimed_row(self):
        """The claim is a compare-and-set: a row already processed/claimed is
        invisible to the next drain, so concurrent drains never double-send."""
        row = self._pending("send_message")
        db = self._db([row])
        sender = FakeWhatsAppSender()
        run_due_actions(db, ORG_ID, sender)
        run_due_actions(db, ORG_ID, sender)
        assert len(sender.sent) == 1

    def test_lost_claim_race_skips_without_sending(self):
        """Row listed as pending but flipped to 'processing' by a peer before our
        CAS: our update matches nothing, so we must not send."""
        from app.services import automation_engine as eng

        row = self._pending("send_message")
        db = self._db([row])
        sender = FakeWhatsAppSender()
        real_claim = eng._claim
        # Peer wins the race: flip the row between our SELECT and our claim.
        db.table("automation_pending_actions").update({"status": "processing"}).eq(
            "id", row["id"]
        ).execute()
        assert real_claim(db, ORG_ID, row["id"]) is False
        assert sender.sent == []

    def test_wait_marked_sent_no_send_and_advances(self):
        row = self._pending("wait")
        db = self._db([row])
        sender = FakeWhatsAppSender()
        advanced: list[str] = []
        counts = run_due_actions(db, ORG_ID, sender, advance=advanced.append)
        assert counts["sent"] == 1 and sender.sent == []
        assert advanced == [EXEC_ID]

    def test_action_runs_via_run_action(self):
        row = self._pending("action")
        db = self._db([row])
        ran: list[dict] = []
        counts = run_due_actions(db, ORG_ID, FakeWhatsAppSender(), run_action=ran.append)
        assert counts["sent"] == 1
        assert ran[0]["action_type"] == "add_tag"

    def test_action_error_fails_action_and_execution(self):
        from app.services.automation_engine import ActionError

        def boom(payload):
            raise ActionError("Tipo de ação não suportado: x.")

        row = self._pending("action")
        db = self._db([row])
        counts = run_due_actions(db, ORG_ID, FakeWhatsAppSender(), run_action=boom)
        assert counts["failed"] == 1
        assert self._row(db, "automation_pending_actions", row["id"])["error_detail"] == (
            "Tipo de ação não suportado: x."
        )
        assert self._row(db, "automation_executions", EXEC_ID)["status"] == "failed"

    def test_action_without_executor_fails_explicitly_never_acked(self):
        row = self._pending("action")
        db = self._db([row])
        counts = run_due_actions(db, ORG_ID, FakeWhatsAppSender())
        assert counts["failed"] == 1 and counts["sent"] == 0

    def test_media_step_with_media_url_fails_explicitly(self):
        row = self._pending("send_whatsapp_media", media_url="https://x/y.png")
        db = self._db([row])
        sender = FakeWhatsAppSender()
        counts = run_due_actions(db, ORG_ID, sender)
        assert counts["failed"] == 1 and sender.sent == []
        assert "mídia" in self._row(db, "automation_pending_actions", row["id"])["error_detail"]

    def test_send_no_phone_skips(self):
        row = self._pending("send_message", phone="")
        db = self._db([row])
        sender = FakeWhatsAppSender()
        counts = run_due_actions(db, ORG_ID, sender)
        assert counts["skipped"] == 1 and sender.sent == []
        assert self._row(db, "automation_pending_actions", row["id"])["status"] == "skipped"

    def test_unknown_step_type_skips(self):
        row = {**self._pending("x"), "payload": {"step_type": "unknown_future_type"}}
        counts = run_due_actions(self._db([row]), ORG_ID, FakeWhatsAppSender())
        assert counts["skipped"] == 1

    def test_canceled_execution_skips_without_sending(self):
        row = self._pending("send_message")
        db = self._db([row], [{"id": EXEC_ID, "org_id": ORG_ID, "status": "canceled"}])
        sender = FakeWhatsAppSender()
        advanced: list[str] = []
        counts = run_due_actions(db, ORG_ID, sender, advance=advanced.append)
        assert counts["skipped"] == 1 and sender.sent == [] and advanced == []

    def test_future_actions_are_not_due(self):
        row = {**self._pending("send_message"), "scheduled_for": "2999-01-01T00:00:00+00:00"}
        sender = FakeWhatsAppSender()
        counts = run_due_actions(self._db([row]), ORG_ID, sender)
        assert counts["processed"] == 0 and sender.sent == []

    def test_stale_processing_claim_is_failed_not_resent(self):
        row = {
            **self._pending("send_message"),
            "status": "processing",
            "claimed_at": "2020-01-01T00:00:00+00:00",
        }
        db = self._db([row])
        sender = FakeWhatsAppSender()
        run_due_actions(db, ORG_ID, sender)
        assert sender.sent == []
        stored = self._row(db, "automation_pending_actions", row["id"])
        assert stored["status"] == "failed" and "duplicidade" in stored["error_detail"]
        assert self._row(db, "automation_executions", EXEC_ID)["status"] == "failed"

    def test_advance_failure_fails_the_execution(self):
        row = self._pending("wait")
        db = self._db([row])

        def bad(execution_id):
            raise RuntimeError("db down")

        run_due_actions(db, ORG_ID, FakeWhatsAppSender(), advance=bad)
        assert self._row(db, "automation_executions", EXEC_ID)["status"] == "failed"

    def test_orgs_with_due_work_lists_pending_and_stale_orgs(self):
        from app.services.automation_engine import orgs_with_due_work

        rows = [
            {**self._pending("wait"), "org_id": "org-a"},
            {**self._pending("wait"), "org_id": "org-b", "scheduled_for": "2999-01-01T00:00:00+00:00"},
            {**self._pending("wait"), "org_id": "org-c", "status": "processing",
             "claimed_at": "2020-01-01T00:00:00+00:00"},
        ]
        assert sorted(orgs_with_due_work(self._db(rows))) == ["org-a", "org-c"]


# ---------------------------------------------------------------------------
# FakeWhatsAppSender
# ---------------------------------------------------------------------------

class TestFakeWhatsAppSender:
    def test_records_calls(self):
        sender = FakeWhatsAppSender()
        sender.send(phone="5511000000000", message="Hi!", org_id=ORG_ID)
        assert len(sender.sent) == 1
        assert sender.sent[0] == {
            "phone": "5511000000000",
            "message": "Hi!",
            "org_id": ORG_ID,
        }

    def test_multiple_calls_accumulated(self):
        sender = FakeWhatsAppSender()
        for i in range(5):
            sender.send(phone=f"551199990000{i}", message=f"Msg {i}", org_id=ORG_ID)
        assert len(sender.sent) == 5
