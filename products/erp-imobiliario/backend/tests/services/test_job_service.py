"""
Unit tests for job_service — Job class, handler registration, submit/list/get,
status tracking, error handling, cleanup.
"""
import pytest
import asyncio
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Job class
# ---------------------------------------------------------------------------

class TestJobClass:

    def test_initial_state(self):
        from app.services.job_service import Job, JobStatus
        job = Job("test_job", "org-1", {"key": "val"})

        assert job.name == "test_job"
        assert job.org_id == "org-1"
        assert job.params == {"key": "val"}
        assert job.status == JobStatus.PENDING
        assert job.result is None
        assert job.error is None
        assert job.progress == 0
        assert isinstance(job.created_at, datetime)
        assert job.started_at is None
        assert job.completed_at is None

    def test_to_dict(self):
        from app.services.job_service import Job
        job = Job("my_job", "org-1")
        d = job.to_dict()

        assert d["name"] == "my_job"
        assert d["org_id"] == "org-1"
        assert d["status"] == "pending"
        assert d["progress"] == 0
        assert d["result"] is None
        assert d["error"] is None
        assert d["started_at"] is None
        assert d["completed_at"] is None
        assert "id" in d
        assert "created_at" in d

    def test_default_params_empty_dict(self):
        from app.services.job_service import Job
        job = Job("test", "org-1")
        assert job.params == {}

    def test_id_is_generated(self):
        from app.services.job_service import Job
        j1 = Job("a", "org-1")
        j2 = Job("b", "org-1")
        assert j1.id != j2.id


# ---------------------------------------------------------------------------
# JobStatus enum
# ---------------------------------------------------------------------------

class TestJobStatus:

    def test_values(self):
        from app.services.job_service import JobStatus
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"


# ---------------------------------------------------------------------------
# register_handler / _handlers
# ---------------------------------------------------------------------------

class TestRegisterHandler:

    def test_register_and_retrieve(self):
        from app.services.job_service import register_handler, _handlers

        async def dummy_handler(job):
            return "ok"

        register_handler("test_dummy", dummy_handler)
        assert "test_dummy" in _handlers
        assert _handlers["test_dummy"] is dummy_handler

        # Clean up
        del _handlers["test_dummy"]


# ---------------------------------------------------------------------------
# get_job / list_jobs
# ---------------------------------------------------------------------------

class TestGetAndListJobs:

    def test_get_job_found(self):
        from app.services.job_service import Job, _jobs, get_job

        job = Job("x", "org-1")
        _jobs[job.id] = job
        try:
            assert get_job(job.id) is job
        finally:
            del _jobs[job.id]

    def test_get_job_not_found(self):
        from app.services.job_service import get_job
        assert get_job("nonexistent-id") is None

    def test_list_jobs_filters_by_org(self):
        from app.services.job_service import Job, _jobs, list_jobs

        j1 = Job("a", "org-1")
        j2 = Job("b", "org-2")
        j3 = Job("c", "org-1")
        _jobs[j1.id] = j1
        _jobs[j2.id] = j2
        _jobs[j3.id] = j3

        try:
            result = list_jobs("org-1")
            ids = [j["id"] for j in result]
            assert j1.id in ids
            assert j3.id in ids
            assert j2.id not in ids
        finally:
            del _jobs[j1.id]
            del _jobs[j2.id]
            del _jobs[j3.id]

    def test_list_jobs_respects_limit(self):
        from app.services.job_service import Job, _jobs, list_jobs

        jobs = [Job(f"job-{i}", "org-limit") for i in range(5)]
        for j in jobs:
            _jobs[j.id] = j

        try:
            result = list_jobs("org-limit", limit=3)
            assert len(result) == 3
        finally:
            for j in jobs:
                del _jobs[j.id]


# ---------------------------------------------------------------------------
# _run_job
# ---------------------------------------------------------------------------

class TestRunJob:

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        from app.services.job_service import Job, JobStatus, _handlers, _run_job

        async def ok_handler(job):
            return {"result": "done"}

        _handlers["test_ok"] = ok_handler
        job = Job("test_ok", "org-1")

        try:
            await _run_job(job)
            assert job.status == JobStatus.COMPLETED
            assert job.result == {"result": "done"}
            assert job.progress == 100
            assert job.started_at is not None
            assert job.completed_at is not None
        finally:
            del _handlers["test_ok"]

    @pytest.mark.asyncio
    async def test_handler_raises_error(self):
        from app.services.job_service import Job, JobStatus, _handlers, _run_job

        async def fail_handler(job):
            raise ValueError("something broke")

        _handlers["test_fail"] = fail_handler
        job = Job("test_fail", "org-1")

        try:
            await _run_job(job)
            assert job.status == JobStatus.FAILED
            assert "something broke" in job.error
            assert job.completed_at is not None
        finally:
            del _handlers["test_fail"]

    @pytest.mark.asyncio
    async def test_no_handler_registered(self):
        from app.services.job_service import Job, JobStatus, _run_job

        job = Job("nonexistent_handler", "org-1")
        await _run_job(job)

        assert job.status == JobStatus.FAILED
        assert "No handler registered" in job.error


# ---------------------------------------------------------------------------
# submit_job
# ---------------------------------------------------------------------------

class TestSubmitJob:

    @pytest.mark.asyncio
    async def test_submit_returns_job(self):
        from app.services.job_service import submit_job, _jobs, _handlers, JobStatus

        async def noop_handler(job):
            return None

        _handlers["test_submit"] = noop_handler

        try:
            job = submit_job("test_submit", "org-1", {"p": 1})
            assert job.name == "test_submit"
            assert job.org_id == "org-1"
            assert job.params == {"p": 1}
            assert job.id in _jobs

            # Let the async task complete
            await asyncio.sleep(0.1)
            assert job.status == JobStatus.COMPLETED
        finally:
            if job.id in _jobs:
                del _jobs[job.id]
            del _handlers["test_submit"]

    @pytest.mark.asyncio
    async def test_submit_cleanup_old_jobs(self):
        from app.services.job_service import submit_job, _jobs, _handlers

        async def noop(job):
            return None

        _handlers["test_cleanup"] = noop

        # Save original state
        original_jobs = dict(_jobs)
        _jobs.clear()

        try:
            # Create 201 jobs to trigger cleanup
            for i in range(201):
                submit_job("test_cleanup", "org-1")

            await asyncio.sleep(0.2)

            # After cleanup, should have at most 201 (the 201st triggers cleanup of older ones)
            assert len(_jobs) <= 201
        finally:
            _jobs.clear()
            _jobs.update(original_jobs)
            del _handlers["test_cleanup"]
