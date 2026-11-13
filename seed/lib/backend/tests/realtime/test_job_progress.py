"""Job-progress channel: publish seam + per-job SSE endpoint
(`KB § PATTERNS/common/realtime-sse-bus.md` § Job progress)."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from noctusai_lib.realtime import (
    FakeRealtimeBus,
    JobProgress,
    RealtimeEvent,
    create_job_progress_router,
    job_progress_scope,
    get_shared_realtime_bus,
    publish_job_progress,
    reset_shared_realtime_buses,
)
from noctusai_lib.realtime.sse import sse_event_stream


def _frames_to_events(text: str) -> list[dict]:
    out = []
    for block in text.split("\n\n"):
        if not block.strip() or block.startswith(":"):
            continue
        fields = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        out.append({"event": fields.get("event"), "id": fields.get("id"), "data": json.loads(fields["data"])})
    return out


def _auth(request: Request):
    token = request.headers.get("authorization")
    if token not in ("Bearer ok-a", "Bearer ok-b"):
        raise HTTPException(status_code=401, detail="unauthenticated")
    return {"org_id": "org-a" if token == "Bearer ok-a" else "org-b"}


def _app(bus, snapshots: dict, **kw) -> FastAPI:
    def resolve_org(request: Request, auth) -> str:
        return auth["org_id"]

    async def snapshot(request: Request, auth, job_id: str):
        return snapshots.get((auth["org_id"], job_id))

    app = FastAPI()
    app.include_router(
        create_job_progress_router(
            bus, auth_dependency=_auth, org_resolver=resolve_org, snapshot_loader=snapshot, **kw
        ),
        prefix="/jobs",
    )
    return app


def test_payload_shape_and_terminal_flag() -> None:
    p = JobProgress(status="processando", progress=0.4, stage="estrutura 2 de 5", message="m")
    assert p.to_payload() == {
        "status": "processando", "progress": 0.4, "stage": "estrutura 2 de 5", "message": "m", "terminal": False,
    }
    assert JobProgress(status="completo", terminal=True).to_payload()["terminal"] is True


def test_progress_is_clamped_to_unit_interval() -> None:
    assert JobProgress(status="x", progress=7).progress == 1.0
    assert JobProgress(status="x", progress=-1).progress == 0.0
    assert JobProgress(status="x", progress=None).progress is None


def test_scope_is_org_and_job_specific() -> None:
    assert job_progress_scope("o1", "j1") != job_progress_scope("o2", "j1")
    assert job_progress_scope("o1", "j1") != job_progress_scope("o1", "j2")


@pytest.mark.asyncio
async def test_publish_puts_one_job_progress_event_on_the_scope() -> None:
    bus = FakeRealtimeBus()
    await publish_job_progress(bus, "o1", "j1", JobProgress(status="processando", progress=0.5))
    sub = bus.subscribe(job_progress_scope("o1", "j1"), last_event_id="0-0")
    ev = await asyncio.wait_for(sub.__anext__(), 1)
    assert ev.event == "job.progress" and ev.payload["progress"] == 0.5


@pytest.mark.asyncio
async def test_publish_failure_never_breaks_the_job_but_can_be_made_loud() -> None:
    class Boom:
        async def publish(self, *a, **k):
            raise RuntimeError("redis down")

    assert await publish_job_progress(Boom(), "o", "j", JobProgress(status="s")) is None
    with pytest.raises(RuntimeError):
        await publish_job_progress(Boom(), "o", "j", JobProgress(status="s"), best_effort=False)


@pytest.mark.asyncio
async def test_sse_event_stream_stops_after_the_terminal_event() -> None:
    bus = FakeRealtimeBus()
    await bus.publish("s", "job.progress", {"terminal": False})
    await bus.publish("s", "job.progress", {"terminal": True})
    await bus.publish("s", "job.progress", {"terminal": False})
    frames = [
        f
        async for f in sse_event_stream(
            bus, "s", last_event_id="0-0", heartbeat_seconds=100,
            stop_after=lambda e: bool(e.payload.get("terminal")),
        )
    ]
    assert len(frames) == 2


@pytest.mark.asyncio
async def test_sse_event_stream_max_seconds_ends_an_idle_stream() -> None:
    frames = [
        f
        async for f in sse_event_stream(
            FakeRealtimeBus(), "idle", heartbeat_seconds=100, disconnect_poll_seconds=0.01, max_seconds=0.05,
        )
    ]
    assert frames == []


def test_unauthenticated_is_strictly_401() -> None:
    client = TestClient(_app(FakeRealtimeBus(), {}))
    assert client.get("/jobs/j1").status_code == 401
    assert client.get("/jobs/j1", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_unknown_or_foreign_job_is_404_not_a_stream() -> None:
    snaps = {("org-a", "j1"): JobProgress(status="processando", progress=0.1)}
    client = TestClient(_app(FakeRealtimeBus(), snaps))
    assert client.get("/jobs/j1", headers={"Authorization": "Bearer ok-b"}).status_code == 404
    assert client.get("/jobs/zzz", headers={"Authorization": "Bearer ok-a"}).status_code == 404


def test_terminal_snapshot_is_sent_then_stream_closes_with_proxy_safe_headers() -> None:
    snaps = {("org-a", "j1"): JobProgress(status="completo", progress=1, terminal=True)}
    client = TestClient(_app(FakeRealtimeBus(), snaps))
    r = client.get("/jobs/j1", headers={"Authorization": "Bearer ok-a"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["x-accel-buffering"] == "no"
    assert "no-cache" in r.headers["cache-control"]
    events = _frames_to_events(r.text)
    assert [e["event"] for e in events] == ["job.progress"]
    assert events[0]["data"]["terminal"] is True and events[0]["data"]["status"] == "completo"


def test_live_job_streams_snapshot_then_closes_on_terminal_event() -> None:
    class ScriptedBus:
        def __init__(self) -> None:
            self.seen: list = []

        async def publish(self, *a, **k):
            raise NotImplementedError

        async def subscribe(self, scope, *, last_event_id=None):
            self.seen.append((scope, last_event_id))
            yield RealtimeEvent("1-1", "job.progress", JobProgress(status="processando", progress=0.5).to_payload())
            yield RealtimeEvent("1-2", "job.progress", JobProgress(status="completo", progress=1, terminal=True).to_payload())
            await asyncio.Event().wait()

    bus = ScriptedBus()
    snaps = {("org-a", "j1"): JobProgress(status="processando", progress=0.1)}
    client = TestClient(_app(bus, snaps))
    r = client.get("/jobs/j1", headers={"Authorization": "Bearer ok-a", "Last-Event-ID": "1-0"})
    events = _frames_to_events(r.text)
    assert [e["data"]["progress"] for e in events] == [0.1, 0.5, 1.0]
    assert events[-1]["data"]["terminal"] is True
    assert bus.seen[0][0] == job_progress_scope("org-a", "j1")  # scope derives from the AUTH org, never the URL
    assert bus.seen[0][1] == "1-0"  # Last-Event-ID resumes


def test_shared_bus_is_one_per_url_and_warns_loudly_when_fake(caplog: pytest.LogCaptureFixture) -> None:
    reset_shared_realtime_buses()
    with caplog.at_level("WARNING"):
        a = get_shared_realtime_bus(None, label="Job progress")
        b = get_shared_realtime_bus(None, label="Job progress")
    assert a is b
    assert sum("FAKE" in r.message for r in caplog.records) == 1
    reset_shared_realtime_buses()
