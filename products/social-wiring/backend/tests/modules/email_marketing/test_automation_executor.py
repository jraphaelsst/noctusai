"""Automation step executor (P1b(b)): scheduler scan -> seed Worker -> one step per job.

The queue is the seed ``FakeJobRepository`` driven by the real seed ``Worker``; the DB is a small
in-memory PostgREST stand-in; the Resend boundary is ``SendService``'s ``http_client_factory`` seam.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from noctusai_lib.domain.jobs import FakeJobRepository, JobStatus, Worker

from app.config import settings
from app.modules.email_marketing.services import automation_executor as ex
from app.modules.email_marketing.services import send_service as ss

ORG, OTHER_ORG = "org-1", "org-2"
AUTO, CONTACT, TPL, LIST = "auto-1", "ct-1", "tpl-1", "list-1"


class _Q:
    def __init__(self, db, table):
        self.db, self.table, self.op, self.payload, self.conflict = db, table, "select", None, None
        self.filters, self._limit = [], None

    def select(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def eq(self, c, v):
        self.filters.append(lambda r: r.get(c) == v)
        return self

    def neq(self, c, v):
        self.filters.append(lambda r: r.get(c) != v)
        return self

    def lte(self, c, v):
        self.filters.append(lambda r: r.get(c) is not None and r[c] <= v)
        return self

    def is_(self, c, v):
        self.filters.append(lambda r: r.get(c) is None)
        return self

    def in_(self, c, vs):
        self.filters.append(lambda r: r.get(c) in vs)
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def upsert(self, payload, on_conflict=None):
        self.op, self.payload, self.conflict = "upsert", payload, on_conflict
        return self

    def execute(self):
        t = self.db.rows.setdefault(self.table, [])
        if self.op in ("insert", "upsert"):
            for row in ([self.payload] if isinstance(self.payload, dict) else self.payload):
                if self.op == "upsert":
                    keys = self.conflict.split(",")
                    if any(all(r.get(k) == row.get(k) for k in keys) for r in t):
                        continue
                t.append({"id": f"{self.table}-{len(t) + 1}", **row})
            return SimpleNamespace(data=[dict(r) for r in t], count=len(t))
        rows = [r for r in t if all(f(r) for f in self.filters)]
        if self.op == "update":
            for r in rows:
                r.update(self.payload)
        if self._limit:
            rows = rows[: self._limit]
        return SimpleNamespace(data=[dict(r) for r in rows], count=len(rows))


class FakeDb:
    def __init__(self):
        iso = datetime.now(timezone.utc).isoformat()
        self.rows = {
            "automations": [{"id": AUTO, "org_id": ORG, "status": "ativa"}],
            "automation_steps": [],
            "automation_enrollments": [
                {"id": "en-1", "automation_id": AUTO, "contact_id": CONTACT, "current_step_id": None,
                 "status": "active", "next_action_at": iso, "completed_at": None}
            ],
            "contacts": [{"id": CONTACT, "org_id": ORG, "email": "ana@example.com", "nome": "Ana",
                          "status": "active", "tags": []}],
            "templates": [{"id": TPL, "org_id": ORG, "assunto": "Oi {{nome}}", "corpo_html": "<p>Oi {{nome}}</p>"}],
            "contact_lists": [{"id": LIST, "org_id": ORG}],
            "contact_list_members": [], "send_logs": [],
        }

    def table(self, name):
        return _Q(self, name)

    # helpers
    def steps(self, *specs):
        """specs: (tipo, config) in posicao order -> step ids; enrollment starts at the first."""
        ids = []
        for i, (tipo, config) in enumerate(specs, 1):
            sid = f"st-{i}"
            self.rows["automation_steps"].append(
                {"id": sid, "automation_id": AUTO, "posicao": i, "tipo": tipo, "config": config})
            ids.append(sid)
        self.rows["automation_enrollments"][0]["current_step_id"] = ids[0]
        return ids

    @property
    def enrollment(self):
        return self.rows["automation_enrollments"][0]

    @property
    def contact(self):
        return self.rows["contacts"][0]


@pytest.fixture
def db():
    return FakeDb()


@pytest.fixture
def repo():
    return FakeJobRepository()


def drain(db, repo):
    """Scan -> enqueue -> run the real seed Worker until the queue is empty."""
    async def go():
        await ex.enqueue_due(db, repo)
        worker = Worker(repo, worker_id="t", handlers={ex.JOB_TYPE: ex.build_handler(db, repo)})
        while await worker.run_once():
            pass
    asyncio.run(go())


def jobs(repo):
    return list(repo._jobs.values())


def dead(repo):
    return [j for j in jobs(repo) if j.status == JobStatus.DEAD_LETTER]


class TestIdempotentEnqueue:
    def test_same_due_enrollment_twice_is_one_job(self, db, repo):
        db.steps(("add_tag", {"tag": "x"}))

        async def twice():
            await ex.enqueue_due(db, repo)
            await ex.enqueue_due(db, repo)

        asyncio.run(twice())
        assert len(jobs(repo)) == 1
        assert jobs(repo)[0].dedupe_key == "en-1:st-1"

    def test_never_scheduled_enrollment_is_due(self, db, repo):
        db.steps(("add_tag", {"tag": "x"}))
        db.enrollment["next_action_at"] = None
        assert len(ex.scan_due_enrollments(db)) == 1

    def test_future_inactive_and_non_ativa_are_not_enqueued(self, db):
        db.steps(("add_tag", {"tag": "x"}))
        db.enrollment["next_action_at"] = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        assert ex.scan_due_enrollments(db) == []
        db.enrollment["next_action_at"] = datetime.now(timezone.utc).isoformat()
        db.rows["automations"][0]["status"] = "pausada"
        assert ex.scan_due_enrollments(db) == []


class TestSteps:
    def test_send_email_queues_one_log_and_completes(self, db, repo):
        db.steps(("send_email", {"template_id": TPL}))
        drain(db, repo)
        (log,) = db.rows["send_logs"]
        assert (log["org_id"], log["contact_id"], log["email"], log["automation_id"],
                log["automation_step_id"], log["status"]) == (ORG, CONTACT, "ana@example.com", AUTO, "st-1", "queued")
        assert db.enrollment["status"] == "completed" and db.enrollment["completed_at"]

    def test_send_email_runs_into_the_next_step_immediately(self, db, repo):
        db.steps(("send_email", {"template_id": TPL}), ("add_tag", {"tag": "enviado"}))
        drain(db, repo)
        assert len(db.rows["send_logs"]) == 1
        assert db.contact["tags"] == ["enviado"] and db.enrollment["status"] == "completed"

    def test_send_email_is_not_duplicated_on_a_replayed_step(self, db):
        db.steps(("send_email", {"template_id": TPL}), ("add_tag", {"tag": "t"}))
        ex.run_step(db, enrollment_id="en-1", step_id="st-1", org_id=ORG)
        db.enrollment["current_step_id"] = "st-1"  # crash-replay: advanced state lost
        ex.run_step(db, enrollment_id="en-1", step_id="st-1", org_id=ORG)
        assert len(db.rows["send_logs"]) == 1

    def test_wait_hours_schedules_next_action_and_ends_the_job(self, db, repo):
        db.steps(("wait", {"hours": 2}), ("add_tag", {"tag": "depois"}))
        before = datetime.now(timezone.utc)
        drain(db, repo)
        due = datetime.fromisoformat(db.enrollment["next_action_at"])
        assert before + timedelta(hours=2) <= due <= datetime.now(timezone.utc) + timedelta(hours=2)
        assert db.enrollment["current_step_id"] == "st-2" and db.enrollment["status"] == "active"
        assert db.contact["tags"] == [] and all(j.status == JobStatus.COMPLETED for j in jobs(repo))
        # once due, the scan re-enqueues the NEXT step
        db.enrollment["next_action_at"] = datetime.now(timezone.utc).isoformat()
        drain(db, repo)
        assert db.contact["tags"] == ["depois"] and db.enrollment["status"] == "completed"

    def test_wait_days(self, db, repo):
        db.steps(("wait", {"days": 1}), ("add_tag", {"tag": "x"}))
        drain(db, repo)
        due = datetime.fromisoformat(db.enrollment["next_action_at"])
        assert due - datetime.now(timezone.utc) > timedelta(hours=23)

    @pytest.mark.parametrize("field,value,setup,taken", [
        ("tag", "vip", lambda d: d.contact["tags"].append("vip"), True),
        ("tag", "vip", lambda d: None, False),
        ("status", "active", lambda d: None, True),
        ("status", "bounced", lambda d: None, False),
        ("opened_campaign", "camp-1", lambda d: d.rows["send_logs"].append(
            {"org_id": ORG, "contact_id": CONTACT, "campaign_id": "camp-1", "status": "opened"}), True),
        ("opened_campaign", "camp-1", lambda d: d.rows["send_logs"].append(
            {"org_id": ORG, "contact_id": CONTACT, "campaign_id": "camp-1", "status": "sent"}), False),
    ])
    def test_condition_both_branches(self, db, repo, field, value, setup, taken):
        db.steps(("condition", {"field": field, "op": "eq", "value": value, "then_posicao": 2, "else_posicao": 3}),
                 ("add_tag", {"tag": "then"}), ("add_tag", {"tag": "else"}))
        setup(db)
        drain(db, repo)
        assert ("then" in db.contact["tags"]) is taken

    def test_condition_not_has_inverts(self, db, repo):
        db.steps(("condition", {"field": "tag", "op": "not_has", "value": "vip", "then_posicao": 2, "else_posicao": 3}),
                 ("add_tag", {"tag": "then"}), ("add_tag", {"tag": "else"}))
        drain(db, repo)
        assert "then" in db.contact["tags"]

    def test_add_and_remove_tag(self, db, repo):
        db.contact["tags"] = ["velha"]
        db.steps(("add_tag", {"tag": "nova"}), ("remove_tag", {"tag": "velha"}))
        drain(db, repo)
        assert db.contact["tags"] == ["nova"]

    def test_move_to_list_upserts_once(self, db, repo):
        db.steps(("move_to_list", {"list_id": LIST}))
        drain(db, repo)
        db.enrollment.update(status="active", current_step_id="st-1")
        ex.run_step(db, enrollment_id="en-1", step_id="st-1", org_id=ORG)
        assert [(m["list_id"], m["contact_id"]) for m in db.rows["contact_list_members"]] == [(LIST, CONTACT)]

    def test_completion_after_last_step(self, db, repo):
        db.steps(("add_tag", {"tag": "fim"}))
        drain(db, repo)
        assert db.enrollment["status"] == "completed" and db.enrollment["completed_at"]
        assert all(j.status == JobStatus.COMPLETED for j in jobs(repo))


class TestExitsAndRefusals:
    @pytest.mark.parametrize("status", ["unsubscribed", "bounced", "complained"])
    def test_contact_no_longer_active_exits(self, db, repo, status):
        db.steps(("send_email", {"template_id": TPL}))
        db.contact["status"] = status
        drain(db, repo)
        assert db.enrollment["status"] == "exited" and db.rows["send_logs"] == []

    def test_non_ativa_automation_skips_without_running_a_step(self, db, repo):
        db.steps(("add_tag", {"tag": "x"}))
        db.rows["automations"][0]["status"] = "pausada"
        job = asyncio.run(ex.enqueue_enrollment(repo, {**db.enrollment, "org_id": ORG}))
        asyncio.run(Worker(repo, worker_id="t", handlers={ex.JOB_TYPE: ex.build_handler(db, repo)}).run_once())
        assert repo._jobs[job.id].status == JobStatus.COMPLETED
        assert db.contact["tags"] == [] and db.enrollment["status"] == "active"

    def test_foreign_org_job_cannot_touch_the_enrollment(self, db):
        db.steps(("add_tag", {"tag": "x"}))
        assert ex.run_step(db, enrollment_id="en-1", step_id="st-1", org_id=OTHER_ORG) is None
        assert db.contact["tags"] == [] and db.enrollment["status"] == "active"

    def test_webhook_refused_pauses_and_dead_letters(self, db, repo):
        db.steps(("webhook", {"url": "https://x.example"}), ("add_tag", {"tag": "nunca"}))
        drain(db, repo)
        assert db.enrollment["status"] == "paused" and db.contact["tags"] == []
        (job,) = dead(repo)
        assert "webhook" in job.last_error and "not supported" in job.last_error

    @pytest.mark.parametrize("tipo,config", [
        ("wait", {}), ("wait", {"hours": -1}), ("add_tag", {}), ("move_to_list", {}),
        ("move_to_list", {"list_id": "nope"}), ("send_email", {"template_id": "nope"}), ("send_email", {}),
        ("condition", {"field": "tag", "value": "v", "then_posicao": 9, "else_posicao": 9}),
        ("condition", {"field": "tag", "value": "v", "then_posicao": 1, "else_posicao": 2}),
        ("condition", {"field": "bogus", "value": "v", "then_posicao": 2, "else_posicao": 2}),
    ])
    def test_malformed_config_pauses_and_dead_letters(self, db, repo, tipo, config):
        db.steps((tipo, config), ("add_tag", {"tag": "nunca"}))
        drain(db, repo)
        assert db.enrollment["status"] == "paused" and db.contact["tags"] == []
        (job,) = dead(repo)
        assert "malformed" in job.last_error


class TestAutomationSendGoesThroughSendService:
    """The queued automation row resolves its template from the step config and passes the
    same guards as a campaign send."""

    class _Http:
        calls: list = []

        def __init__(self, *_a, **_k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None, timeout=None):
            self.calls.append(json)
            return SimpleNamespace(status_code=200, json=lambda: {"data": [{"id": "re_1"}]}, text="")

    def _queued(self, db, repo):
        db.steps(("send_email", {"template_id": TPL}))
        drain(db, repo)
        for log in db.rows["send_logs"]:
            log["contacts"] = {"nome": "Ana", "empresa": ""}

    def _process(self, db, **cfg):
        self._Http.calls = []
        svc = ss.SendService(db, settings.model_copy(update=cfg), http_client_factory=self._Http)
        return asyncio.run(svc.process_queued_sends())

    def test_dry_run_without_a_key_marks_the_row_failed(self, db, repo):
        self._queued(db, repo)
        assert self._process(db, resend_api_key="") == 0
        log = db.rows["send_logs"][0]
        assert log["status"] == "failed" and log["error_message"] == ss.DRY_RUN_REASON
        assert self._Http.calls == []

    def test_live_send_carries_the_unsubscribe_footer_and_headers(self, db, repo):
        self._queued(db, repo)
        assert self._process(db, resend_api_key="re_key", frontend_base_url="https://sw.example") == 1
        (email,) = self._Http.calls[0]
        link = email["headers"]["List-Unsubscribe"].strip("<>")
        assert email["subject"] == "Oi Ana" and link in email["html"] and "Descadastrar" in email["html"]
        assert email["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        assert db.rows["send_logs"][0]["status"] == "sent"

    def test_live_send_without_frontend_url_is_refused(self, db, repo):
        self._queued(db, repo)
        assert self._process(db, resend_api_key="re_key", frontend_base_url="") == 0
        assert db.rows["send_logs"][0]["error_message"] == ss.UNSUBSCRIBE_REFUSAL
        assert self._Http.calls == []

    def test_template_of_another_org_is_not_resolved(self, db, repo):
        self._queued(db, repo)
        db.rows["templates"][0]["org_id"] = OTHER_ORG
        assert self._process(db, resend_api_key="re_key", frontend_base_url="https://sw.example") == 0
        assert db.rows["send_logs"][0]["status"] == "failed" and self._Http.calls == []
