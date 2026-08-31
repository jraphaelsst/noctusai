"""Assert `app.main`'s `_MAX_BODY_PATH_OVERRIDES` covers every browser
upload route AND that each `*`-wildcard pattern actually RESOLVES
against the route's real mounted path.

Presence alone is not enough: the pattern matches on EXACT segment
count AND literal equality on every non-`*` segment (see
`noctusai_lib.api.middleware.MaxBodySizeMiddleware`'s docstring) — a
sibling route with the SAME segment count but a different literal leaf
(`/api/marcas/{id}/acessos` vs `/api/marcas/{id}/logo`) must NOT match.
A bare "key in dict" check would never catch either failure mode.
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


class TestIgIgMaxBodyPathOverrides:
    def test_declared_upload_routes_resolve_to_expected_ceiling(self, client):
        app = client.raw().app
        overrides = _overrides_from_app(app)
        expectations = {
            "/api/pautas/11111111-1111-1111-1111-111111111111/pecas": 60 * 1024 * 1024,
            "/api/marcas/22222222-2222-2222-2222-222222222222/logo": 3 * 1024 * 1024,
        }
        for path, expected in expectations.items():
            assert _limit_for(overrides, path) == expected, path

    def test_same_segment_count_different_leaf_does_not_match(self, client):
        """`/api/marcas/{cliente_id}/acessos/{acesso_id}` -> the SAME
        4-segment shape as the marcas/{id}/logo pattern would have if
        the literal leaf differed — regression guard for a pattern that
        matched on segment count alone and forgot the literal check."""
        app = client.raw().app
        overrides = _overrides_from_app(app)
        assert (
            _limit_for(overrides, "/api/marcas/22222222-2222-2222-2222-222222222222/acessos")
            == _UNMATCHED_SENTINEL
        )

    def test_unrelated_json_routes_stay_on_default(self, client):
        app = client.raw().app
        overrides = _overrides_from_app(app)
        for path in (
            "/api/pautas",
            "/api/pautas/calendario",
            "/api/marcas",
            "/api/marcas/22222222-2222-2222-2222-222222222222",
        ):
            assert _limit_for(overrides, path) == _UNMATCHED_SENTINEL, path
