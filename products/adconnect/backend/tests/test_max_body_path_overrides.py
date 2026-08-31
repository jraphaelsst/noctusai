"""Assert `app.main`'s `_MAX_BODY_PATH_OVERRIDES` covers every browser
upload route AND that each key resolves against the route's REAL
mounted path — `/sellout/...`, NOT `/api/sellout/...`.

`sellout.router` carries its own constructor-time `prefix="/sellout"`
(see `routers/sellout.py`), and unlike `auth.router` this product does
not apply a blanket `/api` prefix at mount time either — so an override
keyed on the plausible-looking-but-wrong `/api/sellout/upload-nfe`
would silently never match any real request. This test asserts the
CORRECT bare path resolves AND that the wrong assumed path does not —
the regression guard for exactly that mistake.
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


class TestAdConnectMaxBodyPathOverrides:
    def test_declared_upload_routes_resolve_to_expected_ceiling(self, client):
        app = client.raw().app
        overrides = _overrides_from_app(app)
        expectations = {
            "/sellout/upload-nfe": 10 * 1024 * 1024,
            "/sellout/upload-attachment": 30 * 1024 * 1024,
        }
        for path, expected in expectations.items():
            assert _limit_for(overrides, path) == expected, path

    def test_api_prefixed_assumption_does_not_match(self, client):
        """`sellout.router` is NOT mounted under `/api` — confirm the
        wrong-but-plausible `/api/sellout/upload-nfe` path is NOT
        covered, proving the entries were keyed on the verified real
        path rather than an inferred one."""
        app = client.raw().app
        overrides = _overrides_from_app(app)
        assert _limit_for(overrides, "/api/sellout/upload-nfe") == _UNMATCHED_SENTINEL
        assert _limit_for(overrides, "/api/sellout/upload-attachment") == _UNMATCHED_SENTINEL

    def test_unrelated_json_routes_stay_on_default(self, client):
        app = client.raw().app
        overrides = _overrides_from_app(app)
        for path in ("/sellout/submit", "/sellout/list", "/cart", "/products"):
            assert _limit_for(overrides, path) == _UNMATCHED_SENTINEL, path
