"""Real-DB test credential resolution — opt-in, prod-refusing.

Formalized 2026-09-23 (N=3: `core`, `adconnect`, `erp-imobiliario` each
carried a byte-similar `_get_credentials()` copy in their
`tests/realdb/conftest.py`) after a live incident: every dev's local
`.env` carries the **production** Supabase project's `SUPABASE_URL` +
`SUPABASE_SERVICE_ROLE_KEY` (the dev fleet is dormant — see
`KB § PATTERNS/devops/dev-fleet-dormant.md` — there is no separate
dev-project pair to point at instead). The old helper gated on those two
vars merely being *set*, so every local `pytest` / `noctus.dev.pytest`
run for `core`'s real-DB suite silently created organizations named
``"RealDB Test test-realdb-*"`` in **production**.

Those orgs then leaked permanently: core migration 053
(`products/core/backend/migrations/053_audit_trail_expansion.sql`) added
the ``guard_audit_logs_append_only`` trigger on ``public.audit_logs``, so
the session teardown's ``DELETE FROM audit_logs WHERE org_id = ...`` is
refused by the DB — and the refusal was swallowed by a bare
``except Exception: pass``. The subsequent ``DELETE FROM organizations``
then fails on FK 23503 (audit_logs rows still reference the org) and is
*also* swallowed. Net effect: the test org, and its audit-log rows,
persist in prod forever. Five such orgs existed in prod as of 2026-09-23.

This module closes that hole with two independent, fail-loud gates:

1. **Explicit opt-in.** ``NOCTUS_REALDB_TESTS=1`` must be set. Merely
   having ``SUPABASE_URL`` / ``SUPABASE_SERVICE_ROLE_KEY`` in the
   environment (true for every dev's `.env`) is no longer sufficient.
2. **Prod-ref refusal.** Even with the opt-in set, if the resolved
   ``SUPABASE_URL`` points at the production project
   (``nyplttplcoyiiqjrvtiw``), credentials are refused. Real-DB runs
   must target a disposable Supabase branch, never prod.

Both gates fail via ``pytest.skip`` with a loud, specific reason — never
a silent pass-through — per the platform's no-silent-errors rule.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlparse

import pytest

__all__ = ["get_realdb_credentials"]

# The production Supabase project ref. Mirrors
# `DEFAULT_PROJECT_REF` in `mcp/noctusai/tools/noctus/dev/verify_db_guards.py`
# (and the same literal `migrate_product.py` defaults `project_ref=` to).
# `mcp/noctusai` ships its own `pyproject.toml` as an independent installable
# package that product test suites do not depend on, so it cannot be
# imported from here — this is the intentional, documented seed-lib sibling
# of that constant, not an undocumented duplicate. Keep both in sync by hand
# until the two surfaces share a common importable home.
_PROD_PROJECT_REF = "nyplttplcoyiiqjrvtiw"

_OPT_IN_VAR = "NOCTUS_REALDB_TESTS"

_SUPABASE_HOST_RE = re.compile(r"^([a-z0-9]+)\.supabase\.co$")


def _project_ref_from_url(url: str) -> str:
    """Extract the Supabase project ref (subdomain) from a project URL.

    ``https://<ref>.supabase.co`` -> ``<ref>``. Returns ``""`` for a URL
    that doesn't match that shape (e.g. a local/self-hosted stack) — such
    a URL can never collide with `_PROD_PROJECT_REF`, so it is treated as
    safe rather than raising.
    """
    host = urlparse(url).hostname or ""
    match = _SUPABASE_HOST_RE.match(host)
    return match.group(1) if match else ""


def get_realdb_credentials() -> tuple[str, str]:
    """Return ``(url, service_role_key)`` for real-DB integration tests.

    Skips (never silently passes) unless ALL of:

    1. ``NOCTUS_REALDB_TESTS=1`` is set explicitly;
    2. ``SUPABASE_URL`` and ``SUPABASE_SERVICE_ROLE_KEY`` are both set;
    3. the URL's project ref is NOT the production ref
       (`_PROD_PROJECT_REF`) — refused even when (1) is set.
    """
    if os.environ.get(_OPT_IN_VAR, "") != "1":
        pytest.skip(
            f"{_OPT_IN_VAR} not set to '1' — real-DB tests are opt-in only. "
            "Every dev .env carries PRODUCTION Supabase credentials (the dev "
            "fleet is dormant), so this suite no longer runs on mere "
            "credential presence. Point SUPABASE_URL at a disposable "
            f"Supabase branch and set {_OPT_IN_VAR}=1 to run it."
        )

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        pytest.skip(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — skipping real-DB tests"
        )

    ref = _project_ref_from_url(url)
    if ref == _PROD_PROJECT_REF:
        pytest.skip(
            f"SUPABASE_URL resolves to the PRODUCTION project ({_PROD_PROJECT_REF}) — "
            f"refusing to run real-DB tests against prod even with {_OPT_IN_VAR}=1. "
            "Point SUPABASE_URL at a disposable Supabase branch instead."
        )

    return url, key
