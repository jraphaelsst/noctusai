"""Segundo Cérebro — stale sweeps (scheduler job + read-time refresh)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import anyio

from app.modules.media_creation import cerebro_scheduler
from app.modules.media_creation.services import cerebro_service
from app.modules.media_creation.services.cerebro_service import sweep_stale

ORG = "test-org-123"
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


def _ago(minutes: int) -> str:
    return (NOW - timedelta(minutes=minutes)).isoformat()


def _seed(client):
    sb = client.mock_supabase
    marca = str(uuid.uuid4())
    sb.from_("marcas").insert({"id": marca, "org_id": ORG, "name": "M"}).execute()

    def brain(started, org=ORG, status="processing"):
        bid = str(uuid.uuid4())
        sb.from_("cs_brains").insert({
            "id": bid, "org_id": org, "marca_id": marca, "kind": "custom", "name": bid[:8],
            "content": "", "content_version": 0, "synthesis_status": status,
            "synthesis_started_at": started,
        }).execute()
        return bid

    def answer(bid, requested, status="pending"):
        sb.from_("cs_brain_answers").insert({
            "id": str(uuid.uuid4()), "org_id": ORG, "brain_id": bid,
            "question_id": f"q.{uuid.uuid4().hex[:4]}", "text": "t", "review_status": status,
            "review_requested_at": requested,
        }).execute()

    def imp(created, status="processing", org=ORG, bid=None):
        iid = str(uuid.uuid4())
        sb.from_("cs_brain_imports").insert({
            "id": iid, "org_id": org, "brain_id": bid or str(uuid.uuid4()), "kind": "file",
            "filename": "a.pdf", "status": status, "created_at": created,
        }).execute()
        return iid

    return sb, brain, answer, imp


def _by_id(sb, table):
    return {r["id"]: r for r in sb.from_(table).select("*").execute().data}


class TestSweepStale:
    def test_moves_only_stale_rows_to_error(self, client):
        sb, brain, answer, imp = _seed(client)
        old, fresh, idle = brain(_ago(11)), brain(_ago(2)), brain(_ago(30), status="idle")
        b = brain(_ago(1))
        answer(b, _ago(11)); answer(b, _ago(3)); answer(b, _ago(60), status="done")
        i_old, i_fresh, i_done = imp(_ago(16)), imp(_ago(14)), imp(_ago(60), status="appended")

        moved = sweep_stale(sb, now=NOW)

        assert moved == {"brains": 1, "answers": 1, "imports": 1}
        brains = _by_id(sb, "cs_brains")
        assert brains[old]["synthesis_status"] == "error"
        assert brains[old]["synthesis_error"] == "Tempo esgotado ao gerar o cérebro"
        assert brains[fresh]["synthesis_status"] == "processing"
        assert brains[idle]["synthesis_status"] == "idle"
        reviews = sorted((a["review_status"], a.get("review_error")) for a in _by_id(sb, "cs_brain_answers").values())
        assert reviews == [("done", None), ("error", "Tempo esgotado ao revisar com IA"), ("pending", None)]
        imports = _by_id(sb, "cs_brain_imports")
        assert imports[i_old]["status"] == "error" and imports[i_fresh]["status"] == "processing"
        assert imports[i_done]["status"] == "appended"

    def test_org_scoped_sweep_leaves_other_orgs_alone(self, client):
        sb, brain, _, imp = _seed(client)
        mine, theirs = brain(_ago(30)), brain(_ago(30), org="other-org")
        imp(_ago(30), org="other-org")
        moved = sweep_stale(sb, org_id=ORG, now=NOW)
        assert moved["brains"] == 1 and moved["imports"] == 0
        brains = _by_id(sb, "cs_brains")
        assert brains[mine]["synthesis_status"] == "error"
        assert brains[theirs]["synthesis_status"] == "processing"

    def test_scheduler_job_sweeps_every_org_and_never_raises(self, client):
        sb, brain, _, _ = _seed(client)
        a, b = brain(_ago(30)), brain(_ago(30), org="other-org")
        anyio.run(lambda: cerebro_scheduler.sweep_stranded(client=lambda: sb))
        brains = _by_id(sb, "cs_brains")
        assert brains[a]["synthesis_status"] == brains[b]["synthesis_status"] == "error"

        def boom():
            raise RuntimeError("db down")

        anyio.run(lambda: cerebro_scheduler.sweep_stranded(client=boom))   # swallowed, logged
        anyio.run(lambda: cerebro_scheduler.sweep_stranded(client=lambda: None))

    def test_read_time_refresh_settles_the_callers_own_stranded_synthesis(self, client):
        sb, brain, _, _ = _seed(client)
        stale = brain(_ago(30))
        cerebro_service._last_refresh.clear()
        svc = cerebro_service.CerebroService(sb, ORG)
        row = svc.get_brain(stale)
        assert row["synthesis_status"] == "error"
        assert row["synthesis_error"] == "Tempo esgotado ao gerar o cérebro"

    def test_job_is_registered_once_with_the_seed_scheduler(self):
        from noctusai_lib.api import scheduler as seed_scheduler

        cerebro_scheduler.configure()
        cerebro_scheduler.configure()   # idempotent: re-registering replaces, never duplicates
        jobs = [j for j in seed_scheduler.scheduler.get_jobs() if j.id == cerebro_scheduler.JOB_ID]
        assert len(jobs) == 1
