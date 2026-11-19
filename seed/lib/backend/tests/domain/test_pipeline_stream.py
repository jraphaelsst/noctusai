"""Live pipeline stream: the `move_card` publish hook + the org-scoped SSE router."""
from __future__ import annotations

import asyncio
import json
import logging

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from noctusai_lib.domain.pipeline import (
    CARD_MOVED_EVENT,
    PipelineConfig,
    create_pipeline_stream_router,
    make_pipeline_publisher,
    move_card,
    pipeline_scope,
    publish_card_state,
)
from noctusai_lib.realtime import FakeRealtimeBus
from noctusai_lib.testing.mocks import MockSupabaseClient

CFG = PipelineConfig(pipeline="funil", card_table="cards", value_field="valor", entity_label="card", entity_kind="card")
ORG = "org-a"


@pytest.fixture
def db():
    c = MockSupabaseClient(validate_schema=False, schema="erp")
    c.set_table_data("pipeline_stages", [
        {"id": "s1", "org_id": ORG, "pipeline": "funil", "slug": "a", "label": "A", "posicao": 0, "ativo": True},
        {"id": "s2", "org_id": ORG, "pipeline": "funil", "slug": "b", "label": "B", "posicao": 1, "ativo": True},
    ])
    c.set_table_data("pipeline_movimentos", [])
    c.set_table_data("cards", [{"id": "c1", "org_id": ORG, "etapa_id": "s1", "kanban_pos": 0}])
    return c


def test_publish_runs_after_the_history_row_is_written(db):
    seen = []

    def hook(event, payload):
        # The move + history are already persisted when the hook fires.
        seen.append((event, payload, len(db.table("pipeline_movimentos").inserted_payloads)))

    move_card(db, CFG, card_id="c1", to_stage_id="s2", user_id="u1", org_id=ORG, motivo="m", publish=hook)
    (event, payload, history_rows), = seen
    assert event == CARD_MOVED_EVENT == "pipeline.card_moved"
    assert history_rows == 1
    assert payload["card_id"] == "c1" and payload["from_stage_id"] == "s1" and payload["to_stage_id"] == "s2"
    assert payload["motivo"] == "m" and payload["actor"] == "u1" and payload["at"]


def test_publish_not_called_for_a_within_stage_reorder(db):
    hook_calls = []
    move_card(db, CFG, card_id="c1", to_stage_id="s1", user_id="u1", org_id=ORG, novo_indice=3,
              publish=lambda *a: hook_calls.append(a))
    assert hook_calls == []


def test_publish_failure_is_logged_and_never_raises_into_the_move(db, caplog):
    def boom(event, payload):
        raise RuntimeError("bus down")

    with caplog.at_level(logging.WARNING):
        row = move_card(db, CFG, card_id="c1", to_stage_id="s2", user_id="u1", org_id=ORG, publish=boom)
    assert row["etapa_id"] == "s2"
    assert len(db.table("pipeline_movimentos").inserted_payloads) == 1
    assert any("pipeline publish hook failed" in r.message and "card=c1" in r.message for r in caplog.records)


def test_publisher_lands_on_the_org_pipeline_scope(db):
    bus = FakeRealtimeBus()
    move_card(db, CFG, card_id="c1", to_stage_id="s2", user_id="u1", org_id=ORG,
              publish=make_pipeline_publisher(bus, ORG, "funil"))

    async def read():
        out = []
        async for ev in bus.subscribe(pipeline_scope(ORG, "funil"), last_event_id="0-0"):
            out.append(ev)
            break
        return out

    (ev,) = asyncio.run(asyncio.wait_for(read(), 2))
    assert ev.event == "pipeline.card_moved" and ev.payload["to_stage_id"] == "s2"


def test_bus_failure_inside_the_publisher_is_logged_not_raised(db, caplog):
    class DeadBus(FakeRealtimeBus):
        async def publish(self, scope, event, payload):
            raise ConnectionError("redis gone")

    with caplog.at_level(logging.WARNING):
        row = move_card(db, CFG, card_id="c1", to_stage_id="s2", user_id="u1", org_id=ORG,
                        publish=make_pipeline_publisher(DeadBus(), ORG, "funil"))
    assert row["etapa_id"] == "s2"
    assert any("pipeline publish failed" in r.message and "org=org-a" in r.message for r in caplog.records)


def test_publish_card_state_payload():
    bus = FakeRealtimeBus()
    asyncio.run(publish_card_state(bus, ORG, "funil", "c1", {"mensagem": "Gerando", "progresso": 0.5}))

    async def read():
        async for ev in bus.subscribe(pipeline_scope(ORG, "funil"), last_event_id="0-0"):
            return ev

    ev = asyncio.run(asyncio.wait_for(read(), 2))
    assert ev.event == "pipeline.card_state"
    assert ev.payload == {"card_id": "c1", "state": {"mensagem": "Gerando", "progresso": 0.5}}


# --- router -----------------------------------------------------------------


def _auth(request: Request):
    token = request.headers.get("authorization")
    if token not in ("Bearer a", "Bearer b"):
        raise HTTPException(status_code=401, detail="unauthenticated")
    return {"org_id": "org-a" if token == "Bearer a" else "org-b"}


def _app(bus) -> FastAPI:
    app = FastAPI()
    app.include_router(
        create_pipeline_stream_router(CFG, bus, auth_dependency=_auth, org_resolver=lambda r, a: a["org_id"]),
        prefix="/stream",
    )
    return app


def test_stream_unauthenticated_is_401():
    assert TestClient(_app(FakeRealtimeBus())).get("/stream/").status_code == 401


class _FiniteBus:
    """Per-scope buffered events, then the stream ENDS (an endless live-tail would hang TestClient)."""

    def __init__(self, by_scope):
        self.by_scope = by_scope
        self.scopes = []

    async def subscribe(self, scope, *, last_event_id=None):
        self.scopes.append(scope)
        for ev in self.by_scope.get(scope, []):
            yield ev


def test_stream_is_scoped_to_the_callers_org():
    from noctusai_lib.realtime import RealtimeEvent

    bus = _FiniteBus({
        pipeline_scope("org-a", "funil"): [RealtimeEvent(id="1-0", event="pipeline.card_moved", payload={"card_id": "x-of-a"})],
        pipeline_scope("org-b", "funil"): [RealtimeEvent(id="1-0", event="pipeline.card_moved", payload={"card_id": "x-of-b"})],
    })
    r = TestClient(_app(bus)).get("/stream/", headers={"Authorization": "Bearer b"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert bus.scopes == [pipeline_scope("org-b", "funil")]
    assert "x-of-b" in r.text and "x-of-a" not in r.text
