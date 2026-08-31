"""Assert `app.main`'s `_MAX_BODY_PATH_OVERRIDES` covers every browser
upload route AND that each key actually RESOLVES against the route's
real mounted path.

Presence alone is not enough: `MaxBodySizeMiddleware`'s `*`-wildcard
pattern matches on EXACT segment count (see
`noctusai_lib.api.middleware.MaxBodySizeMiddleware`'s docstring) — a
wrong pattern silently fails to match while still looking correct in a
diff, which a bare "key in dict" check would never catch. These tests
instead build a real `MaxBodySizeMiddleware` from the app's configured
overrides and resolve the actual request path through `_limit_for`, the
same method the middleware itself uses at request time.
"""
from noctusai_lib.api.middleware import MaxBodySizeMiddleware

_UNMATCHED_SENTINEL = 1  # smallest legal max_bytes; no real ceiling is 1 byte


def _overrides_from_app(app) -> dict:
    for m in app.user_middleware:
        if m.cls is MaxBodySizeMiddleware:
            return m.kwargs.get("path_overrides") or {}
    raise AssertionError("MaxBodySizeMiddleware is not mounted on this app")


def _limit_for(overrides: dict, path: str) -> int:
    mw = MaxBodySizeMiddleware(
        app=None, max_bytes=_UNMATCHED_SENTINEL, path_overrides=overrides
    )
    return mw._limit_for(path)


class TestSocialWiringMaxBodyPathOverrides:
    def test_declared_upload_routes_resolve_to_expected_ceiling(self, client):
        app = client.raw().app
        overrides = _overrides_from_app(app)
        expectations = {
            # New in this slice.
            "/api/chat/upload-file": 500 * 1024 * 1024,
            "/api/leads/import/preview": 50 * 1024 * 1024,
            "/api/leads/import/commit": 50 * 1024 * 1024,
            # Pre-existing — asserted here too so a future edit to the
            # shared dict can't silently regress them.
            "/api/videos/upload": 500 * 1024 * 1024,
            "/api/clientes/11111111-1111-1111-1111-111111111111/documentos": 30 * 1024 * 1024,
            "/api/imoveis/ONE0001/documentos": 50 * 1024 * 1024,
            "/api/clientes/11111111-1111-1111-1111-111111111111/financiamento/documentos": 30 * 1024 * 1024,
            "/api/clientes/11111111-1111-1111-1111-111111111111/checklist-extras/22222222-2222-2222-2222-222222222222/documento": 30 * 1024 * 1024,
        }
        for path, expected in expectations.items():
            assert _limit_for(overrides, path) == expected, path

    def test_video_upload_from_code_covered_by_plain_prefix(self, client):
        """`/api/videos/upload/from-code` is deliberately NOT its own
        entry — the plain-prefix `/api/videos/upload` key already covers
        it via longest-matching-prefix (see the comment above that entry
        in `app/main.py`). Verify the coverage instead of assuming it."""
        app = client.raw().app
        overrides = _overrides_from_app(app)
        assert _limit_for(overrides, "/api/videos/upload/from-code") == 500 * 1024 * 1024

    def test_unrelated_json_routes_stay_on_default(self, client):
        app = client.raw().app
        overrides = _overrides_from_app(app)
        for path in (
            "/api/leads/import/batches",
            "/api/chat/message",
            "/api/clientes",
            "/api/marcas",
        ):
            assert _limit_for(overrides, path) == _UNMATCHED_SENTINEL, path
