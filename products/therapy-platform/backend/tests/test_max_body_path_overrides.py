"""Assert `app.main`'s `_MAX_BODY_PATH_OVERRIDES` covers the attachment
upload route AND that the key actually RESOLVES against the route's
real mounted path — not just present in the dict.
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


class TestTherapyMaxBodyPathOverrides:
    def test_declared_upload_route_resolves_to_expected_ceiling(self, client):
        app = client.raw().app
        overrides = _overrides_from_app(app)
        assert _limit_for(overrides, "/api/attachments/upload") == 60 * 1024 * 1024

    def test_unrelated_json_routes_stay_on_default(self, client):
        app = client.raw().app
        overrides = _overrides_from_app(app)
        for path in ("/api/attachments/signed-url", "/api/patients", "/api/messaging"):
            assert _limit_for(overrides, path) == _UNMATCHED_SENTINEL, path
