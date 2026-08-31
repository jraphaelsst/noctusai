"""
Boot-time compliance-by-construction check for `max_body_path_overrides`.

`MaxBodySizeMiddleware` (`noctusai_lib.api.middleware`) caps every inbound
request body at `settings.max_body_bytes` — 1 MB by default, a deliberate
DoS guard for webhooks. A route that legitimately receives a browser
upload (an `UploadFile` parameter, in any of its annotation shapes) needs
a per-route entry in `max_body_path_overrides` to raise that ceiling — and
that map is HAND-MAINTAINED. A forgotten entry doesn't fail fast: it 413s
only for realistically-sized files, so fixture-sized tests keep passing
while real uploads fail in production, before the handler that would have
accepted them ever runs. Five products drifted this way independently
before this module existed.

This is the CLAUDE.md §1 "hand-maintained lists drift and break the
fleet — derive, don't sync by hand; gate pre-push" shape. This module is
the boot-time / primary-mechanism half (`enforce_upload_route_overrides`,
called from `noctusai_seed.app.create_product_app` AFTER every router is
mounted); the commit-time backstop is the
`check_upload_route_body_override` keeper in
`mcp/noctusai/tools/noctus/dev/compliance.py`. See
`KB § PATTERNS/backend/upload-route-body-override-derivation.md`.

Split out of `noctusai_seed.app` (rather than inlined there) so the
route-walk + annotation-unwrap logic can be unit-tested against small
synthetic FastAPI apps without booting a full product app.
"""
from __future__ import annotations

import types
import typing
from typing import Mapping, Optional

from fastapi import FastAPI, UploadFile

# `X | None` (PEP-604) origin is `types.UnionType` on Python 3.10-3.13 —
# a DIFFERENT object from `typing.Union`, the origin `typing.Optional[X]`
# / `typing.Union[X, None]` resolves to. They only became
# interchangeable later. Checking `typing.Union` alone (Python's own
# `get_origin` docs sample) silently misses every PEP-604 annotation on
# the versions this platform actually runs — caught by
# `test_endpoint_declares_upload_file_pep604_union` after this exact
# miss shipped once already in this module's own first draft.
_UNION_ORIGINS = (typing.Union, types.UnionType)

from noctusai_lib.api.middleware import (
    DEFAULT_MAX_BODY_BYTES,
    path_is_covered_by_overrides,
    to_wildcard_pattern,
)


def _annotation_declares_upload_file(annotation: object) -> bool:
    """True if `annotation` is `UploadFile`, or wraps one — recursively,
    so any nesting of the following resolves to True:

    - `UploadFile` (bare)
    - `list[UploadFile]` / `typing.List[UploadFile]`
    - `UploadFile | None` (PEP-604) / `typing.Optional[UploadFile]` /
      `typing.Union[UploadFile, None]`
    - `typing.Annotated[UploadFile, fastapi.File(...)]`
    - any combination, e.g. `list[UploadFile] | None`

    A naive `annotation is UploadFile` equality check misses every
    wrapped form — which is exactly the gap that let
    `erp-imobiliario/routers/storage.py`'s `List[UploadFile]` and
    `social-wiring/routers/chat_router.py`'s `UploadFile | None` ship
    with no override entry: neither is textually `UploadFile` at the
    top level.
    """
    if annotation is UploadFile:
        return True
    origin = typing.get_origin(annotation)
    if origin is None:
        return False
    args = typing.get_args(annotation)
    if origin is typing.Annotated:
        # First arg is the real type; the rest is FastAPI/Pydantic
        # metadata (File(...), etc.) — irrelevant to this check.
        return bool(args) and _annotation_declares_upload_file(args[0])
    if origin is list or origin in _UNION_ORIGINS:
        return any(_annotation_declares_upload_file(a) for a in args)
    return False


def _endpoint_declares_upload_file(endpoint: object) -> bool:
    """`typing.get_type_hints` (not raw `__annotations__` /
    `inspect.signature`) — because a majority of this fleet's router
    modules use `from __future__ import annotations`, which stores every
    annotation as an unevaluated string; only `get_type_hints` resolves
    those against the endpoint's own `__globals__`. `include_extras=True`
    keeps `Annotated[...]` metadata intact so the `File(...)` marker
    survives (unused today, but the recursive unwrap in
    `_annotation_declares_upload_file` handles it either way)."""
    try:
        hints = typing.get_type_hints(endpoint, include_extras=True)
    except Exception as exc:  # noqa: BLE001 — see message below
        raise RuntimeError(
            "upload-route-override derivation could not resolve type "
            f"hints for endpoint {getattr(endpoint, '__qualname__', endpoint)!r}: "
            f"{exc}. This endpoint is already mounted — FastAPI itself "
            "resolved its annotations to build the route, so a failure "
            "here is almost certainly a bug in this derivation, not a "
            "broken route. Surfacing loudly rather than silently "
            "skipping the check (a skipped route could be a real, "
            "un-overridden UploadFile route)."
        ) from exc
    hints.pop("return", None)
    return any(_annotation_declares_upload_file(a) for a in hints.values())


def find_uncovered_upload_routes(
    app: FastAPI,
    max_body_path_overrides: Optional[Mapping[str, object]],
) -> list[tuple[str, str, str]]:
    """Walk every route currently mounted on `app`; return one
    `(pattern_key, route_path, endpoint_qualname)` tuple per
    `UploadFile`-declaring route that has no covering entry in
    `max_body_path_overrides` (see
    `noctusai_lib.api.middleware.path_is_covered_by_overrides` for what
    "covering" means — a pattern OR prefix match, `KEEP_DEFAULT_MAX_BODY`
    counts as covered).

    Pure function, never raises on "found something" (only on the
    internal type-hint-resolution failure described in
    `_endpoint_declares_upload_file`) — so both the boot-time refusal
    (`enforce_upload_route_overrides`) and a test can call it directly
    and make their own decision about what "missing" means.

    `app.routes` at call time must already include every product router
    — call this AFTER `app.include_router(...)` for all of them, never
    before (see `enforce_upload_route_overrides`'s docstring for why).
    """
    missing: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        path = getattr(route, "path", None)
        if endpoint is None or path is None:
            # Mounts (e.g. a future StaticFiles mount) and non-HTTP
            # routes (websockets) don't carry a plain callable endpoint
            # with inspectable parameter annotations — not upload routes
            # by construction.
            continue
        if not _endpoint_declares_upload_file(endpoint):
            continue
        pattern_key = to_wildcard_pattern(path)
        if path_is_covered_by_overrides(pattern_key, max_body_path_overrides):
            continue
        item = (pattern_key, path, getattr(endpoint, "__qualname__", repr(endpoint)))
        if item not in seen:
            seen.add(item)
            missing.append(item)
    return missing


def enforce_upload_route_overrides(
    app: FastAPI,
    max_body_path_overrides: Optional[Mapping[str, object]],
    *,
    product_name: str,
) -> None:
    """Raise `RuntimeError` — refuse to finish booting — if any route
    mounted on `app` declares an `UploadFile` parameter with no matching
    entry in `max_body_path_overrides`.

    MUST be called AFTER every router is mounted (i.e. after step
    9/10 in `noctusai_seed.app.create_product_app`, not from
    `noctusai_lib.api.app_factory.configure_app` / step 8) — `configure_app`
    constructs `MaxBodySizeMiddleware` before any router has been
    registered, so `app.routes` is empty at that point and this check
    would find nothing to refuse, which is worse than not running it at
    all (a false "all clear").

    Refuse-not-null: no silent fallback, no partial check, no env-var
    escape hatch — the only sanctioned opt-out is a route explicitly
    mapped to `noctusai_lib.api.middleware.KEEP_DEFAULT_MAX_BODY`.
    """
    missing = find_uncovered_upload_routes(app, max_body_path_overrides)
    if not missing:
        return
    lines = "\n".join(
        f"  - {pattern_key}   (route={path}, endpoint={qualname})"
        for pattern_key, path, qualname in sorted(missing)
    )
    default_mb = DEFAULT_MAX_BODY_BYTES // (1024 * 1024)
    raise RuntimeError(
        f"{product_name}: {len(missing)} route(s) declare an UploadFile "
        "parameter but have no entry in max_body_path_overrides. They "
        f"would silently inherit the webhook-DoS default cap "
        f"(settings.max_body_bytes, {default_mb} MB unless overridden) "
        "and reject any realistically-sized upload with a 413, before "
        "the handler that would have accepted it ever runs:\n"
        f"{lines}\n"
        "Add each pattern key above to max_body_path_overrides with "
        "either a real byte ceiling, or "
        "noctusai_lib.api.middleware.KEEP_DEFAULT_MAX_BODY if this route "
        "should genuinely stay at the default cap. See "
        "noctusai_lib.api.middleware.MaxBodySizeMiddleware."
    )
