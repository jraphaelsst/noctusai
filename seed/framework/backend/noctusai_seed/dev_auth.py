"""Dev-only pre-seeded auth path — parallel to the prod Supabase path.

WHY
---
The seed promises "a scaffolded product runs end-to-end on day one".
Today that is half-true: backend boots, frontend serves ``/landing``,
but anything past ``/landing`` requires a real Supabase user + org
binding the seed does not provision. Every workspace hits this wall
(N≥3: PF, ERP-imobiliario, the youtube-crawler workspace, therapy
bootstrap) — per the recurrence rule, MUST formalize. This module is
the backend half of that formalization (frontend half:
``VITE_DEV_AUTOLOGIN`` in ``seed/lib/frontend/src/auth.ts``).

DESIGN — a PARALLEL implementation, never a modification of the prod
path. This matches the "no monkey-patching, in production OR tests"
rule: real Supabase Auth + Google SSO + invite flow keep working
untouched; the dev path is a separate factory the product wires
*instead of* the prod ``get_current_user`` when dev-auth is on.

HARD-OFF IN PRODUCTION
----------------------
``make_dev_auth_get_current_user`` returns a dependency ONLY when
``dev_auth_enabled()`` is True. The gate is a single explicit env flag
``SEED_DEV_AUTH`` that MUST be ``true`` AND ``debug`` MUST be on. There
is no implicit activation. Production compose/CI never set
``SEED_DEV_AUTH`` → the factory raises rather than silently returning a
backdoor (silent backdoor = silent error). A loud log line fires on
every activation so it cannot ship unnoticed.

SQLITE LOCAL-DEV BACKEND (shipped — the datastore half)
-------------------------------------------------------
The companion ``noctusai_seed.apply_sqlite_migrations`` materializes a
pre-seeded local SQLite file (identity-mirror tables + the bootstrap
``orgs``/``user``/``membership`` rows) so the synthesized dev identity
resolves against a real, RLS-satisfiable local DB with NO Supabase
project provisioned. It activates under ``DATABASE_BACKEND=sqlite``,
double-gated exactly like ``SEED_DEV_AUTH`` (``config.py``'s
``validate_database_backend`` fails loud if ``sqlite`` in a prod-shaped
env). ``select_get_current_user(settings, prod_dep)`` (below) is the
single seam that CONNECTS this module's dev factory to the canonical
product ``dependencies.py``: dev path iff ``database_backend=="sqlite"``
AND ``dev_auth_enabled``; otherwise the prod path is returned untouched
(parallel, never-modify). The dev path still synthesizes the user from
config — it does not query SQLite for the identity; the SQLite rows
exist so the product's *data* paths (RLS-bound product tables) have a
real org/membership to resolve against on day one.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)

# Well-known dev identity (matches SEED-NEEDS-DEV-AUTH-AND-SQLITE.md §1).
DEV_USER_EMAIL = "dev@noctusai.local"
DEV_TOKEN = "seed-dev-token"  # never a real JWT; only valid in dev-auth mode


class _DevUser:
    """Minimal stand-in matching the attributes the seed reads off a
    Supabase user object (``id``, ``email``, ``user_metadata``,
    ``app_metadata``). Mirrors the prod ``user_response.user`` shape so
    every downstream resolver (``resolve_sso_role``,
    ``get_org_id``-style lambdas, ``make_get_current_user_org``) works
    unchanged."""

    def __init__(self, user_id: str, org_id: str, email: str = DEV_USER_EMAIL):
        self.id = user_id
        self.email = email
        self.user_metadata = {"org_id": org_id, "role": "owner"}
        self.app_metadata = {"provider": "seed-dev-auth"}


def dev_auth_enabled(settings) -> bool:
    """True only when the explicit dev-auth flag is on AND debug is on.

    Two independent gates so a stray ``SEED_DEV_AUTH=true`` in a
    non-debug (production-shaped) env still cannot activate the bypass.
    ``settings`` may expose ``seed_dev_auth`` as a bool field or fall
    back to absent (→ False).
    """
    flag = bool(getattr(settings, "seed_dev_auth", False))
    debug = bool(getattr(settings, "debug", False))
    return flag and debug


def make_dev_auth_get_current_user(
    settings,
    *,
    user_id: Optional[str] = None,
    org_id: Optional[str] = None,
):
    """Factory → a ``get_current_user``-shaped dependency for dev mode.

    Returns the same ``(user, token)`` tuple the prod path returns, so
    it drops straight into
    ``noctusai_lib.api.auth.make_get_current_user_org`` with zero
    per-product code.

    Args:
        settings: the product settings instance (read for the gate +
            optional ``local_dev_user_id`` / ``local_dev_org_id``).
        user_id / org_id: explicit overrides; otherwise sourced from
            ``settings.local_dev_user_id`` / ``settings.local_dev_org_id``
            (falling back to fixed dev sentinels).

    Raises:
        RuntimeError: if called when ``dev_auth_enabled(settings)`` is
            False — fail loud rather than silently minting a bypass.
    """
    if not dev_auth_enabled(settings):
        raise RuntimeError(
            "make_dev_auth_get_current_user() called but dev-auth is OFF "
            "(SEED_DEV_AUTH must be true AND debug must be on). Refusing to "
            "create an auth bypass — this would be a silent production "
            "backdoor."
        )

    resolved_user_id = (
        user_id
        or getattr(settings, "local_dev_user_id", None)
        or "00000000-0000-0000-0000-0000000000de"
    )
    resolved_org_id = (
        org_id
        or getattr(settings, "local_dev_org_id", None)
        or "00000000-0000-0000-0000-0000000000a0"
    )

    logger.warning(
        "[SEED DEV AUTH] backend auth bypass ACTIVE — every request is "
        "authenticated as %s (org=%s). This MUST be off in production.",
        DEV_USER_EMAIL,
        resolved_org_id,
    )

    dev_user = _DevUser(resolved_user_id, resolved_org_id)

    async def _dev_get_current_user(authorization: Optional[str] = Header(None)):
        # Accept any (or no) Authorization header — the dev identity is
        # fixed. We still raise 401 on an obviously malformed non-Bearer
        # value so middleware/tests that assert the contract behave
        # consistently with the prod path.
        if authorization and not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Token malformado")
        return dev_user, DEV_TOKEN

    return _dev_get_current_user


def select_get_current_user(settings, prod_get_current_user):
    """Pick the dev-auth dependency over the prod one when the local
    SQLite dev backend is active — otherwise return the prod path
    unchanged.

    This is the single seam that CONNECTS the already-shipped
    ``make_dev_auth_get_current_user`` to the canonical product
    ``dependencies.py``. It is NOT a rebuild — the dev factory and the
    prod path both already exist; this only chooses between them, with
    zero per-product code (the canonical seed ``dependencies.py`` calls
    it; every product inherits via ``scaffold_product``/propagation).

    Selection rule (the dev path is chosen ONLY when ALL hold):
      * ``settings.database_backend == "sqlite"`` — explicit opt-in to
        the local-dev datastore, and
      * ``dev_auth_enabled(settings)`` — the double-gate
        (``SEED_DEV_AUTH=true`` AND ``debug``) from ``dev_auth.py``.

    The two gates compose: ``sqlite`` cannot itself activate in a
    production-shaped env (``validate_database_backend`` in
    ``config.py`` fails loud), and the dev-auth gate is independently
    enforced. A non-sqlite backend ⇒ the prod path is returned
    untouched (parallel, never-modify — same discipline as the rest of
    this module). Selecting the dev path WITHOUT ``dev_auth_enabled``
    would be a silent backdoor, so the dev path requires BOTH.

    Args:
        settings: product settings (read for ``database_backend`` +
            the dev-auth gate).
        prod_get_current_user: the product's normal get_current_user
            dependency (e.g. ``make_get_current_user(...)`` result).
            Returned as-is whenever the dev path is not selected.

    Returns:
        Either ``make_dev_auth_get_current_user(settings)`` (dev) or
        ``prod_get_current_user`` (prod) — both yield the same
        ``(user, token)`` shape, so the caller's
        ``make_get_current_user_org`` wrapping is identical either way.
    """
    if (
        getattr(settings, "database_backend", "supabase") == "sqlite"
        and dev_auth_enabled(settings)
    ):
        return make_dev_auth_get_current_user(settings)
    return prod_get_current_user
