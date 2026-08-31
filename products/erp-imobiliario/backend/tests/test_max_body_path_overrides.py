"""Assert `app.main`'s `_MAX_BODY_PATH_OVERRIDES` covers every browser
upload route AND that each key actually RESOLVES against the route's
real mounted path — including the `/api/storage/upload` vs
`/api/storage/upload-multiple` prefix-collision footgun the comment in
`app/main.py` calls out explicitly.

Presence alone is not enough: `MaxBodySizeMiddleware`'s `*`-wildcard
pattern matches on EXACT segment count (see
`noctusai_lib.api.middleware.MaxBodySizeMiddleware`'s docstring), and a
plain-prefix entry can accidentally swallow a LONGER, unrelated route
via `str.startswith`. A bare "key in dict" check would catch neither
failure mode. These tests instead build a real `MaxBodySizeMiddleware`
from the app's configured overrides and resolve the actual request path
through `_limit_for`, the same method the middleware uses at request
time.
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


class TestErpMaxBodyPathOverrides:
    def test_declared_upload_routes_resolve_to_expected_ceiling(self, client):
        app = client.raw().app
        overrides = _overrides_from_app(app)
        expectations = {
            "/api/matriculas/extrair": 25 * 1024 * 1024,
            "/api/storage/upload": 15 * 1024 * 1024,
            "/api/storage/upload-multiple": 220 * 1024 * 1024,
            "/api/certidoes/resultados/11111111-1111-1111-1111-111111111111/upload": 25 * 1024 * 1024,
        }
        for path, expected in expectations.items():
            assert _limit_for(overrides, path) == expected, path

    def test_storage_upload_multiple_not_swallowed_by_upload_prefix(self, client):
        """The exact footgun the comment in `app/main.py` calls out:
        `/api/storage/upload-multiple`.startswith(`/api/storage/upload`)
        is True, so WITHOUT its own entry the longest-matching-prefix
        rule would silently resolve the batch route to the single-file
        route's tighter 15 MB cap instead of the 220 MB one it needs."""
        app = client.raw().app
        overrides = _overrides_from_app(app)
        assert _limit_for(overrides, "/api/storage/upload-multiple") != 15 * 1024 * 1024
        assert _limit_for(overrides, "/api/storage/upload-multiple") == 220 * 1024 * 1024

    def test_unrelated_json_routes_stay_on_default(self, client):
        app = client.raw().app
        overrides = _overrides_from_app(app)
        for path in (
            "/api/matriculas/extracoes",
            "/api/storage/delete",
            "/api/certidoes/consultas",
            "/api/certidoes/tipos",
        ):
            assert _limit_for(overrides, path) == _UNMATCHED_SENTINEL, path
