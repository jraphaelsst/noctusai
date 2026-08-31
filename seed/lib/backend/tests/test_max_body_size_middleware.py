"""Unit tests for `noctusai_lib.api.middleware.MaxBodySizeMiddleware`.

Asserts:
  - Below cap: handler runs, body is readable.
  - Content-Length above cap: 413 short-circuit, handler never invoked.
  - Invalid Content-Length: 400.
  - max_bytes <= 0 raises at construction time (not silently accepted).
  - path_overrides: longest-matching-prefix wins, non-matching paths keep
    the default, both the Content-Length AND the streaming-counter checks
    honor the resolved per-path limit, and the 413 body names the limit
    that was actually applied.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from noctusai_lib.api.middleware import (
    KEEP_DEFAULT_MAX_BODY,
    MaxBodySizeMiddleware,
    path_is_covered_by_overrides,
    to_wildcard_pattern,
)


def _make_app(
    *, max_bytes: int, path_overrides: dict[str, int] | None = None
) -> tuple[TestClient, dict]:
    app = FastAPI()
    app.add_middleware(
        MaxBodySizeMiddleware, max_bytes=max_bytes, path_overrides=path_overrides
    )
    counter = {"handled": 0}

    @app.post("/echo")
    async def echo(request: Request):
        counter["handled"] += 1
        body = await request.body()
        return {"len": len(body)}

    @app.post("/uploads/echo")
    async def echo_uploads(request: Request):
        counter["handled"] += 1
        body = await request.body()
        return {"len": len(body)}

    @app.post("/uploads/videos/echo")
    async def echo_uploads_videos(request: Request):
        counter["handled"] += 1
        body = await request.body()
        return {"len": len(body)}

    return TestClient(app), counter


def test_under_cap_request_succeeds():
    client, counter = _make_app(max_bytes=1024)
    resp = client.post("/echo", content=b"x" * 100)
    assert resp.status_code == 200
    assert resp.json() == {"len": 100}
    assert counter["handled"] == 1


def test_content_length_over_cap_returns_413_without_invoking_handler():
    client, counter = _make_app(max_bytes=512)
    resp = client.post("/echo", content=b"x" * 1024)
    assert resp.status_code == 413
    body = resp.json()
    assert body["error"] == "request body too large"
    assert body["limit_bytes"] == 512
    assert counter["handled"] == 0  # short-circuit before handler


def test_invalid_content_length_returns_400():
    client, _ = _make_app(max_bytes=1024)
    resp = client.post(
        "/echo", content=b"x", headers={"content-length": "not-a-number"},
    )
    assert resp.status_code == 400
    assert "Content-Length" in resp.json()["detail"]


def test_construction_rejects_non_positive_max_bytes():
    with pytest.raises(ValueError):
        MaxBodySizeMiddleware(app=None, max_bytes=0)
    with pytest.raises(ValueError):
        MaxBodySizeMiddleware(app=None, max_bytes=-1)


def test_default_cap_via_configure_app(monkeypatch):
    """`configure_app` honors `settings.max_body_bytes`."""
    from types import SimpleNamespace

    from noctusai_lib.api.app_factory import configure_app

    settings = SimpleNamespace(
        cors_origins_list=["http://localhost"],
        sentry_dsn="",
        is_production=False,
        debug=True,
        max_body_bytes=256,
    )
    app = FastAPI()

    @app.post("/echo")
    async def echo(request: Request):
        return {"len": len((await request.body()))}

    configure_app(app, settings)
    client = TestClient(app)
    # 200B fits under 256-byte cap
    assert client.post("/echo", content=b"x" * 200).status_code == 200
    # 300B trips the cap
    assert client.post("/echo", content=b"x" * 300).status_code == 413


def test_configure_app_returns_the_effective_max_body_path_overrides():
    """`create_product_app` needs the SAME map `configure_app` actually
    wired into the middleware — including the settings-vs-kwarg fallback
    — to hand to the boot-time upload-route derivation. Covers both
    resolution paths: the explicit kwarg, and the `settings.
    max_body_path_overrides` fallback when the kwarg is omitted."""
    from types import SimpleNamespace

    from noctusai_lib.api.app_factory import configure_app

    base_settings_kwargs = dict(
        cors_origins_list=["http://localhost"],
        sentry_dsn="",
        is_production=False,
        debug=True,
    )

    # Explicit kwarg wins.
    app1 = FastAPI()
    settings1 = SimpleNamespace(**base_settings_kwargs)
    kwarg_overrides = {"/api/foo/upload": 999}
    resolved1 = configure_app(app1, settings1, max_body_path_overrides=kwarg_overrides)
    assert resolved1 == kwarg_overrides

    # Falls back to settings.max_body_path_overrides when the kwarg is omitted.
    app2 = FastAPI()
    settings_overrides = {"/api/bar/upload": 111}
    settings2 = SimpleNamespace(
        **base_settings_kwargs, max_body_path_overrides=settings_overrides
    )
    resolved2 = configure_app(app2, settings2)
    assert resolved2 == settings_overrides

    # Neither present -> None, not a KeyError / AttributeError.
    app3 = FastAPI()
    settings3 = SimpleNamespace(**base_settings_kwargs)
    resolved3 = configure_app(app3, settings3)
    assert resolved3 is None


# ─────────────────────────────────────────────────────────────────────────
# path_overrides
# ─────────────────────────────────────────────────────────────────────────

_OVERRIDES = {
    "/uploads": 2048,          # broad prefix
    "/uploads/videos": 8192,   # more specific prefix — longer, must win
}


def test_path_override_applies_to_matching_prefix():
    client, counter = _make_app(max_bytes=256, path_overrides=_OVERRIDES)
    # 1500B: over the 256B default, under the /uploads 2048B override.
    resp = client.post("/uploads/echo", content=b"x" * 1500)
    assert resp.status_code == 200
    assert counter["handled"] == 1


def test_path_override_rejects_body_over_its_own_cap():
    client, counter = _make_app(max_bytes=256, path_overrides=_OVERRIDES)
    resp = client.post("/uploads/echo", content=b"x" * 4000)
    assert resp.status_code == 413
    body = resp.json()
    assert body["limit_bytes"] == 2048  # names the limit that was hit
    assert counter["handled"] == 0


def test_non_matching_path_keeps_app_wide_default():
    client, counter = _make_app(max_bytes=256, path_overrides=_OVERRIDES)
    resp = client.post("/echo", content=b"x" * 1000)
    assert resp.status_code == 413
    assert resp.json()["limit_bytes"] == 256
    assert counter["handled"] == 0


def test_longest_prefix_wins():
    client, counter = _make_app(max_bytes=256, path_overrides=_OVERRIDES)
    # 5000B: over the broad /uploads (2048B) override, under the more
    # specific /uploads/videos (8192B) override — the longer prefix must
    # win, or this request would wrongly 413 at 2048B.
    resp = client.post("/uploads/videos/echo", content=b"x" * 5000)
    assert resp.status_code == 200
    assert counter["handled"] == 1

    # Confirm the specific override actually enforces ITS OWN cap too.
    resp2 = client.post("/uploads/videos/echo", content=b"x" * 9000)
    assert resp2.status_code == 413
    assert resp2.json()["limit_bytes"] == 8192


def test_construction_rejects_non_positive_override():
    with pytest.raises(ValueError):
        MaxBodySizeMiddleware(app=None, max_bytes=1024, path_overrides={"/x": 0})
    with pytest.raises(ValueError):
        MaxBodySizeMiddleware(app=None, max_bytes=1024, path_overrides={"/x": -1})


@pytest.mark.asyncio
async def test_streaming_path_honors_override_below_cap():
    """No Content-Length header (streaming/chunked) — the override must
    apply on the streaming-counter leg too, not just the Content-Length
    leg."""
    app = FastAPI()
    app.add_middleware(
        MaxBodySizeMiddleware, max_bytes=256, path_overrides=_OVERRIDES
    )
    counter = {"handled": 0}

    @app.post("/uploads/echo")
    async def echo_uploads(request: Request):
        counter["handled"] += 1
        body = await request.body()
        return {"len": len(body)}

    async def _gen():
        # 1500B over 3 chunks — httpx won't set Content-Length for a
        # streamed/iterator body, forcing the middleware onto its
        # streaming-counter leg.
        for _ in range(3):
            yield b"x" * 500

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/uploads/echo", content=_gen())

    assert resp.status_code == 200
    assert resp.json() == {"len": 1500}
    assert counter["handled"] == 1


@pytest.mark.asyncio
async def test_streaming_path_honors_override_above_cap():
    """Same streaming path, but the body exceeds the per-path override —
    must still 413 via the streaming-counter leg, naming the override's
    limit, not the app-wide default.

    Unlike the Content-Length check, the streaming counter can't reject
    before the handler starts (it only learns the body is oversized once
    bytes accumulate, typically while the handler is already awaiting
    `request.body()`). That triggers Starlette's `ClientDisconnect` deep
    in body-parsing, deliberately NOT routed through any registered
    exception handler — the middleware's own `except` around `call_next`
    is what turns that into a clean 413 (see `dispatch`); this test
    exercises that path directly.
    """
    app = FastAPI()
    app.add_middleware(
        MaxBodySizeMiddleware, max_bytes=256, path_overrides=_OVERRIDES
    )
    counter = {"handled": 0}

    @app.post("/uploads/echo")
    async def echo_uploads(request: Request):
        counter["handled"] += 1
        await request.body()
        return {"ok": True}

    async def _gen():
        # 3000B over 3 chunks — over the /uploads 2048B override.
        for _ in range(3):
            yield b"x" * 1000

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/uploads/echo", content=_gen())

    assert resp.status_code == 413
    assert resp.json()["limit_bytes"] == 2048
    # The handler DOES start (FastAPI must invoke it to know it wants the
    # body) — this isn't a pre-handler short-circuit like Content-Length.
    # What matters is the client sees a clean 413, not a 500.
    assert counter["handled"] == 1


@pytest.mark.asyncio
async def test_streaming_path_still_honors_default_without_override():
    """Baseline sanity: the streaming leg trips the app-wide default when
    no override applies (pre-existing behavior, unaffected by this
    change)."""
    app = FastAPI()
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=256)
    counter = {"handled": 0}

    @app.post("/echo")
    async def echo(request: Request):
        counter["handled"] += 1
        await request.body()
        return {"ok": True}

    async def _gen():
        for _ in range(3):
            yield b"x" * 200  # 600B total, over the 256B default

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/echo", content=_gen())

    assert resp.status_code == 413
    assert resp.json()["limit_bytes"] == 256
    assert counter["handled"] == 1


# ─────────────────────────────────────────────────────────────────────────
# path_overrides — single-segment-wildcard patterns
# ─────────────────────────────────────────────────────────────────────────
#
# Motivating shape: `POST /api/clientes/{cliente_id}/documentos` — a
# path parameter (dynamic UUID) sits BEFORE the segment that actually
# needs the bigger cap. A plain prefix can't express "this exact suffix
# under a parameterised segment" without either stopping short at
# `/api/clientes` (too broad — would also raise the cap on every JSON
# clientes route) or being unwritable (the id is dynamic). The pattern
# `"/api/clientes/*/documentos"` matches ONLY that exact 4-segment shape.

_PATTERN_OVERRIDES = {"/api/clientes/*/documentos": 2048}


def _make_pattern_app(*, max_bytes: int = 256) -> tuple[TestClient, dict]:
    app = FastAPI()
    app.add_middleware(
        MaxBodySizeMiddleware, max_bytes=max_bytes, path_overrides=_PATTERN_OVERRIDES
    )
    counter = {"handled": 0}

    def _mk(path):
        async def _handler(request: Request):
            counter["handled"] += 1
            body = await request.body()
            return {"path": path, "len": len(body)}
        return _handler

    # The route the override targets.
    app.add_api_route(
        "/api/clientes/{cliente_id}/documentos", _mk("documentos"), methods=["POST"],
    )
    # Same segment COUNT (4), but a DIFFERENT literal at the wildcard's
    # neighboring position — must NOT match.
    app.add_api_route(
        "/api/clientes/documentos/tipos", _mk("tipos"), methods=["POST"],
    )
    # Same segment count (4), but the LAST segment differs — must NOT match.
    app.add_api_route(
        "/api/clientes/{cliente_id}/timeline", _mk("timeline"), methods=["POST"],
    )
    # Fewer segments (2) — the bare collection route — must NOT match.
    app.add_api_route("/api/clientes", _mk("collection"), methods=["POST"])
    # More segments (5) — a sub-resource under documentos — must NOT match.
    app.add_api_route(
        "/api/clientes/{cliente_id}/documentos/{documento_id}/url",
        _mk("doc-url"),
        methods=["POST"],
    )

    return TestClient(app), counter


def test_pattern_override_matches_exact_wildcard_shape():
    client, counter = _make_pattern_app()
    cid = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    # 1500B: over the 256B default, under the pattern's 2048B override.
    resp = client.post(f"/api/clientes/{cid}/documentos", content=b"x" * 1500)
    assert resp.status_code == 200
    assert counter["handled"] == 1


def test_pattern_override_rejects_body_over_its_own_cap():
    client, counter = _make_pattern_app()
    cid = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    resp = client.post(f"/api/clientes/{cid}/documentos", content=b"x" * 4000)
    assert resp.status_code == 413
    assert resp.json()["limit_bytes"] == 2048  # names the pattern's own limit
    assert counter["handled"] == 0


def test_pattern_override_does_not_widen_same_segment_count_sibling():
    """`/api/clientes/documentos/tipos` has the SAME segment count (4) as
    the targeted pattern, but "documentos" sits at the WILDCARD's
    position rather than the literal `documentos` tail — must still be
    rejected under the 256B default, not the 2048B override. Guards
    against the exact "too-broad override silently weakens the guard"
    failure mode this feature exists to prevent."""
    client, counter = _make_pattern_app()
    resp = client.post("/api/clientes/documentos/tipos", content=b"x" * 1500)
    assert resp.status_code == 413
    assert resp.json()["limit_bytes"] == 256
    assert counter["handled"] == 0


def test_pattern_override_does_not_match_different_final_segment():
    """`/api/clientes/{id}/timeline` — same shape up to the wildcard, but
    the tail segment is `timeline`, not `documentos`. Must keep the
    app-wide default."""
    client, counter = _make_pattern_app()
    cid = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    resp = client.post(f"/api/clientes/{cid}/timeline", content=b"x" * 1500)
    assert resp.status_code == 413
    assert resp.json()["limit_bytes"] == 256
    assert counter["handled"] == 0


def test_pattern_override_does_not_match_shorter_collection_route():
    client, counter = _make_pattern_app()
    resp = client.post("/api/clientes", content=b"x" * 1500)
    assert resp.status_code == 413
    assert resp.json()["limit_bytes"] == 256
    assert counter["handled"] == 0


def test_pattern_override_does_not_match_longer_sub_resource_route():
    client, counter = _make_pattern_app()
    cid = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    did = "11111111-2222-3333-4444-555555555555"
    resp = client.post(
        f"/api/clientes/{cid}/documentos/{did}/url", content=b"x" * 1500
    )
    assert resp.status_code == 413
    assert resp.json()["limit_bytes"] == 256
    assert counter["handled"] == 0


def test_pattern_and_plain_prefix_overrides_coexist():
    """Sanity: adding a pattern override doesn't disturb an unrelated
    plain-prefix override in the same middleware instance."""
    app = FastAPI()
    app.add_middleware(
        MaxBodySizeMiddleware,
        max_bytes=256,
        path_overrides={**_PATTERN_OVERRIDES, **_OVERRIDES},
    )
    counter = {"handled": 0}

    @app.post("/api/clientes/{cliente_id}/documentos")
    async def documentos(request: Request, cliente_id: str):
        counter["handled"] += 1
        await request.body()
        return {"ok": True}

    @app.post("/uploads/echo")
    async def uploads_echo(request: Request):
        counter["handled"] += 1
        await request.body()
        return {"ok": True}

    client = TestClient(app)
    cid = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    # Pattern override (2048B) applies to the documentos route.
    assert client.post(f"/api/clientes/{cid}/documentos", content=b"x" * 1500).status_code == 200
    # Plain-prefix override (2048B, from _OVERRIDES["/uploads"]) applies independently.
    assert client.post("/uploads/echo", content=b"x" * 1500).status_code == 200
    assert counter["handled"] == 2


def test_construction_rejects_non_positive_pattern_override():
    with pytest.raises(ValueError):
        MaxBodySizeMiddleware(
            app=None, max_bytes=1024, path_overrides={"/api/clientes/*/documentos": 0}
        )


# ─────────────────────────────────────────────────────────────────────────
# KEEP_DEFAULT_MAX_BODY sentinel — the documented opt-out for a route that
# should genuinely stay at the app-wide default despite declaring an
# UploadFile parameter (see `noctusai_seed.upload_route_overrides`).
# ─────────────────────────────────────────────────────────────────────────


def test_keep_default_sentinel_behaves_identically_to_the_app_wide_default():
    client, _ = _make_app(
        max_bytes=256, path_overrides={"/echo": KEEP_DEFAULT_MAX_BODY}
    )
    assert client.post("/echo", content=b"x" * 200).status_code == 200
    assert client.post("/echo", content=b"x" * 300).status_code == 413


def test_keep_default_sentinel_does_not_trip_the_positive_value_guard():
    # A plain `int <= 0` would raise (see test_construction_rejects_non_positive_
    # override above) — the sentinel must NOT be treated as such a value.
    MaxBodySizeMiddleware(
        app=None, max_bytes=1024, path_overrides={"/api/avatar/upload": KEEP_DEFAULT_MAX_BODY}
    )
    MaxBodySizeMiddleware(
        app=None,
        max_bytes=1024,
        path_overrides={"/api/clientes/*/avatar": KEEP_DEFAULT_MAX_BODY},
    )


# ─────────────────────────────────────────────────────────────────────────
# to_wildcard_pattern / path_is_covered_by_overrides — the boot-time
# derivation's shared vocabulary with the middleware's own matching rules.
# ─────────────────────────────────────────────────────────────────────────


def test_to_wildcard_pattern_converts_every_dynamic_segment():
    assert (
        to_wildcard_pattern("/api/clientes/{cliente_id}/documentos")
        == "/api/clientes/*/documentos"
    )
    assert (
        to_wildcard_pattern("/api/clientes/{cliente_id}/checklist-extras/{extra_id}/documento")
        == "/api/clientes/*/checklist-extras/*/documento"
    )


def test_to_wildcard_pattern_handles_path_converters():
    assert to_wildcard_pattern("/api/files/{path:path}") == "/api/files/*"


def test_to_wildcard_pattern_is_a_no_op_for_a_fully_literal_path():
    assert to_wildcard_pattern("/api/videos/upload") == "/api/videos/upload"


def test_path_is_covered_by_overrides_pattern_match():
    overrides = {"/api/clientes/*/documentos": 30}
    assert path_is_covered_by_overrides("/api/clientes/*/documentos", overrides)
    # Different segment count under the same prefix — NOT covered by the
    # pattern (mirrors _pattern_matches' exact-shape requirement).
    assert not path_is_covered_by_overrides(
        "/api/clientes/*/financiamento/documentos", overrides
    )


def test_path_is_covered_by_overrides_prefix_match():
    overrides = {"/api/videos/upload": 500}
    assert path_is_covered_by_overrides("/api/videos/upload", overrides)
    assert path_is_covered_by_overrides("/api/videos/upload/from-code", overrides)
    assert not path_is_covered_by_overrides("/api/videos/list", overrides)


def test_path_is_covered_by_overrides_sentinel_value_still_counts_as_covered():
    overrides = {"/api/avatar/upload": KEEP_DEFAULT_MAX_BODY}
    assert path_is_covered_by_overrides("/api/avatar/upload", overrides)


def test_path_is_covered_by_overrides_empty_or_none():
    assert not path_is_covered_by_overrides("/api/anything", None)
    assert not path_is_covered_by_overrides("/api/anything", {})
