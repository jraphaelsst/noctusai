"""
Tests for Jobs router — /api/jobs
Covers job submission, status check, and listing.
"""
import pytest


class TestSubmitJob:
    def test_submit_valid(self, client):
        resp = client.post("/api/jobs/submit", json={
            "name": "gerar_parcelas",
            "params": {"contrato_id": "c1"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "id" in data["data"]

    def test_submit_empty_name(self, client):
        resp = client.post("/api/jobs/submit", json={
            "name": "",
            "params": {},
        })
        assert resp.status_code == 422


class TestGetJob:
    def test_job_not_found(self, client):
        resp = client.get("/api/jobs/nonexistent")
        assert resp.status_code == 404


class TestListJobs:
    def test_list_empty(self, client):
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
