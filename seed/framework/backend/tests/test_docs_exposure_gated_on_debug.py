"""`/docs`, `/redoc` AND `/openapi.json` are all gated on `settings.debug`.

Production ran with `DEBUG=true` until 2026-08-24 and served all three on the
public internet for every product in the fleet.

The load-bearing case is `openapi_url`. `docs_url=None` removes only the Swagger
*page*; FastAPI keeps serving the schema at `openapi_url` regardless, and the
schema is the half that matters — a machine-readable map of every route,
parameter, and response model. Gating the two page URLs and leaving the third
would have closed the door and left the blueprint on the step, while looking
fixed from a browser.

These assert the ROUTE TABLE, not just the constructor kwargs: `openapi_url` is
what decides whether the route is mounted, and a refactor that kept the
attribute but re-added the route would slip past a kwargs-only check.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI


def _routes(app: FastAPI) -> set[str]:
    return {getattr(r, "path", None) for r in app.routes}


def _build(debug: bool) -> FastAPI:
    """The seed's own construction shape, isolated from product wiring."""
    return FastAPI(
        title="t",
        docs_url="/docs" if debug else None,
        redoc_url="/redoc" if debug else None,
        openapi_url="/openapi.json" if debug else None,
    )


class TestProdShapeServesNoSchema:
    @pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
    def test_none_of_the_three_is_mounted_when_debug_is_off(self, path: str):
        assert path not in _routes(_build(debug=False)), (
            f"{path} is mounted with debug=False — this is the 2026-08-24 leak. "
            "openapi_url must be gated alongside docs_url/redoc_url."
        )

    def test_openapi_url_attribute_is_actually_none(self):
        assert _build(debug=False).openapi_url is None


class TestDevShapeKeepsTheDocs:
    """The gate must not cost local development its API docs."""

    @pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
    def test_all_three_are_mounted_when_debug_is_on(self, path: str):
        assert path in _routes(_build(debug=True))


def test_the_seed_source_gates_all_three_on_settings_debug():
    """Pins the REAL call site, not just the shape reproduced above."""
    import inspect

    from noctusai_seed import app as seed_app

    src = inspect.getsource(seed_app)
    for kwarg in ("docs_url", "redoc_url", "openapi_url"):
        assert f'{kwarg}="/' in src, f"{kwarg} not constructed in noctusai_seed.app"
    # openapi_url specifically — the one that was missing until 2026-08-24.
    assert 'openapi_url="/openapi.json" if settings.debug else None' in src
