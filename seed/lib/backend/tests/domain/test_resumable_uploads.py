"""Resumable uploads: service (Fake store + Fake storage), router, migration."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.domain.resumable_uploads import (
    FakeUploadSessionStore, PartInvalid, PartsMissing, ResumableUploadService, UploadExpired, UploadNotFound,
    UploadPolicy, UploadRejected, create_resumable_upload_router, resumable_uploads_migration,
)
from noctusai_lib.integrations.storage import FakeStorageBackend

ORG, OTHER = "org-1", "org-2"
POL = UploadPolicy(max_bytes=1000, part_size=300, min_part_size=100, max_part_size=400, allowed_types=("video/*", "image/png"))
DATA = bytes(range(256)) * 3 + b"xyz"  # 771 bytes -> parts 300/300/171


class Clock:
    def __init__(self):
        self.t = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.t


def make():
    clock = Clock()
    store, storage = FakeUploadSessionStore(), FakeStorageBackend()
    svc = ResumableUploadService(store=store, storage=storage, bucket="b", prefix="up", policy=POL, now_fn=clock)
    return svc, store, storage, clock


def open_(svc, **kw):
    args = dict(org_id=ORG, user_id="u1", filename="../a b.mp4", content_type="video/mp4", size_bytes=len(DATA))
    args.update(kw)
    return svc.open(**args)


def test_open_validates_limits_and_type():
    svc, *_ = make()
    with pytest.raises(UploadRejected):
        open_(svc, size_bytes=1001)
    with pytest.raises(UploadRejected):
        open_(svc, size_bytes=0)
    with pytest.raises(UploadRejected):
        open_(svc, content_type="application/zip")
    s = open_(svc)
    assert (s.part_size, s.total_parts, s.filename) == (300, 3, "a_b.mp4")


def test_resume_reports_only_missing_and_assembles():
    async def scenario():
        svc, store, storage, _ = make()
        s = open_(svc)
        await svc.put_part(org_id=ORG, session_id=s.id, number=1, data=DATA[:300])
        await svc.put_part(org_id=ORG, session_id=s.id, number=3, data=DATA[600:])
        _, parts = await svc.status(org_id=ORG, session_id=s.id)
        assert [p.number for p in parts] == [1, 3]  # a "disconnect": the server says which it has
        with pytest.raises(PartsMissing) as ei:
            await svc.complete(org_id=ORG, session_id=s.id)
        assert ei.value.extra["missing"] == [2]
        await svc.put_part(org_id=ORG, session_id=s.id, number=2, data=DATA[300:600])
        done = await svc.complete(org_id=ORG, session_id=s.id)
        assert done.status == "completed" and done.object_key == f"up/{ORG}/{s.id}/a_b.mp4"
        assert (await svc.read(org_id=ORG, session_id=s.id)) == DATA
        assert await storage.list_keys(bucket="b", prefix=f"up/{ORG}/_parts/") == []  # parts cleaned
        got, data = await svc.consume(org_id=ORG, session_id=s.id)
        assert data == DATA and await storage.list_keys(bucket="b", prefix=f"up/{ORG}/{s.id}/") == []
        assert (await svc.complete(org_id=ORG, session_id=s.id)).status == "completed"  # idempotent
        assert [e["kind"] for e in store.events] == ["opened", "completed"]
    asyncio.run(scenario())


def test_part_validation_and_idempotent_put():
    async def scenario():
        svc, *_ = make()
        s = open_(svc)
        with pytest.raises(PartInvalid):
            await svc.put_part(org_id=ORG, session_id=s.id, number=4, data=b"x")
        with pytest.raises(PartInvalid):
            await svc.put_part(org_id=ORG, session_id=s.id, number=1, data=b"short")
        for _ in range(2):
            await svc.put_part(org_id=ORG, session_id=s.id, number=1, data=DATA[:300])
        _, parts = await svc.status(org_id=ORG, session_id=s.id)
        assert [p.number for p in parts] == [1]
    asyncio.run(scenario())


def test_org_isolation_is_404():
    async def scenario():
        svc, *_ = make()
        s = open_(svc)
        for call in (svc.status(org_id=OTHER, session_id=s.id), svc.abort(org_id=OTHER, session_id=s.id),
                     svc.put_part(org_id=OTHER, session_id=s.id, number=1, data=DATA[:300])):
            with pytest.raises(UploadNotFound):
                await call
    asyncio.run(scenario())


def test_client_key_resumes_the_same_session():
    svc, *_ = make()
    a, b = open_(svc, client_key="k"), open_(svc, client_key="k")
    assert a.id == b.id
    assert open_(svc, client_key="k", user_id="u2").id != a.id


def test_abort_and_expiry_record_events_and_drop_parts():
    async def scenario():
        svc, store, storage, clock = make()
        a, b = open_(svc), open_(svc)
        await svc.put_part(org_id=ORG, session_id=a.id, number=1, data=DATA[:300])
        await svc.abort(org_id=ORG, session_id=a.id)
        await svc.put_part(org_id=ORG, session_id=b.id, number=1, data=DATA[:300])
        clock.t += timedelta(seconds=POL.ttl_s + 1)
        with pytest.raises(UploadExpired):
            await svc.put_part(org_id=ORG, session_id=b.id, number=2, data=DATA[300:600])
        assert await svc.expire_stale() == 1
        assert await storage.list_keys(bucket="b", prefix="up/") == []
        assert [e["kind"] for e in store.events] == ["opened", "opened", "aborted", "expired"]
        assert await svc.expire_stale() == 0
    asyncio.run(scenario())


def _client(svc):
    app = FastAPI()
    ctx = SimpleNamespace(org_id=ORG, user_id="u1")

    async def auth():
        return ctx

    app.include_router(create_resumable_upload_router(get_auth_context=auth, get_service=lambda: svc))
    return TestClient(app)


def test_router_roundtrip_and_error_envelope():
    svc, *_ = make()
    c = _client(svc)
    r = c.post("/api/uploads", json={"filename": "v.mp4", "content_type": "video/mp4", "size_bytes": len(DATA)})
    assert r.status_code == 201
    sid = r.json()["id"]
    assert c.put(f"/api/uploads/{sid}/parts/1", content=DATA[:300]).status_code == 200
    miss = c.post(f"/api/uploads/{sid}/complete")
    assert miss.status_code == 409 and miss.json()["detail"]["missing"] == [2, 3]
    assert c.get(f"/api/uploads/{sid}").json()["parts"] == [1]
    c.put(f"/api/uploads/{sid}/parts/2", content=DATA[300:600])
    c.put(f"/api/uploads/{sid}/parts/3", content=DATA[600:])
    assert c.post(f"/api/uploads/{sid}/complete").json()["status"] == "completed"
    assert c.get("/api/uploads/nope").status_code == 404
    assert c.post("/api/uploads", json={"filename": "x", "size_bytes": 5000}).status_code == 422


def test_migration_is_service_only_with_events():
    sql = resumable_uploads_migration("erp")
    assert "erp.upload_sessions" in sql and "erp.upload_session_events" in sql
    assert "REVOKE ALL" in sql and "service_role_bypass" in sql and "GRANT ALL" in sql and "TO authenticated" not in sql
