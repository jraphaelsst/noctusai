"""Tests for `noctusai_seed.upload_route_overrides` — the boot-time
compliance-by-construction check for `max_body_path_overrides`.

WHAT THIS PINS
---------------
`MaxBodySizeMiddleware` caps every inbound body at 1 MB by default (a
DoS guard for webhooks). A route that legitimately receives an
`UploadFile` needs an entry in `max_body_path_overrides` to raise that
cap — and that map is HAND-MAINTAINED, so a forgotten entry drifted
silently across five products (fixture-sized tests kept passing; only a
realistically-sized upload ever 413s). This module derives the required
set from the live route table and refuses to boot when an entry is
missing — see `KB § PATTERNS/backend/upload-route-body-override-derivation.md`.

Three layers, from narrowest to broadest:
  1. `_annotation_declares_upload_file` — one test per annotation SHAPE
     an `UploadFile` parameter can take (this is the part a naive
     `annotation is UploadFile` check would get wrong).
  2. `find_uncovered_upload_routes` — the route-table walk + pattern
     conversion + coverage check, against small synthetic FastAPI apps.
  3. `create_product_app` end-to-end — proves the seam actually fires
     post-router-mount inside the real framework factory, not just in
     isolation.

Per the dispatch brief: exercised ONLY against synthetic/fixture apps
built here, never against a real `products/*/backend/app/main.py` — the
refusal is expected to stay red for those until the sibling slice
(`feat/upload-cap-fleet-ceilings`) lands their ceilings; weakening this
check to make a product boot would defeat the point of it.
"""
from __future__ import annotations

import typing
from typing import Annotated, List, Optional

import pytest
from fastapi import APIRouter, FastAPI, File, UploadFile
from fastapi.testclient import TestClient

from noctusai_lib.api.middleware import KEEP_DEFAULT_MAX_BODY
from noctusai_seed.upload_route_overrides import (
    _annotation_declares_upload_file,
    enforce_upload_route_overrides,
    find_uncovered_upload_routes,
)


# ─────────────────────────────────────────────────────────────────────────
# Layer 1 — annotation-shape detection. One test per shape named in the
# dispatch brief, plus the forms discovered while building this (Annotated,
# and a nested list[UploadFile] | None).
# ─────────────────────────────────────────────────────────────────────────


def test_bare_upload_file_annotation():
    assert _annotation_declares_upload_file(UploadFile) is True


def test_list_upload_file_annotation_lowercase_generic():
    # erp-imobiliario/routers/storage.py's `List[UploadFile] = File(...)`
    # shape, `list[...]` spelling.
    assert _annotation_declares_upload_file(list[UploadFile]) is True


def test_list_upload_file_annotation_typing_generic():
    # Same route, `typing.List[...]` spelling (both appear fleet-wide).
    assert _annotation_declares_upload_file(List[UploadFile]) is True


def test_optional_upload_file_annotation_typing_union():
    assert _annotation_declares_upload_file(Optional[UploadFile]) is True


def test_upload_file_or_none_pep604_union():
    # social-wiring/routers/chat_router.py's `file: UploadFile | None`
    # shape. On Python < 3.14 this origin is `types.UnionType`, a
    # DIFFERENT object from `typing.Union` — the exact miss this test
    # exists to pin (see the `_UNION_ORIGINS` comment in the module).
    assert _annotation_declares_upload_file(UploadFile | None) is True


def test_annotated_upload_file():
    assert _annotation_declares_upload_file(Annotated[UploadFile, File(...)]) is True


def test_nested_list_upload_file_or_none():
    assert _annotation_declares_upload_file(list[UploadFile] | None) is True


def test_non_upload_annotations_are_not_flagged():
    assert _annotation_declares_upload_file(str) is False
    assert _annotation_declares_upload_file(Optional[str]) is False
    assert _annotation_declares_upload_file(list[str]) is False
    assert _annotation_declares_upload_file(int | None) is False


# ─────────────────────────────────────────────────────────────────────────
# Layer 2 — find_uncovered_upload_routes against synthetic apps.
# ─────────────────────────────────────────────────────────────────────────


def _synthetic_upload_app() -> FastAPI:
    app = FastAPI()

    @app.post("/api/plain/upload")
    async def plain(file: UploadFile = File(...)):
        return {}

    @app.post("/api/multi/upload")
    async def multi(files: list[UploadFile] = File(...)):
        return {}

    @app.post("/api/message")
    async def optional_upload(file: UploadFile | None = File(None)):
        return {}

    @app.post("/api/clientes/{cliente_id}/documentos")
    async def dynamic_segment(cliente_id: str, file: UploadFile = File(...)):
        return {}

    @app.post("/api/clientes/{cliente_id}/notas")
    async def no_upload_same_prefix(cliente_id: str, texto: str):
        return {}

    @app.get("/api/no-upload")
    async def no_upload():
        return {}

    return app


def test_uncovered_routes_are_all_found_when_map_is_empty():
    app = _synthetic_upload_app()
    missing = find_uncovered_upload_routes(app, None)
    pattern_keys = {m[0] for m in missing}
    assert pattern_keys == {
        "/api/plain/upload",
        "/api/multi/upload",
        "/api/message",
        "/api/clientes/*/documentos",
    }


def test_non_upload_routes_are_never_flagged():
    app = _synthetic_upload_app()
    missing = find_uncovered_upload_routes(app, None)
    flagged_paths = {m[1] for m in missing}
    assert "/api/no-upload" not in flagged_paths
    assert "/api/clientes/{cliente_id}/notas" not in flagged_paths


def test_fully_covered_map_leaves_nothing_uncovered():
    app = _synthetic_upload_app()
    overrides = {
        "/api/plain/upload": 10,
        "/api/multi/upload": 20,
        "/api/message": KEEP_DEFAULT_MAX_BODY,
        "/api/clientes/*/documentos": 30,
    }
    assert find_uncovered_upload_routes(app, overrides) == []


def test_partial_coverage_reports_only_the_gap():
    app = _synthetic_upload_app()
    overrides = {"/api/plain/upload": 10}
    missing = find_uncovered_upload_routes(app, overrides)
    pattern_keys = {m[0] for m in missing}
    assert pattern_keys == {"/api/multi/upload", "/api/message", "/api/clientes/*/documentos"}


def test_prefix_override_covers_a_deeper_sibling_route():
    # Mirrors social-wiring's real `/api/videos/upload` -> also covers
    # `/api/videos/upload/from-code` via longest-prefix, not an exact key.
    app = FastAPI()

    @app.post("/api/videos/upload")
    async def base(file: UploadFile = File(...)):
        return {}

    @app.post("/api/videos/upload/from-code")
    async def from_code(file: UploadFile = File(...)):
        return {}

    missing = find_uncovered_upload_routes(app, {"/api/videos/upload": 500})
    assert missing == []


# ─────────────────────────────────────────────────────────────────────────
# Layer 2b — enforce_upload_route_overrides: the raise/pass boundary.
# ─────────────────────────────────────────────────────────────────────────


def test_enforce_raises_runtime_error_naming_the_pattern_key_and_endpoint():
    app = FastAPI()

    @app.post("/api/foo/upload")
    async def upload_foo(file: UploadFile = File(...)):
        return {}

    with pytest.raises(RuntimeError) as exc_info:
        enforce_upload_route_overrides(app, None, product_name="Widgets")

    message = str(exc_info.value)
    assert "Widgets" in message
    assert "/api/foo/upload" in message
    assert "upload_foo" in message
    assert "KEEP_DEFAULT_MAX_BODY" in message  # the documented opt-out is named


def test_enforce_passes_when_every_route_is_covered():
    app = FastAPI()

    @app.post("/api/foo/upload")
    async def upload_foo(file: UploadFile = File(...)):
        return {}

    # Must not raise.
    enforce_upload_route_overrides(
        app, {"/api/foo/upload": 999}, product_name="Widgets"
    )


def test_enforce_passes_with_the_keep_default_opt_out():
    app = FastAPI()

    @app.post("/api/small/upload")
    async def upload_small(file: UploadFile = File(...)):
        return {}

    enforce_upload_route_overrides(
        app,
        {"/api/small/upload": KEEP_DEFAULT_MAX_BODY},
        product_name="Widgets",
    )


def test_enforce_is_a_no_op_for_an_app_with_no_upload_routes():
    app = FastAPI()

    @app.get("/api/ping")
    async def ping():
        return {"ok": True}

    enforce_upload_route_overrides(app, None, product_name="Widgets")


# ─────────────────────────────────────────────────────────────────────────
# Layer 3 — end-to-end through the real `create_product_app` seam. Proves
# step 10a actually fires post-router-mount (not inside `configure_app`,
# where `app.routes` would still be empty) and that BOTH resolution paths
# for `max_body_path_overrides` (kwarg vs `settings.max_body_path_overrides`)
# feed the boot-time check the SAME effective map the middleware uses.
# ─────────────────────────────────────────────────────────────────────────


def _upload_router() -> APIRouter:
    router = APIRouter(prefix="/api/docs", tags=["docs"])

    @router.post("/upload")
    async def upload(file: UploadFile = File(...)):
        return {"ok": True}

    return router


def test_create_product_app_refuses_to_boot_with_an_uncovered_upload_route(
    fake_settings,
):
    from noctusai_seed import create_product_app

    with pytest.raises(RuntimeError, match="max_body_path_overrides"):
        create_product_app(
            name="Test",
            schema="test",
            settings=fake_settings,
            routers=[_upload_router()],
            standard_routers=["health"],
        )


def test_create_product_app_boots_when_the_kwarg_covers_the_route(fake_settings):
    from noctusai_seed import create_product_app

    app = create_product_app(
        name="Test",
        schema="test",
        settings=fake_settings,
        routers=[_upload_router()],
        standard_routers=["health"],
        max_body_path_overrides={"/api/docs/upload": 25 * 1024 * 1024},
    )
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200


def test_create_product_app_boots_when_settings_carries_the_overrides(fake_settings):
    """The fallback path `configure_app` resolves internally
    (`settings.max_body_path_overrides` when the kwarg is omitted) must
    ALSO satisfy the boot-time refusal — pins the
    `_effective_max_body_path_overrides` plumbing in `create_product_app`,
    not just `configure_app`'s own return value in isolation."""
    from noctusai_seed import create_product_app

    fake_settings.max_body_path_overrides = {"/api/docs/upload": 25 * 1024 * 1024}

    app = create_product_app(
        name="Test",
        schema="test",
        settings=fake_settings,
        routers=[_upload_router()],
        standard_routers=["health"],
    )
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
