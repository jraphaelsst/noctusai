"""Test helpers for the credential resolution module.

Shipped 2026-05-20 by `erp-imobiliario-test-baseline-recovery` (formalize
threshold tripped after N=3 instances of the same `patch(
"noctusai_lib.config.credentials._get_public_client", return_value=...)`
shape recurred across ERP `tests/conftest.py`, ERP `test_email_service.py`
(two sites), and the LLM mount-smoke `test_standard_llm_smoke.py`).

`_get_public_client` is the seed's external Supabase boundary: it
constructs the public-anon-key client used by feature flags, LLM-router,
and other unauthenticated read paths. App boot calls
`configure_credentials(url=..., anon_key=...)` once via `create_product_app`;
tests booting against a `MockSupabaseClient` need that boundary to return
their mock instead of attempting `create_client(url="")` (which crashes
"Supabase URL is required").

`patch_credentials_to_mock(mock_sb)` is the canonical patcher — returns
an unstarted `unittest.mock.patch` context manager so existing
`with patch(...), patch(...)`-chained fixtures can compose it in.

Why a thin helper and not `bind_credentials_module_to_mock(mock_sb)` like
`bind_consent_module_to_mock`? The consent module stores its FastAPI deps
as module-level slots (configurable via `configure_consent_module`); the
credentials module exposes a module-level function `_get_public_client()`
that's invoked at every credential resolution. A "bind" helper would have
to monkey-patch the function pointer, which is what `unittest.mock.patch`
already does. Wrapping the patch as a named helper centralizes the import
path (so a future rename in the credentials module surfaces in ONE place)
and makes test fixtures self-documenting.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import _patch, patch


def patch_credentials_to_mock(mock_sb: Any) -> _patch:
    """Return an unstarted patcher that points the credentials module's
    `_get_public_client` at `mock_sb`.

    Use inside a product's `client` fixture, composed with the
    `DatabaseModule.get_*` patches::

        with patch("noctusai_seed.database.DatabaseModule.get_client",
                   return_value=mock_sb), \\
             patch("noctusai_seed.database.DatabaseModule.get_admin_client",
                   return_value=mock_sb), \\
             patch_credentials_to_mock(mock_sb):
            from app.main import app
            bind_consent_module_to_mock(mock_sb)
            tc = TestClient(app)
            yield AuthClient(tc, mock_sb)

    Also valid as a stand-alone context manager for per-test patching::

        with patch_credentials_to_mock(mock_sb):
            result = service_call_that_resolves_credentials(...)
    """
    return patch(
        "noctusai_lib.config.credentials._get_public_client",
        return_value=mock_sb,
    )


__all__ = ["patch_credentials_to_mock"]
