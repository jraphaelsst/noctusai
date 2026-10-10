"""Refuse to run a hermetic test session against a LIVE Supabase project.

THE INCIDENT (social-wiring, 2026-10-09): a worktree carried the primary
``.env`` (prod service-role creds); a router test using the real client path
wrote fixture rows (a real customer's Facebook page id under a non-existent
org) into PRODUCTION, and the live leadgen webhook then routed real leads to
that ghost org. Every product inherits this guard through the ``pytest11``
plugin (``pytest_plugin``) -- by construction, no per-product wiring.

Rule: if the process env points at the prod project ref or any
``*.supabase.co`` host, and ANY collected test is not explicitly marked
``realdb`` (the sanctioned live-DB tier), the session aborts before a single
test runs. ``realdb`` tests carry their own prod-refusal
(``realdb.get_realdb_credentials``).
"""
from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping

PROD_PROJECT_REF = "nyplttplcoyiiqjrvtiw"
_SUPABASE_HOST = re.compile(r"[a-z0-9]+\.supabase\.(co|com|in)\b", re.IGNORECASE)
_ENV_KEYS = (
    "SUPABASE_URL", "SUPABASE_PROJECT_REF", "SUPABASE_DB_URL", "DATABASE_URL",
    "DIRECT_URL", "POSTGRES_URL",
)


def live_supabase_env_keys(environ: Mapping[str, str] | None = None) -> list[str]:
    """Names (never values) of env keys that point at a live Supabase project."""
    env = os.environ if environ is None else environ
    hits = []
    for key in _ENV_KEYS:
        value = env.get(key) or ""
        if PROD_PROJECT_REF in value or _SUPABASE_HOST.search(value):
            hits.append(key)
    return hits


def live_settings_keys(settings_cls=None) -> list[str]:
    """Defense in depth: names of RESOLVED seed-settings fields that point at a
    live project (what a product's settings would actually load, incl. any
    ``.env`` the no-env-file seam did not drop). Names only, never values.
    ``settings_cls`` is the injection seam (default: the seed base)."""
    if settings_cls is None:
        from noctusai_lib.config.settings import BaseAppSettings as settings_cls
    try:
        resolved = settings_cls()
    except Exception as exc:  # noqa: BLE001 -- loud, not silent
        raise RuntimeError(
            f"live_db_guard: cannot resolve seed settings ({type(exc).__name__}); refusing"
        ) from exc
    hits = []
    for name in ("supabase_url",):
        value = str(getattr(resolved, name, "") or "")
        if PROD_PROJECT_REF in value or _SUPABASE_HOST.search(value):
            hits.append(f"settings.{name}")
    return hits


def non_realdb_item_count(items: Iterable) -> int:
    return sum(1 for it in items if it.get_closest_marker("realdb") is None)


def assert_hermetic(
    items: Iterable, environ: Mapping[str, str] | None = None, settings_cls=None,
) -> None:
    """Raise ``RuntimeError`` (loud) when a live DB env meets hermetic tests."""
    hits = live_supabase_env_keys(environ)
    if environ is None:  # real session: also inspect what settings RESOLVE
        hits += live_settings_keys(settings_cls)
    if not hits:
        return
    n = non_realdb_item_count(list(items))
    if n == 0:
        return
    raise RuntimeError(
        f"REFUSING to run {n} hermetic test(s): {', '.join(hits)} point at a LIVE "
        "Supabase project (prod ref or *.supabase.co). Tests build real clients "
        "from env and would WRITE to production (2026-10-09 ghost-org incident). "
        "Unset those variables (do not symlink/source the platform .env into a "
        "test shell); only tests marked `realdb` may target a live project."
    )
